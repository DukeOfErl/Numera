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

from scinumbers_ask import neon, pending, trail_store
from scinumbers_ask.pending import Waiting, main, waiting


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
    # double answers by the bound event and never runs the join. It passed while
    # `signin.refused` appeared in its own progress set, which emptied this queue
    # completely. `test_pending_live.py` is where that is caught, and the reason
    # this file is not enough.
    _wire(monkeypatch, _Engine({"signin.refused": [("new@example.org", WHEN, 1)]}))
    assert main(["--branch", "alpha"]) == 0
    said = capsys.readouterr().out
    assert "new@example.org" in said and "scinumbers-enrol" in said


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


def test_no_branch_is_refused_with_the_same_sentence_as_enrolment(monkeypatch, capsys):
    _wire(monkeypatch, _Engine())
    assert main(["--hours", "24"]) == 2
    assert "none is assumed" in capsys.readouterr().err


def test_the_management_key_is_not_required_and_is_flagged_if_present(monkeypatch, capsys):
    """This command reads the trail and touches no provider, so a cron line that
    sources the whole enrolment env file is handing a key that can mint credentials
    to a job that only reads. Harmless here; worth one line before somebody copies
    the cron entry somewhere it is not."""
    _wire(monkeypatch, _Engine())
    monkeypatch.delenv("OPENROUTER_MANAGEMENT_KEY", raising=False)
    assert main(["--branch", "alpha"]) == 0
    assert "not needed" not in capsys.readouterr().err

    _wire(monkeypatch, _Engine())
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "mgmt")
    assert main(["--branch", "alpha"]) == 0
    assert "not needed" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["NEON_API_KEY", "NEON_PROJECT_ID"])
def test_the_missing_variable_is_named(monkeypatch, capsys, missing):
    _wire(monkeypatch, _Engine())
    monkeypatch.delenv(missing, raising=False)
    assert main(["--branch", "alpha"]) == 2
    assert missing in capsys.readouterr().err


def test_waiting_returns_rows_rather_than_a_report():
    """Returned, not printed, so a second caller is not made to parse prose."""
    engine = _Engine({"signin.resend_requested": [("a@b.org", WHEN, 3)]})
    no_email, not_enrolled = waiting(engine)
    assert no_email == [Waiting(address="a@b.org", last_seen=WHEN, times=3)]
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
