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


def cross_references(text: str) -> tuple[int, ...]:
    """Identifiers written in BioNumbers' notation, in order, without repeats.

    Order is kept because it is the order a reader meets them in, which is the
    order the entries table shows them in.
    """
    seen: dict[int, None] = {}
    for match in PATTERN.finditer(text or ""):
        first = match.group(1)
        if len(first) < MIN_DIGITS:
            continue
        seen.setdefault(int(first), None)
        for following in _RUN.findall(match.group(2) or ""):
            if len(following) != len(first):
                break
            seen.setdefault(int(following), None)
    return tuple(seen)
