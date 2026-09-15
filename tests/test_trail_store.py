"""The durable trail, and the one place in this system where a write fails open.

Every failure test here varies the dimension `TrailStore.record` actually reads,
which is *where* the failure happens, not merely that one did. A single
always-raising double would exercise one path and read as though it covered them
all -- the shape CLAUDE.md records under `_is_out_of_credit`, whose negatives
carried no status code at all and so let a fatal mutant pass 905 tests.

**Two** distinct places a write can fail offline, not three: opening the
transaction and executing the statement. Taking too long is not a third, and an
earlier version of this file claimed it was -- `record` has no client-side
deadline, no branch and no timer, so there is nothing here to exercise. A slow
write is bounded by `SET LOCAL statement_timeout`, which the *server* enforces,
and a sleep in the double would have measured the double. That case lives in
`test_trail_store_live.py`, against a real endpoint, deselected by default.

The distinction is worth the paragraph: the withdrawn test read correctly, was
named for the property, and proved nothing -- and the suite could not say so.
"""

from __future__ import annotations

import datetime
import json
import logging

import pytest

from scinumbers_ask import trail_store
from scinumbers_ask.trail_store import TrailHandler, TrailStore, install


class _Conn:
    """Records what was executed **and with which parameters**.

    The parameters are the point. An earlier version of this double took
    `params=None` and dropped it, which meant no test could observe what was
    actually written -- so a mutant passing `session_id=None` unconditionally, or
    swapping question_id and session_id, survived the whole suite. That is the
    change's central property, asserted by nothing.
    """

    def __init__(self, fail_on_execute: Exception | None = None):
        self.fail_on_execute = fail_on_execute
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        if params is not None:
            self.params.append(dict(params))
        if self.fail_on_execute is not None and "insert" in str(statement).lower():
            raise self.fail_on_execute
        return None


class _Engine:
    """A stand-in engine whose failure mode is chosen per test.

    `fail_on_begin` and `fail_on_execute` are deliberately separate: they are
    different code paths in `record`, and a double that conflated them would
    leave one of the two untested while looking thorough.
    """

    def __init__(self, fail_on_begin=None, fail_on_execute=None):
        self.fail_on_begin = fail_on_begin
        self.fail_on_execute = fail_on_execute
        self.conns: list[_Conn] = []
        self.begins = 0

    def begin(self):
        self.begins += 1
        if self.fail_on_begin is not None:
            raise self.fail_on_begin
        conn = _Conn(self.fail_on_execute)
        self.conns.append(conn)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()

    @property
    def inserts(self) -> int:
        return sum(
            1 for c in self.conns for s in c.statements if s.lower().lstrip().startswith("insert")
        )

    @property
    def written(self) -> list[dict]:
        """Every parameter set handed to an INSERT, in order."""
        return [p for c in self.conns for p in c.params]


@pytest.fixture(autouse=True)
def _isolate_counters():
    """The process-wide counters are shared state between tests."""
    trail_store.reset_counters()
    yield
    trail_store.reset_counters()


def _store(**kwargs) -> TrailStore:
    store = TrailStore(engine=_Engine(**kwargs))
    store.ready = True
    return store


# --- the write lands ------------------------------------------------------


def test_a_record_is_written_and_counted():
    store = _store()
    assert store.record("searched", question_id="q1", session_id="s1") is True
    assert store.writes == 1
    assert store.failures == 0
    assert store.engine.inserts == 1


def test_the_statement_timeout_is_set_inside_the_transaction():
    """Neon's default is 0 -- unlimited -- so an unset timeout hangs for ever.

    Asserted on the statement rather than on behaviour because the pooler refuses
    the startup-parameter form, and `SET LOCAL` is the only form that both applies
    and does not leak to the next borrower of a pooled connection.
    """
    store = _store()
    store.record("searched")
    issued = " ".join(store.engine.conns[0].statements).lower()
    assert "set local statement_timeout" in issued
    assert str(trail_store.STATEMENT_TIMEOUT_MS) in issued


# --- the two ways it fails, each a different path -------------------------


def test_a_failure_to_open_the_transaction_is_swallowed_and_counted():
    store = _store(fail_on_begin=OSError("connection refused"))
    assert store.record("searched") is False
    assert store.failures == 1
    assert store.writes == 0


def test_a_failure_to_execute_the_statement_is_swallowed_and_counted():
    """A different path from the one above: the transaction opened fine.

    If `record` only guarded `engine.begin()`, the test above would pass and this
    one would raise -- which is the whole reason the two are separate.
    """
    store = _store(fail_on_execute=ValueError("relation does not exist"))
    assert store.record("searched") is False
    assert store.failures == 1
    assert store.engine.begins == 1


def test_a_failed_write_is_attempted_exactly_once():
    """One attempt, never a retry.

    Named for what it pins. It was called `test_a_slow_write_...` and claimed to
    be a third failure path alongside the two above -- it was not: it passed a
    `TimeoutError` with the double's delay left at zero, so the dimension it
    varied was the *exception class*, not the duration. `record` contains no
    client-side deadline, no branch and no timer; the only thing bounding a slow
    write is `SET LOCAL statement_timeout`, which the server enforces. A sleep in
    the double would have measured the double.

    The slow case is therefore recorded as a gap and closed by a `network` test
    against the live endpoint, not faked here.
    """
    store = _store(fail_on_execute=TimeoutError("canceling statement due to timeout"))
    assert store.record("searched") is False
    assert store.engine.inserts == 1, "the write was retried"
    assert store.engine.begins == 1


@pytest.mark.parametrize(
    "boom",
    [
        OSError("network unreachable"),
        ValueError("bad parameter"),
        TimeoutError("statement timeout"),
        RuntimeError("driver exploded"),
        KeyboardInterrupt,
    ],
    ids=["oserror", "valueerror", "timeout", "runtime", "keyboardinterrupt"],
)
def test_no_exception_type_escapes_record(boom):
    """Including one that is not an `Exception`.

    `KeyboardInterrupt` derives from `BaseException`, so a bare `except Exception`
    lets it through. That is the correct behaviour -- a person pressing Ctrl-C
    must not be swallowed by telemetry -- and it is asserted rather than assumed,
    because the opposite would be an easy and invisible change to make.
    """
    store = _store(fail_on_execute=boom)
    if boom is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            store.record("searched")
    else:
        assert store.record("searched") is False


# --- the guard belongs to the operation -----------------------------------


def test_a_direct_caller_needs_no_error_handling():
    """The spec scenario "Something other than a driver records".

    Written as the thing a second caller would actually do: call it in a loop and
    keep going. If the swallow lived in the web driver instead, this would raise
    on the first iteration.
    """
    store = _store(fail_on_begin=OSError("down"))
    for _ in range(3):
        store.record("searched")  # no try/except here, deliberately
    assert store.failures == 3


def test_the_failure_counter_answers_whether_anything_is_landing():
    """ "Nothing has been recorded for three weeks" has to be answerable."""
    store = _store(fail_on_begin=OSError("down"))
    for _ in range(5):
        store.record("searched")
    assert (store.failures, store.writes) == (5, 0)


# --- configuration is absence-tolerant ------------------------------------


def test_install_with_no_engine_returns_none_and_adds_no_handler():
    logger = logging.getLogger("test.trail.absent")
    before = list(logger.handlers)
    assert install(None, logger_name="test.trail.absent") is None
    assert logger.handlers == before


def test_install_when_the_schema_cannot_be_created_adds_no_handler():
    """Configured and broken is an operator's problem, not a reader's.

    No handler is attached, so the per-question path never attempts a write it
    cannot make -- the failure is reported once at install rather than once per
    question.
    """
    logger = logging.getLogger("test.trail.broken")
    logger.handlers.clear()
    store = install(_Engine(fail_on_begin=OSError("down")), logger_name="test.trail.broken")
    assert store is not None and store.ready is False
    assert not logger.handlers


def test_install_attaches_a_handler_when_the_schema_is_there():
    logger = logging.getLogger("test.trail.ok")
    logger.handlers.clear()
    store = install(_Engine(), logger_name="test.trail.ok")
    assert store is not None and store.ready is True
    assert any(isinstance(h, TrailHandler) for h in logger.handlers)


# --- the bridge from the existing trail -----------------------------------


def test_the_handler_carries_the_identifiers_the_trail_already_has():
    """Asserts the row, not the row count.

    This previously checked `store.writes == 1` and nothing else, which its name
    did not admit: a handler passing `session_id=None`, or swapping the question
    and session identifiers, satisfied it. Those identifiers are the whole point
    of the change.
    """
    store = _store()
    handler = TrailHandler(store)
    record = logging.LogRecord("x", logging.INFO, "f", 1, "searched", None, None)
    record.question_id = "q7"
    record.session_id = "s7"
    record.run_label = "eval"
    record.fields = {"matched": 12}
    handler.emit(record)

    (written,) = store.engine.written
    assert written["question_id"] == "q7"
    assert written["session_id"] == "s7", "a swap of these two would be invisible"
    assert written["run_label"] == "eval"
    assert written["event"] == "searched"
    assert json.loads(written["detail"]) == {"matched": 12}


def test_a_record_carries_every_identifier_it_was_given():
    """The same assertion one level down, on `record` rather than the handler."""
    store = _store()
    store.record(
        "retrieved",
        session_id="s1",
        question_id="q1",
        run_label="dev",
        user_email="someone@example.com",
        detail={"entry_ids": [1, 2]},
    )
    (written,) = store.engine.written
    assert written["session_id"] == "s1"
    assert written["question_id"] == "q1"
    assert written["user_email"] == "someone@example.com"
    assert json.loads(written["detail"]) == {"entry_ids": [1, 2]}


def test_the_detail_is_serialised_rather_than_handed_over_raw():
    """A value json cannot encode must not lose the whole record.

    `default=str` is what makes that true, and nothing else in the suite would
    notice its removal.
    """
    store = _store()
    store.record("searched", detail={"when": datetime.date(2026, 9, 15)})
    (written,) = store.engine.written
    assert json.loads(written["detail"]) == {"when": "2026-09-15"}


def test_the_previous_write_duration_travels_on_the_next_row():
    """The first row has none; the second carries the first's duration.

    It cannot carry its own, and the figure that matters -- the first write after
    a long quiet period -- is recoverable by pairing this with the gap between
    timestamps. A scheduled probe cannot get it: pinging on a timer keeps the
    database warm and destroys the condition. ADR-0700.
    """
    store = _store()
    store.record("first")
    store.record("second")
    first, second = store.engine.written
    assert first["prev_write_ms"] is None
    assert isinstance(second["prev_write_ms"], int)


def test_the_handler_never_raises_so_logging_never_reaches_handle_error():
    """A raising handler would print a SQLAlchemy traceback per question."""
    store = _store(fail_on_begin=OSError("down"))
    handler = TrailHandler(store)
    record = logging.LogRecord("x", logging.INFO, "f", 1, "searched", None, None)
    handler.emit(record)  # must not raise
    assert store.failures == 1


# --- reported to the operator, never to the reader -------------------------


def test_a_dropped_record_is_reported_to_stderr(capsys):
    """The spec's "the failure is reported to the operator".

    Previously executed and unasserted: both `_complain` call sites could be
    deleted with the suite staying green, so "reported to the operator" was
    credited to tests blind to its removal.
    """
    store = _store(fail_on_begin=OSError("connection refused"))
    store.record("searched")
    err = capsys.readouterr().err
    assert "trail record dropped" in err
    assert "OSError" in err, "the type is what distinguishes a bad URL from a bad password"
    assert "connection refused" in err


def test_the_report_carries_no_traceback(capsys):
    """Several screens of SQLAlchemy per failed question is how a log stops
    being read at all."""
    store = _store(fail_on_begin=OSError("down"))
    store.record("searched")
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.count("\n") == 1


def test_a_schema_failure_is_reported_and_counted_apart_from_dropped_writes(capsys):
    """A misconfiguration is not continuing data loss, and must not read as it.

    One counter covering both would report a single unusable destination as a
    write failure per question.
    """
    store = TrailStore(engine=_Engine(fail_on_begin=OSError("down")))
    assert store.ensure_schema() is False
    assert (store.schema_failures, store.failures) == (1, 0)
    assert "trail store unavailable" in capsys.readouterr().err


def test_the_process_wide_counter_sees_failures_from_any_store():
    """An operator asking "is this container writing?" holds no store reference."""
    for _ in range(3):
        _store(fail_on_begin=OSError("down")).record("searched")
    assert trail_store.failures() == 3
    assert trail_store.writes() == 0


# --- installing twice ------------------------------------------------------


def test_installing_twice_does_not_write_every_record_twice():
    """Streamlit re-runs the whole script on every interaction.

    A driver that installs at the top of the page installs once per rerun, so an
    unconditional `addHandler` would write each record as many times as the
    reader has clicked -- growing without bound, and looking like traffic rather
    than a bug. The earlier test could not see this: it cleared the handler list
    first.
    """
    logger = logging.getLogger("test.trail.twice")
    logger.handlers.clear()
    engine = _Engine()
    install(engine, logger_name="test.trail.twice")
    install(engine, logger_name="test.trail.twice")

    assert sum(isinstance(h, TrailHandler) for h in logger.handlers) == 1
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info("searched", extra={"question_id": "q1", "fields": {}})
    assert engine.inserts == 1, "the record was written once per installed handler"
    logger.handlers.clear()


def test_a_store_whose_schema_is_absent_does_not_connect_per_call():
    """Connecting is the expensive, unbounded part; the answer is already known.

    `install` hands back a not-ready store rather than None, and a direct caller
    could reasonably keep using it.
    """
    store = TrailStore(engine=_Engine())
    assert store.ready is False
    for _ in range(3):
        assert store.record("searched") is False
    assert store.engine.begins == 0
