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

# Endings after which asking again cannot produce a different answer. What these
# share is that they are not about the question just asked: a spent run budget
# stays spent, and a conversation over its token bound only grows. The per-question
# ceiling is deliberately absent -- that one refreshes.
#
# Shared because it is a fact about the ending rather than a rendering of it. The
# terminal quit on these and the web went on accepting questions, replaying the
# same refusal indefinitely; two drivers disagreeing about whether the door is shut
# is the divergence `messages` exists to prevent.
STOP_THE_RUN = frozenset(
    {EndReason.RUN_BUDGET, EndReason.CONVERSATION_BOUND, EndReason.NOT_CONFIGURED}
)


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
UNRENDERED_DETAIL = {"bnids"}


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
