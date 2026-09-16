"""The trail records what was asked, what was answered, and what that rested on.

A rating collected before this change said "answer c23c83c16324 was wrong" and
there was no way to learn what it was answering. These tests pin the three records
that make a judgement readable.

**Every assertion here varies the thing it reads.** A test asserting "the record
carries the question" passes against a mutant recording any constant string, and
this project has been caught by exactly that shape three times. So the questions
differ from each other, the answers differ from each other, and the cited set
differs from the retrieved set -- a test where they are equal proves nothing about
whether the two are kept apart.
"""

from __future__ import annotations

import io
import json
import logging

import pytest
from conftest import agent_with

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import trace, trail_store
from scinumbers_ask.agent import AskAgent
from scinumbers_ask.corpus import load
from scinumbers_ask.events import Answer, EndReason
from scinumbers_ask.repository import CorpusRepository
from scinumbers_ask.trace import configure

ASKED = "question.asked"
ANSWER = "answer.given"
EVIDENCE = "answer.evidence"


@pytest.fixture
def trail() -> io.StringIO:
    """The trail as a file-shaped stream, read back a record at a time."""
    stream = io.StringIO()
    configure(stream)
    return stream


def records(stream: io.StringIO, event: str | None = None) -> list[dict]:
    rows = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    return [r for r in rows if event is None or r["event"] == event]


# -- the question ----------------------------------------------------------


def test_two_different_questions_record_what_each_actually_asked(repo, config, tmp_path, trail):
    """Varied deliberately: "the field is non-empty" passes against a constant."""
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")))
    list(agent.ask("s", "how wide is an E. coli cell?"))
    list(agent.ask("s", "and how long?"))

    asked = records(trail, ASKED)
    assert [r["question"] for r in asked] == ["how wide is an E. coli cell?", "and how long?"]
    assert len({r["question_id"] for r in asked}) == 2, "two questions, two identifiers"


def test_a_question_that_ends_without_an_answer_still_recorded_what_was_asked(
    repo, config, tmp_path, trail
):
    """The runs worth investigating are the ones that did not finish.

    Asserted through the trail rather than through the events: the events carry
    the question anyway (`QuestionStarted.question`), so reading them would pass
    whether or not anything was ever recorded.
    """
    from langchain_core.messages import AIMessage

    agent = agent_with(repo, config, tmp_path, scripted(AIMessage(content="")))
    events = list(agent.ask("s", "a question nothing will answer"))
    assert events[-1].reason is EndReason.NO_ANSWER

    (asked,) = records(trail, ASKED)
    assert asked["question"] == "a question nothing will answer"
    assert not records(trail, ANSWER), "there was no answer, so none should be recorded"


def test_the_question_is_recorded_before_the_work_that_might_fail(repo, config, tmp_path, trail):
    """Ordering, not merely presence.

    A record written at the end is lost to every crash, and a crash is the case
    this exists for. The search records sit between, so their position in the
    trail is what proves the question was written first.
    """
    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    events = [r["event"] for r in records(trail)]
    assert events[0] == ASKED, events
    assert "search" in events, "nothing ran between, so the ordering claim is vacuous"
    assert events.index(ASKED) < events.index("search")


# -- the answer ------------------------------------------------------------


def test_two_different_answers_are_recorded_under_the_questions_that_produced_them(
    repo, config, tmp_path, trail
):
    agent = agent_with(repo, config, tmp_path, scripted(says("about 1 μm"), says("about 2 μm")))
    first = list(agent.ask("s", "how wide?"))
    second = list(agent.ask("s", "how long?"))

    by_id = {r["question_id"]: r["answer"] for r in records(trail, ANSWER)}
    assert len(by_id) == 2
    assert by_id[first[0].question_id] == "about 1 μm"
    assert by_id[second[0].question_id] == "about 2 μm"


def test_the_answer_is_recorded_verbatim_rather_than_shortened(repo, config, tmp_path, trail):
    """A shortened answer cannot be compared against the rating it received."""
    long_answer = "The cell is about 1 μm across. " * 200
    list(agent_with(repo, config, tmp_path, scripted(says(long_answer))).ask("s", "q"))

    (recorded,) = records(trail, ANSWER)
    assert recorded["answer"] == long_answer
    assert len(recorded["answer"]) > 5000, "the fixture is too short to catch a truncation"


def test_every_ending_that_gives_an_answer_records_it(repo, config, tmp_path, monkeypatch):
    """The branch-complete property, not a sample of branches.

    `ask` can yield an `Answer` from eight places, seven of them endings -- a
    spend limit, a length bound, a missing key -- and an ending is exactly the
    answer a reader rates down. Enumerated per-case tests keep missing the branch
    nobody thought of, so this drives every ending the agent can produce and
    asserts the invariant: wherever an `Answer` reached the driver, the same text
    is in the trail under the same identifier.

    Three of the eleven endings produce no `Answer` at all -- `NO_ANSWER`,
    `PROVIDER_FAILURE` and `INTERNAL_ERROR` have no `yield Answer` on their path
    -- so for those the core assertion reduces to `[] == []`. That is correct and
    is not proof of anything, which is why the set of answerless builds is pinned
    below: a build that silently stopped yielding an `Answer` would otherwise slip
    from "checked" into "vacuous" without failing.

    "Every ending" is checked against `EndReason` itself rather than counted. The
    first version of this test said `== 8`, which was true and hid the gap it was
    written to prevent: the `PROVIDER_LIMIT` site -- the partial answer kept when
    a key runs out of credit, the ending most likely to be rated down -- was
    reached by no build. A verifier found it by measuring coverage of `agent.py`
    rather than by reading this docstring, which is the lesson.
    """
    from agent_endings import ending_builds

    # No `trail` fixture: this configures its own stream per build, and asking for
    # one that is then discarded reads as though it were what is asserted on.
    seen_endings = set()
    answerless: set[str] = set()
    for build in ending_builds(repo, config, tmp_path, monkeypatch):
        # Built before the stream is attached: two of the builds ask a question
        # of their own to reach the state they are named for, and those records
        # would otherwise be read as this question's.
        agent, session = build()
        stream = io.StringIO()
        configure(stream)
        events = list(agent.ask(session, "How wide is an E. coli cell?"))
        seen_endings.add(events[-1].reason)

        answers = [e.text for e in events if isinstance(e, Answer)]
        if not answers:
            answerless.add(build.__name__)
        recorded = [r["answer"] for r in records(stream, ANSWER)]
        assert recorded == answers, (
            f"{build.__name__}: driver saw {len(answers)} answer(s), trail has {len(recorded)}"
        )
        # The text, not merely a row. `assert records(...)` here survived a mutant
        # recording a constant question for all eleven builds; it was killed only
        # by the two-question test above, which is a different property.
        assert [r["question"] for r in records(stream, ASKED)] == [
            "How wide is an E. coli cell?"
        ], f"{build.__name__}: the question itself went unrecorded, or recorded wrong"

    from agent_endings import COVERED

    assert seen_endings == COVERED, sorted(r.value for r in COVERED - seen_endings)
    # Exactly these produce no answer. Pinned so a build whose `Answer` quietly
    # disappeared turns this test vacuous loudly rather than silently.
    assert answerless == {"blank", "provider_dead", "internal_error"}, sorted(answerless)


def test_a_crash_mid_answer_still_leaves_the_question_recorded(
    repo, config, tmp_path, trail, monkeypatch
):
    """`ask` names three failures it survives; this is the third.

    A spend ceiling and a missing key are endings the agent produces and shapes.
    A defect of ours is not: it escapes as an exception, taking the generator
    with it. That run is the one most worth reading afterwards, and until this
    test existed the comment claiming it was covered had nothing behind it.
    """

    def explode(_message):
        raise TypeError("a bug in this file, not the provider")

    monkeypatch.setattr("scinumbers_ask.agent._text_of", explode)
    agent = agent_with(repo, config, tmp_path, scripted(says("x")))
    with pytest.raises(TypeError, match="a bug in this file"):
        list(agent.ask("s", "a question whose run crashed"))

    (asked,) = records(trail, ASKED)
    assert asked["question"] == "a question whose run crashed"
    assert not records(trail, ANSWER), "the crash came before any answer"


# -- the evidence ----------------------------------------------------------


def test_the_cited_set_and_the_retrieved_set_stay_apart_in_the_record(
    repo, config, tmp_path, trail
):
    """Equal sets would prove nothing: they differ here, and by more than order."""
    model = scripted(
        tool_call("search_entries", property="Cell"),
        says("about 1 micrometre [[100002]]"),
    )
    list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    (evidence,) = records(trail, EVIDENCE)
    assert evidence["cited"] == [100002]
    assert 100002 in evidence["retrieved"]
    assert set(evidence["retrieved"]) - set(evidence["cited"]), (
        "the search returned only what was cited, so nothing here is distinguishable"
    )


def _wide_corpus(tmp_path) -> CorpusRepository:
    """A synthetic corpus large enough that one search exceeds the driver's cap.

    Identifiers in the `9xxxxx` range and invented content, per ADR-0200: no
    BioNumbers data enters this repository.
    """
    path = tmp_path / "wide.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for n in range(20):
            handle.write(
                json.dumps(
                    {
                        "entry_id": 900_100 + n,
                        "property": "Widget span",
                        "organism": "Synthetica ficta",
                        "units": "μm",
                        "value": 1.0 + n,
                        "range_low": None,
                        "range_high": None,
                        "reference": f"Invented A. J Nowhere. 20{n:02d} p.1",
                        "reference_pubmed_id": None,
                        "measurement_method": "invented",
                        "comments": "",
                        "keywords": ["widget"],
                    }
                )
                + "\n"
            )
    return CorpusRepository(load(str(path)))


def test_the_whole_retrieved_set_is_recorded_not_the_head_the_driver_shows(config, tmp_path, trail):
    """The record is the agent's evidence, not the table a reader was shown.

    `web.CITED_ROWS` is a presentation limit. Driven with a retrieval larger than
    it, so a day when that cap leaks into the record fails here rather than
    quietly halving every evidence row.
    """
    from scinumbers_ask import web

    model = scripted(
        tool_call("search_entries", property="Widget"),
        says("about 1 μm [[900100]]"),
    )
    agent = AskAgent(_wide_corpus(tmp_path), config, str(tmp_path / "w.sqlite"), model=model)
    list(agent.ask("s", "how wide is a widget?"))

    (evidence,) = records(trail, EVIDENCE)
    # The identities, not merely the count: a record holding twenty *wrong* ids
    # would satisfy a length assertion, and a presentation cap leaking in is only
    # one of the ways this can go wrong.
    assert sorted(evidence["retrieved"]) == list(range(900_100, 900_120))
    assert len(evidence["retrieved"]) > web.CITED_ROWS + web.UNCITED_ROWS


def test_a_question_that_retrieved_nothing_records_no_evidence_row(repo, config, tmp_path, trail):
    """No row rather than an empty one.

    The agent emits no `AnswerEntries` when nothing was searched, retrieved or
    cited -- there is no evidence to describe, and a row of empty lists would read
    as "the answer rested on nothing we could find" when what happened is that it
    never looked. `answer.ungrounded` is the record that says so, and it already
    exists.
    """
    list(agent_with(repo, config, tmp_path, scripted(says("about 1 μm"))).ask("s", "q"))

    assert not records(trail, EVIDENCE)
    assert records(trail, "answer.ungrounded"), "the ungrounded record is what stands in its place"


# -- the obligations ------------------------------------------------------


def test_nothing_recorded_here_reaches_the_model(repo, config, tmp_path, trail):
    """These are records of a question already answered, not context for the next.

    Asserted over what the model was shown. The positive control comes first:
    every assertion below is a `not in`, which an empty haystack satisfies.
    """
    model = scripted(says("the first answer, about 1 μm"), says("the second answer"))
    agent = agent_with(repo, config, tmp_path, model)
    list(agent.ask("s1", "how many ribosomes?"))
    list(agent.ask("s1", "and in yeast?"))

    shown = "\n".join(str(getattr(m, "content", m)) for m in model.seen)

    assert model.seen, "the model was never called; the assertions below are vacuous"
    assert "and in yeast?" in shown, "the second question did not reach the model"
    assert records(trail, ANSWER), "nothing was recorded; the assertions below are vacuous"

    assert ASKED not in shown
    assert ANSWER not in shown
    assert EVIDENCE not in shown
    assert "question.answered" not in shown


class _RefusingEngine:
    """An engine whose every transaction fails, counting the attempts.

    `test_feedback._Engine(fail_on_begin=...)` raises from `begin()` and records
    nothing, so a test using it cannot tell a record that was attempted and
    swallowed from one that was never attempted at all. That distinction is the
    whole of what the two tests below are about.
    """

    def __init__(self) -> None:
        self.attempts = 0

    def begin(self):
        self.attempts += 1
        raise OSError("the destination is gone")


def _drive_with_a_dead_destination(repo, config, tmp_path, store) -> tuple[list, io.StringIO]:
    """One retrieving question, with `store` attached beside a file-shaped sink.

    The stream shows what reached the *logger*; the store's own counters show
    what reached the destination. The two diverge, which is the point.
    """
    stream = io.StringIO()
    configure(stream)
    logger = logging.getLogger(trace.LOGGER_NAME)
    logger.addHandler(trail_store.TrailHandler(store))
    try:
        model = scripted(tool_call("search_entries", property="Cell"), says("1 μm [[100002]]"))
        return list(agent_with(repo, config, tmp_path, model).ask("s", "how wide?")), stream
    finally:
        logger.handlers.clear()


def test_a_destination_that_cannot_be_written_does_not_fail_a_question(
    repo, config, tmp_path, monkeypatch
):
    """Fail-open (ADR-0710), exercised on the records this change adds.

    The real sink, not a hand-rolled one: `TrailHandler.emit` is what swallows,
    and the guarantee is a property of that handler rather than of `logging`,
    which does not wrap `emit` at all.

    **`FAILURES_BEFORE_GIVING_UP` is raised for this test, and that is not a
    convenience.** At its real value of 3 the budget is consumed by
    `question.asked`, a `spend.increment` and `search` — all records that predate
    this change — after which the store pauses and `answer.given` and
    `answer.evidence` are never attempted at all. A test at the real threshold
    therefore exercises the swallow on none of the two new records while looking
    exactly as though it does. The other regime is pinned by the test below.
    """
    monkeypatch.setattr(trail_store, "FAILURES_BEFORE_GIVING_UP", 99)
    engine = _RefusingEngine()
    store = trail_store.TrailStore(engine=engine)
    store.ready = True

    events, stream = _drive_with_a_dead_destination(repo, config, tmp_path, store)

    assert events[-1].reason is EndReason.ANSWERED
    assert any(isinstance(e, Answer) for e in events)

    # Every record the logger saw was attempted against the dead destination and
    # swallowed -- the two counts being equal is what rules out "skipped".
    emitted = records(stream)
    assert engine.attempts == len(emitted) == store.failures
    assert {ASKED, ANSWER, EVIDENCE} <= {r["event"] for r in emitted}
    assert store.ready is True, "nothing should have given up at this threshold"


def test_a_dead_destination_stops_trying_before_the_answer_is_reached(repo, config, tmp_path):
    """The regime that actually holds in production, written down because it is
    surprising.

    Three consecutive failures and the store pauses for `SCHEMA_RETRY_AFTER_S`.
    Those three are spent on `question.asked` and the retrieval records that
    follow it, so the answer and its evidence are *skipped upstream of the write*
    rather than swallowed by it. The reader is unaffected either way — which is
    the guarantee — but an operator reading a half-written question's rows should
    know the tail is missing by design and not because the two records are
    broken.
    """
    engine = _RefusingEngine()
    store = trail_store.TrailStore(engine=engine)
    store.ready = True

    events, stream = _drive_with_a_dead_destination(repo, config, tmp_path, store)

    assert events[-1].reason is EndReason.ANSWERED, "the reader is unaffected"
    assert store.failures == trail_store.FAILURES_BEFORE_GIVING_UP
    assert store.ready is False, "the store should have paused rather than gone on trying"
    # Which records were never attempted, without pinning which three consumed the
    # budget: attempts happen in emission order, so everything from index
    # `attempts` onward never reached the engine. Naming the three would break the
    # day somebody adds a `trace.record` earlier in `_ask`, and would read as a
    # bug in the give-up regime rather than as a moved record.
    emitted = [r["event"] for r in records(stream)]
    never_attempted = emitted[engine.attempts :]
    assert ANSWER in never_attempted
    assert EVIDENCE in never_attempted
    assert ASKED in emitted[: engine.attempts], "the question itself was attempted"


def test_the_records_reach_the_durable_store_under_the_question_s_own_identifier(
    repo, config, tmp_path
):
    """The join the whole change exists for, read back off the store.

    Every test above asserts the file-shaped record, which `trace.configure`
    leaves as the only handler. Nothing there establishes that these rows reach
    `TrailStore` at all, or that they carry the identifier a feedback row joins to.
    """
    from test_feedback import _Engine

    engine = _Engine()
    store = trail_store.install(engine, logger_name=trace.LOGGER_NAME)
    assert store is not None and store.ready
    try:
        model = scripted(tool_call("search_entries", property="Cell"), says("1 μm [[100002]]"))
        events = list(agent_with(repo, config, tmp_path, model).ask("s7", "how wide?"))
    finally:
        logging.getLogger(trace.LOGGER_NAME).handlers.clear()

    question_id = events[0].question_id
    rows = {r["event"]: r for r in engine.written}
    assert {ASKED, ANSWER, EVIDENCE} <= set(rows)
    for event in (ASKED, ANSWER, EVIDENCE):
        assert rows[event]["question_id"] == question_id
        assert rows[event]["session_id"] == "s7"
    assert json.loads(rows[ASKED]["detail"])["question"] == "how wide?"
    assert json.loads(rows[ANSWER]["detail"])["answer"] == "1 μm [[100002]]"
    assert json.loads(rows[EVIDENCE]["detail"])["cited"] == [100002]


def test_no_driver_records_the_question_as_well(repo, config, tmp_path, trail):
    """Two records of one question under one identifier double-count a query.

    The agent-side record is the one the spec requires, because a record written
    by a driver exists only for that driver -- the evaluation harness is the third
    adapter and would be missing from the data.
    """
    from scinumbers_ask import web

    model = scripted(tool_call("search_entries", property="Cell"), says("1 μm [[100002]]"))
    list(web.items_for(agent_with(repo, config, tmp_path, model).ask("s", "how wide?"), repo))

    assert len(records(trail, ASKED)) == 1
    assert len(records(trail, ANSWER)) == 1
    assert len(records(trail, EVIDENCE)) == 1


def test_the_answer_is_recorded_even_when_the_driver_abandons_the_generator(
    repo, config, tmp_path, trail
):
    """Streamlit abandons a generator mid-iteration on every rerun.

    Code after a `yield` runs only if somebody asks for the next item, so a
    record written after the `Answer` is handed on is lost exactly when a reader
    clicked something -- which is the moment a rating is about to arrive.
    """
    events = agent_with(repo, config, tmp_path, scripted(says("about 1 μm"))).ask("s", "q")
    for event in events:
        if isinstance(event, Answer):
            break
    events.close()

    assert [r["answer"] for r in records(trail, ANSWER)] == ["about 1 μm"]


# -- the reader is told ----------------------------------------------------


def test_the_page_says_that_questions_and_answers_are_kept(monkeypatch, repo, config, tmp_path):
    """An obligation the requirement states, not a nicety.

    The system stores words somebody typed, and a person who can only discover
    that by reading the database afterwards has not been told.
    """
    from test_web_driver import app

    from scinumbers_ask import web

    # Literal fragments as well as the constant: `RECORDS_NOTE` is re-exported,
    # so an empty one would satisfy `in` everywhere and this would pass having
    # checked that the page contains the empty string.
    assert "are kept" in web.RECORDS_NOTE and "goes wrong" in web.RECORDS_NOTE

    at = app(monkeypatch, repo, agent_with(repo, config, tmp_path, scripted(says("a")))).run()
    panel = " ".join(c.value for c in at.sidebar.caption)
    assert web.RECORDS_NOTE in panel
    assert "kept" in panel and "goes wrong" in panel


def test_the_terminal_says_it_too_including_for_a_single_question(
    repo, config, tmp_path, monkeypatch, capsys
):
    """`--ask` records exactly as a session does, so it must say so exactly as well.

    The note goes to stderr: a pipeline reading the answer off stdout must not
    find this in it.
    """
    from scinumbers_ask import messages
    from scinumbers_ask.cli import main

    monkeypatch.setattr("scinumbers_ask.cli.AskAgent", lambda *a, **k: _NoModel())
    monkeypatch.setenv("SCINUMBERS_CORPUS", str(_corpus_path()))
    with pytest.raises(SystemExit):
        main(["--ask", "q", "--checkpoints", str(tmp_path / "c.sqlite")])

    captured = capsys.readouterr()
    assert messages.RECORDS_NOTE in captured.err
    assert "kept" in captured.err and "goes wrong" in captured.err
    assert "kept" not in captured.out, "stdout carries the answer, not this"


class _NoModel:
    """An agent that ends at once: this test is about the notice, not an answer."""

    def ask(self, session_id, question):
        from scinumbers_ask.events import QuestionEnded, QuestionStarted

        yield QuestionStarted(question_id="q", session_id=session_id, question=question)
        yield QuestionEnded(
            question_id="q",
            reason=EndReason.NO_ANSWER,
            spend=0,
            run_spend=0,
            model="m",
            tool_calls=0,
        )


def _corpus_path() -> str:
    from conftest import FIXTURE

    return FIXTURE


def test_the_terminal_does_not_claim_to_keep_what_it_discards(
    repo, config, tmp_path, monkeypatch, capsys
):
    """`--trace ""` discards the trail, and this driver installs no durable store.

    The notice is a claim about what is kept, so on a run that keeps nothing it
    must not be made. Found by the code review, not by the tests: the first
    version printed it unconditionally.
    """
    from scinumbers_ask import messages
    from scinumbers_ask.cli import main

    monkeypatch.setattr("scinumbers_ask.cli.AskAgent", lambda *a, **k: _NoModel())
    monkeypatch.setenv("SCINUMBERS_CORPUS", str(_corpus_path()))
    with pytest.raises(SystemExit):
        main(["--ask", "q", "--trace", "", "--checkpoints", str(tmp_path / "c.sqlite")])

    captured = capsys.readouterr()
    assert messages.RECORDS_NOTE not in captured.err
    assert "kept" not in captured.err
    # Positive control: the run itself happened and said so.
    assert "no_answer" in captured.out
