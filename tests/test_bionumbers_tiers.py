"""The trust tier rule (ADR-0990): one function the dashboard and the ask agent both read.

The expectations are written from the rule as Yoav stated it, not from running the code: the
highest approving role sets the tier, any objection sets the flag, and the two are independent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from test_bionumbers_store import QUESTION, RUN, a_result, an_item

from bionumbers import store, tiers
from bionumbers.records import ReviewerRole
from bionumbers.tiers import Tier, Trust, trust_of


@dataclass(frozen=True)
class Row:
    reviewer_role: str | None
    approved: bool | None
    issue: str = ""
    reviewer_model: str | None = None


def approval(role: ReviewerRole, model: str | None = None) -> Row:
    return Row(role.value, True, reviewer_model=model)


def disapproval(role: ReviewerRole, model: str | None = None) -> Row:
    return Row(role.value, False, reviewer_model=model)


def issue(role: ReviewerRole, model: str | None = None) -> Row:
    return Row(role.value, None, "the figure is a specimen's", model)


OPEN = Row(ReviewerRole.STUDENT.value, None)


def test_no_decision_is_no_tier_and_no_dispute():
    assert trust_of([]) == Trust(Tier.NONE, disputed=False, simulated=False)


@pytest.mark.parametrize(
    ("decisions", "tier"),
    [
        ([approval(ReviewerRole.AI)], Tier.AI),
        ([approval(ReviewerRole.STUDENT)], Tier.STUDENT),
        ([approval(ReviewerRole.SCIENTIST)], Tier.SCIENTIST),
        ([approval(ReviewerRole.SENIOR_SCIENTIST)], Tier.SENIOR_SCIENTIST),
        # The highest approving role, whatever order the rows come in.
        ([approval(ReviewerRole.SCIENTIST), approval(ReviewerRole.AI)], Tier.SCIENTIST),
        (
            [approval(ReviewerRole.AI), approval(ReviewerRole.SENIOR_SCIENTIST)],
            Tier.SENIOR_SCIENTIST,
        ),
        # A disapproval or an issue sets no tier, however high its role.
        ([disapproval(ReviewerRole.SENIOR_SCIENTIST), approval(ReviewerRole.AI)], Tier.AI),
        ([issue(ReviewerRole.SENIOR_SCIENTIST), approval(ReviewerRole.STUDENT)], Tier.STUDENT),
        # An open row, and a row from before roles were recorded, set none either.
        ([OPEN], Tier.NONE),
        ([Row(None, True)], Tier.NONE),
    ],
)
def test_the_tier_is_the_highest_role_that_approved(decisions, tier):
    assert trust_of(decisions).tier is tier


@pytest.mark.parametrize(
    ("decisions", "disputed"),
    [
        ([approval(ReviewerRole.SENIOR_SCIENTIST)], False),
        ([OPEN], False),
        ([disapproval(ReviewerRole.AI)], True),
        ([issue(ReviewerRole.AI)], True),
        # A dispute beside an approval: the flag is set and the tier stands (below).
        ([approval(ReviewerRole.SENIOR_SCIENTIST), disapproval(ReviewerRole.STUDENT)], True),
        ([approval(ReviewerRole.SENIOR_SCIENTIST), issue(ReviewerRole.STUDENT)], True),
    ],
)
def test_any_disapproval_or_issue_disputes_the_entry(decisions, disputed):
    assert trust_of(decisions).disputed is disputed


def test_a_dispute_does_not_lower_the_tier():
    trust = trust_of([approval(ReviewerRole.SENIOR_SCIENTIST), disapproval(ReviewerRole.STUDENT)])
    assert trust == Trust(Tier.SENIOR_SCIENTIST, disputed=True, simulated=False)


def test_approved_and_disputed_by_no_one_is_none_and_disputed():
    assert trust_of([disapproval(ReviewerRole.SCIENTIST)]) == Trust(Tier.NONE, disputed=True)


@pytest.mark.parametrize(
    ("decisions", "simulated"),
    [
        # A model in a person's role set the tier: simulated.
        ([approval(ReviewerRole.STUDENT, "typesafe/jev-router")], True),
        # A model as itself is the AI rung, not a simulation of anyone.
        ([approval(ReviewerRole.AI, "nvidia/nemotron")], False),
        # The flag follows the decision that set the tier, not every decision.
        (
            [approval(ReviewerRole.AI, "nvidia/nemotron"), approval(ReviewerRole.SCIENTIST)],
            False,
        ),
        (
            [approval(ReviewerRole.SCIENTIST), approval(ReviewerRole.SENIOR_SCIENTIST, "opus")],
            True,
        ),
    ],
)
def test_a_tier_set_by_a_model_in_a_person_s_role_is_marked_simulated(decisions, simulated):
    assert trust_of(decisions).simulated is simulated


def test_a_curated_entry_is_the_top_tier_and_never_disputed():
    assert tiers.CURATED == Trust(Tier.CURATED, disputed=False, simulated=False)


def test_the_store_s_rows_are_read_item_by_item():
    """The same rule over the real table: the writers' shapes, not a hand-built row."""
    engine = create_engine("sqlite://")
    store.create_all(engine)
    store.load_run(
        engine,
        [a_result()],
        [an_item("i1"), an_item("i2", claim_id="c2"), an_item("i3", claim_id="c3")],
        question=QUESTION,
        run_id=RUN,
    )
    store.record_decision(
        engine,
        "i1",
        reviewer="simulated-scientist:m",
        chosen_supporting=True,
        approved=True,
        reviewer_role=ReviewerRole.SCIENTIST,
        reviewer_model="m",
    )
    store.record_issue(
        engine, "i1", reviewer="ai:n", issue="two values", reviewer_role=ReviewerRole.AI
    )
    store.record_choice(engine, "i2", reviewer="alice", chosen_supporting=True, value_read="39")

    assert tiers.by_item(engine) == {
        "i1": Trust(Tier.SCIENTIST, disputed=True, simulated=True),
        "i2": Trust(Tier.NONE),
    }
