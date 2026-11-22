"""The first-use notice: silent when nobody is new, loud when it cannot look.

Written from the spec's scenarios, not from running the code. What is asserted here
is everything that does *not* live in SQL: the silence, the one-message-per-reader
shape, the exclusions, the refusals, and that asking writes nothing. The meaning of
"first" -- an event in the window and none earlier, case-folded -- is a `where` and a
`having`, and a double accepts any string, so that is `test_first_use_live.py`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from numera_ask import first_use
from numera_ask.first_use import URL_ENV, FirstSeen, first_seen, main

SIGNED_IN = datetime(2026, 10, 2, 14, 3, tzinfo=UTC)
ASKED = datetime(2026, 10, 2, 14, 9, tzinfo=UTC)


class _Conn:
    def __init__(self, rows, fail=None):
        self.rows = rows
        self.fail = fail
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append(text)
        if params is not None:
            self.params.append(dict(params))
        if self.fail is not None and text.lstrip().lower().startswith(("with", "select")):
            raise self.fail

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _Result(self.rows)


class _Engine:
    def __init__(self, rows=(), fail=None):
        self.conn = _Conn(list(rows), fail)
        self.disposed = False

    def begin(self):
        engine = self

        class _Ctx:
            def __enter__(self):
                return engine.conn

            def __exit__(self, *exc):
                return False

        return _Ctx()

    def dispose(self):
        self.disposed = True


@pytest.fixture
def run(monkeypatch, capsys):
    """`main` against a fake engine, returning (exit status, stdout, stderr, engine)."""

    def _run(rows=(), argv=(), fail=None, env=True):
        engine = _Engine(rows, fail)
        monkeypatch.setattr(first_use.trail_store, "engine_from_url", lambda url, **kw: engine)
        if env:
            monkeypatch.setenv(URL_ENV, "postgresql+psycopg://reader@example/db")
        else:
            monkeypatch.delenv(URL_ENV, raising=False)
        status = main(list(argv))
        out, err = capsys.readouterr()
        return status, out, err, engine

    return _run


def test_nobody_new_prints_nothing_at_all(run):
    status, out, err, _ = run(rows=[])
    assert (status, out, err) == (0, "", "")


def test_a_first_sign_in_is_reported_as_a_sign_in_and_not_as_a_question(run):
    _, out, _, _ = run(rows=[("new@example.org", SIGNED_IN, None)])
    assert "new@example.org" in out
    assert "signed in" in out
    assert "question" not in out


def test_a_first_question_is_reported_as_a_question_and_not_as_a_sign_in(run):
    _, out, _, _ = run(rows=[("new@example.org", None, ASKED)])
    assert "new@example.org" in out
    assert "first question" in out
    assert "signed in" not in out


def test_both_firsts_for_one_reader_are_one_message_about_one_person(run):
    _, out, _, _ = run(rows=[("new@example.org", SIGNED_IN, ASKED)])
    lines = [line for line in out.splitlines() if "new@example.org" in line]
    assert len(lines) == 1, "one reader, one line"
    assert "signed in" in lines[0] and "first question" in lines[0]


def test_two_readers_are_two_lines_each_naming_its_own_reader(run):
    _, out, _, _ = run(rows=[("a@example.org", SIGNED_IN, None), ("b@example.org", None, ASKED)])
    assert sum("a@example.org" in line for line in out.splitlines()) == 1
    assert sum("b@example.org" in line for line in out.splitlines()) == 1


def test_an_excluded_address_is_not_reported_whatever_its_case(run):
    _, out, _, _ = run(
        rows=[("me@example.org", SIGNED_IN, None), ("other@example.org", SIGNED_IN, None)],
        argv=["--exclude", "ME@Example.org"],
    )
    assert "me@example.org" not in out
    assert "other@example.org" in out


def test_everyone_excluded_is_silence_not_an_empty_report(run):
    # The excluded reader had both firsts: exclusion must not leave half a row, and
    # an all-excluded answer is "nothing", exactly as if nobody had come.
    status, out, err, _ = run(
        rows=[("me@example.org", SIGNED_IN, ASKED)], argv=["--exclude", "me@example.org"]
    )
    assert (status, out, err) == (0, "", "")


def test_exclude_can_be_repeated(run):
    _, out, _, _ = run(
        rows=[("a@example.org", SIGNED_IN, None), ("b@example.org", SIGNED_IN, None)],
        argv=["--exclude", "a@example.org", "--exclude", "b@example.org"],
    )
    assert out == ""


def test_asking_writes_nothing_and_says_so_to_the_database(run):
    _, _, _, engine = run(rows=[("new@example.org", SIGNED_IN, None)])
    statements = [s.lower() for s in engine.conn.statements]
    assert not any(word in s for s in statements for word in ("insert", "update", "delete", "drop"))
    # The credential is the first guard (a role that can only read); this is the
    # operation's own, so a more powerful URL still cannot make asking a write.
    assert any("read only" in s for s in statements)


def test_the_read_only_setting_comes_before_the_question(run):
    _, _, _, engine = run(rows=[])
    statements = [s.lower() for s in engine.conn.statements]
    first_select = next(i for i, s in enumerate(statements) if "select" in s)
    assert any("read only" in s for s in statements[:first_select])


def test_the_window_is_bound_as_a_parameter_not_interpolated(run):
    _, _, _, engine = run(rows=[], argv=["--minutes", "95"])
    assert {"minutes": 95} in engine.conn.params


def test_the_fallback_window_covers_the_longest_gap_the_schedule_was_seen_to_leave(run):
    # GitHub ran the "hourly" workflows 4-7 hours apart: the longest gap seen was
    # 6 h 51 m (411 minutes). A fallback shorter than that would lose a reader whose
    # arrival fell in it (see `first_use.DEFAULT_MINUTES`, ADR-1290).
    assert first_use.DEFAULT_MINUTES >= 411
    _, _, _, engine = run(rows=[])
    assert {"minutes": first_use.DEFAULT_MINUTES} in engine.conn.params


def test_a_trail_that_cannot_be_read_says_so_and_fails(run):
    status, out, err, engine = run(fail=RuntimeError("connection refused"))
    assert status == 1
    assert out == "", "a failure must not look like a report"
    assert "could not read" in err and "connection refused" in err
    assert engine.disposed


@pytest.mark.parametrize("minutes", ["0", "-5"])
def test_a_window_that_can_match_nothing_is_refused(run, minutes):
    status, out, err, engine = run(argv=["--minutes", minutes])
    assert status == 2
    assert out == ""
    assert "positive" in err
    assert engine.conn.statements == [], "refused before it looked"


def test_a_missing_database_url_is_refused_and_names_the_setting(run):
    status, out, err, engine = run(env=False)
    assert status == 2
    assert out == ""
    assert URL_ENV in err
    assert engine.conn.statements == []


def test_importing_first_use_never_loads_the_neon_control_plane():
    # The scheduled job holds a database URL and nothing that can manage the project.
    # Checked in a fresh process, because this one has long since imported `neon` for
    # other tests: what matters is that `first_use` does not pull it in by itself.
    program = (
        "import sys, numera_ask.first_use; "
        "bad = [m for m in ('numera_ask.neon', 'numera_ask.pending', "
        "'numera_ask.enrol') if m in sys.modules]; "
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert result.returncode == 0, "first_use imports a module that reaches the control plane"


ROLE_SQL = Path(__file__).resolve().parents[1] / "sql" / "first_use_reader.sql"


def test_an_unedited_role_script_is_a_syntax_error_not_a_login_role_with_a_known_password():
    sql = ROLE_SQL.read_text()
    create = next(s for s in sql.split(";") if "create role" in s)
    assert not re.search(r"password\s+'", create), "the password placeholder is a valid literal"
    assert "CHANGE-ME" not in sql


def test_the_role_is_granted_three_columns_and_never_the_table():
    sql = "\n".join(
        line for line in ROLE_SQL.read_text().splitlines() if not line.lstrip().startswith("--")
    )
    grants = re.findall(r"grant select[^;]*;", sql)
    assert grants == ["grant select (at, event, user_email) on trail to first_use_reader;"]


def test_first_seen_returns_values_rather_than_printing(capsys):
    engine = _Engine(rows=[("new@example.org", SIGNED_IN, ASKED)])
    seen = first_seen(engine, minutes=70)
    assert seen == [FirstSeen("new@example.org", SIGNED_IN, ASKED)]
    assert capsys.readouterr().out == ""


def test_first_seen_applies_exclusions_after_combining_so_a_reader_never_splits():
    engine = _Engine(rows=[("me@example.org", SIGNED_IN, ASKED), ("x@example.org", None, ASKED)])
    seen = first_seen(engine, minutes=70, exclude=("ME@example.org",))
    assert [s.address for s in seen] == ["x@example.org"]


def test_the_retired_url_name_is_refused_by_name(monkeypatch, capsys):
    """Not "set it first": the reader is told the old name is the problem (ADR-1900)."""
    monkeypatch.delenv(URL_ENV, raising=False)
    monkeypatch.setenv("SCINUMBERS_TRAIL_READ_URL", "postgresql://reader@old/trail")

    assert main([]) == 2
    assert "SCINUMBERS_TRAIL_READ_URL is now NUMERA_TRAIL_READ_URL" in capsys.readouterr().err
