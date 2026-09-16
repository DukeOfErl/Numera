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
import time

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

    def __init__(self, fail_on_execute: Exception | None = None, delay: float = 0.0):
        self.fail_on_execute = fail_on_execute
        # Used by exactly one test, and only because there is arithmetic to get
        # wrong: `record` converts an elapsed duration into milliseconds. An
        # earlier version of this parameter existed for a test that claimed to
        # exercise a slow *write*, where there is no client-side code path at
        # all -- that one was withdrawn, and this one is not the same thing.
        self.delay = delay
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        if self.delay:
            time.sleep(self.delay)
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

    def __init__(self, fail_on_begin=None, fail_on_execute=None, delay=0.0):
        self.fail_on_begin = fail_on_begin
        self.fail_on_execute = fail_on_execute
        self.delay = delay
        self.conns: list[_Conn] = []
        self.begins = 0

    def begin(self):
        self.begins += 1
        if self.fail_on_begin is not None:
            raise self.fail_on_begin
        conn = _Conn(self.fail_on_execute, self.delay)
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
    for _ in range(trail_store.FAILURES_BEFORE_GIVING_UP):
        store.record("searched")
    assert (store.failures, store.writes) == (trail_store.FAILURES_BEFORE_GIVING_UP, 0)


# --- a destination that dies after install --------------------------------


def test_a_dead_destination_stops_being_attempted():
    """The cost of failing open is per record, and a question emits many.

    One per retrieved entry, plus searches, aliases and spend increments -- 25 is
    ordinary. `record` refused early only when `ensure_schema` had failed at
    install, so a store that installed cleanly and later lost its destination kept
    trying for ever: 25 connection attempts, each bounded only by
    `CONNECT_TIMEOUT_S`, is about two minutes added to one question.

    That is "one attempt, never a retry" holding within a write and being defeated
    across them -- and a delay the spec forbids in as many words.
    """
    store = _store(fail_on_begin=OSError("host is gone"))
    for _ in range(25):
        store.record("searched")

    assert store.engine.begins == trail_store.FAILURES_BEFORE_GIVING_UP
    assert store.ready is False
    assert store.failures == trail_store.FAILURES_BEFORE_GIVING_UP


def test_one_failure_does_not_close_a_working_store():
    """A blip is not a dead host, and only a *run* of failures means it is.

    The counter resets on success, so this varies the dimension the rule reads --
    consecutive-ness -- rather than merely the number of failures. Without the
    reset, any store that ever failed three times in its life would close.
    """
    engine = _Engine()
    store = TrailStore(engine=engine)
    store.ready = True

    for _ in range(10):
        engine.fail_on_begin = OSError("blip")
        store.record("searched")
        engine.fail_on_begin = None
        store.record("searched")

    assert store.ready is True, "an intermittent destination was closed"
    assert store.writes == 10


# --- configuration is absence-tolerant ------------------------------------


def test_install_with_no_engine_returns_none_and_adds_no_handler():
    logger = logging.getLogger("test.trail.absent")
    before = list(logger.handlers)
    assert install(None, logger_name="test.trail.absent") is None
    assert logger.handlers == before


def test_install_attaches_a_handler_even_when_the_schema_cannot_be_created():
    """**This test asserted the opposite, and the opposite lost every record.**

    Attaching no handler made a failure at install permanent: `install` runs
    inside `web.resources`, which is `@st.cache_resource` and therefore runs once
    per container, so a single timed-out connection at startup meant nothing was
    even trying to write for the life of the process. Neon suspends a free-tier
    branch after minutes of idleness and a cold start can outrun the connect
    timeout, so "open the app after lunch" was the failing case. It was silent:
    recording fails open, and the only evidence was one line on stderr.

    The reasoning that produced the old behaviour was not wrong about cost -- a
    reader must not pay a connection attempt per question to rediscover a dead
    destination. That is now `_reachable`'s timed backoff, which bounds the cost
    without making the verdict permanent.
    """
    logger = logging.getLogger("test.trail.broken")
    logger.handlers.clear()
    store = install(_Engine(fail_on_begin=OSError("down")), logger_name="test.trail.broken")
    assert store is not None and store.ready is False
    assert any(isinstance(h, TrailHandler) for h in logger.handlers), (
        "no handler, so nothing will ever retry: the destination is dead for the "
        "life of the process even after it comes back"
    )


def test_a_destination_that_was_asleep_at_startup_is_used_once_it_wakes():
    """The whole point of the change above, stated as the behaviour it buys.

    The engine refuses the schema attempt at install and works afterwards -- which
    is exactly a suspended serverless database taking longer to wake than the
    connect timeout allows.
    """

    class WakesUp(_Engine):
        """Refuses the first connection, then behaves. Built on `_Engine` rather
        than beside it, so the transaction it hands back is the same one every
        other test here exercises."""

        def __init__(self):
            super().__init__()
            self.attempts = 0

        def begin(self):
            self.attempts += 1
            if self.attempts == 1:
                self.begins += 1
                raise TimeoutError("compute is suspended")
            return super().begin()

    logger = logging.getLogger("test.trail.wakes")
    logger.handlers.clear()
    engine = WakesUp()
    store = install(engine, logger_name="test.trail.wakes")
    assert store.ready is False, "the fixture did not reproduce a failed install"

    assert store.record("searched") is True, "the store never recovered"
    assert store.record("searched") is True, "recovery did not stick"
    assert store.writes == 2


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


def test_the_counters_accumulate_rather_than_being_set():
    """`+= 1`, not `= 1`. Found by mutation testing, not by review.

    Every earlier counter test wrote or failed exactly once, so `self.writes = 1`
    and `_WRITES = 1` were indistinguishable from the real thing -- and a counter
    that never passes one answers "is this container writing?" with a number that
    looks fine and means nothing.
    """
    store = _store()
    for _ in range(3):
        store.record("searched")
    assert store.writes == 3
    assert trail_store.writes() == 3

    broken = _store(fail_on_begin=OSError("down"))
    for _ in range(2):
        broken.record("searched")
    assert broken.failures == 2
    assert trail_store.failures() == 2


def test_a_second_schema_failure_is_counted_too():
    """Same defect, the other counters: `_FAILURES = 1` and `schema_failures = 1`.

    Retried on one store as well as across two, because the per-instance counter
    and the process-wide one are separate lines and only the second was covered.
    """
    first = TrailStore(engine=_Engine(fail_on_begin=OSError("down")))
    second = TrailStore(engine=_Engine(fail_on_begin=OSError("down")))
    first.ensure_schema()
    second.ensure_schema()
    assert trail_store.failures() == 2

    first.ensure_schema()
    assert first.schema_failures == 2, "the per-store counter did not accumulate"


def test_a_schema_failure_names_the_exception_type_too(capsys):
    """The type is what separates a bad URL from a bad password from a dead host.

    `complain("trail store unavailable", None)` survived: the existing test
    asserted only the message, so the exception could have been dropped on the
    way and the line would still have read as a report.
    """
    TrailStore(engine=_Engine(fail_on_begin=OSError("refused"))).ensure_schema()
    err = capsys.readouterr().err
    assert "OSError" in err
    assert "refused" in err


def test_install_uses_the_table_it_was_given():
    """`table=None` and the default both survived: nothing read it back."""
    store = install(_Engine(), table="trail_elsewhere", logger_name="test.trail.table")
    assert store is not None
    assert store.table == "trail_elsewhere"
    logging.getLogger("test.trail.table").handlers.clear()


def test_the_table_named_is_the_table_written_to():
    """Both statements carry it, and neither test could see it before.

    The double accepts any string, so `_SCHEMA.format(table=None)` and
    `_INSERT.format(table=None)` both survived -- offline nothing read the SQL,
    and the live tests that would are deselected by default.
    """
    store = TrailStore(engine=_Engine(), table="trail_elsewhere")
    assert store.ensure_schema()
    store.record("searched")

    statements = " ".join(s for c in store.engine.conns for s in c.statements)
    assert "trail_elsewhere" in statements
    assert statements.count("trail_elsewhere") >= 2, "schema and insert must both name it"
    assert "None" not in statements


def test_an_absent_identifier_is_written_as_null_not_as_an_empty_string():
    """The two sinks must agree, and one of them omits the key entirely.

    `QuestionTrace.session_id` defaults to `""` and is always put in `extra`, so
    `getattr(record, "session_id", None)` returns `""` and never `None`. Written
    through, a sessionless row gets `''` -- and then `where session_id is null`
    returns nothing on a table full of them, while `count(distinct session_id)`
    reports a phantom session. The file sink already omits the key when falsy.
    """
    store = _store()
    handler = TrailHandler(store)
    record = logging.LogRecord("x", logging.INFO, "f", 1, "searched", None, None)
    record.session_id = ""
    record.question_id = "q1"
    record.run_label = ""
    handler.emit(record)

    (written,) = store.engine.written
    assert written["session_id"] is None
    assert written["run_label"] is None
    assert written["question_id"] == "q1"


def test_the_handler_carries_a_user_when_there_is_one():
    """Null until people can sign in, which is exactly why it needs a test now.

    `user_email=None` hardcoded in `emit` survived everything: no test set the
    attribute, because nothing sets it in production yet. The column exists so
    that rows written before identity arrives are not the only unattributable
    ones -- a guarantee that silently stops holding the day identity lands.
    """
    store = _store()
    handler = TrailHandler(store)
    record = logging.LogRecord("x", logging.INFO, "f", 1, "searched", None, None)
    record.user_email = "someone@example.com"
    handler.emit(record)
    (written,) = store.engine.written
    assert written["user_email"] == "someone@example.com"


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


def test_a_failed_write_s_duration_is_recorded_too():
    """The slow writes are the ones that fail, and theirs is the figure wanted.

    Updated in `finally`, so a failure's elapsed time still lands on the next
    row. Recorded only on success, the first write after a long quiet period --
    the likeliest to be both slow and failing, and the whole reason the column
    exists (ADR-0700) -- is exactly the case discarded, leaving the next row
    claiming a duration from some earlier, faster write.
    """
    engine = _Engine(delay=0.05)
    store = TrailStore(engine=engine)
    store.ready = True

    engine.fail_on_execute = ValueError("nope")
    store.record("doomed")
    engine.fail_on_execute = None
    store.record("fine")

    # Two entries: the double records parameters before raising, so the failed
    # write's own INSERT is visible too. The second is the one under test.
    doomed, fine = engine.written
    assert doomed["prev_write_ms"] is None, "nothing preceded the first write"
    assert fine["prev_write_ms"] is not None, "the failed write's duration was discarded"
    assert fine["prev_write_ms"] >= 25


def test_the_duration_is_in_milliseconds_and_not_some_other_unit():
    """`* 1000`, not `/ 1000`. Found by mutation testing.

    The assertion above was `isinstance(..., int)`, which `0` satisfies for ever
    -- so dividing instead of multiplying survived, and the figure task 6.2 exists
    to collect would have been zero on every row with nothing to say so. The
    number is the whole point of the column; its type is not.

    This uses a deliberate delay, unlike the withdrawn `test_a_slow_write_...`.
    The difference is that there is arithmetic here to get wrong: `record`
    converts an elapsed duration into a unit, and a double can make the elapsed
    duration large enough to read. There was no equivalent code path for the
    timeout, which is why faking one there would have measured the fake.
    """
    store = _store(delay=0.05)
    store.record("first")
    store.record("second")
    _, second = store.engine.written
    # 50 ms of sleep, generously bounded: the assertion is the unit, not the clock.
    assert 25 <= second["prev_write_ms"] <= 5_000, second["prev_write_ms"]


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

    Previously executed and unasserted: both `complain` call sites could be
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


def test_a_store_that_cannot_reach_its_destination_does_not_connect_per_call():
    """Connecting is the expensive, unbounded part, and a reader pays for it.

    The retry that revives a sleeping destination must not become a connection
    attempt per question: an unreachable database does not fail fast, so ten
    records would be ten stalls. One attempt, then silence until the wait is up.

    Varies the count rather than asserting zero -- zero was the old, permanent
    behaviour, and a test asserting it would fail the moment recovery worked.
    """
    store = TrailStore(engine=_Engine(fail_on_begin=OSError("down")))
    assert store.ready is False
    for _ in range(10):
        assert store.record("searched") is False
    assert store.engine.begins == 1, (
        f"{store.engine.begins} connection attempts for 10 records; the backoff is not holding"
    )


def test_the_wait_before_retrying_grows_and_is_reset_by_success():
    """A destination down for an hour must not be probed 60 times.

    Reset on success matters as much: an app that recovers should not keep a
    punitive interval it no longer needs.
    """
    store = TrailStore(engine=_Engine(fail_on_begin=OSError("down")))
    first = store.retry_delay
    store.record("searched")
    assert store.retry_delay > first, "the wait did not grow after a failure"

    store.retry_after = 0.0
    store.engine = _Engine()
    assert store.record("searched") is True
    assert store.retry_delay == trail_store.SCHEMA_RETRY_AFTER_S, (
        "a recovered store kept its punitive wait"
    )
