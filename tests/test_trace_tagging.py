"""Run identity on every record.

The point is separability after the fact. A total that mixes an evaluation run
with hand-driven use cannot be split later, because the records already written
carry nothing to filter on -- which is why this is worth doing before there is
anything to separate rather than after.
"""

from __future__ import annotations

import io
import json

import pytest
from conftest import agent_with

from agent_doubles import costing, says, scripted, tool_call
from bionumbers_ask.config import Config, usd
from bionumbers_ask.events import QuestionEnded
from bionumbers_ask.trace import configure, start_question


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


def test_the_increment_records_the_tokens_behind_the_cost(repo, tmp_path):
    """Cost alone cannot separate a reprice from deeper retrieval.

    Both raise the bill; only one is a regression somebody shipped. The tokens are
    already in the response, so recording them is what makes the two separable
    later -- and, like the run label, cannot be added to records already written.
    """
    buf = io.StringIO()
    configure(buf)
    config = Config(model="fake/model", warning_threshold=usd("0.50"), run_budget=usd("1.20"))
    # The pinned OpenRouter shape: 14 prompt tokens, 4 completion, $0.000034.
    model = scripted(says("about 1 micrometre (BNID 100002)"))
    list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    increment = next(r for r in records(buf) if r["event"] == "spend.increment")
    assert (increment["prompt_tokens"], increment["completion_tokens"]) == (14, 4)
    assert increment["increment"] == 34


def test_a_provider_reporting_no_tokens_is_recorded_as_unknown_not_zero():
    """Zero tokens is a measurement; no tokens is an absence. They must differ."""
    from langchain_core.messages import AIMessage

    from bionumbers_ask.spend import SpendLedger

    ledger = SpendLedger(model="m", prices=None)
    charge = ledger.add_response(
        [AIMessage(content="ok", response_metadata={"token_usage": {"cost": 3.4e-05}})]
    )
    assert charge.micro == 34
    assert charge.prompt_tokens is None and charge.completion_tokens is None


def test_usage_metadata_is_read_when_the_provider_shape_is_absent():
    """The framework's normalised form, which a different client may populate instead."""
    from agent_doubles import reports_usage_only
    from bionumbers_ask.config import ModelPrices
    from bionumbers_ask.spend import SpendLedger

    ledger = SpendLedger(model="m", prices=ModelPrices(1_000_000, 5_000_000))
    charge = ledger.add_response([reports_usage_only("ok", input_tokens=1_000, output_tokens=100)])
    assert (charge.prompt_tokens, charge.completion_tokens) == (1_000, 100)
    assert charge.micro == 1_500


def test_tokens_from_several_assistant_messages_in_one_response_are_summed():
    """Rare but reachable, and the branch where unknown-versus-zero actually bites."""
    from langchain_core.messages import AIMessage

    from agent_doubles import OPENROUTER_RESPONSE_METADATA, reports_usage_only
    from bionumbers_ask.config import ModelPrices
    from bionumbers_ask.spend import SpendLedger

    # Prices configured, because the second message reports usage and no cost --
    # without them the ledger correctly refuses rather than guessing.
    ledger = SpendLedger(model="m", prices=ModelPrices(1_000_000, 5_000_000))
    charge = ledger.add_response(
        [
            AIMessage(content="a", response_metadata=OPENROUTER_RESPONSE_METADATA),
            reports_usage_only("b", input_tokens=100, output_tokens=10),
        ]
    )
    # 14 + 100 and 4 + 10: the reported figures added, neither treated as zero.
    assert (charge.prompt_tokens, charge.completion_tokens) == (114, 14)
    # Reported cost for the first, the price table for the second: 34 + 150.
    assert charge.micro == 184


def test_a_known_count_beside_an_unknown_one_keeps_the_known_figure():
    from langchain_core.messages import AIMessage

    from agent_doubles import OPENROUTER_RESPONSE_METADATA
    from bionumbers_ask.spend import SpendLedger

    ledger = SpendLedger(model="m", prices=None)
    charge = ledger.add_response(
        [
            AIMessage(content="a", response_metadata=OPENROUTER_RESPONSE_METADATA),
            AIMessage(content="b", response_metadata={"token_usage": {"cost": 1e-06}}),
        ]
    )
    assert (charge.prompt_tokens, charge.completion_tokens) == (14, 4)
    assert charge.micro == 35


# -- pointing the trail somewhere a real run can be read from --------------


def test_the_driver_writes_a_trail_when_it_runs(tmp_path, monkeypatch):
    """The gap this closes: `configure` was called only from tests, so every record
    a real run produced was discarded -- at INFO, through a handler-less root, which
    drops it at WARNING without raising. The trail vanished exactly where nobody
    would think to look.

    Driven through `main` rather than by asserting the default is non-empty. An
    earlier version of this test checked the constant and the function existed,
    which passed just as happily with the call removed from `main` -- the same blind
    spot that let the original defect through.

    No API key, so the question ends unconfigured. That is enough: an ending is a
    record, and what is under test is whether anything reaches the file at all.
    """
    from conftest import FIXTURE

    from bionumbers_ask.cli import DEFAULT_TRACE, main

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["--corpus", FIXTURE, "--checkpoints", str(tmp_path / "c.sqlite"), "--ask", "q"])

    written = (tmp_path / DEFAULT_TRACE).read_text()
    assert '"event": "not_configured"' in written, written


def test_the_trail_is_written_as_json_lines_to_the_given_path(tmp_path):
    from bionumbers_ask.cli import configure_trace

    path = tmp_path / "nested" / "trace.jsonl"
    configure_trace(str(path))
    start_question("run-a").record("search", matched=7)

    written = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert [(r["event"], r["run"], r["matched"]) for r in written] == [("search", "run-a", 7)]


def test_the_trail_can_be_sent_to_stderr(capsys):
    """Never stdout: the rendered answer and the table go there, and interleaving
    JSON with them would corrupt both."""
    from bionumbers_ask.cli import configure_trace

    configure_trace("-")
    start_question("run-b").record("search", matched=1)
    captured = capsys.readouterr()
    assert '"matched": 1' in captured.err
    assert captured.out == ""


def test_an_empty_spec_adds_no_handler_and_writes_no_file(tmp_path, monkeypatch):
    """Opting out has to be genuinely silent -- not a file quietly created and left
    empty, which reads as a trail that recorded nothing."""
    import logging

    from bionumbers_ask.cli import configure_trace
    from bionumbers_ask.trace import LOGGER_NAME

    logger = logging.getLogger(LOGGER_NAME)
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.chdir(tmp_path)

    configure_trace("")
    assert logger.handlers == []
    assert not list(tmp_path.iterdir())
