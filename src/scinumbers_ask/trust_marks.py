"""A trust tier as a reader sees it: stars, a simulated mark and a dispute mark (design D6).

**Presentation, not core.** Shared by both drivers, like `entries_table`; the agent never imports
it, so the model is never shown a star and cannot learn to write one (ADR-1630). The model is told
a tier in words by `tools.trust_text`; this module draws the same tier for a person.

Reads a tier by its name (`corpus.TRUST_LEVEL`), so neither driver imports `bionumbers`
(ADR-1600). An entry with no tier -- one from a corpus file -- draws as nothing at all: not zero
stars, which would say that someone looked and no one approved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .citations import DELIMITED, citations
from .corpus import TRUST_LEVEL, TRUST_ROLE

FULL = "★"
EMPTY = "☆"
#: After the stars: the review that set this tier was a model standing in for a person (ADR-0960).
#: `sim`, not `#`: papers label their rings and samples "#1–#4", and a `#` beside a citation of one
#: read as part of it (add-answer-view-redesign, ADR-1850).
SIMULATED = "sim"
#: After the stars: some reviewer objected to this entry, whoever approved it (ADR-0990).
#: The emoji form (U+26A0 U+FE0F), which browsers and the table draw in yellow; the bare U+26A0
#: draws in the text colour, where a warning does not stand out (the user's call, 2026-10-16).
DISPUTED = "\u26a0\ufe0f"

SCALE_LEGEND = (
    f"{FULL * 5} curated · {FULL * 4}{EMPTY} senior scientist · {FULL * 3}{EMPTY * 2} scientist · "
    f"{FULL * 2}{EMPTY * 3} student · {FULL}{EMPTY * 4} AI reviewer · "
    f"{EMPTY * 5} no reviewer approved it, or not yet reviewed"
)
SIMULATED_LEGEND = f"{SIMULATED}: set by a simulated review, a model standing in for the reviewer"
#: The page opens an entry beside the table, and the objections are there (ADR-1850).
DISPUTED_LEGEND = f"{DISPUTED} : a reviewer objected to this entry. Open the entry to read why"
#: The terminal cannot open a cell, so its objections are listed under the table instead.
DISPUTED_LEGEND_TERMINAL = (
    f"{DISPUTED} : a reviewer objected to this entry; the objections are listed above"
)


def stars(trust: Any) -> str:
    """`★★★☆☆ sim ⚠️` for a tier, or "" where an entry has none."""
    if trust is None:
        return ""
    level = TRUST_LEVEL[str(trust.tier)]
    drawn = FULL * level + EMPTY * (5 - level)
    marks = [SIMULATED] * bool(trust.simulated) + [DISPUTED] * bool(trust.disputed)
    return " ".join([drawn, *marks])


def tier_words(trust: Any) -> str:
    """Who stands behind a tier, for a reader who opened the entry; "" where there is none."""
    if trust is None:
        return ""
    tier = str(trust.tier)
    if tier == "CURATED":
        said = "Curated in BioNumbers"
    elif tier == "NONE":
        said = "Not yet approved by any reviewer"
    else:
        said = f"Approved by {_article(TRUST_ROLE[tier])} {TRUST_ROLE[tier]}"
    if trust.simulated:
        said += " (simulated review)"
    if trust.disputed:
        said += "; a reviewer objected"
    return said


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def legend(trusts: Iterable[Any], *, terminal: bool = False) -> list[str]:
    """What the stars and marks mean, for the tiers actually shown; empty where none is.

    `terminal` words the dispute line for a driver that lists objections under its table rather
    than opening a cell on a double click.
    """
    shown = [t for t in trusts if t is not None]
    if not shown:
        return []
    lines = [SCALE_LEGEND]
    if any(t.simulated for t in shown):
        lines.append(SIMULATED_LEGEND)
    if any(t.disputed for t in shown):
        lines.append(DISPUTED_LEGEND_TERMINAL if terminal else DISPUTED_LEGEND)
    return lines


def trust_lookup(repo: Any):
    """An identifier's tier from a repository, or None where it has none or names no entry."""

    def trust_of(entry_id: Any) -> Any:
        found = repo.get(entry_id) if repo is not None else None
        return found.entry.trust if found is not None else None

    return trust_of


def cited_stars(text: str, trust_of: Any) -> tuple[tuple[str, str], ...]:
    """(identifier, stars) for each entry an answer cites that has a tier, in the order cited.

    `trust_of` maps an identifier to a tier or None. Computed once, where the answer is turned into
    something to draw, so a redrawn transcript needs no repository.
    """
    out = []
    for entry_id in citations(text):
        drawn = stars(trust_of(entry_id))
        if drawn:
            out.append((str(entry_id), drawn))
    return tuple(out)


def annotate(text: str, drawn: Mapping[str, str]) -> str:
    """The answer with each citation followed by its stars, for a driver with no superscript.

    Only where it is displayed: the stored and recorded answer keeps the model's text exactly
    (ADR-1630). A group citing one entry gains its stars after it; a group citing several gains
    them in parentheses, each beside its identifier.
    """
    if not drawn:
        return text

    def one(match) -> str:
        ids = [str(i) for i in citations(match.group(0))]
        marked = [(i, drawn[i]) for i in ids if i in drawn]
        if not marked:
            return match.group(0)
        if len(ids) == 1:
            return f"{match.group(0)} {marked[0][1]}"
        return f"{match.group(0)} ({'; '.join(f'{i} {s}' for i, s in marked)})"

    return DELIMITED.sub(one, text)
