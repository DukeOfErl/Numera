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
import re
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


def short(csl_json: str) -> str:
    """First author and year from the record -- "Kamasaki 2007", "Wu & Pollard 2005", "Dhar et al.
    2026" -- for the table's grey line (ADR-1850); "" where the record does not give both."""
    try:
        item = json.loads(csl_json) if csl_json else None
    except ValueError:
        return ""
    if not isinstance(item, dict):
        return ""
    names = [
        a.get("family") or a.get("literal") or ""
        for a in item.get("author") or []
        if isinstance(a, dict)
    ]
    parts = (item.get("issued") or {}).get("date-parts") or [[]]
    year = parts[0][0] if parts and parts[0] and isinstance(parts[0][0], int) else None
    return _short(names, year)


#: One author as BioNumbers writes it: a surname, then up to four initials -- "Wu JQ",
#: "Van der Merwe AB", "O'Neil J". Anything else is not trusted to be a name.
_BN_AUTHOR = re.compile(
    r"^(?P<surname>(?:(?:von|van|de|der|den|di|da|du|le|la) )*[A-Z][\w'’-]*"
    r"(?: [A-Za-z][\w'’-]*)*) [A-Z]{1,4}(?: (?:Jr|Sr|II|III))?$"
)
_BN_ET_AL = re.compile(r"^et al\.?$", re.I)
#: "Goffeau A et al." -- the last author written with "et al." inside the same comma-piece.
_BN_TRAILING_ET_AL = re.compile(r"\s+et al\.?$", re.I)
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


def short_from_bionumbers(reference: str) -> str:
    """First author and year from a BioNumbers reference string, or "" where it cannot be told.

    BioNumbers writes "Wu JQ, Pollard TD. Counting cytokinesis proteins ... Science. 2005 Oct 14
    ...". The authors are what comes before the first ". ", and each must read as a surname --
    "von der Haar" and "Giddings ... Jr" included -- and initials, or end in "et al."; the year is
    the first four-digit year after them. **The cheap direction is giving
    none**: a missing short form costs one grey word beside the organism, a wrong year mis-dates a
    paper while looking right (ADR-1850, measured over the store's 423 curated references).
    """
    head, sep, rest = reference.partition(". ")
    if not sep or not rest:
        return ""
    surnames: list[str] = []
    et_al = False
    for author in (a.strip() for a in head.split(",")):
        if _BN_ET_AL.match(author):
            et_al = True
            continue
        if _BN_TRAILING_ET_AL.search(author):
            et_al = True
            author = _BN_TRAILING_ET_AL.sub("", author)
        found = _BN_AUTHOR.match(author)
        if not found:
            return ""
        surnames.append(found["surname"])
    year = _YEAR.search(rest)
    if not surnames or not year:
        return ""
    return _short(surnames + (["et al."] * 2 if et_al else []), int(year.group(1)))


def _short(names: list[str], year: int | None) -> str:
    names = [n for n in names if n]
    if not names or year is None:
        return ""
    if len(names) == 1:
        return f"{names[0]} {year}"
    if len(names) == 2:
        return f"{names[0]} & {names[1]} {year}"
    return f"{names[0]} et al. {year}"
