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

import json
import logging
import re
from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import feedback, trace, trail_store, web
from scinumbers_ask.events import Answer, AnswerEntries, EndReason, QuestionEnded


class _RecordingConn:
    def __init__(self):
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        if params is not None:
            self.params.append(dict(params))
        return None


class _RecordingEngine:
    """Enough of an engine to read back what the page actually wrote."""

    def begin(self):
        conn = _RecordingConn()
        self.conns.append(conn)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()

    def __init__(self):
        self.conns: list[_RecordingConn] = []

    @property
    def written(self) -> list[dict]:
        return [p for c in self.conns for p in c.params if "event" in p]


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
    monkeypatch.setattr(web, "resources", lambda corpus=None: repo)
    monkeypatch.setattr(web, "agent_for", lambda state, repo, admission: agent)
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    # No `resources.clear()`: patching the name replaces the cached function
    # outright, so there is no cache to clear and calling it would raise.
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def ask(at: AppTest, question: str) -> AppTest:
    return at.chat_input[0].set_value(question).run()


def _recorded(at: AppTest) -> dict:
    return feedback.ratings(at.session_state)


def _turn_columns(at: AppTest) -> list[tuple]:
    """Each turn's (prose, evidence) pair, in the order the turns were drawn.

    `at.main.columns` flattens every column on the page into one list, so the
    pairing is positional: two columns per turn, prose first. Asserted rather than
    assumed — an odd count means a turn drew one column or three, and silently
    reading them in twos would then pair one turn's prose with the next turn's
    table and still pass.
    """
    columns = at.main.columns
    assert len(columns) % 2 == 0, f"{len(columns)} columns is not a whole number of turns"
    return [(columns[i], columns[i + 1]) for i in range(0, len(columns), 2)]


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
    # The positive control, and it is the whole test. Without it every assertion
    # below is satisfied by a page with no rating widget on it at all -- which is
    # how this test passed the widget-removal experiment unchanged. The dimension
    # is *ignored*, so something has to establish there was a control to ignore.
    assert at.get("feedback"), "no rating was offered, so ignoring one proves nothing"
    assert _recorded(at) == {}

    at = ask(at, "and in yeast?")
    assert not at.exception
    assert len(at.get("feedback")) == 2, "two answers, two controls"
    assert len(web.transcript(at.session_state)) == 2, "the conversation did not continue"
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
    monkeypatch.setattr(web, "resources", lambda corpus=None: repo)
    monkeypatch.setattr(web, "agent_for", lambda state, repo, admission: agent)
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def test_the_rating_sits_with_the_prose_and_not_with_the_evidence(cites):
    """At the foot of the prose column, beside the table rather than under it.

    Document order alone no longer says this. The prose column is drawn first, so
    "the rating comes before the table" is true however the two are split -- it
    stayed true when the table moved into its own column, which means it had
    stopped testing anything. What is asserted now is which column each landed in,
    and that the prose is above the rating *within* that column.
    """
    at = ask(cites.run(), "how wide?")
    prose, evidence = _turn_columns(at)[0]

    assert prose.get("feedback"), "no rating in the prose column"
    assert not evidence.get("feedback"), "the rating went to the evidence column"
    assert evidence.dataframe, "the fixture drew no table, so this proves nothing"
    assert not prose.dataframe, "the table stayed in the prose column"

    inside = _element_order(prose)
    assert inside.index("markdown") < inside.index("feedback"), "the prose came after the rating"


def test_a_redrawn_turn_puts_the_rating_in_the_same_place(cites):
    """The live path and the replay path draw the same turn in two places.

    If only one of them moved, scrolling back would change the layout -- and the
    replay path is the one the reader sees for every turn but the newest. The
    first pair below was drawn by the replay path on the second run; the second
    pair is the live one.
    """
    at = ask(ask(cites.run(), "how wide?"), "and in yeast?")
    turns = _turn_columns(at)
    assert len(turns) == 2, f"{len(turns)} turns drawn, expected 2"
    for index, (prose, evidence) in enumerate(turns):
        assert prose.get("feedback"), f"turn {index} has no rating in its prose column"
        assert not evidence.get("feedback"), f"turn {index} rated in the evidence column"


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
    blocks = [m.value for m in at.markdown if "stIconMaterial" in m.value]
    assert len(blocks) == 1, f"{len(blocks)} copies of the colour rule"


def _feedback_bundle() -> str:
    """The JavaScript Streamlit renders `st.feedback` with, as installed.

    Found by name rather than by scanning `static/`, and that distinction is the
    whole point of the test below: the id this rule used to name really is in
    `static/` — in `ButtonGroup.*.js`, which is `st.pills` and
    `st.segmented_control`. Scanning the directory cannot tell the two apart.
    """
    import streamlit

    js = Path(streamlit.__file__).parent / "static" / "static" / "js"
    bundles = sorted(js.glob("Feedback.*.js"))
    assert bundles, f"no Feedback bundle under {js}; Streamlit's layout has moved"
    return bundles[0].read_text(errors="ignore")


def test_the_colour_rule_names_an_id_st_feedback_actually_renders(app):
    """A selector that matches nothing is a silent no-op, and no test here sees a
    browser — so the id is read out of the component's own bundle and compared.

    **This test previously asserted the wrong id and passed.** It looked for
    `stButtonGroup` "verified against the bundle", and that string is in the
    bundle — for `st.pills` and `st.segmented_control`. `st.feedback` has its own
    module, enqueues as `"feedback"`, and renders as `stFeedback`. The rule matched
    nothing, the thumbs stayed grey, and a grep-level check reported success.

    Reading the id from `Feedback.*.js` is what makes the difference: a string
    present somewhere in `static/` proves nothing about which widget renders it.
    """
    bundle = _feedback_bundle()
    at = app.run()
    rule = next((m.value for m in at.markdown if "stIconMaterial" in m.value), None)
    assert rule, "no colour rule was emitted"

    named = [n for n in re.findall(r'data-testid="(st[A-Za-z]+)"', rule) if n != "stIconMaterial"]
    assert named, f"the rule does not select the icon inside a named wrapper: {rule}"
    wrapper = named[0]
    assert wrapper in bundle, (
        f"the rule targets {wrapper.group(1)!r}, which the Feedback component does not render. "
        "That id may exist elsewhere in static/ — for a different widget."
    )
    assert "stButtonGroup" not in rule, "stButtonGroup is st.pills, not st.feedback"
    assert "prefers-color-scheme: light" in rule, "one colour cannot suit both themes"


def test_the_rating_is_not_drawn_until_the_answer_is_finished(repo):
    """The defect a reader found by clicking, and the one `AppTest` cannot see.

    A widget is live in the browser the moment it renders. A click re-runs the
    script, and a re-run abandons the agent's generator at whatever yield it had
    reached -- so a thumbs-down pressed while the answer was still arriving
    cancelled the tool call it was in the middle of and left the turn unfinished.

    `AppTest` runs scripts to completion and can never click mid-run, so what is
    asserted is the structural property that closes the window: the rating is
    drawn only after the last item has been consumed. Placement is a separate
    test, because a fix that put it in the wrong place would pass this one.
    """
    events = [
        Answer(question_id="q1", text="an answer"),
        AnswerEntries(question_id="q1", cited=(100002,), retrieved=(100002, 100001)),
        QuestionEnded(
            question_id="q1",
            reason=EndReason.ANSWERED,
            spend=10,
            run_spend=10,
            model="m",
            tool_calls=1,
        ),
    ]
    consumed: list[int] = []
    drawn: list[web.Item] = []
    web.answer(iter(events), repo, drawn, after_prose=lambda: consumed.append(len(drawn)))

    assert consumed == [len(events)], (
        f"the rating was drawn after {consumed} of {len(events)} items, with the "
        "generator still live -- a click there abandons the turn"
    )


def test_a_turn_that_never_reaches_the_seam_still_offers_a_rating(repo):
    """No entries and no ending: the seat is never reserved, and the fallback at
    the foot of the column is what offers the control at all."""
    drawn: list[web.Item] = []
    calls: list[int] = []
    web.answer(
        iter([Answer(question_id="q1", text="an answer")]),
        repo,
        drawn,
        after_prose=lambda: calls.append(len(drawn)),
    )
    assert calls == [1], "a turn with no entries and no ending was never offered a rating"


def test_the_question_box_is_readable_before_the_page_draws_anything(app):
    """Half of what makes past ratings inert: the key exists to be read early.

    Streamlit restores widget state at the top of a run, so a keyed question box
    is readable before the `st.chat_input` call that returns it — which is what
    lets the page know a question is coming *before* it redraws the transcript.
    Lose the key and `question_pending` is silently False for ever, and every past
    rating goes back to being clickable mid-answer.
    """
    at = ask(app.run(), "how many ribosomes?")
    assert at.chat_input[0].key == web.ASK_KEY


def test_a_pending_question_is_what_question_pending_reports():
    """The other reading of the same key. Kept as a unit test because `AppTest`
    cannot hold a run open: a chat input is a trigger widget, its value is cleared
    after each run, and a value written into session state by hand does not
    survive to the next one. So the mid-run page state is unreachable from here,
    and the two halves are checked separately — this one, and the disabling below.
    """
    assert not web.question_pending({})
    assert not web.question_pending({web.ASK_KEY: ""})
    assert web.question_pending({web.ASK_KEY: "and in yeast?"})


def test_nothing_in_a_rating_is_clickable_while_a_question_is_answered():
    """A click on any of these re-runs the script, and a re-run abandons the
    agent's generator mid-tool-call — so the answer being asked for right now is
    what a thumb on a *past* answer would cost. This predates the live control's
    own version of the defect.

    `AppTest.from_function` runs the function in a fresh namespace, so the page
    imports for itself. That is the price of reaching a state the real script
    cannot be held in.
    """

    def page():
        import streamlit as st

        from scinumbers_ask import web

        items = [web.Item(web.Kind.ANSWER, "an answer", question_id="q1")]
        web.draw_feedback(items, "s1", st.session_state, answering=True)

    at = AppTest.from_function(page, default_timeout=TIMEOUT).run()
    assert at.get("feedback")[0].disabled, "a past answer's rating stayed live mid-question"


def test_a_comment_in_progress_is_disabled_rather_than_dropped(tmp_path):
    """Streamlit discards the state of a widget it did not render, so leaving the
    box out for the duration of a run would take a half-typed comment with it —
    the loss the rating is disabled rather than hidden to avoid."""
    flag = tmp_path / "answering"

    def page():
        import pathlib

        import streamlit as st

        from scinumbers_ask import feedback, web

        items = [web.Item(web.Kind.ANSWER, "an answer", question_id="q1")]
        st.session_state.setdefault(feedback.STATE_KEY, {})["q1"] = feedback.Rating(
            feedback.Verdict.DOWN
        )
        answering = pathlib.Path(st.session_state["flag"]).exists()
        web.draw_feedback(items, "s1", st.session_state, answering=answering)

    at = AppTest.from_function(page, default_timeout=TIMEOUT)
    at.session_state["flag"] = str(flag)
    at = at.run()
    at = at.text_area[0].set_value("BNID 102345 looks 10x high").run()
    assert "102345" in at.text_area[0].value
    assert not at.text_area[0].disabled, "the box was inert with no question running"

    flag.touch()
    at = at.run()
    assert at.text_area, "the comment box vanished while a question was running"
    assert at.text_area[0].disabled, "the comment box stayed live mid-question"
    assert at.button[0].disabled, "Send stayed live mid-question"
    assert "102345" in at.text_area[0].value, "the draft was lost"


def test_older_ratings_come_back_to_life_once_the_answer_is_finished(app):
    """Inert *while* a question runs, not inert until something else happens.

    Reported by a reader: after asking a second question, the first answer's
    rating stayed dead, and only came back when they clicked something — pressing
    a thumb on the new answer was what woke it. The disabling worked; nothing
    re-drew the page once the reason for it had passed, so the last frame of the
    answering run was the one left on screen.

    The same shape as the "run is over" banner, which was decided before the
    input existed and so arrived one interaction late: a page that stops re-running
    when the script ends keeps whatever the script last said.
    """
    at = ask(app.run(), "how many ribosomes?")
    assert not at.get("feedback")[0].disabled

    at = ask(at, "and in yeast?")
    live = at.get("feedback")
    assert len(live) == 2, "two answers, two ratings"
    assert not live[0].disabled, "the older answer's rating stayed dead after the run finished"
    assert not live[1].disabled, "the new answer's rating is not offered"


def test_the_live_path_splits_the_columns_the_same_way_the_replay_does():
    """The placement tests above only ever see `show()`, and that is not obvious.

    `streamlit_app.py` ends the live branch with `st.rerun()`, so by the time
    `AppTest` settles, what it inspects is the *replay* render. Two mutants in
    `answer()` — sending every item to the prose column, and sending the rating to
    the evidence column — survived the entire suite because of it.

    That is the mirror of the trap recorded at `RETRIEVAL_RUNNING`: there the
    rerun exposed a replay-path defect loudly, here it hides a live-path one
    silently. The reader sees the live render for the whole time an answer streams,
    which is the moment the requirement is written about — a rating waiting at the
    foot of the prose, never below the entries.

    So this drives `web.answer` directly, with no page to re-run.
    """

    def page():
        import streamlit as st

        from scinumbers_ask import web
        from scinumbers_ask.corpus import load
        from scinumbers_ask.events import Answer, AnswerEntries, EndReason, QuestionEnded
        from scinumbers_ask.repository import CorpusRepository

        repo = CorpusRepository(load(st.session_state["corpus"]))
        events = [
            Answer(question_id="q1", text="about 1 micrometre"),
            AnswerEntries(question_id="q1", cited=(100002,), retrieved=(100002, 100001)),
            QuestionEnded(
                question_id="q1",
                reason=EndReason.ANSWERED,
                spend=10,
                run_spend=10,
                model="m",
                tool_calls=1,
            ),
        ]
        items: list[web.Item] = []
        web.answer(
            iter(events),
            repo,
            items,
            after_prose=lambda: web.draw_feedback(items, "s1", st.session_state),
        )

    at = AppTest.from_function(page, default_timeout=TIMEOUT)
    at.session_state["corpus"] = FIXTURE
    at = at.run()
    assert not at.exception, at.exception

    prose, evidence = _turn_columns(at)[0]
    assert prose.get("feedback"), "the live path put no rating in the prose column"
    assert not evidence.get("feedback"), "the live path rated in the evidence column"
    assert evidence.dataframe, "the live path drew no table in the evidence column"
    assert not prose.dataframe, "the live path left the table in the prose column"


# --- what the *page* hands down, not what the functions do with literals ------


def test_the_page_records_the_session_it_is_in_and_the_comment_that_was_typed(app, monkeypatch):
    """Two gaps in one blind spot, both of which survived the whole suite.

    Every page-level test in this file runs under `_quiet_trail`, which clears the
    trail logger's handlers — so none of them can observe a record at all — and
    `_recorded()` reads `feedback.ratings()`, which keeps a verdict and a
    `commented` flag and neither the session nor the text. The consequence:
    `draw_feedback(items, "wrong-session")` and `text="x"` in `_draw_comment_box`
    each passed 1243 tests.

    Every test that checks text fidelity or the session calls `feedback.record_*`
    directly with literals, so the wire from the page to the record is the one
    stretch nothing covers. That is the expensive direction: a rating row carrying
    a session that joins to no trail row is well-formed, plausible and useless,
    and a comment is the one input here that cannot be reconstructed from anything
    else.

    So this installs a real sink over the real script and reads the row back.
    """
    engine = _RecordingEngine()
    store = trail_store.install(engine, logger_name=trace.LOGGER_NAME)
    assert store is not None and store.ready, "the sink is not installed; this proves nothing"
    monkeypatch.setattr(web, "install_trail", lambda engine: store)

    typed = "BNID 102345 looks 10x too high for E. coli"
    at = ask(app.run(), "how many ribosomes?")
    at = at.get("feedback")[0].set_value(0).run()
    at = at.text_area[0].set_value(typed).run()
    at = at.button[0].click().run()

    session = web.session_id(at.session_state, {})
    question_id = web.question_id_of(web.transcript(at.session_state)[0][1])

    verdicts = [r for r in engine.written if r["event"] == feedback.VERDICT_EVENT]
    comments = [r for r in engine.written if r["event"] == feedback.COMMENT_EVENT]
    assert len(verdicts) == 1 and len(comments) == 1, engine.written

    assert verdicts[0]["question_id"] == question_id
    assert verdicts[0]["session_id"] == session, (
        "the page handed down a session that is not the one it is in, so this "
        "rating joins to no row of that question's trail"
    )
    assert comments[0]["session_id"] == session
    assert json.loads(comments[0]["detail"])["comment"] == typed, (
        "the comment stored is not the comment typed"
    )


def test_the_page_tells_the_ratings_a_question_is_running(app, monkeypatch):
    """The join nothing held: both halves were unit-tested, the wire was not.

    `question_pending` is tested as a function, and `draw_feedback(answering=True)`
    is tested for what it disables — but that the *page* computes the first and
    hands it to the second was verified only by reading. Replacing the call with
    `answering = False`, or dropping the keyword from the transcript loop, left
    1243 tests green.

    What that costs if it regresses: a reader clicks a thumb on an older answer
    while a new question is streaming, the click re-runs the script, the agent's
    generator is abandoned mid-tool-call, and the turn is left half-persisted —
    the defect this wiring exists to prevent, returned silently.

    `AppTest` cannot pause inside a run to look, so the call is recorded instead.
    The run that answers must pass `answering=True`; the re-run afterwards passes
    False, which is what revives the controls.
    """
    seen: list[bool] = []
    real = web.draw_feedback

    def recording(items, session_id, state=None, *, answering=False):
        seen.append(answering)
        return real(items, session_id, state, answering=answering)

    at = ask(app.run(), "how many ribosomes?")
    monkeypatch.setattr(web, "draw_feedback", recording)
    seen.clear()
    ask(at, "and in yeast?")

    assert seen, "the page drew no ratings at all, so this proves nothing"
    assert True in seen, (
        "no rating was drawn with answering=True while a question ran, so every "
        "older answer's thumb stayed clickable and a click abandons the generator"
    )
    assert False in seen, (
        "nothing was drawn with answering=False, so the controls are never revived"
    )


def test_a_turn_that_only_ended_is_not_offered_a_rating():
    """`is_ratable` had nothing holding it: `return True` survived the full suite.

    No test drives a turn that ends without an answer — a spend ceiling, a missing
    key, a spent provider — so the rule's own reasoning stood unbacked, which this
    project treats as worse than silence.

    What it protects: a reader who hits the run budget, sees the refusal and
    thumbs it down produces a row indistinguishable from a reader saying the
    science was wrong. The ratings are the evidence base for whether the answers
    are any good, so a handful of infrastructure complaints poisons the one
    dataset that cannot be recomputed.
    """
    ending = web.Item(web.Kind.ENDING, "This run has stopped taking questions.", question_id="q1")
    answer = web.Item(web.Kind.ANSWER, "about 1 micrometre", question_id="q1")

    assert not web.is_ratable([ending]), "an ending alone was offered a rating"
    assert not web.is_ratable([web.Item(web.Kind.WARNING, "hm", question_id="q1"), ending])
    assert web.is_ratable([answer, ending]), "an answered turn was refused a rating"
    # The dimension the rule actually reads is *an answer*, not *an identifier*:
    # a turn with no question_id is unratable for a different reason, and a test
    # that varied only that would pass against `return item.question_id != ""`.
    assert not web.is_ratable([web.Item(web.Kind.ANSWER, "orphan")]), "no identifier to key on"
