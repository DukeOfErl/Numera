"""A harvested paper's reference in Chicago author-date, read from its CSL-JSON (ADR-1640).

**Presentation, not core.** The model is told to cite entries and name no paper, so it is never
handed the formatted reference with its authors; the drivers draw it in the Reference column and
the full entry. Formatted by citeproc-py -- a CSL processor, the library's own -- with the CSL
project's own `chicago-author-date` style, rather than by a hand-written formatter.

Two departures from the style, both deliberate. Titles stay as the paper wrote them: the style
title-cases them, which rewrites biology's notation (`cdc15` to `Cdc15`, `S. pombe` to `S. Pombe`).
And a period after a quoted title moves inside the quote, which Chicago requires and
citeproc-py 0.11.1 does not yet do (`punctuation-in-quote`).

Where the record cannot be formatted faithfully -- no record, no type, no author, a
collaboration's name (which citeproc-py 0.11.1 does not support), a date that is not integers,
or a record citeproc raises on -- the caller keeps the entry's plain reference. That is
the cheap direction: a plainer reference is still the right paper.
"""

from __future__ import annotations

import json
from functools import lru_cache

from citeproc import (
    Citation,
    CitationItem,
    CitationStylesBibliography,
    CitationStylesStyle,
    formatter,
)
from citeproc.source.json import CiteProcJSON
from citeproc_styles import get_style_filepath

STYLE = "chicago-author-date"


@lru_cache(maxsize=1)
def _style() -> CitationStylesStyle:
    style = CitationStylesStyle(get_style_filepath(STYLE), validate=False)
    for element in style.xml.iter():
        if element.get("text-case") == "title":
            del element.attrib["text-case"]
    return style


def chicago(csl_json: str) -> str | None:
    """The reference, or None where the record cannot be formatted faithfully."""
    try:
        item = json.loads(csl_json) if csl_json else None
    except ValueError:
        return None
    if not isinstance(item, dict) or not item.get("id") or not item.get("type"):
        return None
    authors = item.get("author") or []
    if not authors or any(not isinstance(a, dict) or "family" not in a for a in authors):
        return None
    # A year citeproc can read: date-parts of integers. Strings or only `raw` came out as
    # "Edition." where the year belongs -- a wrong reference where the plain one was right.
    parts = (item.get("issued") or {}).get("date-parts") or [[]]
    if not parts[0] or not all(isinstance(n, int) for n in parts[0]):
        return None
    try:
        bibliography = CitationStylesBibliography(_style(), CiteProcJSON([item]), formatter.plain)
        bibliography.register(Citation([CitationItem(item["id"])]))
        drawn = str(bibliography.bibliography()[0])
    except Exception:  # citeproc-py raises on records it does not expect; the plain one stands
        return None
    return drawn.replace("”.", ".”")
