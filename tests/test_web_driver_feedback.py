"""Rating an answer, through the real script.

Everything here needs a whole script run to see. Whether a widget exists, whether
it exists once, and which answer a click lands on are all properties of the page
as Streamlit rebuilds it — not of any function this could call directly. The
banner incident in `.claude/rules/streamlit-driver.md` is the precedent: every
item-level test passed while the page was wrong, and the first real question found
it.

The one to read hardest is `test_rating_the_second_answer_leaves_the_first_alone`.
Rating the *first* answer would pass under a shared-key bug, and a shared key is
the failure that produces no error at all — every answer holding one value, so a
click on the third writes onto the first.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted
from scinumbers_ask import feedback, trace, web

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
TIMEOUT = 30


@pytest.fixture(autouse=True)
def _quiet_trail():
    """No durable sink; these tests are about the page, not the store."""
    logger = logging.getLogger(trace.LOGGER_NAME)
    before = list(logger.handlers)
    logger.handlers.clear()
    yield
    logger.handlers[:] = before


@pytest.fixture
def app(monkeypatch, repo, config, tmp_path):
    """The real script over a scripted agent."""
    agent = agent_with(
        repo, config, tmp_path, scripted(says("first answer"), says("second answer"))
    )
    monkeypatch.setattr(web, "resources", lambda corpus=None: (repo, agent))
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    # No `resources.clear()`: patching the name replaces the cached function
    # outright, so there is no cache to clear and calling it would raise.
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def ask(at: AppTest, question: str) -> AppTest:
    return at.chat_input[0].set_value(question).run()


def _recorded(at: AppTest) -> dict:
    return feedback.ratings(at.session_state)


# --- the control is offered, once ------------------------------------------


def test_an_answered_question_offers_a_rating(app):
    at = ask(app.run(), "how many ribosomes?")
    assert len(at.get("feedback")) == 1


def test_the_control_appears_on_the_run_that_answered(app):
    """Not one interaction late, which is the banner incident's exact shape.

    The turn joins the transcript after the loop that redraws past turns, so a
    widget drawn only in that loop would not exist until the reader interacted
    again — and a reader who reads the answer and stops would never see it.
    """
    at = app.run()
    assert not at.get("feedback"), "a rating was offered before anything was answered"
    at = ask(at, "how many ribosomes?")
    assert at.get("feedback"), "the rating waited for the next interaction"


def test_each_answer_is_offered_exactly_one_control(app):
    at = ask(ask(app.run(), "how many ribosomes?"), "and in yeast?")
    assert len(at.get("feedback")) == 2, "a turn was drawn twice, or not at all"


def test_nothing_is_offered_before_a_question(app):
    assert not app.run().get("feedback")


# --- a click lands on the right answer -------------------------------------


def test_rating_an_answer_records_it(app):
    at = ask(app.run(), "how many ribosomes?")
    at.get("feedback")[0].set_value(0).run()

    recorded = _recorded(at)
    assert len(recorded) == 1
    assert next(iter(recorded.values())).verdict is feedback.Verdict.DOWN


def test_rating_the_second_answer_leaves_the_first_alone(app):
    """The failure this exists for produces no error at all.

    A shared widget key gives every answer one value, so clicking the third
    answer's thumb writes the verdict onto the first. Rating the *first* answer
    would pass under that bug; rating the second is what distinguishes them.
    """
    at = ask(ask(app.run(), "how many ribosomes?"), "and in yeast?")
    first_id = web.question_id_of(web.transcript(at.session_state)[0][1])
    second_id = web.question_id_of(web.transcript(at.session_state)[1][1])
    assert first_id and second_id and first_id != second_id

    at.get("feedback")[1].set_value(1).run()

    recorded = _recorded(at)
    assert second_id in recorded, "the rating did not land on the answer that was rated"
    assert first_id not in recorded, "the rating landed on the wrong answer"


def test_the_page_survives_a_rating(app):
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(1).run()
    assert not at.exception


# --- once rated, it stays rated --------------------------------------------


def test_the_control_is_settled_once_a_rating_is_given(app):
    """`answer-feedback`: a rating is final, and the control shows it as settled.

    Also what protects the comment draft: Streamlit discards the state of a widget
    it did not render, and a re-clickable thumb could clear itself, un-render the
    comment box, and take a half-typed comment with it.
    """
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(1).run()
    assert at.get("feedback")[0].disabled


def test_a_comment_box_appears_only_after_a_rating(app):
    at = ask(app.run(), "how many ribosomes?")
    assert not at.text_area, "a comment box was offered before any rating"

    at = at.get("feedback")[0].set_value(0).run()
    assert at.text_area, "no comment box after rating"
    assert "ID" in at.text_area[0].label, "the hint does not ask for an entry identifier"


def test_a_comment_is_recorded_against_the_same_answer(app):
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(0).run()
    at = at.text_area[0].set_value("BNID 102345 looks 10x high").run()
    at = at.button[0].click().run()

    question_id = web.question_id_of(web.transcript(at.session_state)[0][1])
    assert _recorded(at)[question_id].commented


def test_an_unrated_answer_records_nothing_and_the_page_goes_on(app):
    at = ask(app.run(), "how many ribosomes?")
    assert _recorded(at) == {}
    at = ask(at, "and in yeast?")
    assert not at.exception
    assert _recorded(at) == {}
