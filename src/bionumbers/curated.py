"""BioNumbers' own entries as the curated tier, where nothing about them gives cause for doubt.

A harvested entry earns trust through review; a BioNumbers entry was entered by a curator from the
paper, which is a review already. So the demo shows the two side by side, the curated one at the
top of the trust order -- but only where the entry itself carries no sign that the curator's record
is unsure, broken or not a measurement. Which signs, and why each, is ADR-1510.

The two directions do not cost the same. An entry left out costs one row of a curated tier that has
hundreds; an entry let in that should not be is a wrong value shown with the highest trust there
is, next to harvested values a reviewer is asked to doubt. So every rule here refuses on the first
sign, and the cheap direction absorbs the uncertainty: a doubt word in an entry's prose drops it
even where the doubt is about something else.

The corpus is read as raw JSON lines rather than through `scinumbers_ask.corpus`, which this
package's core may not import (design D9). The keys read are the ingester's contract with that
module -- `range_fused`, `range_one_sided` and the rest are its flags, reported and never repaired
-- so the same fields mean the same things here; the one judgement copied rather than shared is the
implausible span, whose threshold is `scinumbers_ask.corpus.IMPLAUSIBLE_SPAN`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from enum import StrEnum
from pathlib import Path

from bionumbers.records import Frozen

#: Where an entry can be read by a person. The id is BioNumbers' BNID.
ENTRY_URL = "https://bionumbers.hms.harvard.edu/bionumber.aspx?id={entry_id}"

#: The demo's slice, as harvest's biology scope was read off it (2026-10-03): yeast by organism,
#: the cytoskeleton by property or keyword.
YEAST = re.compile(r"saccharomyces|yeast|pombe", re.I)
CYTOSKELETON = re.compile(
    r"microtubul|tubulin|\bactin|kinesin|dynein|myosin|cytoskelet|filament|spindle|cofilin|"
    r"formin|arp2/3|profilin|septin|kinetochore|flagell|cilia|cilium|axonem|treadmill",
    re.I,
)

#: A method that reads as a calculation, an estimate or a model rather than a measurement.
CALCULATED = re.compile(
    r"calculat|estimat|assum|derived from|model(l)?ed|simulat|theoretical|computed", re.I
)

#: Words in an entry's own prose that say its curator, or its source, was unsure of the value.
#: Narrow on purpose: "crude" and "probably" read as doubt and mostly were not ("crude extract"),
#: so they are not here; what is here fired on 2 of the 492 entries in the slice, both right.
DOUBT = re.compile(
    r"rule of thumb|\buncertain|\bunclear|not clear|questionabl|rough estimate|"
    r"order of magnitude|ballpark|\bguess|speculat|disput|controvers|inconsisten|discrepan",
    re.I,
)

#: The span beyond which two bounds cannot be one measurement; the ask package's threshold.
IMPLAUSIBLE_SPAN = 1_000_000

_NO_UNIT = {"", "n/a", "na", "none", "-", "?"}
#: Characters a unit may hold. Anything else is a character the export garbled -- BioNumbers'
#: multiplication sign arrives as a Cyrillic letter (`μM^-1хsec^-1`), which reads as a unit and
#: is not one.
_UNIT_CHARACTERS = {chr(code) for code in range(32, 127)} | set("μµÅ°×·")


class Refusal(StrEnum):
    """Why an entry is not in the curated tier. The first that applies is the one recorded."""

    OUT_OF_SCOPE = "outside the demo's slice"
    NO_VALUE = "no value and no two-sided range"
    NOT_MEASURED = "no method, or a method that reads as a calculation"
    NO_REFERENCE = "no PubMed reference"
    FUSED_RANGE = "bounds that may belong to two quantities"
    IMPLAUSIBLE_SPAN = "bounds too far apart to be one measurement"
    ONE_SIDED = "a bound, not a value"
    NO_UNIT = "no unit"
    GARBLED_UNIT = "a unit with a character the export garbled"
    DOUBT = "its own prose says the value is unsure, or a rule of thumb"


class CuratedEntry(Frozen):
    """One BioNumbers entry as the curated tier shows it."""

    entry_id: int
    property: str
    organism: str
    value: float | None
    range_low: float | None
    range_high: float | None
    units: str
    approximate: bool
    """The source hedged the value ("~60,000"). Kept, and shown: the hedge is the source's own."""
    reference: str
    pubmed_id: str
    method: str
    comments: str

    @property
    def url(self) -> str:
        return ENTRY_URL.format(entry_id=self.entry_id)


def _number(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)  # type: ignore[arg-type]


def _keywords(raw: dict) -> str:
    keywords = raw.get("keywords")
    return " ".join(keywords) if isinstance(keywords, list) else str(keywords or "")


def _text(raw: dict, *keys: str) -> str:
    return " ".join(str(raw.get(key) or "") for key in keys)


def refusal(raw: dict) -> Refusal | None:
    """The first reason this entry may not be curated, or None if there is none.

    The guard is here rather than in the loader or the command: a second caller -- the ask agent
    reading curated entries, a test, a re-load -- must not be able to admit an entry that skips it.
    """
    if not (
        YEAST.search(str(raw.get("organism") or ""))
        or CYTOSKELETON.search(_text(raw, "property") + " " + _keywords(raw))
    ):
        return Refusal.OUT_OF_SCOPE
    value, low, high = (_number(raw.get(k)) for k in ("value", "range_low", "range_high"))
    if value is None and (low is None or high is None):
        return Refusal.NO_VALUE
    method = str(raw.get("measurement_method") or "").strip()
    if not method or CALCULATED.search(method):
        return Refusal.NOT_MEASURED
    if not raw.get("reference_pubmed_id"):
        return Refusal.NO_REFERENCE
    if raw.get("range_fused"):
        return Refusal.FUSED_RANGE
    if low is not None and high is not None and low > 0 and high > 0:
        if max(low, high) / min(low, high) > IMPLAUSIBLE_SPAN:
            return Refusal.IMPLAUSIBLE_SPAN
    if raw.get("range_one_sided"):
        return Refusal.ONE_SIDED
    units = str(raw.get("units") or "").strip()
    if units.lower() in _NO_UNIT:
        return Refusal.NO_UNIT
    if any(character not in _UNIT_CHARACTERS for character in units):
        return Refusal.GARBLED_UNIT
    if DOUBT.search(_text(raw, "property", "comments", "measurement_method", "keywords")):
        return Refusal.DOUBT
    return None


def entry(raw: dict) -> CuratedEntry:
    """The entry as the tier shows it. Refuses what `refusal` refuses, by the same rule."""
    reason = refusal(raw)
    if reason is not None:
        raise ValueError(f"entry {raw.get('entry_id')} may not be curated: {reason.value}")
    return CuratedEntry(
        entry_id=int(raw["entry_id"]),
        property=str(raw.get("property") or "").strip(),
        organism=str(raw.get("organism") or "").strip(),
        value=_number(raw.get("value")),
        range_low=_number(raw.get("range_low")),
        range_high=_number(raw.get("range_high")),
        units=str(raw.get("units") or "").strip(),
        approximate=bool(raw.get("range_approximate")),
        reference=str(raw.get("reference") or "").strip(),
        pubmed_id=str(raw.get("reference_pubmed_id")),
        method=str(raw.get("measurement_method") or "").strip(),
        comments=str(raw.get("comments") or "").strip(),
    )


def select(raws: Iterable[dict]) -> tuple[list[CuratedEntry], Counter[Refusal]]:
    """The entries that may be curated, and how many were refused for each reason."""
    kept: list[CuratedEntry] = []
    refused: Counter[Refusal] = Counter()
    for raw in raws:
        reason = refusal(raw)
        if reason is None:
            kept.append(entry(raw))
        else:
            refused[reason] += 1
    return kept, refused


def read_corpus(path: str | Path) -> Iterator[dict]:
    """The corpus's lines as the ingester wrote them. An external input: never committed."""
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
