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
PATTERN = re.compile(r"(?i)\bbnid[\s:#\-=]*(\d+)\b")

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
        seen.setdefault(int(match.group(1)), None)
    return tuple(seen)
