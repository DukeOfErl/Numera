"""Spend control against a real provider, at the smallest limits that mean anything.

The offline spend suite proves the arithmetic and the wiring: a scripted model
returns a scripted cost, and the gate does the right thing with it. What it cannot
prove is the part that costs money. Every offline assertion about a limit rests on
a double reporting cost in the shape the provider used *once*, and on a gate whose
refusal is only ever observed as an ending reason rather than as a request that
never left. Both can stop being true without a single test going red, and the bill
is where anyone would find out. That is what this module is for.

Five properties, each of which a green offline suite is compatible with being
broken:

1. A limit reached in a real run actually stops a *dispatch* -- the provider is
   never asked again. Counted at the provider boundary, not inferred from an
   ending reason.
2. A real response is priced from what the provider reported, not from the
   fallback table standing in for it. This is the one the others rest on, and the
   two figures are numerically identical, so only removing the table can tell.
3. The overshoot past a ceiling is at most one request. The gate checks before
   dispatching, so this is the real guarantee, and it is the one a bill reflects.
4. Spend recorded by a real request stops the next question in another agent
   instance, through the persisted run ledger.
5. The ceiling a session was created with survives a real checkpoint round-trip,
   so a resumed conversation cannot be handed a bigger budget.

**Cost.** About $0.01 in total, eight or so requests on the six-entry fixture with
the development model. The limits are the smallest that still exercise the thing
under test: one micro-dollar where the point is "stops after the first request",
and a few thousand where the point is "stops part-way through a question".

**What bounds a bug in these tests.** Every configuration here carries a run
budget, and the run budget is enforced by the code under test -- so the worst case
of a test that loops is its own budget plus one request. The module-scoped `spent`
fixture adds a second, independent bound: it sums what each test really spent and
fails if the module went past MODULE_CAP, which would catch the case where the
mechanism these tests exist to check is the thing that broke.

Excluded by default via the `network` marker. To run it:

    OPENROUTER_API_KEY=... uv run pytest -m network tests/test_live_spend.py
"""

from __future__ import annotations

import logging
import os

import pytest
from langchain_core.callbacks import BaseCallbackHandler

from bionumbers_ask import run_ledger
from bionumbers_ask.agent import RUN_CALL_LIMIT, AskAgent, default_model
from bionumbers_ask.config import Config, format_usd, usd
from bionumbers_ask.events import Answer, EndReason, QuestionEnded, Retrieval
from bionumbers_ask.trace import LOGGER_NAME

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="set OPENROUTER_API_KEY to run the live spend checks",
    ),
]

# The most this module may spend before it stops trusting its own subject matter.
# Roughly five times what it costs when everything works.
MODULE_CAP = usd("0.05")

# A safety net on every test here, not a limit under test: high enough that no
# assertion depends on it, low enough that a test which somehow looped could not
# spend meaningfully before the code under test stopped it.
SAFETY_BUDGET = usd("0.02")

# A question that cannot be answered without retrieving, so answering it takes at
# least two model calls: one to choose a tool, one to use what came back. A
# question the model could answer in a single call would end before any limit was
# reached, and the test would pass without testing anything.
NEEDS_RETRIEVAL = "How wide is an E. coli cell?"
# Two entries for `Cell diameter` differing by organism alone, which the prompt
# requires be reported with what distinguishes them -- so this question searches
# several times rather than once.
NEEDS_SEVERAL_CALLS = "How wide is a cell, in micrometres?"


@pytest.fixture(autouse=True)
def _real_retry_delay(monkeypatch):
    """Undo the offline suite's zeroed backoff.

    The conftest fixture is right for doubles and wrong here: retrying a real
    provider with no delay turns one rate-limited request into three failed ones,
    which is both rude and enough to break the dispatch counts these tests are
    built on.
    """
    monkeypatch.setattr("bionumbers_ask.agent.RETRY_INITIAL_DELAY", 1.0)


class Dispatches(BaseCallbackHandler):
    """Counts requests that actually reached the provider.

    The point of a spend gate is that the request is never issued, and no ending
    reason can prove that -- a question that simply finished looks the same from
    the outside. This counts at the boundary: the callback fires when the model
    client starts a request, and the gate raises before calling the handler, so a
    declined request never appears here.
    """

    def __init__(self) -> None:
        self.calls = 0

    def on_chat_model_start(self, *args, **kwargs) -> None:
        self.calls += 1


class Increments(logging.Handler):
    """The per-request charges the gate recorded, read off the trail.

    Taken from the trace rather than from a callback because it is the trail a
    person reads to explain a bill; if these numbers are wrong there, nothing
    downstream is right either.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.charges: list[int] = []
        self.declines: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, "fields", {}) or {}
        if record.getMessage() == "spend.increment":
            self.charges.append(int(fields["increment"]))
        elif record.getMessage() == "spend.gate_declined":
            self.declines.append(dict(fields))


@pytest.fixture
def trail() -> Increments:
    handler = Increments()
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


@pytest.fixture(scope="module")
def spent():
    """Independent tally of what this module really spent.

    Independent of the per-test budgets on purpose: those are enforced by the code
    under test, so if that code is broken they bound nothing. This reads the run
    ledger, which is written per charge, and fails the module if the total ran
    away.
    """

    class Tally:
        def __init__(self) -> None:
            self.total = 0

        def record(self, path: str, run: str) -> int:
            micro = run_ledger.read(path, run)
            self.total += micro
            return micro

    tally = Tally()
    yield tally
    # Reported either way: what these tests cost is a number worth watching drift
    # in, and it is invisible unless something prints it.
    print(f"\nlive spend tests: {format_usd(tally.total)} across the module")
    assert tally.total < MODULE_CAP, (
        f"this module spent {format_usd(tally.total)}, past its {format_usd(MODULE_CAP)} cap"
    )


def live_agent(repo, config: Config, path: str, watcher: Dispatches) -> AskAgent:
    """A real agent on the real model, with requests counted at the boundary.

    Built through `default_model` rather than by constructing a client here, so
    what is under test is the model the application actually uses -- including its
    base URL and credentials -- and not a lookalike.
    """
    model = default_model(config)
    model.callbacks = [watcher]
    return AskAgent(repo, config, path, model=model)


def ended(events) -> QuestionEnded:
    return next(e for e in events if isinstance(e, QuestionEnded))


def test_the_ceiling_a_person_configures_declines_a_real_second_request(
    repo, tmp_path, monkeypatch, spent, trail
):
    """The headline: environment to refused dispatch, with real money in between.

    Configured through `Config.from_env`, because the number a person sets in the
    environment is the number that has to stop the work -- a test that constructed
    a Config directly would leave the path they actually use unproven.

    One micro-dollar is the smallest ceiling that means anything: the gate checks
    before dispatching and spend starts at zero, so the first request always goes
    out, and every request after it must not.
    """
    monkeypatch.setenv("BIONUMBERS_ASK_QUESTION_CEILING_USD", "0.000001")
    monkeypatch.setenv("BIONUMBERS_ASK_RUN_BUDGET_USD", "0.02")
    monkeypatch.setenv("BIONUMBERS_ASK_RUN", "live-ceiling")
    config = Config.from_env()
    path = str(tmp_path / "ceiling.sqlite")

    watcher = Dispatches()
    events = list(live_agent(repo, config, path, watcher).ask("live-ceiling", NEEDS_RETRIEVAL))
    end = ended(events)

    assert end.reason is EndReason.SPEND_CEILING, f"ended as {end.reason}"
    assert end.incomplete is True
    assert watcher.calls == 1, (
        f"{watcher.calls} requests reached the provider under a one-micro-dollar ceiling"
    )
    assert end.model_calls < RUN_CALL_LIMIT, "the retrieval bound stopped this, not the gate"

    # The loop wanted to continue. Without this the assertion above is satisfied by
    # a question that happened to finish in one call, which proves nothing.
    assert any(isinstance(e, Retrieval) for e in events), (
        "the question never retrieved, so nothing wanted a second request"
    )

    # A real cost. Zero here would mean the ledger read nothing and every limit in
    # the system holds only because nothing ever accumulates. Where the figure came
    # from -- the provider's report or the fallback table -- is the next test's job.
    assert end.spend > 0, "nothing was charged for a request the provider billed"

    # The question ended by raising, and the charge was still recorded. A crash
    # loop that did not bill would be free to run for ever.
    assert spent.record(path, "live-ceiling") == end.run_spend == end.spend

    # And the trail says why, with both figures, since this is what someone reads
    # when they want to know where a bill came from.
    assert trail.declines, "the gate declined a request without recording it"
    assert trail.declines[-1]["reason"] == EndReason.SPEND_CEILING.value
    assert trail.declines[-1]["limit"] == 1
    assert trail.declines[-1]["spent"] == end.spend


def test_a_real_response_is_priced_from_the_provider_and_not_from_the_table(repo, tmp_path, spent):
    """The claim the whole module rests on: the provider still reports cost.

    Every other test would survive OpenRouter renaming that field, because the
    development model has fallback prices configured and the ledger would quietly
    price from the table instead -- accurate only until the provider reprices, and
    blind to cache reads and writes. The two figures matched exactly when the table
    was written, so no assertion on the amount can tell them apart.

    Configured with no prices at all, so there is no table to fall back to: a
    response the provider did not price raises `Unpriceable` and the question ends
    as NOT_CONFIGURED. Ending on the ceiling instead is the proof.
    """
    config = Config(
        model="anthropic/claude-haiku-4.5",
        question_ceiling=usd("0.000001"),
        run_budget=SAFETY_BUDGET,
        prices={},
        run_label="live-priced",
    )
    path = str(tmp_path / "priced.sqlite")

    watcher = Dispatches()
    end = ended(list(live_agent(repo, config, path, watcher).ask("priced", NEEDS_RETRIEVAL)))

    assert end.reason is EndReason.SPEND_CEILING, (
        f"ended as {end.reason}: with no prices configured, this means the provider "
        "no longer reports cost where the ledger reads it"
    )
    assert end.spend > 0, "a provider-reported cost of nothing for a billed request"
    assert watcher.calls == 1
    spent.record(path, "live-priced")


def test_the_overshoot_past_a_ceiling_is_one_request_at_most(repo, tmp_path, spent, trail):
    """What a ceiling actually promises, stated in money.

    The gate cannot know what a request will cost until it has been billed, so
    spend can pass the ceiling by exactly the request in flight -- and no further.
    Asserted from the recorded charges rather than against a fixed figure, so it
    holds whatever the model charges on the day: the total before the last charge
    must still be under the ceiling.

    The ceiling is chosen to fall between one request and a whole question: about
    $0.003, against roughly $0.0007 for a first request and $0.01 for a question
    that runs to five calls (measured 2026-08-19). If the model gets dear enough
    that a single request passes it, this test says so rather than passing quietly.
    """
    ceiling = usd("0.003")
    config = Config(
        model="anthropic/claude-haiku-4.5",
        question_ceiling=ceiling,
        run_budget=SAFETY_BUDGET,
        run_label="live-overshoot",
    )
    path = str(tmp_path / "overshoot.sqlite")

    watcher = Dispatches()
    events = list(
        live_agent(repo, config, path, watcher).ask("live-overshoot", NEEDS_SEVERAL_CALLS)
    )
    end = ended(events)

    assert end.reason is EndReason.SPEND_CEILING, (
        f"ended as {end.reason} having spent {format_usd(end.spend)} of "
        f"{format_usd(ceiling)}; the ceiling may need lowering"
    )
    assert len(trail.charges) >= 2, (
        "a single request passed the ceiling, so this run never crossed it part-way "
        "through a question; raise the ceiling"
    )

    # Every dispatched request was priced. A dispatch with no charge behind it is
    # spend the gate cannot see, which is the one accounting failure that lets a
    # limit be passed without bound.
    assert watcher.calls == len(trail.charges), (
        f"{watcher.calls} requests reached the provider but {len(trail.charges)} were priced"
    )

    assert sum(trail.charges) == end.spend, "the charges do not add up to the reported spend"
    assert sum(trail.charges[:-1]) < ceiling, (
        "the ceiling was already passed before the last request was dispatched"
    )
    assert end.spend <= ceiling + max(trail.charges), (
        f"overshot the {format_usd(ceiling)} ceiling by more than one request: "
        f"{format_usd(end.spend)}"
    )

    # Work already paid for is presented rather than discarded.
    assert next(e for e in events if isinstance(e, Answer)).text.strip()
    spent.record(path, "live-overshoot")


def test_spend_from_a_real_request_stops_the_next_question_in_a_new_agent(repo, tmp_path, spent):
    """The run budget across agent instances, which is what an evaluation is.

    A run is not a session and not a process: a driver opening a session per
    question must still be bounded by one figure. The second question here is
    asked by a fresh agent over a fresh session, and must be refused before
    anything is dispatched -- asserted by the dispatch count not moving, which is
    the only thing that distinguishes "refused" from "answered cheaply".

    One micro-dollar again, for the same reason as the ceiling: it is the smallest
    budget that leaves the first request billable and every later one refused.
    """
    config = Config(
        model="anthropic/claude-haiku-4.5",
        question_ceiling=usd("0.60"),
        run_budget=usd("0.000001"),
        run_label="live-budget",
    )
    path = str(tmp_path / "budget.sqlite")

    first_watcher = Dispatches()
    first = ended(list(live_agent(repo, config, path, first_watcher).ask("s1", NEEDS_RETRIEVAL)))
    assert first.reason is EndReason.RUN_BUDGET, (
        f"the run budget did not outrank the {format_usd(config.question_ceiling)} ceiling: "
        f"ended as {first.reason}"
    )
    assert first_watcher.calls == 1, f"{first_watcher.calls} requests under a one-micro budget"
    billed = spent.record(path, "live-budget")
    assert billed == first.run_spend > 0

    second_watcher = Dispatches()
    events = list(live_agent(repo, config, path, second_watcher).ask("s2", NEEDS_RETRIEVAL))
    second = ended(events)

    assert second_watcher.calls == 0, "a question was dispatched past the run budget"
    assert second.reason is EndReason.RUN_BUDGET
    assert second.spend == 0 and second.run_spend == billed
    # It says what to do about it, and the refusal is the thing a person meets.
    assert "Raise the budget" in next(e for e in events if isinstance(e, Answer)).text


def test_a_session_resumed_live_keeps_the_ceiling_it_was_created_with(repo, tmp_path, spent):
    """A real checkpoint round-trip, because that is where this could quietly fail.

    The offline suite proves the value is read back from state. Live, the state has
    been through SQLite, written by one process's run and read by another's, and a
    ceiling lost in that round-trip is a session silently handed the configured
    budget instead of its own -- which is a bill, not a test failure.
    """
    path = str(tmp_path / "resume.sqlite")
    tight = Config(
        model="anthropic/claude-haiku-4.5",
        question_ceiling=usd("0.000001"),
        run_budget=SAFETY_BUDGET,
        run_label="live-resume",
    )

    watcher = Dispatches()
    first = ended(list(live_agent(repo, tight, path, watcher).ask("resumed", NEEDS_RETRIEVAL)))
    assert first.reason is EndReason.SPEND_CEILING
    assert first.spend_ceiling == 1, "the ending did not carry the ceiling it ran against"
    assert watcher.calls == 1

    # A generous ceiling, and the session must refuse to take it.
    generous = Config(
        model=tight.model,
        question_ceiling=usd("0.50"),
        run_budget=SAFETY_BUDGET,
        run_label="live-resume",
    )
    resumed_watcher = Dispatches()
    second = ended(
        list(live_agent(repo, generous, path, resumed_watcher).ask("resumed", NEEDS_RETRIEVAL))
    )

    assert second.reason is EndReason.SPEND_CEILING, (
        f"the resumed session took the new {format_usd(generous.question_ceiling)} ceiling"
    )
    assert second.spend_ceiling == 1
    assert resumed_watcher.calls == 1, (
        f"{resumed_watcher.calls} requests on resumption under the session's own ceiling"
    )
    spent.record(path, "live-resume")
