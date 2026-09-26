"""Whether a resolved problem stops being reported. Real Postgres only.

These caught two things on their first run, which is the argument for having them.
The query itself was right -- all four semantics were confirmed against real rows.
The *test helper* was not: `jsonb_build_object` with a bound parameter raises
`IndeterminateDatatype`, and every offline test had passed because a double accepts
any string. A live test whose own SQL is wrong still tells you something, and it
told it immediately.


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


#: The same shape `trail_store._INSERT` uses, and for the reason its failure taught:
#: `jsonb_build_object('email', :email)` with a bound parameter raises
#: `IndeterminateDatatype` -- the function takes `any`, so Postgres cannot infer an
#: untyped parameter's type from it, and every offline test passed because a double
#: accepts any string. `cast(:detail as jsonb)` says the type outright, which is
#: what the store already does against this same database.
_INSERT = """
insert into {name} (at, event, detail, user_email)
values (now() - cast(:ago as interval), :event, cast(:detail as jsonb), :stamped)
"""


def _write(engine, name, rows):
    """Rows in the order given, a minute apart, so "later" is unambiguous."""
    import json

    from sqlalchemy import text

    with engine.begin() as conn:
        for index, (event, email, stamped) in enumerate(rows):
            conn.execute(
                text(_INSERT.format(name=name)),
                {
                    "ago": f"{(len(rows) - index) * 60} seconds",
                    "event": event,
                    "detail": json.dumps({"email": email} if email else {}),
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


def test_an_unenrolled_account_is_reported_until_it_is_admitted(table):
    """The query that was broken, asserted directly.

    Progress is **per stage**, and one shared definition made `signin.refused`
    appear in its own progress set — so every unenrolled account resolved itself and
    this queue was permanently empty. `test_pending.py` passed throughout, because
    its double ignores the join; reproduced against real rows, the buggy form
    returns nothing here and the correct one returns both addresses.
    """
    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.refused", "waiting@example.org", None),
            ("signin.refused", "also-waiting@example.org", None),
        ],
    )
    _, not_enrolled = waiting(engine, table=name)
    assert sorted(w.address for w in not_enrolled) == [
        "also-waiting@example.org",
        "waiting@example.org",
    ], "the enrolment queue is empty when two people are in it"


def test_an_account_that_was_admitted_stops_being_reported(table):
    """The identity stamp writes `user_email` only onto a signed-in session's
    records, so its presence is proof the door opened.

    The realistic record here is `signin.admitted`, written on arrival and stamped
    like any other; a `question.asked` is the same shape and the same arm of the
    union. Before `signin.admitted` existed this only resolved for readers who went
    on to ask something, which is how a solved problem came to be reported daily.
    """
    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.refused", "enrolled@example.org", None),
            ("signin.admitted", None, "enrolled@example.org"),
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
                f"(now() - interval '40 days', 'signin.resend_requested', "
                f'cast(\'{{"email": "ancient@example.org"}}\' as jsonb))'
            )
        )
    assert waiting(engine, hours=24 * 30, table=name)[0] == [], "outside the window"
    assert [w.address for w in waiting(engine, hours=24 * 60, table=name)[0]] == [
        "ancient@example.org"
    ]
