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
    ready: bool = False
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
            _complain("trail store unavailable", exc)
            self.ready = False
            return False
        self.ready = True
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
        if not self.ready:
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
            _FAILURES += 1
            _complain("trail record dropped", exc)
            return False
        global _WRITES
        self.writes += 1
        _WRITES += 1
        self._last_write_ms = int((time.perf_counter() - started) * 1000)
        return True


def _complain(what: str, exc: BaseException) -> None:
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
        stderr, which is the noise `_complain` exists to avoid.
        """
        self.store.record(
            record.getMessage(),
            session_id=getattr(record, "session_id", None),
            question_id=getattr(record, "question_id", None),
            run_label=getattr(record, "run_label", None),
            user_email=getattr(record, "user_email", None),
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
    if not store.ensure_schema():
        # Reported once, here, rather than once per question. A destination that
        # is configured and broken is an operator's problem and not a reader's.
        return store
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
        # The container sleeps after 12 hours of no traffic, by which time the far
        # side has dropped every connection the pool believes it holds.
        pool_recycle=300,
        connect_args=connect_args,
        **kwargs,
    )
