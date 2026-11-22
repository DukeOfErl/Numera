"""What the review page takes from the deployment it runs in: its database, and a person's rung.

The one module in the package that reaches `numera_ask`, beside the root `review_app.py`
(design D9; `tests/test_bionumbers_dependency_direction.py` is where that stops being a
convention). It is kept apart from `review.py` so that everything deciding what a screen shows is
core and importable by the simulated review with the validator's own dependencies alone: a model
standing in for a reviewer has no door to pass and no account to read.

Named functions rather than calls made from the page, so the page's own tests can hand it a
database with no connection string, and so "which database" and "which rung" are each one
decision in one place.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from numera_ask.accounts import Account
from numera_ask.permissions import Role
from numera_validator import environment, store
from numera_validator.records import ReviewerRole

#: The secrets section naming the review store. Its own section, not the trail's
#: `[connections.usage]`: on a developer's machine that one points at the Neon trail, which holds no
#: review tables, and the page opened it anyway (ADR-2000).
REVIEW_CONNECTION = "review"

#: The variable `numera-validator load` reads, and the page's store where the secrets name none.
DB_URL_ENV = "NUMERA_REVIEW_DB_URL"


def review_destination() -> Engine | None:
    """The engine `[connections.review]` names, or None where the secrets have no such section.

    `st.connection` caches the engine across sessions, as `web.trail_destination` does for the
    trail: the page reruns on every click, and a fresh engine would pay TCP, TLS and Postgres auth
    before each `next_item`. A section that is present but unusable is raised rather than read as
    absence, so the page cannot quietly fall through to some other store than the one configured.
    """
    from streamlit.errors import StreamlitAPIException, StreamlitSecretNotFoundError

    try:
        return st.connection(REVIEW_CONNECTION, type="sql", pool_pre_ping=True).engine
    except (StreamlitAPIException, StreamlitSecretNotFoundError):
        # Absence, by type and not by message, as `web._is_not_configured` decides it.
        return None


def store_engine() -> Engine | None:
    """The engine holding the review tables, or None where nothing names one.

    `[connections.review]` first, then `NUMERA_REVIEW_DB_URL`. Never the trail's
    `[connections.usage]`: it used to be, on the reasoning that a second section is a second thing
    to get wrong, but no review page is deployed, while every developer's secrets name the trail --
    so the page read a database with no review tables and failed (ADR-2000). A configured section
    still wins over the environment, so a deployed page cannot be redirected by a variable.
    """
    configured = review_destination()
    if configured is not None:
        return configured
    url = environment.read(DB_URL_ENV).strip()
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
