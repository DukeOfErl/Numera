"""Fixtures shared by the agent and spend suites.

Both drive a real AskAgent over the sample corpus with a scripted model, so the
fixtures live here rather than being duplicated per module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bionumbers_ask.agent import AskAgent
from bionumbers_ask.config import Config, usd
from bionumbers_ask.corpus import load
from bionumbers_ask.repository import CorpusRepository

FIXTURE = str(Path(__file__).parent / "fixtures" / "corpus_sample.jsonl")


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr("bionumbers_ask.agent.RETRY_INITIAL_DELAY", 0.0)


@pytest.fixture(autouse=True)
def _trail_stays_in_the_tmp_dir(tmp_path, monkeypatch):
    """Keep the structured trail out of the working directory.

    `--trace` defaults to `logs/trace.jsonl` *relative to the cwd*, so five driver
    tests that call `main()` without it were writing into whatever directory pytest
    was started from. Harmless in this repo, where the path is git-ignored, and a
    hard failure anywhere the cwd is not writable: a peer running this suite from
    another checkout got `OSError: [Errno 30] Read-only file system` on exactly
    those five and reported them as our failing tests.

    Set through the documented environment variable rather than by patching, so the
    path a real run takes is the one under test.
    """
    monkeypatch.setenv("BIONUMBERS_ASK_TRACE", str(tmp_path / "trace.jsonl"))


@pytest.fixture
def config() -> Config:
    return Config(model="fake/model", question_ceiling=usd("0.60"), run_budget=usd("1.20"))


@pytest.fixture
def repo() -> CorpusRepository:
    return CorpusRepository(load(FIXTURE))


def agent_with(repo, config, tmp_path, model, name="checkpoints.sqlite") -> AskAgent:
    return AskAgent(repo, config, str(tmp_path / name), model=model)


def run(agent: AskAgent, session: str, question: str) -> list:
    return list(agent.ask(session, question))
