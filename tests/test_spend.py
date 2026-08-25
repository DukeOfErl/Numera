"""Spend control: the ledger, the gate in the dispatch path, and the projection.

The gate is the point of this group. An instruction to the model to stay within
budget is a preference; declining to dispatch a request is a limit. These tests
check the limit rather than the preference -- several of them assert on how many
times the model was called, because that is what "not dispatched" means.
"""

from __future__ import annotations

import pytest
from conftest import agent_with
from langchain_core.messages import AIMessage, ToolMessage

from agent_doubles import (
    OPENROUTER_RESPONSE_METADATA,
    costing,
    reports_usage_only,
    says,
    scripted,
    tool_call,
)
from bionumbers_ask.agent import RUN_CALL_LIMIT, AskAgent
from bionumbers_ask.config import FALLBACK_PRICES, Config, ModelPrices, usd
from bionumbers_ask.events import (
    Answer,
    CostProjection,
    EndReason,
    QuestionEnded,
    SpendWarning,
)
from bionumbers_ask.spend import (
    SpendLedger,
    SpendLimitReached,
    Unpriceable,
    project_question_cost,
)

# 100 micro-dollars, so the derived ceiling is 120. Costs in these tests are chosen
# relative to those two figures.
THRESHOLD = usd("0.000100")
CEILING = 120


@pytest.fixture
def tight(config) -> Config:
    """The same configuration with a threshold small enough to reach in a test."""
    return Config(
        model=config.model,
        warning_threshold=THRESHOLD,
        run_budget=usd("1.20"),
        prices=config.prices,
    )


def ended(events) -> QuestionEnded:
    return next(e for e in events if isinstance(e, QuestionEnded))


# -- the ledger -----------------------------------------------------------


def test_configured_prices_price_a_response_that_reports_usage_but_no_cost():
    """The fallback path, which no provider we use actually takes.

    OpenRouter reports cost, so nothing in normal operation exercises this. It is
    the branch that would be silently wrong the day a provider stopped.
    """
    ledger = SpendLedger(model="m", prices=ModelPrices(1_000_000, 5_000_000))
    ledger.add_response([reports_usage_only("ok", input_tokens=1_000, output_tokens=100)])
    # 1000 in at 1 USD/MTok plus 100 out at 5 USD/MTok = 0.0015 USD.
    assert ledger.question == 1_500


def test_reported_cost_wins_over_configured_prices():
    """Prices are a spare, not a second opinion.

    A ledger that preferred the table would drift the moment the provider
    repriced, and would miss cache reads and writes entirely.
    """
    ledger = SpendLedger(model="m", prices=ModelPrices(9_000_000, 9_000_000))
    message = AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA)
    ledger.add_response([message])
    assert ledger.question == 34, "the table was consulted when a cost was reported"


def test_a_response_reporting_neither_cost_nor_usage_stops_the_run():
    ledger = SpendLedger(model="some/model", prices=ModelPrices(1, 1))
    with pytest.raises(Unpriceable, match="some/model"):
        ledger.add_response([AIMessage(content="ok")])


def test_usage_without_configured_prices_stops_the_run():
    ledger = SpendLedger(model="some/model", prices=None)
    with pytest.raises(Unpriceable, match="some/model"):
        ledger.add_response([reports_usage_only("ok", input_tokens=10, output_tokens=1)])


def test_a_tool_message_in_a_response_is_not_priced():
    """The framework returns one alongside a structured-output response.

    Pricing it would raise Unpriceable over a message that never cost anything,
    ending a working question as a configuration failure.
    """
    ledger = SpendLedger(model="m", prices=None)
    ledger.add_response(
        [
            AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA),
            ToolMessage(content="{}", tool_call_id="c1"),
        ]
    )
    assert ledger.question == 34


def test_the_two_counters_move_together_but_start_differently():
    """A resumed session carries its run total; its question total starts at zero."""
    ledger = SpendLedger(model="m", prices=None, run_spend=500)
    ledger.add_response([AIMessage(content="ok", response_metadata=OPENROUTER_RESPONSE_METADATA)])
    assert (ledger.question, ledger.run) == (34, 534)


# -- the gate -------------------------------------------------------------


def test_the_gate_stops_dispatching_once_the_ceiling_is_reached(repo, tight, tmp_path):
    """The ceiling, not the call limit, is what stops this question.

    Asserting on the model's call count is the point: "not dispatched" is a claim
    about the provider never being asked, which an ending reason alone would not
    prove.
    """
    model = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_200))
    end = ended(list(agent_with(repo, tight, tmp_path, model).ask("s", "q")))

    assert end.reason is EndReason.SPEND_CEILING
    assert end.incomplete is True
    assert end.spend == 200, "the request that crossed the ceiling is counted at its real cost"
    assert model.attempts == 1, (
        f"the model was called {model.attempts} times after the ceiling was reached"
    )
    assert model.attempts < RUN_CALL_LIMIT, "the call limit stopped this, not the spend gate"


def test_a_question_stopped_on_its_ceiling_presents_what_it_established(repo, tight, tmp_path):
    """Work already paid for is not thrown away."""
    partial = AIMessage(
        content="So far: an E. coli cell is about 1 micrometre wide (BNID 100002).",
        tool_calls=[{"name": "search_entries", "args": {"property": "Cell"}, "id": "call-1"}],
    )
    model = scripted(costing(partial, 0.000_200))
    events = list(agent_with(repo, tight, tmp_path, model).ask("s", "q"))

    answer = next(e for e in events if isinstance(e, Answer))
    assert "BNID 100002" in answer.text
    assert ended(events).reason is EndReason.SPEND_CEILING
    assert ended(events).incomplete is True


def test_a_ceiling_reached_before_anything_was_established_still_answers(repo, tight, tmp_path):
    """An empty ending would leave a driver with nothing to render."""
    model = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_200))
    events = list(agent_with(repo, tight, tmp_path, model).ask("s", "q"))
    answer = next(e for e in events if isinstance(e, Answer))
    assert "spend limit" in answer.text


def test_the_warning_fires_past_the_threshold_and_work_continues(repo, tight, tmp_path):
    """Threshold is notice; ceiling is the stop. 110 micro is past one, not the other."""
    model = scripted(
        costing(tool_call("search_entries", property="Cell"), 0.000_110),
        costing(says("about 1 micrometre (BNID 100002)"), 0.000_005),
    )
    events = list(agent_with(repo, tight, tmp_path, model).ask("s", "q"))

    warning = next(e for e in events if isinstance(e, SpendWarning))
    assert warning.spent == 110
    assert warning.threshold == THRESHOLD
    end = ended(events)
    assert end.reason is EndReason.ANSWERED, "the warning ended the question"
    assert end.spend == 115


def test_the_warning_is_emitted_once_per_question(repo, tight, tmp_path):
    model = scripted(
        costing(tool_call("search_entries", property="Cell"), 0.000_110),
        costing(tool_call("get_entry", bnid=100002), 0.000_002),
        costing(says("about 1 micrometre (BNID 100002)"), 0.000_002),
    )
    events = list(agent_with(repo, tight, tmp_path, model).ask("s", "q"))
    assert len([e for e in events if isinstance(e, SpendWarning)]) == 1


def test_a_spend_warning_is_not_counted_as_a_tool_call(repo, tight, tmp_path):
    """Retrievals and warnings share one queue, and only one of them is a tool call."""
    model = scripted(
        costing(tool_call("search_entries", property="Cell"), 0.000_110),
        costing(says("about 1 micrometre (BNID 100002)"), 0.000_002),
    )
    events = list(agent_with(repo, tight, tmp_path, model).ask("s", "q"))
    assert any(isinstance(e, SpendWarning) for e in events)
    assert ended(events).tool_calls == 1


def test_the_retry_predicate_excludes_the_gate_and_unpriceable_responses():
    """The retry middleware's default is to retry every Exception.

    Retrying the gate's own refusal sleeps through the full backoff and then fails
    anyway; retrying an unpriceable response will not make a provider start
    reporting cost.
    """
    from bionumbers_ask.agent import _retry_on

    assert _retry_on(SpendLimitReached(EndReason.SPEND_CEILING, 200, 120)) is False
    assert _retry_on(Unpriceable("no cost")) is False
    assert _retry_on(RuntimeError("upstream unavailable")) is True


def test_declining_at_the_ceiling_does_not_sleep_through_the_backoff(
    repo, tight, tmp_path, monkeypatch
):
    """The predicate wired in, measured end to end.

    The autouse fixture zeroes the retry delay, which would make this pass whether
    the refusal were retried or not, so a real delay is restored here. Two retries
    at an initial delay of 1s and a backoff factor of 2 would take about 3s.
    """
    import time

    monkeypatch.setattr("bionumbers_ask.agent.RETRY_INITIAL_DELAY", 1.0)
    model = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_200))
    agent = AskAgent(repo, tight, str(tmp_path / "r.sqlite"), model=model)

    started = time.monotonic()
    end = ended(list(agent.ask("s", "q")))
    elapsed = time.monotonic() - started

    assert end.reason is EndReason.SPEND_CEILING
    assert elapsed < 1.0, f"the refusal was retried with backoff ({elapsed:.1f}s)"


# -- per-question versus per-run -----------------------------------------


def test_a_second_question_gets_a_fresh_ceiling_while_run_spend_accumulates(repo, tight, tmp_path):
    model = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000_110))
    agent = agent_with(repo, tight, tmp_path, model)

    first = ended(list(agent.ask("s", "q1")))
    second = ended(list(agent.ask("s", "q2")))

    assert first.reason is second.reason is EndReason.ANSWERED
    assert second.spend == 110, "the per-question ceiling did not reset"
    assert (first.run_spend, second.run_spend) == (110, 220), "run spend did not accumulate"


def test_the_run_budget_refuses_the_next_question_before_dispatching(repo, config, tmp_path):
    budgeted = Config(model=config.model, warning_threshold=usd("0.50"), run_budget=usd("0.000200"))
    model = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000_110))
    agent = agent_with(repo, budgeted, tmp_path, model)

    assert ended(list(agent.ask("s", "q1"))).reason is EndReason.ANSWERED
    assert ended(list(agent.ask("s", "q2"))).reason is EndReason.ANSWERED
    calls_before = model.attempts

    third = ended(list(agent.ask("s", "q3")))
    assert third.reason is EndReason.RUN_BUDGET
    assert third.run_spend == 220
    assert model.attempts == calls_before, "a question was dispatched past the run budget"


def test_the_run_budget_can_end_a_question_part_way(repo, config, tmp_path):
    """The run budget outranks the per-question ceiling when both would trip.

    Its threshold is set well above what this question spends, so an ending of
    SPEND_CEILING here would mean the wrong limit was reported.
    """
    budgeted = Config(model=config.model, warning_threshold=usd("0.50"), run_budget=usd("0.000150"))
    model = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_110))
    end = ended(list(agent_with(repo, budgeted, tmp_path, model).ask("s", "q")))

    assert end.reason is EndReason.RUN_BUDGET
    assert end.spend == 220 and end.run_spend == 220


def test_the_ceiling_a_session_was_created_with_is_the_one_it_keeps(repo, tight, tmp_path):
    """A session resumed under a larger configured ceiling keeps its own.

    Otherwise an environment change between two processes would silently hand a
    conversation already under way a bigger budget.
    """
    path = str(tmp_path / "keep.sqlite")
    cheap = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000_010))
    assert ended(list(AskAgent(repo, tight, path, model=cheap).ask("s", "q1"))).spend == 10

    generous = Config(model=tight.model, warning_threshold=usd("0.010"), run_budget=usd("1.20"))
    expensive = scripted(costing(tool_call("search_entries", property="Cell"), 0.000_200))
    end = ended(list(AskAgent(repo, generous, path, model=expensive).ask("s", "q2")))

    assert end.reason is EndReason.SPEND_CEILING, (
        f"the session took the new configuration's ceiling; spent {end.spend} of {CEILING}"
    )


def test_the_run_total_and_the_ceiling_are_readable_without_a_model(repo, tight, tmp_path):
    """A driver deciding whether to offer another question needs both, and building
    an agent to ask would read the API key from the environment for a question that
    needs no model at all."""
    from dataclasses import replace

    model = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000_110))
    agent = agent_with(repo, tight, tmp_path, model)
    list(agent.ask("s", "q"))
    assert agent.run_spend() == 110

    # Keyed on the run, so another run over the same file starts at nothing. The
    # ceiling stays with the session, which is why it is read per session.
    other_run = AskAgent(repo, replace(tight, run_label="other"), agent._checkpoint_path)
    assert other_run.run_spend() == 0


# -- accounting failures --------------------------------------------------


def test_a_model_reporting_no_cost_ends_the_question_naming_the_model(repo, config, tmp_path):
    """Spec 5.2: a run that cannot account for its spend has no working control.

    Discovering this needs a response, so the request that reveals it has already
    been billed; what is bounded is every request after it.
    """
    model = scripted(says("about 1 micrometre"), reports_cost=False)
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    end = ended(events)
    assert end.reason is EndReason.NOT_CONFIGURED
    assert end.incomplete is True
    answer = next(e for e in events if isinstance(e, Answer))
    assert config.model in answer.text
    assert model.attempts == 1, "another request was dispatched with spend unaccounted for"


# -- the projection -------------------------------------------------------


def test_the_projection_flags_a_capable_model_but_not_a_cheap_one():
    """It is an upper bound, so it should be quiet on the development model."""
    threshold = usd("0.50")
    cheap = Config(
        model="anthropic/claude-haiku-4.5",
        warning_threshold=threshold,
        run_budget=usd("1.20"),
        prices=dict(FALLBACK_PRICES),
    )
    capable = Config(
        model="anthropic/claude-opus-4.7",
        warning_threshold=threshold,
        run_budget=usd("1.20"),
        prices=dict(FALLBACK_PRICES),
    )
    assert project_question_cost(cheap, "How wide is an E. coli cell?", RUN_CALL_LIMIT) < threshold
    assert (
        project_question_cost(capable, "How wide is an E. coli cell?", RUN_CALL_LIMIT) > threshold
    )


def test_the_projection_is_absent_without_configured_prices(config):
    """Nothing has been dispatched, so provider-reported cost cannot help here."""
    assert project_question_cost(config, "q", RUN_CALL_LIMIT) is None


def test_a_flagged_question_is_still_answered(repo, config, tmp_path, monkeypatch):
    """The projection is an estimate, and the gate acts on measured spend alone."""
    monkeypatch.setattr("bionumbers_ask.agent.project_question_cost", lambda *_: usd("999.00"))
    model = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000_110))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    projection = next(e for e in events if isinstance(e, CostProjection))
    assert projection.projected == usd("999.00")
    end = ended(events)
    assert end.reason is EndReason.ANSWERED, "the projection stopped the work"
    assert end.spend == 110, "the projection was counted as spend"


def test_no_projection_event_when_it_stays_under_the_threshold(repo, config, tmp_path):
    """A flag that fired on every question would be a running commentary."""
    model = scripted(says("about 1 micrometre (BNID 100002)"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    assert not [e for e in events if isinstance(e, CostProjection)]


def test_a_reported_cost_of_zero_is_a_cost_not_a_missing_one():
    """`if cost:` read 0.0 as "nothing reported", fell through to the price table,
    and with no prices configured ended the question unable to account for spend --
    on a call that succeeded and cost nothing. Any free model slug reports this."""
    ledger = SpendLedger(model="free/model", prices=None)
    free = says("answered").model_copy(update={"response_metadata": {"token_usage": {"cost": 0.0}}})
    assert ledger.add_response([free]).micro == 0
    assert ledger.question == 0


def test_a_run_budget_reached_in_one_session_stops_another(repo, tmp_path):
    """The point of keying spend to the run: the budget has to stop the next
    question wherever it is asked, not only in the session that spent the money."""
    from dataclasses import replace

    # Not the default label, so a write that ignored the label would put the spend
    # where this run does not read it and the budget would appear to hold.
    tiny = Config(
        model="fake/model",
        warning_threshold=usd("0.50"),
        run_budget=usd("0.000100"),
        run_label="eval-1",
    )
    spender = scripted(costing(says("about 1 micrometre (BNID 100002)"), 0.000_110))
    first = AskAgent(repo, tiny, str(tmp_path / "c.sqlite"), model=spender)
    assert list(first.ask("session-one", "q"))[-1].reason is EndReason.ANSWERED

    fresh = AskAgent(repo, tiny, str(tmp_path / "c.sqlite"), model=scripted(says("x")))
    end = list(fresh.ask("session-two", "q"))[-1]
    assert end.reason is EndReason.RUN_BUDGET
    assert end.run_spend == 110

    # A different run over the same file is unaffected.
    other = AskAgent(
        repo,
        replace(tiny, run_label="eval-2"),
        str(tmp_path / "c.sqlite"),
        model=scripted(says("x")),
    )
    assert list(other.ask("session-three", "q"))[-1].reason is not EndReason.RUN_BUDGET


def test_spend_is_recorded_as_each_charge_is_made(repo, tmp_path):
    """Not at the end of the question: one that ends by raising must still have its
    spend counted, or a crash loop is free."""
    from bionumbers_ask import run_ledger

    config = Config(model="fake/model", warning_threshold=usd("0.50"), run_budget=usd("1.20"))
    db = str(tmp_path / "c.sqlite")
    model = scripted(
        costing(tool_call("search_entries", property="Cell"), 0.000_110),
        costing(says("about 1 micrometre (BNID 100002)"), 0.000_110),
    )
    list(AskAgent(repo, config, db, model=model).ask("s", "q"))
    assert run_ledger.read(db, "dev") == 220


def test_a_zero_charge_touches_nothing(tmp_path):
    """A model call the provider reported as free is still a call. Writing a zero
    row would create a run in the ledger that had spent nothing, which reads as a run
    that ran."""
    from bionumbers_ask import run_ledger

    db = str(tmp_path / "c.sqlite")
    run_ledger.add(db, "eval-1", 0)
    assert run_ledger.read(db, "eval-1") == 0
    run_ledger.add(db, "eval-1", 110)
    assert run_ledger.read(db, "eval-1") == 110
