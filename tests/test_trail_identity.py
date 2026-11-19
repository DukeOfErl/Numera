"""A record names its question and its session; an item names its question.

The question identifier locates one question. Without the session, a sequence of
questions asked by one person cannot be reassembled -- and one person asking ten
questions is indistinguishable from ten people asking one, which is the first
thing anyone will want to know from this data.

None of it can be retrofitted. A record already written carries what it carries,
so these have to be right before the records that matter exist rather than after.
"""

from __future__ import annotations

import io
import json

from conftest import agent_with

from agent_doubles import says, scripted
from numera_ask import trace, web
from numera_ask.events import (
    Answer,
    EndReason,
    QuestionEnded,
    QuestionStarted,
    Retrieval,
)


def _records(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


# --- the trail ------------------------------------------------------------


def test_two_questions_in_one_session_share_it_and_differ_by_question():
    stream = io.StringIO()
    trace.configure(stream)
    first = trace.start_question("dev", session_id="s-abc")
    second = trace.start_question("dev", session_id="s-abc")
    first.record("search", matched=3)
    second.record("search", matched=5)

    one, two = _records(stream)
    assert one["session_id"] == two["session_id"] == "s-abc"
    assert one["question_id"] != two["question_id"]


def test_two_sessions_are_not_confusable():
    """The point of carrying the session at all.

    Varies the session while holding everything else equal -- the dimension the
    data is read on. Two records that differ only by question identifier would
    satisfy a weaker test and tell nobody how many people there were.
    """
    stream = io.StringIO()
    trace.configure(stream)
    trace.start_question("dev", session_id="s-one").record("search")
    trace.start_question("dev", session_id="s-two").record("search")

    one, two = _records(stream)
    assert {one["session_id"], two["session_id"]} == {"s-one", "s-two"}


def test_the_order_questions_were_asked_is_recoverable_from_the_records():
    """Reassembling a session means ordering it, not just grouping it.

    Recoverable from the records alone -- no external clock, no knowledge of how
    the file was produced -- because that is the situation of whoever reads this
    weeks later.
    """
    stream = io.StringIO()
    trace.configure(stream)
    asked = [trace.start_question("dev", session_id="s1") for _ in range(3)]
    for position, question in enumerate(asked):
        question.record("search", position=position)

    records = [r for r in _records(stream) if r.get("session_id") == "s1"]
    seen = [r["question_id"] for r in records]
    assert seen == [q.question_id for q in asked]
    assert len(set(seen)) == 3


def test_a_question_without_a_session_records_no_session_at_all():
    """Absent, not empty. The terminal has a session it has no reason to name.

    An empty string would put a column on every line that is never populated, and
    an empty facet in a tracing tool is worse than a missing one.
    """
    stream = io.StringIO()
    trace.configure(stream)
    trace.start_question("dev").record("search")
    (record,) = _records(stream)
    assert "session_id" not in record


# --- what a framework call is tagged with ---------------------------------


def test_the_session_reaches_the_run_config_a_tracer_would_read():
    """One key in the dict `agent.py` already merges, so a tracer added later
    inherits it with no further change."""
    config = trace.start_question("dev", session_id="s-xyz").run_config("ask")
    assert config["metadata"]["session_id"] == "s-xyz"
    assert config["metadata"]["question_id"]


def test_no_session_means_no_key_rather_than_an_empty_one():
    config = trace.start_question("dev").run_config("ask")
    assert "session_id" not in config["metadata"]


# --- what the page draws --------------------------------------------------


def _ended(question_id: str) -> QuestionEnded:
    return QuestionEnded(
        question_id=question_id,
        reason=EndReason.ANSWERED,
        spend=1,
        run_spend=1,
        model="m",
        tool_calls=1,
    )


def test_every_drawn_item_names_the_question_that_produced_it():
    """Across kinds, not for one: an answer, a progress line and an ending.

    The stamping happens in one place so a branch cannot forget it; this asserts
    that it actually reaches every kind rather than trusting the arrangement.
    """
    events = [
        Retrieval(question_id="q1", tool="search", detail={}),
        Answer(question_id="q1", text="42"),
        _ended("q1"),
    ]
    items = list(web.items_for(events))
    assert items, "no items drawn"
    assert {item.question_id for item in items} == {"q1"}


def test_items_from_two_questions_are_told_apart():
    """A rating on the third answer must not land on the first.

    This is the property the whole change exists for, so it is asserted on the
    items a page would actually hold rather than on one item in isolation.
    """
    events = [
        Answer(question_id="q1", text="first"),
        _ended("q1"),
        Answer(question_id="q2", text="second"),
        _ended("q2"),
    ]
    items = list(web.items_for(events))
    answers = [i for i in items if i.text in {"first", "second"}]
    assert [a.question_id for a in answers] == ["q1", "q2"]


def test_a_started_question_draws_nothing_but_still_costs_no_identity():
    """`QuestionStarted` produces no item; that must stay true, not become an
    item with an empty identifier."""
    assert web.item_for(QuestionStarted(question_id="q1", session_id="s1", question="?")) is None


# --- the seam every test above would miss ---------------------------------


def test_a_real_agent_run_records_the_session_it_was_asked_in(repo, config, tmp_path):
    """Drives `AskAgent.ask`, because nothing above would notice it regressing.

    Every trail test in this file calls `start_question` directly, so if
    `agent.ask` stopped passing the session through, all of them would still pass
    and the deployed app would record no session at all. This is the one assertion
    that spans the two -- and it is the kind of gap that is invisible until
    someone asks which test covers the wiring rather than the parts.
    """
    stream = io.StringIO()
    trace.configure(stream)

    agent = agent_with(repo, config, tmp_path, scripted(says("The answer is 42.")))
    list(agent.ask("s-live", "how many?"))

    records = _records(stream)
    assert records, "the run recorded nothing at all"
    sessions = {r.get("session_id") for r in records}
    assert sessions == {"s-live"}, f"records carried {sessions}"


def test_two_sessions_through_the_agent_stay_apart(repo, config, tmp_path):
    stream = io.StringIO()
    trace.configure(stream)

    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")))
    list(agent.ask("s-one", "first?"))
    list(agent.ask("s-two", "second?"))

    by_session: dict[str, set[str]] = {}
    for record in _records(stream):
        by_session.setdefault(record["session_id"], set()).add(record["question_id"])
    assert set(by_session) == {"s-one", "s-two"}
    # No question identifier appears under two sessions.
    assert not by_session["s-one"] & by_session["s-two"]
