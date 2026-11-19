"""The validator refuses its retired environment names where it reads them (ADR-1900).

Its core may not import `numera_ask`, so it cannot share `config.RENAMED_ENV`; each read site is
checked here because a refusal in one caller protects only that caller (ADR-0250).
"""

import pytest

from numera_validator import cli, environment, openrouter


@pytest.mark.parametrize(("old", "new"), sorted(environment.RENAMED.items()))
def test_a_retired_name_is_refused_at_the_read(monkeypatch, old, new):
    monkeypatch.setenv(old, "anything")
    monkeypatch.setenv(new, "the current value")

    with pytest.raises(environment.RetiredSetting) as raised:
        environment.read(new)

    assert old in str(raised.value)
    assert new in str(raised.value)


def test_the_current_name_is_read_when_nothing_retired_is_set(monkeypatch):
    monkeypatch.setenv("NUMERA_REVIEW_DB_URL", "sqlite:///x.sqlite")

    assert environment.read("NUMERA_REVIEW_DB_URL") == "sqlite:///x.sqlite"


def test_the_command_reports_a_retired_name_and_stops(monkeypatch, capsys):
    """A sentence on stderr and exit 2, the way the command reports its other refusals."""
    monkeypatch.setenv("BIONUMBERS_REVIEW_DB_URL", "sqlite:///old.sqlite")

    assert cli.main(["load", "some-run"]) == 2
    assert "BIONUMBERS_REVIEW_DB_URL is now NUMERA_REVIEW_DB_URL" in capsys.readouterr().err


def test_the_model_client_refuses_a_retired_key_name(monkeypatch):
    """The key is read in the client itself, not in the command, so it is checked there too."""
    monkeypatch.setenv("BIONUMBERS_OPENROUTER_API_KEY", "sk-or-old")

    with pytest.raises(environment.RetiredSetting, match="NUMERA_OPENROUTER_API_KEY"):
        openrouter.OpenRouterModel()
