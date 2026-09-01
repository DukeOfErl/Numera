"""BioNumbers' own notation, read where BioNumbers is the one writing.

The corpus's entry prose cites sibling entries in the source's notation -- "Range
for E. coli B. See BNID 102065, 104333" -- and it must keep saying so. The text is
the source's words, a displayed entry is an attribution, and a raw-entry view is
planned, so the notation is read here rather than normalised away when the corpus
is built.

**This is the one module in the package that knows BioNumbers exists.** Everything
else speaks of entries and identifiers. When a second source arrives it gets its
own module beside this one; nothing else has to move.

A single module and not a `sources/` package, deliberately:
`tests/test_driver_independence.py` builds the list it checks from
`PACKAGE.glob("*.py")`, so a subpackage would escape the dependency rule entirely
and an `import streamlit` in here would pass every test in that file.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# The marker is required. A bare six-digit number is indistinguishable from a
# six-digit quantity -- "100000 molecules per cell" is not a citation -- and the
# ambiguity only grows as the corpus does. The glue is permissive because the form
# is a preference rather than a control: this parser reads text nobody here wrote
# -- the source's prose, and a reader's own question, which is where the notation
# re-enters a session -- so a parser that rejected "BNID: 100002" would score a
# good answer as uncited, and a false negative is worse than the ambiguity it
# removes.
#
# One marker may introduce a run: "BNIDs 100002 and 100003" is how the corpus's own
# entry text writes several, and it is what a model listing entries writes without
# being asked. Read as a single citation, a well-cited answer scored as having none
# at all. Identifiers after the first are inferred from position rather than from a
# marker of their own, so each must look like the first -- the same number of digits
# -- and the run stops at the first thing that does not. That is what keeps
# "BNID 100002 and 3 other entries" from reading 3 as an identifier, without
# hardcoding how wide an identifier is.
#
# A floor on width, not a width. Some entry text writes an identifier with an
# internal space -- "BNID 104 678" -- and without a floor the leading "104" reads
# as an identifier, turning a citation this parser used to miss into a wrong one it
# confidently reports. Three digits is not an identifier in any scheme worth
# building, and a floor leaves room for a corpus whose identifiers are wider than
# this one's six digits.
MIN_DIGITS = 4
PATTERN = re.compile(r"(?i)\bbnids?[\s:#\-=]*(\d+)((?:\s*(?:,|and|&)\s*\d+)*)")
_RUN = re.compile(r"\d+")


def label(entry_id: int) -> str:
    """How an entry from this source is named to a person.

    Deliberately not the citation form. A reader is looking at BioNumbers entries,
    and their identifiers are BNIDs -- saying so is the attribution that makes a
    number traceable back to the database it came from, and it is what a raw-entry
    view would show. The form the model is asked to write (`citations.FORM`) is a
    different thing with a different job: it exists to be parsed unambiguously out
    of prose, and it says nothing about which database an entry came from.

    They were one function once, and the machine notation leaked into the table the
    moment the model's form changed.
    """
    return f"BNID {entry_id}"


def occurrences(text: str) -> tuple[tuple[int, int], ...]:
    """Every identifier in BioNumbers' notation, as (position, identifier).

    Positions are carried because a caller merging these with citations written in
    another notation has to order them the way a reader meets them, and neither
    notation's matches alone say where they sit relative to the other's.
    """
    out: list[tuple[int, int]] = []
    for match in PATTERN.finditer(text or ""):
        first = match.group(1)
        if len(first) < MIN_DIGITS:
            continue
        # Only the relative order of these positions is ever read, so the exact group
        # they are measured from does not matter -- a mutant using group 2's start
        # survives, correctly, because the sequence stays monotonic either way.
        out.append((match.start(1), int(first)))
        tail = match.group(2) or ""
        base = match.start(2)
        for run in _RUN.finditer(tail):
            if len(run.group(0)) != len(first):
                break
            out.append((base + run.start(), int(run.group(0))))
    return tuple(out)


def cross_references(text: str) -> tuple[int, ...]:
    """Identifiers written in BioNumbers' notation, in order, without repeats.

    Order is kept because it is the order a reader meets them in, which is the
    order the entries table shows them in.
    """
    seen: dict[int, None] = {}
    for _, entry_id in occurrences(text):
        seen.setdefault(entry_id, None)
    return tuple(seen)


def rewrite(text: str, format_id: Callable[[int], str]) -> str:
    """The source's cross-references, restated in the caller's notation.

    For handing an entry to the model, which is asked to write one notation and
    should not be shown another in the same breath -- an entry's prose saying "See
    BNID 102065" is the likeliest reason for a model to answer in a form the
    answer parser was not told to expect.

    A rendering, never a repair: the corpus keeps the source's words, and so does
    everything shown to a person. Only the copy handed to the model is restated.

    What is not an identifier is left exactly as the source wrote it. "BNID 104 678"
    fails the width floor, so it passes through untouched rather than being
    half-converted into a citation the source never made.
    """

    def one(match: re.Match[str]) -> str:
        first = match.group(1)
        if len(first) < MIN_DIGITS:
            return match.group(0)
        out = [format_id(int(first))]
        tail = match.group(2) or ""
        # 0 rather than None only for readability: `tail[None:n]` is `tail[0:n]`, so a
        # mutant setting None here survives and is equivalent.
        pos = 0
        for run in _RUN.finditer(tail):
            if len(run.group(0)) != len(first):
                break
            out.append(tail[pos : run.start()])
            out.append(format_id(int(run.group(0))))
            pos = run.end()
        out.append(tail[pos:])
        return "".join(out)

    return PATTERN.sub(one, text or "")
