"""What "first" means, and what the read-only role can and cannot do. Real Postgres only.

"First" is a `having min(at) > ...` over a case-folded address, and a double accepts
any string: every offline test in `test_first_use.py` would pass with that predicate
dropped, inverted, or comparing case-sensitively -- and a dropped predicate makes the
notice report every reader every hour, which is how a monitor stops being read. So
these write rows into throwaway tables and read the real answer back. Run with
`pytest -m network`; skipped where no database is configured.

The role test executes `sql/first_use_reader.sql` itself, statement by statement, with
the identifiers swapped for throwaway ones -- so what is proved is the file the
operator will run, not a copy of it written to make the test pass.
"""

from __future__ import annotations

import tomllib
import uuid
from pathlib import Path

import pytest

from scinumbers_ask.first_use import first_seen
from scinumbers_ask.trail_store import TrailStore, engine_from_url

pytestmark = pytest.mark.network

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / ".streamlit" / "secrets.toml"
ROLE_SQL = ROOT / "sql" / "first_use_reader.sql"

TABLE_PREFIX = "first_use_test_"
ROLE_PREFIX = "first_use_test_"


def _url() -> str:
    if not SECRETS.exists():
        pytest.skip("no .streamlit/secrets.toml; nothing to connect to")
    try:
        return tomllib.loads(SECRETS.read_text())["connections"]["usage"]["url"]
    except (KeyError, tomllib.TOMLDecodeError):
        pytest.skip("no [connections.usage] url configured")


def _make_table(engine) -> str:
    name = f"{TABLE_PREFIX}{uuid.uuid4().hex[:8]}"
    assert TrailStore(engine=engine, table=name).ensure_schema(), "could not create a test table"
    return name


@pytest.fixture
def engine():
    from sqlalchemy import text

    engine = engine_from_url(_url())
    # Orphans from an interrupted run: a table, or a role, left in whatever database
    # `secrets.toml` names.
    with engine.begin() as conn:
        for orphan in conn.execute(
            text(
                "select tablename from pg_tables "
                "where schemaname = 'public' and tablename like :like"
            ),
            {"like": f"{TABLE_PREFIX}%"},
        ).scalars():
            conn.execute(text(f"drop table if exists {orphan}"))
    yield engine
    engine.dispose()


@pytest.fixture
def table(engine):
    from sqlalchemy import text

    name = _make_table(engine)
    yield name
    with engine.begin() as conn:
        conn.execute(text(f"drop table if exists {name}"))


_INSERT = """
insert into {name} (at, event, user_email, session_id)
values (now() - cast(:ago as interval), :event, :email, 'acct:test')
"""


def _write(engine, name, rows):
    """`(event, email, minutes_ago)` rows."""
    from sqlalchemy import text

    with engine.begin() as conn:
        for event, email, minutes_ago in rows:
            conn.execute(
                text(_INSERT.format(name=name)),
                {"ago": f"{minutes_ago} minutes", "event": event, "email": email},
            )


SIGN_IN = "signin.admitted"
ASK = "question.asked"


def _seen(engine, table, minutes=70, exclude=()):
    return {s.address: s for s in first_seen(engine, minutes=minutes, table=table, exclude=exclude)}


def test_a_first_sign_in_inside_the_window_is_reported(engine, table):
    _write(engine, table, [(SIGN_IN, "new@example.org", 10)])
    seen = _seen(engine, table)
    assert list(seen) == ["new@example.org"]
    assert seen["new@example.org"].signed_in_at is not None
    assert seen["new@example.org"].asked_at is None


def test_a_first_question_inside_the_window_is_reported(engine, table):
    _write(engine, table, [(ASK, "new@example.org", 10)])
    seen = _seen(engine, table)
    assert seen["new@example.org"].asked_at is not None
    assert seen["new@example.org"].signed_in_at is None


def test_both_firsts_in_one_window_come_back_as_one_row(engine, table):
    _write(engine, table, [(SIGN_IN, "new@example.org", 50), (ASK, "new@example.org", 10)])
    rows = first_seen(engine, minutes=70, table=table)
    assert len(rows) == 1
    assert rows[0].signed_in_at is not None and rows[0].asked_at is not None


def test_a_sign_in_that_is_not_the_first_is_not_reported(engine, table):
    # The reader signed in three hours ago and again ten minutes ago. Only the
    # second is inside the window, and it is not the first -- the dropped
    # "no earlier event" predicate would report them every time they came back.
    _write(engine, table, [(SIGN_IN, "back@example.org", 180), (SIGN_IN, "back@example.org", 10)])
    assert _seen(engine, table) == {}


def test_a_question_that_is_not_the_first_is_not_reported(engine, table):
    # The mirror of the sign-in case. It was missing, and a seeded defect found it:
    # with the window dropped from the question side only, every reader who had ever
    # asked anything was reported every hour, and all of the "not the first" cases
    # here were sign-ins, so nothing noticed.
    _write(engine, table, [(ASK, "back@example.org", 180), (ASK, "back@example.org", 10)])
    assert _seen(engine, table) == {}


def test_a_first_question_older_than_the_window_is_not_reported(engine, table):
    _write(engine, table, [(ASK, "old@example.org", 120)])
    assert _seen(engine, table, minutes=70) == {}
    assert list(_seen(engine, table, minutes=180)) == ["old@example.org"]


def test_a_new_sign_in_does_not_make_an_old_first_question_new(engine, table):
    _write(engine, table, [(ASK, "old@example.org", 180), (SIGN_IN, "old@example.org", 10)])
    seen = _seen(engine, table)
    assert seen["old@example.org"].signed_in_at is not None
    assert seen["old@example.org"].asked_at is None, "the question was not the first in this window"


def test_a_returning_reader_asking_for_the_first_time_is_reported_for_asking_only(engine, table):
    _write(engine, table, [(SIGN_IN, "back@example.org", 180), (ASK, "back@example.org", 10)])
    seen = _seen(engine, table)
    assert seen["back@example.org"].asked_at is not None
    assert seen["back@example.org"].signed_in_at is None, "the sign-in was not new"


def test_one_address_in_two_spellings_is_one_reader(engine, table):
    _write(
        engine, table, [(SIGN_IN, "Reader@Example.ORG", 180), (SIGN_IN, "reader@example.org", 10)]
    )
    assert _seen(engine, table) == {}, "the capitals earlier made this a returning reader"


def test_the_address_comes_back_lower_cased(engine, table):
    _write(engine, table, [(SIGN_IN, "Reader@Example.ORG", 10)])
    assert list(_seen(engine, table)) == ["reader@example.org"]


def test_records_with_no_address_are_nobody(engine, table):
    _write(engine, table, [(SIGN_IN, None, 10), (ASK, "", 10)])
    assert _seen(engine, table) == {}


def test_the_window_is_the_operators_to_choose(engine, table):
    _write(engine, table, [(SIGN_IN, "late@example.org", 120)])
    assert _seen(engine, table, minutes=70) == {}
    assert list(_seen(engine, table, minutes=180)) == ["late@example.org"]


def test_other_events_are_not_firsts(engine, table):
    _write(
        engine,
        table,
        [("question.answered", "x@example.org", 10), ("signin.refused", "x@example.org", 10)],
    )
    assert _seen(engine, table) == {}


def test_an_excluded_address_is_dropped_whole(engine, table):
    _write(engine, table, [(SIGN_IN, "me@example.org", 50), (ASK, "me@example.org", 10)])
    assert _seen(engine, table, exclude=("ME@example.org",)) == {}


# -- the credential: what the role can and cannot do -----------------------------


def _statements(sql: str):
    # Comments carry apostrophes and semicolons, so strip them before splitting.
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def _drop_role(conn, role: str) -> None:
    """Drop a role and everything granted to it.

    The owner role Neon hands out is not a member of a role it just created, and
    `drop owned by` is refused to a non-member ("permission denied to drop
    objects") -- which surfaced as seven errors in fixture teardown, leaving seven
    roles behind. Membership first, then the drop.
    """
    from sqlalchemy import text

    conn.execute(text(f"grant {role} to current_user"))
    conn.execute(text(f"drop owned by {role}"))
    conn.execute(text(f"drop role if exists {role}"))


@pytest.fixture
def reader(engine, table):
    """The real `sql/first_use_reader.sql`, run against a throwaway role and table.

    Yields an engine connected *as that role*, plus a second table it was never
    granted. Every substitution is asserted to have happened: a rename in the file
    that stopped matching would otherwise run an unchanged statement against the
    real names, or none at all, and the test would pass while proving nothing.
    """
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    role = f"{ROLE_PREFIX}{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    other = _make_table(engine)
    with engine.begin() as conn:
        database = conn.execute(text("select current_database()")).scalar()
        for orphan in conn.execute(
            text("select rolname from pg_roles where rolname like :like"),
            {"like": f"{ROLE_PREFIX}%"},
        ).scalars():
            _drop_role(conn, orphan)

    sql = ROLE_SQL.read_text()
    for needle, replacement in (
        ("first_use_reader", role),
        ("CHANGE-ME", password),
        (" neondb ", f" {database} "),
        ("select on trail", f"select on {table}"),
    ):
        assert needle in sql, f"sql/first_use_reader.sql no longer contains {needle!r}"
        sql = sql.replace(needle, replacement)

    try:
        with engine.begin() as conn:
            for statement in _statements(sql):
                conn.execute(text(statement))
        url = make_url(_url()).set(username=role, password=password)
        role_engine = engine_from_url(url.render_as_string(hide_password=False))
        yield role_engine, other
        role_engine.dispose()
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"drop table if exists {other}"))
            _drop_role(conn, role)


def test_the_role_can_ask_the_question(engine, table, reader):
    role_engine, _ = reader
    _write(engine, table, [(SIGN_IN, "new@example.org", 10)])
    seen = {s.address for s in first_seen(role_engine, minutes=70, table=table)}
    assert seen == {"new@example.org"}


@pytest.mark.parametrize(
    "statement",
    [
        "insert into {t} (event, session_id) values ('x', 'y')",
        "update {t} set event = 'x'",
        "delete from {t}",
        "create table first_use_test_nope (a int)",
    ],
)
def test_the_role_cannot_change_anything(reader, table, statement):
    from sqlalchemy import text

    role_engine, _ = reader
    with pytest.raises(Exception, match="read-only|permission denied"):
        with role_engine.begin() as conn:
            conn.execute(text(statement.format(t=table)))


def test_the_grants_alone_refuse_a_write_even_if_the_transaction_is_made_writable(reader, table):
    # Two guards, and this isolates the first: with the role's read-only default
    # overridden, it is the *missing grant* that refuses.
    from sqlalchemy import text

    role_engine, _ = reader
    with pytest.raises(Exception, match="permission denied"):
        with role_engine.begin() as conn:
            conn.execute(text("set transaction read write"))
            conn.execute(text(f"insert into {table} (event, session_id) values ('x', 'y')"))


def test_the_role_cannot_read_another_table(reader):
    from sqlalchemy import text

    role_engine, other = reader
    with pytest.raises(Exception, match="permission denied"):
        with role_engine.begin() as conn:
            conn.execute(text(f"select count(*) from {other}")).all()
