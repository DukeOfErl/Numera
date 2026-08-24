"""Run configuration: the model, the spend limits, and a fallback price table.

Money is held as integer **micro-dollars** (1e-6 USD), not cents. Cents are too
coarse: a thousand-token call on a cheap model costs a fraction of a cent, so a
ledger that rounded each increment to whole cents would round most of them to
zero and never move. Integers avoid the drift that repeated float addition
introduces; micro-dollars make them fine-grained enough to accumulate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

MICRO_PER_USD = 1_000_000


class NotConfigured(Exception):
    """Something the run needs is absent from the environment.

    Distinct from a defect: a missing credential is a condition a driver can
    report to its user, so it must not be indistinguishable from a bug.
    """


def usd(amount: str) -> int:
    """Micro-dollars from a decimal string. A string, so no float ever appears.

    Rejects what a misconfigured environment produces rather than propagating it:
    an empty value would raise deep inside int(), and a negative amount parsed
    naively loses its sign -- "-0.50" would become a positive limit.
    """
    text = (amount or "").strip()
    if not text:
        raise ValueError("expected an amount in USD, for example '0.50'")
    if text.startswith("-"):
        raise ValueError(f"amount must not be negative: {amount!r}")
    whole, _, frac = text.lstrip("+").partition(".")
    if not (whole or frac).isdigit() or (whole and not whole.isdigit()):
        raise ValueError(f"not a decimal amount: {amount!r}")
    return int(whole or 0) * MICRO_PER_USD + int((frac + "000000")[:6])


def format_usd(micro: int) -> str:
    """Render micro-dollars for a human.

    Development calls cost fractions of a cent, so a fixed two- or four-decimal
    format would render most real spend as "$0" and make the figure useless
    exactly when it is being watched most closely. Precision follows magnitude.
    """
    if micro == 0:
        return "$0"
    places = 2 if micro >= 10_000 else 6
    return f"${micro / MICRO_PER_USD:.{places}f}"


def micro_from_provider_cost(cost: float) -> int:
    """Convert a provider's reported cost to micro-dollars.

    Providers report cost as a float. This is the single point where one is
    allowed in: round once here, then stay in integers, so the ledger never
    accumulates float error.
    """
    return round(cost * MICRO_PER_USD)


@dataclass(frozen=True)
class ModelPrices:
    """Per-million-token prices, in micro-dollars. Only a fallback.

    OpenRouter reports the cost of each request, which is authoritative and needs
    no table. This exists for a provider that reports token counts alone.
    """

    input_per_mtok: int
    output_per_mtok: int


@dataclass(frozen=True)
class Config:
    model: str
    warning_threshold: int
    run_budget: int
    prices: dict[str, ModelPrices] = field(default_factory=dict)
    # What this run is, carried on every record. Without it an evaluation's spend
    # and a person's spend are one undifferentiated total, and that cannot be
    # separated afterwards: records already written carry no label to filter on.
    # A label for the run, deliberately not a name for the caller -- the agent is
    # given nothing it could branch on to behave differently for one driver.
    run_label: str = "dev"

    @property
    def question_ceiling(self) -> int:
        """The hard per-question limit: the warning threshold plus 20 per cent."""
        return self.warning_threshold * 12 // 10

    def prices_for(self, model: str) -> ModelPrices | None:
        return self.prices.get(model)

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            model=os.environ.get("BIONUMBERS_ASK_MODEL", DEFAULT_MODEL),
            warning_threshold=usd(os.environ.get("BIONUMBERS_ASK_WARN_USD", "0.50")),
            run_budget=usd(os.environ.get("BIONUMBERS_ASK_RUN_BUDGET_USD", "1.20")),
            prices=dict(FALLBACK_PRICES),
            run_label=os.environ.get("BIONUMBERS_ASK_RUN", "").strip() or "dev",
        )


# Development runs on a cheap, strong instruction-follower; the capable target is
# Claude Opus 4.7. The exact OpenRouter slug is confirmed in task 1.7 rather than
# assumed here.
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"

# Prices read from OpenRouter's models endpoint on 2026-08-18, in micro-dollars per
# million tokens. Only reached if a provider stops reporting cost -- OpenRouter's
# reported figure matched these exactly when checked, so this table is a spare.
FALLBACK_PRICES: dict[str, ModelPrices] = {
    "anthropic/claude-haiku-4.5": ModelPrices(1_000_000, 5_000_000),
    "anthropic/claude-opus-4.7": ModelPrices(5_000_000, 25_000_000),
}
