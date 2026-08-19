"""Configuration: the derived ceiling, and rendering money for a human.

Both are load-bearing and neither had a test. The ceiling is what the gate
enforces, and format_usd writes the sentence a user reads when a run stops.
"""

from __future__ import annotations

import pytest

from bionumbers_ask.config import (
    MICRO_PER_USD,
    Config,
    format_usd,
    micro_from_provider_cost,
    usd,
)


def config_with(threshold: str) -> Config:
    return Config(model="m", warning_threshold=usd(threshold), run_budget=usd("1.20"))


def test_the_ceiling_is_the_warning_threshold_plus_twenty_per_cent():
    assert config_with("0.50").question_ceiling == usd("0.60")


def test_reconfiguring_the_threshold_recomputes_the_ceiling():
    """Spec: the threshold is changeable without code changes, and the ceiling follows."""
    assert config_with("0.10").question_ceiling == usd("0.12")
    assert config_with("2.00").question_ceiling == usd("2.40")


def test_the_ceiling_stays_above_the_threshold_at_development_scale():
    """Integer division must not collapse the 20 per cent gap on small amounts.

    Sub-cent thresholds are what a development run actually uses, and a ceiling
    equal to its threshold would stop a question the moment it warned.
    """
    small = config_with("0.000100")
    assert small.question_ceiling > small.warning_threshold


@pytest.mark.parametrize(
    ("micro", "rendered"),
    [
        (0, "$0"),
        (34, "$0.000034"),
        (9_999, "$0.009999"),
        (10_000, "$0.01"),
        (600_000, "$0.60"),
        (MICRO_PER_USD, "$1.00"),
    ],
)
def test_precision_follows_magnitude(micro, rendered):
    """Two decimals would render every development-scale figure as "$0".

    That is exactly when the number is being watched most closely, so precision
    increases as the amount gets smaller rather than being fixed.
    """
    assert format_usd(micro) == rendered


def test_the_provider_cost_boundary_rounds_once():
    """The single place a float is allowed in; everything after it is integral."""
    assert micro_from_provider_cost(3.4e-05) == 34
    assert micro_from_provider_cost(0.0) == 0
