"""Is a quote the model produced literally present in the paper?

Ported from `probes/2026-09-09-retrieval/check_quote.py` rather than rewritten (design D4): every
"verified verbatim" claim in ADR-0040 came out of that file, so a rewrite would quietly restate the
one instrument the rest of the prototype leans on. What changed in the port is the shape, not the
rule -- a function over passages instead of a command over an XML file -- plus one fold entry, and
the README's canary is now `tests/test_bionumbers_quotes.py` instead of a table someone read once.

Normalisation is deliberately minimal and one-directional: NFKC, the fold table below, the removal
of the JATS reader's citation tokens, and whitespace collapse. Anything beyond that starts excusing
paraphrase, which is the thing being checked. The check fails towards refusal on purpose: a quote
wrongly refused costs the one bounded retry the pipeline already budgets for, while a quote wrongly
passed reaches a reviewer looking exactly like a verified one.

No tag stripping, unlike the probe: passages arrive from the JATS reader already flattened, so a
stripper on the quote side would only widen the check with nothing on the other side to match.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# Written as code points rather than literal characters: this table is the whole looseness budget
# of the check, and a character that is mangled in transit (through a message, a clipboard, an
# editor's normalisation) silently widens or narrows it with nothing to show. The probe wrote them
# as \u escapes; ruff's formatter rewrote those into the literal characters on 2026-09-18 and the
# ASCII canary below caught it, so they are integers now, which no formatter normalises. Five
# dashes, four quotes, four spaces, the multiplication sign and the minus sign, byte for byte as
# the probe had them.
FOLD = {
    chr(0x2010): "-",  # HYPHEN
    chr(0x2011): "-",  # NON-BREAKING HYPHEN
    chr(0x2012): "-",  # FIGURE DASH
    chr(0x2013): "-",  # EN DASH
    chr(0x2014): "-",  # EM DASH
    chr(0x2018): "'",  # LEFT SINGLE QUOTATION MARK
    chr(0x2019): "'",  # RIGHT SINGLE QUOTATION MARK
    chr(0x201C): '"',  # LEFT DOUBLE QUOTATION MARK
    chr(0x201D): '"',  # RIGHT DOUBLE QUOTATION MARK
    chr(0x00A0): " ",  # NO-BREAK SPACE
    chr(0x2007): " ",  # FIGURE SPACE
    chr(0x2009): " ",  # THIN SPACE
    chr(0x202F): " ",  # NARROW NO-BREAK SPACE
    chr(0x00D7): "x",  # MULTIPLICATION SIGN
    chr(0x2212): "-",  # MINUS SIGN
    # The one addition, and the paper that forced it: PMC13248727 (inspected 2026-09-18) writes the
    # same unit with both U+00B5 and U+03BC, in prose and in its table headers. NFKC already maps
    # MICRO SIGN to GREEK SMALL LETTER MU, so this entry changes no result today; it is here because
    # the table -- not the Unicode standard -- is where this project states its looseness budget,
    # and a fold that only exists inside NFKC cannot be read off the budget.
    chr(0x00B5): chr(0x03BC),  # MICRO SIGN -> GREEK SMALL LETTER MU
}

# The JATS reader keeps bibliographic markers as tokens in passage text (design D2), because their
# presence beside a number is what separates a measured value from a cited one. They are rendering,
# not the paper's words, so a model may quote a span with them or without them and both are the same
# quote. Dropping them from both sides is the only tolerance here that is about our own output.
#
# Removed rather than replaced by a space: the marker usually sits inside the paper's own
# punctuation -- "the replisome ([ref 31])" -- and a space would leave "( )", which no model
# dropping the token would write, so the tolerance would only work in one direction.
_CITATION_TOKEN = re.compile(r"\[ref [^\]]+\]")
_WHITESPACE = re.compile(r"\s+")


class PassageLike(Protocol):
    """One container of the paper: the unit a location names, and the unit a quote must fit in."""

    id: str
    text: str


class HasPassages(Protocol):
    """What this module needs of a JATS document. Structural rather than an import of
    `bionumbers.jats`, so the checker can be exercised against a handful of strings -- and so the
    canary does not depend on the reader it is meant to be independent of."""

    passages: Sequence[PassageLike]

    def text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Verified:
    passage_id: str
    """Where the quote was found, which is what the claim's location records."""

    in_named_passage: bool
    """False means the quote is verbatim in the paper but not in the passage the model named: a
    location error, reported rather than excused (design D3). True when nothing was named, because
    a caller that named no passage cannot be told its passage was wrong."""


@dataclass(frozen=True, slots=True)
class Failed:
    reason: str
    """Named for the model: the one bounded retry is only useful if it says where the quote
    diverged from the paper."""

    longest_prefix: int
    """In folded characters, not in the characters the model sent."""


def fold(text: str) -> str:
    """The comparison form both sides are reduced to. Order matters: NFKC first (it settles
    superscripts, ligatures and the compatibility spaces), then the explicit table, then the
    citation tokens, then whitespace -- folding a NO-BREAK SPACE to a space before the collapse is
    what makes the collapse see it."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(FOLD.get(character, character) for character in text)
    text = _CITATION_TOKEN.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def contains(haystack: str, needle: str) -> bool:
    """Is `needle` a substring of `haystack` once both are folded?

    An empty needle is not contained in anything. The substring test would say yes, and a model
    that returned no quote at all would have every claim verified -- the one input that must be
    refused loudest.
    """
    wanted = fold(needle)
    if not wanted:
        return False
    return wanted in fold(haystack)


def verify(quote: str, document: HasPassages, passage_id: str | None = None) -> Verified | Failed:
    """Check one quote against the paper, and say where it was found or where it diverged.

    The named passage is tried first and the whole document second, so a right quote with a wrong
    id comes back `Verified` with `in_named_passage` false rather than silently correct or wrongly
    refused. A quote spanning two passages fails: the claim's location has to name one container,
    and a span that fits none has no location to record.
    """
    wanted = fold(quote)
    if not wanted:
        return Failed(reason="empty quote", longest_prefix=0)

    if passage_id is not None:
        for passage in document.passages:
            if passage.id == passage_id and wanted in fold(passage.text):
                return Verified(passage_id=passage_id, in_named_passage=True)

    for passage in document.passages:
        if wanted in fold(passage.text):
            return Verified(passage_id=passage.id, in_named_passage=passage_id is None)

    # The probe's diagnostic, over the whole paper rather than a passage: where a quote diverges is
    # usually outside the passage it was meant to come from, and the retry has to be told the
    # divergence point rather than "not found".
    haystack = fold(document.text())
    low, high = 0, len(wanted)
    while low < high:
        middle = (low + high + 1) // 2
        if wanted[:middle] in haystack:
            low = middle
        else:
            high = middle - 1
    snippet = wanted[max(0, low - 40) : low + 60]
    return Failed(
        reason=(
            f"not verbatim: longest matching prefix {low}/{len(wanted)} chars, "
            f"diverges at ...{snippet}..."
        ),
        longest_prefix=low,
    )
