"""The agent: sessions, events, isolation, retries, and the conversation bound."""

from __future__ import annotations

import pytest

from bionumbers_ask.agent import CONVERSATION_BOUND, SYSTEM_PROMPT, AskAgent
from bionumbers_ask.config import Config, usd
from bionumbers_ask.corpus import load
from bionumbers_ask.events import Answer, EndReason, QuestionEnded, QuestionStarted, Retrieval
from bionumbers_ask.repository import CorpusRepository

from agent_doubles import says, scripted, tool_call

FIXTURE = "tests/fixtures/corpus_sample.jsonl"


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr("bionumbers_ask.agent.RETRY_INITIAL_DELAY", 0.0)


@pytest.fixture
def config() -> Config:
    return Config(model="fake/model", warning_threshold=usd("0.50"), run_budget=usd("1.20"))


@pytest.fixture
def repo() -> CorpusRepository:
    return CorpusRepository(load(FIXTURE))


def agent_with(repo, config, tmp_path, model, name="checkpoints.sqlite") -> AskAgent:
    return AskAgent(repo, config, str(tmp_path / name), model=model)


def run(agent: AskAgent, session: str, question: str) -> list:
    return list(agent.ask(session, question))


# -- the event contract ---------------------------------------------------


def test_a_question_emits_start_retrieval_answer_and_end(repo, config, tmp_path):
    model = scripted(
        tool_call("search_entries", property="Cell diameter"),
        says("About 1.0–1.1 μm (BNID 100002)."),
    )
    events = run(agent_with(repo, config, tmp_path, model), "s1", "How wide is E. coli?")
    kinds = [type(e).__name__ for e in events]
    assert kinds[0] == "QuestionStarted"
    assert "Retrieval" in kinds
    assert kinds[-2:] == ["Answer", "QuestionEnded"]
    end = events[-1]
    assert end.reason is EndReason.ANSWERED
    assert end.tool_calls >= 1
    assert end.model == "fake/model"


def test_retrieval_events_describe_what_was_looked_up(repo, config, tmp_path):
    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    retrieval = next(e for e in events if isinstance(e, Retrieval))
    assert retrieval.tool == "search_entries"
    # A driver needs the totals to render progress meaningfully.
    assert retrieval.detail["matched"] == 4


def test_every_event_carries_the_question_identifier(repo, config, tmp_path):
    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    ids = {e.question_id for e in events}
    assert len(ids) == 1


def test_the_agent_writes_nothing_itself(repo, config, tmp_path, capsys):
    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    run(agent_with(repo, config, tmp_path, model), "s1", "q")
    captured = capsys.readouterr()
    assert captured.out == ""


# -- sessions -------------------------------------------------------------


def test_a_follow_up_inherits_the_conversation(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, scripted(says("first")))
    run(agent, "s1", "How wide is E. coli?")
    assert agent.conversation_length("s1") >= 2

    agent2 = agent_with(repo, config, tmp_path, scripted(says("second")))
    run(agent2, "s1", "What about yeast?")
    # Both turns are present, so a follow-up can resolve against the earlier one.
    assert agent2.conversation_length("s1") >= 4


def test_a_new_session_does_not_inherit(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, scripted(says("first")))
    run(agent, "s1", "How wide is E. coli?")
    agent2 = agent_with(repo, config, tmp_path, scripted(says("second")))
    run(agent2, "s2", "What about yeast?")
    assert agent2.conversation_length("s2") == 2


def test_two_sessions_share_nothing(repo, config, tmp_path):
    a = agent_with(repo, config, tmp_path, scripted(says("one")))
    run(a, "alpha", "question one")
    b = agent_with(repo, config, tmp_path, scripted(says("two")))
    run(b, "beta", "question two")
    assert a.conversation_length("alpha") == 2
    assert b.conversation_length("beta") == 2


# -- reliability ----------------------------------------------------------


def test_a_transient_failure_is_retried_and_the_question_continues(repo, config, tmp_path):
    model = scripted(says("recovered"), failures=1)
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    assert model.attempts == 2, "the first attempt should have been retried"
    assert events[-1].reason is EndReason.ANSWERED


def test_exhausted_retries_end_the_question_as_a_provider_failure(repo, config, tmp_path):
    model = scripted(says("never reached"), failures=99)
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    end = events[-1]
    assert isinstance(end, QuestionEnded)
    # Reported as a provider failure rather than dressed up as an answer.
    assert end.reason is EndReason.PROVIDER_FAILURE
    assert end.incomplete is True
    assert not any(isinstance(e, Answer) for e in events)


# -- unattended operation is a driver, not a mode -------------------------


def test_the_same_question_emits_the_same_events_whoever_drives(repo, config, tmp_path):
    def once(name):
        model = scripted(tool_call("search_entries", property="Cell"), says("same"))
        return [type(e).__name__ for e in run(agent_with(repo, config, tmp_path, model, name), "s", "q")]

    assert once("a.sqlite") == once("b.sqlite")


def test_the_agent_takes_no_parameter_naming_its_caller(repo, config, tmp_path):
    import inspect

    params = set(inspect.signature(AskAgent.ask).parameters) | set(
        inspect.signature(AskAgent.__init__).parameters
    )
    for forbidden in ("driver", "interactive", "attended", "unattended", "mode", "headless"):
        assert forbidden not in params


# -- the conversation bound ----------------------------------------------


def test_a_session_at_the_bound_refuses_rather_than_dropping_context(repo, config, tmp_path, monkeypatch):
    monkeypatch.setattr("bionumbers_ask.agent.CONVERSATION_BOUND", 2)
    agent = agent_with(repo, config, tmp_path, scripted(says("first"), says("second")))
    run(agent, "s1", "first question")

    events = run(agent, "s1", "second question")
    end = events[-1]
    assert end.reason is EndReason.CONVERSATION_BOUND
    assert end.incomplete is True
    # The user is told, rather than context being discarded silently.
    assert "new session" in next(e for e in events if isinstance(e, Answer)).text
    # And nothing was dropped: the earlier turn is still there.
    assert agent.conversation_length("s1") == 2


def test_the_bound_is_a_real_limit_not_a_placeholder():
    assert CONVERSATION_BOUND > 0


# -- the answering rules live in the prompt ------------------------------


def test_the_prompt_states_the_rules_the_evaluation_will_score():
    # Whether the model obeys these is measured by answer-evaluation, not here.
    # What is checkable here is that it was told.
    lowered = SYSTEM_PROMPT.lower()
    assert "cite every quantity" in lowered
    assert "does not cover" in lowered
    assert "computed" in lowered
    assert "follow-up" in lowered
