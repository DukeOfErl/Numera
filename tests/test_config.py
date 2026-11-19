"""Configuration: the configured ceiling, its derived warning, and money for a human.

Both are load-bearing and neither had a test. The ceiling is what the gate
enforces, and format_usd writes the sentence a user reads when a run stops.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from numera_ask.config import (
    MICRO_PER_USD,
    RENAMED_ENV,
    WITHDRAWN_ENV,
    Config,
    NotConfigured,
    env_setting,
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
    monkeypatch.delenv("NUMERA_QUESTION_CEILING_USD", raising=False)

    with pytest.raises(NotConfigured) as raised:
        Config.from_env()

    assert "NUMERA_QUESTION_CEILING_USD" in str(raised.value)


def test_the_ceiling_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("BIONUMBERS_ASK_WARN_USD", raising=False)
    monkeypatch.setenv("NUMERA_QUESTION_CEILING_USD", "0.25")

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


ROOT = Path(__file__).resolve().parents[1]


def _env_reads() -> str:
    """Every environment *read* in the package and the entry point, as text.

    The call sites, not the whole file. Matching a bare quoted name against the
    source cannot fail: `config.py` holds every replacement name as a value in
    `RENAMED_ENV`, so the map would satisfy a check on itself and a typo in a
    replacement would pass. That is a check that reports a verdict it can only
    ever give one way, which is worse than no check -- it retires the suspicion
    that would otherwise have found the bug.
    """
    files = [*(ROOT / "src" / "numera_ask").glob("*.py"), ROOT / "streamlit_app.py"]
    text = "\n".join(f.read_text(encoding="utf-8") for f in files)
    # A read through a named constant (`env_setting(SETTING)`, `os.environ.get(URL_ENV)`)
    # is still a read, so a module-level `NAME = "VALUE"` is resolved on the read lines.
    # The map's own values are dictionary entries, not such assignments, so they still
    # cannot satisfy this check. `_number` is `web.py`'s tolerant numeric reader over
    # `env_setting`.
    constants = dict(re.findall(r'(?m)^([A-Z][A-Z0-9_]*) = "([A-Z][A-Z0-9_]*)"$', text))
    reads = [
        line
        for line in text.splitlines()
        if "os.environ" in line or "env_setting(" in line or "_number(" in line
    ]
    return "\n".join(
        re.sub(r"\b[A-Z][A-Z0-9_]*\b", lambda m: constants.get(m[0], m[0]), line) for line in reads
    )


@pytest.mark.parametrize("new", sorted(RENAMED_ENV.values()))
def test_the_replacement_named_is_one_the_code_actually_reads(new):
    """Otherwise the refusal sends the reader to set a variable nothing reads.

    A typo in the replacement name is invisible from inside the refusal: it raises,
    the message looks right, and the reader follows it into a run configured by
    nothing.
    """
    assert new in _env_reads()


def test_no_replacement_is_itself_retired():
    """A name retired twice names the variable to set now (ADR-1900).

    `BIONUMBERS_ASK_CORPUS` became `SCINUMBERS_CORPUS` and then `NUMERA_CORPUS`. Left
    pointing at the intermediate name, the refusal sends the reader to a variable that
    is refused in turn -- a loop, with each message looking right on its own. Checked
    over every entry and every withdrawn name's guidance, not one example.
    """
    retired = set(RENAMED_ENV) | set(WITHDRAWN_ENV)
    assert {old: new for old, new in RENAMED_ENV.items() if new in retired} == {}
    for old, guidance in WITHDRAWN_ENV.items():
        named = {name for name in retired if re.search(rf"\b{name}\b", guidance)}
        assert named == set(), f"{old}'s guidance names retired {sorted(named)}"


def test_a_name_retired_twice_is_refused_with_the_current_name(monkeypatch):
    """The scenario end to end, on the corpus variable both renames touched."""
    monkeypatch.setenv("BIONUMBERS_ASK_CORPUS", "/somewhere/corpus.jsonl")

    with pytest.raises(NotConfigured) as raised:
        refuse_retired_env()

    assert "NUMERA_CORPUS" in str(raised.value)
    assert "SCINUMBERS_CORPUS" not in str(raised.value)


#: Every `SCINUMBERS_*` setting the code read before rename-to-numera, from a survey of `dev`
#: at ecc1cf4 -- written out here, not derived from `RENAMED_ENV`, because a test built from
#: the map loses its case when an entry is deleted. `SCINUMBERS_TEST_WORKERS` is absent on
#: purpose: only `bin/testloop.py` reads it (ADR-1900).
RETIRED_BY_NUMERA = (
    "CORPUS", "STORE", "RUN", "TRACING", "CHECKPOINTS", "TRACE", "TRAIL_READ_URL",
    "RUN_BUDGET_USD", "QUESTION_CEILING_USD", "MODEL", "MAX_SESSIONS", "SESSION_IDLE_S",
)  # fmt: skip


@pytest.mark.parametrize("suffix", RETIRED_BY_NUMERA)
def test_each_name_retired_by_the_numera_rename_is_refused(suffix):
    assert RENAMED_ENV.get(f"SCINUMBERS_{suffix}") == f"NUMERA_{suffix}"


def test_no_retired_name_is_still_being_read():
    """The other direction, and the one the first version of this exempted.

    `config.py` was skipped wholesale because it lists the retired names in order
    to refuse them -- which also skipped almost every environment read in the
    package. A read left on the old name there is refused by `refuse_retired_env`
    *and* ignored by the reader, so the setting becomes unconfigurable and its
    default is used for ever: a run that looks like it is working.

    Scanning the read lines rather than whole files distinguishes the two.
    """
    reads = _env_reads()
    for old in [*RENAMED_ENV, *WITHDRAWN_ENV]:
        assert old not in reads, old


@pytest.mark.parametrize("old", sorted(WITHDRAWN_ENV))
def test_a_withdrawn_variable_is_refused_without_being_called_a_rename(monkeypatch, old):
    """ "0.50" as a warning and as a ceiling are different limits.

    A rename message would tell the reader to move the value across, which would
    tighten their spend limit by 20 per cent while appearing to preserve it. So
    these are refused, like a rename, but never *described* as one.
    """
    assert old not in RENAMED_ENV
    monkeypatch.setenv(old, "0.50")

    with pytest.raises(NotConfigured) as raised:
        refuse_retired_env()

    message = str(raised.value)
    assert old in message
    assert "no longer exists" in message
    assert "Rename it" not in message


def test_a_setting_read_without_a_driver_is_still_refused(monkeypatch):
    """The second-caller audit, which is what put the guard here rather than in main.

    The corpus, the trail and the checkpoint store never pass through `Config`, so
    a refusal living in the two drivers protected exactly the two callers that
    existed. The architecture note says the evaluation harness will be a third
    adapter -- and a harness reading the trail path directly would have written its
    trail to the default while a stale name sat exported, with nothing reporting a
    fault.
    """
    monkeypatch.setenv("BIONUMBERS_ASK_TRACE", "/somewhere/trace.jsonl")

    with pytest.raises(NotConfigured) as raised:
        env_setting("NUMERA_TRACE", "logs/trace.jsonl")

    assert "NUMERA_TRACE" in str(raised.value)
