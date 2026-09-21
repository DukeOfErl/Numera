"""Neon's control plane: a branch's *name* to the connection URL for that branch.

Two calls and no state. It exists because the enrolment command must write into
the branch the deployed app reads, and the only other way to get that URL onto an
operator's laptop is to keep it in a file -- which is the spare credential
`.streamlit/secrets.toml.example` forbids, and the wrong branch by default.

**Nothing here is cached and nothing is written down.** The URL carries the
password; it is built for one insert and goes when the process does.

**This raises where `allowance.py` swallows.** That module puts a caption on a
page that is already drawn, so every failure has the same right answer: say
nothing. Here an operator is watching a command they typed, and a failure they
are not shown is an enrolment they believe happened. Opposite policies, on
purpose.

Verified against api-docs.neon.tech on 2026-09-18: `GET
/projects/{id}/branches?search=` filters by *partial* name or id, and `GET
/projects/{id}/connection_uri` takes `branch_id`, `database_name`, `role_name`
and `pooled`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API = "https://console.neon.tech/api/v2"

#: Long enough for a control-plane call over a slow link, short enough that an
#: operator waiting at a prompt sees a failure rather than a hang.
TIMEOUT_S = 30

#: Neon's own defaults for a new project. Flags on the command rather than
#: constants inside it, because a project can rename either.
DEFAULT_DATABASE = "neondb"
DEFAULT_ROLE = "neondb_owner"


#: As `enrol.REFUSING_STATUSES`, and for the same reason.
REFUSING_STATUSES = (401, 403)

API_KEY_REFUSED = (
    "Neon refused the API key, so nothing was enrolled and no branch was read. If you "
    "created it with an expiry it has most likely reached it: make a new one under "
    "Account settings, API keys, and set NEON_API_KEY to it. Check NEON_PROJECT_ID too "
    "-- a key that cannot see the project is refused the same way."
)


class ApiKeyRefused(RuntimeError):
    """The operator's Neon API key was refused. Not a wrong branch name.

    Distinct from `BranchNotFound` on purpose: that one lists the branches it
    found, which is the wrong help entirely when the answer is that none could be
    read.
    """


class BranchNotFound(RuntimeError):
    """No branch of that exact name, or more than one. Nothing was written.

    Carries the names that *were* found, because the operator's next move is to
    look at the list and spot the typo -- and a refusal that only says "not
    found" makes them go to the console to do it.
    """


def _get(path: str, api_key: str, params: dict[str, str], opener) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    )
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as refused:
        if refused.code in REFUSING_STATUSES:
            raise ApiKeyRefused(API_KEY_REFUSED) from refused
        raise


def branch_id(api_key: str, project: str, name: str, *, opener=urllib.request.urlopen) -> str:
    """The id of the branch called exactly `name`.

    `search` matches partially, so `alpha` also returns `alpha-2` and `dev`
    returns `dev-scratch`. Taking the first result would enrol a tester into
    whichever branch Neon happened to list first, which is the silent wrong write
    this whole path exists to prevent -- so the match is narrowed to exact
    equality here, and anything other than exactly one is a refusal.
    """
    payload = _get(f"/projects/{project}/branches", api_key, {"search": name}, opener)
    branches = payload.get("branches") or []
    found = [b for b in branches if b.get("name") == name]
    if len(found) != 1:
        names = ", ".join(sorted(b.get("name", "?") for b in branches)) or "none"
        raise BranchNotFound(f'no single Neon branch is named "{name}". Found: {names}')
    return found[0]["id"]


def connection_url(
    api_key: str,
    project: str,
    branch: str,
    *,
    database: str = DEFAULT_DATABASE,
    role: str = DEFAULT_ROLE,
    opener=urllib.request.urlopen,
) -> str:
    """The pooled connection URL for one branch, ready for SQLAlchemy.

    `pooled=true` asks for the `-pooler` host: the direct endpoint is for
    long-lived connections and caps out around a hundred of them, which is the
    same reason the app's own URL carries it.

    The scheme is rewritten from `postgresql://` to `postgresql+psycopg://`
    because SQLAlchemy reaches for psycopg2 otherwise, and psycopg2 is not a
    dependency here -- the same correction `.streamlit/secrets.toml.example`
    tells an operator to make by hand to a URL copied from the console.
    """
    payload = _get(
        f"/projects/{project}/connection_uri",
        api_key,
        {
            "branch_id": branch,
            "database_name": database,
            "role_name": role,
            "pooled": "true",
        },
        opener,
    )
    url = payload.get("uri")
    if not url:
        raise RuntimeError(f"Neon returned no connection uri for branch {branch}")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url
