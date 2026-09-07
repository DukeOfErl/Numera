"""The evaluation driver: what it asks, what it records, and what it resumes.

Every assertion here is about the *record*, because the record is the only thing
that survives a run. A driver that asked correctly and wrote the wrong thing down
would be indistinguishable, from the report, from a system that answered wrongly.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import agent_with, write_all_shapes_corpus

from agent_doubles import costing, says, scripted, tool_call
from scinumbers_ask.config import Config, usd
from scinumbers_ask.corpus import load
from scinumbers_ask.evaluation import (
    Provenance,
    Result,
    ResultsFileError,
    ResultsWouldBeCommitted,
    append_result,
    code_version,
    in_order,
    outstanding,
    provenance_for,
    read_results,
    run_evaluation,
    session_for,
)
from scinumbers_ask.question_set import Question

PROVENANCE = Provenance(
    recorded_at="2026-09-04T12:00:00+00:00",
    model="fake/model",
    question_ceiling=usd("0.60"),
    run_budget=usd("1.20"),
    run_label="test",
    prompt_digest="0123456789abcdef",
    corpus_digest="fedcba9876543210",
    corpus_entries=6,
    code_version="git abc1234",
)


def a_question(identifier: str, **kwargs) -> Question:
    base = dict(
        question_id=identifier,
        question=f"question {identifier}?",
        asked_properties=("Cell diameter",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=(100002,),
    )
    base.update(kwargs)
    return Question(**base)


def a_result(identifier: str) -> Result:
    """A recorded result, for the resumption and file-reading tests."""
    return Result(
        question_id=identifier,
        repeat=1,
        question="q?",
        answer="an answer",
        end_reason="answered",
        provenance=PROVENANCE,
    )


def results_of(path) -> list:
    return list(read_results(path))


# -- 3.2 and 3.3: driving, and the record ---------------------------------------


def test_a_question_is_asked_and_everything_it_emitted_is_recorded(repo, config, tmp_path):
    model = scripted(tool_call("search_entries", property="Cell diameter"), says("1.0 [[100002]]"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    outcome = run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    assert (outcome.attempted, outcome.recorded, outcome.failed) == (1, 1, 0)
    (result,) = results_of(path)
    assert result.question_id == "q1"
    assert result.repeat == 1
    assert result.answer == "1.0 [[100002]]"
    assert result.cited == (100002,)
    assert 100002 in result.retrieved
    assert result.expected_entries == (100002,)
    assert result.end_reason == "answered"
    assert result.model_calls >= 1
    assert result.tool_calls >= 1
    assert result.run_budget == config.run_budget
    assert result.failure == ""


def test_the_context_recorded_is_what_the_agent_was_shown(repo, config, tmp_path):
    """Read from the session's transcript after the question, not rebuilt from the
    identifiers in the events -- the spec requires the context shown, and only the
    transcript is that by construction."""
    model = scripted(tool_call("search_entries", property="Cell diameter"), says("done"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    (result,) = results_of(path)
    assert len(result.context) == 1
    assert "100002" in result.context[0]


def test_a_question_that_retrieved_nothing_records_an_empty_context(repo, config, tmp_path):
    """Empty and unrecorded are different statements, and the spec requires them to
    be told apart. An empty context is the normal shape of a correct refusal; a
    context that could not be read is a fault in the harness. Collapsed into one
    value, an unrecorded context would read as proof the agent searched for
    nothing.
    """
    agent = agent_with(repo, config, tmp_path, scripted(says("not in the corpus")))
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    (result,) = results_of(path)
    assert result.context == ()
    assert result.context is not None


def test_a_context_that_could_not_be_read_is_not_recorded_as_empty(
    repo, config, tmp_path, monkeypatch
):
    agent = agent_with(repo, config, tmp_path, scripted(says("an answer")))
    monkeypatch.setattr(
        agent, "tool_results", lambda session: (_ for _ in ()).throw(OSError("no checkpoint"))
    )
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    (result,) = results_of(path)
    assert result.context is None
    assert "context unread" in result.failure


def test_a_record_is_readable_without_this_projects_reader(repo, config, tmp_path):
    """The requirement is that another tool can read a record *without
    transformation*, so this reads the line with the standard library alone and
    asks for the fields the requirement names."""
    model = scripted(tool_call("search_entries", property="Cell diameter"), says("1.0 [[100002]]"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    raw = json.loads(path.read_text().splitlines()[0])
    assert raw["question"] == "question q1?"
    assert raw["answer"] == "1.0 [[100002]]"
    assert raw["cited"] == [100002]
    assert 100002 in raw["retrieved"]
    assert raw["expected_entries"] == [100002]
    assert "100002" in raw["context"][0]
    assert raw["provenance"]["model"] == "fake/model"


def test_every_retrieval_is_recorded_with_the_arguments_it_was_made_with(repo, config, tmp_path):
    """Scoring whether the agent searched for the asked organism reads exactly
    these, so a record without them would mean re-asking the set to score it."""
    model = scripted(
        tool_call("search_entries", property="Cell diameter", organism="coli"),
        says("done"),
    )
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    (result,) = results_of(path)
    (retrieval,) = result.retrievals
    assert retrieval["tool"] == "search_entries"
    assert retrieval["property"] == "Cell diameter"
    assert retrieval["organism"] == "coli"


def test_a_follow_up_is_asked_in_its_parents_session(repo, config, tmp_path):
    """Otherwise "does a follow-up cite in full rather than referring back" is not
    a measurable question: there would be nothing for it to refer back to."""
    model = scripted(says("first"), says("second"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"), a_question("q1b", follows="q1")), path, PROVENANCE)

    parent, child = results_of(path)
    assert parent.session_id == child.session_id == session_for("q1", 1)


def test_questions_that_are_not_follow_ups_get_a_session_each(repo, config, tmp_path):
    """A question's recorded context has to be the context that question produced."""
    model = scripted(says("first"), says("second"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"), a_question("q2")), path, PROVENANCE)

    first, second = results_of(path)
    assert first.session_id != second.session_id


def test_the_agents_own_grounding_warnings_are_recorded(repo, config, tmp_path):
    """An answer with no retrieval behind it. The harness counts what the agent
    established about itself rather than judging the answer."""
    model = scripted(says("about 1 micron, based on my searches"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    (result,) = results_of(path)
    assert result.ungrounded_refusal is True
    assert result.claimed_searching is True


def test_a_citation_the_corpus_does_not_hold_is_recorded_as_such(repo, config, tmp_path):
    model = scripted(says("about 1 micron [[999999]]"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"),), path, PROVENANCE)

    (result,) = results_of(path)
    assert result.unknown_citations == (999999,)


def test_a_question_that_raises_is_recorded_as_a_failure_and_the_run_goes_on(
    repo, config, tmp_path, monkeypatch
):
    """An evaluation exists to measure a system that sometimes breaks. A run that
    died on the first exception would measure nothing, and a failure that vanished
    from the record would look exactly like a question never asked.
    """
    agent = agent_with(repo, config, tmp_path, scripted(says("second")))
    real_ask = agent.ask
    calls = {"n": 0}

    def ask(session_id, question):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the provider fell over")
        return real_ask(session_id, question)

    monkeypatch.setattr(agent, "ask", ask)
    path = tmp_path / "results.jsonl"

    outcome = run_evaluation(agent, (a_question("q1"), a_question("q2")), path, PROVENANCE)

    assert (outcome.attempted, outcome.recorded, outcome.failed) == (2, 2, 1)
    first, second = results_of(path)
    assert "RuntimeError: the provider fell over" in first.failure
    assert second.failure == ""
    assert second.answer == "second"


def test_the_run_stops_when_a_question_ends_on_the_run_budget(repo, tmp_path):
    """The budget bounds the run, not the question, so every question after it
    would end the same way and cost a model call each to say so."""
    budgeted = Config(model="fake/model", question_ceiling=usd("0.60"), run_budget=usd("0.000050"))
    model = scripted(costing(says("an answer"), 0.000_110))
    agent = agent_with(repo, budgeted, tmp_path, model)
    path = tmp_path / "results.jsonl"

    outcome = run_evaluation(
        agent, (a_question("q1"), a_question("q2"), a_question("q3")), path, PROVENANCE
    )

    assert outcome.stopped_on_run_budget is True
    # The second is refused by the agent before dispatch and recorded as such; the
    # third is never asked, and only the driver can be responsible for that.
    assert model.attempts == 1
    assert outcome.attempted == 2
    assert outcome.questions_skipped == 1
    assert outcome.skipped == ("q3",)
    first, second = results_of(path)
    assert first.end_reason == "answered"
    assert second.end_reason == "run_budget"


def test_each_result_is_on_disk_before_the_next_question_is_asked(repo, config, tmp_path):
    """A run costs money and can be interrupted; a file written at the end would
    lose everything up to the interruption."""
    model = scripted(says("first"), says("second"), says("third"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"
    seen = []

    run_evaluation(
        agent,
        (a_question("q1"), a_question("q2"), a_question("q3")),
        path,
        PROVENANCE,
        announce=lambda text: seen.append(len(results_of(path))),
    )

    # Announced before each question, so the counts read 0, 1, 2.
    assert seen == [0, 1, 2]


# -- 3.4: provenance -------------------------------------------------------------


def test_every_result_carries_the_provenance_of_the_run(repo, config, tmp_path):
    model = scripted(says("first"), says("second"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"), a_question("q2")), path, PROVENANCE)

    for result in results_of(path):
        assert result.provenance == PROVENANCE


def test_provenance_records_the_three_things_that_move_the_figures(tmp_path):
    """A date is a proxy for the corpus, the prompt and the code, so all three are
    recorded beside it rather than left to be inferred from when a run happened."""
    corpus = write_all_shapes_corpus(tmp_path)
    config = Config(
        model="a/model", question_ceiling=usd("0.60"), run_budget=usd("1.20"), run_label="eval"
    )
    recorded = provenance_for(config, corpus, len(load(corpus)))

    assert recorded.model == "a/model"
    assert recorded.run_label == "eval"
    assert recorded.corpus_entries == 6
    assert len(recorded.corpus_digest) == 16
    assert len(recorded.prompt_digest) == 16
    assert recorded.recorded_at.endswith("+00:00")
    assert recorded.code_version.split()[0] in {"git", "package", "unknown"}


def test_a_different_corpus_gets_a_different_digest(tmp_path):
    """What the report refuses to combine across. Two corpora that hashed alike
    would be averaged together and nothing would say so."""
    config = Config(model="m", question_ceiling=1, run_budget=1)
    one = write_all_shapes_corpus(tmp_path)
    grown = tmp_path / "grown.jsonl"
    grown.write_text(Path(one).read_text() + json.dumps({"entry_id": 7, "property": "p"}) + "\n")

    first = provenance_for(config, one, 6)
    second = provenance_for(config, grown, 7)
    assert first.corpus_digest != second.corpus_digest
    # The prompt has not changed, so that digest must not move with the corpus.
    assert first.prompt_digest == second.prompt_digest


def test_the_code_version_says_which_kind_of_answer_it_is():
    """ "git 4ccd5b2" and "package 0.1.0" are different claims, and a reader
    comparing two runs needs to know which of the two they are holding."""
    reported = code_version()
    assert reported.split()[0] in {"git", "package", "unknown"}
    if reported.startswith("git "):
        # A commit alone would claim provenance a modified tree does not have.
        assert reported.split()[1]


# -- 3.5: resumption -------------------------------------------------------------


def test_only_the_questions_with_no_result_are_asked_again(repo, config, tmp_path):
    model = scripted(says("first"), says("second"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"
    questions = (a_question("q1"), a_question("q2"))

    run_evaluation(agent, questions[:1], path, PROVENANCE)
    second = run_evaluation(agent, questions, path, PROVENANCE)

    assert second.attempted == 1
    assert [result.question_id for result in results_of(path)] == ["q1", "q2"]


def test_resumption_counts_a_repeat_as_its_own_attempt(repo, config, tmp_path):
    """The gap fault seeding found: a `done` set keyed on the question alone.

    Both questions have a result for repeat 1. Resuming with two repeats must ask
    repeat 2 and nothing else. Keyed on the question id alone, every question reads
    as done, the run records nothing, and the report shows one repeat where three
    were asked for -- against the requirement that run-to-run variation is measured
    rather than averaged away. Every other resumption test here runs at the default
    of one repeat, where the mistake cannot show.
    """
    path = tmp_path / "results.jsonl"
    for identifier in ("q1", "q2"):
        append_result(path, a_result(identifier))
    questions = (a_question("q1"), a_question("q2"))

    todo = outstanding(questions, read_results(path), repeats=2)

    assert [(question.question_id, repeat) for question, repeat in todo] == [
        ("q1", 2),
        ("q2", 2),
    ]


def test_a_follow_up_whose_parent_is_missing_is_asked_again(repo, config, tmp_path):
    """Its own result is present, and it is still missing: the parent will be asked
    in a new session, so the recorded answer belongs to a session that no longer
    exists and would be scored against context it never had.
    """
    questions = (a_question("q1"), a_question("q1b", follows="q1"))
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1b"))

    todo = outstanding(questions, read_results(path), repeats=1)

    assert [question.question_id for question, _ in todo] == ["q1", "q1b"]


def test_a_partial_last_line_is_an_interruption_and_is_tolerated(tmp_path):
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"question_id": "q2", "repe')

    (result,) = read_results(path)
    assert result.question_id == "q1"


def test_a_broken_line_that_is_not_the_last_is_refused(tmp_path):
    """Reading on would drop results the report would then simply be missing."""
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    append_result(path, a_result("q3"))

    with pytest.raises(ResultsFileError, match="is not valid JSON"):
        read_results(path)


def test_a_results_file_from_another_version_is_refused(tmp_path):
    """A field this reader does not know means the file was written by a different
    version, and reading it as if the fields matched is how a report comes to
    describe figures it has misread."""
    path = tmp_path / "results.jsonl"
    path.write_text(json.dumps({"question_id": "q1", "repeat": 1, "verdict": "good"}) + "\n")
    with pytest.raises(ResultsFileError, match="carries \\['verdict'\\]"):
        read_results(path)


def test_a_missing_results_file_is_an_empty_run_not_an_error(tmp_path):
    assert read_results(tmp_path / "never-written.jsonl") == ()


# -- 3.6: repeats ----------------------------------------------------------------


def test_each_question_is_asked_once_per_repeat_in_its_own_session(repo, config, tmp_path):
    """The agent is not deterministic, so one run measures a trajectory rather than
    the system. Repeats in one session would let the second answer read the first."""
    model = scripted(says("a"), says("b"), says("c"), says("d"))
    agent = agent_with(repo, config, tmp_path, model)
    path = tmp_path / "results.jsonl"

    run_evaluation(agent, (a_question("q1"), a_question("q2")), path, PROVENANCE, repeats=2)

    recorded = results_of(path)
    assert [(r.question_id, r.repeat) for r in recorded] == [
        ("q1", 1),
        ("q2", 1),
        ("q1", 2),
        ("q2", 2),
    ]
    assert len({r.session_id for r in recorded}) == 4


def test_a_run_of_no_repeats_is_refused_rather_than_recording_nothing(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, scripted(says("a")))
    with pytest.raises(ValueError, match="at least one repeat"):
        run_evaluation(agent, (a_question("q1"),), tmp_path / "r.jsonl", PROVENANCE, repeats=0)


# -- ordering --------------------------------------------------------------------


def test_a_parent_is_asked_before_its_child_whatever_order_the_file_used(repo):
    """The format permits any order, so a driver that trusted it would ask a
    follow-up against a session that did not exist yet."""
    child = a_question("q1b", follows="q1")
    parent = a_question("q1")
    assert [q.question_id for q in in_order((child, parent))] == ["q1", "q1b"]


def test_a_chain_is_ordered_from_its_root():
    third = a_question("q3", follows="q2")
    second = a_question("q2", follows="q1")
    first = a_question("q1")
    ordered = in_order((third, second, first))
    assert [q.question_id for q in ordered] == ["q1", "q2", "q3"]


# -- What the branch review of group 3 found -------------------------------------


def test_appending_after_a_torn_line_does_not_lose_the_new_result(tmp_path):
    """The failure the append-per-result shape was supposed to survive.

    A run killed mid-write leaves a partial record with no trailing newline.
    Appending onto it fused the two into one invalid line -- still the *last*
    line, so the newly paid-for result was silently dropped on the next read; one
    more append pushed it into the middle and every read from then on refused the
    whole file, blaming damage after the fact.
    """
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"question_id": "q2", "repe')

    append_result(path, a_result("q3"))
    append_result(path, a_result("q4"))

    assert [result.question_id for result in read_results(path)] == ["q1", "q3", "q4"]


def test_a_torn_line_is_the_only_thing_a_repair_removes(tmp_path):
    """A complete file must be appended to untouched: the repair reads the last
    byte, and a rule that trimmed a whole line regardless would eat a good one."""
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    append_result(path, a_result("q2"))
    assert [result.question_id for result in read_results(path)] == ["q1", "q2"]


def test_a_results_file_git_would_track_is_refused_before_it_is_written(tmp_path):
    """Every record carries the retrieval results verbatim, so a results file
    holds corpus text -- the same unlicensed data the corpus itself is, which must
    never enter a repository (ADR-0170), where history is permanent.

    The guard is on the write, not on the command: a second driver would otherwise
    route around the one irreversible mistake this project can make.
    """
    tracked = Path("src") / "scinumbers_ask" / "leaked-results.jsonl"
    with pytest.raises(ResultsWouldBeCommitted, match="git would track"):
        append_result(tracked, a_result("q1"))
    assert not tracked.exists()


def test_a_results_file_outside_the_repository_is_allowed(tmp_path):
    """The other direction. A guard that refused everywhere would be discovered
    only as "the evaluation cannot write anything"."""
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    assert path.is_file()


def test_a_provenance_from_a_later_version_is_refused_with_an_explanation(tmp_path):
    """`Provenance` is documented as gaining reasoning effort as soon as `Config`
    carries it, so a file from a later version is expected rather than exotic. It
    used to raise `TypeError`, which the command does not catch, so `report` gave
    a traceback instead of the "written by a different version" sentence.
    """
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    record = json.loads(path.read_text().splitlines()[0])
    record["provenance"]["reasoning_effort"] = "high"
    path.write_text(json.dumps(record) + "\n")

    with pytest.raises(ResultsFileError, match="reasoning_effort"):
        read_results(path)


def test_an_untracked_file_does_not_mark_the_code_modified():
    """A stray untracked path is not a change to the code.

    Without `--untracked-files=no`, the results directory itself marks every run
    `+modified`, and the report then splits identical code into groups it refuses
    to combine on the grounds that they are different systems.
    """
    reported = code_version()
    if not reported.startswith("git "):
        pytest.skip("not a git checkout")
    tracked_changes = subprocess.run(
        ["git", "diff", "--quiet", "HEAD"], capture_output=True, check=False
    )
    if tracked_changes.returncode == 0:
        assert "+modified" not in reported


def test_a_re_asked_question_supersedes_its_earlier_record(tmp_path):
    """Appending is the only write, so re-asking leaves the earlier record behind.

    `outstanding` re-asks deliberately when a follow-up's parent is missing, on
    the ground that the recorded answer belongs to a session that no longer
    exists. Returning both would have every figure count the answer the driver
    had just declared invalid, and would report the question as unstable across
    repeats it never had.
    """
    path = tmp_path / "results.jsonl"
    append_result(path, replace(a_result("q1"), answer="the stale answer"))
    append_result(path, replace(a_result("q1"), answer="the current answer"))

    (result,) = read_results(path)
    assert result.answer == "the current answer"


def test_superseding_keeps_each_repeat_of_a_question_apart(tmp_path):
    """The key is the question *and* the repeat: collapsing on the question alone
    would throw away every repeat but the last, which is the measurement."""
    path = tmp_path / "results.jsonl"
    append_result(path, a_result("q1"))
    append_result(path, replace(a_result("q1"), repeat=2))

    assert [result.repeat for result in read_results(path)] == [1, 2]
