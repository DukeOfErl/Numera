"""Whether a resolved problem stops being reported. Real Postgres only.

The resolution rule is a `join`, and a `join` lives in SQL. A double accepts any
string, so every offline test in `test_pending.py` would pass with the join written
backwards, with the case-folding dropped, or with `progress.at < asked.last_seen`
inverted — and two of those three make the monitor **permanently silent**, which is
the worst failure available to it: an empty report is how a quiet day looks.

So these write rows into a throwaway table and read the real answer back. Run with
`pytest -m network`. Skipped rather than failed where no database is configured, so
a contributor without one does not see red.
"""

from __future__ import annotations

import tomllib
import uuid
from pathlib import Path

import pytest

from scinumbers_ask.pending import waiting
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
def table():
    """A throwaway table, dropped afterwards. Never the real `trail`: these tests
    write rows, and rows left in the table an operator reads make it untrustworthy."""
    engine = engine_from_url(_url())
    name = f"trail_test_{uuid.uuid4().hex[:8]}"
    store = TrailStore(engine=engine, table=name)
    assert store.ensure_schema(), "could not create the test table"
    yield engine, name
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(f"drop table if exists {name}"))
    engine.dispose()


def _write(engine, name, rows):
    """Rows in the order given, each a second apart, so "later" is unambiguous."""
    from sqlalchemy import text

    with engine.begin() as conn:
        for index, (event, email, stamped) in enumerate(rows):
            conn.execute(
                text(
                    f"insert into {name} (at, event, detail, user_email) values "
                    f"(now() - make_interval(secs => :ago), :event, "
                    f"jsonb_build_object('email', :email), :stamped)"
                ),
                {
                    "ago": (len(rows) - index) * 60,
                    "event": event,
                    "email": email,
                    "stamped": stamped,
                },
            )


def test_a_request_with_no_later_progress_is_reported(table):
    engine, name = table
    _write(engine, name, [("signin.resend_requested", "stuck@example.org", None)])
    no_email, _ = waiting(engine, table=name)
    assert [w.address for w in no_email] == ["stuck@example.org"]


def test_a_request_answered_by_verification_stops_being_reported(table):
    """`signin.refused` sits behind the verified-address check, so seeing it later
    is proof the address got verified -- the reader's problem moved on."""
    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.resend_requested", "moved@example.org", None),
            ("signin.refused", "moved@example.org", None),
        ],
    )
    no_email, not_enrolled = waiting(engine, table=name)
    assert no_email == [], "a resolved request was reported again"
    assert [w.address for w in not_enrolled] == ["moved@example.org"], (
        "they are now in the other queue, which is the point"
    )


def test_an_account_that_was_admitted_stops_being_reported(table):
    """The identity stamp writes `user_email` only onto a signed-in session's
    records, so its presence is proof the door opened."""
    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.refused", "enrolled@example.org", None),
            ("question.asked", None, "enrolled@example.org"),
        ],
    )
    no_email, not_enrolled = waiting(engine, table=name)
    assert not_enrolled == [], "an enrolled account was still reported as waiting"
    assert no_email == []


def test_progress_before_the_request_does_not_resolve_it(table):
    """The comparison is directional. `progress.at < asked.last_seen` inverted
    would silence every genuine request from anyone who had ever signed in, which
    is the population most likely to ask."""
    engine, name = table
    _write(
        engine,
        name,
        [
            ("question.asked", None, "again@example.org"),
            ("signin.resend_requested", "again@example.org", None),
        ],
    )
    no_email, _ = waiting(engine, table=name)
    assert [w.address for w in no_email] == ["again@example.org"], (
        "an old success was treated as answering a new problem"
    )


def test_two_spellings_of_one_address_are_one_person(table):
    """`accounts.lookup` folds case, so the provider's spelling and the row's may
    differ. Without folding here, an admitted `Tester@` would not resolve a request
    from `tester@` and the operator would chase a solved problem forever."""
    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.refused", "Mixed@Example.org", None),
            ("question.asked", None, "mixed@example.org"),
        ],
    )
    _, not_enrolled = waiting(engine, table=name)
    assert not_enrolled == [], "case alone made one person look like two"


def test_the_window_bounds_how_far_back_it_looks(table):
    """An address abandoned long ago ages out rather than nagging forever."""
    engine, name = table
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                f"insert into {name} (at, event, detail) values "
                f"(now() - make_interval(days => 40), 'signin.resend_requested', "
                f"jsonb_build_object('email', 'ancient@example.org'))"
            )
        )
    assert waiting(engine, hours=24 * 30, table=name)[0] == [], "outside the window"
    assert [w.address for w in waiting(engine, hours=24 * 60, table=name)[0]] == [
        "ancient@example.org"
    ]
