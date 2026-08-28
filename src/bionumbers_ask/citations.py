"""How an entry identifier is written in an answer, and how it is read back.

One module, so the prompt that asks for a form, the drivers that display it and
the evaluation harness that scores it cannot drift apart. A scorer that parsed
citations differently from the way the model was asked to write them would report
a wrong figure with no error anywhere.
"""

from __future__ import annotations

import re

# The marker is required. A bare six-digit number is indistinguishable from a
# six-digit quantity -- "100000 molecules per cell" is not a citation -- and the
# ambiguity only grows as the corpus does. The glue is permissive because the form
# is asked of the model, which makes it a preference rather than a control: a
# parser that rejected "BNID: 100002" would score a good answer as uncited, and a
# false negative in evaluation is worse than the ambiguity it removes.
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

# What the model is told to write, and what a driver writes when it renders one.
FORM = "BNID 100002"


def format_citation(bnid: int) -> str:
    return f"BNID {bnid}"


def citations(text: str) -> tuple[int, ...]:
    """Identifiers cited in a piece of text, in order, without repeats.

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
