"""The daily check: silent when nothing is waiting, and loud when it cannot look.

The assertion that matters most here is the **silence**. A monitor that prints "0
pending" every morning is one whose output stops being read, and then the morning
it says 1 goes unread too — so "nothing to say" has to mean nothing written at all,
and that is what a cron line depends on.

The second is that a failure is *not* silent. A check that cannot reach the
database and says nothing is indistinguishable from a quiet day, which is the worst
outcome available to it: it retires the suspicion it exists to raise.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from numera_ask import neon, pending, trail_store
from numera_ask.pending import Waiting, main, waiting


class _Conn:
    """Answers the two queries by the event they bind, and records what was asked."""

    def __init__(self, rows: dict, fail=None):
        self.rows = rows
        self.fail = fail
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append(text)
        if params is not None:
            self.params.append(dict(params))
        if self.fail is not None and "select" in text.lower():
            raise self.fail

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        # Keyed on the statement, not only on the event, because the enrolment
        # queue binds no event at all now: whether somebody is enrolled is asked of
        # the accounts table, so that query joins rather than filtering by event.
        if "not exists" in text.lower():
            return _Result(self.rows.get("unenrolled", []))
        if params and "event" in params:
            return _Result(self.rows.get(params["event"], []))
        return _Result([])


class _Engine:
    def __init__(self, rows=None, fail=None):
        self.conn = _Conn(rows or {}, fail)
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


WHEN = datetime(2026, 9, 26, 12, 0, 0)


def test_nothing_waiting_prints_nothing_at_all(monkeypatch, capsys):
    """The contract a cron line rests on. Not "0 pending", not a header: nothing,
    so the operator's mail arrives only on the days something happened."""
    _wire(monkeypatch, _Engine())
    assert main(["--branch", "alpha"]) == 0
    out = capsys.readouterr()
    assert out.out == "", f"a quiet day printed {out.out!r}"


def test_a_request_for_the_email_is_reported_with_what_to_do(monkeypatch, capsys):
    engine = _Engine(
        {"signin.resend_requested": [("stuck@example.org", WHEN, 2)]},
    )
    _wire(monkeypatch, engine)
    assert main(["--branch", "alpha"]) == 0
    said = capsys.readouterr().out
    assert "stuck@example.org" in said
    assert "resend" in said.lower(), "the line says who, not what the operator should do"
    assert "2x" in said, "how many times they asked is how urgent it is"


def test_an_unenrolled_account_is_reported_as_the_enrolment_queue(monkeypatch, capsys):
    # **This test is blind to the resolution rule** and cannot be otherwise: the
    # double never runs the join or the `not exists`. It passed while
    # `signin.refused` appeared in its own progress set, which emptied this queue
    # completely. `test_pending_live.py` is where that is caught, and the reason
    # this file is not enough.
    _wire(monkeypatch, _Engine({"unenrolled": [("new@example.org", WHEN, 1)]}))
    assert main(["--branch", "alpha"]) == 0
    said = capsys.readouterr().out
    assert "new@example.org" in said and "numera-enrol" in said


def test_the_window_is_applied_and_bound_not_interpolated(monkeypatch, capsys):
    """Two claims, and the first is the one that nearly went untested.

    *Applied*: the interval has to read the parameter. Asserting only that `hours`
    was **passed** left a mutant alive that hard-coded `99999` into the SQL —
    every request reported every day forever, which is the failure mode this
    command's whole "window, not a ledger" design exists to avoid, and the
    parameter was still dutifully bound.

    *Bound*: interpolated into the statement it would work, and would put a
    command-line value into SQL aimed at the deployment's database.

    What no offline test can show is that Postgres then honours the window, since
    the double is what we wrote. That is unverified against a real database.
    """
    engine = _Engine()
    _wire(monkeypatch, engine)
    main(["--branch", "alpha", "--hours", "72"])
    statements = "".join(engine.conn.statements)
    assert "make_interval(hours => :hours)" in statements, "the window ignores its parameter"
    assert {"hours": 72} == {k: v for k, v in engine.conn.params[-1].items() if k == "hours"}
    assert "72" not in statements


def test_a_trail_that_cannot_be_read_says_so_and_fails(monkeypatch, capsys):
    """The worst outcome available to a monitor is silence on failure, which reads
    as a quiet day and retires the suspicion it exists to raise."""
    _wire(monkeypatch, _Engine(fail=RuntimeError("could not connect")))
    assert main(["--branch", "alpha"]) == 1
    err = capsys.readouterr().err
    assert "could not read the trail" in err and "could not connect" in err


def test_no_branch_is_refused_in_this_command_s_own_words(monkeypatch, capsys):
    """Not enrolment's sentence. That one talks about a row landing in the wrong
    branch and enrolling a tester the app will never find, and this command writes
    nothing -- an operator debugging a failed cron job should not be told about
    rows."""
    from numera_ask import enrol as enrol_mod

    _wire(monkeypatch, _Engine())
    assert main(["--hours", "24"]) == 2
    said = capsys.readouterr().err
    assert "--branch" in said and "no default" in said
    assert "row" not in said.lower(), "a read-only command talked about writing"
    assert said.strip() != enrol_mod.NO_BRANCH.strip()


@pytest.mark.parametrize("hours", [0, -1])
def test_a_window_that_can_match_nothing_is_refused(monkeypatch, capsys, hours):
    """Silence means nobody is stuck, so a window matching nothing would be a
    confident all-clear manufactured by a bad argument -- in the one tool whose
    entire contract is that an empty report means an empty queue."""
    reached: list = []
    _wire(monkeypatch, _Engine())
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: reached.append(a))
    assert main(["--branch", "alpha", "--hours", str(hours)]) == 2
    assert "positive" in capsys.readouterr().err
    assert reached == [], "a bad window still opened a connection"


class _Tty:
    """Stderr that claims to be a terminal, writing through to whatever captures it."""

    def __init__(self, inner):
        self._inner = inner

    def isatty(self):
        return True

    def write(self, text):
        return self._inner.write(text)

    def flush(self):
        return self._inner.flush()


def test_the_management_key_note_goes_to_a_terminal_and_never_to_cron(monkeypatch, capsys):
    """**The note must not reach a scheduled run.** The documented cron line sources
    the enrolment env file, whose first line is this variable, so an ungated note
    went to stderr every morning and cron mailed it -- daily mail about something
    harmless, which is precisely how the report that matters stops being read. A
    review found it; it would have made the whole silence contract worthless.

    A person at a prompt can act on it, so they still see it.
    """
    import sys

    _wire(monkeypatch, _Engine())
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    assert main(["--branch", "alpha"]) == 0
    assert capsys.readouterr().err == "", "a scheduled run was sent mail"

    _wire(monkeypatch, _Engine())
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    monkeypatch.setattr(sys, "stderr", _Tty(sys.stderr))
    assert main(["--branch", "alpha"]) == 0
    assert "not needed" in capsys.readouterr().err

    _wire(monkeypatch, _Engine())
    monkeypatch.delenv("OPENROUTER_MANAGEMENT_KEY", raising=False)
    monkeypatch.setattr(sys, "stderr", _Tty(sys.stderr))
    assert main(["--branch", "alpha"]) == 0
    assert "not needed" not in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["NEON_API_KEY", "NEON_PROJECT_ID"])
def test_the_missing_variable_is_named(monkeypatch, capsys, missing):
    _wire(monkeypatch, _Engine())
    monkeypatch.delenv(missing, raising=False)
    assert main(["--branch", "alpha"]) == 2
    assert missing in capsys.readouterr().err


def test_waiting_returns_rows_rather_than_a_report():
    """Returned, not printed, so a second caller is not made to parse prose."""
    engine = _Engine({"signin.resend_requested": [("a@example.org", WHEN, 3)]})
    no_email, not_enrolled = waiting(engine)
    assert no_email == [Waiting(address="a@example.org", last_seen=WHEN, times=3)]
    assert not_enrolled == []
    assert any("statement_timeout" in s for s in engine.conn.statements)


def test_the_engine_is_disposed_even_when_the_query_fails(monkeypatch, capsys):
    engine = _Engine(fail=RuntimeError("boom"))
    _wire(monkeypatch, engine)
    main(["--branch", "alpha"])
    assert engine.disposed, "a failed run left a connection pool behind"


def _wire(monkeypatch, engine):
    monkeypatch.setenv("NEON_API_KEY", "napi")
    monkeypatch.setenv("NEON_PROJECT_ID", "proj")
    monkeypatch.delenv("OPENROUTER_MANAGEMENT_KEY", raising=False)
    monkeypatch.setattr(neon, "branch_id", lambda *a, **k: "br-alpha")
    monkeypatch.setattr(neon, "connection_url", lambda *a, **k: "postgresql+psycopg://u:p@h/db")
    monkeypatch.setattr(trail_store, "engine_from_url", lambda url, **k: engine)
    monkeypatch.setattr(pending.trail_store, "engine_from_url", lambda url, **k: engine)
