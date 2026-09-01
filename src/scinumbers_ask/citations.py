"""How an entry identifier is written in an answer, and how it is read back.

One module, so the prompt that asks for a form, the drivers that display it and
the evaluation harness that scores it cannot drift apart. A scorer that parsed
citations differently from the way the model was asked to write them would report
a wrong figure with no error anywhere.

The *source's* notation is not read here. BioNumbers writes its own
cross-references in its own form, and that lives in `bionumbers.py` -- one
implementation, called from here rather than restated, because two independent
readings of one notation is exactly the defect this module was written after.
"""

from __future__ import annotations

from .bionumbers import cross_references

# What the model is told to write, and what a driver writes when it renders one.
FORM = "BNID 100002"


def format_citation(bnid: int) -> str:
    return f"BNID {bnid}"


def citations(text: str) -> tuple[int, ...]:
    """Identifiers cited in a piece of text, in order, without repeats.

    Order is kept because it is the order a reader meets them in, which is the
    order the entries table shows them in.
    """
    return cross_references(text)
