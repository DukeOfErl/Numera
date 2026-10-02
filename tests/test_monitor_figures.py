"""The figures the operator reads, computed from trail rows with no database and no page.

Every expected value here was written from `operator-monitoring`'s requirements and
the trail's recording order (`AskAgent.ask` records the answer and its evidence
*after* the ending, because it records events as they pass on to the driver), not
read back from a run of the code.

The ending classification is a rule that marks some questions and not others, so
both populations are tested: the questions it must call answered, and the ones it
must not -- no ending at all, an event it does not know, a reason outside the
event's set. The negative cases vary the event names and the `reason` it reads,
not merely the outcome.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

import pytest

from scinumbers_ask.events import EndReason
from scinumbers_monitor import figures
from scinumbers_monitor.figures import (
    ENDING_EVENTS,
    LIMIT_ENDINGS,
    UNIDENTIFIED,
    Row,
    Share,
    classify,
    health,
    quality,
    questions,
    recording,
)

ASK_SOURCE = Path(__file__).resolve().parents[1] / "src" / "scinumbers_ask"
T0 = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
_ids = count(1)


def row(event, *, at=None, q=None, email=None, label="run-a", prev_ms=None, **detail) -> Row:
    """One trail row. Ids increase in call order, which is write order."""
    n = next(_ids)
    return Row(
        id=n,
        at=at or T0 + timedelta(seconds=n),
        event=event,
        question_id=q,
        session_id="s1" if q else None,
        run_label=label,
        user_email=email,
        user_role="tester" if email else None,
        detail=detail,
        prev_write_ms=prev_ms,
    )


def answered(q, *, email="a@x.org", label="run-a", spend=(1000,), cited=(), retrieved=()):
    """The rows one answered question leaves, in the order `ask` writes them."""
    rows = [row("question.asked", q=q, email=email, label=label, question=f"what is {q}?")]
    rows += [row("spend.increment", q=q, email=email, label=label, increment=s) for s in spend]
    rows.append(row("question.answered", q=q, email=email, label=label, spend_micro=sum(spend)))
    rows.append(row("answer.given", q=q, email=email, label=label, answer=f"{q} is 42"))
    rows.append(
        row(
            "answer.evidence",
            q=q,
            email=email,
            label=label,
            cited=list(cited),
            retrieved=list(retrieved),
        )
    )
    return rows


# --- The map --------------------------------------------------------------------


def test_the_map_covers_every_end_reason_and_nothing_else():
    """A new `EndReason` fails here until it is mapped. Until then its questions
    land in unidentified, never in answered."""
    mapped = set().union(*ENDING_EVENTS.values())
    assert mapped == {reason.value for reason in EndReason}


def test_every_mapped_event_is_one_the_application_records():
    """A renamed event would otherwise leave its questions unidentified for ever,
    with nothing to say why."""
    literals = set()
    for path in ASK_SOURCE.glob("*.py"):
        literals |= set(re.findall(r'"([a-z_]+(?:\.[a-z_]+)?)"', path.read_text()))
    missing = sorted(set(ENDING_EVENTS) - literals)
    assert not missing, f"mapped but never written by scinumbers_ask: {missing}"


def test_the_two_events_that_carry_their_reason_say_so():
    assert ENDING_EVENTS["spend.limit_reached"] == {"spend_ceiling", "run_budget"}
    assert ENDING_EVENTS["provider.failed"] == {"provider_failure", "provider_limit"}


# --- Classification: what it must call answered ---------------------------------


def test_asked_and_answered_is_answered():
    endings = classify(answered("q1"))
    assert endings["q1"].kind == "answered"


def test_records_after_the_ending_do_not_change_it():
    """The answer, its evidence and a rating all follow `question.answered`."""
    rows = answered("q1") + [
        row("feedback.verdict", q="q1", email="a@x.org", verdict="down"),
        row("feedback.comment", q="q1", email="a@x.org", comment="wrong unit"),
    ]
    assert classify(rows)["q1"].kind == "answered"


def test_an_event_carrying_its_reason_is_classified_by_that_reason():
    rows = [
        row("question.asked", q="q1", question="?"),
        row("spend.limit_reached", q="q1", reason="run_budget", spent=5, limit=5),
        row("question.asked", q="q2", question="?"),
        row("provider.failed", q="q2", reason="provider_limit", error="E"),
    ]
    endings = classify(rows)
    assert endings["q1"].kind == "run_budget"
    assert endings["q2"].kind == "provider_limit"


def test_two_events_for_one_reason_both_classify():
    rows = [
        row("question.asked", q="q1", question="?"),
        row("spend.unpriceable", q="q1", detail="no price"),
        row("question.asked", q="q2", question="?"),
        row("not_configured", q="q2", detail="no key"),
    ]
    endings = classify(rows)
    assert endings["q1"].kind == endings["q2"].kind == "not_configured"


def test_the_latest_ending_wins():
    """`at` and write order agree in practice; the later of two endings is the one
    the question finished on."""
    rows = [
        row("question.asked", q="q1", question="?"),
        row("question.no_answer", q="q1"),
        row("question.answered", q="q1"),
    ]
    assert classify(rows)["q1"].kind == "answered"


# --- Classification: what it must not call answered -----------------------------


def test_asked_and_never_ended_is_unidentified_and_names_its_last_event():
    rows = [
        row("question.asked", q="q1", question="?"),
        row("entry.retrieved", q="q1", entry="123456"),
    ]
    ending = classify(rows)["q1"]
    assert ending.kind == UNIDENTIFIED
    assert ending.last_event == "entry.retrieved"


def test_an_unknown_last_event_is_unidentified_not_answered():
    """An ending added to the application after this map was written."""
    rows = [
        row("question.asked", q="q1", question="?"),
        row("answer.given", q="q1", answer="partial"),
        row("question.abandoned_by_new_rule", q="q1"),
    ]
    ending = classify(rows)["q1"]
    assert ending.kind == UNIDENTIFIED
    assert ending.last_event == "question.abandoned_by_new_rule"


@pytest.mark.parametrize("detail", [{}, {"reason": "answered"}, {"reason": "nonsense"}])
def test_a_reason_outside_the_event_s_set_is_unidentified(detail):
    """`provider.failed` can only mean the provider; a payload claiming `answered`,
    or nothing, must not be believed into a known ending."""
    rows = [row("question.asked", q="q1", question="?"), row("provider.failed", q="q1", **detail)]
    assert classify(rows)["q1"].kind == UNIDENTIFIED


def test_only_asked_questions_are_classified():
    """A rating of a question asked before the period is not a question in it."""
    rows = [row("feedback.verdict", q="old", verdict="up")] + answered("q1")
    assert set(classify(rows)) == {"q1"}


# --- Health ---------------------------------------------------------------------


def test_health_counts_questions_testers_and_endings_each_with_its_denominator():
    rows = (
        answered("q1", email="a@x.org", spend=(1000, 500))
        + answered("q2", email="b@x.org", spend=(2000,))
        + [
            row("question.asked", q="q3", email="a@x.org", question="?"),
            row("spend.increment", q="q3", email="a@x.org", increment=300),
            row("retrieval.bound_reached", q="q3", email="a@x.org"),
            row("question.asked", q="q4", question="?"),
        ]
    )
    h = health(rows)
    assert h.questions == 4
    assert h.testers == 2
    assert h.unattributed_questions == 1
    assert h.endings["answered"] == Share(2, 4)
    assert h.endings["retrieval_bound"] == Share(1, 4)
    assert h.endings[UNIDENTIFIED] == Share(1, 4)
    assert h.limit_endings == Share(1, 4)
    assert h.spend_micro == 3800
    assert h.spend_per_question_micro == 950
    assert not h.quiet


def test_spend_counts_every_model_call_not_only_answered_questions():
    """A question stopped at a limit still cost money; `question.answered` alone
    would under-count exactly the expensive ones."""
    rows = [
        row("question.asked", q="q1", question="?"),
        row("spend.increment", q="q1", increment=400),
        row("spend.increment", q="q1", increment=None),
        row("spend.limit_reached", q="q1", reason="spend_ceiling"),
    ]
    assert health(rows).spend_micro == 400


def test_a_quiet_period_says_so():
    h = health([row("signin.admitted"), row("tracing.failed")])
    assert h.quiet
    assert h.questions == 0
    assert h.spend_per_question_micro is None


def test_a_share_of_nothing_has_no_ratio():
    assert Share(0, 0).ratio is None
    assert Share(1, 4).ratio == 0.25


def test_limit_endings_are_the_limits_and_only_the_limits():
    assert LIMIT_ENDINGS == {
        "spend_ceiling",
        "run_budget",
        "retrieval_bound",
        "conversation_bound",
        "provider_limit",
    }


# --- Quality --------------------------------------------------------------------


def test_verdicts_are_grouped_by_run_label_each_with_its_count():
    rows = (
        answered("q1", label="run-a")
        + answered("q2", label="run-a")
        + answered("q3", label="run-b")
        + [
            row("feedback.verdict", q="q1", label="run-a", email="a@x.org", verdict="up"),
            row("feedback.verdict", q="q2", label="run-a", email="a@x.org", verdict="down"),
            row("feedback.verdict", q="q3", label="run-b", email="b@x.org", verdict="up"),
        ]
    )
    v = quality(rows).verdicts
    assert (v["run-a"].up, v["run-a"].down, v["run-a"].rated) == (1, 1, 2)
    assert (v["run-b"].up, v["run-b"].down, v["run-b"].rated) == (1, 0, 1)


def test_a_changed_verdict_counts_once_as_its_latest():
    rows = answered("q1") + [
        row("feedback.verdict", q="q1", email="a@x.org", verdict="up"),
        row("feedback.verdict", q="q1", email="a@x.org", verdict="down"),
    ]
    v = quality(rows).verdicts["run-a"]
    assert (v.up, v.down) == (0, 1)


def test_a_verdict_with_no_reader_is_counted_and_shown_as_unattributed():
    rows = answered("q1", email=None) + [row("feedback.verdict", q="q1", verdict="down")]
    q = quality(rows)
    assert q.unattributed_verdicts == 1
    assert q.verdicts["run-a"].down == 1


def test_comments_carry_the_question_and_answer_they_are_about():
    rows = answered("q1") + [row("feedback.comment", q="q1", email="a@x.org", comment="bad unit")]
    [c] = quality(rows).comments
    assert (c.question_id, c.comment) == ("q1", "bad unit")
    assert c.question == "what is q1?"
    assert c.answer == "q1 is 42"


def test_ungrounded_and_unsupported_are_shares_of_the_questions_given_an_answer():
    rows = (
        answered("q1")
        + answered("q2")
        + [
            row("answer.ungrounded", q="q1"),
            row("citations.unsupported", q="q2", unknown=["9"], unretrieved=[]),
            row("question.asked", q="q3", question="?"),
        ]
    )
    q = quality(rows)
    assert q.ungrounded == Share(1, 2)
    assert q.unsupported_citations == Share(1, 2)


def test_cited_is_a_share_of_retrieved():
    rows = answered("q1", cited=["1"], retrieved=["1", "2", "3"]) + answered(
        "q2", cited=["4", "5"], retrieved=["4", "5"]
    )
    assert quality(rows).cited == Share(3, 5)


# --- Recording health -----------------------------------------------------------


def test_recording_reports_the_last_row_and_tracer_trouble_by_name():
    rows = [
        row("question.asked", q="q1", question="?"),
        row("tracing.failed"),
        row("tracing.failed"),
        row("tracing.unavailable"),
        row("feedback.verdict", q="q1", verdict="up"),
    ]
    r = recording(rows)
    assert r.last_row_at == rows[-1].at
    assert r.tracer_trouble == {"tracing.failed": 2, "tracing.unavailable": 1}


def test_a_cold_write_is_timed_by_the_row_after_it():
    """`prev_write_ms` is the *previous* write's duration (ADR-0700). So the first
    write after a quiet gap is timed by the row that follows it."""
    rows = [
        row("question.asked", q="q1", at=T0, prev_ms=40, question="?"),
        row("question.asked", q="q2", at=T0 + timedelta(hours=3), prev_ms=35, question="?"),
        row("entry.retrieved", q="q2", at=T0 + timedelta(hours=3, seconds=4), prev_ms=4800),
        row("entry.retrieved", q="q2", at=T0 + timedelta(hours=3, seconds=5), prev_ms=30),
    ]
    [cold] = recording(rows).cold_writes
    assert cold.at == rows[1].at
    assert cold.gap == timedelta(hours=3)
    assert cold.write_ms == 4800


def test_a_cold_write_with_no_row_after_it_has_no_duration_yet():
    rows = [
        row("question.asked", q="q1", at=T0, question="?"),
        row("question.asked", q="q2", at=T0 + timedelta(hours=1), question="?"),
    ]
    [cold] = recording(rows).cold_writes
    assert cold.write_ms is None


def test_writes_close_together_are_not_cold():
    rows = [row("question.asked", q="q1", at=T0 + timedelta(minutes=m)) for m in range(0, 50, 9)]
    assert recording(rows).cold_writes == []


def test_recording_on_no_rows():
    r = recording([])
    assert r.last_row_at is None
    assert r.tracer_trouble == {}
    assert r.cold_writes == []


# --- The recent-questions table -------------------------------------------------


def test_questions_are_newest_first_with_ending_spend_and_latest_verdict():
    rows = (
        answered("q1", email="a@x.org", spend=(100, 200))
        + answered("q2", email="b@x.org", label="run-b", spend=(50,))
        + [
            row("feedback.verdict", q="q1", verdict="up"),
            row("feedback.verdict", q="q1", verdict="down"),
        ]
    )
    lines = questions(rows)
    assert [line.question_id for line in lines] == ["q2", "q1"]
    q1 = lines[1]
    assert q1.asker == "a@x.org"
    assert q1.question == "what is q1?"
    assert q1.ending.kind == "answered"
    assert q1.spend_micro == 300
    assert q1.verdict == "down"
    assert lines[0].verdict is None
    assert lines[0].run_label == "run-b"


def test_the_module_reads_no_database_and_draws_nothing():
    """Pure functions over rows: what makes the figures testable at all."""
    source = Path(figures.__file__).read_text()
    for name in ("streamlit", "sqlalchemy", "psycopg", "langfuse"):
        assert f"import {name}" not in source and f"from {name}" not in source
