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
# Public because the answer sheet marks citations up for a reader, and a second
# copy of the pattern there would be a second definition of the citation form --
# which is the thing ADR-0410 exists to prevent.
DELIMITED = re.compile(r"\[\[([^\[\]]+)\]\]")


def format_citation(entry_id: int) -> str:
    """The form the model is asked to write, and the only form this file promises."""
    return f"[[{entry_id}]]"


# What the model is told to write. Produced by the formatter rather than restated,
# so the prompt cannot ask for a form the parser does not read.
FORM = format_citation(100002)


# A list separator, which must be followed by whitespace. That is what tells a list
# from a thousands separator: "100002, 100003" is two identifiers and "100,002" is
# one number written for a human, and no rule about an identifier's own shape can
# separate the two. Where it cannot tell, this file refuses and records rather than
# guessing -- see `_identifiers`.
_LIST = re.compile(r"\s*(?:,|;|&|\band\b)\s+")


def _identifiers(inner: str) -> tuple[int, ...] | None:
    """The identifiers inside one pair of delimiters, or None if it holds none.

    Plural, because a model listing entries writes `[[100002, 100003]]` without
    being asked -- the retired notation read exactly that shape on exactly that
    ground, and reading it as nothing scores a well-cited answer as uncited.

    Tolerant of a model that brackets the source's marker along with the number
    (`[[BNID 100002]]`), which is a plausible hedge from one shown that form in an
    entry's prose. That case is handed to `bionumbers.py` rather than guessed at
    here: it already knows how to read a run in that notation, and it is the only
    place that should.

    **Which direction absorbs the uncertainty, and why.** A group holding one run of
    digits is accepted whatever its width -- `[[2]]` becomes a citation of entry 2.
    That is deliberate: this file promises no rule about an identifier's shape, so a
    corpus with short identifiers must work, and a footnote written `[[2]]` is
    reported honestly as an identifier the corpus does not hold rather than silently
    dropped. The opposite choice -- a width floor -- would discard real citations
    from any corpus numbering below it, and that failure is invisible.

    A group it cannot read is refused, not resolved: several digit runs with no
    separator, or no digits at all. `[[Table 1]]` is not a citation attempt, and
    reading the 1 out of it would invent one.
    """
    text = inner.strip()
    if text.isdigit():
        return (int(text),)
    parts = [part.strip() for part in _LIST.split(text)]
    # `> 1` cannot fail here -- a single all-digit part would have returned above --
    # but it states what a list is, and a reader should not have to prove that.
    if len(parts) > 1 and all(part.isdigit() for part in parts):
        return tuple(int(part) for part in parts)
    # Not redundant with the tolerance in `citations`, though it looks it: that union
    # would find this identifier anyway. What this prevents is the group being
    # *recorded as unparsable* while its identifier is counted -- a trace line saying
    # a citation could not be read, next to the citation.
    marked = cross_references(text)
    return marked or None


def citations(text: str, *, trace: QuestionTrace | None = None) -> tuple[int, ...]:
    """Identifiers cited in a piece of text, in order, without repeats.

    Order is kept because it is the order a reader meets them in, which is the
    order the entries table shows them in. The two notations are merged by
    position rather than one appended to the other: concatenating them would put
    a citation the reader met first after every citation written the other way.
    """
    text = text or ""
    found: list[tuple[int, int]] = []
    for match in DELIMITED.finditer(text):
        group = _identifiers(match.group(1))
        if group is None:
            # Recorded, not dropped in silence. A bracket group that holds no
            # identifier is the model trying to cite and failing, which is worth
            # knowing about and is invisible otherwise -- the answer simply reads
            # as uncited, indistinguishable from one that never tried.
            if trace is not None:
                trace.record("citations.unparsable", inside=match.group(1)[:80])
            continue
        # Offset within the group, so several identifiers in one pair of brackets keep
        # their written order among the citations around them.
        found.extend((match.start() + offset, entry_id) for offset, entry_id in enumerate(group))
    found.extend(occurrences(text))
    seen: dict[int, None] = {}
    # Plain tuple order: position first, and the identifier only where two share a
    # position, which cannot happen. An explicit key here was equivalent, and
    # mutation testing could not tell the two apart -- which is the finding.
    for _, entry_id in sorted(found):
        seen.setdefault(entry_id, None)
    return tuple(seen)
