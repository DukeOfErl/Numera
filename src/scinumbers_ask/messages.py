"""What a warning says, in words, shared by the drivers.

Every driver renders the same events, and a warning is the one kind whose wording
is a claim rather than a layout: "cited without being retrieved" means something,
and two drivers that phrase it differently are two different statements about the
same fact. The terminal prefixes these with a marker and the web page puts them in
a coloured box; neither owns the sentence.

Deliberately not on the events themselves. `events.py` is the port -- what the
agent knows -- and how a fact is put to a person is not something the agent should
carry. Deliberately not in `cli.py` either, which is one adapter among several.
"""

from __future__ import annotations

from . import bionumbers
from .config import format_usd
from .events import (
    CitationWarning,
    ConversationWarning,
    CostProjection,
    EndReason,
    Event,
    QuestionEnded,
    Retrieval,
    SpendWarning,
    UngroundedRefusal,
)

# What is kept, in the reader's own view rather than in a policy nobody opens.
#
# The requirement is that a reader can learn it *from the interface*: the system
# stores the words somebody typed, and a person discovering that by reading the
# database afterwards has been told nothing. Shared by the drivers for the reason
# every other sentence here is -- two interfaces making different claims about
# what is kept are two different claims.
#
# Deliberately not folded into `web.PROTOTYPE_NOTE`: that banner is one line by
# design, and a banner that wraps becomes a block a reader learns to skip.
#
# Says why, not only what. "Questions are logged" reads as surveillance; the
# reason is that a rating on an answer nobody can read is worth nothing, which is
# the whole of what this records.
RECORDS_NOTE = (
    "Questions, answers and the entries behind them are kept, so whoever runs "
    "this can see where it goes wrong."
)

# Endings after which asking again cannot produce a different answer. What these
# share is that they are not about the question just asked: a spent run budget
# stays spent, and a conversation over its token bound only grows. The per-question
# ceiling is deliberately absent -- that one refreshes.
#
# Shared because it is a fact about the ending rather than a rendering of it. The
# terminal quit on these and the web went on accepting questions, replaying the
# same refusal indefinitely; two drivers disagreeing about whether the door is shut
# is the divergence `messages` exists to prevent.
#
# A provider out of credit is here for the same reason, and is the only member a
# reader cannot fix themselves: the key funding the run has no balance, so every
# further question fails identically until somebody tops it up. PROVIDER_FAILURE
# stays out -- a gateway that failed once may well answer the next call.
STOP_THE_RUN = frozenset(
    {
        EndReason.RUN_BUDGET,
        EndReason.CONVERSATION_BOUND,
        EndReason.NOT_CONFIGURED,
        EndReason.PROVIDER_LIMIT,
    }
)


# What to do about a shut door, where "start a new session" is the wrong answer.
#
# Each driver has its own generic line for a run that is over, and for a spent run
# budget or a full conversation that line is right: a fresh session does refresh
# both. A key with no credit is different in kind -- the next session's first
# question meets the same refusal -- so the generic advice sends the reader round a
# loop, and it is the last thing on screen, under an answer that has just told them
# the opposite.
#
# Shared for the reason the rest of this module is: the terminal and the page are
# answering one question, "may I ask again, and if not what would help", and two
# drivers phrasing that differently are two claims about one fact.
# Each sentence has to read correctly to *both* readers this project has: someone
# using a hosted instance, and the developer running the same code on their own key.
# "Ask whoever deployed the app" was the first wording and told the second reader to
# contact themselves -- the exact absurdity that moving the sentence out of the agent
# was supposed to avoid. Naming the remedy without addressing anyone works for both.
RUN_OVER_ADVICE: dict[EndReason, str] = {
    EndReason.PROVIDER_LIMIT: (
        "The key that pays for this app's model calls has reached its usage limit, so a "
        "new session will not help — the limit has to be raised by whoever funds it."
    ),
    # Here for the same reason, and it was wrong before this change too: a missing
    # credential or a spend that cannot be accounted for meets the reader again on
    # the first question of any new session. The ending's own answer carries the
    # specifics -- which variable, what to set -- so this only has to stop the page
    # advising something that cannot work.
    EndReason.NOT_CONFIGURED: (
        "A new session will not help: this run stopped because something the app needs "
        "is not configured, and that has to be fixed where the app runs."
    ),
}


def run_over_advice(reason: EndReason) -> str | None:
    """What a driver should say about this ending, beyond its own generic line.

    `None` for every ending with no advice of its own, which is most of them: a
    driver falls back to its own wording rather than being handed a sentence for a
    case where its existing one is already correct.
    """
    return RUN_OVER_ADVICE.get(reason)


def warning_text(event: Event) -> str | None:
    """The sentence for a warning event, or None if the event is not one."""
    if isinstance(event, ConversationWarning):
        return (
            f"this session holds {event.tokens:,} of {event.bound:,} tokens; "
            "it will stop taking questions at the bound"
        )
    if isinstance(event, SpendWarning):
        return (
            f"spent {format_usd(event.spent)}, past the "
            f"{format_usd(event.threshold)} warning threshold"
        )
    if isinstance(event, CostProjection):
        return (
            f"this question could cost up to {format_usd(event.projected)}, "
            f"above the {format_usd(event.threshold)} threshold (an estimate)"
        )
    if isinstance(event, UngroundedRefusal):
        if event.claimed_searching:
            return (
                "this answer describes searching that did not happen: no retrieval "
                "was made, so it says nothing about what the corpus holds"
            )
        return (
            "nothing was retrieved for this question, so this answer is not grounded "
            "in the corpus -- it says only what the model expected to find"
        )
    if isinstance(event, CitationWarning):
        parts = []
        if event.unknown:
            parts.append(f"not in the corpus: {', '.join(map(bionumbers.label, event.unknown))}")
        if event.unretrieved:
            parts.append(
                "cited without being retrieved: "
                + ", ".join(map(bionumbers.label, event.unretrieved))
            )
        return "; ".join(parts)
    return None


# Carried for the entries table and the citation check, not for a person to read:
# fifty identifiers on a progress line would bury what the search was for.
UNRENDERED_DETAIL = {"entry_ids"}


def retrieval_text(event: Retrieval) -> str:
    """What a retrieval was, in words: the tool and what it was asked."""
    detail = " ".join(
        f"{k}={v!r}"
        for k, v in event.detail.items()
        if v is not None and k not in UNRENDERED_DETAIL
    )
    return f"{event.tool} {detail}".rstrip()


def _run_clause(event: QuestionEnded) -> str:
    """Run spend, against the run's cap where the ending carries one.

    The cap is shown on every ending rather than only when it is reached, because
    unlike the per-question ceiling it is not refreshed by asking again: spend
    accumulates until the run stops taking questions at all. A reader watching a
    number climb needs to know what it is climbing towards, and the moment it is
    worth knowing is before the run ends, not at it.
    """
    if not event.run_budget:
        return f"(run {format_usd(event.run_spend)})"
    return f"(run {format_usd(event.run_spend)} of {format_usd(event.run_budget)})"


def ending_text(event: QuestionEnded) -> str:
    """Why a question ended, what it consumed, and against which limits.

    Shared because it is a report, not a layout: the terminal prefixes it with a
    dash and the page draws it as a caption, and a driver that quietly left a
    clause out would be under-reporting rather than restyling. The web driver had
    already dropped the retrieval-bound clause that way.

    Both bound clauses appear only where the bound was reached. Printed on every
    answer they would put a number nobody needs beside the ones they do; printed
    where there was no room left for another call, each says something a reader
    cannot otherwise see.
    """
    mark = " (incomplete)" if event.incomplete else ""
    parts = [
        f"{event.reason.value}{mark}",
        format_usd(event.spend),
        _run_clause(event),
        event.model,
        f"{event.tool_calls} tool calls",
    ]
    line = " · ".join(parts[:1] + [" ".join(parts[1:3])] + parts[3:])
    if event.at_retrieval_bound:
        line += f" · {event.model_calls} of {event.call_limit} model calls"
    if event.at_tool_bound:
        line += f" · {event.tool_calls} of {event.tool_call_limit} retrievals"
    # Only where the question answered: an ending that already names the ceiling
    # as its reason does not need telling twice.
    if event.at_spend_ceiling and not event.incomplete:
        line += f" · at the {format_usd(event.spend_ceiling)} ceiling"
    return line
