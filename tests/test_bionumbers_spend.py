"""Spend: the projection, the provider's report, and the two bounds.

Two kinds of money assertion, and only one of them can catch a repriced table. The dollar figures
worked out by hand from the published $/M rates — `0.6`, `0.23`, `0.5` and `0.05`, each shown as
arithmetic in its test's docstring — do catch it, and so does the rate test below; that is why they
are literals rather than expressions over `PRICES`. Every other assertion composes from `PRICES`,
which pins how a figure is put together and deliberately says nothing about the rates, since a test
that reprices along with the table would ratify whatever the table said.

No figure in this file was copied from a run of the module.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bionumbers.records import Spend
from bionumbers.spend import (
    MODEL,
    PRICES,
    Ceiling,
    CeilingReached,
    Ledger,
    Unpriceable,
    cost,
    count_input_tokens,
    projected_cost,
)

PRICE = PRICES[MODEL]


def usage(**fields):
    """The SDK's usage block: all four fields present, and None unless the test names one.

    None is what the SDK reports for a cache field on a call that used no caching. A field that is
    *absent* is a different case with a different answer, so it has its own tests rather than a
    flag here — a helper that could produce both would hold the distinction constant by default.
    """
    return SimpleNamespace(
        input_tokens=fields.get("input_tokens"),
        cache_creation_input_tokens=fields.get("cache_creation_input_tokens"),
        cache_read_input_tokens=fields.get("cache_read_input_tokens"),
        output_tokens=fields.get("output_tokens"),
    )


def test_the_rates_are_the_ones_the_module_was_written_against():
    """$5 / $25 per million, cache write at 1.25x input, cache read at 0.1x, per token, so
    nothing downstream carries a scaling constant.

    Not "the published ones", which is a claim this file cannot make good on and an earlier
    wording here made anyway. `design.md` corroborates the $5 / $25 pair and nothing reachable
    from this worktree corroborates the two multipliers or the model id; `spend.py`'s docstring
    says so and names what to read before the first paid run. What this test is for is the other
    direction: it fails the moment the table is edited, so the table cannot be repriced without
    that open question being reread.
    """
    assert (PRICE.input, PRICE.output) == (5e-6, 25e-6)
    assert PRICE.cache_write == pytest.approx(1.25 * PRICE.input)
    assert PRICE.cache_read == pytest.approx(0.1 * PRICE.input)


def test_cost_prices_all_four_reported_token_kinds():
    spend = cost(
        MODEL,
        usage(
            input_tokens=100_000,
            cache_creation_input_tokens=20_000,
            cache_read_input_tokens=200_000,
            output_tokens=4_000,
        ),
    )

    assert (spend.input_tokens, spend.cache_write_tokens) == (100_000, 20_000)
    assert (spend.cache_read_tokens, spend.output_tokens) == (200_000, 4_000)
    assert spend.calls == 1
    assert spend.usd == pytest.approx(
        100_000 * PRICE.input
        + 20_000 * PRICE.cache_write
        + 200_000 * PRICE.cache_read
        + 4_000 * PRICE.output
    )


def test_a_cache_read_is_priced_below_the_same_tokens_uncached():
    """The distinction the cached rate exists for: read at 0.1x, not at full input rate."""
    cached = cost(MODEL, usage(cache_read_input_tokens=200_000))
    uncached = cost(MODEL, usage(input_tokens=200_000))

    assert cached.usd == pytest.approx(200_000 * PRICE.cache_read)
    assert cached.usd == pytest.approx(uncached.usd / 10)


def test_unreported_token_fields_cost_nothing():
    """A call that used no caching leaves both cache fields None, and None is not a number to
    multiply by a rate."""
    spend = cost(MODEL, usage(input_tokens=1_000, output_tokens=10))

    assert (spend.cache_write_tokens, spend.cache_read_tokens) == (0, 0)
    assert spend.usd == pytest.approx(1_000 * PRICE.input + 10 * PRICE.output)


def test_a_usage_block_from_before_prompt_caching_is_priced_as_uncached():
    """Absent is not None: an SDK that predates prompt caching carries no cache attributes at all,
    and there zero is the true figure rather than a guess, because no caching can have happened."""
    spend = cost(MODEL, SimpleNamespace(input_tokens=1_000, output_tokens=10))

    assert (spend.cache_write_tokens, spend.cache_read_tokens) == (0, 0)
    assert spend.usd == pytest.approx(1_000 * PRICE.input + 10 * PRICE.output)


@pytest.mark.parametrize("missing", ["input_tokens", "output_tokens"])
def test_an_object_missing_a_priced_token_count_is_not_priced_at_zero(missing):
    """The negative case for that tolerance, in the direction it must fail. Absent cache counts
    mean no caching; an absent input or output count means this is not a usage block, and counting
    it as zero would under-report spend and quietly raise both ceilings."""
    fields = {"input_tokens": 100_000, "output_tokens": 4_000}
    del fields[missing]

    with pytest.raises(AttributeError):
        cost(MODEL, SimpleNamespace(**fields))


def test_a_response_reporting_nothing_costs_nothing_but_still_counts_as_a_call():
    spend = cost(MODEL, usage())

    assert (spend.input_tokens, spend.output_tokens, spend.usd) == (0, 0, 0.0)
    assert spend.calls == 1


def test_an_unknown_model_cannot_be_priced():
    """The negative case for the price lookup: a model absent from the table stops the run
    rather than being accounted for at zero, which would silently disable both bounds."""
    with pytest.raises(Unpriceable):
        cost("claude-sonnet-9", usage(input_tokens=1_000))


def test_an_unknown_model_cannot_be_projected_either():
    with pytest.raises(Unpriceable):
        projected_cost("claude-sonnet-9", input_tokens=1_000, max_tokens=100)


def test_projection_prices_output_at_the_requested_maximum():
    """100k input tokens at $5/M is $0.50; 4k output at $25/M is $0.10."""
    assert projected_cost(MODEL, input_tokens=100_000, max_tokens=4_000) == pytest.approx(0.6)


def test_projection_prices_the_cached_part_of_the_input_at_the_cached_rate():
    """60k of the 100k input tokens served from the cache: $0.20 + $0.03, not $0.50."""
    projected = projected_cost(MODEL, input_tokens=100_000, max_tokens=0, cached_tokens=60_000)

    assert projected == pytest.approx(0.23)


def test_projection_of_a_wholly_uncached_request_is_ten_times_a_wholly_cached_one():
    """The negative case for caching: the same token count, varying only which part is cached."""
    uncached = projected_cost(MODEL, input_tokens=100_000, max_tokens=0)
    cached = projected_cost(MODEL, input_tokens=100_000, max_tokens=0, cached_tokens=100_000)

    assert uncached == pytest.approx(0.5)
    assert cached == pytest.approx(0.05)


def test_more_cached_tokens_than_input_tokens_is_refused():
    """The negative case for "cached tokens are part of the input", in the direction it must fail.
    Priced through, the overshoot is charged at a negative input rate, and the projection it
    returns is below zero: a figure no ceiling can be crossed by, which is the one outcome a
    spend bound must never produce quietly. One more cached token than input is enough to ask —
    the equal case above is the boundary and is allowed."""
    with pytest.raises(ValueError):
        projected_cost(MODEL, input_tokens=100_000, max_tokens=4_000, cached_tokens=100_001)


class _Messages:
    def __init__(self, count: int) -> None:
        self.count = count
        self.requests: list[dict] = []

    def count_tokens(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(input_tokens=self.count)


class _Client:
    def __init__(self, count: int) -> None:
        self.messages = _Messages(count)


SYSTEM = [{"type": "text", "text": "the paper", "cache_control": {"type": "ephemeral"}}]
MESSAGES = [{"role": "user", "content": "the instruction"}]


def test_the_token_count_is_taken_on_the_exact_request():
    client = _Client(64_321)

    counted = count_input_tokens(client, MODEL, system=SYSTEM, messages=MESSAGES)

    assert counted == 64_321
    assert client.messages.requests == [{"model": MODEL, "system": SYSTEM, "messages": MESSAGES}]


def test_an_output_format_is_passed_when_there_is_one_and_omitted_when_there_is_not():
    """Omitted rather than sent as null: a null output format is not the same request as none,
    and the projection is worth nothing if it counts a different request from the one sent."""
    schema = {"type": "json_schema"}
    with_format = _Client(10)
    without_format = _Client(10)

    count_input_tokens(with_format, MODEL, system=SYSTEM, messages=MESSAGES, output_format=schema)
    count_input_tokens(without_format, MODEL, system=SYSTEM, messages=MESSAGES)

    assert with_format.messages.requests[0]["output_format"] is schema
    assert "output_format" not in without_format.messages.requests[0]


def a_ledger(**bounds) -> Ledger:
    return Ledger(Ceiling(**bounds))


def test_the_default_per_paper_ceiling_is_two_dollars():
    """The user's decision of 2026-09-18. Recorded as an assertion because it is a decision,
    not a tuning constant somebody may round."""
    assert Ceiling().per_paper == 2.00
    assert Ceiling().per_run == 40.00


def test_a_call_crossing_the_paper_ceiling_is_refused():
    ledger = a_ledger(per_paper=2.00, per_run=40.00)
    ledger.record("PMC1", Spend(usd=1.75, calls=1))

    with pytest.raises(CeilingReached) as raised:
        ledger.check("PMC1", 0.50)

    assert raised.value.scope == "paper"
    assert (raised.value.spent, raised.value.projected, raised.value.limit) == (1.75, 0.50, 2.00)


def test_a_refused_call_leaves_the_ledger_untouched():
    """The refusal is a decision not to spend, so nothing about it may look like spending."""
    ledger = a_ledger(per_paper=2.00)
    ledger.record("PMC1", Spend(input_tokens=100, usd=1.75, calls=1))

    with pytest.raises(CeilingReached):
        ledger.check("PMC1", 0.50)

    assert ledger.paper("PMC1") == Spend(input_tokens=100, usd=1.75, calls=1)
    assert ledger.run == Spend(input_tokens=100, usd=1.75, calls=1)


def test_a_call_crossing_the_run_budget_is_refused_though_the_paper_is_well_under():
    """The negative case for the paper bound and the positive one for the run bound: this paper
    has spent nothing at all, so only the run total can refuse the call."""
    ledger = a_ledger(per_paper=2.00, per_run=4.00)
    ledger.record("PMC1", Spend(usd=3.75, calls=3))

    with pytest.raises(CeilingReached) as raised:
        ledger.check("PMC2", 0.50)

    assert raised.value.scope == "run"
    assert ledger.paper("PMC2") == Spend()


def test_a_paper_that_would_cross_both_bounds_is_reported_as_the_paper_stopping():
    """Naming the run would halt a run that is fine; the paper ends CEILING_REACHED and the
    next paper is still started."""
    ledger = a_ledger(per_paper=2.00, per_run=4.00)
    ledger.record("PMC1", Spend(usd=3.75, calls=3))

    with pytest.raises(CeilingReached) as raised:
        ledger.check("PMC1", 0.50)

    assert raised.value.scope == "paper"


def test_a_call_landing_exactly_on_a_bound_is_allowed():
    """Strict crossing, both bounds: the projection is already a worst case, so withholding the
    last affordable call would cost a paper for nothing."""
    ledger = a_ledger(per_paper=2.00, per_run=4.00)
    ledger.record("PMC1", Spend(usd=1.50, calls=1))
    ledger.record("PMC2", Spend(usd=2.00, calls=1))

    ledger.check("PMC1", 0.50)


def test_spend_accumulates_per_paper_and_per_run():
    ledger = a_ledger()
    ledger.record("PMC1", Spend(input_tokens=1_000, usd=0.10, calls=1))
    ledger.record("PMC1", Spend(cache_read_tokens=1_000, usd=0.01, calls=1))
    ledger.record("PMC2", Spend(input_tokens=500, usd=0.05, calls=1))

    assert ledger.paper("PMC1").usd == pytest.approx(0.11)
    assert ledger.paper("PMC1").calls == 2
    assert ledger.paper("PMC2").usd == pytest.approx(0.05)
    assert ledger.run.usd == pytest.approx(0.16)
    assert ledger.run.calls == 3


def test_an_untouched_paper_has_spent_nothing():
    assert a_ledger().paper("PMC404") == Spend()


def test_the_cached_fraction_is_cache_reads_over_all_input_tokens():
    ledger = a_ledger()
    ledger.record("PMC1", Spend(input_tokens=10_000, cache_write_tokens=50_000, calls=1))
    ledger.record("PMC1", Spend(input_tokens=1_000, cache_read_tokens=139_000, calls=1))

    assert ledger.cached_fraction() == pytest.approx(139_000 / 200_000)


def test_a_run_that_never_hit_the_cache_reports_no_cached_fraction():
    """Zero is the run summary's signal that caching is not working — so it must mean that, and
    not merely "nothing has happened yet"."""
    empty = a_ledger()
    uncached = a_ledger()
    uncached.record("PMC1", Spend(input_tokens=60_000, output_tokens=2_000, calls=1))

    assert empty.cached_fraction() == 0.0
    assert uncached.cached_fraction() == 0.0
