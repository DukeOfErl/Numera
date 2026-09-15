"""The trail store against a real Postgres. Deselected by default.

These exist because two properties of the store cannot be asserted against a
double, and writing a double that appeared to assert them would be worse than
leaving them unasserted:

- **A slow write is bounded.** `record` has no client-side deadline -- no branch,
  no timer, no cancellation. The only thing bounding it is `SET LOCAL
  statement_timeout`, which the *server* enforces. A `time.sleep` in a fake
  connection would measure the fake. Varying duration means varying it against
  the machinery that actually bounds it.
- **The SQL is valid.** A double accepts any string, so `_SCHEMA`, `_INSERT` and
  the `jsonb` cast would survive a syntax error in every offline test.

Run with `pytest -m network`. Skipped, not failed, where no destination is
configured: a contributor without a database must not see a red suite.
"""

from __future__ import annotations

import time
import tomllib
import uuid
from pathlib import Path

import pytest

from scinumbers_ask import trail_store
from scinumbers_ask.trail_store import TrailStore, engine_from_url

pytestmark = pytest.mark.network

SECRETS = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"


def _url() -> str:
    if not SECRETS.exists():
        pytest.skip("no .streamlit/secrets.toml; nothing to connect to")
    try:
        return tomllib.loads(SECRETS.read_text())["connections"]["usage"]["url"]
    except (KeyError, tomllib.TOMLDecodeError):
        pytest.skip("no [connections.usage] url configured")


@pytest.fixture
def store():
    """A store on its own throwaway table, dropped afterwards.

    Its own table rather than the real one: these tests write rows, and a test
    that leaves rows in the table an operator reads would make the trail's own
    data untrustworthy.
    """
    engine = engine_from_url(_url())
    table = f"trail_test_{uuid.uuid4().hex[:8]}"
    store = TrailStore(engine=engine, table=table)
    assert store.ensure_schema(), "could not create the test table"
    yield store
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(f"drop table if exists {table}"))
    engine.dispose()


def test_the_schema_and_the_insert_are_valid_sql(store):
    """Offline, a double accepts any string; a syntax error would survive."""
    from sqlalchemy import text

    assert store.record(
        "searched",
        session_id="s1",
        question_id="q1",
        run_label="dev",
        detail={"matched": 12, "terms": ["ribosome"]},
    )
    with store.engine.begin() as conn:
        row = conn.execute(
            text(f"select session_id, question_id, event, detail from {store.table}")
        ).one()
    assert row.session_id == "s1"
    assert row.question_id == "q1"
    assert row.event == "searched"
    # Read back through jsonb, so the cast is exercised rather than the string.
    assert row.detail == {"matched": 12, "terms": ["ribosome"]}


def test_a_statement_that_runs_too_long_is_cancelled_rather_than_waited_out(store):
    """The scenario "the destination is slow", closed against the real server.

    Neon's own default `statement_timeout` is `0` -- unlimited -- so without
    `SET LOCAL` this would block for the full sleep. Asserting the elapsed time is
    the point: a test that only checked the return value would pass just as well
    if the timeout never fired.
    """
    from sqlalchemy import text

    sleep_for = trail_store.STATEMENT_TIMEOUT_MS / 1000 * 3
    started = time.monotonic()
    with pytest.raises(Exception):  # noqa: B017 - the driver's own cancellation
        with store.engine.begin() as conn:
            conn.execute(text(f"set local statement_timeout = {trail_store.STATEMENT_TIMEOUT_MS}"))
            conn.execute(text(f"select pg_sleep({sleep_for})"))
    elapsed = time.monotonic() - started
    assert elapsed < sleep_for, f"waited {elapsed:.1f}s for a {sleep_for:.1f}s statement"


def test_the_timeout_does_not_leak_onto_the_next_pooled_transaction(store):
    """`SET LOCAL` is scoped to the transaction; the pooler hands the connection on.

    A leak would impose our 2s ceiling on whatever borrowed the connection next,
    which for a shared pooler is somebody else's query.
    """
    from sqlalchemy import text

    with store.engine.begin() as conn:
        conn.execute(text(f"set local statement_timeout = {trail_store.STATEMENT_TIMEOUT_MS}"))
    with store.engine.begin() as conn:
        assert conn.execute(text("show statement_timeout")).scalar_one() == "0"


def test_an_unreachable_host_does_not_raise_out_of_record():
    """Fail-open against a real failure, not a fake one.

    The offline tests raise a chosen exception from a double; this reaches a host
    that does not exist and confirms whatever the driver actually raises is
    swallowed too. `connect_timeout` is what stops this hanging.
    """
    trail_store.reset_counters()
    engine = engine_from_url(
        "postgresql+psycopg://u:p@no-such-host.invalid:5432/db?sslmode=disable"
    )
    store = TrailStore(engine=engine, table="trail")
    assert store.ensure_schema() is False
    assert store.record("searched") is False
    assert trail_store.failures() >= 1
    engine.dispose()
