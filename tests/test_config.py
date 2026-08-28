"""Configuration: the configured ceiling, its derived warning, and money for a human.

Both are load-bearing and neither had a test. The ceiling is what the gate
enforces, and format_usd writes the sentence a user reads when a run stops.
"""

from __future__ import annotations

import pytest

from bionumbers_ask.config import (
    MICRO_PER_USD,
    Config,
    NotConfigured,
    format_usd,
    micro_from_provider_cost,
    usd,
)


def config_with(ceiling: str) -> Config:
    return Config(model="m", question_ceiling=usd(ceiling), run_budget=usd("1.20"))


def test_the_warning_is_four_fifths_of_the_ceiling():
    """The configured number is the one that stops work; notice is derived from it."""
    assert config_with("0.60").warning_threshold == usd("0.48")


def test_reconfiguring_the_ceiling_recomputes_the_warning():
    """Spec: the limit is changeable without code changes, and notice follows it."""
    assert config_with("0.10").warning_threshold == usd("0.08")
    assert config_with("2.00").warning_threshold == usd("1.60")


def test_the_warning_stays_below_the_ceiling_at_development_scale():
    """Integer division must not collapse the gap on small amounts.

    Sub-cent limits are what a development run actually uses, and a warning equal
    to its ceiling would stop a question the moment it warned.
    """
    small = config_with("0.000120")
    assert small.warning_threshold < small.question_ceiling


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


def test_the_retired_key_is_refused_rather_than_read_as_a_ceiling(monkeypatch):
    """Read as a ceiling it would stop 20 per cent below where it used to warn.

    A spend limit that silently tightens is worse than one that will not start,
    so the old name is rejected with the new one named. ADR-0180.
    """
    monkeypatch.setenv("BIONUMBERS_ASK_WARN_USD", "0.50")
    monkeypatch.delenv("BIONUMBERS_ASK_QUESTION_CEILING_USD", raising=False)

    with pytest.raises(NotConfigured) as raised:
        Config.from_env()

    assert "BIONUMBERS_ASK_QUESTION_CEILING_USD" in str(raised.value)


def test_the_ceiling_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("BIONUMBERS_ASK_WARN_USD", raising=False)
    monkeypatch.setenv("BIONUMBERS_ASK_QUESTION_CEILING_USD", "0.25")

    config = Config.from_env()

    assert config.question_ceiling == usd("0.25")
    assert config.warning_threshold == usd("0.20")
