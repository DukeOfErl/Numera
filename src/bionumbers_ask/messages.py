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

from .citations import format_citation
from .config import format_usd
from .events import (
    CitationWarning,
    ConversationWarning,
    CostProjection,
    Event,
    QuestionEnded,
    Retrieval,
    SpendWarning,
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
    if isinstance(event, CitationWarning):
        parts = []
        if event.unknown:
            parts.append(f"not in the corpus: {', '.join(map(format_citation, event.unknown))}")
        if event.unretrieved:
            parts.append(
                "cited without being retrieved: "
                + ", ".join(map(format_citation, event.unretrieved))
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
        f"(run {format_usd(event.run_spend)})",
        event.model,
        f"{event.tool_calls} tool calls",
    ]
    line = " · ".join(parts[:1] + [" ".join(parts[1:3])] + parts[3:])
    if event.at_retrieval_bound:
        line += f" · {event.model_calls} of {event.call_limit} model calls"
    # Only where the question answered: an ending that already names the ceiling
    # as its reason does not need telling twice.
    if event.at_spend_ceiling and not event.incomplete:
        line += f" · at the {format_usd(event.spend_ceiling)} ceiling"
    return line
