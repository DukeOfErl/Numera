"""How an entry identifier is written in an answer, and how it is read back.

One module, so the prompt that asks for a form, the drivers that display it and
the evaluation harness that scores it cannot drift apart. A scorer that parsed
citations differently from the way the model was asked to write them would report
a wrong figure with no error anywhere. The prompt interpolates `FORM` rather than
restating it, because it did restate it once and the two were free to diverge.

**Delimited, and therefore shape-free.** `[[100002]]` says where an identifier
ends, so nothing here has to infer it: no minimum width, no run heuristic, no rule
about how many digits an identifier has. Those existed to read a notation that
marks only where an identifier *begins*, and they are what an identifier's shape
was previously coupled to -- a corpus whose identifiers were not fixed-width
integers would have needed this file rewritten.

**The source's notation is still read, and deliberately.** BioNumbers writes its
own cross-references as `BNID 102065`, and a reader who knows the database types
that in their question. Sessions are checkpointed and follow-ups inherit the
conversation, so once that form is in the transcript the model will answer in it
for the rest of the session -- and a parser that accepted only the delimited form
would mark those well-cited answers unsupported. That is the false negative this
module was written to avoid, so both are accepted. `bionumbers.py` owns the
reading of the source's form; it is called from here, never restated.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .bionumbers import cross_references, occurrences

if TYPE_CHECKING:
    from .trace import QuestionTrace

__all__ = ["FORM", "citations", "cross_references", "format_citation"]

# The delimiters are the whole contract. Nothing about the identifier's shape is
# asserted here -- `[^\[\]]+` is "whatever is between them" -- so the only thing a
# corpus with wider, padded or non-numeric identifiers would change is the
# coercion in `_identifier`, not the pattern.
_DELIMITED = re.compile(r"\[\[([^\[\]]+)\]\]")
_DIGITS = re.compile(r"\d+")

def format_citation(entry_id: int) -> str:
    """The form the model is asked to write, and the only form this file promises."""
    return f"[[{entry_id}]]"


# What the model is told to write. Produced by the formatter rather than restated,
# so the prompt cannot ask for a form the parser does not read.
FORM = format_citation(100002)


def _identifier(inner: str) -> int | None:
    """The identifier inside a pair of delimiters, or None if it does not hold one.

    Tolerant of a model that brackets more than the number -- `[[BNID 100002]]` is
    a plausible hedge from a model that has been shown the source's form -- because
    the alternative is dropping a citation the reader can plainly see. Refuses only
    what is genuinely ambiguous: no digits at all, or several runs of them, where
    picking one would be a guess presented as a reading.
    """
    text = inner.strip()
    if text.isdigit():
        return int(text)
    digits = _DIGITS.findall(text)
    if len(digits) == 1:
        return int(digits[0])
    return None


def citations(text: str, *, trace: QuestionTrace | None = None) -> tuple[int, ...]:
    """Identifiers cited in a piece of text, in order, without repeats.

    Order is kept because it is the order a reader meets them in, which is the
    order the entries table shows them in. The two notations are merged by
    position rather than one appended to the other: concatenating them would put
    a citation the reader met first after every citation written the other way.
    """
    text = text or ""
    found: list[tuple[int, int]] = []
    for match in _DELIMITED.finditer(text):
        entry_id = _identifier(match.group(1))
        if entry_id is None:
            # Recorded, not dropped in silence. A bracket group that holds no
            # identifier is the model trying to cite and failing, which is worth
            # knowing about and is invisible otherwise -- the answer simply reads
            # as uncited, indistinguishable from one that never tried.
            if trace is not None:
                trace.record("citations.unparsable", inside=match.group(1)[:80])
            continue
        found.append((match.start(), entry_id))
    found.extend(occurrences(text))
    seen: dict[int, None] = {}
    for _, entry_id in sorted(found, key=lambda pair: pair[0]):
        seen.setdefault(entry_id, None)
    return tuple(seen)
