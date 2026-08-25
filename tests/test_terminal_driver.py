"""The terminal driver: rendering, when to stop, and holding no state.

The last of those is the point of the port. If the driver accumulated anything --
the conversation, spend, a ceiling -- the web driver could not replace it, because
a framework that re-runs its script on every interaction has nowhere to keep it.
"""

from __future__ import annotations

import io

import pytest

from bionumbers_ask.cli import render, run
from bionumbers_ask.config import Config, usd
from bionumbers_ask.events import (
    Answer,
    ConversationWarning,
    CostProjection,
    EndReason,
    QuestionEnded,
    QuestionStarted,
    Retrieval,
    SpendWarning,
)

from agent_doubles import costing, says, scripted, tool_call
from conftest import agent_with


def ended(reason, **kwargs):
    defaults = dict(
        question_id="q", reason=reason, spend=110, run_spend=220,
        model="fake/model", tool_calls=3,
    )
    return QuestionEnded(**{**defaults, **kwargs})


# -- rendering ------------------------------------------------------------


def test_a_retrieval_shows_the_tool_and_what_it_was_asked():
    line = render(Retrieval(question_id="q", tool="search_entries",
                            detail={"property": "Cell volume", "matched": 12}))
    assert "search_entries" in line
    assert "'Cell volume'" in line and "matched=12" in line


def test_a_retrieval_omits_absent_detail_rather_than_showing_none():
    line = render(Retrieval(question_id="q", tool="get_entry",
                            detail={"bnid": 100002, "organism": None}))
    assert "bnid=100002" in line
    assert "None" not in line


def test_an_answer_is_rendered_as_itself():
    assert "1 micrometre (BNID 100002)" in render(
        Answer(question_id="q", text="1 micrometre (BNID 100002)")
    )


def test_the_ending_reports_the_reason_the_spend_the_run_and_the_model():
    """Spend is only interpretable next to the model that incurred it."""
    line = render(ended(EndReason.ANSWERED))
    assert "answered" in line
    assert "$0.000110" in line and "run $0.000220" in line
    assert "fake/model" in line and "3 tool calls" in line
    assert "incomplete" not in line


def test_an_incomplete_ending_says_so():
    assert "(incomplete)" in render(ended(EndReason.SPEND_CEILING, incomplete=True))


@pytest.mark.parametrize(
    "event",
    [
        ConversationWarning(question_id="q", messages=45, bound=60),
        SpendWarning(question_id="q", spent=usd("0.55"), threshold=usd("0.50")),
        CostProjection(question_id="q", projected=usd("0.80"), threshold=usd("0.50")),
    ],
)
def test_every_warning_is_shown_rather_than_swallowed(event):
    """A warning a driver drops is a warning the user never had."""
    line = render(event)
    assert line is not None and line.strip()


def test_the_start_event_needs_no_line():
    """The user typed the question; echoing it back is noise."""
    assert render(QuestionStarted(question_id="q", session_id="s", question="how wide?")) is None


# -- the loop -------------------------------------------------------------


def test_a_question_renders_retrieval_then_answer_then_the_ending(repo, config, tmp_path):
    out = io.StringIO()
    model = scripted(tool_call("search_entries", property="Cell"),
                     says("about 1 micrometre (BNID 100002)"))
    assert run(agent_with(repo, config, tmp_path, model), "s", ["how wide?"], out) == 0

    text = out.getvalue()
    assert text.index("search_entries") < text.index("BNID 100002") < text.index("answered")


def test_a_blank_line_is_not_put_to_the_agent(repo, config, tmp_path):
    out = io.StringIO()
    model = scripted(says("an answer"))
    run(agent_with(repo, config, tmp_path, model), "s", ["", "   ", "a real question"], out)
    assert model.attempts == 1, "a blank line was charged for"


class Counting:
    """The real agent, with every question put to it recorded.

    The driver's claim is about control flow -- which questions it puts to the
    agent -- so that is what this makes observable. Asserting over rendered text
    instead would couple the test to a line prefix, which is cosmetic: changing how
    an ending is printed would fail a test about when the loop stops.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.asked: list[str] = []

    def ask(self, session_id: str, question: str):
        self.asked.append(question)
        yield from self._inner.ask(session_id, question)


def test_the_run_stops_when_the_budget_is_spent(repo, config, tmp_path):
    """Continuing would put the same refusal on every remaining question."""
    budgeted = Config(model=config.model, warning_threshold=usd("0.50"),
                      run_budget=usd("0.000050"))
    out = io.StringIO()
    model = scripted(costing(says("an answer"), 0.000_110))
    agent = Counting(agent_with(repo, budgeted, tmp_path, model))

    run(agent, "s", ["first", "second", "third"], out)

    # The second question is refused by the agent, before dispatch. The third is
    # never asked at all, and only the driver can be responsible for that -- which
    # is why the model call count cannot stand in for this: the agent's own
    # pre-dispatch guard keeps it at one whether the loop stops or not.
    assert agent.asked == ["first", "second"]
    assert model.attempts == 1
    assert "run_budget" in out.getvalue()


def test_a_missing_key_exits_non_zero_rather_than_looping(repo, config, tmp_path, monkeypatch):
    from bionumbers_ask.agent import AskAgent

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = io.StringIO()
    agent = AskAgent(repo, config, str(tmp_path / "u.sqlite"))
    assert run(agent, "s", ["first", "second"], out) == 1
    assert "not_configured" in out.getvalue()


# -- the driver holds no state -------------------------------------------


def test_the_conversation_survives_a_new_call_to_the_driver(repo, config, tmp_path):
    """Two separate run() calls, one session: the follow-up still has context.

    If the driver were keeping the conversation, the second call would start from
    nothing. It comes from the checkpoint instead, which is the property the web
    driver depends on -- its script re-runs on every interaction.
    """
    model = scripted(says("first answer"), says("second answer"))
    agent = agent_with(repo, config, tmp_path, model)

    run(agent, "s", ["how wide is an E. coli cell?"], io.StringIO())
    assert agent.conversation_length("s") == 2

    run(agent, "s", ["and yeast?"], io.StringIO())
    assert agent.conversation_length("s") == 4, "the second question began a fresh conversation"


def test_spend_accumulates_across_calls_to_the_driver(repo, config, tmp_path):
    out = io.StringIO()
    model = scripted(costing(says("an answer"), 0.000_110))
    agent = agent_with(repo, config, tmp_path, model)

    run(agent, "s", ["first"], out)
    run(agent, "s", ["second"], out)

    # The run total is the run ledger's, not something the driver added up.
    assert agent.run_spend() == 220
    assert "run $0.000220" in out.getvalue()


# -- the entry point ------------------------------------------------------


def test_a_missing_corpus_explains_itself_rather_than_raising(tmp_path):
    """The corpus is an external input, so its absence is a condition, not a bug."""
    from bionumbers_ask.cli import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--corpus", str(tmp_path / "nowhere.jsonl"), "--ask", "q"])
    assert "No corpus file" in str(exit_info.value)


def test_no_corpus_at_all_says_one_must_be_supplied(monkeypatch):
    from bionumbers_ask.cli import main

    monkeypatch.delenv("BIONUMBERS_ASK_CORPUS", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        main(["--ask", "q"])
    assert "No corpus path supplied" in str(exit_info.value)


def test_one_shot_mode_runs_a_single_question_and_exits(tmp_path, monkeypatch, capsys):
    """Without a key this ends as not_configured -- which is still one question,
    rendered and ended, rather than a traceback or a prompt."""
    from bionumbers_ask.cli import main
    from conftest import FIXTURE

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        main([
            "--corpus", FIXTURE,
            "--checkpoints", str(tmp_path / "sessions" / "ask.sqlite"),
            "--ask", "How wide is an E. coli cell?",
        ])
    assert exit_info.value.code == 1
    assert "not_configured" in capsys.readouterr().out


def test_the_checkpoint_directory_is_created_rather_than_assumed(tmp_path, monkeypatch):
    from bionumbers_ask.cli import main
    from conftest import FIXTURE

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    store = tmp_path / "made" / "up" / "ask.sqlite"
    with pytest.raises(SystemExit):
        main(["--corpus", FIXTURE, "--checkpoints", str(store), "--ask", "q"])
    assert store.parent.is_dir()


# -- reading from a terminal ---------------------------------------------


def feed(monkeypatch, *lines):
    """Stand in for a person typing, one line per call, then end of input."""
    it = iter(lines)

    def fake_input(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)


def test_typed_lines_become_questions(monkeypatch):
    from bionumbers_ask.cli import _questions_from_terminal

    feed(monkeypatch, "how wide?", "and yeast?")
    assert list(_questions_from_terminal(io.StringIO())) == ["how wide?", "and yeast?"]


@pytest.mark.parametrize("word", ["exit", "quit", "  exit  "])
def test_the_session_can_be_ended_by_typing(monkeypatch, word):
    from bionumbers_ask.cli import _questions_from_terminal

    feed(monkeypatch, "how wide?", word, "never asked")
    assert list(_questions_from_terminal(io.StringIO())) == ["how wide?"]


@pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
def test_ending_the_input_stops_cleanly_rather_than_raising(monkeypatch, interrupt):
    """Ctrl-D and Ctrl-C are how a person leaves, not failures to report."""
    from bionumbers_ask.cli import _questions_from_terminal

    def raises(_prompt=""):
        raise interrupt

    monkeypatch.setattr("builtins.input", raises)
    assert list(_questions_from_terminal(io.StringIO())) == []


def test_the_interactive_entry_point_announces_the_session_and_exits(
    tmp_path, monkeypatch, capsys
):
    from bionumbers_ask.cli import main
    from conftest import FIXTURE

    feed(monkeypatch)  # no input at all: straight to end of input
    with pytest.raises(SystemExit) as exit_info:
        main(["--corpus", FIXTURE, "--checkpoints", str(tmp_path / "i.sqlite"),
              "--session", "chosen-session"])

    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "6 entries" in out and "chosen-session" in out


# -- reporting an answer produced against the retrieval bound --------------


def test_the_meta_line_names_the_bound_only_when_it_was_reached():
    """The pair means something precisely when there was no room for another call.
    On every other answer it is a number beside the ones that matter."""
    at_bound = render(ended(EndReason.ANSWERED, model_calls=12, call_limit=12))
    assert "12 of 12 model calls" in at_bound
    assert at_bound.startswith("  — answered ·")

    spare = render(ended(EndReason.ANSWERED, model_calls=4, call_limit=12))
    assert "model calls" not in spare
    assert "3 tool calls" in spare, "the rest of the line is unchanged"


def test_an_ending_carrying_no_bound_says_nothing_about_one():
    """A question that never reached the model met no bound, and "0 of 0" would
    describe one it did."""
    assert "model calls" not in render(ended(EndReason.RUN_BUDGET, incomplete=True))


# -- what the process exit code says --------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        EndReason.PROVIDER_FAILURE,
        EndReason.NO_ANSWER,
        EndReason.SPEND_CEILING,
        EndReason.RETRIEVAL_BOUND,
        EndReason.RUN_BUDGET,
        EndReason.NOT_CONFIGURED,
    ],
)
def test_a_question_that_did_not_finish_exits_non_zero(reason):
    """Only a configuration error used to. A provider outage, a blank answer and an
    exhausted budget all exited zero, so a script driving --ask read them as
    success."""

    class OneEnding:
        def ask(self, session_id, question):
            yield ended(reason, incomplete=True)

    assert run(OneEnding(), "s", ["q"], io.StringIO()) == 1


def test_an_answered_question_exits_zero():
    class Answered:
        def ask(self, session_id, question):
            yield ended(EndReason.ANSWERED)

    assert run(Answered(), "s", ["q"], io.StringIO()) == 0
