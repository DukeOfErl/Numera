"""An entry's trust tier, read off its decisions, and the one place the rule is written (ADR-0990).

The dashboard's pie and the ask agent's stars both say how far an entry is trusted, and if each
computed it the two would drift apart on the day one of them was changed. So there is one rule,
here, returning two things that the two readers render differently:

- `tier`: `CURATED` for a BioNumbers entry; otherwise the **highest** role among the decisions
  that approved the entry with no issue beside them; otherwise `NONE`, nobody having approved it.
- `disputed`: whether **any** decision disapproved or raised an issue. A dispute does not lower the
  tier -- a senior scientist's approval stands beside a student's objection, and a reader is
  told both -- which is why it is a flag and not a rung.

The dashboard shows a disputed entry as "issue raised" and a `NONE` entry as "not yet reviewed";
the ask agent shows the tier as stars and adds a caution when disputed. Simulated decisions count
toward a tier like any other, and `simulated` says when they did, so every figure drawn from them
can say so (ADR-0960).

Pure over decision rows, so a test needs no database and the two readers need no second query.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select

from numera_validator.records import ReviewerRole
from numera_validator.store import _bound, review_decision


class Tier(StrEnum):
    """From the most trusted down. Closed, like every state here (ADR-1530)."""

    CURATED = "CURATED"
    SENIOR_SCIENTIST = "SENIOR_SCIENTIST"
    SCIENTIST = "SCIENTIST"
    STUDENT = "STUDENT"
    AI = "AI"
    NONE = "NONE"
    """No one has approved it: not yet reviewed, or reviewed and approved by nobody."""


#: Rungs from the lowest up, so that `max` by index is the highest approving role.
_LADDER: tuple[ReviewerRole, ...] = tuple(ReviewerRole)


@dataclass(frozen=True)
class Trust:
    tier: Tier
    disputed: bool = False
    """Some decision disapproved, or raised an issue."""
    simulated: bool = False
    """The decision that set the tier was a model's, standing in for a person (ADR-0960)."""


#: Every curated entry, by construction (ADR-1510): no decision points at one.
CURATED = Trust(Tier.CURATED)


def trust_of(decisions: Iterable[Any]) -> Trust:
    """The trust an item has earned from its decisions, each with `reviewer_role`, `approved`,
    `issue` and `reviewer_model` (a row of `review_decision`, or anything with those fields).

    An open row -- `approved` null and no issue -- is a decision not yet made and counts as
    nothing. A role of null is a decision from before roles were recorded, and sets no tier.
    """
    best: ReviewerRole | None = None
    simulated = False
    disputed = False
    for decision in decisions:
        if decision.approved is False or decision.issue:
            disputed = True
            continue
        if decision.approved is not True or decision.reviewer_role is None:
            continue
        role = ReviewerRole(decision.reviewer_role)
        if best is None or _LADDER.index(role) > _LADDER.index(best):
            best = role
            simulated = decision.reviewer_model is not None and role is not ReviewerRole.AI
    tier = Tier.NONE if best is None else Tier(best.value)
    return Trust(tier, disputed=disputed, simulated=simulated)


def by_item(engine: Any) -> dict[str, Trust]:
    """The trust of every item that has a decision; an item with none is absent, and is `NONE`."""
    rows = select(
        review_decision.c.item_id,
        review_decision.c.reviewer_role,
        review_decision.c.approved,
        review_decision.c.issue,
        review_decision.c.reviewer_model,
    )
    grouped: dict[str, list[Any]] = {}
    with engine.begin() as conn:
        _bound(conn)  # the store's statement timeout, like every other read of its tables
        for row in conn.execute(rows):
            grouped.setdefault(row.item_id, []).append(row)
    return {item_id: trust_of(decisions) for item_id, decisions in grouped.items()}
