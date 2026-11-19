"""What a call will cost before it is made, what it did cost after, and the two ceilings.

Projected before, reported after, discarded on ceiling (design D6). The projection asks the
provider to count the tokens of the exact request rather than estimating from characters: Opus
4.7's tokenizer yields up to about a third more tokens than earlier Opus models, and a character
estimate would be wrong in the cheap direction — the direction that lets a runaway through.

Where the numbers come from, written on 2026-09-18, because the table is the input to both
ceilings and a wrong rate misprices every projection in silence. `design.md` is the corroboration
reachable from this repository, and it covers $5 and $25 per million tokens and the 2048-token
minimum cacheable prefix. It does **not** cover the model id `claude-opus-4-7` or the cache
multipliers (write 1.25x input, read 0.1x): those were supplied with the task, and the
`claude-api` reference that `tasks.md` says to check them against is not reachable from this
worktree — no such skill is installed. **Read them off the provider's current price page before
the first paid run**, and treat this paragraph as the open question it is rather than as a check
already done. The code is written against anthropic 0.122.0, whose `Usage` carries the four token
fields this module prices and whose `messages.count_tokens` takes `model`, `system`, `messages`
and `output_format`.

The cache minimum is why the paper goes into the system block whole (design D1) rather than being
split across messages — a split prefix is a prefix that never gets cached, and the retry and the
second-text call would then each pay full input rate for the article.

Not the ask app's `SpendGate`: that is a LangChain `wrap_model_call` middleware and this pipeline
has no LangChain. The projection-then-report shape is the same by design (ADR-0180) and so is its
`Unpriceable` — a run that cannot account for what it is spending has no working control, so it
stops. Only the enforcement point differs: here the caller asks the ledger before each of the
up-to-three calls per paper, because there is no dispatch path to sit in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from numera_validator.records import Spend

MODEL = "claude-opus-4-7"


@dataclass(frozen=True, slots=True)
class Prices:
    """USD per token, not per million, so every arithmetic site is free of a scaling constant.

    A per-million table reads closer to the provider's own page, but then each of the four
    multiplications below carries a `/ 1e6` that one of them will eventually be missing.
    """

    input: float
    cache_write: float
    cache_read: float
    output: float
    provider: str = ""
    """The OpenRouter provider slug these prices were read from, and the one the request is pinned
    to (`openrouter.OpenRouterModel`). A price is a price *at a provider*: the same model is served
    by several at different rates -- GLM 5.3 Flash from $0.25 to $1.00 per million output tokens on
    2026-10-07, Opus 5.5 at twice list on `anthropic/fast` -- and OpenRouter's default routing is
    free to pick any of them, so a table row without a pin is a projection against a price that
    may not be the one charged. Empty for a model id that is not an OpenRouter route."""


#: Cache write at 1.25x input and cache read at 0.1x (unconfirmed — see the docstring) make three
#: reads of a cached paper cheaper than one uncached read, which is the whole reason the pipeline
#: re-reads rather than re-sends.
_OPUS_4_7 = Prices(5e-6, 6.25e-6, 0.5e-6, 25e-6)
#: The same model under the two names it is reached by: Anthropic's own id, and OpenRouter's,
#: which bills Anthropic models at Anthropic's list price (checked 2026-09-18 against
#: openrouter.ai/anthropic/claude-opus-4.7). One entry per route, so `cost` needs no
#: knowledge of which adapter made the call.
OPENROUTER_MODEL = "anthropic/claude-opus-4.7"
#: Cheaper candidates for harvest mode, where cost scales with papers rather than questions, and
#: the models tried as simulated reviewers. Each row is pinned to the provider its price was read
#: from (`Prices.provider`), checked against `/api/v1/models/<id>/endpoints` on 2026-10-07.
#: GPT-4.1 has no separate cache-write price (its caching is automatic), so a write is priced as
#: plain input.
PRICES: dict[str, Prices] = {
    MODEL: _OPUS_4_7,
    OPENROUTER_MODEL: Prices(5e-6, 6.25e-6, 0.5e-6, 25e-6, provider="anthropic"),
    "anthropic/claude-sonnet-5": Prices(2e-6, 2.5e-6, 0.2e-6, 10e-6, provider="anthropic"),
    "anthropic/claude-sonnet-5.5": Prices(2e-6, 2.5e-6, 0.2e-6, 10e-6, provider="anthropic"),
    "anthropic/claude-haiku-4.5": Prices(1e-6, 1.25e-6, 0.1e-6, 5e-6, provider="anthropic"),
    "openai/gpt-4.1": Prices(2e-6, 2e-6, 0.5e-6, 8e-6, provider="openai"),
    "anthropic/claude-opus-5.5": Prices(4e-6, 5e-6, 0.2e-6, 20e-6, provider="anthropic"),
    # The Nemotron rows are DeepInfra's prices (read off `/api/v1/models/<id>/endpoints` on
    # 2026-10-07): no cache-write price there, and none for a cache read on the Super, so each
    # missing figure is priced as plain input, which errs high.
    "nvidia/nemotron-3.5-lightning": Prices(
        0.06e-6, 0.06e-6, 0.03e-6, 0.16e-6, provider="deepinfra"
    ),
    "nvidia/nemotron-3-super-120b-a12b": Prices(
        0.085e-6, 0.085e-6, 0.085e-6, 0.4e-6, provider="deepinfra"
    ),
    "nvidia/nemotron-3-ultra-550b-a55b": Prices(
        0.5e-6, 0.5e-6, 0.1e-6, 2.2e-6, provider="deepinfra"
    ),
    "openai/gpt-6.1-sol": Prices(2e-6, 2.5e-6, 0.1e-6, 10e-6, provider="openai"),
    # Moonshot's own endpoint; the listing's cheaper figures were other providers' quantised
    # copies, which is the kind of drift the pin exists to stop. No cache-write price.
    "moonshotai/kimi-k3": Prices(3e-6, 3e-6, 0.3e-6, 15e-6, provider="moonshotai"),
    "z-ai/glm-5.3-flash": Prices(0.15e-6, 0.15e-6, 0.03e-6, 0.5e-6, provider="z-ai"),
    # A router has no price of its own: it sends each call to a model of its choosing and bills
    # that model's rate. These are Sonnet's figures as an upper bound for the projection -- the
    # calls observed on 2026-10-07 went to GPT-6 Luna and DeepSeek V4.1 Flash at a tenth of
    # this -- so a run's recorded spend for it overstates, and the provider's own ledger is the
    # figure to read. No pin: the routing is the service.
    "typesafe/jev-router": Prices(2e-6, 2.5e-6, 0.2e-6, 10e-6),
}


class Unpriceable(Exception):
    """No prices are known for the model, so nothing can be projected or accounted for.

    Raised rather than defaulted: a zero price silently disables both ceilings, and the failure
    would show up as an invoice rather than as a stopped run.
    """


def _prices(model: str) -> Prices:
    prices = PRICES.get(model)
    if prices is None:
        raise Unpriceable(f"no prices are configured for {model!r}; known: {sorted(PRICES)}")
    return prices


def _tokens(value: Any) -> int:
    """A usage count the provider reported as None, read as zero.

    The SDK leaves `cache_creation_input_tokens` and `cache_read_input_tokens` as None on a call
    that used no caching, and None is not a number to multiply by a rate. None and zero are the
    same charge, so unlike the ask app's ledger this one keeps no third state for "unknown": it
    prices from the table on every call, so there is no fallback for an unknown to select. Whether
    a field may be missing altogether is a different rule, decided per field in `cost`.
    """
    return int(value) if value else 0


def cost(model: str, usage: Any) -> Spend:
    """Price one response from what the provider reported about it.

    `usage` is the SDK's usage block, or anything carrying `input_tokens` and `output_tokens` —
    and, on an SDK that knows about prompt caching, the two cache counts as well. Cache reads are
    counted at the cached rate, which is what makes "a run with zero cache reads is a bug, not a
    cost" checkable after the fact.
    """
    prices = _prices(model)
    # The two cache fields may be absent rather than None on an SDK predating prompt caching, and
    # absent there means no caching happened, so zero is the true figure. `input_tokens` and
    # `output_tokens` get no such default: an object without them is not a usage block at all, and
    # pricing that at zero would under-count spend and disable both ceilings — the same failure
    # `Unpriceable` refuses above, so it is refused the same way, by stopping.
    input_tokens = _tokens(usage.input_tokens)
    cache_write_tokens = _tokens(getattr(usage, "cache_creation_input_tokens", 0))
    cache_read_tokens = _tokens(getattr(usage, "cache_read_input_tokens", 0))
    output_tokens = _tokens(usage.output_tokens)
    return Spend(
        input_tokens=input_tokens,
        cache_write_tokens=cache_write_tokens,
        cache_read_tokens=cache_read_tokens,
        output_tokens=output_tokens,
        usd=(
            input_tokens * prices.input
            + cache_write_tokens * prices.cache_write
            + cache_read_tokens * prices.cache_read
            + output_tokens * prices.output
        ),
        calls=1,
    )


def projected_cost(
    model: str, *, input_tokens: int, max_tokens: int, cached_tokens: int = 0
) -> float:
    """What the next call could cost at worst, before it is made.

    Output is priced at `max_tokens` because that is the only output figure that exists before the
    call, and the worst case is the one a ceiling must be checked against. `cached_tokens` is the
    part of `input_tokens` the provider will serve from its cache, not an addition to it — more
    cached than input is a miscount, and it is refused rather than projected.

    Known to under-project in one place: the call that *writes* the cache pays 1.25x input on the
    article, and this prices that article at plain input rate. The error is 25% of one call's
    article cost — about $0.08 on a 65k-token paper against a $2 ceiling — and it fails in the
    cheap direction, so it is the ceiling's headroom that absorbs it rather than a reviewer. Price
    the write here if the ceiling is ever tightened towards the projection.
    """
    prices = _prices(model)
    # Refused rather than clamped, and refused here rather than at the one call site that does not
    # exist yet: the arithmetic below would charge the overshoot at a negative input rate, and a
    # negative projection crosses no ceiling and reads as headroom in the run summary. Clamping to
    # `input_tokens` would price the request as wholly cached instead — the same failure, one
    # decimal quieter. Stopping is the cheap direction for a bound whose job is to fail expensive.
    if cached_tokens > input_tokens:
        raise ValueError(
            f"cached_tokens ({cached_tokens}) exceeds input_tokens ({input_tokens}): "
            "cached tokens are part of the input, not an addition to it"
        )
    return (
        (input_tokens - cached_tokens) * prices.input
        + cached_tokens * prices.cache_read
        + max_tokens * prices.output
    )


def count_input_tokens(
    client: Any, model: str, *, system: Any, messages: Any, output_format: Any = None
) -> int:
    """The provider's own count of the request that is about to be sent.

    A thin wrapper for two reasons: the projection must be taken on the *exact* request, so the
    caller passes the same objects it will send; and a test can hand this a double with the same
    method rather than reaching the network for a number it already knows.
    """
    extra = {"output_format": output_format} if output_format is not None else {}
    # Omitted rather than passed as None: the SDK distinguishes an absent parameter from an
    # explicit null, and a null output format is not the same request as none at all.
    return client.messages.count_tokens(
        model=model, system=system, messages=messages, **extra
    ).input_tokens


class CeilingReached(Exception):
    """The next call would cross a bound, checked before it was made.

    Carries which bound: a paper that stops is one `CEILING_REACHED` record among many, while a
    run that stops leaves every remaining article unread. Whoever reads the ending needs to tell
    those apart, and the scope is the only thing that does.
    """

    def __init__(self, scope: str, projected: float, spent: float, limit: float) -> None:
        self.scope = scope
        self.projected = projected
        self.spent = spent
        self.limit = limit
        super().__init__(
            f"{scope} ceiling: ${spent:.2f} spent plus ${projected:.2f} projected "
            f"exceeds ${limit:.2f}"
        )


@dataclass(frozen=True, slots=True)
class Ceiling:
    """The two bounds, in US dollars.

    $2 per paper is the user's decision of 2026-09-18. It is a runaway stop and not a cost target
    (the design's "cheapness" non-goal): one Opus pass over a 150 kB paper plus a cached retry and
    a cached second-text call projects well under it, so a paper that reaches $2 has gone wrong
    rather than gone long.
    """

    per_paper: float = 2.00
    per_run: float = 40.00


class Ledger:
    """What has been spent, per paper and per run, and the refusal that keeps it bounded.

    The refusal is *worded* here and *invoked* elsewhere, which is the weak form of the house rule
    and is worth naming as such. Nothing in this module makes a model call, so there is no
    operation here to put the guard inside: a call site that never asks `check` spends without any
    bound, and no test in this package can see that it did. The ask app's `SpendGate` does not have
    that hole because LangChain gives it a dispatch path to sit in; this pipeline has none.

    So the bound is only as good as its call sites, and the way to keep that auditable is to keep
    them few: route the up-to-three Anthropic calls per paper through one function in the
    extraction step, ask `check` there, and the guard has one place to be missing from instead of
    three. Adding a second call site elsewhere silently widens both ceilings.
    """

    def __init__(self, ceiling: Ceiling) -> None:
        self.ceiling = ceiling
        self._papers: dict[str, Spend] = {}
        self._run = Spend()

    def check(self, article_id: str, projected_usd: float) -> None:
        """Refuse the next call if its projection would cross either bound.

        Paper before run, because a paper that would cross its own ceiling must end
        `CEILING_REACHED` even on a run with budget to spare; reporting that as a run stop would
        halt a run that is fine.

        Crossing is strict: a projection landing exactly on the limit is allowed, so the last
        affordable call is made rather than withheld. That direction is the cheap one here — the
        projection is already a worst case, so equality means the call will almost certainly come
        in under the bound.
        """
        spent = self.paper(article_id).usd
        if spent + projected_usd > self.ceiling.per_paper:
            raise CeilingReached("paper", projected_usd, spent, self.ceiling.per_paper)
        if self._run.usd + projected_usd > self.ceiling.per_run:
            raise CeilingReached("run", projected_usd, self._run.usd, self.ceiling.per_run)

    def record(self, article_id: str, spend: Spend) -> None:
        """Accumulate an actual charge against both counters."""
        self._papers[article_id] = self.paper(article_id).plus(spend)
        self._run = self._run.plus(spend)

    def paper(self, article_id: str) -> Spend:
        """What this article has cost so far; an untouched article has cost nothing."""
        return self._papers.get(article_id, Spend())

    @property
    def run(self) -> Spend:
        return self._run

    def cached_fraction(self) -> float:
        """Cache reads as a share of all input tokens, for the run summary.

        A run whose fraction is zero has been paying full rate for every re-read of every paper:
        the design calls that a bug rather than a cost, and this is the figure that shows it.
        """
        total = self._run.input_tokens + self._run.cache_write_tokens + self._run.cache_read_tokens
        return self._run.cache_read_tokens / total if total else 0.0


def call(
    model: Any,
    *,
    system: Any,
    messages: list[dict],
    output_format: type,
    max_tokens: int,
    ledger: Ledger,
    entry: str,
    model_id: str,
) -> tuple[Any, str]:
    """Project, ask the ledger, call, record: the one model call under the ledger.

    Every call the extractor and the simulated review make comes through here, so the bound has
    one place to be missing from instead of several. Returns the parsed output and the model the
    provider says answered (`""` where it says nothing). `entry` is the ledger's per-entry key: the
    paper for an extraction, the item for a simulated decision.

    The projection assumes nothing is cached, even where most of the prefix will be. That
    over-projects, and over-projecting stops a paper early while under-projecting lets a runaway
    through -- and the cache can expire between two calls, so the cheap-looking figure is also the
    one that can be wrong. A ceiling's job is to fail expensive.

    A response the adapter could not read into the schema was still billed: the first live run had
    one such paper showing $0.00 and no call, which is the one figure a ceiling must never
    under-count. Adapters that know the usage attach it to the error, and it is recorded before the
    error goes on.
    """
    counted = model.count_tokens(system=system, messages=messages, output_format=output_format)
    projected = projected_cost(model_id, input_tokens=counted.input_tokens, max_tokens=max_tokens)
    ledger.check(entry, projected)
    try:
        response = model.parse(
            system=system, messages=messages, output_format=output_format, max_tokens=max_tokens
        )
    except Exception as failure:
        usage = getattr(failure, "usage", None)
        if usage is not None:
            ledger.record(entry, cost(model_id, usage))
        raise
    ledger.record(entry, cost(model_id, response.usage))
    raw = getattr(response, "raw", None)
    answered = raw.get("model") if isinstance(raw, dict) else None
    return response.parsed_output, answered if isinstance(answered, str) else ""
