"""The review page, driven as a whole script through `AppTest`.

What the page *decides* is asserted in `test_bionumbers_review.py` without a browser; what is left
for here is when each element exists relative to the rest of a run and what a click does to the
next run (`.claude/rules/streamlit-driver.md`). Every assertion reads the rendered page and never
the store: a decision the store holds and the page did not acknowledge, or the reverse, is exactly
the class of defect this file exists to see.

The database is one in-memory SQLite shared with the script thread -- `StaticPool` with
`check_same_thread=False`, because `AppTest` runs the script on its own thread and a per-thread
in-memory database would hand the page an empty one. `review.store_engine` is patched at the point
the page looks it up, so the page runs with no secrets and no connection string.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from streamlit.testing.v1 import AppTest

from bionumbers import records, review, store
from bionumbers.records import (
    CandidateKind,
    Claim,
    ClaimKind,
    DistractorType,
    Fingerprint,
    Location,
    Paper,
    PaperResult,
    PaperState,
    Quote,
    ReviewItem,
    SecondTextKind,
)
from scinumbers_ask import messages, web

APP = Path(__file__).resolve().parents[1] / "review_app.py"
TIMEOUT = 30


def _constant(name: str) -> str:
    """A string assigned at the top of the script, read from the source: importing the module
    would run the page outside Streamlit, and the keys have to be its own or a renamed widget
    would pass here while the test drove a widget that no longer exists."""
    for node in ast.parse(APP.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise LookupError(name)


CHOICE_KEY = _constant("CHOICE_KEY")
VALUE_KEY = _constant("VALUE_KEY")
VERDICT_KEY = _constant("VERDICT_KEY")
COMMENT_KEY = _constant("COMMENT_KEY")
ISSUE_KEY = _constant("ISSUE_KEY")
CONTINUE = _constant("CONTINUE")
SAVE_AND_NEXT = _constant("SAVE_AND_NEXT")
RAISE_AN_ISSUE = _constant("RAISE_AN_ISSUE")
CHOSEN = _constant("CHOSEN")
CHOICE_KEY_STEP = "{item}:1"
CONFIRM_ISSUE = _constant("CONFIRM_ISSUE")
CANCEL_ISSUE = _constant("CANCEL_ISSUE")
SKIP_PAPER = _constant("SKIP_PAPER")
DOMAIN_KEY = _constant("DOMAIN_KEY")
TOPIC_KEY = _constant("TOPIC_KEY")
ANY = _constant("ANY")
NO_STORE = _constant("NO_STORE")

QUESTION = "doubling time of Escherichia coli"
RUN = "run-1"
FP = Fingerprint(model="opus", instruction_sha256="abc123", article_id="PMC1", run_id=RUN)

#: The two items' texts, and the phrase each is searched for on the page. A phrase rather than
#: the sentence, so the search does not depend on how the renderer escapes the rest of it.
FIRST_SUPPORTING = "in rich medium the doubling time was 39 min"
FIRST_SECOND = "in minimal medium it was 21 min"
SECOND_SUPPORTING = "cells divided every 47 min at thirty degrees"
SECOND_SECOND = "a lag before growth resumed of 12 min"
PHRASES = {
    FIRST_SUPPORTING: "in rich medium",
    FIRST_SECOND: "in minimal medium",
    SECOND_SUPPORTING: "at thirty degrees",
    SECOND_SECOND: "before growth resumed",
}
#: The stored value of the item each supporting text belongs to, as the reveal prints it.
STORED = {FIRST_SUPPORTING: "Stored: 39 min", SECOND_SUPPORTING: "Stored: 47 min"}

#: Every token that would tell a reviewer what kind of item they are looking at. The enum members
#: by name, so a member added later joins the rule.
NEVER_SHOWN = {"DISTRACTOR", "SECOND_OCCURRENCE"} | {kind.name for kind in records.DistractorType}


def a_paper() -> Paper:
    return Paper(
        pmcid="PMC1", pmid="39123456", doi="10.1/abc", title="A paper", year=2026, licence="CC BY"
    )


def a_claim(claim_id: str, value: str, supporting: str) -> Claim:
    return Claim(
        claim_id=claim_id,
        property_asked="doubling time",
        property_in_paper="generation time",
        value=value,
        unit="min",
        kind=ClaimKind.SINGLE,
        candidate_kind=CandidateKind.MEASURED,
        quote=Quote(text=supporting, location=Location(passage_id="p1")),
        fingerprint=FP,
    )


def an_item(item_id: str, claim_id: str, value: str, supporting: str, second: str) -> ReviewItem:
    return ReviewItem(
        item_id=item_id,
        question=QUESTION,
        claim=a_claim(claim_id, value, supporting),
        paper=a_paper(),
        supporting=Quote(text=supporting, location=Location(passage_id="p1")),
        second=Quote(text=second, location=Location(passage_id="p2")),
        second_kind=SecondTextKind.DISTRACTOR,
        distractor_type=DistractorType.ADJACENT_CONDITION,
    )


#: The first item's supporting text is a cell of this table, so the page has a table to draw.
TABLE_CAPTION = "Growth parameters by medium"
TABLE = records.TableView(
    label="Table 1",
    caption=TABLE_CAPTION,
    rows=(
        (
            records.TableCell(text="Medium", header=True),
            records.TableCell(text="Doubling time (min)", header=True),
        ),
        (
            records.TableCell(text="Rich", header=True),
            records.TableCell(text=FIRST_SUPPORTING, passage_id="p1"),
        ),
    ),
)

ITEMS = (
    an_item("i1", "c1", "39", FIRST_SUPPORTING, FIRST_SECOND).model_copy(
        update={"tables": (TABLE,)}
    ),
    an_item("i2", "c2", "47", SECOND_SUPPORTING, SECOND_SECOND),
)


@pytest.fixture
def engine():
    """One paper, two items, in a database every thread of the test sees."""
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    store.create_all(engine)
    result = PaperResult(paper=a_paper(), state=PaperState.CLAIMS_FOUND, fingerprint=FP)
    store.load_run(engine, [result], ITEMS, question=QUESTION, run_id=RUN)
    yield engine
    engine.dispose()


@pytest.fixture
def page(monkeypatch, engine):
    """The real script over the seeded database, with the door open unless a test closes it."""
    monkeypatch.setattr(review, "store_engine", lambda: engine)
    return AppTest.from_file(str(APP), default_timeout=TIMEOUT)


# --- reading the page -----------------------------------------------------------------------


def _texts(at: AppTest) -> str:
    """Everything the page says, whatever element it says it in."""
    return "\n".join(str(element.proto) for element in _elements(at))


def _elements(at: AppTest):
    """Every element on the page, walking the tree rather than asking for types by name --
    so a text drawn in an element kind this file did not think of is still read."""
    pending = [at._tree]
    while pending:
        block = pending.pop()
        for child in block.children.values():
            if hasattr(child, "children"):
                pending.append(child)
            else:
                yield child


def _remaining(at: AppTest) -> int:
    (caption,) = [c.value for c in at.sidebar.caption if "left to review" in c.value]
    return int(caption.split()[0])


def _on_screen(at: AppTest, *texts: str) -> bool:
    """The texts reach the page inside the boxes' data; the walk over the elements sees it."""
    page = _texts(at)
    return all(PHRASES[text] in page for text in texts)


def _widget(widgets, prefix: str):
    """The one widget whose key starts with the prefix: the keys carry the item id, so a test
    that does not know which item is on screen finds the widget by its prefix."""
    (found,) = [w for w in widgets if (w.key or "").startswith(prefix + ":")]
    return found


def _button(at: AppTest, label: str):
    (found,) = [b for b in at.button if b.label == label]
    return found


def _click_box(at: AppTest, label: str) -> AppTest:
    """A click on a text box. The box is a custom component whose click `AppTest` cannot
    deliver, so this does what the click does: it records the choice the page reads on the
    next run (the page's `picked_key`)."""
    (item_id,) = {_box_data_of(c)["item"] for c in _cards(at)}
    at.session_state[f"{CHOICE_KEY}:{item_id}:1"] = label
    return at.run()


def _cards(at: AppTest):
    """The two text boxes: the page's custom components, which `AppTest` shows as unknown
    elements carrying a `BidiComponent` proto."""
    return [
        c
        for c in _elements(at)
        if type(c.proto).__name__ == "BidiComponent"
        and c.proto.component_name == "scinumbers_text_card"
    ]


def _box_data_of(card) -> dict:
    import json

    return json.loads(card.proto.json)


def _choose(at: AppTest, *, choice: str | None, value: str | None) -> AppTest:
    """The first step: click a box, type the value read from it, then Continue."""
    if choice is not None:
        at = _click_box(at, choice)
    if value is not None:
        _widget(at.text_input, VALUE_KEY).set_value(value)
    return _button(at, CONTINUE).click().run()


def _box_data(at: AppTest) -> dict[str, dict]:
    """What each box was handed to draw, by label: the content and whether it is chosen."""
    found = {}
    for card in _cards(at):
        data = _box_data_of(card)
        found[data["label"]] = data
    return found


def _chosen_box(at: AppTest) -> str | None:
    """Which box was told it is chosen."""
    chosen = [label for label, data in _box_data(at).items() if data.get("chosen")]
    return chosen[0] if chosen else None


def _judge(at: AppTest, *, verdict: str | None, comment: str | None = None) -> AppTest:
    """The second step: the verdict, then Save and next."""
    if verdict is not None:
        _widget(at.radio, VERDICT_KEY).set_value(verdict)
    if comment is not None:
        _widget(at.text_area, COMMENT_KEY).set_value(comment)
    return _button(at, SAVE_AND_NEXT).click().run()


def _raise(at: AppTest, text: str | None) -> AppTest:
    """Open the issue box, write into it, confirm."""
    at = _button(at, RAISE_AN_ISSUE).click().run()
    if text is not None:
        _widget(at.text_area, ISSUE_KEY).set_value(text)
    return _button(at, CONFIRM_ISSUE).click().run()


def _decide(at: AppTest, *, choice: str, verdict: str, comment: str | None = None) -> AppTest:
    """Both steps of one item, for the cases that only need to get past it."""
    return _judge(_choose(at, choice=choice, value="some value"), verdict=verdict, comment=comment)


def _revealed(at: AppTest) -> bool:
    return "Stored:" in _texts(at)


def _rows(engine):
    with engine.begin() as conn:
        return conn.execute(select(store.review_decision)).all()


def _the_first_item(at: AppTest) -> tuple[str, str]:
    """Which of the two items is on screen; the order is the store's, not this file's."""
    if _on_screen(at, FIRST_SUPPORTING, FIRST_SECOND):
        return FIRST_SUPPORTING, FIRST_SECOND
    assert _on_screen(at, SECOND_SUPPORTING, SECOND_SECOND), "neither item is on screen"
    return SECOND_SUPPORTING, SECOND_SECOND


# --- the open door, and the two steps -------------------------------------------------------------


def test_with_no_identity_configured_an_item_is_shown_with_both_texts_and_without_its_value(page):
    """The first step (ADR-0970): the quantity, the paper and the two texts, and none of the
    stored entry -- not the value, not the paper's name for it, not the conditions."""
    at = page.run()
    assert not at.exception
    shown = _the_first_item(at)
    assert _on_screen(at, *shown)
    assert _remaining(at) == 2
    assert not at.radio, "no verdict yet; the choice is the box itself"
    boxes = _box_data(at)
    assert set(boxes) == {"A", "B"} and all(d["choosable"] for d in boxes.values())
    assert _chosen_box(at) is None
    assert _widget(at.text_input, VALUE_KEY).value == ""
    everything = _texts(at)
    assert not _revealed(at)
    assert "generation time" not in everything
    assert "Condition" not in everything


def test_clicking_a_box_chooses_it_and_can_be_changed(page):
    """The choice is the click on the box (Yoav, 2026-10-09), the chosen box says so, and a
    second click on the other box moves it; both boxes are shown side by side, each carrying
    the text the page would otherwise have drawn."""
    at = page.run()
    assert len(at.columns) >= 2, "the two texts sit in two columns"
    shown = _the_first_item(at)
    boxes = _box_data(at)
    assert {d["text"] for d in boxes.values()} == set(shown)

    at = _click_box(at, "B")
    assert not at.exception
    assert _chosen_box(at) == "B"
    at = _click_box(at, "A")
    assert _chosen_box(at) == "A"


def test_continuing_without_a_choice_is_refused_and_the_item_stays(page):
    at = page.run()
    shown = _the_first_item(at)

    at = _choose(at, choice=None, value="39 min")

    assert not at.exception
    assert any(review.CHOICE_REQUIRED in w.value for w in at.warning)
    assert _on_screen(at, *shown), "the same item, not the next"
    assert not _revealed(at)
    assert _widget(at.text_input, VALUE_KEY).value == "39 min", "the half given is kept"


def test_continuing_without_the_value_read_is_refused_and_nothing_is_revealed(page):
    """The value is typed before the stored one is shown, or the comparison means nothing."""
    at = page.run()

    at = _choose(at, choice="A", value=None)

    assert not at.exception
    assert any(review.VALUE_REQUIRED in w.value for w in at.warning)
    assert not _revealed(at)
    assert _chosen_box(at) == "A", "the half given is kept"


def test_the_choice_is_written_and_reveals_the_stored_entry_for_the_verdict(page, engine):
    at = page.run()
    first = _the_first_item(at)

    at = _choose(at, choice="A", value="39 min")

    assert not at.exception
    assert not at.warning and not at.error
    (row,) = _rows(engine)
    assert (row.value_read, row.approved, row.issue) == ("39 min", None, "")
    assert _remaining(at) == 2, "chosen is not yet decided"
    assert _on_screen(at, *first), "the same item, both texts still in view"
    everything = _texts(at)
    assert STORED[first[0]] in everything
    assert "You chose **A** and read the value as **39 min**" in everything
    assert "Your reading" in everything, "how the reading stands to the stored value is said"
    assert "generation time" in everything
    assert "Condition" in everything
    assert {radio.key for radio in at.radio} == {f"{VERDICT_KEY}:{row.item_id}:2"}
    assert at.radio[0].value is None
    assert _chosen_box(at) == "A", "the reveal keeps the chosen box marked"
    assert not any(d["choosable"] for d in _box_data(at).values()), "no choosing at step 2"


def test_the_verdict_completes_the_item_and_the_next_one_starts_blank_at_the_first_step(
    page, engine
):
    at = page.run()
    first = _the_first_item(at)
    at = _choose(at, choice="A", value="39 min")

    at = _judge(at, verdict=review.APPROVE, comment="clear enough")

    assert not at.exception
    assert not at.warning and not at.error
    (row,) = _rows(engine)
    assert (row.chosen_supporting, row.approved, row.comment) == (True, True, "clear enough")
    assert _remaining(at) == 1
    assert not _on_screen(at, first[0]), "the decided item is gone"
    other = (
        (SECOND_SUPPORTING, SECOND_SECOND)
        if first[0] == FIRST_SUPPORTING
        else (
            FIRST_SUPPORTING,
            FIRST_SECOND,
        )
    )
    assert _on_screen(at, *other)
    assert not _revealed(at), "the next item is at its first step"
    # The next item starts blank: nothing chosen, nothing typed. Seen otherwise in the browser
    # on 2026-09-22, when the widgets kept one key across items.
    assert all(radio.value is None for radio in at.radio)
    assert _widget(at.text_input, VALUE_KEY).value == ""
    assert not [w for w in at.text_area if (w.key or "").startswith(ISSUE_KEY)], "no box open"


def test_a_verdict_without_approve_or_disapprove_is_refused_and_the_reveal_stays(page):
    at = page.run()
    at = _choose(at, choice="B", value="21 min")

    at = _judge(at, verdict=None, comment="hmm")

    assert not at.exception
    assert any(review.VERDICT_REQUIRED in w.value for w in at.warning)
    assert _revealed(at)
    assert _widget(at.text_area, COMMENT_KEY).value == "hmm"


def test_a_reviewer_who_left_after_the_first_step_comes_back_to_the_second(page, engine):
    at = page.run()
    first = _the_first_item(at)
    _choose(at, choice="A", value="39 min")

    again = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    assert not again.exception
    assert _on_screen(again, *first), "the half-done item, before any other"
    assert _revealed(again)
    assert "read the value as **39 min**" in _texts(again)


def test_a_choice_the_store_refuses_is_reported_and_the_item_stays(page, monkeypatch):
    def refusing(*args, **kwargs):
        raise store.DecisionNotSaved("connection refused")

    monkeypatch.setattr(store, "record_choice", refusing)
    at = page.run()
    shown = _the_first_item(at)

    at = _choose(at, choice="B", value="21 min")

    assert not at.exception
    assert any(review.NOT_SAVED in e.value for e in at.error)
    assert _on_screen(at, *shown), "the item is still open"
    assert not _revealed(at)
    assert _remaining(at) == 2


def test_a_verdict_the_store_refuses_is_reported_and_the_reveal_stays(page, monkeypatch):
    at = page.run()
    at = _choose(at, choice="A", value="39 min")

    def refusing(*args, **kwargs):
        raise store.DecisionNotSaved("connection refused")

    monkeypatch.setattr(store, "record_verdict", refusing)
    at = _judge(at, verdict=review.DISAPPROVE)

    assert not at.exception
    assert any(review.NOT_SAVED in e.value for e in at.error)
    assert _revealed(at)
    assert _remaining(at) == 2


def test_an_issue_at_the_first_step_is_recorded_with_no_choice_and_moves_on(page, engine):
    at = page.run()
    first = _the_first_item(at)

    at = _raise(at, "neither text states a doubling time")

    assert not at.exception
    assert not at.warning and not at.error
    (row,) = _rows(engine)
    assert row.issue == "neither text states a doubling time"
    assert (row.chosen_supporting, row.approved, row.value_read) == (None, None, "")
    assert _remaining(at) == 1
    assert not _on_screen(at, first[0])


def test_an_issue_at_the_second_step_keeps_the_choice_and_the_value_read(page, engine):
    at = page.run()
    at = _choose(at, choice="A", value="39 min")

    at = _raise(at, "the stored unit is wrong")

    assert not at.exception
    (row,) = _rows(engine)
    assert (row.chosen_supporting, row.value_read) == (True, "39 min")
    assert (row.approved, row.issue) == (None, "the stored unit is wrong")
    assert _remaining(at) == 1
    assert not _revealed(at), "on to the next item's first step"


def test_raising_an_issue_opens_a_box_that_can_be_taken_back(page, engine):
    """Two clicks, never one: the box appears on the first and replaces the save button; the
    second confirms, or the reviewer takes it back and the save button returns."""
    at = page.run()
    assert not [w for w in at.text_area if (w.key or "").startswith(ISSUE_KEY)]
    assert [b.label for b in at.button if b.label in (CONTINUE, CONFIRM_ISSUE)] == [CONTINUE]

    at = _button(at, RAISE_AN_ISSUE).click().run()

    assert not at.exception
    assert _widget(at.text_area, ISSUE_KEY).value == ""
    labels = [b.label for b in at.button]
    assert CONFIRM_ISSUE in labels and CANCEL_ISSUE in labels and CONTINUE not in labels
    at = _button(at, CANCEL_ISSUE).click().run()
    assert not [w for w in at.text_area if (w.key or "").startswith(ISSUE_KEY)]
    assert CONTINUE in [b.label for b in at.button]
    assert _rows(engine) == []


def test_an_issue_without_its_text_is_refused_and_nothing_is_written(page, engine):
    at = page.run()
    shown = _the_first_item(at)

    at = _raise(at, None)

    assert not at.exception
    assert any(review.ISSUE_REQUIRED in w.value for w in at.warning)
    assert _rows(engine) == []
    assert _on_screen(at, *shown)


def test_when_every_item_is_decided_the_page_says_so(page):
    at = page.run()
    at = _decide(at, choice="A", verdict=review.APPROVE)
    at = _decide(at, choice="B", verdict=review.DISAPPROVE)

    assert not at.exception
    assert any(review.NOTHING_LEFT in i.value for i in at.info)
    assert _remaining(at) == 0
    assert not at.radio and not at.button, "nothing to decide, nothing to click"
    for text in (FIRST_SUPPORTING, FIRST_SECOND, SECOND_SUPPORTING, SECOND_SECOND):
        assert not _on_screen(at, text)


def test_a_cell_s_table_is_drawn_whole_with_its_caption_and_its_cell_marked(page):
    """The first item's supporting text is a table cell; the second item's texts are prose."""
    at = page.run()
    if _the_first_item(at)[0] != FIRST_SUPPORTING:
        at = _decide(at, choice="A", verdict=review.APPROVE)
    assert _on_screen(at, FIRST_SUPPORTING)

    everything = _texts(at)
    assert TABLE_CAPTION in everything
    assert "Doubling time (min)" in everything
    # The proto's text escapes the quote; the style rule (`.bn-badge{`) carries none.
    assert everything.count('bn-badge\\"') == 1, "one of the two texts is in this table"

    at = _decide(at, choice="A", verdict=review.APPROVE)
    assert TABLE_CAPTION not in _texts(at), "the prose item brings no table"


# --- what a person may choose, and a model may not (ADR-0980) ------------------------------------

PHYSICS_SUPPORTING = "the lattice constant was measured as 0.41 nm at room temperature"
PHYSICS_SECOND = "a thermal expansion coefficient of 12 per million per kelvin"
PHRASES[PHYSICS_SUPPORTING] = "lattice constant"
PHRASES[PHYSICS_SECOND] = "thermal expansion"
PHYSICS_FP = Fingerprint(
    model="opus", instruction_sha256="abc123", article_id="PMC2", run_id=RUN, scope="physics"
)


def a_physics_paper() -> Paper:
    return Paper(pmcid="PMC2", title="A crystal", year=2025, licence="CC BY")


@pytest.fixture
def two_domains(engine):
    """The two biology items of `engine` plus one physics item from a second paper."""
    item = an_item("i3", "c3", "0.41", PHYSICS_SUPPORTING, PHYSICS_SECOND).model_copy(
        update={
            "paper": a_physics_paper(),
            "claim": a_claim("c3", "0.41", PHYSICS_SUPPORTING).model_copy(
                update={"fingerprint": PHYSICS_FP}
            ),
        }
    )
    result = PaperResult(
        paper=a_physics_paper(), state=PaperState.CLAIMS_FOUND, fingerprint=PHYSICS_FP
    )
    store.load_run(engine, [result], [item], question=QUESTION, run_id=RUN)
    return engine


def _select(at: AppTest, key: str, value: str) -> AppTest:
    (box,) = [s for s in at.sidebar.selectbox if (s.key or "").startswith(key)]
    return box.set_value(value).run()


def test_the_domain_filter_offers_the_loaded_domains_and_narrows_what_is_served(page, two_domains):
    at = page.run()
    (box,) = [s for s in at.sidebar.selectbox if s.key == DOMAIN_KEY]
    assert box.options == [ANY, "biology", "physics"]
    assert _remaining(at) == 3

    at = _select(at, DOMAIN_KEY, "physics")

    assert not at.exception
    assert _on_screen(at, PHYSICS_SUPPORTING, PHYSICS_SECOND)
    assert _remaining(at) == 1
    at = _decide(at, choice="A", verdict=review.APPROVE)
    assert any(review.NOTHING_LEFT in i.value for i in at.info), "physics is done; biology waits"


def test_no_topic_filter_is_offered_until_a_paper_carries_a_topic(page, two_domains):
    at = page.run()
    assert not [s for s in at.sidebar.selectbox if s.key == TOPIC_KEY]

    with two_domains.begin() as conn:
        conn.execute(
            store.review_paper.update()
            .where(store.review_paper.c.pmcid == "PMC2")
            .values(topic="crystals")
        )
    at = page.run()
    (box,) = [s for s in at.sidebar.selectbox if s.key.startswith(TOPIC_KEY)]
    assert box.options == [ANY, "crystals"]
    at = _select(at, TOPIC_KEY, "crystals")
    assert _on_screen(at, PHYSICS_SUPPORTING)
    assert _remaining(at) == 1


def test_the_topics_offered_are_those_of_the_chosen_domain(page, two_domains):
    with two_domains.begin() as conn:
        conn.execute(
            store.review_paper.update()
            .where(store.review_paper.c.pmcid == "PMC2")
            .values(topic="crystals")
        )
        conn.execute(
            store.review_paper.update()
            .where(store.review_paper.c.pmcid == "PMC1")
            .values(topic="yeast")
        )
    at = page.run()
    (box,) = [s for s in at.sidebar.selectbox if s.key.startswith(TOPIC_KEY)]
    assert box.options == [ANY, "crystals", "yeast"]

    at = _select(at, DOMAIN_KEY, "physics")

    (box,) = [s for s in at.sidebar.selectbox if s.key.startswith(TOPIC_KEY)]
    assert box.options == [ANY, "crystals"]
    assert box.value == ANY, "a fresh topic choice for the new domain"
    at = _select(at, DOMAIN_KEY, "biology")
    (box,) = [s for s in at.sidebar.selectbox if s.key.startswith(TOPIC_KEY)]
    assert box.options == [ANY, "yeast"]


def test_skipping_a_paper_records_it_and_moves_to_another_paper(page, two_domains):
    at = _select(page.run(), DOMAIN_KEY, "physics")
    assert _on_screen(at, PHYSICS_SUPPORTING)

    at = _button(at, SKIP_PAPER).click().run()

    assert not at.exception
    with two_domains.begin() as conn:
        (skip,) = conn.execute(select(store.review_skip)).all()
    assert (skip.pmcid, skip.run_id, skip.reviewer) == ("PMC2", RUN, None)
    assert any(review.NOTHING_LEFT in i.value for i in at.info), (
        "the only physics paper is set aside"
    )
    at = _select(at, DOMAIN_KEY, ANY)
    assert not _on_screen(at, PHYSICS_SUPPORTING)
    assert _remaining(at) == 2
    assert _rows(two_domains) == [], "a skip is not a decision"


# --- the closed door, and no store --------------------------------------------------------------


def test_with_identity_configured_a_visitor_not_signed_in_sees_the_door_and_no_item(
    page, monkeypatch
):
    monkeypatch.setattr(web, "identity_configured", lambda: True)
    monkeypatch.setattr(web, "signed_in_email", lambda: None)

    at = page.run()

    assert not at.exception
    assert any(messages.SIGN_IN_NEEDED in i.value for i in at.info)
    assert any("Sign in" in b.label for b in at.button)
    assert not at.radio
    for text in (FIRST_SUPPORTING, FIRST_SECOND, SECOND_SUPPORTING, SECOND_SECOND):
        assert not _on_screen(at, text)
    assert not any("left to review" in c.value for c in at.sidebar.caption)


def test_a_deployment_with_no_store_says_so_in_one_sentence_and_shows_no_item(monkeypatch, engine):
    monkeypatch.setattr(review, "store_engine", lambda: None)

    at = AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    assert not at.exception
    assert [e.value for e in at.error] == [NO_STORE]
    assert not at.radio and not at.button
    for text in (FIRST_SUPPORTING, FIRST_SECOND):
        assert not _on_screen(at, text)
    assert not any("left to review" in c.value for c in at.sidebar.caption)


# --- what the reviewer must never learn ----------------------------------------------------------


def test_nothing_on_the_page_names_the_second_text_s_kind_or_type(page):
    """Read from every element's proto, not from the types this file knows: a kind leaked through
    a caption, a tooltip or a table cell is the same leak."""
    at = page.run()
    everything = _texts(at)
    assert everything, "the walk read nothing, which would make the assertion below vacuous"
    for token in NEVER_SHOWN:
        assert token not in everything, f"{token} reached the screen"


def test_the_walk_over_the_page_sees_a_token_that_is_there(page):
    """The negative of the leak test: the walk must be able to find a token at all."""
    at = page.run()
    assert _on_screen(at, FIRST_SUPPORTING) or _on_screen(at, SECOND_SUPPORTING)
