"""An evaluation run shows the tracer's allowance and pauses for approval when it is at risk.

Spec: `hosted-tracing`, "An evaluation run waits for approval when the tracer's
allowance is at risk". The conditions themselves are pure and are tested in
`test_hosted_tracing.py`; these tests are about the command: that it asks
before the first question, that nothing but `yes` proceeds, and that a refusal
leaves nothing behind -- no results file, no model call.

`run_evaluation` is replaced by a recorder, which is what "before the first
question" means here: if it was called, a question could have been asked.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest
from conftest import write_all_shapes_corpus

from scinumbers_ask import eval_cli, hosted_trace
from scinumbers_ask.hosted_trace import HostedTracer, Setting, Usage

#: Six questions, one per entry shape: a run refuses a set that leaves a shape out.
QUESTIONS = [
    {
        "question_id": f"q{identifier}",
        "question": "How big is an E. coli cell?",
        "asked_properties": "Cell volume",
        "asked_organisms": "Bacteria Escherichia coli",
        "expected_entries": [identifier],
    }
    for identifier in range(1, 7)
]


class Tracer(HostedTracer):
    """Reports a fixed usage; counts how often it was asked."""

    def __init__(self, usage: Usage | None):
        super().__init__(Setting(on=usage is not None))
        self._usage = usage
        self.counted = 0

    def monthly_usage(self, now=None):
        self.counted += 1
        return self._usage


def usage(units, traces=100):
    now = datetime(2026, 9, 24, tzinfo=UTC)
    return Usage(units=units, traces=traces, since=now, until=now)


class Terminal(io.StringIO):
    def __init__(self, text: str, tty: bool = True):
        super().__init__(text)
        self.tty = tty
        self.read_from = False

    def isatty(self):
        return self.tty

    def readline(self, *args):
        self.read_from = True
        return super().readline(*args)


@pytest.fixture
def run(tmp_path, monkeypatch):
    """`scinumbers-eval run` over one question, with the run itself recorded, not performed."""
    calls = []
    monkeypatch.setattr(eval_cli, "run_evaluation", lambda *a, **k: calls.append(a) or _done())
    questions = tmp_path / "questions.jsonl"
    questions.write_text("".join(json.dumps(q) + "\n" for q in QUESTIONS))
    corpus = write_all_shapes_corpus(tmp_path)
    results = tmp_path / "results.jsonl"

    def go(tracer, stdin, repeats=1):
        monkeypatch.setattr(hosted_trace, "current", lambda: tracer)
        monkeypatch.setattr("sys.stdin", stdin)
        argv = ["run", str(questions), "--corpus", corpus, "--results", str(results)]
        argv += ["--checkpoints", str(tmp_path / "c.sqlite"), "--repeats", str(repeats)]
        eval_cli.main(argv)

    go.calls, go.results = calls, results
    return go


def _done():
    from scinumbers_ask.evaluation import Outcome

    return Outcome()


def test_under_half_and_fitting_runs_without_asking(run, capsys):
    stdin = Terminal("")
    run(Tracer(usage(1_000)), stdin)
    assert run.calls
    assert not stdin.read_from
    out = capsys.readouterr().out
    assert "1,000 of 50,000 units (2%)" in out
    assert "This run: 6 question(s)" in out


@pytest.mark.parametrize("answer", ["yes\n", "YES\n", " yes \n"])
def test_more_than_half_proceeds_on_yes(run, answer):
    run(Tracer(usage(30_000)), Terminal(answer))
    assert run.calls


@pytest.mark.parametrize("answer", ["no\n", "\n", "", "y\n", "sure\n"])
def test_more_than_half_ends_on_anything_but_yes(run, answer, capsys):
    stdin = Terminal(answer)
    with pytest.raises(SystemExit) as ended:
        run(Tracer(usage(30_000)), stdin)
    assert ended.value.code not in (0, None)
    assert run.calls == []
    assert not run.results.exists()
    assert stdin.read_from
    assert "Paused before the first question" in capsys.readouterr().out


def test_no_terminal_ends_the_run_without_reading(run):
    stdin = Terminal("yes\n", tty=False)
    with pytest.raises(SystemExit):
        run(Tracer(usage(30_000)), stdin)
    assert run.calls == []
    assert not stdin.read_from  # a "yes" that nobody typed must not count


def test_unknown_usage_is_shown_as_unknown_and_pauses(run, capsys):
    with pytest.raises(SystemExit):
        run(Tracer(usage(None, traces=None)), Terminal("no\n"))
    out = capsys.readouterr().out
    assert "unknown" in out
    assert "0%" not in out and "0 of" not in out
    assert run.calls == []


def test_a_run_that_would_not_fit_pauses_under_half(run, capsys):
    """10% used and 500 units a question leaves room for 90 questions. Six questions
    x 16 repeats is 96 and pauses; x 15 is exactly 90 and runs -- the boundary, and
    the control that differs only in repeats."""
    with pytest.raises(SystemExit):
        run(Tracer(usage(5_000, traces=10)), Terminal("no\n"), repeats=16)
    assert "exceed" in capsys.readouterr().out
    run(Tracer(usage(5_000, traces=10)), Terminal(""), repeats=15)
    assert run.calls


def test_tracing_off_counts_nothing_and_asks_nothing(run, capsys):
    tracer = Tracer(None)
    stdin = Terminal("")
    run(tracer, stdin)
    assert run.calls
    assert not stdin.read_from
    assert "Hosted tracing" not in capsys.readouterr().out


def test_a_resumed_run_estimates_only_what_it_still_has_to_ask(run, capsys):
    """Two repeats of six, one answer already recorded: eleven to ask, not twelve."""
    from scinumbers_ask import evaluation

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(evaluation, "read_results", lambda path: ())
        run(Tracer(usage(1_000)), Terminal(""), repeats=2)
    assert "This run: 12 question(s)" in capsys.readouterr().out

    recorded = _a_recorded_result("q1", repeat=1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(evaluation, "read_results", lambda path: (recorded,))
        run(Tracer(usage(1_000)), Terminal(""), repeats=2)
    assert "This run: 11 question(s)" in capsys.readouterr().out


def _a_recorded_result(question_id, repeat):
    """Only what `outstanding` reads: the key."""

    class Recorded:
        key = (question_id, repeat)

    return Recorded()
