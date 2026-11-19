"""An evaluation run costs its questions against the tracer's allowance, and asks first.

Spec: `hosted-tracing`, "An evaluation run waits for approval when the tracer's
allowance is at risk". The conditions are pure and tested beside the tracer
(`test_hosted_tracing.py`). Two layers here:

- **The operation** (`run_evaluation`): the refusal lives there, so a caller that
  is not the command -- a notebook, a test, another harness -- is held to it
  too, and gets the `eval` tag without being asked to remember it.
- **The command**: the wording and the prompt. Nothing but a typed `yes`
  approves.

`_ask_one` is replaced by a stub that raises `Asked`. Reaching it means a question
would have been asked, which is exactly the line "before the first question"
draws.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest
from conftest import write_all_shapes_corpus

from numera_ask import eval_cli, evaluation, hosted_trace
from numera_ask.evaluation import RunNotApproved, run_evaluation
from numera_ask.hosted_trace import HostedTracer, Setting, Usage
from numera_ask.question_set import load_question_set

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


class Asked(Exception):
    """Raised where the first question would have been asked."""


class Tracer(HostedTracer):
    """Reports a fixed usage and counts how often it was asked."""

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


class _Recorded:
    """Only what `outstanding` reads: the key."""

    def __init__(self, question_id, repeat):
        self.key = (question_id, repeat)


def _stop_at_the_first_question(monkeypatch, record=lambda question: None):
    calls = []

    def stub(agent, question, repeat, session, provenance):
        calls.append(question.question_id)
        record(question)
        raise Asked(question.question_id)

    monkeypatch.setattr(evaluation, "_ask_one", stub)
    return calls


@pytest.fixture
def asks(monkeypatch):
    """Every question the run would have asked, stopped at the first."""
    return _stop_at_the_first_question(monkeypatch)


@pytest.fixture
def questions(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text("".join(json.dumps(q) + "\n" for q in QUESTIONS))
    return load_question_set(path, None)


def _run_directly(tmp_path, questions, tracer, monkeypatch, **kwargs):
    monkeypatch.setattr(hosted_trace, "current", lambda: tracer)
    return run_evaluation(None, questions, tmp_path / "results.jsonl", None, **kwargs)


# --- the operation: every caller is held to it ------------------------------------


def test_a_direct_caller_at_risk_is_refused_before_the_first_question(
    tmp_path, questions, monkeypatch, asks
):
    """The review finding this layer exists for: the check used to live in the command,
    so a caller of `run_evaluation` itself spent the allowance unasked."""
    with pytest.raises(RunNotApproved) as refused:
        _run_directly(tmp_path, questions, Tracer(usage(30_000)), monkeypatch)
    assert asks == []
    assert not (tmp_path / "results.jsonl").exists()
    assert "more than 50%" in str(refused.value)


def test_a_direct_caller_not_at_risk_proceeds_without_being_asked(
    tmp_path, questions, monkeypatch, asks
):
    """The pair: the same caller, the same absence of `approve`, under half used."""
    with pytest.raises(Asked):
        _run_directly(tmp_path, questions, Tracer(usage(1_000)), monkeypatch)
    assert asks == ["q1"]


def test_a_direct_caller_at_risk_proceeds_when_it_approves(tmp_path, questions, monkeypatch, asks):
    with pytest.raises(Asked):
        _run_directly(
            tmp_path, questions, Tracer(usage(30_000)), monkeypatch, approve=lambda u, e: True
        )


def test_unknown_usage_refuses_a_caller_that_does_not_approve(
    tmp_path, questions, monkeypatch, asks
):
    with pytest.raises(RunNotApproved):
        _run_directly(tmp_path, questions, Tracer(usage(None, traces=None)), monkeypatch)
    assert asks == []


def test_approve_is_shown_the_figures_even_when_no_approval_is_needed(
    tmp_path, questions, monkeypatch, asks
):
    shown = []
    with pytest.raises(Asked):
        _run_directly(
            tmp_path,
            questions,
            Tracer(usage(1_000)),
            monkeypatch,
            approve=lambda u, e: shown.append((u.units, e.questions)) or False,
        )
    # Shown the figures, and its "no" did not stop a run that needed no approval.
    assert shown == [(1_000, 6)]


def test_nothing_left_to_ask_contacts_no_tracer(tmp_path, questions, monkeypatch, asks):
    tracer = Tracer(usage(30_000))
    recorded = tuple(_Recorded(q["question_id"], 1) for q in QUESTIONS)
    monkeypatch.setattr(evaluation, "read_results", lambda path: recorded)
    outcome = _run_directly(tmp_path, questions, tracer, monkeypatch)
    assert tracer.counted == 0
    assert outcome.attempted == 0


def test_repeats_are_validated_before_the_tracer_is_contacted(
    tmp_path, questions, monkeypatch, asks
):
    tracer = Tracer(usage(30_000))
    with pytest.raises(ValueError):
        _run_directly(tmp_path, questions, tracer, monkeypatch, repeats=0)
    assert tracer.counted == 0


def test_every_question_is_asked_inside_the_eval_tag(tmp_path, questions, monkeypatch):
    """Read off the context each question is asked in, because that is where its trace
    begins. From the operation, so every caller gets it without remembering to."""
    from langfuse._client.resource_manager import LangfuseResourceManager
    from opentelemetry import context as otel
    from tracing_doubles import on_setting

    seen = []
    _stop_at_the_first_question(
        monkeypatch, lambda q: seen.append(otel.get_current().get("langfuse.propagated.tags"))
    )

    class On(Tracer):
        def __init__(self):
            HostedTracer.__init__(self, on_setting())
            self._usage = usage(1_000)
            self.counted = 0

    try:
        with pytest.raises(Asked):
            _run_directly(tmp_path, questions, On(), monkeypatch)
    finally:
        LangfuseResourceManager.reset()  # one per public key per process otherwise
    assert seen == [[evaluation.EVAL_TAG]]


def test_with_tracing_off_no_tag_is_in_force(tmp_path, questions, monkeypatch):
    from opentelemetry import context as otel

    seen = []
    _stop_at_the_first_question(
        monkeypatch, lambda q: seen.append(otel.get_current().get("langfuse.propagated.tags"))
    )
    with pytest.raises(Asked):
        _run_directly(tmp_path, questions, Tracer(None), monkeypatch)
    assert seen == [None]


# --- the command: the wording, and only `yes` approves ------------------------------


@pytest.fixture
def run(tmp_path, monkeypatch, asks):
    """`numera-eval run` over six questions, stopped where the first would be asked."""
    path = tmp_path / "questions.jsonl"
    path.write_text("".join(json.dumps(q) + "\n" for q in QUESTIONS))
    corpus = write_all_shapes_corpus(tmp_path)
    results = tmp_path / "results.jsonl"

    def go(tracer, stdin, repeats=1):
        monkeypatch.setattr(hosted_trace, "current", lambda: tracer)
        monkeypatch.setattr("sys.stdin", stdin)
        argv = ["run", str(path), "--corpus", corpus, "--results", str(results)]
        argv += ["--checkpoints", str(tmp_path / "c.sqlite"), "--repeats", str(repeats)]
        eval_cli.main(argv)

    go.asks, go.results = asks, results
    return go


def test_under_half_and_fitting_runs_without_asking(run, capsys):
    stdin = Terminal("")
    with pytest.raises(Asked):
        run(Tracer(usage(1_000)), stdin)
    assert not stdin.read_from
    out = capsys.readouterr().out
    assert "1,000 of 50,000 units (2%)" in out
    assert "This run: 6 attempt(s)" in out


@pytest.mark.parametrize("answer", ["yes\n", "YES\n", " yes \n"])
def test_more_than_half_proceeds_on_yes(run, answer):
    with pytest.raises(Asked):
        run(Tracer(usage(30_000)), Terminal(answer))


@pytest.mark.parametrize("answer", ["no\n", "\n", "", "y\n", "sure\n"])
def test_more_than_half_ends_on_anything_but_yes(run, answer, capsys):
    stdin = Terminal(answer)
    with pytest.raises(SystemExit) as ended:
        run(Tracer(usage(30_000)), stdin)
    assert ended.value.code not in (0, None)
    assert run.asks == []
    assert not run.results.exists()
    assert stdin.read_from
    assert "Paused before the first question" in capsys.readouterr().out


def test_no_terminal_ends_the_run_without_reading(run):
    stdin = Terminal("yes\n", tty=False)
    with pytest.raises(SystemExit):
        run(Tracer(usage(30_000)), stdin)
    assert run.asks == []
    assert not stdin.read_from  # a "yes" that nobody typed must not count


def test_unknown_usage_is_shown_as_unknown_and_pauses(run, capsys):
    with pytest.raises(SystemExit):
        run(Tracer(usage(None, traces=None)), Terminal("no\n"))
    out = capsys.readouterr().out
    assert "unknown" in out
    assert "0%" not in out and "0 of" not in out
    assert run.asks == []


def test_a_run_that_would_not_fit_pauses_under_half(run, capsys):
    """10% used and 500 units a question leaves room for 90 attempts. Six questions
    x 16 repeats is 96 and pauses; x 15 is exactly 90 and runs -- the boundary, and
    the control that differs only in repeats."""
    with pytest.raises(SystemExit):
        run(Tracer(usage(5_000, traces=10)), Terminal("no\n"), repeats=16)
    assert "exceed" in capsys.readouterr().out
    with pytest.raises(Asked):
        run(Tracer(usage(5_000, traces=10)), Terminal(""), repeats=15)


def test_tracing_off_asks_nothing_and_says_nothing(run, capsys):
    stdin = Terminal("")
    with pytest.raises(Asked):
        run(Tracer(None), stdin)
    assert not stdin.read_from
    assert "Hosted tracing" not in capsys.readouterr().out


def test_a_resumed_run_estimates_only_what_it_still_has_to_ask(run, capsys, monkeypatch):
    """Two repeats of six, one answer already recorded: eleven attempts, not twelve."""
    monkeypatch.setattr(evaluation, "read_results", lambda path: ())
    with pytest.raises(Asked):
        run(Tracer(usage(1_000)), Terminal(""), repeats=2)
    assert "This run: 12 attempt(s)" in capsys.readouterr().out

    monkeypatch.setattr(evaluation, "read_results", lambda path: (_Recorded("q1", 1),))
    with pytest.raises(Asked):
        run(Tracer(usage(1_000)), Terminal(""), repeats=2)
    assert "This run: 11 attempt(s)" in capsys.readouterr().out
