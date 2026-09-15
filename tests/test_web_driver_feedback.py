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

from agent_doubles import says, scripted, tool_call
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


def _element_order(block) -> list[str]:
    """Every element on the page, depth first, in the order it was drawn.

    Order is the whole question for `test_the_rating_sits_between_the_prose_and_the
    _table`, and no per-element accessor can answer it: `at.get("feedback")` and
    `at.dataframe` each return their own kind, with nothing relating the two.
    """
    order: list[str] = []
    for child in getattr(block, "children", {}).values():
        order.append(getattr(child, "type", type(child).__name__))
        order.extend(_element_order(child))
    return order


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


# --- where the rating sits ---------------------------------------------------


@pytest.fixture
def cites(monkeypatch, repo, config, tmp_path):
    """An app whose answer cites an entry, so the turn has a table to sit above."""
    model = scripted(
        tool_call("get_entry", entry_id=100002),
        says("about 1 micrometre (BNID 100002)"),
        says("second answer (BNID 100002)"),
    )
    agent = agent_with(repo, config, tmp_path, model)
    monkeypatch.setattr(web, "resources", lambda corpus=None: (repo, agent))
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def test_the_rating_sits_between_the_prose_and_the_table(cites):
    """Below the answer it is about, above a table that can run off the screen.

    Drawn last -- which is where it was -- the control is under the cited table,
    the uncited table and the dimension note, and a reader who has finished
    reading the prose has to scroll past all three to find it.
    """
    at = ask(cites.run(), "how wide?")
    order = _element_order(at.main)
    assert "dataframe" in order, "the fixture drew no table, so this proves nothing"
    assert order.index("feedback") < order.index("dataframe")
    assert order.index("markdown") < order.index("feedback"), "the prose came after the rating"


def test_a_redrawn_turn_puts_the_rating_in_the_same_place(cites):
    """The live path and the replay path draw the same turn in two places.

    If only one of them moved, scrolling back would change the layout -- and the
    replay path is the one the reader sees for every turn but the newest.
    """
    at = ask(ask(cites.run(), "how wide?"), "and in yeast?")
    order = _element_order(at.main)
    assert order.count("feedback") == 2
    first_table = order.index("dataframe")
    assert order.index("feedback") < first_table, "the redrawn turn's rating fell below its table"


# --- approval asks for nothing further ---------------------------------------


def test_approval_is_not_asked_what_went_wrong(app):
    """`answer-feedback`: only disapproval opens the comment box.

    The hint asks what was *wrong*, which is unanswerable about an answer just
    approved -- a reader who thumbs up and is then asked that reads it as the page
    not having registered the click.
    """
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(1).run()
    assert not at.text_area, "approval was asked what went wrong"
    assert any(web.FEEDBACK_THANKS in c.value for c in at.caption), "approval was not acknowledged"


def test_approval_is_still_recorded(app):
    """The box not opening must not mean the thumb stopped counting."""
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(1).run()
    recorded = _recorded(at)
    assert len(recorded) == 1
    assert next(iter(recorded.values())).verdict is feedback.Verdict.UP


# --- one action sends a comment ----------------------------------------------


def test_the_comment_and_its_button_submit_together(app):
    """One action sends, which is a property of them sharing a form.

    A plain text area beside a plain button takes two: typing leaves the text
    uncommitted, the first click or Ctrl+Enter commits it and reruns, and only a
    second one presses Send. `AppTest` cannot see that -- it sets widget values
    directly and never blurs anything -- so what is asserted is the structure that
    makes it true, which is what a revert would break.
    """
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(0).run()

    form = at.text_area[0].proto.form_id
    assert form, "the comment box is not in a form, so sending it takes two actions"
    send = at.button[0]
    assert send.proto.is_form_submitter, "Send is not the form's submit button"
    assert send.proto.form_id == form, "Send submits a different form from the comment box"


def test_send_with_nothing_typed_records_nothing_and_does_not_break(app):
    """The button cannot be disabled on empty text without costing the extra action."""
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(0).run()
    at = at.button[0].click().run()
    assert not at.exception
    question_id = web.question_id_of(web.transcript(at.session_state)[0][1])
    assert not _recorded(at)[question_id].commented


# --- a failed write is invisible to the reader -------------------------------


def test_a_store_that_cannot_be_written_to_does_not_reach_the_reader(app):
    """`answer-feedback`: recording fails open, and the conversation goes on.

    The operation-level tests establish that `record_verdict` does not raise. This
    is the other half of the requirement — that the *page* carries on: no error
    panel, and the input still there to ask the next question with. It needs the
    real script, because "the conversation continues to accept questions" is not a
    property any function has.

    A handler that raises, rather than a store that fails: `logging` catches
    nothing on its own — `Handler.handle` does not wrap `emit` — so this is the
    shape that actually reaches a caller.
    """

    class Raises(logging.Handler):
        def emit(self, record):
            raise RuntimeError("the trail is on fire")

    at = ask(app.run(), "how many ribosomes?")
    # Installed only now, so the *rating* is what meets the broken sink. Installed
    # before the question, every trace record raises and the failure is the
    # question's, not the rating's -- a test that fails for the wrong reason and
    # would keep failing after this requirement was satisfied.
    logging.getLogger(trace.LOGGER_NAME).addHandler(Raises())

    at = at.get("feedback")[0].set_value(1).run()

    assert not at.exception, "a failed write raised into the page"
    assert not at.error, "a failed write put an error on screen"
    assert at.chat_input, "the conversation stopped taking questions"


# --- the thumbs are coloured, once ------------------------------------------


def test_the_colour_rule_is_emitted_once_however_long_the_conversation(app):
    """Once for the page, not once per rated turn.

    `draw_feedback` runs for every turn in the transcript, so a `<style>` block
    emitted from inside it would be repeated as many times as the conversation is
    long. Two questions is enough to tell the two placements apart; one is not.
    """
    at = ask(ask(app.run(), "how many ribosomes?"), "and in yeast?")
    blocks = [m.value for m in at.markdown if "stButtonGroup" in m.value]
    assert len(blocks) == 1, f"{len(blocks)} copies of the colour rule"


def test_the_colour_rule_names_the_element_it_colours(app):
    """A selector that matches nothing is a silent no-op, and no test here can see
    the browser. What is asserted is that the rule names Streamlit's own test ids
    — both verified against 1.61.1's bundle — so a rename shows up as this test
    failing rather than as thumbs quietly going grey.
    """
    at = app.run()
    rule = next(m.value for m in at.markdown if "stButtonGroup" in m.value)
    assert 'data-testid="stIconMaterial"' in rule
    assert "prefers-color-scheme: light" in rule, "one colour cannot suit both themes"
