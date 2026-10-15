"""What the review page takes from the deployment it runs in: its database, and a person's rung.

The one module in the package that reaches `scinumbers_ask`, beside the root `review_app.py`
(design D9; `tests/test_bionumbers_dependency_direction.py` is where that stops being a
convention). It is kept apart from `review.py` so that everything deciding what a screen shows is
core and importable by the simulated review with the validator's own dependencies alone: a model
standing in for a reviewer has no door to pass and no account to read.

Named functions rather than calls made from the page, so the page's own tests can hand it a
database with no connection string, and so "which database" and "which rung" are each one
decision in one place.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine

from bionumbers import store
from bionumbers.records import ReviewerRole
from scinumbers_ask import web
from scinumbers_ask.accounts import Account
from scinumbers_ask.permissions import Role

#: The variable `bionumbers load` reads, naming the store where no `[connections.usage]` is set.
DB_URL_ENV = "BIONUMBERS_REVIEW_DB_URL"


def store_engine() -> Engine | None:
    """The engine holding the review tables, or None where the deployment configures none.

    The same `[connections.usage]` section, and so the same database, as the trail and the accounts
    table: the review tables are three more tables in it, and a second secrets section would be a
    second thing to get wrong on a deployment whose first symptom is a page nobody can use.

    `web.trail_destination` is reused rather than a second `st.connection` call because it caches
    the engine at global scope across sessions -- a fresh engine per rerun would pay TCP, TLS and
    Postgres auth before every `next_item`, on a page that reruns on every click.

    Where no `[connections.usage]` is configured, `BIONUMBERS_REVIEW_DB_URL` names the store
    instead, so a run loaded into a local SQLite file can be reviewed on the machine that produced
    it. Secrets win when both are present: the deployed page must not be redirected by an
    environment variable.
    """
    configured = web.trail_destination()
    if configured is not None:
        return configured
    url = os.environ.get(DB_URL_ENV, "").strip()
    return store.engine_from_url(url) if url else None


#: The account roles that are rungs (ADR-0990). A developer or an administrator is neither a
#: student nor a scientist, so their decisions set no tier: someone clicking through the page to
#: test it cannot rate an entry.
_RUNG_OF: dict[Role, ReviewerRole] = {
    Role.STUDENT: ReviewerRole.STUDENT,
    Role.SCIENTIST: ReviewerRole.SCIENTIST,
    Role.SENIOR_SCIENTIST: ReviewerRole.SENIOR_SCIENTIST,
}


def reviewer_role_of(account: Account | None) -> ReviewerRole | None:
    """The rung a signed-in reviewer's decisions are recorded on, from the account table; None
    with no identity configured, and for a role that is not a rung."""
    return _RUNG_OF.get(account.role) if account else None
