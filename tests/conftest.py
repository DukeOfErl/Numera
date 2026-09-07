"""Fixtures shared across the suites.

The ask fixtures drive a real AskAgent over the sample corpus with a scripted
model, so they live here rather than being duplicated per module. The ingest
fixture supplies a synthetic export in the published file's shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scinumbers_ask.agent import AskAgent
from scinumbers_ask.config import Config, usd
from scinumbers_ask.corpus import load
from scinumbers_ask.repository import CorpusRepository

FIXTURE = str(Path(__file__).parent / "fixtures" / "corpus_sample.jsonl")


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr("scinumbers_ask.agent.RETRY_INITIAL_DELAY", 0.0)


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
    monkeypatch.setenv("SCINUMBERS_TRACE", str(tmp_path / "trace.jsonl"))


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


@pytest.fixture
def sample_html() -> Path:
    """A synthetic export in the published file's exact shape.

    The identifiers are deliberately outside the real corpus's range (`9xxxxx`)
    and the content is invented, so no BioNumbers data enters this repository —
    see ADR-0200. What the fixture reproduces faithfully is the *structure* and
    the quirks: `<td>` header cells, the text-marker apostrophe, HTML-escaped
    injected markup, entity-encoded micrometre glyphs, a link-only range, and a
    trailing padding row. Behaviour against the real file is verified separately
    against a locally-fetched export, never from a committed copy of it.
    """
    return Path(__file__).parent / "fixtures" / "sample_table.html"
