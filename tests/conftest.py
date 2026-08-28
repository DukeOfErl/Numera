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
