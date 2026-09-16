"""The trail's durable destination: one append-only table, written best-effort.

`trace.py` writes the trail to a logger, and the file that logger points at lives
inside a container whose disk does not survive a redeploy. Every search, alias
resolution and spend increment from every real session was therefore discarded --
the requirement to log under a per-question identifier was satisfied, and its
stated purpose ("investigable after the fact") defeated, because the run worth
investigating is almost never the run still in progress.

This module is the second destination. It attaches as a logging handler, so no
call site changes and both sinks see the same records.

**It fails open, and that is the opposite of everything else here that writes.**
`SpendGate` fails closed because proceeding costs unbounded real money. This
fails open because proceeding costs one row of a dataset that is read by eye. The
two are both "a write that did not happen", so a reader who notices the
inconsistency will make them consistent -- and one of the two directions is badly
wrong. Hence the noise here, and the requirement in `agent-session` that says the
same thing in the spec.

No Streamlit here, deliberately: `tests/test_driver_independence.py` asserts that
exactly one module imports the web framework. The driver builds the engine (with
`st.connection`, which caches it across sessions) and hands it over.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

# The statement timeout, in milliseconds, applied per transaction.
#
# Neon's default is `0` -- unlimited -- so without this a hung statement hangs for
# ever, which is precisely the "question held open waiting to record a row" that
# the spec forbids. Verified against the live endpoint rather than assumed.
#
# Applied with `SET LOCAL`, inside our own transaction, for two reasons. The
# pooler *refuses* `options=-c statement_timeout=...` at startup (loudly, with a
# doc link -- a prior project had the same parameter silently ignored by a
# different pooler and found out by reading it back). And `SET LOCAL` is scoped to
# the transaction, so it cannot leak onto the next borrower of a pooled
# connection; confirmed by reading it back on three subsequent transactions.
#
# It is set here rather than left to whoever built the engine, because a guard
# that depends on the caller's construction is a guard for one caller.
STATEMENT_TIMEOUT_MS = 2000

#: Seconds to wait for a connection to be established.
#:
#: The statement timeout above bounds a query that has started. It does nothing
#: for an unreachable host, which is where a write actually hangs -- and that is
#: the case the spec's "the destination is slow" scenario is about.
#:
#: Applied by `engine_from_url` and offered to whoever builds the engine instead.
#: It cannot be enforced from inside `record`, because by then the engine exists:
#: libpq takes it at connect time. That makes it the one guard here which does
#: depend on the caller, so it is named in the docstring of `install` rather than
#: left for someone to discover.
CONNECT_TIMEOUT_S = 5

#: Seconds before a pooled connection is discarded and remade.
#:
#: Named here rather than written twice, because `web.trail_destination` builds
#: its engine through `st.connection` and cannot share the construction. Two
#: hard-coded copies are two things that can drift, and one had already grown a
#: comment that did not explain its value.
POOL_RECYCLE_S = 300

#: Consecutive failed writes after which this store stops trying.
#:
#: Without it, "one attempt, never a retry" holds within a write and is defeated
#: across them. A question emits one record per retrieved entry plus its searches,
#: aliases and spend increments -- 25 is ordinary -- so a destination that dies
#: *after* install costs 25 connection attempts, each bounded only by
#: `CONNECT_TIMEOUT_S`. Two minutes added to one question, which is exactly the
#: delay the spec forbids, arrived at by retrying across records instead of
#: within one.
#:
#: Low, because the cost of giving up too early is some missing rows and the cost
#: of giving up too late is the reader waiting. That asymmetry is the whole design
#: (ADR-0710), and it points the same way here.
FAILURES_BEFORE_GIVING_UP = 3

# How long a store that cannot reach its destination waits before trying again,
# and the ceiling that wait doubles towards.
#
# **Giving up used to be permanent, and that lost every record this module was
# written to keep.** `install` runs inside `web.resources`, which is
# `@st.cache_resource` -- once per container. A single failed connection there and
# the handler was never attached at all; the database being awake two seconds
# later changed nothing until somebody restarted the app. Neon's free tier
# suspends compute after minutes of inactivity and a cold start can outrun
# `CONNECT_TIMEOUT_S`, so the ordinary case -- open the app after lunch -- was the
# failing one. Nothing said so: recording fails open, so the only evidence was one
# line on stderr at startup.
#
# The retry is timed rather than per-record because the original reasoning still
# holds: an unreachable database does not fail fast, and paying a connection
# attempt on every question to rediscover something already known is what the
# no-retry rule forbids. Once a minute, doubling to a quarter of an hour, bounds
# that cost to one stalled question per interval while the destination is down.
SCHEMA_RETRY_AFTER_S = 60
SCHEMA_RETRY_CEILING_S = 900

DEFAULT_TABLE = "trail"

#: Failures across every store in this process, so an operator asking "is this
#: container writing anything?" does not have to hold a reference to the store.
#:
#: Per-process and in memory, which bounds what it can answer: it resets on the
#: restart this module exists to survive. "Has anything been recorded this month"
#: is a different question and is answered by querying the table for a gap in
#: timestamps. The two are easy to mistake for each other; ADR-0710.
_FAILURES = 0
_WRITES = 0


def failures() -> int:
    """Writes and schema attempts that did not land, across this process."""
    return _FAILURES


def writes() -> int:
    """Records that did land, across this process."""
    return _WRITES


def reset_counters() -> None:
    """For tests. Process-global state is otherwise shared between them."""
    global _FAILURES, _WRITES
    _FAILURES = 0
    _WRITES = 0


#: Columns are created once, on demand, the way `run_ledger` already does it.
#:
#: Append-only: nothing updates or deletes a row. A new kind of record is a new
#: `event` value, not a migration.
#:
#: `user_email` is here before anyone can sign in, and stays null until they can.
#: It costs nothing now; added later, every row from the period most worth
#: understanding would be permanently unattributable.
#:
#: `prev_write_ms` is how long the *previous* write to this table took. The
#: previous one, because a row cannot carry its own duration -- and the figure
#: that matters is the first write after a long quiet period, which is knowable
#: only by pairing this with the gap between timestamps. A scheduled probe cannot
#: measure it: pinging on a timer keeps the database warm and destroys the
#: condition. See ADR-0700.
_SCHEMA = """
create table if not exists {table} (
    id            bigserial primary key,
    at            timestamptz not null default now(),
    session_id    text,
    question_id   text,
    run_label     text,
    user_email    text,
    event         text not null,
    detail        jsonb not null default '{{}}'::jsonb,
    prev_write_ms integer
)
"""

_INSERT = """
insert into {table}
    (session_id, question_id, run_label, user_email, event, detail, prev_write_ms)
values
    (:session_id, :question_id, :run_label, :user_email, :event,
     cast(:detail as jsonb), :prev_write_ms)
"""


@dataclass
class TrailStore:
    """One append-only table, and the refusal to let it break a question.

    Holds the engine rather than building one: the web driver gets its engine from
    `st.connection`, which caches it at global scope across sessions, and building
    a second one here would pay TCP, TLS and Postgres auth on every rerun.
    """

    engine: Any
    table: str = DEFAULT_TABLE
    #: Writes that were attempted and did not land, for this store. Read by an
    #: operator, never by the person asking a question. The hazard of failing open
    #: is not the lost row -- it is discovering in six weeks that the table has
    #: been empty the whole time, and a counter is the cheapest thing that
    #: answers it. Counted separately from `schema_failures` below: a schema that
    #: could not be created is not a dropped write, and one number covering both
    #: would report a single misconfiguration as continuing data loss.
    failures: int = 0
    schema_failures: int = 0
    writes: int = 0
    #: Reset by any success. Only a *run* of failures means the destination is
    #: gone; one is an ordinary blip and must not close a working store.
    consecutive_failures: int = 0
    ready: bool = False
    # Monotonic, so it is immune to the clock being set. Zero means "try now",
    # which is what a store that has never succeeded should do on its first record.
    retry_after: float = 0.0
    retry_delay: float = SCHEMA_RETRY_AFTER_S
    _last_write_ms: int | None = None

    def ensure_schema(self) -> bool:
        """Create the table if it is absent. Never raises; reports instead.

        Separate from `record` so the cost is paid once, at install, rather than
        being attempted again on every question after a failure.
        """
        try:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
                conn.execute(text(_SCHEMA.format(table=self.table)))
        except Exception as exc:  # noqa: BLE001 - see the module docstring
            global _FAILURES
            self.schema_failures += 1
            _FAILURES += 1
            complain("trail store unavailable", exc)
            self.ready = False
            return False
        self.ready = True
        return True

    def _reachable(self) -> bool:
        """Whether to attempt a write, retrying the schema when its wait is up.

        The one place that decides a store is usable. Both ways of becoming
        unusable -- the schema failing at install, and enough consecutive write
        failures to conclude the destination has died -- clear `ready`, so both
        recover through here and neither needs its own revival path.

        The wait is extended *before* the attempt, so a failure cannot retry on
        the very next record, and reset on success, so an app that recovers does
        not keep a punitive interval it no longer needs.
        """
        if self.ready:
            return True
        now = time.monotonic()
        if now < self.retry_after:
            return False
        self.retry_after = now + self.retry_delay
        self.retry_delay = min(self.retry_delay * 2, SCHEMA_RETRY_CEILING_S)
        if not self.ensure_schema():
            return False
        self.retry_delay = SCHEMA_RETRY_AFTER_S
        self.consecutive_failures = 0
        return True

    def record(
        self,
        event: str,
        *,
        session_id: str | None = None,
        question_id: str | None = None,
        run_label: str | None = None,
        user_email: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> bool:
        """Write one record. Returns whether it landed. **Never raises.**

        The swallow is here rather than at the call site on purpose. A tolerance
        written into the web driver protects the web driver, and the next caller --
        a harness, a test, a second interface -- inherits an operation that
        raises. `guard.py` had to move out of a driver for the mirror-image
        reason; the principle is the same and only the polarity differs.

        One attempt, never a retry. An unreachable database does not fail quickly,
        it hangs, and a question held open to record a row is a worse outcome for
        the reader than the missing row.

        Refuses immediately when the schema was never created. Without this a
        store whose table is absent would open a connection per call and fail on
        the insert every time -- paying the connect cost, which is the expensive
        and unbounded part, to discover something already known. Recovery is a
        restart, or another call to `ensure_schema`; deliberately not automatic,
        since retrying on the render path is what the paragraph above forbids.
        """
        if not self._reachable():
            return False
        started = time.perf_counter()
        try:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
                conn.execute(
                    text(_INSERT.format(table=self.table)),
                    {
                        "session_id": session_id,
                        "question_id": question_id,
                        "run_label": run_label,
                        "user_email": user_email,
                        "event": event,
                        "detail": json.dumps(detail or {}, default=str),
                        "prev_write_ms": self._last_write_ms,
                    },
                )
        except Exception as exc:  # noqa: BLE001 - see the module docstring
            global _FAILURES
            self.failures += 1
            self.consecutive_failures += 1
            _FAILURES += 1
            complain("trail record dropped", exc)
            if self.consecutive_failures >= FAILURES_BEFORE_GIVING_UP:
                # The destination died after install, and every further record
                # would pay a connection attempt to rediscover that. Stopping is
                # the same decision as `record`'s early refusal above, reached by
                # evidence rather than by configuration.
                self.ready = False
                self.retry_after = time.monotonic() + self.retry_delay
                complain(
                    f"trail store pausing after {self.consecutive_failures}"
                    f" consecutive failures; retrying in {int(self.retry_delay)}s",
                    exc,
                )
            return False
        finally:
            # In `finally`, so a *failed* write's duration is recorded too. It is
            # the slow ones that fail, and the figure ADR-0700 exists to collect --
            # the first write after a long quiet period -- is the likeliest of all
            # to be both. Recording only successes discards exactly that case and
            # leaves the next row claiming a duration from some earlier write.
            self._last_write_ms = int((time.perf_counter() - started) * 1000)
        global _WRITES
        self.writes += 1
        _WRITES += 1
        self.consecutive_failures = 0
        return True


def complain(what: str, exc: BaseException) -> None:
    """Report to the operator, never to the reader, and never a traceback.

    A traceback here would be several screens of SQLAlchemy per failed question,
    which is how a log stops being read at all. The type and the message identify
    a misconfigured URL, an unreachable host and a refused password differently
    enough to act on.
    """
    print(f"{what}: {type(exc).__name__}: {exc}", file=sys.stderr)


class TrailHandler(logging.Handler):
    """Bridges `trace.py`'s logger to the store, so no call site changes.

    The trail is already a logger with a JSON-lines formatter; a second handler is
    the smallest thing that gives it a second destination, and it means a caller
    that knows nothing about this module still gets its records persisted.
    """

    def __init__(self, store: TrailStore) -> None:
        super().__init__(logging.INFO)
        self.store = store

    def emit(self, record: logging.LogRecord) -> None:
        """Never raises, so `logging`'s own error path is never reached.

        `logging.Handler.handleError` would print a traceback per failure to
        stderr, which is the noise `complain` exists to avoid.
        """
        # `or None` on each, so an absent identifier becomes NULL rather than an
        # empty string. `QuestionTrace.session_id` defaults to `""` and is always
        # put in `extra`, so without this a sessionless record writes `''` --
        # `where session_id is null` then returns nothing on a table full of
        # them, and `count(distinct session_id)` reports a phantom session. The
        # file sink already omits the key when falsy; the two must agree.
        self.store.record(
            record.getMessage(),
            session_id=getattr(record, "session_id", None) or None,
            question_id=getattr(record, "question_id", None) or None,
            run_label=getattr(record, "run_label", None) or None,
            user_email=getattr(record, "user_email", None) or None,
            detail=getattr(record, "fields", {}) or {},
        )


def install(engine: Any, *, table: str = DEFAULT_TABLE, logger_name: str) -> TrailStore | None:
    """Attach a durable destination to the trail's logger. Returns None if absent.

    Additive: the existing file handler stays. A developer running locally needs
    no database, and refusing to start without one would make the absence of
    telemetry an outage -- which is a worse version of the failure this module
    exists to fix.

    **Idempotent, and that is load-bearing rather than tidy.** Streamlit re-runs
    its whole script on every interaction, so a driver calling this at the top of
    the page calls it once per rerun. An unconditional `addHandler` would stack a
    handler per interaction and write each record as many times as the reader has
    clicked -- growing without bound, and looking like traffic rather than like a
    bug. Any handler this module previously attached is removed first.

    `logger_name` is passed rather than imported from `trace` so this module does
    not depend on the one that will depend on it.
    """
    if engine is None:
        return None
    store = TrailStore(engine=engine, table=table)
    # The schema is attempted here so the cost is paid once at startup rather than
    # on a reader's first question -- but a failure here **must not** be the end of
    # it. The handler is attached either way, and `_reachable` retries on a later
    # record. Returning early without attaching is what made one timed-out
    # connection at startup silently discard every record for the life of the
    # container; see SCHEMA_RETRY_AFTER_S.
    store.ensure_schema()
    logger = logging.getLogger(logger_name)
    for existing in [h for h in logger.handlers if isinstance(h, TrailHandler)]:
        logger.removeHandler(existing)
    logger.addHandler(TrailHandler(store))
    return store


def engine_from_url(url: str, **kwargs: Any) -> Any:
    """An engine with this module's own timeouts, for a caller without Streamlit.

    The web driver gets its engine from `st.connection`, which caches it across
    sessions; this exists for the terminal, the evaluation harness and tests,
    which have no such thing. `connect_timeout` is set here because libpq takes it
    at connect time and it therefore cannot be enforced from inside `record` --
    the one guard in this module that does depend on how the engine was built.
    """
    from sqlalchemy import create_engine

    connect_args = {"connect_timeout": CONNECT_TIMEOUT_S} | kwargs.pop("connect_args", {})
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_S,
        connect_args=connect_args,
        **kwargs,
    )
