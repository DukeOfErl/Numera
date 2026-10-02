"""The view's connection: its own role, its own password, and a host from Neon by name.

Never the owner's URL. `neon.connection_url` returns a URL with a password in it,
and for the owner that is a credential the view must not hold even in memory: a
bug in a page that can only read cannot become a write. So the host is fetched
on its own (`neon.endpoint_host`) and the password is the one
`scinumbers-monitor-grant` printed, read from the operator's environment. No URL is
written to disk (ADR-1310).
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from collections.abc import Mapping

from scinumbers_ask import neon, trail_store

ROLE = "scinumbers_monitor"
PASSWORD_ENV = "SCINUMBERS_MONITOR_DB_PASSWORD"
REQUIRED_ENV = ("NEON_API_KEY", "NEON_PROJECT_ID", PASSWORD_ENV)


class Missing(RuntimeError):
    """Settings the view cannot start without. Names every one, not the first."""


def monitor_url(host: str, password: str, *, database: str = neon.DEFAULT_DATABASE) -> str:
    # Quoted: a generated password is alphanumeric, but one set by hand need not be,
    # and an `@` or `/` in it would silently move the host.
    secret = urllib.parse.quote(password, safe="")
    return f"postgresql+psycopg://{ROLE}:{secret}@{host}/{database}?sslmode=require"


def resolve(
    branch: str,
    env: Mapping[str, str] = os.environ,
    *,
    database: str = neon.DEFAULT_DATABASE,
    opener=urllib.request.urlopen,
) -> str:
    """The view's URL for the branch called `branch`."""
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        raise Missing(
            f"set {', '.join(missing)} before starting the view. The password is the one "
            "scinumbers-monitor-grant printed; run it again to get a new one."
        )
    api_key, project = env["NEON_API_KEY"], env["NEON_PROJECT_ID"]
    branch_id = neon.branch_id(api_key, project, branch, opener=opener)
    host = neon.endpoint_host(api_key, project, branch_id, opener=opener)
    return monitor_url(host, env[PASSWORD_ENV], database=database)


def engine(url: str):
    """With `trail_store`'s connect timeout and pool recycle, not new numbers."""
    return trail_store.engine_from_url(url)
