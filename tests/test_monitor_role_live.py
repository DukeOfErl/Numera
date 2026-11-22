"""The monitor's role, against a real branch: what Postgres refuses it, and what it allows.

Grants are the database's decision, so no double can say whether they hold. Runs
against the branch in `.streamlit/secrets.toml` (`dev`) after
`numera-monitor-grant --branch dev`, with `NUMERA_MONITOR_DB_PASSWORD` set
to the password it printed. Skips without either.

**The same probes run as the owner first, and must not be refused.** That is the
canary: `refused()` decides on an exception, and a probe that fails for an unrelated
reason -- a typo, a missing table -- would read as a refusal and turn every
assertion below into a false all-clear. Watching the owner get through with the same
statements is what shows the refusals are about the role. Nothing is ever kept: each
probe runs in a transaction that is rolled back.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from numera_ask.trail_store import engine_from_url
from numera_monitor.connection import PASSWORD_ENV, monitor_url

pytestmark = pytest.mark.network

SECRETS = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"

#: Each must be refused to the monitor and allowed to the owner.
FORBIDDEN = {
    "write to the trail": "insert into trail (event) values ('monitor.live_probe')",
    "change the trail": "update trail set event = event where false",
    "delete from the trail": "delete from trail where false",
    "read a key": "select openrouter_key from accounts limit 1",
    "read a key's hash": "select openrouter_key_hash from accounts limit 1",
    "read every column of accounts": "select * from accounts limit 1",
    "create a table": "create table monitor_live_probe (a int)",
}
ALLOWED = {
    "read the trail": "select count(*) from trail",
    "read who is enrolled": "select email, disabled from accounts limit 1",
}


def _owner_url() -> str:
    if not SECRETS.exists():
        pytest.skip("no .streamlit/secrets.toml; nothing to connect to")
    try:
        return tomllib.loads(SECRETS.read_text())["connections"]["usage"]["url"]
    except (KeyError, tomllib.TOMLDecodeError):
        pytest.skip("no [connections.usage] url configured")


@pytest.fixture(scope="module")
def owner():
    engine = engine_from_url(_owner_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def monitor():
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        pytest.skip(f"{PASSWORD_ENV} unset; run numera-monitor-grant --branch dev first")
    host = urlsplit(_owner_url()).hostname
    engine = engine_from_url(monitor_url(host, password))
    yield engine
    engine.dispose()


def refused(engine, statement: str) -> bool:
    """Whether Postgres refused `statement`. Never commits."""
    from sqlalchemy import exc, text

    conn = engine.connect()
    trans = conn.begin()
    try:
        # Read-write explicitly, so what is measured is the grants. The role's
        # `default_transaction_read_only` would refuse every write by itself, and a
        # role that can `set transaction read write` is only as read-only as its
        # grants.
        conn.execute(text("set transaction read write"))
        conn.execute(text(statement))
        return False
    except exc.DBAPIError as error:
        sqlstate = getattr(error.orig, "sqlstate", None)
        # 42501 insufficient_privilege. Anything else is a broken probe, not a
        # refusal, and must not count as one.
        assert sqlstate == "42501", f"{statement!r} failed for another reason: {error}"
        return True
    finally:
        trans.rollback()
        conn.close()


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_the_owner_is_not_refused_the_probe(owner, name):
    """The canary. If this fails, the probe is broken and the refusals prove nothing."""
    assert not refused(owner, FORBIDDEN[name])


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_the_monitor_is_refused(monitor, name):
    assert refused(monitor, FORBIDDEN[name])


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_the_monitor_can_read_what_the_view_needs(monitor, name):
    assert not refused(monitor, ALLOWED[name])


def test_the_monitor_connects_as_itself(monitor):
    from sqlalchemy import text

    with monitor.connect() as conn:
        assert conn.execute(text("select current_user")).scalar() == "numera_monitor"
