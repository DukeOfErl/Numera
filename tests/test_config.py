"""Configuration: the configured ceiling, its derived warning, and money for a human.

Both are load-bearing and neither had a test. The ceiling is what the gate
enforces, and format_usd writes the sentence a user reads when a run stops.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scinumbers_ask.config import (
    MICRO_PER_USD,
    RENAMED_ENV,
    WITHDRAWN_ENV,
    Config,
    NotConfigured,
    format_usd,
    micro_from_provider_cost,
    refuse_retired_env,
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
    monkeypatch.delenv("SCINUMBERS_QUESTION_CEILING_USD", raising=False)

    with pytest.raises(NotConfigured) as raised:
        Config.from_env()

    assert "SCINUMBERS_QUESTION_CEILING_USD" in str(raised.value)


def test_the_ceiling_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("BIONUMBERS_ASK_WARN_USD", raising=False)
    monkeypatch.setenv("SCINUMBERS_QUESTION_CEILING_USD", "0.25")

    config = Config.from_env()

    assert config.question_ceiling == usd("0.25")
    assert config.warning_threshold == usd("0.20")


@pytest.mark.parametrize(("old", "new"), sorted(RENAMED_ENV.items()))
def test_a_renamed_variable_is_refused_and_its_replacement_named(monkeypatch, old, new):
    """Ignoring it would be configuration that silently stops being read.

    Every one of these changes what a run does: a ceiling that no longer binds, a
    run label that quietly becomes "dev" and mixes an evaluation's spend into a
    person's, a corpus path that falls back to none. All of them look like a
    working run, so the old name must stop the run rather than be skipped.
    """
    monkeypatch.setenv(old, "anything")

    with pytest.raises(NotConfigured) as raised:
        refuse_retired_env()

    assert old in str(raised.value)
    assert new in str(raised.value)


@pytest.mark.parametrize("new", sorted(RENAMED_ENV.values()))
def test_the_replacement_named_is_one_the_code_actually_reads(new):
    """Otherwise the refusal sends the reader to set a variable nothing reads.

    A typo in the replacement name is invisible from inside the refusal: it raises,
    the message looks right, and the reader follows it into a run configured by
    nothing. Checked against the source rather than a second list, because a second
    list would drift the same way.
    """
    source = Path(__file__).resolve().parents[1] / "src" / "scinumbers_ask"
    read_anywhere = "\n".join(f.read_text(encoding="utf-8") for f in source.glob("*.py"))
    entry_point = (Path(__file__).resolve().parents[1] / "streamlit_app.py").read_text(
        encoding="utf-8"
    )
    assert f'"{new}"' in read_anywhere + entry_point


def test_every_retired_name_shares_the_prefix_that_was_retired():
    """The refusal is a map, and a map only refuses what someone remembered to add.

    This is the cheap half of that: nothing carrying the old prefix should still be
    read. `test_a_renamed_variable_is_refused` covers the other direction.
    """
    source = Path(__file__).resolve().parents[1] / "src" / "scinumbers_ask"
    for path in source.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "config.py":
            continue  # where the retired names are listed in order to be refused
        assert "BIONUMBERS_ASK_" not in text, path.name


def test_a_withdrawn_variable_is_refused_without_being_called_a_rename():
    """"~0.50" as a warning and as a ceiling are different limits.

    A rename message would tell the reader to move the value across, which would
    tighten their spend limit by 20 per cent while appearing to preserve it.
    """
    for old in WITHDRAWN_ENV:
        assert old not in RENAMED_ENV
