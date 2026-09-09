"""The agent: sessions, events, isolation, retries, and the conversation bound."""

from __future__ import annotations

import pytest
from conftest import agent_with, run
from langchain_core.messages import AIMessage

from agent_doubles import (
    OutOfCreditModel,
    batched_tool_calls,
    costing,
    out_of_credit_error,
    provider_error,
    says,
    scripted,
    tool_call,
)
from scinumbers_ask import messages
from scinumbers_ask.agent import CONVERSATION_BOUND, SYSTEM_PROMPT, AskAgent
from scinumbers_ask.config import Config, usd
from scinumbers_ask.events import (
    Answer,
    AnswerEntries,
    CitationWarning,
    EndReason,
    QuestionEnded,
    QuestionStarted,
    Retrieval,
    UngroundedRefusal,
)

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
    # The answer, then the entries it rests on, then the ending. The entries come
    # after the answer because a reader checks prose against a table, not the
    # other way round.
    assert kinds[-3:] == ["Answer", "AnswerEntries", "QuestionEnded"]
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


def test_the_context_a_session_was_shown_is_readable_from_it(repo, config, tmp_path):
    """The evaluation records what the agent was shown, and this is the only source
    that is that by construction: a search for "Cell diameter" against the fixture
    corpus must have put entry 100002 in front of the model, so the recorded text
    has to carry it."""
    model = scripted(tool_call("search_entries", property="Cell diameter"), says("done"))
    agent = agent_with(repo, config, tmp_path, model)
    run(agent, "s1", "How wide is E. coli?")
    (shown,) = agent.tool_results("s1")
    assert "100002" in shown


def test_a_session_shown_nothing_records_nothing(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, scripted(says("from memory")))
    run(agent, "s1", "How wide is E. coli?")
    assert agent.tool_results("s1") == ()


def test_every_tool_result_is_recorded_in_order_not_only_the_last(repo, config, tmp_path):
    """A question makes several retrievals, and the context is all of them.

    Keeping only the last would misreport the evidence of exactly the questions
    that took the most work to answer.
    """
    model = scripted(
        tool_call("search_entries", property="Cell diameter"),
        tool_call("search_entries", property="Cell length"),
        says("done"),
    )
    agent = agent_with(repo, config, tmp_path, model)
    run(agent, "s1", "How big is E. coli?")
    first, second = agent.tool_results("s1")
    assert "100002" in first
    assert "100001" in second


def test_a_search_that_matched_nothing_is_recorded_rather_than_dropped(repo, config, tmp_path):
    """It is what the model was shown, and it is why a refusal was right.

    A record that held only fruitful retrievals would make a correct refusal look
    like a refusal with no search behind it.
    """
    model = scripted(tool_call("search_entries", property="Number of neoblasts"), says("no"))
    agent = agent_with(repo, config, tmp_path, model)
    run(agent, "s1", "How many neoblasts?")
    (shown,) = agent.tool_results("s1")
    assert "No entries matched" in shown


def test_each_session_records_only_its_own_context(repo, config, tmp_path):
    a = agent_with(
        repo,
        config,
        tmp_path,
        scripted(tool_call("search_entries", property="Cell diameter"), says("a")),
    )
    run(a, "alpha", "question one")
    b = agent_with(
        repo,
        config,
        tmp_path,
        scripted(tool_call("search_entries", property="Cell length"), says("b")),
    )
    run(b, "beta", "question two")
    assert "100002" in a.tool_results("alpha")[0]
    assert "100002" not in b.tool_results("beta")[0]


def test_a_follow_up_sees_its_parent_context_too(repo, config, tmp_path):
    """A follow-up shares its parent's session, so the context recorded for it is
    the whole session's -- which is what the harness needs, since a follow-up's
    answer may rest on an entry retrieved for the question before it."""
    first = agent_with(
        repo,
        config,
        tmp_path,
        scripted(tool_call("search_entries", property="Cell diameter"), says("a")),
    )
    run(first, "s1", "How wide is E. coli?")
    second = agent_with(
        repo,
        config,
        tmp_path,
        scripted(tool_call("search_entries", property="Cell length"), says("b")),
    )
    run(second, "s1", "And how long?")
    assert len(second.tool_results("s1")) == 2


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
    # The other direction of the same rule, and the one that costs more: an outage
    # must not be reported as a spent key, which would shut the run for everyone on
    # a reason that was not true.
    assert end.reason not in messages.STOP_THE_RUN


def test_a_key_out_of_credit_says_what_happened_and_stops_the_run(repo, config, tmp_path):
    """A shared deployment's key hits its cap while somebody is using it.

    The terse ending line was all a reader got: "provider_failure · $0.00 · ...",
    which reads as a fault in the app or in their question, and left the input live
    so the next question failed the same way. Both parts are the point -- the
    sentence, and the door closing.
    """
    model = OutOfCreditModel(responses=[says("never reached")])
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    end = events[-1]
    assert isinstance(end, QuestionEnded)
    assert end.reason is EndReason.PROVIDER_LIMIT
    assert end.incomplete is True
    # Asking again cannot come out differently until somebody pays.
    assert end.reason in messages.STOP_THE_RUN
    answer = next(e for e in events if isinstance(e, Answer))
    # The agent reports the fact. What to *do* about it -- whose key, who can raise
    # it -- is a fact about a deployment, so it is the drivers' sentence:
    # `test_terminal_driver` and `test_web_driver` asserts each renders it.
    assert "no credit left" in answer.text
    assert messages.run_over_advice(EndReason.PROVIDER_LIMIT), "the drivers need the advice"
    # Not retried: the key does not acquire a balance during the backoff, and the
    # reader would wait out the full delay for the same sentence.
    assert model.attempts == 1


def test_a_key_out_of_credit_keeps_the_answer_it_had_already_paid_for(repo, config, tmp_path):
    """The balance usually runs out part-way through, not before the first call.

    This branch used to yield a canned notice *as* the answer, discarding whatever
    the model had established -- the opposite of what every other early ending in
    the same loop does, and on the shape of failure that happens most.
    """
    model = OutOfCreditModel(
        responses=[
            AIMessage(
                content="Cell diameter is about 1.0–1.1 μm [[100002]].",
                tool_calls=[{"name": "search_entries", "args": {"property": "Cell"}, "id": "c1"}],
            )
        ],
        refuse_after=1,
    )
    events = run(agent_with(repo, config, tmp_path, model), "s1", "How wide is E. coli?")
    answer = next(e for e in events if isinstance(e, Answer))
    assert "1.0–1.1 μm" in answer.text, "the model's own text, not a notice replacing it"
    assert events[-1].reason is EndReason.PROVIDER_LIMIT
    assert events[-1].incomplete is True
    # The entries it did retrieve are still shown: work already paid for.
    assert any(isinstance(e, AnswerEntries) for e in events)


def test_a_question_with_no_answer_is_not_told_its_answer_is_ungrounded(repo, config, tmp_path):
    """There is no answer, so "this answer is not grounded in the corpus" describes
    something that does not exist -- and `NO_ANSWER` already says what happened.

    A fourth instance of the same defect, found while fixing the three branches that
    substitute a sentence: this one does not even substitute, it shows nothing.
    """
    model = scripted(AIMessage(content=""))
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    assert events[-1].reason is EndReason.NO_ANSWER
    assert not any(isinstance(e, UngroundedRefusal) for e in events)


def test_what_retrieval_found_before_the_refusal_is_still_shown(repo, config, tmp_path):
    """A 402 after a search but before any prose: the entries survive the substitute.

    The guarantee the `judge_the_prose` flag is *for* -- suppress the report about
    prose, keep the evidence -- and it was unasserted. Moving the guard to the top of
    `evidence()`, which drops the table for every substituted answer, passed the whole
    suite: the two other tests here have prose (so nothing is suppressed) or nothing
    retrieved (so an absent table is correct).
    """
    model = OutOfCreditModel(
        responses=[tool_call("search_entries", property="Cell")], refuse_after=1
    )
    events = run(agent_with(repo, config, tmp_path, model), "s1", "How wide is E. coli?")
    assert events[-1].reason is EndReason.PROVIDER_LIMIT
    entries = next(e for e in events if isinstance(e, AnswerEntries))
    assert entries.retrieved, "the search happened and was paid for; its entries stand"
    # And still no judgement about the substitute standing in for an answer.
    assert not any(isinstance(e, (CitationWarning, UngroundedRefusal)) for e in events)


def test_nothing_is_judged_about_prose_the_reader_never_saw(repo, config, tmp_path):
    """With no answer of the model's, the notice stands in -- and is not analysed.

    Judged, it produced accusations about invisible text: a citation warning naming
    an entry the discarded prose had cited, or "this answer is not grounded in the
    corpus -- it says only what the model expected to find" about a system notice,
    with `answer.ungrounded` in the trail for a question the model never answered.
    """
    model = OutOfCreditModel(responses=[says("never reached")])
    events = run(agent_with(repo, config, tmp_path, model), "s1", "q")
    answer = next(e for e in events if isinstance(e, Answer))
    assert "no credit left" in answer.text
    assert not any(isinstance(e, (CitationWarning, UngroundedRefusal)) for e in events)
    # Nothing was retrieved either, so an entries table would say nothing at all.
    assert not any(isinstance(e, AnswerEntries) for e in events)


def test_the_attribute_this_rule_reads_is_on_the_provider_s_own_error(repo, config, tmp_path):
    """`_is_out_of_credit` reads `status_code`, so this asserts the real type has one.

    Against `openai.APIStatusError` rather than a stand-in with the attribute
    bolted on, which would pass whether or not the provider's error still carried
    it -- and the failure that mattered would be silent: every spent key reported
    as an ordinary outage, with the door left open.
    """
    from scinumbers_ask.agent import _is_out_of_credit

    assert _is_out_of_credit(out_of_credit_error())
    # The expensive direction, and it needs errors that *have* a status: with only
    # status-less exceptions here, a rule reading `status_code is not None` passed
    # the whole suite -- and under it a rate limit or a bad gateway would close the
    # run for every reader. 429 and 502 are the two this would actually meet.
    assert not _is_out_of_credit(provider_error(429, "Rate limited"))
    assert not _is_out_of_credit(provider_error(502, "Bad gateway"))
    assert not _is_out_of_credit(provider_error(401, "Invalid credentials"))
    assert not _is_out_of_credit(RuntimeError("upstream unavailable"))
    assert not _is_out_of_credit(TimeoutError())


# -- unattended operation is a driver, not a mode -------------------------


def test_the_same_question_emits_the_same_events_whoever_drives(repo, config, tmp_path):
    def once(name):
        model = scripted(tool_call("search_entries", property="Cell"), says("same"))
        return [
            type(e).__name__ for e in run(agent_with(repo, config, tmp_path, model, name), "s", "q")
        ]

    assert once("a.sqlite") == once("b.sqlite")


def test_the_agent_takes_no_parameter_naming_its_caller(repo, config, tmp_path):
    import inspect

    params = set(inspect.signature(AskAgent.ask).parameters) | set(
        inspect.signature(AskAgent.__init__).parameters
    )
    for forbidden in ("driver", "interactive", "attended", "unattended", "mode", "headless"):
        assert forbidden not in params


# -- the conversation bound ----------------------------------------------


def test_a_session_at_the_bound_refuses_rather_than_dropping_context(
    repo, config, tmp_path, monkeypatch
):
    monkeypatch.setattr("scinumbers_ask.agent.CONVERSATION_BOUND", 2)
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
    # The weaker claim on purpose: "could not find" is what a handful of searches
    # establishes, and "does not contain" is not.
    assert "could not find it" in lowered
    assert "not that the corpus does not contain it" in lowered
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
    from scinumbers_ask.agent import TOOL_RETRIES

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
    # "the corpus has nothing on this" -- wrong, and sounding grounded. Nor is it
    # the provider's fault: that reading says "try again", and this will fail the
    # same way every time.
    assert end.reason is EndReason.INTERNAL_ERROR
    assert end.incomplete
    assert not any(isinstance(e, Answer) for e in events)


def test_a_failing_provider_is_still_reported_as_the_provider(config, tmp_path):
    """The other side of the split. A request that failed is worth retrying, and
    saying otherwise sends the reader to look for a bug that is not there."""
    failing = _FailingRepo(ConnectionError("upstream reset"))
    model = scripted(tool_call("search_entries", property="x"), says("unreachable"))
    events = list(_agent_over(failing, config, tmp_path, model).ask("s", "q"))
    assert events[-1].reason is EndReason.PROVIDER_FAILURE


def test_the_trail_says_where_our_own_defect_was_raised(repo):
    """Reported without a location, an internal error is only marginally better
    than the provider's name: it says the fault is ours without saying where.

    Only our own frames are named, so a defect surfacing deep inside a library
    still points at the line of ours that led there rather than at the library."""
    from scinumbers_ask.agent import _origin

    try:
        repo.vocabulary("not-a-field")
    except ValueError as exc:
        where = _origin(exc)
    assert where.startswith("repository.py:"), where

    try:
        raise AttributeError("raised outside the package")
    except AttributeError as exc:
        assert _origin(exc) == "", "nothing of ours is on that traceback"


def test_the_trail_finds_our_frames_by_module_rather_than_by_path(repo):
    """Two versions of this returned no origin at all, silently, and this is why.

    The first matched a hardcoded package name, which the rename falsified. The
    second compared each frame's filename against the package directory resolved
    from `__file__` -- and `co_filename` is *not* resolved, so an install or a
    checkout reached through a symlink made every origin blank. Both failures look
    identical from outside: an internal error that says the fault is ours without
    saying where, with nothing raising.

    Asserting the mechanism rather than the outcome, because the outcome under a
    symlink is only reproducible by building one, and the property that actually
    holds is that no filesystem path is consulted at all.
    """
    import inspect

    from scinumbers_ask import agent as agent_module

    # The docstring is stripped first: it explains the two failures by name, so a
    # check against the raw source matches the explanation rather than the code.
    body = inspect.getsource(agent_module._origin).replace(agent_module._origin.__doc__, "")
    assert "f_globals" in body and "__package__" in body
    assert "__file__" not in body, "the origin check is back on the filesystem"

    # And a sibling package sharing our prefix is not ours.
    assert not "scinumbers_ask_helpers".startswith(f"{agent_module.__package__}.")


def test_the_tool_error_message_names_the_type_not_the_exception_text(config):
    from scinumbers_ask.agent import _tool_error_message

    message = _tool_error_message(ValueError("secret internal detail"), None)
    assert "ValueError" in message
    assert "secret internal detail" not in message
    assert _tool_error_message(AttributeError("boom"), None) is None


def test_reaching_the_call_limit_names_the_limit_rather_than_answering(repo, config, tmp_path):
    from scinumbers_ask.agent import RUN_CALL_LIMIT

    # A model that only ever asks for another search never terminates on its own.
    model = scripted(tool_call("search_entries", property="Cell"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    end = events[-1]
    # Before the fix this was ANSWERED, with the middleware's own string
    # "Model call limits exceeded: run limit (12/12)" presented as the answer.
    assert end.reason is EndReason.RETRIEVAL_BOUND
    assert end.incomplete is True
    assert end.tool_calls <= RUN_CALL_LIMIT + 1

    # This model established nothing, so what it gets is an explanation rather than
    # a partial answer -- and never the middleware's own message, which with
    # exit_behavior="error" lives in the exception and not in a model message.
    answer = next(e for e in events if isinstance(e, Answer))
    assert "limit on how much retrieval" in answer.text
    assert "Model call limits exceeded" not in answer.text


def test_what_was_established_before_the_bound_is_still_presented(repo, config, tmp_path):
    """The spend ceiling already did this; the retrieval bound discarded it. A
    question stopped at the bound may already hold something citable, and throwing
    it away discards work that was paid for."""
    from langchain_core.messages import AIMessage

    monkey = AIMessage(
        content="Cell length is 1.94-2.72 um (BNID 100001), and I am still looking.",
        tool_calls=[{"name": "search_entries", "args": {"property": "Cell"}, "id": "c1"}],
    )
    # Prose and a tool call in the same message, every hop: the model never stops,
    # so the bound does -- with real findings already on the table.
    events = list(agent_with(repo, config, tmp_path, scripted(monkey)).ask("s", "q"))
    end = events[-1]
    assert end.reason is EndReason.RETRIEVAL_BOUND

    answer = next(e for e in events if isinstance(e, Answer))
    assert "BNID 100001" in answer.text
    entries = next(e for e in events if isinstance(e, AnswerEntries))
    assert 100001 in entries.cited, "the citations in the partial answer were lost"


def test_the_bound_ending_reports_the_count_that_tripped_it(repo, config, tmp_path):
    """The ending already named the bound; it did not say what reached it, so
    nothing downstream could tell a bound set too low from a model that looped."""
    from scinumbers_ask.agent import RUN_CALL_LIMIT

    model = scripted(tool_call("search_entries", property="Cell"))
    end = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))[-1]
    assert (end.model_calls, end.call_limit) == (RUN_CALL_LIMIT, RUN_CALL_LIMIT)
    assert end.at_retrieval_bound is True


def test_an_answer_produced_with_no_calls_left_is_marked(repo, config, tmp_path, monkeypatch):
    """An answer reached at the wall stopped searching because it ran out of room,
    not because it was satisfied -- and it is otherwise indistinguishable from one
    produced with calls to spare."""
    monkeypatch.setattr("scinumbers_ask.agent.RUN_CALL_LIMIT", 3)
    model = scripted(
        tool_call("search_entries", property="Cell"),
        tool_call("get_entry", entry_id=100001),
        says("Cell length is 1.94-2.72 um (BNID 100001)."),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    end = events[-1]
    assert end.reason is EndReason.ANSWERED
    # Answered, and complete: the bound is a fact about how it was reached, not a
    # reason to distrust the answer.
    assert end.incomplete is False
    assert (end.model_calls, end.call_limit) == (3, 3)
    assert end.at_retrieval_bound is True


def test_an_answer_with_calls_to_spare_is_not_marked(repo, config, tmp_path, monkeypatch):
    monkeypatch.setattr("scinumbers_ask.agent.RUN_CALL_LIMIT", 3)
    model = scripted(
        tool_call("search_entries", property="Cell"),
        says("Cell length is 1.94-2.72 um (BNID 100001)."),
    )
    end = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))[-1]
    assert (end.model_calls, end.call_limit) == (2, 3)
    assert end.at_retrieval_bound is False


def test_a_retried_call_is_counted_once(repo, config, tmp_path, monkeypatch):
    """The count has to be the middleware's own, not attempts made here: a provider
    failure that succeeds on retry is one model call against the bound, and counting
    attempts would report a question as cornered when it had every call left."""
    monkeypatch.setattr("scinumbers_ask.agent.RUN_CALL_LIMIT", 3)
    model = scripted(says("Cell length is 1.94-2.72 um (BNID 100001)."), failures=1)
    end = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))[-1]
    assert model.attempts == 2, "the double did not actually fail once"
    assert end.model_calls == 1
    assert end.at_retrieval_bound is False


def test_a_question_that_never_reaches_the_model_claims_no_bound(repo, config, tmp_path):
    """No bound was applied, so reporting one -- even as zero of twelve -- would
    describe a limit the question never met."""
    spent = Config(model="fake/model", question_ceiling=usd("0.60"), run_budget=usd("0.00"))
    agent = AskAgent(repo, spent, str(tmp_path / "c.sqlite"), model=scripted(says("x")))
    end = list(agent.ask("s", "q"))[-1]
    assert end.reason is EndReason.RUN_BUDGET
    assert (end.model_calls, end.call_limit) == (0, 0)
    assert end.at_retrieval_bound is False


def test_a_question_the_corpus_does_not_cover_is_presented_as_answered(repo, config, tmp_path):
    """Refusing correctly *is* answering. Reporting it as a failure would push a
    driver to retry, or to show an error where the right thing happened.

    This is the harness half of the requirement. Whether the model refuses at all
    is rule 2, and a scripted double cannot test that -- it says whatever the test
    tells it to. The live suite covers that half.
    """
    from scinumbers_ask.citations import citations

    model = scripted(
        tool_call("search_entries", property="lifespan", organism="mouse"),
        tool_call("list_values", field="property", contains="lifespan"),
        says("The corpus holds no entries on mouse lifespan, so I cannot answer this."),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "how long do mice live?"))
    end = events[-1]
    assert end.reason is EndReason.ANSWERED
    assert end.incomplete is False

    answer = next(e for e in events if isinstance(e, Answer))
    assert citations(answer.text) == ()


def test_a_refusal_claims_no_entries_and_no_coverage(repo, config, tmp_path):
    """The presentation must not suggest evidence that is not there: no table, and
    no matched figure, since "0 matched" beside a refusal reads as a measurement of
    the corpus rather than of the search."""
    from scinumbers_ask.cli import render as render_event
    from scinumbers_ask.events import AnswerEntries, CitationWarning

    model = scripted(
        tool_call("search_entries", property="lifespan", organism="mouse"),
        says("The corpus holds no entries on mouse lifespan, so I cannot answer this."),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "how long do mice live?"))

    entries = next(e for e in events if isinstance(e, AnswerEntries))
    assert (entries.cited, entries.retrieved) == ((), ())
    assert entries.matched == 0
    assert render_event(entries, repo=repo) is None, "a refusal must render no table"

    # Citing nothing is not a citation defect. The warning is for citing something
    # the corpus does not hold, and firing it here would turn the correct behaviour
    # into a reported fault.
    assert not any(isinstance(e, CitationWarning) for e in events)


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


def test_the_user_is_warned_before_the_conversation_bound_bites(
    repo, config, tmp_path, monkeypatch
):
    from scinumbers_ask.events import ConversationWarning

    # The double reports a 14-token prompt, the shape a real response carries. A
    # bound of 18 warns at 13.5, so one completed turn lands past the warning and
    # short of the bound -- the window in which the user can still finish what
    # they were doing. The first question has made no request yet, so there is
    # nothing reported to warn about.
    monkeypatch.setattr("scinumbers_ask.agent.CONVERSATION_BOUND", 18)
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b"), says("c")))
    assert not any(isinstance(e, ConversationWarning) for e in agent.ask("s", "first"))

    warned = [e for e in agent.ask("s", "second") if isinstance(e, ConversationWarning)]
    assert warned, "the session filled up with no warning"
    assert warned[0].bound == 18 and warned[0].tokens == 14


def test_conversation_length_needs_no_model_and_no_api_key(repo, config, tmp_path, monkeypatch):
    agent = agent_with(repo, config, tmp_path, scripted(says("hello")))
    list(agent.ask("s", "q"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    bare = AskAgent(repo, config, str(tmp_path / "checkpoints.sqlite"))  # no model supplied
    # Reading how full a session is must not construct a chat model.
    assert bare.conversation_length("s") >= 2
    assert bare.conversation_length("never-used") == 0


def test_a_defect_in_our_own_code_is_not_labelled_a_provider_failure(
    repo, config, tmp_path, monkeypatch
):
    def explode(_message):
        raise TypeError("a bug in this file, not the provider")

    monkeypatch.setattr("scinumbers_ask.agent._text_of", explode)
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
    from scinumbers_ask.spend import SpendLedger

    message = AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA)
    ledger = SpendLedger(model="m", prices=None)
    ledger.add_response([message])
    # 3.4e-05 USD, the figure the live call reported, in micro-dollars.
    assert ledger.question == 34
    assert ledger.run == 34


def test_spend_accumulates_across_several_calls():
    from langchain_core.messages import AIMessage

    from agent_doubles import OPENROUTER_RESPONSE_METADATA
    from scinumbers_ask.spend import SpendLedger

    ledger = SpendLedger(model="m", prices=None)
    for _ in range(3):
        ledger.add_response(
            [AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA)]
        )
    assert ledger.question == 102


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


def test_every_non_raising_path_ends_with_a_question_ended(repo, config, tmp_path, monkeypatch):
    """The contract property, not another case.

    A driver pairs a start with an ending, or renders progress until one arrives.
    A path that returns without one leaves it waiting for an event that never
    comes. Enumerated per-case tests keep missing the path nobody thought of --
    this asserts the invariant across every ending the agent can produce.
    """
    from langchain_core.messages import AIMessage

    from scinumbers_ask.agent import AskAgent

    def normal():
        return agent_with(repo, config, tmp_path, scripted(says("an answer")), "n.sqlite"), "s"

    def blank():
        return agent_with(repo, config, tmp_path, scripted(AIMessage(content="")), "b.sqlite"), "s"

    def provider_dead():
        return agent_with(repo, config, tmp_path, scripted(says("x"), failures=99), "p.sqlite"), "s"

    def call_limit():
        model = scripted(tool_call("search_entries", property="Cell"))
        return agent_with(repo, config, tmp_path, model, "l.sqlite"), "s"

    def unconfigured():
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        return AskAgent(repo, config, str(tmp_path / "u.sqlite")), "s"

    def at_conversation_bound():
        # Must ask once first: with a fresh session the bound is not yet reached,
        # so lowering it alone produced an ordinary answer rather than a refusal.
        # Last in the list, because the patched bound outlives this closure.
        monkeypatch.setattr("scinumbers_ask.agent.CONVERSATION_BOUND", 1)
        agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")), "c.sqlite")
        list(agent.ask("s", "a first question, which fills the conversation"))
        return agent, "s"

    def at_spend_ceiling():
        tight = Config(model=config.model, question_ceiling=usd("0.000120"), run_budget=usd("1.20"))
        model = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_200))
        return AskAgent(repo, tight, str(tmp_path / "sc.sqlite"), model=model), "s"

    def at_run_budget():
        budgeted = Config(
            model=config.model, question_ceiling=usd("0.60"), run_budget=usd("0.000050")
        )
        model = scripted(costing(says("an answer"), 0.000_110))
        agent = AskAgent(repo, budgeted, str(tmp_path / "rb.sqlite"), model=model)
        list(agent.ask("s", "a first question, which exhausts the budget"))
        return agent, "s"

    def unpriceable():
        model = scripted(says("an answer"), reports_cost=False)
        return agent_with(repo, config, tmp_path, model, "up.sqlite"), "s"

    builds = (
        normal,
        blank,
        provider_dead,
        call_limit,
        unconfigured,
        at_spend_ceiling,
        at_run_budget,
        unpriceable,
        at_conversation_bound,
    )
    reasons = set()
    for build in builds:
        agent, session = build()
        events = list(agent.ask(session, "How wide is an E. coli cell?"))
        assert events, f"{build.__name__}: emitted nothing"
        assert isinstance(events[0], QuestionStarted), f"{build.__name__}: no start"
        end = events[-1]
        assert isinstance(end, QuestionEnded), (
            f"{build.__name__}: ended without a QuestionEnded -- "
            f"got {[type(e).__name__ for e in events]}"
        )
        # Spend is always reported, whatever ended the question, and is only
        # interpretable next to the model that incurred it.
        assert end.model, f"{build.__name__}: ending named no model"
        assert end.spend >= 0 and end.run_spend >= end.spend, (
            f"{build.__name__}: question spend {end.spend} exceeds run spend {end.run_spend}"
        )
        reasons.add(end.reason)

    # Nine builds, eight distinct endings -- the unconfigured and unpriceable paths
    # share NOT_CONFIGURED. Asserting the exact count so a build that silently
    # collapsed onto another ending would be caught rather than absorbed.
    assert len(reasons) == 8, sorted(r.value for r in reasons)


# -- gaps found by coverage, not by reading -------------------------------


def test_get_entry_returns_the_detail_an_answer_needs_to_cite(repo, config, tmp_path):
    """Coverage found this tool entirely unexercised offline.

    It is the one that produces every citation: the live test ran it, so it worked,
    but nothing offline would have noticed it breaking.
    """
    model = scripted(tool_call("get_entry", entry_id=100001), says("cited it"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    retrieval = next(e for e in events if isinstance(e, Retrieval))
    assert retrieval.tool == "get_entry"
    assert retrieval.detail == {"entry_id": 100001, "found": True}


def test_get_entry_text_carries_value_units_reference_and_cross_references(repo, config, tmp_path):
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import QuestionTrace

    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), lambda _e: None)}
    text = tools["get_entry"].invoke({"entry_id": 100001})
    for expected in ("entry_id: 100001", "Cell length", "1.94–2.72", "μm", "reference:", "cites:"):
        assert expected in text, f"{expected!r} missing from:\n{text}"
    assert "102065" in text, "cross-referenced identifiers must be listed"


def test_an_unknown_entry_id_says_so_rather_than_inventing(repo, config, tmp_path):
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import QuestionTrace

    seen: list = []
    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), seen.append)}
    assert "No entry 999999" in tools["get_entry"].invoke({"entry_id": 999999})
    assert seen[0].detail == {"entry_id": 999999, "found": False}


def test_an_empty_search_points_the_agent_at_vocabulary_discovery(repo):
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import QuestionTrace

    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), lambda _e: None)}
    text = tools["search_entries"].invoke({"property": "nothing matches this"})
    # Distinguishing "absent" from "worded differently" is the whole point of the
    # message; without it the agent concludes the corpus has nothing.
    assert "list_values" in text


def test_an_empty_vocabulary_lookup_says_the_corpus_has_nothing_under_that_wording(repo):
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import QuestionTrace

    tools = {t.name: t for t in build_tools(repo, QuestionTrace("q"), lambda _e: None)}
    text = tools["list_values"].invoke({"field": "organism", "contains": "Drosophila"})
    assert "nothing under that wording" in text


# -- dimensional compatibility at the point of decision --------------------


def test_a_search_spanning_kinds_of_quantity_says_so_in_the_tool_result(repo, config, tmp_path):
    """The system prompt already forbids presenting a mass and a count as one range.
    This is the same rule where the decision is made, against the rows it applies to
    -- an instruction read before the question is not a control."""
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import start_question

    search = next(
        t for t in build_tools(repo, start_question(), lambda e: None) if t.name == "search_entries"
    )
    spanning = search.func(organism="e. coli")
    assert "different kinds of quantity" in spanning
    assert "must not be presented as a range or an average" in spanning

    # And silent when every row measures the same kind, or it becomes boilerplate
    # the model learns to skip.
    assert "different kinds of quantity" not in search.func(property="Cell diameter")


def test_an_answer_citing_a_mass_and_a_count_is_shown_the_mismatch(repo, config, tmp_path):
    """End to end, on the pair the requirement names: mass in micrograms against a
    ribosome count. The check is on the units, so it holds whatever the prose says."""
    from scinumbers_ask.cli import render as render_event
    from scinumbers_ask.events import AnswerEntries

    model = scripted(
        tool_call("search_entries", organism="e. coli"),
        says("Values range from 25 (BNID 100030) to 72000 (BNID 100020)."),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "how big is it?"))
    entries = next(e for e in events if isinstance(e, AnswerEntries))
    assert 100030 in entries.cited and 100020 in entries.cited

    table = render_event(entries, repo=repo)
    assert "2 kinds of quantity" in table
    assert "dimensionless, mass" in table


def test_the_bound_is_the_conversation_size_not_the_number_of_turns(
    repo, config, tmp_path, monkeypatch
):
    """A message is a poor proxy: a retrieved entry's payload runs from 16
    characters to 8,023 across the corpus, so the same turn count can be a few
    thousand tokens or a hundred thousand."""
    from scinumbers_ask.agent import _conversation_size

    reported = _conversation_size({"prompt_tokens": 9_000}, ["ignored", "messages"])
    assert reported == 9_000, "the provider's own figure was not preferred"


def test_a_conversation_nobody_has_measured_is_counted_rather_than_called_empty(
    repo, config, tmp_path
):
    """A provider reporting no usage would otherwise leave the bound at zero for
    ever -- a limit that can never be reached, which is the failure this project
    has already met from the other side."""
    from langchain_core.messages import AIMessage, HumanMessage

    from scinumbers_ask.agent import _conversation_size

    messages = [HumanMessage(content="how wide is a cell?" * 200), AIMessage(content="a" * 4000)]
    counted = _conversation_size({}, messages)

    assert counted > 0, "an unmeasured conversation was treated as empty"
    assert _conversation_size({}, []) == 0


def test_the_conversation_bound_stops_a_session_that_is_too_large(
    repo, config, tmp_path, monkeypatch
):
    from scinumbers_ask.events import ConversationWarning

    monkeypatch.setattr("scinumbers_ask.agent.CONVERSATION_BOUND", 10)
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")))
    list(agent.ask("s", "first"))

    events = list(agent.ask("s", "second"))
    end = events[-1]

    assert end.reason is EndReason.CONVERSATION_BOUND
    assert end.incomplete is True
    assert not any(isinstance(e, ConversationWarning) for e in events), "warned as it refused"


# -- 8.7: the model is told what the source did not claim -----------------


@pytest.fixture
def hedged_repo():
    """One entry whose source said `<8`, stored as the interval [8, 8]."""
    from scinumbers_ask.corpus import Entry
    from scinumbers_ask.repository import CorpusRepository

    return CorpusRepository(
        (
            Entry(
                entry_id=1,
                property="Minimal inhibitory concentration",
                organism="E. coli",
                units="mg/L",
                value=None,
                range_low=8.0,
                range_high=8.0,
                reference="r",
                reference_pubmed_id=None,
                measurement_method="",
                comments="",
                keywords=(),
                range_qualified=True,
            ),
        )
    )


@pytest.fixture
def fused_repo():
    """One entry whose bounds may be two different quantities."""
    from scinumbers_ask.corpus import Entry
    from scinumbers_ask.repository import CorpusRepository

    return CorpusRepository(
        (
            Entry(
                entry_id=2,
                property="Cell width",
                organism="E. coli",
                units="um",
                value=None,
                range_low=0.5,
                range_high=72.0,
                reference="r",
                reference_pubmed_id=None,
                measurement_method="",
                comments="",
                keywords=(),
                range_fused=True,
            ),
        )
    )


def entry_text(repo, entry_id: int) -> str:
    """What `get_entry` actually hands the model."""
    from scinumbers_ask.tools import build_tools
    from scinumbers_ask.trace import QuestionTrace

    tools = build_tools(repo, emit=lambda _e: None, trace=QuestionTrace("q", "run"))
    get_entry = next(t for t in tools if t.name == "get_entry")
    return get_entry.invoke({"entry_id": entry_id})


def test_the_model_is_told_when_the_source_stated_a_bound(hedged_repo):
    """The prose is what people read. A model that only sees "8.0" states it as a
    measurement while the table alone contradicts it -- which is exactly what
    happened live: "the minimal inhibitory concentration is 8.0 mg/L", table
    agreeing, nothing on the page dissenting.

    Given as an instruction, not as `range_qualified: true`: a flag is something the
    model may act on, a sentence saying what the source did claim is harder to round
    away.
    """
    text = entry_text(hedged_repo, 1)
    assert "caution:" in text
    assert "bound" in text and "not a measured quantity" not in text
    assert "do not report this number as a measured quantity" in text
    # Still returned in full and still citable: a citation claims provenance, and
    # that stays true of an entry whose value the source hedged.
    assert "entry_id: 1" in text and "reference:" in text


def test_the_model_is_told_separately_about_a_fused_range(fused_repo):
    text = entry_text(fused_repo, 2)
    assert "may have been taken from different" in text
    assert "do not report this number as a measured quantity" not in text


def test_an_entry_the_source_stated_plainly_carries_no_caution(repo):
    assert "caution:" not in entry_text(repo, 100002)


# -- 8.9 and 8.10: bounded retrieval, and refusing only after looking ------


def test_retrieval_stops_at_its_own_bound_not_at_the_model_call_limit(repo, config, tmp_path):
    """The two are different quantities and neither bounds the other. A model
    batches tool calls into one hop, so twelve model calls bought twenty-nine
    retrievals in one observed question -- $0.27, a fifth of the run budget, with
    the spend ceiling as the only brake."""
    monkeypatch_limit = 3
    from scinumbers_ask import agent as agent_module

    original = agent_module.TOOL_CALL_LIMIT
    agent_module.TOOL_CALL_LIMIT = monkeypatch_limit
    try:
        model = scripted(
            batched_tool_calls(
                ("search_entries", {"property": "Cell"}),
                ("search_entries", {"property": "Volume"}),
                ("search_entries", {"property": "Mass"}),
                ("search_entries", {"property": "Length"}),
                ("search_entries", {"property": "Width"}),
            ),
            says("about 1 micrometre (BNID 100002)"),
        )
        events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    finally:
        agent_module.TOOL_CALL_LIMIT = original

    declined = [e for e in events if isinstance(e, Retrieval) and e.detail.get("declined")]
    assert declined, "every call ran; the bound did nothing"
    end = events[-1]
    assert end.at_tool_bound, "the ending must say retrieval ran out, not merely end"
    assert end.reason is EndReason.ANSWERED, (
        "exhaustion is returned to the model, not raised: what was found so far is "
        "still worth presenting with its citations"
    )


def test_a_declined_call_is_still_reported_as_something_that_happened(repo, config, tmp_path):
    """A call the model made and was refused is part of what happened to the
    question, so it belongs in the progress a reader sees and in the count."""
    from scinumbers_ask.tools import ToolBudget, build_tools
    from scinumbers_ask.trace import QuestionTrace

    seen = []
    tools = build_tools(repo, QuestionTrace("q", "run"), seen.append, ToolBudget(1))
    search = next(t for t in tools if t.name == "search_entries")
    assert "Cell" in search.invoke({"property": "Cell"})
    second = search.invoke({"property": "Cell"})
    assert "No retrieval calls remain" in second
    assert "Answer now from the entries you have already retrieved" in second
    assert seen[-1].detail.get("declined")


def test_an_answer_with_no_retrieval_behind_it_is_reported(repo, config, tmp_path):
    """ "Not in the corpus" and "not looked for" are different statements, and a
    reader cannot tell them apart from the answer."""
    from scinumbers_ask.events import UngroundedRefusal

    model = scripted(says("I could not find anything about that in the corpus."))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    refusal = next(e for e in events if isinstance(e, UngroundedRefusal))
    assert not refusal.claimed_searching
    assert events[-1].tool_calls == 0, "the count is the evidence"


def test_an_answer_claiming_searches_it_never_made_is_reported_as_such(repo, config, tmp_path):
    """Observed live: zero tool calls, prose reading "based on my searches through
    the available data". The harness had the truth and the answer did not."""
    from scinumbers_ask.events import UngroundedRefusal

    model = scripted(says("Based on my searches through the available data, this is not covered."))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    assert next(e for e in events if isinstance(e, UngroundedRefusal)).claimed_searching


def test_an_answer_that_searched_is_not_reported(repo, config, tmp_path):
    from scinumbers_ask.events import UngroundedRefusal

    model = scripted(
        tool_call("search_entries", property="nothing at all"),
        says("I could not find it."),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    assert not any(isinstance(e, UngroundedRefusal) for e in events)
