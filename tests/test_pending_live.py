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


#: Every table these tests make, so an orphan from an interrupted run is
#: recognisable and can be swept. The url in `secrets.toml` is the branch *this
#: checkout* writes to -- `dev` on a laptop -- but nothing stops an operator having
#: pointed it elsewhere, so a table left behind is a table left in whatever database
#: that is.
TABLE_PREFIX = "pending_test_"


@pytest.fixture
def table():
    """A throwaway table, dropped afterwards, and orphans from earlier runs swept
    first.

    Never the real `trail`: these tests write rows, and rows left in the table an
    operator reads make it untrustworthy. The sweep is because a run interrupted
    between `ensure_schema` and teardown -- Ctrl-C, a failed assertion inside the
    fixture, a lost connection -- leaves its table behind, and nothing else would
    ever remove it.
    """
    from sqlalchemy import text

    engine = engine_from_url(_url())
    with engine.begin() as conn:
        orphans = conn.execute(
            text(
                "select tablename from pg_tables "
                "where schemaname = 'public' and tablename like :like"
            ),
            {"like": f"{TABLE_PREFIX}%"},
        ).scalars()
        for orphan in list(orphans):
            conn.execute(text(f"drop table if exists {orphan}"))
    name = f"{TABLE_PREFIX}{uuid.uuid4().hex[:8]}"
    store = TrailStore(engine=engine, table=name)
    assert store.ensure_schema(), "could not create the test table"
    yield engine, name
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


def test_a_request_with_no_later_progress_is_reported(table, accounts_table):
    engine, name = table
    _write(engine, name, [("signin.resend_requested", "stuck@example.org", None)])
    no_email, _ = waiting(engine, table=name, accounts_table=accounts_table)
    assert [w.address for w in no_email] == ["stuck@example.org"]


def test_a_request_answered_by_verification_stops_being_reported(table, accounts_table):
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
    no_email, not_enrolled = waiting(engine, table=name, accounts_table=accounts_table)
    assert no_email == [], "a resolved request was reported again"
    assert [w.address for w in not_enrolled] == ["moved@example.org"], (
        "they are now in the other queue, which is the point"
    )


@pytest.fixture
def accounts_table(table):
    """An `accounts` table of its own, because the enrolment queue asks the authority
    rather than inferring from later sign-ins."""
    from sqlalchemy import text

    engine, _ = table
    name = f"{TABLE_PREFIX}accounts_{uuid.uuid4().hex[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text(
                f"create table {name} (email text primary key, role text not null, "
                f"openrouter_key text, issued_at timestamptz not null default now(), "
                f"disabled boolean not null default false)"
            )
        )
    yield name
    with engine.begin() as conn:
        conn.execute(text(f"drop table if exists {name}"))


def test_an_enrolled_account_leaves_the_queue_even_if_it_never_returns(table, accounts_table):
    """The finding that sent this query to the accounts table. Resolution used to be
    "signed in again through an open door", so a tester who was enrolled and did not
    come back was reported for thirty days -- and following the advice failed with
    `AlreadyEnrolled`. Whether somebody is enrolled is a row, and this asks for it.
    """
    from sqlalchemy import text

    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.refused", "done@example.org", None),
            ("signin.refused", "waiting@example.org", None),
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                f"insert into {accounts_table} (email, role) values ('Done@Example.org', 'student')"
            )
        )
    _, not_enrolled = waiting(engine, table=name, accounts_table=accounts_table)
    assert [w.address for w in not_enrolled] == ["waiting@example.org"], (
        "an enrolled account was still reported, or an unenrolled one was not"
    )


def test_a_withdrawn_account_is_not_enrolled(table, accounts_table):
    """`accounts.lookup` refuses a disabled row exactly as an absent one, so this
    must agree: a withdrawn tester who tries again is genuinely waiting."""
    from sqlalchemy import text

    engine, name = table
    _write(engine, name, [("signin.refused", "gone@example.org", None)])
    with engine.begin() as conn:
        conn.execute(
            text(
                f"insert into {accounts_table} (email, role, disabled) "
                f"values ('gone@example.org', 'student', true)"
            )
        )
    _, not_enrolled = waiting(engine, table=name, accounts_table=accounts_table)
    assert [w.address for w in not_enrolled] == ["gone@example.org"]


def test_the_enrolment_queue_reports_everyone_with_no_row(table, accounts_table):
    """This queue was empty twice, for two different reasons, and both are worth
    keeping.

    First `signin.refused` appeared in its own progress set, so every unenrolled
    account resolved itself. Then, with that fixed, resolution was still "signed in
    again through an open door" — which a tester who was enrolled and never came
    back never does, and which an enrolled account with no credential *cannot* do,
    because that door stops the page before anything is recorded. Whether somebody
    is enrolled is a row, and this asks for it.

    `test_pending.py` passed through both, because its double runs neither the join
    nor the `not exists`.
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
    _, not_enrolled = waiting(engine, table=name, accounts_table=accounts_table)
    assert sorted(w.address for w in not_enrolled) == [
        "also-waiting@example.org",
        "waiting@example.org",
    ], "the enrolment queue is empty when two people are in it"


def test_an_admitted_session_resolves_a_request_for_the_email(table, accounts_table):
    """The identity stamp writes `user_email` only onto a signed-in session's
    records, so its presence proves the door opened -- which is what a reader who
    never got their confirmation email needs.

    The realistic record is `signin.admitted`, written on arrival and stamped like
    any other. Before it existed this resolved only for readers who went on to ask
    something, which is how a solved problem came to be reported daily.

    It does **not** resolve the enrolment queue: that asks the accounts table, and
    this address has no row, so it is still reported there. Two stages, two
    authorities.
    """
    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.resend_requested", "in@example.org", None),
            ("signin.admitted", None, "in@example.org"),
        ],
    )
    no_email, _ = waiting(engine, table=name, accounts_table=accounts_table)
    assert no_email == [], "an admitted reader was still asked to check their email"


def test_progress_before_the_request_does_not_resolve_it(table, accounts_table):
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
    no_email, _ = waiting(engine, table=name, accounts_table=accounts_table)
    assert [w.address for w in no_email] == ["again@example.org"], (
        "an old success was treated as answering a new problem"
    )


def test_two_spellings_of_one_address_are_one_person(table, accounts_table):
    """Both places a spelling can differ, because `accounts.lookup` folds case and
    nothing makes the provider's assertion and the operator's typing agree.

    Without folding, a solved problem is chased forever: an admitted `Mixed@` would
    not resolve a request from `mixed@`, and an accounts row spelled either way
    would not clear a refusal spelled the other.

    This test previously asserted that an *admitted* session cleared the enrolment
    queue, which stopped being true when that queue started asking the accounts
    table -- correctly, since a reader may be enrolled and never come back. It was
    stale rather than failing, and it was the only one of the nine not updated.
    """
    from sqlalchemy import text

    engine, name = table
    _write(
        engine,
        name,
        [
            ("signin.resend_requested", "Asked@Example.org", None),
            ("signin.admitted", None, "asked@example.org"),
            ("signin.refused", "Rowed@Example.org", None),
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                f"insert into {accounts_table} (email, role) "
                f"values ('rowed@example.org', 'student')"
            )
        )
    no_email, not_enrolled = waiting(engine, table=name, accounts_table=accounts_table)
    assert no_email == [], "an admission under another capitalisation did not resolve the request"
    assert not_enrolled == [], "an accounts row under another capitalisation did not count"


def test_the_window_bounds_how_far_back_it_looks(table, accounts_table):
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
    assert waiting(engine, hours=24 * 30, table=name, accounts_table=accounts_table)[0] == [], (
        "outside the window"
    )
    assert [
        w.address
        for w in waiting(engine, hours=24 * 60, table=name, accounts_table=accounts_table)[0]
    ] == ["ancient@example.org"]
