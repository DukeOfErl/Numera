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


#: Every environment name this project has retired, and what replaced it.
#:
#: A renamed variable that is merely ignored is configuration that silently stops
#: being read: a ceiling that no longer binds, a run label that quietly becomes
#: "dev" and mixes an evaluation's spend into a person's, a corpus path that falls
#: back to none. Each of those looks like a working run. So a retired name is
#: refused by name, with its replacement in the message.
RENAMED_ENV = {
    "BIONUMBERS_ASK_CORPUS": "SCINUMBERS_CORPUS",
    "BIONUMBERS_ASK_TRACE": "SCINUMBERS_TRACE",
    "BIONUMBERS_ASK_CHECKPOINTS": "SCINUMBERS_CHECKPOINTS",
    "BIONUMBERS_ASK_MODEL": "SCINUMBERS_MODEL",
    "BIONUMBERS_ASK_QUESTION_CEILING_USD": "SCINUMBERS_QUESTION_CEILING_USD",
    "BIONUMBERS_ASK_RUN_BUDGET_USD": "SCINUMBERS_RUN_BUDGET_USD",
    "BIONUMBERS_ASK_RUN": "SCINUMBERS_RUN",
}

#: Retired without a replacement of the same meaning, so a rename message would be
#: wrong. Read as a ceiling, a value that used to permit spending 20 per cent above
#: it would now stop 20 per cent below -- a spend limit that silently tightens,
#: which is worse than one that will not start. ADR-0180.
WITHDRAWN_ENV = {
    "BIONUMBERS_ASK_WARN_USD": (
        "SCINUMBERS_QUESTION_CEILING_USD is the hard per-question limit, and the "
        "warning is derived at 80 per cent of it"
    ),
}


def refuse_retired_env() -> None:
    """Refuse a run configured through a name this project no longer reads.

    Called from `Config.from_env` so a library caller cannot miss it, **and** from
    each driver before anything else reads the environment. The ordering matters
    more than it looks: both drivers resolve the corpus before building a config,
    so a reader with only the old corpus variable exported would otherwise be told
    "no corpus path supplied" -- true, unhelpful, and pointing at the wrong thing.
    """
    for old, new in RENAMED_ENV.items():
        if old in os.environ:
            raise NotConfigured(f"{old} is now {new}. Rename it and try again.")
    for old, guidance in WITHDRAWN_ENV.items():
        if old in os.environ:
            raise NotConfigured(f"{old} no longer exists. {guidance}.")


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
    # The hard per-question limit. Configured directly, because the number a
    # person sets should be the number that stops work -- it used to be the
    # warning, with the ceiling derived 20 per cent above it and never named, and
    # a reader of this file concluded there was no per-question stop at all.
    # ADR-0180; the same shape as CONVERSATION_BOUND / CONVERSATION_WARN_AT.
    question_ceiling: int
    run_budget: int
    prices: dict[str, ModelPrices] = field(default_factory=dict)
    # What this run is, carried on every record. Without it an evaluation's spend
    # and a person's spend are one undifferentiated total, and that cannot be
    # separated afterwards: records already written carry no label to filter on.
    # A label for the run, deliberately not a name for the caller -- the agent is
    # given nothing it could branch on to behave differently for one driver.
    run_label: str = "dev"

    @property
    def warning_threshold(self) -> int:
        """Notice, at four fifths of the stop configured here.

        Only correct for a question running against *this* configuration's
        ceiling. A session keeps the ceiling it was created with, so a resumed
        session must derive its warning from that one -- use `warning_for`.
        """
        return warning_for(self.question_ceiling)

    def prices_for(self, model: str) -> ModelPrices | None:
        return self.prices.get(model)

    @classmethod
    def from_env(cls) -> Config:
        refuse_retired_env()
        return cls(
            model=os.environ.get("SCINUMBERS_MODEL", DEFAULT_MODEL),
            question_ceiling=usd(os.environ.get("SCINUMBERS_QUESTION_CEILING_USD", "0.60")),
            run_budget=usd(os.environ.get("SCINUMBERS_RUN_BUDGET_USD", "1.20")),
            prices=dict(FALLBACK_PRICES),
            run_label=os.environ.get("SCINUMBERS_RUN", "").strip() or "dev",
        )


# Development runs on a cheap, strong instruction-follower; the capable target is
# Claude Opus 4.7. The exact OpenRouter slug is confirmed in task 1.7 rather than
# assumed here.
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"

# Where notice is given, as a fraction of the stop. Integer arithmetic throughout,
# because money here is integer micro-dollars and a float ratio would reintroduce
# rounding at the one place the ledger is careful to avoid it.
WARN_AT_NUMERATOR = 8
WARN_AT_DENOMINATOR = 10


def warning_for(ceiling: int) -> int:
    """Where notice is given for a question stopping at `ceiling`.

    Takes the ceiling rather than reading configuration, because the two can
    differ: a session keeps the ceiling it was created with (ADR-0180), so a
    session made under one ceiling and resumed under another would otherwise get
    a warning derived from a limit it is not subject to -- silently never firing
    when the session's ceiling is the lower of the two, which is exactly the case
    the warning exists for.
    """
    return ceiling * WARN_AT_NUMERATOR // WARN_AT_DENOMINATOR


# Prices read from OpenRouter's models endpoint on 2026-08-18, in micro-dollars per
# million tokens. Only reached if a provider stops reporting cost -- OpenRouter's
# reported figure matched these exactly when checked, so this table is a spare.
FALLBACK_PRICES: dict[str, ModelPrices] = {
    "anthropic/claude-haiku-4.5": ModelPrices(1_000_000, 5_000_000),
    "anthropic/claude-opus-4.7": ModelPrices(5_000_000, 25_000_000),
}
