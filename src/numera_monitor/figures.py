"""The figures the operator reads, as pure functions over trail rows.

No database and no page: a row is a plain value, so every figure is testable without
either, and the module cannot grow a query by accident. It also imports nothing from
`numera_ask` -- the ending map below is keyed by strings, and a test holds it
against `EndReason` and against the events the application writes, so the two sides
cannot drift apart silently.

Every figure that is a rate carries its denominator (`Share`). A rate shown without
the count it is out of reads as precise when three questions are all there is.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

#: What a question is when no recorded event says how it ended. Never `answered`.
UNIDENTIFIED = "unidentified"

TRACER_TROUBLE = frozenset({"tracing.failed", "tracing.unavailable", "tracing.usage_unknown"})

LIMIT_ENDINGS = frozenset(
    {"spend_ceiling", "run_budget", "retrieval_bound", "conversation_bound", "provider_limit"}
)

#: A gap between consecutive rows longer than this makes the next write "cold": long
#: enough for the database to have gone to sleep, which is the cost worth seeing.
QUIET_GAP = timedelta(minutes=10)

#: Event -> the `EndReason` values it can mean. A one-member set is the answer; a larger
#: one is resolved by `detail["reason"]`, which must itself be a member.
ENDING_EVENTS: dict[str, frozenset[str]] = {
    event: frozenset(reasons)
    for event, reasons in {
        "question.answered": {"answered"},
        "question.no_answer": {"no_answer"},
        "not_configured": {"not_configured"},
        "spend.unpriceable": {"not_configured"},
        "run.budget_reached": {"run_budget"},
        "conversation.bound_reached": {"conversation_bound"},
        "spend.limit_reached": {"spend_ceiling", "run_budget"},
        "retrieval.bound_reached": {"retrieval_bound"},
        "provider.failed": {"provider_failure", "provider_limit"},
        "internal.failed": {"internal_error"},
    }.items()
}


@dataclass(frozen=True)
class Row:
    id: int
    at: datetime
    event: str
    question_id: str | None = None
    session_id: str | None = None
    run_label: str | None = None
    user_email: str | None = None
    user_role: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)
    prev_write_ms: int | None = None


@dataclass(frozen=True)
class Share:
    count: int
    of: int

    @property
    def ratio(self) -> float | None:
        return None if self.of == 0 else self.count / self.of


def _by_write_order(rows: Iterable[Row]) -> list[Row]:
    # `id` is write order; `at` is only usually the same, and the ending is "the last
    # thing written", so the id is what is sorted on.
    return sorted(rows, key=lambda r: r.id)


# --- Endings --------------------------------------------------------------------


@dataclass(frozen=True)
class Ending:
    kind: str
    last_event: str


def _kind_of(row: Row) -> str:
    reasons = ENDING_EVENTS[row.event]
    if len(reasons) == 1:
        return next(iter(reasons))
    reason = row.detail.get("reason")
    # Only a reason the event can mean is believed. Unidentified costs the operator a
    # look; a payload talked into "answered" costs a wrong rate that looks ordinary,
    # so the uncertainty is absorbed on the unidentified side.
    return reason if isinstance(reason, str) and reason in reasons else UNIDENTIFIED


def classify(rows: Iterable[Row]) -> dict[str, Ending]:
    """How each *asked* question ended.

    Only questions with a `question.asked` row are classified: a rating of a question
    asked before the period is not a question in it. The ending is the latest mapped
    event; records after it (the answer, its evidence, a rating) never change it,
    because `ask` writes those after the ending.
    """
    ordered = _by_write_order(rows)
    asked = {r.question_id for r in ordered if r.event == "question.asked" and r.question_id}
    last_event: dict[str, str] = {}
    ending_row: dict[str, Row] = {}
    for r in ordered:
        q = r.question_id
        if q not in asked:
            continue
        last_event[q] = r.event
        if r.event in ENDING_EVENTS:
            ending_row[q] = r
    return {
        q: Ending(_kind_of(ending_row[q]) if q in ending_row else UNIDENTIFIED, last_event[q])
        for q in asked
    }


# --- Health ---------------------------------------------------------------------


@dataclass(frozen=True)
class Health:
    questions: int
    testers: int
    unattributed_questions: int
    endings: dict[str, Share]
    limit_endings: Share
    spend_micro: int
    spend_per_question_micro: int | None

    @property
    def quiet(self) -> bool:
        return self.questions == 0


def _spend(rows: Iterable[Row]) -> int:
    # From the increments, not `question.answered`'s total: a question stopped at a
    # limit still cost money, and the answered total would miss exactly those.
    return sum(int(r.detail.get("increment") or 0) for r in rows if r.event == "spend.increment")


def health(rows: Iterable[Row]) -> Health:
    rows = _by_write_order(rows)
    endings = classify(rows)
    n = len(endings)
    asked = [r for r in rows if r.event == "question.asked" and r.question_id]
    kinds: dict[str, int] = {}
    for e in endings.values():
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    spend = _spend(rows)
    return Health(
        questions=n,
        testers=len({r.user_email for r in asked if r.user_email}),
        unattributed_questions=sum(1 for r in asked if not r.user_email),
        endings={k: Share(c, n) for k, c in kinds.items()},
        limit_endings=Share(sum(c for k, c in kinds.items() if k in LIMIT_ENDINGS), n),
        spend_micro=spend,
        spend_per_question_micro=spend // n if n else None,
    )


# --- Quality --------------------------------------------------------------------


@dataclass(frozen=True)
class Verdicts:
    up: int
    down: int

    @property
    def rated(self) -> int:
        return self.up + self.down


@dataclass(frozen=True)
class Comment:
    at: datetime
    question_id: str
    run_label: str | None
    comment: str
    question: str | None
    answer: str | None


@dataclass(frozen=True)
class Quality:
    verdicts: dict[str | None, Verdicts]
    unattributed_verdicts: int
    comments: list[Comment]
    ungrounded: Share
    unsupported_citations: Share
    cited: Share


def _latest_verdicts(rows: list[Row]) -> dict[str, Row]:
    latest: dict[str, Row] = {}
    for r in rows:
        if r.event != "feedback.verdict" or not r.question_id:
            continue
        if r.detail.get("verdict") in ("up", "down"):
            latest[r.question_id] = r
    return latest


def quality(rows: Iterable[Row]) -> Quality:
    rows = _by_write_order(rows)
    counts: dict[str | None, list[int]] = {}
    latest = _latest_verdicts(rows)
    for r in latest.values():
        up_down = counts.setdefault(r.run_label, [0, 0])
        up_down[0 if r.detail["verdict"] == "up" else 1] += 1

    # Joined here rather than in SQL so the figures stay pure; a comment on a question
    # asked before the period still shows, with the text it lacks left as None.
    asked_text = {
        r.question_id: r.detail.get("question")
        for r in rows
        if r.event == "question.asked" and r.question_id
    }
    answer_text = {
        r.question_id: r.detail.get("answer")
        for r in rows
        if r.event == "answer.given" and r.question_id
    }
    comments = [
        Comment(
            at=r.at,
            question_id=r.question_id,
            run_label=r.run_label,
            comment=str(r.detail.get("comment", "")),
            question=asked_text.get(r.question_id),
            answer=answer_text.get(r.question_id),
        )
        for r in reversed(rows)
        if r.event == "feedback.comment" and r.question_id
    ]

    given = {r.question_id for r in rows if r.event == "answer.given" and r.question_id}
    # Intersected with `given`: `ask` also judges the prose of a question that ended
    # on a provider or internal failure, with no answer given, and those rows would
    # otherwise count in the numerator and not the denominator -- "2 of 1 (200%)",
    # or, mixed into a busy period, an inflated rate that looks ordinary.
    ungrounded = given & {
        r.question_id for r in rows if r.event == "answer.ungrounded" and r.question_id
    }
    unsupported = given & {
        r.question_id for r in rows if r.event == "citations.unsupported" and r.question_id
    }
    evidence = [r for r in rows if r.event == "answer.evidence"]
    return Quality(
        verdicts={k: Verdicts(up, down) for k, (up, down) in counts.items()},
        unattributed_verdicts=sum(1 for r in latest.values() if not r.user_email),
        comments=comments,
        ungrounded=Share(len(ungrounded), len(given)),
        unsupported_citations=Share(len(unsupported), len(given)),
        cited=Share(
            sum(len(r.detail.get("cited") or []) for r in evidence),
            sum(len(r.detail.get("retrieved") or []) for r in evidence),
        ),
    )


# --- Recording health -----------------------------------------------------------


@dataclass(frozen=True)
class ColdWrite:
    at: datetime
    gap: timedelta
    write_ms: int | None


@dataclass(frozen=True)
class Recording:
    last_row_at: datetime | None
    tracer_trouble: dict[str, int]
    cold_writes: list[ColdWrite]


def recording(rows: Iterable[Row]) -> Recording:
    rows = _by_write_order(rows)
    trouble: dict[str, int] = {}
    for r in rows:
        if r.event in TRACER_TROUBLE:
            trouble[r.event] = trouble.get(r.event, 0) + 1
    cold = []
    for i in range(1, len(rows)):
        gap = rows[i].at - rows[i - 1].at
        if gap > QUIET_GAP:
            # A row cannot carry its own duration, so the write after the gap is timed
            # by the row after *it* (ADR-0700); None until that row exists.
            nxt = rows[i + 1].prev_write_ms if i + 1 < len(rows) else None
            cold.append(ColdWrite(at=rows[i].at, gap=gap, write_ms=nxt))
    return Recording(
        last_row_at=rows[-1].at if rows else None,
        tracer_trouble=trouble,
        cold_writes=cold,
    )


# --- Recent questions -----------------------------------------------------------


@dataclass(frozen=True)
class QuestionLine:
    question_id: str
    asked_at: datetime
    asker: str | None
    run_label: str | None
    question: str
    ending: Ending
    spend_micro: int
    verdict: str | None


def questions(rows: Iterable[Row]) -> list[QuestionLine]:
    """One line per asked question, newest first."""
    rows = _by_write_order(rows)
    endings = classify(rows)
    latest = _latest_verdicts(rows)
    lines = []
    for r in rows:
        if r.event != "question.asked" or not r.question_id:
            continue
        q = r.question_id
        verdict = latest.get(q)
        lines.append(
            QuestionLine(
                question_id=q,
                asked_at=r.at,
                asker=r.user_email,
                run_label=r.run_label,
                question=str(r.detail.get("question", "")),
                ending=endings[q],
                spend_micro=_spend(x for x in rows if x.question_id == q),
                verdict=verdict.detail["verdict"] if verdict else None,
            )
        )
    lines.reverse()
    return lines
