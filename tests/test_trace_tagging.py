"""Run identity on every record.

The point is separability after the fact. A total that mixes an evaluation run
with hand-driven use cannot be split later, because the records already written
carry nothing to filter on -- which is why this is worth doing before there is
anything to separate rather than after.
"""

from __future__ import annotations

import io
import json

from bionumbers_ask.config import Config, usd
from bionumbers_ask.events import QuestionEnded
from bionumbers_ask.trace import configure, start_question

from agent_doubles import costing, says, scripted, tool_call
from conftest import agent_with


def records(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_every_record_carries_the_run_label():
    buf = io.StringIO()
    configure(buf)
    trace = start_question("eval-2026-08-24")
    trace.record("search", matched=3)
    trace.record("entry.retrieved", bnid=100002)

    written = records(buf)
    assert [r["run"] for r in written] == ["eval-2026-08-24"] * 2
    # And the per-question identifier still ties one question's records together.
    assert len({r["question_id"] for r in written}) == 1


def test_two_runs_are_separable_in_one_trail():
    buf = io.StringIO()
    configure(buf)
    start_question("eval").record("spend.increment", increment=10)
    start_question("dev").record("spend.increment", increment=7)

    by_run = {r["run"]: r["increment"] for r in records(buf)}
    assert by_run == {"eval": 10, "dev": 7}


def test_the_run_label_reaches_the_frameworks_own_run_config():
    """Tags and metadata cannot be retrofitted onto traces already recorded."""
    config = start_question("eval").run_config("ask")
    assert "run:eval" in config["tags"]
    assert config["metadata"]["run"] == "eval"


def test_the_run_label_defaults_rather_than_going_missing():
    assert start_question().run_label == "dev"
    assert Config(model="m", warning_threshold=1, run_budget=2).run_label == "dev"


def test_a_blank_environment_value_does_not_produce_an_unlabelled_run(monkeypatch):
    monkeypatch.setenv("BIONUMBERS_ASK_RUN", "   ")
    assert Config.from_env().run_label == "dev"
    monkeypatch.setenv("BIONUMBERS_ASK_RUN", "eval-2026-08-24")
    assert Config.from_env().run_label == "eval-2026-08-24"


def test_a_question_records_its_run_label_and_the_model_it_spent_on(repo, tmp_path):
    """The two dimensions a spend total has to be splittable by.

    Without the model on the increment, a trail spanning a model change can only
    be split by joining every record back to its ending event.
    """
    buf = io.StringIO()
    configure(buf)
    config = Config(
        model="fake/model",
        warning_threshold=usd("0.50"),
        run_budget=usd("1.20"),
        run_label="eval-2026-08-24",
    )
    model = scripted(
        costing(tool_call("search_entries", property="Cell"), 0.000_010),
        costing(says("about 1 micrometre (BNID 100002)"), 0.000_010),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    assert next(e for e in events if isinstance(e, QuestionEnded)).spend == 20

    increments = [r for r in records(buf) if r["event"] == "spend.increment"]
    assert len(increments) == 2, "one record per model call"
    assert {r["model"] for r in increments} == {"fake/model"}
    assert {r["run"] for r in increments} == {"eval-2026-08-24"}
    # Spend for this run, reconstructed from the trail alone.
    assert sum(r["increment"] for r in increments) == 20
