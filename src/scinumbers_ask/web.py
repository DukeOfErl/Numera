"""Web driver: the second adapter over the same agent.

Streamlit re-runs its whole script on every interaction, so a driver built on it
has nowhere to keep anything between one question and the next except session
state. That suits the port rather than straining it: the conversation, the
accumulated spend and the ceiling in force all live in the checkpoint, and the
only thing this driver keeps is the session identifier that reaches them --
alongside a transcript of what has already been drawn, which is output rather
than state, and which the agent survives losing.

Events become items here, and the page draws from the items. The indirection
earns its place twice over. Streamlit composes successive writes to one screen
location into the last of them, so anything rendered in place and then
overwritten is unobservable afterwards -- to a reader scrolling back and to a
test alike; items are ordinary Python and can be asserted on directly. And the
agent's stream can be drained once, by a caller that is not drawing anything,
which is what lets the same events be rendered twice: now, and again on the
re-run after the next question.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, MutableMapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

import streamlit as st

from . import accounts, allowance, bionumbers, entries_table, feedback, messages, trace, trail_store
from .accounts import Account, EnrolmentUnavailable
from .agent import AskAgent
from .authorization import Refused, allowed, require
from .config import Config, env_setting, format_usd, refuse_retired_env
from .corpus import load
from .events import Answer, AnswerEntries, EndReason, Event, QuestionEnded, Retrieval
from .permissions import Identity, Permission
from .repository import CorpusRepository

# Namespaced, because session state is one flat dictionary shared with every
# widget key on the page: an unprefixed "session_id" is one careless `key=` away
# from being overwritten by a text input.
# One line on screen, which is the constraint: a banner that wraps becomes a block a
# reader learns to skip. Specific on both counts a vaguer line would lose --
# *not trustworthy* rather than merely unpolished, and *the original source* rather
# than "the cited entry", which reads as this page's own rendering of it and is the
# one thing checking it cannot verify. The README makes the same claim; if one
# changes, change both.
PROTOTYPE_NOTE = (
    "**Prototype — not scientifically trustworthy.** "
    "Verify every number against the original source."
)
PROTOTYPE_SHORT = "Prototype — verify numbers against the original source."

# Whose data this is, wherever the app runs. Not deployment wording -- every answer
# rests on someone else's decades of curation, and the citation belongs beside the
# numbers whether one person is reading them locally or a hundred are online. The
# licensing of the underlying export is unresolved (ADR-0170), which is a reason to
# be scrupulous about attribution rather than an excuse to omit it.
DATA_CREDIT = (
    "Data: BioNumbers (Milo et al., Nucl. Acids Res. 2010;38:D750–D753) — "
    "verify each figure at its source."
)
DATA_CREDIT_LABEL = "Data: BioNumbers (Milo et al.)"

# Re-exported rather than restated: the sentence is shared with the terminal
# driver and lives in `messages` for the same reason every warning does. The page
# reads it from here so that `streamlit_app.py` needs one import, as it does for
# every other piece of wording on the page.
RECORDS_NOTE = messages.RECORDS_NOTE

# Pinned to the viewport rather than written into the page. Drawn as an ordinary
# element it sat above the conversation and scrolled away with the first answer --
# so the reader who has read several answers, and is therefore most likely to have
# started trusting them, is the one who can no longer see it.
#
# Fixed under Streamlit's own header, with the main container padded so nothing
# hides behind it. The two test ids are Streamlit's stable ones (verified against
# 1.61.1); if a future version renames them the banner degrades to sitting at the
# top of the page, which is where it was before -- it cannot vanish.
PROTOTYPE_BANNER_CSS = """
<style>
[data-testid="stMainBlockContainer"] { padding-top: 4.5rem; }
.bn-caveat {
  position: fixed; top: 3.5rem; left: 0; right: 0; z-index: 999;
  padding: 0.45rem 1rem; text-align: center; font-size: 0.85rem; line-height: 1.3;
  background: #7a4a00; color: #ffe9c2;
  border-bottom: 1px solid rgba(255, 233, 194, 0.35);
}
@media (prefers-color-scheme: light) {
  .bn-caveat { background: #ffecb3; color: #4a3000; }
}
</style>
"""

SESSION_KEY = "scinumbers_ask.session"

# The question box's widget key. Named so the page can ask, before it draws
# anything, whether a question is about to run -- Streamlit restores widget state
# at the top of the run, so the submitted question is readable there, ahead of the
# `st.chat_input` call that returns it. `question_pending` is that question.
ASK_KEY = "scinumbers_ask.question"
TRANSCRIPT_KEY = "scinumbers_ask.transcript"

# The session identifier lives in the URL as well as in session state. Session
# state dies with the server; the checkpoint it points at does not, so without
# this a restart would orphan every conversation on disk and start a new one.
QUERY_KEY = "session"

DEFAULT_CHECKPOINTS = "checkpoints/ask.sqlite"

# Rows in the table beside the answer, against the terminal's five. Small on
# purpose: this is the evidence a reader checks the prose against, and a table
# long enough to scroll is one nobody reads. Nothing is hidden -- every retrieved
# entry is in the side panel, whole and openable.
# Two caps, not one. A single cap on the table spent all of its rows on cited
# entries whenever an answer cited many -- nine cited entries against eight rows
# dropped one of them and took the uncited section with it. The cited entries are
# what the prose stands on and a reader checking it needs every one; the uncited
# are context, and four of them is enough to show the answer had alternatives.
CITED_ROWS = 10
UNCITED_ROWS = 4

# Pixel widths in the terminal table's proportions (29:17:13:12:7:18), scaled so
# the table fits the main column without a horizontal scrollbar. Sized to the
# column rather than to the content on purpose: a table you have to scroll
# sideways hides the identifier, which is the one cell a reader is checking. A
# truncated cell opens in full on a double click, so nothing is lost.
# Property and Reference are 20% narrower than the terminal's proportions would
# give them, and they are the two that can afford it: both hold prose that
# truncates gracefully and opens in full on a double click, where Value, Units
# and ID hold short strings that either fit or are unreadable. The 62px this
# frees is what pays for the wider gutter between the columns.
COLUMN_WIDTHS = {
    "Property": 152,
    "Organism": 115,
    "Value": 85,
    "Units": 70,
    "ID": 60,
    "Reference": 96,
}

#: How the turn's width is split: the prose on the left, the entries it rests on
#: to the right of it. Two columns rather than one tall one, so a reader checking
#: a number against the table is looking at both at once instead of scrolling
#: between them.
#:
#: **The right-hand share has a floor, and it is not a matter of taste.** The
#: table's widths above are fixed pixels; below their sum the dataframe grows a
#: horizontal scrollbar, and the first column it takes away is the identifier --
#: the one cell a reader is checking. `layout="wide"` follows from the same
#: arithmetic: the centred layout's main area is about 700px, which no split
#: divides into a side wide enough.
#:
#: Even, rather than the 5:6 it started at, and that is the most the evidence
#: column can give back. Narrowing it further undoes the 20% the table's own
#: columns just gave up and then some -- at 6:5 the layout would need a wider
#: browser than it did before either change.
#:
#: `test_web_driver.py::test_the_evidence_column_can_hold_its_table` does that
#: arithmetic, against the stated target below. An earlier version of this comment
#: claimed the test existed before it did.
READING_SPLIT = (1, 1)

#: The narrowest browser this layout is designed for: a 16-inch laptop at full
#: width, or any ordinary external monitor. Stated as a number so the split and
#: the column widths can be checked against it instead of argued about -- every
#: previous attempt to reason about this in prose got it wrong in one direction
#: or the other.
TARGET_BROWSER_WIDTH = 1650

#: What the browser width loses before the two columns get any: Streamlit's
#: sidebar, the main container's padding, and the gutter between them.
LAYOUT_CHROME = 336 + 64 + 64


class Kind(StrEnum):
    """What an item is, so the page can choose how to draw it.

    The driver decides what kind of thing an event is; the page decides what that
    kind looks like. Keeping those apart is what makes the decision testable
    without a browser, since the second half is the part no test can see.
    """

    PROGRESS = "progress"
    WARNING = "warning"
    ANSWER = "answer"
    ENTRIES = "entries"
    ENDING = "ending"


@dataclass(frozen=True)
class Table:
    """The entries an answer is presented with, already selected and ordered.

    Carried on the item rather than looked up when drawn, so a re-run can redraw a
    past answer's table without the repository and without re-running its search.
    """

    rows: tuple[entries_table.Row, ...] = ()
    retrieved: int = 0
    matched: int = 0
    searches: int = 0


@dataclass(frozen=True)
class Item:
    kind: Kind
    text: str = ""
    table: Table | None = None
    # Decided here rather than at the screen, for the reason the whole module is
    # shaped this way (ADR-0100): whether the run is over is a decision, and a
    # test can read it off an item where it cannot read it off a drawn page.
    ends_the_run: bool = False
    # Decided here for the same reason, and carried rather than looked up later: the
    # ending's reason is available at this point and gone by the time the page draws.
    stop_advice: str = ""
    # The reason itself, beside the advice derived from it, so the page can pick
    # the wording for a signed-in reader at draw time -- which is when it knows
    # whether there is an operator who is not the reader.
    reason: EndReason | None = None
    run_spend: int = 0
    run_budget: int = 0
    # The question that produced this item. Carried so a thing on screen can be
    # traced back to the question behind it -- which is what a rating on an answer
    # will have to name, and what joins it to that question's trail.
    #
    # It cannot be retrofitted: an item already drawn has no record of where it
    # came from, and the alternative keys are wrong rather than merely awkward.
    # The transcript's list index looks stable because the list is append-only,
    # but the transcript lives in session state alone -- reload the same
    # `?session=` and indices restart at 0 while the conversation continues, so
    # `(session, 0)` would name two different questions.
    question_id: str = ""


def item_for(event: Event, repo: CorpusRepository | None = None) -> Item | None:
    """One item for an event, or None for one the page does not draw.

    Every event the agent emits produces an item, warnings included: a warning that
    reaches this function and falls through is a fact the agent established and the
    page never said, which is worse than an ugly one.

    The question identifier is stamped here, once, rather than passed at each of
    the branches below. Every event carries it, so there is nothing to decide --
    and a branch added later would otherwise drop it silently, producing an item
    that cannot be traced to its question and nothing that would say so.
    """
    item = _item_without_identity(event, repo)
    if item is None:
        return None
    return replace(item, question_id=getattr(event, "question_id", ""))


def _item_without_identity(event: Event, repo: CorpusRepository | None = None) -> Item | None:
    """What kind of thing this event is. `item_for` adds which question it was."""
    if isinstance(event, Retrieval):
        return Item(Kind.PROGRESS, messages.retrieval_text(event))
    if isinstance(event, AnswerEntries):
        # Needs the corpus: the event carries identifiers, and the reference
        # deliberately never travels through the agent.
        if repo is None:
            return None
        rows = entries_table.rows_for(repo, event.cited, event.retrieved, event.question)
        if not rows:
            return None
        return Item(
            Kind.ENTRIES,
            table=Table(rows, len(event.retrieved), event.matched, event.searches),
        )
    warning = messages.warning_text(event)
    if warning is not None:
        return Item(Kind.WARNING, warning)
    if isinstance(event, Answer):
        return Item(Kind.ANSWER, event.text)
    if isinstance(event, QuestionEnded):
        return Item(
            Kind.ENDING,
            messages.ending_text(event),
            ends_the_run=event.reason in messages.STOP_THE_RUN,
            stop_advice=messages.run_over_advice(event.reason) or "",
            reason=event.reason,
            run_spend=event.run_spend,
            run_budget=event.run_budget,
        )
    return None


def items_for(events: Iterable[Event], repo: CorpusRepository | None = None) -> Iterator[Item]:
    """Each event's item, as the event arrives.

    A generator, because a question's events arrive over its whole life -- a
    search finishes long before the answer exists -- and draining before drawing
    would leave the page blank for all of it. The caller must drain: stopping
    part way leaves the question half-asked, with the model paid for and the
    checkpoint not written.
    """
    return (item for item in (item_for(event, repo) for event in events) if item is not None)


def session_id(
    state: MutableMapping[str, Any], params: MutableMapping[str, Any] | None = None
) -> str:
    """The session this browser tab is continuing, created on first use.

    Held in two places, because neither survives what the other does. Session
    state is per-tab and keeps two browsers apart, but dies when the server does.
    The URL survives a restart and a reload, and is what makes a session something
    a person can bookmark or hand to someone else -- but it is shared by anyone
    given the link, so it is where the identifier is *recovered*, never where it
    is decided.

    Takes both mappings rather than reaching for `st.session_state` and
    `st.query_params`, so a test can hold two of either.
    """
    params = {} if params is None else params
    if SESSION_KEY not in state:
        # Same width as the terminal driver's, so a session started in one can be
        # continued in the other by copying it.
        state[SESSION_KEY] = params.get(QUERY_KEY) or uuid.uuid4().hex[:8]
    params[QUERY_KEY] = state[SESSION_KEY]
    return state[SESSION_KEY]


def tab_id(state: MutableMapping[str, Any]) -> str:
    """This browser session's own identity, for the session cap alone.

    Minted here and never read from the URL, which is what separates it from the
    conversation token above. The token is supplied by whoever holds the link, so
    ten testers opening one shared bookmark would register as a single tab: the
    cap would bound nothing, and any one of them signing out would free the place
    the other nine were sitting in. That is ADR-0830's reasoning about the link,
    applied to the thing the cap counts.

    Per browser session, because that is what costs the host -- one Streamlit
    session and one agent.
    """
    if TAB_KEY not in state:
        state[TAB_KEY] = uuid.uuid4().hex[:8]
    return state[TAB_KEY]


def transcript(state: MutableMapping[str, Any]) -> list[tuple[str, list[Item]]]:
    """What has already been drawn, so a re-run can put it back on screen.

    Output, not state: the conversation itself is in the checkpoint, so losing
    this loses the page's history and not the agent's. A reload shows an empty
    page continuing a session that still remembers everything.
    """
    if TRANSCRIPT_KEY not in state:
        state[TRANSCRIPT_KEY] = []
    return state[TRANSCRIPT_KEY]


# --- the door ---------------------------------------------------------------------

#: Session-state keys for what `admit` and `agent_for` hold. Namespaced like the
#: others: one flat dictionary, shared with every widget on the page.
#: This browser session's own key, apart from the conversation it is in.
TAB_KEY = "scinumbers_ask.tab"
ADMISSION_KEY = "scinumbers_ask.admission"
AGENT_KEY = "scinumbers_ask.agent"


class Door(StrEnum):
    """What the page may do before it draws anything."""

    OPEN = "open"
    SIGN_IN = "sign in"
    NOT_ENROLLED = "not enrolled"
    NO_CREDENTIAL = "no credential"
    CREDENTIAL_REJECTED = "credential rejected"
    UNAVAILABLE = "enrolment check unavailable"
    NO_ACCOUNTS_DATABASE = "no accounts database"


@dataclass(frozen=True)
class Admission:
    """The door's answer for this session, and the account behind it if open.

    `configured` is carried so the page can say the right thing in the
    unconfigured case -- there is no sign-in, records carry no account -- without
    reading secrets a second time.
    """

    door: Door
    configured: bool
    account: Account | None = None

    @property
    def identity(self) -> Identity | None:
        """Who, and as what -- for the grant table and the sidebar, never the agent."""
        return None if self.account is None else self.account.identity


def identity_configured() -> bool:
    """Whether `[auth]` is in secrets. Absent means: run exactly as before.

    Not `st.user.is_logged_in`, which does not exist as an attribute at all when
    `[auth]` is absent (read from the installed Streamlit 1.61.1, not remembered).
    A missing secrets file is "not configured", by the same types
    `_is_not_configured` names for the trail.
    """
    try:
        return "auth" in st.secrets
    except Exception as exc:  # noqa: BLE001 - narrowed by `_is_not_configured`
        if _is_not_configured(exc):
            return False
        raise


def signed_in_email() -> str | None:
    """The account the identity provider asserts, or None. Never a name the
    reader typed: the system accepts no credential of its own."""
    user = st.user.to_dict()
    if not user.get("is_logged_in"):
        return None
    return user.get("email") or None


def admit(
    state: MutableMapping[str, Any],
    engine: Any | Callable[[], Any | None] | None,
    session_id: str,
    *,
    check_key: Callable[[str], Any] | None = None,
) -> Admission:
    """Decide the door, reading enrolment once per account.

    The enrolment row is held in session state keyed by the email, so a rerun
    does not pay a database round trip and a different account signing in on the
    same tab is looked up afresh. The unavailable check is deliberately *not*
    held: a database that wakes up admits the reader on the next rerun, so a
    person told "try again shortly" who tries again is actually retried.

    **What the held row means for an operator: withdrawal takes effect at the
    reader's next page load, not at once.** Disabling an account, changing its
    role or rotating its key changes nothing for a tab that is already open,
    because neither this row nor the agent built from it is re-read while the
    tab lives. Re-reading per question was considered and rejected (a database
    round trip per question); if a key must be cut off immediately, revoke it at
    the provider, which the next model call will meet.

    This decides the door only; it does not register identity. The caller maps
    the account to its *effective* session (`effective_session`) and stamps
    that, because under sign-in the conversation is keyed on the account and not
    on the reader-supplied URL token (ADR-0830) -- so a session id passed here,
    which comes from the URL, is not where identity is keyed.

    `engine` may be an engine or a zero-argument callable returning one; the
    callable is invoked only on the one path that needs it -- configured, signed
    in, and not already held -- so an unconfigured or not-signed-in rerun pays
    nothing, and a misconfigured trail URL does not `complain` on every click.

    **Fails closed.** No engine, or one that cannot be read, is `UNAVAILABLE`,
    never `OPEN`: the accounts module says why the trail's fail-open reasoning
    does not transfer, and the page says a different sentence so the operator is
    not sent looking for a row that exists. An enrolled account with no
    credential is `NO_CREDENTIAL`, a door of its own so the page has one gate and
    never an agent that could fall back to the environment's key.

    A refused sign-in is recorded with the email in the record's own fields --
    there is no identity to stamp, because the person was refused one.
    """
    if not identity_configured():
        return Admission(Door.OPEN, configured=False)
    email = signed_in_email()
    if email is None:
        state.pop(ADMISSION_KEY, None)
        return Admission(Door.SIGN_IN, configured=True)
    held = state.get(ADMISSION_KEY)
    if held is not None and held[0] == email:
        return held[1]
    resolved = engine() if callable(engine) else engine
    if resolved is None:
        # Not `UNAVAILABLE`: that says "try again shortly", and this never comes
        # right on its own. `[auth]` configured without `[connections.usage]` is
        # the likeliest first-deploy mistake, and it should send the operator to
        # `sql/accounts.sql` rather than leave every visitor waiting for a retry
        # that cannot succeed.
        trail_store.complain(
            "no accounts database is configured",
            EnrolmentUnavailable("[auth] is set but [connections.usage] is not"),
        )
        return Admission(Door.NO_ACCOUNTS_DATABASE, configured=True)
    try:
        account = accounts.lookup(resolved, email)
    except EnrolmentUnavailable as exc:
        trail_store.complain("enrolment check unavailable", exc)
        return Admission(Door.UNAVAILABLE, configured=True)
    if account is None:
        trace.QuestionTrace(
            question_id="",
            session_id=session_id,
            run_label=Config.from_env().run_label,
        ).record("signin.refused", email=email)
        admission = Admission(Door.NOT_ENROLLED, configured=True)
    elif not account.openrouter_key:
        admission = Admission(Door.NO_CREDENTIAL, configured=True, account=account)
    elif check_key is not None and check_key(account.openrouter_key).rejected:
        # Asked once, here, rather than left for the first question to discover.
        # A key the provider refuses produces a question whose model call fails,
        # whose tools retrieve nothing, and whose answer reports finding nothing
        # in the corpus -- a broken credential wearing the face of a thin corpus.
        # Only an outright rejection closes this door: an unreachable provider
        # leaves `rejected` false, because locking every tester out over a blip
        # would be the worse failure.
        admission = Admission(Door.CREDENTIAL_REJECTED, configured=True, account=account)
    else:
        admission = Admission(Door.OPEN, configured=True, account=account)
    state[ADMISSION_KEY] = (email, admission)
    return admission


def account_scope(admission: Admission) -> str | None:
    """What the run ledger is narrowed by, or `None` for one shared pot.

    Per account, because each account's questions are paid for by its own
    credential: one shared ledger meant the first tester to spend the run budget
    closed the door on every other, while their own keys were untouched and the
    panel showed each of them the aggregate as if it were theirs.

    A digest rather than the address. The agent is handed this, and the agent is
    handed no identity (ADR-0820); a funding scope it cannot turn back into a
    person is the same kind of value as the credential it already holds.
    """
    if not admission.configured or admission.account is None:
        return None
    return hashlib.sha256(admission.account.email.encode()).hexdigest()[:16]


def effective_session(admission: Admission, url_session: str) -> str:
    """The key the conversation, the identity stamp and the dev panel all use.

    Under sign-in it is derived from **the account and the link token together**,
    and each half is doing a job:

    - *The account*, because the token alone is supplied by whoever holds the
      link. Keyed on the token, a second reader opening a shared link took over
      the first's identity stamp, and every later record of the first reader was
      attributed to the second (ADR-0830).
    - *The token*, because a conversation has to be escapable. It is the
      LangGraph thread, and a thread that fills up (`CONVERSATION_BOUND`) refuses
      every further question. Keyed on the account alone the key was a pure
      function of the email, so a full conversation could not be left: a fresh
      link did nothing, signing out gave the same key back, and the page's own
      advice -- "reload with a fresh `?session=`" -- was impossible to follow.

    Together: two accounts on one link get two conversations, and one account can
    start a new one whenever it wants. The cap does not use this key at all; it
    counts tabs (`tab_id`).

    Where identity is not configured -- a developer's machine -- the token *is*
    the conversation, exactly as before any of this.
    """
    if admission.configured and admission.account is not None:
        seed = f"{admission.account.email}|{url_session}".encode()
        return f"acct:{hashlib.sha256(seed).hexdigest()[:16]}"
    return url_session


def establish_identity(admission: Admission, session_id: str) -> None:
    """Stamp this session with the signed-in account, or clear it if there is none.

    Called by the driver every rerun of an open page, keyed on the *effective*
    session, so a session pruned for idleness and then returned to is re-stamped
    rather than silently losing its account on the next question -- the bug a
    held admission that never re-registered used to have.
    """
    if admission.identity is not None:
        remember_identity(session_id, admission.identity)
    else:
        forget_identity(session_id)


def end_session(conversation_id: str, tab_id: str | None = None) -> None:
    """Forget everything this deployment holds for one session, in one place.

    The identity stamp, the panel's rows and the cap's heartbeat are three
    per-session stores; a sign-out that cleared only one left the next account on
    the same tab able to see the last one's panel rows. One function so a new
    store, or a new exit path, has one place to join rather than a checklist.

    Two keys, because the stores count different things: the stamp and the panel
    belong to the *conversation*, the cap's place to the *tab*. Signing out of one
    tab frees that tab and ends the conversation -- which is what signing out
    means; the account's other tabs meet the door again on their next rerun.
    """
    forget_identity(conversation_id)
    if RECENT is not None:
        RECENT.forget(conversation_id)
    if tab_id is not None:
        session_registry().drop(tab_id)


def checkpoint_path() -> str:
    """Where the conversation store lives, its directory created on demand: the
    checkpointer creates the file but not the directory above it."""
    checkpoints = env_setting("SCINUMBERS_CHECKPOINTS", DEFAULT_CHECKPOINTS)
    directory = os.path.dirname(checkpoints)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return checkpoints


def agent_for(
    state: MutableMapping[str, Any], repo: CorpusRepository, admission: Admission
) -> AskAgent:
    """One agent per browser session, funded by this account's credential.

    Built into session state rather than under `st.cache_resource`, because the
    credential is per person and a cached agent is per server (ADR-0820). The
    repository -- the expensive index -- stays shared; an agent is a config, a
    reference and a path. Rebuilt if the credential changes under the same tab.

    **Raises for an enrolled account with no credential**, rather than building
    one: an agent made with `api_key=None` falls back to the environment, so an
    unconfigured deployment's own key would quietly fund a tester the operator
    never issued one to. The page never meets that raise, because such an account
    met `Door.NO_CREDENTIAL` before it got here; the raise is the backstop for a
    caller that skipped the door.

    Where no identity is configured, `None` is the environment's key, exactly
    as before this change. Called only for an `OPEN` admission -- an enrolled
    account with no credential is `NO_CREDENTIAL`, a closed door -- so this never
    returns `None` and the page never holds an optional agent. It raises rather
    than fall back to the environment's key for a configured account that
    reaches here without one, which the door should already have prevented.
    """
    if admission.configured:
        account = admission.account
        if account is None or not account.openrouter_key:
            raise ValueError("agent_for called for a configured account with no credential")
        key: str | None = account.openrouter_key
    else:
        key = None
    held = state.get(AGENT_KEY)
    if held is not None and held[0] == key:
        return held[1]
    agent = AskAgent(
        repo,
        Config.from_env(),
        checkpoint_path(),
        api_key=key,
        budget_scope=account_scope(admission),
    )
    state[AGENT_KEY] = (key, agent)
    return agent


def _sign_out(conversation_id: str, tab_id: str | None = None) -> None:
    end_session(conversation_id, tab_id)
    st.logout()


def draw_closed_door(admission: Admission, session_id: str, tab_id: str | None = None) -> None:
    """What a visitor sees instead of the page. Sign-in and nothing else, or the
    one sentence that says why not. The caller stops the script after this."""
    st.title("SciNumbers ask", anchor=False)
    if admission.door is Door.SIGN_IN:
        st.info(as_text(messages.SIGN_IN_NEEDED), icon=":material/login:")
        st.button("Sign in with Google", on_click=st.login, icon=":material/login:")
    elif admission.door is Door.NOT_ENROLLED:
        st.error(as_text(messages.NOT_ENROLLED), icon=":material/person_off:")
        st.button("Sign out", on_click=_sign_out, args=(session_id, tab_id))
    elif admission.door is Door.NO_CREDENTIAL:
        st.error(as_text(messages.NO_CREDENTIAL), icon=":material/key_off:")
        st.button("Sign out", on_click=_sign_out, args=(session_id, tab_id))
    elif admission.door is Door.CREDENTIAL_REJECTED:
        st.error(as_text(messages.CREDENTIAL_REJECTED), icon=":material/key_off:")
        st.button("Sign out", on_click=_sign_out, args=(session_id, tab_id))
    elif admission.door is Door.NO_ACCOUNTS_DATABASE:
        st.error(as_text(messages.NO_ACCOUNTS_DATABASE), icon=":material/database_off:")
    elif admission.door is Door.UNAVAILABLE:
        st.error(as_text(messages.ENROLMENT_CHECK_UNAVAILABLE), icon=":material/cloud_off:")
        # A widget, so the retry the docstring promises can happen without the
        # reader reloading: Streamlit only reruns on interaction.
        st.button("Try again", on_click=lambda: None, icon=":material/refresh:")


#: The button's own key, which Streamlit also emits as the CSS class
#: `st-key-<key>` (read from the installed 1.61.1). That is what makes the rule
#: below reach this button and no other.
SIGN_OUT_KEY = "sign-out"

#: Narrower than this and the identity row has nowhere left to go.
SIDEBAR_MIN_WIDTH_PX = 300

# Three rules the layout cannot express on its own.
#
# The row is a flex container, and a flex item may be squeezed below the size of
# its own content: a narrow panel shrank the button until "Sign out" broke across
# two lines, and then until the frame no longer contained it. `flex: 0 0 auto`
# says this item keeps its content's width and the caption beside it does the
# yielding, which is the right way round -- an email can wrap, a control cannot.
#
# `min-width` on the panel itself, because the reader can drag it narrower than
# anything here can survive. The selector is Streamlit's stable test id, verified
# against 1.61.1; if a future version renames it the rule stops applying and the
# panel goes back to being draggable to nothing, which is where it is today.
SIDEBAR_CSS = f"""
<style>
[data-testid="stSidebar"] {{ min-width: {SIDEBAR_MIN_WIDTH_PX}px; }}
.st-key-{SIGN_OUT_KEY} {{ flex: 0 0 auto; }}
.st-key-{SIGN_OUT_KEY} button {{ white-space: nowrap; }}
</style>
"""


def draw_identity(admission: Admission, session_id: str, tab_id: str | None = None) -> None:
    """Who the page thinks you are -- or that it is nobody's, so the state is
    visible rather than inferred."""
    if not admission.configured:
        st.caption(as_text(messages.NO_SIGN_IN_CONFIGURED))
        return
    account = admission.account
    if account is None:
        st.button(
            "Sign out", on_click=_sign_out, args=(session_id, tab_id), icon=":material/logout:"
        )
        return
    # One row, because the two belong to each other: the button is what you do
    # about the name beside it. Centred vertically so the caption's two lines sit
    # level with the button rather than riding above it. `st.container(horizontal=)`
    # and its alignment arguments are read from the installed Streamlit 1.61.1.
    st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)
    # A horizontal container rather than two columns: columns divide the panel by
    # proportion, so a wide panel put the button far from the name it belongs to,
    # and a narrow one squeezed it. This packs both to the left at the size of
    # their own content, whatever the panel is doing.
    with st.container(
        horizontal=True, horizontal_alignment="left", vertical_alignment="center", gap="small"
    ):
        st.caption(
            as_text(messages.SIGNED_IN_AS.format(email=account.email, role=account.role.value))
        )
        # An ordinary button. Tertiary was tried for one release and drew no
        # border or fill at all, which reads as a stray line of text rather than
        # something to click -- smaller, and no longer recognisable as the way
        # out.
        st.button(
            "Sign out",
            key=SIGN_OUT_KEY,
            on_click=_sign_out,
            args=(session_id, tab_id),
            icon=":material/logout:",
        )


#: The secrets section naming the durable trail's database.
#: `[connections.usage]` in `.streamlit/secrets.toml`, or the same content pasted
#: into Community Cloud's secrets box.
TRAIL_CONNECTION = "usage"


def trail_destination() -> Any | None:
    """The engine for the durable trail, or None when none is configured.

    None is the ordinary case on a developer's machine and must stay ordinary:
    refusing to start without a telemetry database would make the absence of
    telemetry an outage, which is a worse version of the problem the durable
    trail was introduced to solve.

    `st.connection` is used rather than a hand-built engine because it caches the
    engine at global scope across sessions. Without that, every rerun would pay
    TCP, TLS and Postgres auth before its INSERT -- which is the cost that would
    make writing on the render path untenable.

    The timeouts are passed here because `create_engine` takes them at
    construction and they cannot be applied later from inside `record`. That
    makes them the one guard in this arrangement belonging to the caller rather
    than to the operation, which is why they are named here and in
    `trail_store.CONNECT_TIMEOUT_S` rather than left to a default.
    """
    try:
        return st.connection(
            TRAIL_CONNECTION,
            type="sql",
            pool_pre_ping=True,
            # Both figures come from `trail_store` rather than being written here
            # as well: this engine cannot be built by `engine_from_url`, but the
            # two must provably agree, and a duplicated literal is a thing that
            # drifts. The container sleeps after 12 hours of no traffic, so the
            # far side has dropped every connection the pool believes it holds.
            pool_recycle=trail_store.POOL_RECYCLE_S,
            connect_args={"connect_timeout": trail_store.CONNECT_TIMEOUT_S},
        ).engine
    except Exception as exc:  # noqa: BLE001 - neither absence nor a bad URL stops the app
        # Both mean "no sink", and neither stops the app -- but they are not the
        # same thing to an operator, and an earlier version reported neither.
        #
        # Absence is the ordinary case on a developer's machine and says nothing.
        # A configured-but-broken destination is a mistake somebody wants told
        # about, and the likeliest one is the first thing
        # `.streamlit/secrets.toml.example` warns against: pasting the provider's
        # `postgresql://` rather than `postgresql+psycopg://`. That raises inside
        # `create_engine`, here, before any connection is attempted -- so it never
        # reaches the store's own reporting, and the operator would see nothing at
        # all. "Looks configured, records nothing" is this change's own failure.
        if _is_not_configured(exc):
            return None
        trail_store.complain("trail destination unusable", exc)
        return None


def _is_not_configured(exc: BaseException) -> bool:
    """Whether this means "no section in secrets" rather than "a broken one".

    By type, not by message text: the wording is Streamlit's to change, and a
    rule matching on prose goes quietly false the day it does. The two directions
    cost differently -- a misconfiguration misread as absence is silent, which is
    the failure being fixed, while absence misread as a misconfiguration is one
    stray line in a log. So anything unrecognised is reported.
    """
    from streamlit.errors import StreamlitAPIException, StreamlitSecretNotFoundError

    return isinstance(exc, StreamlitAPIException | StreamlitSecretNotFoundError)


def install_trail(engine: Any | None) -> Any | None:
    """Attach the durable sink. Separate from `resources` so a test can call it.

    Thin on purpose: what it must not do is decide anything. The refusal to let a
    failed write break a question lives in `trail_store`, not here -- a tolerance
    written into this driver would protect this driver, and the terminal and the
    evaluation harness would inherit an operation that raises.
    """
    return trail_store.install(engine, logger_name=trace.LOGGER_NAME)


#: Which identity each open session is signed in as. Process-wide, keyed by the
#: session identifier every trail record already carries, and read by nothing
#: but `IdentityStamp`. Populated at sign-in, forgotten at sign-out and when the
#: session registry prunes the session.
#:
#: This is where identity stops. The agent is never handed it; `trace.py` never
#: sees it; `feedback.py` writes through the same logger and is stamped without
#: knowing. `tests/test_driver_independence.py` asserts over the source that none
#: of those three names it (ADR-0810, ADR-0820).
IDENTITIES: dict[str, Identity] = {}


def remember_identity(session_id: str, identity: Identity) -> None:
    IDENTITIES[session_id] = identity


def forget_identity(session_id: str) -> None:
    IDENTITIES.pop(session_id, None)


class IdentityStamp(logging.Filter):
    """Stamps the account and role onto every trail record of a known session.

    A `logging.Filter` on the trail's *logger*, so it runs before any handler --
    the file, the durable store and the dev panel all see the stamped record --
    and so it survives `trace.configure`, which clears the logger's handlers and
    leaves its filters alone. `TrailHandler.emit` already reads `user_email` and
    `user_role` off the record; a record from a session that is nobody's carries
    neither attribute, and the handler's `or None` writes NULL.

    The role is written as its value at the moment of the record, never looked
    up afterwards: a rating's weight is the weight the role carried when it was
    given (ADR-0810).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        identity = IDENTITIES.get(getattr(record, "session_id", None) or "")
        if identity is not None:
            record.user_email = identity.email
            record.user_role = identity.role.value
        return True


def _install_once(kind: type, make: Callable[[], Any]) -> Any:
    """Replace any attachment of `kind` on the trail's logger with a fresh one.

    The idempotence is load-bearing (`trail_store.install`'s docstring says why:
    a stacked handler writes each record once per rerun, and Streamlit reruns
    the whole script on every interaction). Handlers and filters are removed and
    added through different methods, so this branches on which `kind` is.
    `trail_store.install` keeps its own copy: it is in the core, which may not
    import this driver.
    """
    logger = logging.getLogger(trace.LOGGER_NAME)
    made = make()
    if isinstance(made, logging.Filter):
        for existing in [f for f in logger.filters if isinstance(f, kind)]:
            logger.removeFilter(existing)
        logger.addFilter(made)
    else:
        for existing in [h for h in logger.handlers if isinstance(h, kind)]:
            logger.removeHandler(existing)
        logger.addHandler(made)
    return made


def install_identity_stamp() -> None:
    """Attach the stamp to the trail's logger, once."""
    _install_once(IdentityStamp, IdentityStamp)


# --- the session cap --------------------------------------------------------------------

#: How many sessions the deployment holds open at once, and how long a session
#: may go quiet before its place is freed. Both from the environment, so a host
#: with more memory can raise one without a code change; the defaults are the
#: design's (ADR-0790).
MAX_SESSIONS_ENV = "SCINUMBERS_MAX_SESSIONS"
SESSION_IDLE_ENV = "SCINUMBERS_SESSION_IDLE_S"
DEFAULT_MAX_SESSIONS = 20
DEFAULT_SESSION_IDLE_S = 600


@dataclass
class SessionRegistry:
    """Which browser sessions are live, by heartbeat -- and what "live" cannot mean.

    Streamlit offers no reliable disconnect hook, so a session is live for as
    long as it has rerun within `idle_s`. Every rerun of an admitted session
    touches it; one that stops rerunning is pruned when its window passes. A
    closed tab therefore counts as live until then -- **the registry over-counts,
    and so admits fewer than the cap, never more.** That is the cheap direction
    for a guard that protects the host, and ADR-0790 says so where an operator
    tempted to raise the cap will read it.

    **Keyed on the browser session, not on the conversation, and the difference
    is load-bearing.** Under sign-in one account is one conversation across all
    its tabs (ADR-0830), so counting conversations would count *accounts*: eight
    testers with five tabs each is forty Streamlit sessions and forty agents,
    which the cap exists to bound, reported as eight. What costs the host is a
    tab. So each entry is a tab, and it remembers which conversation that tab
    belongs to -- which is what lets pruning clear the identity stamp and the
    panel's rows for a conversation once its *last* tab has gone, and not while
    another is still open.

    Not keyed on the client's address: `st.context.ip_address` is supplied by
    the client and is not evidence of anything.

    The clock is an attribute so a test can move it without patching `time` for
    every other module in the process. The lock is not decoration: Streamlit runs
    one script thread per browser session against this single cached object, so
    two reruns prune concurrently, and a check-then-set on the count can admit
    over the cap.
    """

    max_sessions: int = DEFAULT_MAX_SESSIONS
    idle_s: float = DEFAULT_SESSION_IDLE_S
    clock: Callable[[], float] = time.monotonic
    #: tab -> (last seen, the conversation that tab is in)
    _last_seen: dict[str, tuple[float, str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def prune(self) -> None:
        """Drop tabs past their idle window, and the stores of conversations that
        no live tab is left in."""
        with self._lock:
            cutoff = self.clock() - self.idle_s
            expired = [tab for tab, (seen, _) in self._last_seen.items() if seen < cutoff]
            emptied = {self._last_seen.pop(tab, (0.0, ""))[1] for tab in expired}
            still_open = {conversation for _, conversation in self._last_seen.values()}
            # Inside the lock, and that matters. Released here, another tab's
            # thread could complete its whole prologue in the gap -- re-admit,
            # re-stamp -- and this loop would then wipe the stamp it had just
            # set, so that tab's next question is recorded against nobody while
            # its sidebar still names an account. Neither callee takes a lock,
            # so there is no nesting here to deadlock on.
            for conversation in emptied - still_open:
                forget_identity(conversation)
                if RECENT is not None:
                    RECENT.forget(conversation)

    def live(self) -> int:
        self.prune()
        with self._lock:
            return len(self._last_seen)

    def admit(
        self, session_id: str, conversation_id: str | None = None, *, continuing: bool = False
    ) -> bool:
        """Touch a known tab, or admit a new one if there is room.

        A tab already counted is always re-admitted and never ended: the cap
        refuses the door, it does not clear the room. `continuing` says this tab
        already holds a conversation -- so one pruned for idleness while its
        reader was mid-conversation is re-admitted rather than turned away, which
        "no open session is ended" requires and pruning alone would break. A
        genuinely new tab at the cap is refused and **not recorded**, so a refused
        visitor's retry costs nothing.

        `conversation_id` defaults to the tab's own id, which is what an
        unconfigured deployment wants: there, the two are the same thing.
        """
        self.prune()
        with self._lock:
            known = session_id in self._last_seen
            if known or continuing or len(self._last_seen) < self.max_sessions:
                self._last_seen[session_id] = (
                    self.clock(),
                    conversation_id if conversation_id is not None else session_id,
                )
                return True
        return False

    def drop(self, session_id: str) -> None:
        """Free one tab's place immediately, on sign-out."""
        with self._lock:
            self._last_seen.pop(session_id, None)


def _number(name: str, default: float) -> float:
    """A setting read from the environment, falling back rather than crashing.

    `int("twenty")` raises outside `streamlit_app.py`'s `NotConfigured` handler,
    so a typo in a deployment variable took the whole page down with a stack
    trace where every other misconfiguration gets a sentence. A bad value here
    means the default and a line on the operator's log.
    """
    raw = env_setting(name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"{name}={raw!r} is not a number; using {default}", file=sys.stderr)
        return default


@st.cache_resource
def session_registry() -> SessionRegistry:
    """One registry per server, which is what a cap on the server needs."""
    return SessionRegistry(
        max_sessions=int(_number(MAX_SESSIONS_ENV, DEFAULT_MAX_SESSIONS)),
        idle_s=_number(SESSION_IDLE_ENV, DEFAULT_SESSION_IDLE_S),
    )


@st.cache_data(ttl=120, show_spinner=False)
def _allowance(api_key: str) -> allowance.Allowance:
    """The provider's figure, asked for at most every two minutes per key.

    Cached because this is drawn on every rerun -- every thumb, every expander --
    and a network call on each would put the provider in the path of a click.
    Two minutes is short enough that a tester watching their allowance run down
    sees it move, and long enough that clicking about costs nothing.
    """
    return allowance.fetch(api_key)


def spend_line(spent: int, cap: int, admission: Admission) -> str:
    """One line for the run budget, carrying the key's own ceiling behind it.

    Two captions before this -- the budget, then the key -- and a reader had to
    work out which of the two would stop them first. The budget is what this app
    enforces and goes first; the key is the provider's cap behind it and goes in
    the parenthesis.

    The parenthesis is absent, rather than empty or guessed, where a reader has
    no key of their own or the provider says nothing we recognise: an
    unconfigured deployment's key is the operator's and its balance is not a
    tester's business, and a figure that might be wrong is worse here than none,
    because this is the number a tester would act on.
    """
    line = f"{format_usd(spent)} of {format_usd(cap)}"
    account = admission.account
    if not admission.configured or account is None or not account.openrouter_key:
        return line
    on_key = allowance.as_text(_allowance(account.openrouter_key))
    return f"{line} ({on_key})" if on_key else line


def draw_data_credit() -> None:
    """The attribution, behind a popover rather than under the spend figure.

    Attribution has to be present and does not have to be read on every visit:
    as a caption it was a third standing line in a panel whose job is the run's
    own state. A popover keeps it one click from every page view -- which is what
    the obligation asks -- without spending a line on it.
    """
    with st.popover(DATA_CREDIT_LABEL, icon=":material/database:", width="stretch"):
        st.caption(as_text(DATA_CREDIT))


def draw_try_later() -> None:
    """The page at the cap: one sentence, before sign-in is offered, so the cap
    also bounds the OAuth round trips. The caller stops the script after this."""
    st.title("SciNumbers ask", anchor=False)
    st.warning(as_text(messages.TRY_LATER), icon=":material/hourglass_top:")


# --- the dev panel: a third sink on the same logger ---------------------------------

#: How many of a session's questions the panel keeps. Five, per the spec; the
#: bound is what makes holding this in process memory acceptable.
PANEL_QUESTIONS = 5
PANEL_COLUMNS = ("when", "question", "event", "detail")


@dataclass
class _PanelQuestion:
    """One question's rows for the panel, and the text to name it by.

    `text` starts as the question id and is replaced when `question.asked`
    arrives -- the other records of a question carry only its id. Held per
    (session, question) so one session's records can never rename or erase
    another's, which a bare-question-id map could do for two sessions that
    share an id.
    """

    text: str
    rows: list[dict[str, Any]] = field(default_factory=list)


class RecentTrail(logging.Handler):
    """Keeps each session's trail records for its last few questions, in memory.

    The third sink on the trail's logger, beside the file and the durable store,
    and like them attached after `trace.to_file` because `configure` clears the
    handlers. Unlike them it needs no file and no database, which is why the
    panel works on a developer's machine -- the place it is most used.

    One dict, keyed by `session_id`, of that session's last few questions in the
    order they were asked. The panel's "this session's only" is then a property
    of the data structure rather than a filter at render: there is no query here
    that could be widened by mistake, and nothing shared between sessions to key
    inconsistently. Rows without a session or without a question -- a refused
    sign-in has neither -- are not a question's records and are not kept.

    Never raises out of `emit`: the trail's other handlers hold the same line,
    and a panel that could break a question would be a poor trade.
    """

    def __init__(self, questions: int = PANEL_QUESTIONS) -> None:
        super().__init__(logging.INFO)
        self.questions = questions
        self._sessions: dict[str, OrderedDict[str, _PanelQuestion]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            session = getattr(record, "session_id", None) or None
            question_id = getattr(record, "question_id", None) or None
            if session is None or question_id is None:
                return
            fields = getattr(record, "fields", {}) or {}
            event = record.getMessage()
            questions = self._sessions.setdefault(session, OrderedDict())
            question = questions.get(question_id)
            if question is None:
                question = _PanelQuestion(text=question_id)
                questions[question_id] = question
                while len(questions) > self.questions:
                    questions.popitem(last=False)
            if event == "question.asked" and "question" in fields:
                question.text = str(fields["question"])
            # A shallow copy of the fields rather than a JSON dump: the dump is
            # what `TrailHandler` already pays on the durable path, and doing it
            # again here charged every session -- including every tester whose
            # rows nobody can read -- for a rendering only a dev's page performs.
            # Copied rather than referenced because the caller's dict is not ours.
            question.rows.append(
                {
                    "when": datetime.fromtimestamp(record.created),
                    "event": event,
                    "fields": dict(fields),
                }
            )
        except Exception:  # noqa: BLE001 - a panel must not break a question
            return

    def rows(self, session_id: str) -> list[dict[str, Any]]:
        """This session's rows, oldest first, each named by its question's text."""
        return [
            {
                "when": r["when"],
                "question": question.text,
                "event": r["event"],
                "detail": json.dumps(r["fields"], default=str),
            }
            for question in self._sessions.get(session_id, {}).values()
            for r in question.rows
        ]

    def forget(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


#: The one installed handler, read by `dev_panel_rows`. None until `resources`
#: runs, which on every real page it has.
RECENT: RecentTrail | None = None


def install_recent_trail() -> RecentTrail:
    """Attach the panel's sink, once, after `trace.to_file` for the reason
    `install_trail` gives. Idempotent: an existing one is replaced, not stacked."""
    global RECENT
    RECENT = _install_once(RecentTrail, RecentTrail)
    return RECENT


def may_see_dev_panel(admission: Admission) -> bool:
    """Whether to *draw* the tab. Presentation's question; the refusal is
    `dev_panel_rows`'.

    Both read the grant table through the same `allowed` -- `require` is `allowed`
    plus a raise -- so the two cannot disagree about a role. Asked separately
    because answering it by calling the accessor rendered the whole panel just to
    see whether it would raise, and then rendered it again to draw it: two full
    serialisations per rerun, on every click, for exactly the sessions that have
    rows.
    """
    return not admission.configured or allowed(admission.identity, Permission.DEV_PANEL)


def dev_panel_rows(admission: Admission, session_id: str) -> list[dict[str, Any]]:
    """This session's recent trail -- **the operation the permission guards.**

    `require` is here, in the accessor, and not on the page: whatever asks for
    these rows -- the sidebar, a test, a later page -- meets the same refusal,
    and a page that merely hid the section would have enforced nothing. Refused
    with no identity, and for every role the table does not grant.

    Where no identity is configured the rows are given: a session that is
    nobody's is the developer's. That is the deferred decision the spec and the
    roadmap both record -- to be decided again before this panel shows anything
    more than the session's own trail.
    """
    if admission.configured:
        require(admission.identity, Permission.DEV_PANEL)
    return RECENT.rows(session_id) if RECENT is not None else []


#: What the sidebar's tab strip is called, in the order it is drawn. The entries
#: come first because they are what a reader is there for; the trail is the
#: operator's view of the same session and sits behind it.
ENTRIES_TAB = "Full entries"
DEV_TAB = "Dev"


def sidebar_tabs(admission: Admission, session_id: str) -> tuple[Any | None, Any | None]:
    """The sidebar's two views as a tab strip, or no strip at all.

    Returns seats to be filled later -- a Streamlit container is bound to where
    it was made, so the strip is created here, below the run status, and written
    into at the end of the script when the newest question's entries and trail
    records both exist.

    **No strip where the dev panel is refused.** A lone tab labelled "Full
    entries" is a control that does nothing, and a strip whose second tab is
    missing would be the "disabled, not absent" the spec forbids -- a tester's
    page must not show that there is a view they cannot open. The entries then
    draw into the sidebar exactly as they did before tabs existed.

    Whether the panel is refused is asked by trying it, so the rule lives in one
    place: `dev_panel_rows` holds the `require`, and this reads its answer.
    """
    if not may_see_dev_panel(admission):
        return None, None
    with st.sidebar:
        entries, dev = st.tabs([ENTRIES_TAB, DEV_TAB])
    return entries, dev


def draw_dev_panel(admission: Admission, session_id: str, seat: Any | None = None) -> None:
    """This session's trail, into the Dev tab. Nothing at all when refused.

    `seat` is `None` exactly when `sidebar_tabs` refused the panel, so there is
    nowhere to draw and nothing to draw -- present and *empty* on a fresh
    session, so a dev can tell "nothing yet" from "not permitted", and absent
    rather than empty for everyone else.
    """
    if seat is None:
        return
    try:
        rows = dev_panel_rows(admission, session_id)
    except Refused:
        return
    import pandas as pd

    with seat:
        # No caption explaining what this is: the only people who can open this
        # tab are the ones who built it.
        st.dataframe(pd.DataFrame(rows, columns=list(PANEL_COLUMNS)), hide_index=True)


@st.cache_resource(show_spinner="Loading the corpus…")
def resources(corpus: str | None = None) -> CorpusRepository:
    """The corpus index, built once for the life of the server, and the trail's
    sinks attached beside it.

    Cached because the indexes are built over the whole corpus and Streamlit
    would otherwise rebuild them on every interaction; task 8.2 verifies that
    they are not. Configuration comes from the environment because a Streamlit
    script has no argv to read it from.

    The agent is no longer built here: it holds a credential, and a credential
    is per person where a cached resource is per server. `agent_for` builds one
    per session (ADR-0820).
    """
    refuse_retired_env()
    trace.to_file(env_setting("SCINUMBERS_TRACE", trace.DEFAULT_FILE))
    # **After `to_file`, and the order is load-bearing.** `to_file` calls
    # `trace.configure`, which clears the logger's handlers -- so installing the
    # durable sink first would attach it and then silently throw it away, leaving
    # an app that looks configured and records nothing. Exactly the failure this
    # whole change exists to end, reintroduced two lines further up.
    # `test_web_driver_trail.py` pins the ordering rather than this comment.
    install_trail(trail_destination())
    # Beside the sinks rather than at sign-in: the stamp reads the registry at
    # record time, so it is installed once per process and knows nobody until a
    # session signs in. A logger-level filter would survive `to_file` either way;
    # it sits here so that everything attached to the trail is attached in one
    # place.
    install_identity_stamp()
    install_recent_trail()
    # The corpus path is resolved by the caller, outside this function. Anything
    # drawn inside a cached function is recorded and replayed on every cache hit,
    # so an `st.info` announcing a build would be redrawn at the top of the page
    # for the life of the server -- a notice that was true once and false for every
    # rerun after it.
    if corpus is None:
        corpus = env_setting("SCINUMBERS_CORPUS")
    return CorpusRepository(load(corpus))


def as_text(text: str) -> str:
    """Escape what Streamlit's markdown would read as something other than text.

    `$` opens inline mathematics. An ending line carries two of them -- "$0.008181
    (run $0.008181)" -- so the cost between was typeset as an equation and both
    signs were consumed as delimiters, leaving a figure with no currency on it.

    Applied at the point of drawing rather than where the text is built: the item
    carries what the ending says, and how to stop a renderer misreading it is the
    renderer's problem. The terminal driver prints the same string and needs none
    of this.
    """
    return text.replace("$", r"\$")


def _row_label(row: entries_table.Row) -> str:
    """One line identifying an entry, for the side panel's collapsed rows."""
    value = "" if not row.has_scalar else f"{row.value} {row.units}".strip()
    parts = [row.property, row.organism, value, bionumbers.label(row.entry_id)]
    label = " · ".join(part for part in parts if part)
    marks = _markers(row)
    return f"{marks} {label}" if marks else label


def _markers(row: entries_table.Row) -> str:
    """The terminal's markers, plus the one only this driver needs.

    The value column here is blank where the corpus holds no scalar, so the
    absence is marked and explained once in the legend rather than spelled out in
    every such row.
    """
    marks = row.markers()
    return marks + (entries_table.NO_SCALAR if not row.has_scalar else "")


def _legend(rows: tuple[entries_table.Row, ...]) -> list[str]:
    """What the markers mean, said before the table rather than after it.

    A legend below the table is read after the rows it explains, which is the
    wrong order: a reader meets a dagger, wonders, and has to look past the thing
    they were reading.
    """
    applying = (
        (entries_table.NOT_RETRIEVED_LEGEND, lambda r: not r.retrieved),
        (entries_table.NO_METHOD_LEGEND, lambda r: not r.method_recorded),
        (entries_table.NO_SCALAR_LEGEND, lambda r: not r.has_scalar),
        (entries_table.QUALIFIED_LEGEND, lambda r: r.qualified),
        (entries_table.FUSED_LEGEND, lambda r: r.fused),
        (entries_table.IMPLAUSIBLE_LEGEND, lambda r: r.implausible_span),
    )
    return [legend for legend, applies in applying if any(applies(row) for row in rows)]


def _frame(rows: tuple[entries_table.Row, ...]) -> list[dict[str, Any]]:
    """The table's cells, in the reference database's column order."""
    return [
        {
            "Property": f"{_markers(row)} {row.property}".strip(),
            "Organism": row.organism,
            "Value": row.value if row.has_scalar else "",
            "Units": row.units,
            # A string, not a number: an identifier formatted as a quantity picks
            # up a thousands separator and stops matching the citation in the prose.
            "ID": str(row.entry_id),
            "Reference": row.reference,
        }
        for row in rows
    ]


def _draw_entry(row: entries_table.Row) -> None:
    """The whole entry, behind the row that names it.

    Every field is read from the corpus. Nothing here came from the model, so an
    opened row is the evidence against which its prose can be checked -- which is
    the point of being able to open it at all.
    """
    st.markdown(f"**{as_text(row.property)}** — {as_text(row.organism)}")
    if row.has_scalar:
        st.markdown(f"{as_text(row.value)} {as_text(row.units)}".strip())
    else:
        st.caption(entries_table.NO_SCALAR_LEGEND)
    if row.method:
        st.markdown(f"*Measurement method.* {as_text(row.method)}")
    else:
        st.caption(entries_table.NO_METHOD_LEGEND)
    if row.comments:
        st.markdown(f"*Comments.* {as_text(row.comments)}")
    keywords = shown_keywords(row)
    if keywords:
        st.caption("Keywords: " + as_text(", ".join(keywords)))
    reference = row.reference or "(no reference recorded)"
    pubmed = f" · PubMed {row.reference_pubmed_id}" if row.reference_pubmed_id else ""
    st.caption(as_text(f"{reference}{pubmed}"))


def shown_keywords(row: entries_table.Row) -> list[str]:
    """The keywords that will actually appear, markup already stripped.

    Testing `row.keywords` instead drew a bare "Keywords: " for every entry whose
    only keyword was the injected `<IMG SRC=...>` -- which `_without_markup`
    empties, and which the corpus carries on 10,206 of 14,294 records.
    """
    return [keyword for keyword in row.keywords if keyword]


def summary_for(table: Table, shown: int) -> str:
    """How much went unshown, or "" when there is nothing to report.

    Guarded as the terminal guards it. `table.rows` includes entries cited without
    being retrieved while `table.retrieved` counts only retrieved ones, so `shown`
    can exceed it and the ungated sentence read "showing 4 of 1 entries retrieved".
    """
    if table.retrieved > shown or table.matched > shown:
        return entries_table.summarise(shown, table.retrieved, table.matched, table.searches)
    return ""


def _dataframe(rows: tuple[entries_table.Row, ...]) -> None:
    st.dataframe(
        _frame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            name: st.column_config.TextColumn(width=width) for name, width in COLUMN_WIDTHS.items()
        },
    )


def _draw_table(table: Table) -> None:
    """The entries table: cited first, separated from the rest.

    Two tables under two headings rather than one with a marker column. The
    separation is what a reader checking prose against evidence needs, and a
    column they have to scan for does not give it to them.
    """
    every_cited = tuple(row for row in table.rows if row.cited)
    cited = every_cited[:CITED_ROWS]
    rest = tuple(row for row in table.rows if not row.cited)[:UNCITED_ROWS]
    shown = cited + rest

    if cited:
        st.markdown("**Cited in the answer**")
        _dataframe(cited)
    else:
        # Not silence: an answer that cited nothing is a fact about the answer,
        # and a table that just began with uncited rows read as though it had.
        st.markdown(f"**{entries_table.NOTHING_CITED}**")
    # Loud, not a caption. An answer resting on an entry the table does not show
    # is the one omission a reader cannot detect by looking, and the table is
    # where they would look. All of them are in the side panel.
    missing = len(every_cited) - len(cited)
    if missing:
        st.warning(
            as_text(
                f"{missing} more cited "
                f"{'entry is' if missing == 1 else 'entries are'} not shown here — "
                "every one is in the side panel."
            ),
            icon=":material/warning:",
        )
    # Between the two tables: a reader meets the marks in the cited rows, reads
    # what they mean, and carries that into the rows below. Before both it is
    # explaining marks nobody has seen yet; after both it is too late.
    for line in _legend(shown):
        st.caption(as_text(line))
    if rest:
        # Folded away, where the cited table is not. These rows are what the answer
        # *did not* stand on: context for a reader who wants to know what else was
        # there, and length in front of one who is checking the prose against its
        # evidence. The label is the heading, so what is behind it is legible
        # without opening it.
        #
        # Splitting the turn into columns weakened the original argument -- these
        # rows no longer push anything downwards, they sit beside the prose. It
        # still holds in the weaker form that matters: the page is as tall as its
        # tallest column, so an unfolded second table scrolls the prose too.
        with st.expander(entries_table.UNCITED_BANNER.capitalize()):
            _dataframe(rest)

    note = entries_table.dimension_note(table.rows)
    if note:
        st.caption(as_text(note))
    summary = summary_for(table, len(shown))
    if summary:
        # Body text, not a caption. How much of the corpus went unlooked-at is one
        # of the few things a reader can use to judge whether an answer is worth
        # trusting, and it was set in the same grey as the footnotes.
        st.markdown(as_text(summary.removeprefix("… ")))


def draw_full_entries(table: Table | None, seat: Any | None = None) -> None:
    """Every retrieved entry, whole and openable, in the side panel.

    Drawn whether or not there is anything to put in it, so the panel is part of
    the page rather than something that appears once a question has been asked --
    a panel that materialises later reads as a glitch, and other sections will
    live beside this one.

    All of the entries, not the table's first few: this is where "the rest" is
    reached, and an entry the answer passed over is part of the evidence. Only
    the newest question's, because the panel is for reading the answer in front
    of you and a session's worth would bury it.
    """
    with seat if seat is not None else st.sidebar:
        # The tab's own label is the heading when there is a strip; a header
        # repeating it underneath is the same word twice.
        if seat is None:
            st.header(ENTRIES_TAB, anchor=False)
        if table is None:
            st.caption("The entries behind an answer appear here once you ask something.")
            return
        for row in table.rows:
            with st.expander(as_text(_row_label(row))):
                _draw_entry(row)


def latest_table(transcript: Iterable[tuple[str, list[Item]]]) -> Table | None:
    """The newest question's entries, or None if that question produced none.

    The newest question's, not the newest that had any. Falling back to an older
    one leaves a previous question's entries under a heading that says "Full
    entries", with nothing on the page marking them as belonging to a question
    already answered -- and the main column's warning about rows not shown here
    would then be pointing at a panel that no longer holds them.
    """
    for _, items in reversed(list(transcript)):
        for item in items:
            if item.kind is Kind.ENTRIES and item.table is not None:
                return item.table
        return None
    return None


def draw_prototype_banner() -> None:
    """The caveat, pinned so it is still there after the tenth answer.

    Deliberately not a dismissible one. The page shows identifiers, dimension
    checks and marked entries -- every signal a reader uses to judge a number
    solid -- so the statement that none of it has been evaluated has to outlast
    the reader's growing confidence in it.
    """
    st.markdown(PROTOTYPE_BANNER_CSS, unsafe_allow_html=True)
    # The note is written as markdown, and this element is raw HTML, where `**`
    # renders as two asterisks. One source of words, two renderings of it.
    emphasised = PROTOTYPE_NOTE.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
    st.markdown(f'<div class="bn-caveat">{emphasised}</div>', unsafe_allow_html=True)


def run_is_over(transcript: Iterable[tuple[str, list[Item]]]) -> bool:
    """Whether any question ended the run, so the page should stop taking them.

    The terminal returns from its read loop on these endings; without the same
    check here the chat input stays live and every further question replays an
    identical refusal, which reads as a broken app rather than a limit reached.
    Any question, not the last: nothing un-spends a run budget.
    """
    return any(
        item.ends_the_run for _, items in transcript for item in items if item.kind is Kind.ENDING
    )


def run_over_advice(
    transcript: Iterable[tuple[str, list[Item]]], *, signed_in: bool = False
) -> str:
    """What to say about the ending that shut the door, or "" for nothing to add.

    `signed_in` picks the wording for a reader who is not the funder -- a tester
    whose key an operator issued -- so the last line on screen tells them whom to
    ask, rather than the funder-neutral sentence written for a developer on their
    own key. Decided here, at draw time, because whether there is such an
    operator is a fact about the deployment and not about the ending.

    The page's own line -- start a new session -- is right for a spent budget and a
    full conversation, and wrong for a key with no credit: the new session's first
    question meets the same refusal. So the ending that stopped the run gets to
    replace it.

    The first such ending, not the last: it is the one that closed the run, and
    whatever ended a question after that describes a run that was already over.
    """
    for _, items in transcript:
        for item in items:
            if item.kind is Kind.ENDING and item.ends_the_run and item.stop_advice:
                if signed_in and item.reason is not None:
                    return messages.run_over_advice(item.reason, signed_in=True) or item.stop_advice
                return item.stop_advice
    return ""


def run_status(
    transcript: Iterable[tuple[str, list[Item]]],
    fallback: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """What the run has spent and what it may spend.

    Read from the ending events where there is one, rather than from configuration,
    because a session resumed in a process configured differently spends against
    the budget it was created with -- reading the environment would report a cap
    this run is not subject to.

    `fallback` covers the interval before the first answer, where no ending exists
    to read. It is the run's own recorded spend against the configured budget,
    which is the same pair the first ending will carry. Without it the panel gained
    a section the moment a question completed, and a layout that grows under the
    reader is a worse surprise than a bar reading zero.
    """
    latest = fallback
    for _, items in transcript:
        for item in items:
            if item.kind is Kind.ENDING and item.run_budget:
                latest = (item.run_spend, item.run_budget)
    return latest


def draw(item: Item) -> None:
    """Draw one item. The only function here that touches the screen."""
    if item.kind is Kind.ANSWER:
        st.markdown(as_text(item.text))
    elif item.kind is Kind.ENTRIES:
        if item.table is not None:
            _draw_table(item.table)
    elif item.kind is Kind.WARNING:
        st.warning(as_text(item.text), icon=":material/warning:")
    elif item.kind is Kind.PROGRESS:
        st.caption(f"· {as_text(item.text)}")
    else:
        st.caption(as_text(item.text))


#: The retrieval box, running and finished. Two names because the box outlives
#: the search: the live path opens it on the first retrieval and relabels it when
#: the answer is done, and the replay path draws it already finished.
#:
#: Constants rather than two literals, because they drifted. The replay path was
#: drawing a search that had finished under the present-tense label, so every past
#: turn claimed to still be searching. Invisible while the live render was the one
#: the reader saw after asking; the rerun that revives older ratings replaced it
#: with the replay render, and a test that had only ever covered the live path
#: failed.
RETRIEVAL_RUNNING = "Searching the corpus…"
RETRIEVAL_DONE = "Retrieval"


def _retrieval_box(expanded: bool, state: str = "running", label: str = RETRIEVAL_RUNNING):
    # `as_text` although both callers pass a constant of this project's own words:
    # the escaping scan reads the call, not the call sites, and a parameter is
    # exactly the shape it cannot clear. Wrapping is free -- neither constant holds
    # a dollar -- and the alternative is teaching the scan to chase defaults.
    return st.status(as_text(label), expanded=expanded, state=state)


def _column_for(item: Item, prose: Any, evidence: Any) -> Any:
    """Which of the turn's two columns this item belongs in.

    Everything the reader reads goes left -- prose, the warnings about it, the
    rating, the ending. Only the entries table goes right, because it is the one
    thing they check the prose *against*, and side by side is the whole reason
    for splitting the turn at all.
    """
    return evidence if item.kind is Kind.ENTRIES else prose


def _ends_the_prose(item: Item) -> bool:
    """Whether this item is the first thing after the answer's prose.

    The turn arrives as prose, then any warning about that prose, then the table
    of entries, then the ending. The rating goes at this seam, at the foot of the
    prose it is about.

    It used to earn its place by keeping the rating above a table long enough to
    push it off the screen. The table is in the next column now, so that argument
    is gone and the seam is kept for the plainer one: a reader forms a view at the
    end of the prose, and that is where the control should be waiting.

    Shared by the live path and the replay path deliberately. They draw the same
    turn in two different places, and a seam computed twice is a seam that moves.
    """
    return item.kind in (Kind.ENTRIES, Kind.ENDING)


def answer(
    events: Iterable[Event],
    repo: CorpusRepository | None = None,
    into: list[Item] | None = None,
    after_prose: Callable[[], None] | None = None,
) -> list[Item]:
    """Draw a question's items as they arrive, recording each into `into` as it goes.

    Each progress line is its own element rather than one line rewritten in
    place. Streamlit composes successive writes to one screen location into the
    last of them, so a rewritten line would leave no trace of the sequence -- for
    a reader scrolling back or for a test (ADR-0100).

    `into` is the transcript's own list, filled in place, so a failure while
    drawing cannot lose the question. Returning the items and letting the caller
    append them meant a raising `draw` skipped the append entirely, while the agent
    had already persisted the turn -- the page forgot a question the model
    remembered, and the next answer was built on context nothing on screen showed.

    The box is opened by the first retrieval rather than before the loop, because a
    question that retrieves nothing -- a refusal, a spent key, an answer the model
    gave straight -- otherwise left an empty "Retrieval" box on screen, claiming a
    search that never happened. `show` has always guarded this on the replay path;
    only the live path drew it unconditionally.

    Opening it late also places it where the first retrieval falls rather than
    always at the top, so a warning raised before any tool call now appears above
    it instead of below. That is the order the events actually arrived in.

    `after_prose` gets a *seat* at the seam `_ends_the_prose` names, and is called
    into it once the generator is exhausted. **It must not be called at the seam
    itself**, which is what this did first and is a defect a reader found by
    clicking: a widget is live in the browser the moment it renders, a click on it
    re-runs the script, and a re-run abandons this generator at whatever yield it
    had reached. The agent persists the turn as it goes, so a rating pressed while
    the answer was still arriving cancelled the tool call it was in the middle of
    and left the turn half-finished.

    A Streamlit container is bound to the place it was made, so reserving one at
    the seam and filling it later puts the control exactly where calling at the
    seam did -- without it existing while there is still work to interrupt. The
    same trick the retrieval box already used, for the same reason.
    """
    box = None
    seat = None
    prose, evidence = st.columns(READING_SPLIT, gap="large")
    drawn: list[Item] = [] if into is None else into
    for item in items_for(events, repo):
        if item.kind is Kind.PROGRESS and box is None:
            # Created inside the column, drawn into afterwards. A Streamlit
            # container is bound to the place it was made, so `with box` works
            # from anywhere once it exists -- which is what lets the loop keep
            # one flat shape while writing into two columns.
            with prose:
                box = _retrieval_box(expanded=True)
        if after_prose is not None and seat is None and _ends_the_prose(item):
            with prose:
                seat = st.container()
        with box if item.kind is Kind.PROGRESS else _column_for(item, prose, evidence):
            draw(item)
        drawn.append(item)
    if box is not None:
        box.update(label=RETRIEVAL_DONE, state="complete", expanded=False)
    if after_prose is not None:
        # The generator is spent by now, so there is nothing left for a click to
        # interrupt. A turn that never reached the seam gets the foot of its own
        # column, which is where the seam would have put it anyway.
        with seat if seat is not None else prose:
            after_prose()
    return drawn


#: Shown above the comment box. Short on purpose: a hint that wraps into a
#: paragraph is one nobody reads, and this one has to survive being skimmed.
#:
#: It asks for an identifier by name because per-entry rating is not built, and
#: what readers choose to write about entries is the evidence for whether it
#: should be (ADR-0740). "e.g. 102345" rather than "e.g. BNID 102345": readers
#: copy the format they are shown, and the bare number is what a query can find
#: either way.
FEEDBACK_HINT = "What was wrong? If an entry is incorrect, please give its ID (e.g. 102345)."

FEEDBACK_THANKS = "Thanks — recorded."

# The thumbs, in orange. `st.feedback` has no colour parameter in 1.61.1 -- its
# whole signature is options, key, default, disabled, on_change, args, kwargs,
# width -- so this is CSS over the rendered control.
#
# Orange rather than red, though both were offered. Red on a thumbs *up* reads as
# an alarm about the thing the reader just approved of; orange is an attention
# colour and not an error one, so the same rule can cover both thumbs without one
# of them saying something wrong.
#
# **`stFeedback`, not `stButtonGroup`, and the difference was a shipped bug.**
# `st.feedback` has its own module and enqueues as `"feedback"`, so the frontend
# renders its `Feedback` component -- test ids `stFeedback` and
# `stFeedbackButton`. `stButtonGroup` belongs to `st.pills` and
# `st.segmented_control`. The first version of this rule named the latter, matched
# nothing, and the thumbs stayed grey.
#
# The test that was supposed to prevent that asserted the id appeared in the
# frontend bundle. It does -- in `ButtonGroup.DMpjOF8Q.js`, for a different
# widget. So a grep-level check passed while the feature was dead, which is why
# `test_the_colour_rule_names_an_id_st_feedback_actually_renders` now reads the
# id out of the `Feedback` component's own bundle instead of looking for a string
# anywhere in `static/`.
#
# **This degrades to nothing.** If a future version renames either id the rule
# matches nothing and the thumbs keep their default colour -- a strictly safer
# failure than the prototype banner's, which falls back to sitting in the page.
#
# **`:not(:disabled)` is the load-bearing part, and it took three attempts to get
# right.** `answer-feedback` requires that a rating, once given, is *shown* as
# settled. Streamlit does that itself: `Feedback`'s `&:disabled` rule replaces the
# button's colour with `fadedText40` when selected and `fadedText10` when not.
#
# But it sets that colour on the *button*, and the icon is a separate span whose
# own class declares `color: inherit` -- specificity 0,1,0. A rule reading
# `[data-testid="stFeedback"] [data-testid="stIconMaterial"]` is 0,2,0, so it wins,
# `inherit` never resolves, and the disabled colour has nothing to propagate to.
# The thumbs would stay fully orange after rating, with `cursor: not-allowed` as
# the only remaining signal -- the requirement quietly unmet by a stylesheet.
# There is no `!important` in that bundle to save it.
#
# So the rule declines to apply to a disabled control rather than overriding it.
# That also avoids naming which half of the pair is selected --
# `stFeedbackButtonActive` is the markup most likely to move under us, and letting
# Streamlit keep its own state styling means never having to track it.
#: **Live thumbs only. The settled state is deliberately left alone.**
#:
#: Two attempts to style a *rated* thumb both went wrong — first by relying on
#: Streamlit's disabled colour reaching the icon through `inherit`, then by
#: fading it with `opacity` — and neither could be checked from here, because
#: nothing in this suite renders CSS. The `:disabled` half also had a consequence
#: nobody wanted: the control is disabled while any question is answering, not
#: only once rated, so every earlier turn's thumbs changed appearance for the
#: duration of every run.
#:
#: So the rule colours the thumbs and stops. Whatever a rated thumb looks like is
#: Streamlit's business, and the widget is still disabled, still `aria-checked`,
#: and still shows `cursor: not-allowed`.
FEEDBACK_CSS = """
<style>
[data-testid="stFeedback"] [data-testid="stIconMaterial"] { color: #ff9d3c; }
@media (prefers-color-scheme: light) {
  [data-testid="stFeedback"] [data-testid="stIconMaterial"] { color: #c2410c; }
}
</style>
"""


def draw_feedback_style() -> None:
    """Emit the thumbs' colour rule, once for the page.

    Once, not per rating: `draw_feedback` runs for every turn in the transcript,
    and a `<style>` block per turn is the same rule repeated as many times as the
    conversation is long. It is a page-level element, so it is drawn where the
    page's other one is.
    """
    st.markdown(FEEDBACK_CSS, unsafe_allow_html=True)


def question_id_of(items: Iterable[Item]) -> str:
    """The question a turn's items came from, or "" if none say.

    Empty rather than raising: an item drawn before this field existed, or a turn
    that produced nothing but an ending, is a turn with no rating rather than a
    crash on a page somebody is reading.
    """
    for item in items:
        if item.question_id:
            return item.question_id
    return ""


def is_ratable(items: Iterable[Item]) -> bool:
    """Whether this turn has something a reader could form a view about.

    An answer. Not an ending alone: a question that stopped at a spend ceiling or
    a missing key produced nothing the reader can judge, and offering a thumb
    there collects a verdict on the infrastructure while looking like a verdict on
    the science.
    """
    items = list(items)
    return bool(question_id_of(items)) and any(item.kind is Kind.ANSWER for item in items)


def question_pending(state: Any) -> bool:
    """Whether a question has been submitted and is about to be answered.

    True for the whole of the run that answers it, including the part before the
    agent is called -- which is the point. Every control already on the page is
    live in the browser while that run is working, and a click on any of them
    re-runs the script, abandoning the agent's generator mid-tool-call. So the
    page needs to know this *before* it redraws the transcript, not after.
    """
    return bool(state.get(ASK_KEY))


def draw_feedback(
    items: Iterable[Item], session_id: str, state: Any = None, *, answering: bool = False
) -> None:
    """Offer a rating for one answered turn, and a comment once it has been rated.

    **Drawn once per turn per script run**, which is a property of where it is
    called rather than of anything here: the transcript loop redraws past turns
    and the live branch draws the new one, and the new turn joins the transcript
    only after that loop has finished. Move the append above the loop and this
    draws twice, which is a `DuplicateWidgetID` and not a subtle failure --
    `test_web_driver_feedback.py` pins it anyway, because the subtle version is
    what happens if the keys ever stop being unique.

    Keys derive from the question identifier, never from the turn's position.
    Position looks stable because the transcript is append-only, but it lives in
    session state alone -- reopening the same `?session=` restarts it at 0 while
    the conversation continues, so two different questions would share a key. The
    loud version of that is a duplicate-key error; the quiet version is a rating
    landing on the wrong answer with no error at all.
    """
    state = st.session_state if state is None else state
    items = list(items)
    if not is_ratable(items):
        return
    question_id = question_id_of(items)
    given = feedback.rating_for(state, question_id)

    st.feedback(
        "thumbs",
        key=_verdict_key(question_id),
        # `or answering`: inert for the whole of a run that is answering a
        # question. Everything on the page is clickable while the agent works, and
        # a click re-runs the script, which abandons the generator at whatever
        # yield it had reached -- so a thumb on a *past* answer could cancel the
        # tool call of the question being asked now.
        # Disabled once given, rather than left live. Clicking a selected thumb
        # clears it, and Streamlit discards the state of a widget it did not
        # render -- so an un-disabled control lets a reader wipe the comment box
        # out from under their own half-typed comment. A rating is final for the
        # answer (`answer-feedback`), and the control should look final too.
        disabled=given is not None or answering,
        on_change=_took_a_verdict,
        args=(question_id, session_id, state),
    )
    if given is None:
        return
    # Only disapproval opens the box. The hint asks what was *wrong*, which is a
    # question nobody can answer about an answer they just approved -- a reader
    # who thumbs up and is then asked what went wrong reads it as the page not
    # having registered the click. Approval is the cheap signal, and the whole
    # point of it being cheap is that it asks for nothing further.
    if given.verdict is not feedback.Verdict.DOWN or given.commented:
        st.caption(FEEDBACK_THANKS)
        return
    _draw_comment_box(question_id, session_id, state, answering=answering)


def _verdict_key(question_id: str) -> str:
    return f"scinumbers_ask.verdict.{question_id}"


def _comment_key(question_id: str) -> str:
    return f"scinumbers_ask.comment.{question_id}"


def _took_a_verdict(question_id: str, session_id: str, state: Any) -> None:
    """Record on the click, not on the comment.

    Most readers who rate will do nothing else, and a design that waits for a
    second action to commit the first collects nothing from them.
    """
    verdict = feedback.Verdict.from_widget(state.get(_verdict_key(question_id)))
    if verdict is None:
        return
    feedback.record_verdict(state, question_id=question_id, session_id=session_id, verdict=verdict)


def _draw_comment_box(
    question_id: str, session_id: str, state: Any, *, answering: bool = False
) -> None:
    """The comment, offered only after disapproval, and inside a form of its own.

    **The thumb must stay outside this form** -- inside one it would read `None`
    until the form submitted, so the box could never appear conditionally on it
    at all. The form holds the text and its button, which is what a form is for:
    several widgets submitted as one act.

    It is a form rather than a text area beside a button because the plain pair
    takes two actions to send. Typing leaves the text uncommitted; the first
    click or Ctrl+Enter commits it and reruns; only a second one presses Send.
    A `disabled=` on the button made that worse rather than better -- the first
    click landed on a disabled control and did nothing at all. A form submits the
    text and the press together, so one action sends.

    **Where the draft actually lives, corrected.** This used to say the draft was
    held in the widget's own session-state key. It is not: a form batches its
    widgets and sends nothing to the server until the submit button is pressed
    (`streamlit/elements/form.py` -- "all widget values inside the form will be
    sent to Streamlit in a batch"), so before submit that key still holds `""`.
    The draft is in the browser, kept by the frontend re-rendering the same
    widget key across re-runs.

    In practice that holds, and drawing the box disabled rather than skipping it
    is still what keeps the widget mounted. But it is the frontend's behaviour and
    not a guarantee this code provides, so `answer-feedback`'s "a comment in
    progress SHALL NOT be lost when the page is redrawn" rests on something
    nothing here can enforce and nothing here can test -- `AppTest.set_value`
    writes straight into server-side widget state, which is exactly what a browser
    does *not* do before submit, so the test that appears to cover this would pass
    even if the draft were dropped.
    """
    key = _comment_key(question_id)
    with st.form(key=f"{key}.form", border=False):
        # Drawn while a question is being answered, not skipped -- only disabled.
        # Streamlit discards the state of a widget it did not render, so leaving
        # this out for the duration of a run would take a half-typed comment with
        # it, which is exactly what the rating is disabled rather than hidden to
        # avoid.
        text = st.text_area(FEEDBACK_HINT, key=key, height=80, disabled=answering)
        sent = st.form_submit_button("Send", disabled=answering)
    # Empty is a no-op rather than a refusal: the button cannot be disabled for it
    # without reintroducing the two-action problem above, and there is nothing to
    # tell a reader who pressed Send with nothing typed that they do not know.
    if sent and text.strip():
        feedback.record_comment(state, question_id=question_id, session_id=session_id, text=text)
        st.rerun()


def show(items: Iterable[Item], after_prose: Callable[[], None] | None = None) -> None:
    """Put a finished question's items back on screen after a re-run.

    Retrieval is collapsed here, where the live path leaves it open: while a
    question is running the progress is the only thing to look at, and once it
    has an answer the progress is the thing in the way.

    `after_prose` lands at the same seam as on the live path, by the same
    predicate -- a past turn and the turn just answered must not put the rating in
    two different places, or scrolling back changes the layout.
    """
    items = list(items)
    prose, evidence = st.columns(READING_SPLIT, gap="large")
    progress = [item for item in items if item.kind is Kind.PROGRESS]
    if progress:
        with prose, _retrieval_box(expanded=False, state="complete", label=RETRIEVAL_DONE):
            for item in progress:
                draw(item)
    for item in items:
        if item.kind is Kind.PROGRESS:
            continue
        if after_prose is not None and _ends_the_prose(item):
            with prose:
                after_prose()
            after_prose = None
        with _column_for(item, prose, evidence):
            draw(item)
    if after_prose is not None:
        with prose:
            after_prose()
