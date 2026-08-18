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


# =========================================================================
# Regressions from the second code review. Each names the silent failure it
# prevents, because each was invisible to a green suite.
# =========================================================================


class _FailingRepo:
    """A repository whose search always raises, counting attempts.

    Fault injection at a seam we control. A retry policy that is never made to
    fail is unverified by construction -- which is exactly how the tool-retry
    ordering bug survived a passing suite.
    """

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.attempts = 0

    def search(self, **kwargs):
        self.attempts += 1
        raise self.exc

    def get(self, *a, **k):
        return None

    def vocabulary(self, *a, **k):
        return ()


def _agent_over(repo_double, config, tmp_path, model):
    return AskAgent(repo_double, config, str(tmp_path / "c.sqlite"), model=model)


def test_a_recoverable_tool_error_is_actually_retried(config, tmp_path):
    from bionumbers_ask.agent import TOOL_RETRIES

    failing = _FailingRepo(ValueError("bad argument"))
    model = scripted(tool_call("search_entries", property="x"), says("gave up on that lookup"))
    list(_agent_over(failing, config, tmp_path, model).ask("s", "q"))
    # Before the ordering fix this was 1: ToolErrorMiddleware sat inside the retry
    # middleware and converted every exception before retry could see one.
    assert failing.attempts == TOOL_RETRIES + 1


def test_an_unexpected_tool_error_is_not_dressed_up_as_a_lookup_failure(config, tmp_path):
    failing = _FailingRepo(AttributeError("corpus schema changed"))
    model = scripted(tool_call("search_entries", property="x"), says("unreachable"))
    events = list(_agent_over(failing, config, tmp_path, model).ask("s", "q"))
    end = events[-1]
    # A defect must not reach the model as "the lookup failed", or it answers
    # "the corpus has nothing on this" -- wrong, and sounding grounded.
    assert end.reason is EndReason.PROVIDER_FAILURE
    assert not any(isinstance(e, Answer) for e in events)


def test_the_tool_error_message_names_the_type_not_the_exception_text(config):
    from bionumbers_ask.agent import _tool_error_message

    message = _tool_error_message(ValueError("secret internal detail"), None)
    assert "ValueError" in message
    assert "secret internal detail" not in message
    assert _tool_error_message(AttributeError("boom"), None) is None


def test_reaching_the_call_limit_names_the_limit_rather_than_answering(repo, config, tmp_path):
    from bionumbers_ask.agent import RUN_CALL_LIMIT

    # A model that only ever asks for another search never terminates on its own.
    model = scripted(tool_call("search_entries", property="Cell"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    end = events[-1]
    # Before the fix this was ANSWERED, with the middleware's own string
    # "Model call limits exceeded: run limit (12/12)" presented as the answer.
    assert end.reason is EndReason.RETRIEVAL_BOUND
    assert end.incomplete is True
    assert not any(isinstance(e, Answer) for e in events)
    assert end.tool_calls <= RUN_CALL_LIMIT + 1


def test_an_answer_in_content_blocks_is_recovered(repo, config, tmp_path):
    from langchain_core.messages import AIMessage

    blocky = AIMessage(content=[{"type": "text", "text": "one micrometre (BNID 100002)"}])
    events = list(agent_with(repo, config, tmp_path, scripted(blocky)).ask("s", "q"))
    answer = next(e for e in events if isinstance(e, Answer))
    assert "micrometre" in answer.text
    assert events[-1].reason is EndReason.ANSWERED


def test_a_blank_answer_is_not_reported_as_answered(repo, config, tmp_path):
    from langchain_core.messages import AIMessage

    events = list(agent_with(repo, config, tmp_path, scripted(AIMessage(content=""))).ask("s", "q"))
    end = events[-1]
    assert end.reason is EndReason.NO_ANSWER
    assert end.incomplete is True
    assert not any(isinstance(e, Answer) for e in events)


def test_the_user_is_warned_before_the_conversation_bound_bites(repo, config, tmp_path, monkeypatch):
    from bionumbers_ask.events import ConversationWarning

    # Bound 5 warns at 3.75 messages. After two turns a session holds four, which
    # is past the warning point and short of the bound -- the window in which the
    # user can still finish what they were doing.
    monkeypatch.setattr("bionumbers_ask.agent.CONVERSATION_BOUND", 5)
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b"), says("c")))
    assert not any(isinstance(e, ConversationWarning) for e in agent.ask("s", "first"))
    assert not any(isinstance(e, ConversationWarning) for e in agent.ask("s", "second"))

    warned = [e for e in agent.ask("s", "third") if isinstance(e, ConversationWarning)]
    assert warned, "the session filled up with no warning"
    assert warned[0].bound == 5 and warned[0].messages == 4


def test_conversation_length_needs_no_model_and_no_api_key(repo, config, tmp_path, monkeypatch):
    agent = agent_with(repo, config, tmp_path, scripted(says("hello")))
    list(agent.ask("s", "q"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    bare = AskAgent(repo, config, str(tmp_path / "checkpoints.sqlite"))  # no model supplied
    # Reading how full a session is must not construct a chat model.
    assert bare.conversation_length("s") >= 2
    assert bare.conversation_length("never-used") == 0


def test_a_defect_in_our_own_code_is_not_labelled_a_provider_failure(repo, config, tmp_path, monkeypatch):
    def explode(_message):
        raise TypeError("a bug in this file, not the provider")

    monkeypatch.setattr("bionumbers_ask.agent._text_of", explode)
    # It must escape rather than be reported as PROVIDER_FAILURE, which would send
    # whoever debugs it to the provider instead of to this file.
    with pytest.raises(TypeError, match="a bug in this file"):
        list(agent_with(repo, config, tmp_path, scripted(says("x"))).ask("s", "q"))


def test_a_rejected_tool_call_still_appears_in_progress_and_the_count(repo, config, tmp_path):
    model = scripted(tool_call("list_values", field="keyword", contains="x"), says("done"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    retrievals = [e for e in events if isinstance(e, Retrieval)]
    assert retrievals and retrievals[0].detail.get("rejected") is True
    assert events[-1].tool_calls >= 1


# =========================================================================
# Gaps found by auditing the suite against the harness-testing checklist,
# rather than by reviewing the code.
# =========================================================================


def test_spend_is_read_from_the_shape_openrouter_actually_returns():
    """Pin a live discovery as an offline regression test.

    The field path was verified against OpenRouter once, by hand. Nothing checked
    it afterwards, so a renamed field would have made spend read zero in silence --
    under a ceiling built on top of it.
    """
    from langchain_core.messages import AIMessage

    from agent_doubles import OPENROUTER_RESPONSE_METADATA
    from bionumbers_ask.agent import _Spend

    message = AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA)
    spend = _Spend()
    spend.add_from(message)
    # 3.4e-05 USD, the figure the live call reported, in micro-dollars.
    assert spend.micro == 34


def test_spend_accumulates_across_several_calls():
    from langchain_core.messages import AIMessage

    from agent_doubles import OPENROUTER_RESPONSE_METADATA
    from bionumbers_ask.agent import _Spend

    spend = _Spend()
    for _ in range(3):
        spend.add_from(AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA))
    assert spend.micro == 102


def test_a_response_without_a_cost_adds_nothing_rather_than_guessing():
    from langchain_core.messages import AIMessage

    from bionumbers_ask.agent import _Spend

    spend = _Spend()
    spend.add_from(AIMessage(content="ok"))
    spend.add_from(AIMessage(content="ok", response_metadata={"token_usage": {"total_tokens": 5}}))
    # Spend-control requires a question to halt rather than continue with an
    # unknown cost; that gate is group 5's, but the ledger must not invent one.
    assert spend.micro == 0


def test_several_tools_requested_in_one_hop_are_all_reported(repo, config, tmp_path):
    """Real models batch tool calls; a fake that never does hides that path."""
    from agent_doubles import batched_tool_calls

    model = scripted(
        batched_tool_calls(
            ("search_entries", {"property": "Cell diameter"}),
            ("search_entries", {"organism": "cerevisiae"}),
            ("list_values", {"field": "organism", "contains": "coli"}),
        ),
        says("three lookups, one hop"),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    retrievals = [e for e in events if isinstance(e, Retrieval)]
    # Each tool that ran must appear, and the count must not collapse them.
    assert len(retrievals) == 3, [r.tool for r in retrievals]
    assert events[-1].tool_calls == 3
    assert {r.tool for r in retrievals} == {"search_entries", "list_values"}


def test_batched_tool_calls_do_not_lose_events_under_concurrency(repo, config, tmp_path):
    from agent_doubles import batched_tool_calls

    many = batched_tool_calls(*[("search_entries", {"property": "Cell"}) for _ in range(8)])
    events = list(agent_with(repo, config, tmp_path, scripted(many, says("done"))).ask("s", "q"))
    # The framework may run these on worker threads, all appending to one queue.
    assert len([e for e in events if isinstance(e, Retrieval)]) == 8
