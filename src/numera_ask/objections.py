"""What reviewers said when they objected to an entry, for a reader who asks why (ADR-1630).

**Presentation, not core**, and that placement is the guarantee. A reviewer's words are text a
stranger wrote, and the agent must never be able to reach them -- the line `feedback.py` draws for
a reader's comment (ADR-0750). No entry holds them (`store_corpus`); they are read here, by the
drivers, and attached to the loaded repository in a registry only presentation code can reach:
`test_driver_independence.py` forbids every core module to import this one.

Shown after the stars in the Trust cell, where a double click opens them in full (the user's
call, 2026-10-16), and listed under the terminal's table, which cannot open a cell.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from weakref import WeakKeyDictionary

from .corpus import TRUST_ROLE
from .repository import CorpusRepository

#: item id -> what each objecting reviewer said, per loaded repository.
_ATTACHED: WeakKeyDictionary[CorpusRepository, Mapping[str, tuple[str, ...]]] = WeakKeyDictionary()


def load(store: str | Path) -> dict[str, tuple[str, ...]]:
    """Every objection in the store, keyed by the item it was raised against.

    An objection is a decision that disapproved or raised an issue -- the same ones ADR-0990's
    rule counts as a dispute. Its text is the issue where one was written, else the comment, else
    "did not approve"; each is introduced by the reviewer's role, and marked simulated where a model
    stood in for that role.
    """
    # Imported here, not at the top: a corpus-file run never imports `numera_validator`
    # (ADR-1600), and the drivers import this module on every run.
    from sqlalchemy import create_engine, select

    from numera_validator.store import review_decision

    from .store_corpus import connect, path_of

    path = path_of(str(store))
    engine = create_engine("sqlite://", creator=lambda: connect(path))
    rows = select(
        review_decision.c.item_id,
        review_decision.c.reviewer_role,
        review_decision.c.reviewer_model,
        review_decision.c.approved,
        review_decision.c.issue,
        review_decision.c.comment,
    ).order_by(review_decision.c.id)
    found: dict[str, list[str]] = {}
    try:
        with engine.connect() as conn:
            for row in conn.execute(rows):
                if not (row.approved is False or row.issue):
                    continue
                said = (row.issue or row.comment or "did not approve").strip()
                role = TRUST_ROLE.get(row.reviewer_role or "", "reviewer")
                if row.reviewer_model and row.reviewer_role != "AI":
                    role += " (simulated)"
                found.setdefault(row.item_id, []).append(f"{role}: {said}")
    finally:
        engine.dispose()
    return {item_id: tuple(texts) for item_id, texts in found.items()}


def attach(repo: CorpusRepository, objections: Mapping[str, tuple[str, ...]]) -> None:
    """Make `objections` what the tables drawn over `repo` show."""
    _ATTACHED[repo] = objections


def of(repo: CorpusRepository | None, record_id: object) -> tuple[str, ...]:
    """The objections raised against one entry, by its saved id; empty where there are none."""
    if repo is None:
        return ()
    return _ATTACHED.get(repo, {}).get(str(record_id), ())
