"""What a reader thought of an answer, recorded and never shown to the model.

Two records, not one. A verdict is written the moment a thumb is clicked, because
most readers who rate will do nothing further and a design that waits for a
second action to commit the first collects nothing from them. A comment, if it
comes, is a **second** record naming the same question -- the table is
append-only, so a reader who rates and then explains is two events in time order,
which is what actually happened.

**This module is on the presentation side of the dependency line, and that is the
requirement rather than a filing decision.** `trail_store` is core because the
agent legitimately records its own trail; feedback is the opposite direction --
it is a stranger's judgement of the agent, and `answer-feedback` requires that
the model never sees it. Listing this module in `test_driver_independence.py`'s
`PRESENTATION` set turns that requirement into a test: an `import feedback` in
`agent.py` or `tools.py` fails the suite. A comment asking the model to disregard
its instructions must not arrive by this route.

Nothing here holds the store. Records go to `trace`'s logger, which is where the
durable sink is already attached, so feedback inherits the fail-open policy
(ADR-0710) rather than restating it: a rating that cannot be written must never
interrupt a reader mid-conversation.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from . import trace
from .config import env_setting

#: Namespaced, because session state is one flat dictionary shared with every
#: widget key on the page.
STATE_KEY = "scinumbers_ask.feedback"

#: Event names, which are what a query filters on. Written as constants rather
#: than literals at the call sites: the table is append-only and a typo'd event
#: name is a row that exists, looks fine, and is invisible to every query.
VERDICT_EVENT = "feedback.verdict"
COMMENT_EVENT = "feedback.comment"


class Verdict(StrEnum):
    """What a reader thought. Stored as a word, not as 0 and 1.

    A query reading `verdict = 'down'` says what it means; one reading
    `verdict = 0` needs the widget's source to interpret, and `st.feedback`
    returns 0 for *down* -- the order a reader would guess wrong.
    """

    UP = "up"
    DOWN = "down"

    @classmethod
    def from_widget(cls, value: int | None) -> Verdict | None:
        """`st.feedback("thumbs")` returns 1 for up, 0 for down, None for neither.

        None is not only "not yet rated": clicking the selected thumb clears the
        widget, and the source returns None for that too. The caller must not
        treat it as a verdict.
        """
        if value is None:
            return None
        return cls.UP if value else cls.DOWN


@dataclass
class Rating:
    """What this reader has recorded about one question, in this session.

    Held outside widget state deliberately. Streamlit discards the state of a
    widget it did not render, and clearing a thumb un-renders the conditional
    comment box -- so a record kept in the widget's own key would vanish exactly
    when a reader changes their mind. This also makes "already recorded" a
    question with an answer, which is what stops a redraw counting twice.
    """

    verdict: Verdict
    commented: bool = False


def ratings(state: MutableMapping[str, Any]) -> dict[str, Rating]:
    """Ratings given in this session, by question. Created on first use.

    Takes the mapping rather than reaching for `st.session_state`, so this is
    testable without a browser and a test can hold two sessions at once.
    """
    if STATE_KEY not in state:
        state[STATE_KEY] = {}
    return state[STATE_KEY]


def rating_for(state: MutableMapping[str, Any], question_id: str) -> Rating | None:
    return ratings(state).get(question_id)


def _record(event: str, question_id: str, session_id: str, **fields: Any) -> None:
    """One record, through the trail's own logger.

    Not through a `TrailStore` reference, because the durable sink is already
    attached to that logger: going through it means feedback reaches both sinks,
    inherits the fail-open guarantee, and needs no new plumbing to fail safely.

    A `QuestionTrace` built directly rather than `start_question`, because the
    question already happened and already has an identifier. Minting a new one
    here would produce a rating that names a question nobody asked.
    """
    trace.QuestionTrace(
        question_id=question_id,
        session_id=session_id,
        run_label=env_setting("SCINUMBERS_RUN", "").strip() or "dev",
    ).record(event, **fields)


def record_verdict(
    state: MutableMapping[str, Any],
    *,
    question_id: str,
    session_id: str,
    verdict: Verdict,
) -> bool:
    """Record a rating. Returns whether it was written, `False` if already given.

    Refuses a second write for the same question, because the page is redrawn on
    every interaction and a redraw is not a new judgement. A reader who changes
    their mind is a case this deliberately does not serve yet: two contradicting
    rows would need a rule about which counts, and nobody has asked for one.
    """
    if question_id in ratings(state):
        return False
    ratings(state)[question_id] = Rating(verdict=verdict)
    _record(VERDICT_EVENT, question_id, session_id, verdict=str(verdict))
    return True


def record_comment(
    state: MutableMapping[str, Any],
    *,
    question_id: str,
    session_id: str,
    text: str,
) -> bool:
    """Record a comment. Returns whether it was written.

    Refuses a comment with no rating behind it: the rating is what a comment
    qualifies, and the interface never offers the box before one exists. Refuses
    empty text, and refuses a second comment for the same reason a second verdict
    is refused.

    The text is stored exactly as typed. It is never interpreted, never matched
    against anything, and above all never sent to the model -- see the module
    docstring and `answer-feedback`.
    """
    rating = ratings(state).get(question_id)
    if rating is None or rating.commented or not text.strip():
        return False
    rating.commented = True
    _record(COMMENT_EVENT, question_id, session_id, comment=text.strip())
    return True
