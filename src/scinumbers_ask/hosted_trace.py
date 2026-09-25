"""The hosted tracer: Langfuse Cloud, and nothing unless this project says so.

The trail (`trace.py`) covers the deterministic layer and deliberately not the
model calls. This covers the model calls, by handing LangChain a Langfuse
callback for each question. It is a debugger, not a record: the trail is where
anything is read back from (ADR-0750), so every path out of here fails open
(ADR-0710) -- a lost trace costs one trace, and a tracer that could fail a
question would make telemetry an outage.

Three decisions live here rather than in any driver, because the operation that
answers a question is the one place every caller goes through -- the terminal,
the page, the harness and a test that builds `AskAgent` directly:

- **Off unless `SCINUMBERS_TRACING=langfuse`** (ADR-1010). The vendor's keys
  being present do not turn it on: a key left in a shell is not a decision to
  send prompts and corpus text to a third party.
- **A vendor's own switch is refused.** `langsmith` arrives with `langchain-core`
  and traces every call when `LANGSMITH_TRACING` is set, by anyone. The agent's
  stream runs inside `vendor_tracing_refused()` whatever the setting says.
- **The trace id is derived from `question_id`**, so the trail row, a rating and
  the trace name one another without a table that maps them.

Who asked reaches a trace only as an opaque digest the *driver* attaches with
`attributed()` (ADR-1020); nothing here names a person, and the agent is handed
nothing new.

Verified against the installed `langfuse` 4.15.6, `langsmith` 0.11.0 and
`langchain-core` 1.5.6 on 2026-09-24; the answers, and where each came from, are
in the change's design ("Verified against the installed versions").
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import env_setting
from .trace import LOGGER_NAME, QuestionTrace

SETTING = "SCINUMBERS_TRACING"
LANGFUSE = "langfuse"
_OFF = frozenset({"", "off"})

#: What turning it on needs. The host is required rather than defaulted, so the
#: region a deployment sends to is written in its configuration and not inherited
#: from an SDK default. `LANGFUSE_HOST` is the deprecated name and is not read.
CREDENTIALS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")

#: The framework vendor's switches, current name and legacy one. Either makes
#: LangChain attach a LangSmith tracer to every run.
VENDOR_SWITCHES = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")

#: The Hobby tier's monthly allowance, in billable units (traces + observations +
#: scores). Read from langfuse.com/pricing on 2026-09-23.
HOBBY_UNITS = 50_000

#: The window usage is counted over. The billing month is anchored per
#: organisation and the project API cannot read the anchor, so this is the
#: shortest window that always contains the current billing period. It can only
#: over-count, which is the direction that asks the operator more, never less.
USAGE_WINDOW = timedelta(days=31)

#: Above this share of the allowance used, an evaluation run asks before it spends.
APPROVAL_SHARE = 0.5

VERDICT_SCORE = "reader_verdict"
COMMENT_SCORE = "reader_comment"
TRACE_NAME = "ask"

log = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True)
class Setting:
    """What the environment asks for, and what the operator should be told."""

    on: bool
    #: Said to the operator; empty when there is nothing to say.
    problem: str = ""
    public_key: str = ""
    secret_key: str = ""
    base_url: str = ""


def read_setting() -> Setting:
    """Off unless the project's own setting says `langfuse` and every credential is there.

    Off is the answer to anything unexpected -- an unrecognised value, a missing
    key -- because the cost of that direction is a missing trace, and the other
    direction is data leaving the host on a value nobody wrote on purpose. It
    never refuses to start: that would make telemetry an outage (ADR-0710).
    """
    raw = env_setting(SETTING)
    value = raw.strip().lower()
    if value in _OFF:
        return Setting(on=False)
    if value != LANGFUSE:
        return Setting(
            on=False,
            problem=(
                f"{SETTING}={raw!r} is not recognised, so tracing is off. "
                f"The one value that turns it on is {LANGFUSE!r}."
            ),
        )
    values = {name: env_setting(name).strip() for name in CREDENTIALS}
    missing = [name for name, v in values.items() if not v]
    if missing:
        return Setting(
            on=False,
            problem=(
                f"{SETTING}={LANGFUSE} but {', '.join(missing)} "
                f"{'is' if len(missing) == 1 else 'are'} not set, so tracing is off."
            ),
        )
    return Setting(
        on=True,
        public_key=values["LANGFUSE_PUBLIC_KEY"],
        secret_key=values["LANGFUSE_SECRET_KEY"],
        base_url=values["LANGFUSE_BASE_URL"],
    )


def trace_id_for(question_id: str) -> str:
    """The Langfuse trace id of a question: 32 hex characters, the same every time.

    Langfuse's own derivation, so a trace found in its UI and a rating sent later
    agree without either consulting the other.
    """
    from langfuse import Langfuse

    return Langfuse.create_trace_id(seed=question_id)


@dataclass(frozen=True)
class Usage:
    """Units counted over `USAGE_WINDOW`. `None` means it could not be counted.

    Never zero-for-unknown: an unreadable figure shown as nothing used is the
    false all-clear the approval step exists to prevent.
    """

    units: int | None
    traces: int | None
    since: datetime
    until: datetime
    allowance: int = HOBBY_UNITS

    @property
    def share(self) -> float | None:
        return None if self.units is None else self.units / self.allowance

    @property
    def remaining(self) -> int | None:
        return None if self.units is None else max(self.allowance - self.units, 0)

    @property
    def per_question(self) -> float | None:
        """This window's own average, so no constant can go stale. Unknown with no traces."""
        if self.units is None or not self.traces:
            return None
        return self.units / self.traces


@dataclass(frozen=True)
class Estimate:
    """What a run is expected to spend, and whether the operator must approve it."""

    usage: Usage
    questions: int
    units: float | None
    reasons: tuple[str, ...] = field(default=())

    @property
    def needs_approval(self) -> bool:
        return bool(self.reasons)


def estimate(usage: Usage, questions: int) -> Estimate:
    """The conditions under which an evaluation run pauses, as a pure function.

    Pauses when more than half is used, when the run would not fit in what
    remains, or when either figure is unknown. Exactly half does not pause: the
    spec says "more than half".
    """
    per = usage.per_question
    units = None if per is None else per * questions
    reasons: list[str] = []
    if usage.share is None:
        reasons.append("usage this month is unknown")
    elif usage.share > APPROVAL_SHARE:
        reasons.append(f"more than {APPROVAL_SHARE:.0%} of the monthly allowance is used")
    if units is None:
        if questions and usage.share is not None:
            reasons.append("the cost of a question is unknown (no traces counted yet)")
    elif usage.remaining is not None and units > usage.remaining:
        reasons.append("this run is estimated to exceed what remains")
    return Estimate(usage=usage, questions=questions, units=units, reasons=tuple(reasons))


class HostedTracer:
    """One per process. Every method is safe to call when tracing is off.

    The Langfuse client is built on first use and only when the setting is on, so
    an untraced deployment never imports `langfuse` and never starts an
    OpenTelemetry exporter. It is handed a `TracerProvider` of its own, so the
    process's global provider is never replaced (the client would otherwise
    install one whenever the global is still the default).
    """

    def __init__(self, setting: Setting, *, span_exporter: Any = None) -> None:
        self.setting = setting
        self._span_exporter = span_exporter
        self._client: Any = None
        self._broken = False

    @property
    def on(self) -> bool:
        return self.setting.on and not self._broken

    def _langfuse(self) -> Any:
        """The client, or None. A client that cannot be built is tracing off, reported once."""
        if not self.setting.on or self._broken:
            return None
        if self._client is None:
            try:
                from langfuse import Langfuse
                from opentelemetry.sdk.trace import TracerProvider

                self._client = Langfuse(
                    public_key=self.setting.public_key,
                    secret_key=self.setting.secret_key,
                    base_url=self.setting.base_url,
                    tracer_provider=TracerProvider(),
                    span_exporter=self._span_exporter,
                )
            except Exception as exc:  # noqa: BLE001 -- any failure here is tracing off, never an outage
                self._broken = True
                _report_once("tracing.unavailable", detail=f"{type(exc).__name__}: {exc}")
                return None
        return self._client

    def traced(self, config: dict[str, Any], trace: QuestionTrace) -> dict[str, Any]:
        """The framework config for one question, with the tracer's callback when it is on.

        Adds only: a callback bound to the question's trace id, and the metadata
        keys the Langfuse handler lifts onto the whole trace at its root. The
        session travels there rather than in `attributed()`, so every child
        observation carries it from the first one.
        """
        client = self._langfuse()
        if client is None:
            return config
        try:
            from langfuse.langchain import CallbackHandler

            handler = CallbackHandler(
                public_key=self.setting.public_key,
                trace_context={"trace_id": trace_id_for(trace.question_id)},
            )
        except Exception as exc:  # noqa: BLE001
            trace.record("tracing.failed", stage="handler", detail=f"{type(exc).__name__}: {exc}")
            return config
        metadata = dict(config.get("metadata", {}))
        metadata["langfuse_trace_name"] = TRACE_NAME
        metadata["langfuse_tags"] = list(config.get("tags", []))
        if trace.session_id:
            metadata["langfuse_session_id"] = trace.session_id
        callbacks = [*config.get("callbacks", []), handler]
        return {**config, "metadata": metadata, "callbacks": callbacks}

    def attributed(self, user_id: str | None) -> Any:
        """Attach an opaque per-account value to every trace begun inside this block.

        The driver's, not the agent's: this is how a trace learns who asked while
        the agent is handed nothing about the person (ADR-0820, ADR-1020). A no-op
        when tracing is off or nobody is signed in -- `None` attaches nothing,
        rather than a placeholder that reads as an account.
        """
        if user_id is None or self._langfuse() is None:
            return nullcontext()
        try:
            from langfuse import propagate_attributes

            return propagate_attributes(user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            _report_once(
                "tracing.failed", stage="attribution", detail=f"{type(exc).__name__}: {exc}"
            )
            return nullcontext()

    def tagged(self, *tags: str) -> Any:
        """Add tags to every trace begun inside this block, beside the question's own.

        For a driver to say what kind of run this is -- the evaluation harness
        marks its questions `eval` -- without the agent being told who is asking
        (ADR-0110). Langfuse merges these with the tags the handler sets at the
        root, rather than replacing them. A no-op when tracing is off.
        """
        if not tags or self._langfuse() is None:
            return nullcontext()
        try:
            from langfuse import propagate_attributes

            return propagate_attributes(tags=list(tags))
        except Exception as exc:  # noqa: BLE001
            _report_once("tracing.failed", stage="tags", detail=f"{type(exc).__name__}: {exc}")
            return nullcontext()

    def score(
        self,
        question_id: str,
        name: str,
        value: float | str,
        *,
        data_type: str,
        comment: str | None = None,
    ) -> None:
        """Copy a rating onto its question's trace. Never raises; the trail is the record.

        The score id is derived from the question and the score's name, so a
        reader who changes their verdict overwrites it -- within a calendar day,
        which is Langfuse's rule for an overwrite; a change on a later day adds a
        second score. That is accepted for a copy.
        """
        client = self._langfuse()
        if client is None:
            return
        try:
            client.create_score(
                trace_id=trace_id_for(question_id),
                score_id=f"{question_id}-{name}",
                name=name,
                value=value,
                data_type=data_type,
                comment=comment,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "tracing.failed",
                extra={
                    "question_id": question_id,
                    "fields": {"stage": "score", "detail": f"{type(exc).__name__}: {exc}"},
                },
            )

    def monthly_usage(self, now: datetime | None = None) -> Usage | None:
        """Units used over `USAGE_WINDOW`, counted -- Langfuse has no billing API.

        `None` when tracing is off: then there is nothing to ask about, and the
        tracer is not contacted. Any count that fails makes the whole figure
        unknown; a sum over the views that did answer would under-report, which
        is the dangerous direction.

        Traces are counted as root observations: the v2 Metrics API has no
        traces view. Scores are counted over all three score views; a score
        counted by two of them over-counts, which is the safe direction.
        """
        client = self._langfuse()
        if client is None:
            return None
        until = now or datetime.now(UTC)
        since = until - USAGE_WINDOW
        root = [{"column": "isRootObservation", "operator": "=", "value": True, "type": "boolean"}]
        try:
            traces = _count(client, "observations", since, until, filters=root)
            observations = _count(client, "observations", since, until)
            scores = sum(
                _count(client, view, since, until)
                for view in ("scores-numeric", "scores-categorical", "scores-boolean")
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "tracing.usage_unknown",
                extra={"fields": {"detail": f"{type(exc).__name__}: {exc}"}},
            )
            return Usage(units=None, traces=None, since=since, until=until)
        return Usage(units=traces + observations + scores, traces=traces, since=since, until=until)


def _count(
    client: Any, view: str, since: datetime, until: datetime, filters: list | None = None
) -> int:
    """One `count` from the v2 Metrics API. Raises on anything it cannot read as one."""
    query = {
        "view": view,
        "metrics": [{"measure": "count", "aggregation": "count"}],
        "dimensions": [],
        "filters": filters or [],
        "fromTimestamp": since.isoformat().replace("+00:00", "Z"),
        "toTimestamp": until.isoformat().replace("+00:00", "Z"),
    }
    rows = client.api.metrics.metrics(query=json.dumps(query)).data
    if not rows:
        return 0
    if len(rows) != 1:
        raise ValueError(f"{view}: expected one row, got {len(rows)}")
    counts = [v for k, v in rows[0].items() if "count" in k.lower()]
    if len(counts) != 1:
        raise ValueError(f"{view}: no single count in {sorted(rows[0])}")
    return int(counts[0])


_reported: set[str] = set()


def _report_once(event: str, **fields: Any) -> None:
    """Tell the operator, once per process: a setting is not news on every question."""
    key = f"{event}:{sorted(fields.items())}"
    if key in _reported:
        return
    _reported.add(key)
    log.warning(event, extra={"fields": fields})


@contextmanager
def vendor_tracing_refused() -> Iterator[None]:
    """Run the framework with the framework vendor's own tracing off, whatever the env says.

    `LANGSMITH_TRACING` makes LangChain attach a LangSmith tracer to every run,
    worker threads included. `tracing_context(enabled=False)` beats it: probed
    with the switch set, 13 LangSmith runs started without this and 0 with it
    (task 1.3). Langfuse's handler is an ordinary callback and is not affected.

    The operator hears about a set switch once; it is not unset, because
    mutating the environment would silently fix a misconfiguration somebody
    should know about.
    """
    for name in VENDOR_SWITCHES:
        if os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}:
            _report_once("tracing.vendor_switch_refused", variable=name)
    import langsmith

    with langsmith.tracing_context(enabled=False):
        yield


class Isolated:
    """A stream advanced inside a context of its own, with the vendor's tracing refused there.

    Two things must hold for as long as a question's stream runs, and neither
    may leak onto the caller's context, which outlives the question:

    - **The vendor refusal** (`vendor_tracing_refused`). Entered in the caller's
      context, it stayed set there between yields, and a generator abandoned
      without being closed left it set for good -- found when a control test
      stopped seeing LangSmith runs after unrelated tests had run.
    - **The Langfuse handler's own propagation.** It enters one at the root run
      and leaves it when the run ends. A question abandoned mid-stream -- every
      Streamlit rerun -- never ends its run, and when the garbage collector later
      finalised that propagation it reset the context it saw *onto whatever the
      thread was doing then*: the next question was attributed to the previous
      reader. `test_an_abandoned_question_cannot_attribute_a_later_one_to_its_reader`
      reproduces it.

    Every step runs in a copy of the caller's context taken at wrapping time --
    so the driver's attribution comes in, and LangGraph's worker threads copy it
    from here -- and nothing entered inside can reach the caller's.
    """

    def __init__(self, stream: Any) -> None:
        self._context = contextvars.copy_context()
        self._stream = stream
        # Entered inside the private context and never left: the context is
        # discarded with this object, so there is nothing to restore.
        self._context.run(vendor_tracing_refused().__enter__)

    def __iter__(self) -> Isolated:
        return self

    def __next__(self) -> Any:
        return self._context.run(next, self._stream)

    def close(self) -> None:
        self._context.run(self._stream.close)


_current: HostedTracer | None = None


def current() -> HostedTracer:
    """The process's tracer, built from the environment on first use."""
    global _current
    if _current is None:
        setting = read_setting()
        if setting.problem:
            _report_once("tracing.off", detail=setting.problem)
        _current = HostedTracer(setting)
    return _current


def use(tracer: HostedTracer | None) -> None:
    """Replace the process's tracer; `None` rebuilds it from the environment next time.

    For tests, which need a tracer with an in-memory exporter and a clean slate
    between cases. No driver calls this.
    """
    global _current
    _current = tracer
    _reported.clear()
