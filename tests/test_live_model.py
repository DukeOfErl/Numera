"""The one test that talks to a real model.

Everything else in this suite uses doubles, which is right: assertions should be
about this code, not the model's mood. But a suite made entirely of doubles stops
testing the live path the moment nobody runs it by hand, and the doubles encode
what the provider returned *once*. This is the test that notices when that stops
being true.

Excluded by default via the `network` marker. To run it:

    OPENROUTER_API_KEY=... uv run pytest -m network

It uses the six-entry fixture rather than the real corpus, so it stays cheap: one
question, a handful of tool calls, and about a cent.
"""

from __future__ import annotations

import os
import re

import pytest

from bionumbers_ask.agent import AskAgent
from bionumbers_ask.config import Config
from bionumbers_ask.corpus import load
from bionumbers_ask.events import Answer, EndReason, QuestionEnded, Retrieval
from bionumbers_ask.repository import CorpusRepository

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="set OPENROUTER_API_KEY to run the live-model check",
    ),
]


@pytest.fixture(scope="module")
def live_agent(tmp_path_factory) -> AskAgent:
    repo = CorpusRepository(load("tests/fixtures/corpus_sample.jsonl"))
    path = tmp_path_factory.mktemp("live") / "checkpoints.sqlite"
    # The production configuration, not a test-shaped one: a fixture on a default
    # config would be testing a different system than the one that ships.
    return AskAgent(repo, Config.from_env(), str(path))


def test_a_live_question_is_answered_with_a_citation(live_agent):
    events = list(live_agent.ask("live", "How wide is an E. coli cell?"))
    end = next(e for e in events if isinstance(e, QuestionEnded))
    assert end.reason is EndReason.ANSWERED, f"ended as {end.reason}"

    assert any(isinstance(e, Retrieval) for e in events), "no tool was used"
    answer = next(e for e in events if isinstance(e, Answer)).text
    # A quantity without a bnid beside it is the failure this project exists to
    # prevent. Asserting a citation is present is a harness property; whether the
    # right one was chosen is answer-evaluation's job, not this test's.
    assert re.search(r"\b10000\d\b", answer), f"no entry cited in: {answer[:200]}"


def test_the_provider_still_reports_cost_where_the_ledger_reads_it(live_agent):
    """The live half of the pinned metadata shape.

    The offline test preserves the shape recorded once; this one notices if the
    provider stops returning it. Without this, a renamed field would leave spend
    silently reading zero under a ceiling built on top of it.
    """
    events = list(live_agent.ask("live-cost", "How wide is an E. coli cell?"))
    end = next(e for e in events if isinstance(e, QuestionEnded))
    assert end.spend > 0, "the provider reported no cost where the ledger reads it"
    # Sanity, not a budget. Measured on 2026-08-19: 10,417 micro-dollars ($0.0104)
    # over 5 model calls on the six-entry fixture -- the transcript is re-sent on
    # every call, so cost grows with the square of the retrieval, not linearly. The
    # bound is roughly ten times that, well under the $0.60 per-question ceiling,
    # so it catches a runaway without failing on an ordinary run that searched more.
    assert end.spend < 100_000, f"unexpectedly expensive: {end.spend} micro-dollars"


_corpus_path = os.environ.get("BIONUMBERS_ASK_CORPUS", "")


@pytest.mark.skipif(
    not (_corpus_path and os.path.isfile(os.path.expanduser(_corpus_path))),
    reason="set BIONUMBERS_ASK_CORPUS to a JSONL corpus to run the end-to-end check",
)
def test_the_terminal_driver_answers_from_the_real_corpus_with_a_citation(tmp_path):
    """The whole path: driver, agent, tools, real corpus, real model.

    Everything else runs against a six-entry fixture, where a search returns six
    rows rather than a capped fifty. This is the only test where the two-tier
    retrieval the design exists for is actually under load.
    """
    import io

    from bionumbers_ask.cli import run
    from bionumbers_ask.corpus import load

    repo = CorpusRepository(load(os.path.expanduser(_corpus_path)))
    agent = AskAgent(repo, Config.from_env(), str(tmp_path / "e2e.sqlite"))

    out = io.StringIO()
    assert run(agent, "e2e", ["How wide is an E. coli cell?"], out) == 0

    text = out.getvalue()
    assert "answered" in text, text[-400:]

    # The citation must be in the answer, not merely somewhere in the output: the
    # rendered retrieval lines carry bnids too, so asserting over the whole text
    # would pass on an answer that cited nothing.
    body = text.split("\n  — ")[0]
    answer = "\n".join(line for line in body.splitlines() if not line.startswith("  · "))
    assert re.search(r"\b1\d{5}\b", answer), f"no entry cited in the answer: {answer[:400]}"

    # The driver rendered progress before the answer, not only the answer.
    assert "  · " in text


def test_a_question_the_corpus_does_not_cover_gets_no_number(live_agent):
    """The failure this project exists to prevent, against a real model.

    The offline suite can only prove the harness handles a refusal correctly; a
    scripted double says whatever the test tells it to. Whether the model refuses
    rather than answering from its own knowledge is rule 2, and only this can fail.

    The fixture holds six entries about E. coli, yeast and Xenopus, so mouse
    lifespan is comprehensively uncovered -- and it is something the model certainly
    knows, which is what makes it a test rather than a formality.
    """
    from bionumbers_ask.citations import citations

    events = list(live_agent.ask("uncovered", "What is the lifespan of a laboratory mouse?"))
    answer = next(e for e in events if isinstance(e, Answer))
    end = events[-1]

    assert end.reason is EndReason.ANSWERED, "refusing correctly is answering"
    assert answer.text.strip(), "a refusal still has to say something"
    assert citations(answer.text) == (), f"cited something for an uncovered question: {answer.text}"

    # A quantity in the question's own dimension is the fabrication. Targeted rather
    # than a blanket ban on digits: an honest refusal may well count entries, and
    # asserting "no digits at all" would fail on the correct behaviour.
    fabricated = re.search(
        r"\d+(?:\.\d+)?\s*(?:(?:-|to|and)\s*\d+(?:\.\d+)?\s*)?(?:year|month|week|day|hour)s?\b",
        answer.text,
        re.IGNORECASE,
    )
    assert not fabricated, f"answered from its own knowledge: {fabricated.group(0)!r}"

    # And it looked before concluding: a refusal reached without searching makes the
    # corpus look emptier than it is.
    assert any(isinstance(e, Retrieval) for e in events), "refused without looking"


def test_disagreeing_entries_are_reported_with_what_distinguishes_them(live_agent):
    """Rule 4 against a real model. Only a live run can fail this: a scripted
    double says whatever the test tells it to.

    The fixture holds two entries for `Cell diameter` in the same units and with
    very different values -- 1.0-1.1 um for E. coli, 5.0 um for budding yeast --
    distinguished by nothing but the organism. Asked without naming one, the
    tempting wrong answer is "cell diameter ranges from 1 to 5 um", which is a
    spread across two organisms presented as a measurement of one.
    """
    from bionumbers_ask.citations import citations

    events = list(live_agent.ask("disagree", "How wide is a cell, in micrometres?"))
    answer = next(e for e in events if isinstance(e, Answer))
    cited = citations(answer.text)

    assert 100002 in cited and 100010 in cited, f"did not present both: {answer.text[:400]}"

    lowered = answer.text.lower()
    assert "coli" in lowered and ("yeast" in lowered or "cerevisiae" in lowered), (
        f"cited both but named neither organism: {answer.text[:400]}"
    )

    # The fabrication is one spread built across the two. Targeted at a range whose
    # ends are the two entries' values, rather than banning the digits themselves:
    # a correct answer quotes both numbers, and must be free to.
    fused = re.search(
        r"\b1(?:\.\d+)?\s*(?:-|–|—|to)\s*5(?:\.0+)?\s*(?:µ|μ|u)?m\b",
        answer.text,
        re.IGNORECASE,
    )
    assert fused is None, f"presented two organisms as one range: {fused.group(0)!r}"
