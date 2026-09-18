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
from sqlalchemy import create_engine
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
VERDICT_KEY = _constant("VERDICT_KEY")
NO_STORE = _constant("NO_STORE")

QUESTION = "doubling time of Escherichia coli"
RUN = "run-1"
FP = Fingerprint(model="opus", instruction_sha256="abc123", article_id="PMC1", run_id=RUN)

#: The two items' texts. Each is searched for on the page by a phrase with no digit in it, because
#: the page bolds the value's numbers -- `39` is shown as `**39**` -- and a search for the whole
#: sentence would miss the very text it is looking for.
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


ITEMS = (
    an_item("i1", "c1", "39", FIRST_SUPPORTING, FIRST_SECOND),
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
    page = _texts(at)
    return all(PHRASES[text] in page for text in texts)


def _decide(at: AppTest, *, choice: str | None, verdict: str | None) -> AppTest:
    if choice is not None:
        at.radio(key=CHOICE_KEY).set_value(choice)
    if verdict is not None:
        at.radio(key=VERDICT_KEY).set_value(verdict)
    return at.button[0].click().run()


def _the_first_item(at: AppTest) -> tuple[str, str]:
    """Which of the two items is on screen; the order is the store's, not this file's."""
    if _on_screen(at, FIRST_SUPPORTING, FIRST_SECOND):
        return FIRST_SUPPORTING, FIRST_SECOND
    assert _on_screen(at, SECOND_SUPPORTING, SECOND_SECOND), "neither item is on screen"
    return SECOND_SUPPORTING, SECOND_SECOND


# --- the open door -----------------------------------------------------------------------------


def test_with_no_identity_configured_an_item_is_shown_with_both_texts(page):
    at = page.run()
    assert not at.exception
    shown = _the_first_item(at)
    assert _on_screen(at, *shown)
    assert _remaining(at) == 2
    assert len(at.radio) == 2, "a choice and a verdict, both blank"
    assert all(radio.value is None for radio in at.radio)


def test_a_verdict_without_a_choice_is_refused_and_the_item_stays(page):
    """The spec's own scenario: approval with no text chosen does not complete the item."""
    at = page.run()
    shown = _the_first_item(at)

    at = _decide(at, choice=None, verdict=review.APPROVE)

    assert not at.exception
    assert any(review.CHOICE_REQUIRED in w.value for w in at.warning)
    assert _on_screen(at, *shown), "the same item, not the next"
    assert _remaining(at) == 2
    assert at.radio(key=VERDICT_KEY).value == review.APPROVE, "the half given is kept"


def test_a_choice_and_a_verdict_move_to_the_next_item(page):
    at = page.run()
    first = _the_first_item(at)

    at = _decide(at, choice="A", verdict=review.APPROVE)

    assert not at.exception
    assert not at.warning and not at.error
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
    assert all(radio.value is None for radio in at.radio), "the next item starts blank"


def test_a_decision_the_store_refuses_is_reported_and_the_item_stays(page, monkeypatch):
    def refusing(*args, **kwargs):
        raise store.DecisionNotSaved("connection refused")

    monkeypatch.setattr(store, "record_decision", refusing)
    at = page.run()
    shown = _the_first_item(at)

    at = _decide(at, choice="B", verdict=review.DISAPPROVE)

    assert not at.exception
    assert any(review.NOT_SAVED in e.value for e in at.error)
    assert _on_screen(at, *shown), "the item is still open"
    assert _remaining(at) == 2


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
