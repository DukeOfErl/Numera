"""Fixtures shared across the suites.

The ask fixtures drive a real AskAgent over the sample corpus with a scripted
model, so they live here rather than being duplicated per module. The ingest
fixture supplies a synthetic export in the published file's shape.
"""

from __future__ import annotations

import json
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


@pytest.fixture(autouse=True)
def _each_test_starts_with_no_open_sessions():
    """The session cap's registry is a cached resource: one per process, which
    is what a cap on a server needs and exactly wrong for a test process that
    opens a fresh `AppTest` session per test. Without this the twenty-first web
    test in a run is turned away with "try again shortly" -- sixty failures
    that pass one at a time. Imported lazily so tests that never touch the web
    driver do not pay for Streamlit."""
    from scinumbers_ask import web

    web.session_registry.clear()
    yield
    web.session_registry.clear()


@pytest.fixture
def config() -> Config:
    return Config(model="fake/model", question_ceiling=usd("0.60"), run_budget=usd("1.20"))


@pytest.fixture
def repo() -> CorpusRepository:
    return CorpusRepository(load(FIXTURE))


def agent_with(repo, config, tmp_path, model, name="checkpoints.sqlite") -> AskAgent:
    return AskAgent(repo, config, str(tmp_path / name), model=model)


class RecordingEngine:
    """An engine double that keeps every statement and parameter set it was given.

    One definition for the tests that read back *what was written* — the trail's
    identifiers, the identity columns, a feedback row. There were four
    hand-written copies of this, disagreeing on what they filtered on, so a
    column added to `trail_store._INSERT` had to be chased through each: a copy
    that happened to keep passing hid that the column it should have asserted on
    never arrived.

    Two doubles deliberately do **not** use this and say so where they are
    defined: `test_trail_store.py` needs the `SET LOCAL` to succeed while only
    the INSERT fails, and `test_accounts.py` needs a SELECT to return a row.
    Simulating a specific failure point is the thing those tests are for, and a
    shared double with a predicate for it would be harder to read than either.
    """

    def __init__(self, fail: Exception | None = None, fail_on_begin: Exception | None = None):
        # Two failure points, kept apart because they are different code paths in
        # the caller: opening the transaction, and executing the statement. A
        # double that conflated them would leave one untested while looking
        # thorough -- `test_trail_store.py` makes the same distinction and says so.
        self.fail = fail
        self.fail_on_begin = fail_on_begin
        self.conns: list[_RecordingConn] = []

    def begin(self):
        if self.fail_on_begin is not None:
            raise self.fail_on_begin
        conn = _RecordingConn(self.fail)
        self.conns.append(conn)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()

    @property
    def params(self) -> list[dict]:
        """Every parameter set handed to any statement, in order."""
        return [p for c in self.conns for p in c.params]

    @property
    def written(self) -> list[dict]:
        """Every parameter set that carried a record — the rows a reader would see."""
        return [p for p in self.params if "event" in p]


class _RecordingConn:
    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        if self.fail is not None:
            raise self.fail
        if params is not None:
            self.params.append(dict(params))
        return None


def ask_question(at, question: str):
    """Drive one question through the real page and return the rerun.

    One copy, because there were three byte-identical ones and the page now has
    more than one thing that can stand where the input does -- a closed door, a
    try-later notice -- so `at.chat_input[0]` is the assumption that breaks first.
    """
    return at.chat_input[0].set_value(question).run()


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


def write_all_shapes_corpus(tmp_path) -> str:
    """A six-entry corpus carrying all six of `question_set`'s entry shapes.

    `corpus_sample.jsonl` cannot serve here: it holds two of the six and no
    complete entry, so a question set that satisfies the shape rule cannot be
    written against it. Both the question-set suite and the evaluation command's
    suite need this, which is why it lives here.
    """
    base = dict(
        property="Cell volume",
        organism="Bacteria Escherichia coli",
        units="um^3",
        value=1.0,
        reference="r",
        measurement_method="electron microscopy",
    )
    records = [
        {**base, "entry_id": 1},
        {**base, "entry_id": 2, "value": None, "range_low": 1.0, "range_high": 2.0},
        {**base, "entry_id": 3, "units": "wibbles"},
        {**base, "entry_id": 4, "range_fused": True},
        {**base, "entry_id": 5, "measurement_method": ""},
        {**base, "entry_id": 6, "range_approximate": True},
    ]
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return str(path)
