"""The corpus record shape and its loader.

The corpus is an external input with unresolved licensing and must not be
committed, so it is supplied at run time and no copy is bundled. Only the fields
this project actually uses are modelled; anything else in the file is ignored,
so a corpus with extra columns still loads.

`Entry`'s field set and the coercions below are a contract with the
`add-corpus-ingestion` change, whose ingester produces the file this reads. Its
contract test restates these twelve keys as a literal list, so a change here is
invisible to it until the two branches merge. **Changing a field name, adding a
required field, or altering how `_number` or `_keywords` coerce a value needs a
message to that branch**, not just a passing suite here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CorpusUnavailable(Exception):
    """Raised instead of falling back to bundled data, of which there is none."""


@dataclass(frozen=True)
class Entry:
    bnid: int
    property: str
    organism: str
    units: str
    value: float | None
    range_low: float | None
    range_high: float | None
    reference: str
    reference_pubmed_id: str | None
    measurement_method: str
    comments: str
    keywords: tuple[str, ...]
    # What the source did not claim, reported by the ingester and never repaired
    # here. Two fields and not one: a record can carry either without the other,
    # and "the source states a bound, not a range" is a different sentence from
    # "these bounds may belong to two different quantities". BNID 100420 carries
    # both -- `~160,000 (21,000 to 195,700)` is hedged *and* fused -- and one flag
    # would have said a single thing about a record wrong in two ways.
    #
    # Default False so a corpus without the fields still loads, at the cost of
    # reporting nothing rather than reporting wrongly. `tests/test_markers_against_corpus.py`
    # is what catches a corpus where they never arrive.
    range_qualified: bool = False
    range_fused: bool = False
    # Which kind of hedge, so the value can say it in the source's own terms. "~20"
    # is an approximation and "<8" is a bound, and calling the first one "bounded"
    # describes it wrongly while claiming to correct a description. The ingester
    # reports the two behind `range_qualified` as `range_approximate` (1,639) and
    # `range_one_sided` (594); measured over this corpus they partition it exactly,
    # with no overlap and none missing.
    range_approximate: bool = False
    range_one_sided: bool = False

    @property
    def value_display(self) -> str:
        if self.value is not None:
            return str(self.value)
        # Both bounds are required: a half-open range rendered as "0.5–None" would
        # be handed to the model as this entry's value and could be cited.
        if self.range_low is not None and self.range_high is not None:
            # 1,403 of the corpus's entries store a single measurement as a range
            # whose bounds are equal. Rendered literally that reads "400.0–400.0",
            # which invites a reader to look for a spread that is not there.
            if self.range_low == self.range_high:
                # A hedged bound is stored as a degenerate interval: `<8` arrives as
                # [8, 8]. Printed as "8.0" it asserts an equality the source never
                # made, which is a different claim rather than a rounder one -- an
                # MIC of `<8` means susceptible at or below 8. The bound is all the
                # corpus kept, so this says a bound was stated without inventing
                # which direction it pointed.
                if self.range_qualified:
                    return f"{self.range_low} ({self.hedge})"
                return str(self.range_low)
            return f"{self.range_low}–{self.range_high}"
        if self.range_low is not None:
            return f"at least {self.range_low}"
        if self.range_high is not None:
            return f"at most {self.range_high}"
        return "(no scalar value)"

    @property
    def hedge(self) -> str:
        """How the source hedged this value, in as few words as the column allows.

        Falls back to the general wording when the kind is not reported, because
        saying less is not the same as saying something untrue.
        """
        if self.range_approximate:
            return "approximate"
        if self.range_one_sided:
            return "a bound, not exact"
        return "bounded, not exact"

    @property
    def spans_implausibly(self) -> bool:
        """Whether the two bounds are too far apart to be one measurement.

        Ours to judge, and deliberately not the ingester's. `range_fused` claims the
        bounds may come from two quantities, which is a statement about provenance;
        this is a judgement about the number, and the ingester does not judge ranges
        (its ADR-0230). So the threshold is this project's to choose and defend.

        A millionfold. Far outside what a measurement of one quantity spans -- cell
        volumes across all life cover about 10^4 -- and the entries above it in this
        corpus are wrong on inspection rather than merely broad. 47 entries span it;
        `range_fused` already marks 42, so this adds five that parsed correctly and
        are still unusable, `0.25-2.5e30` among them.

        Zero and negative bounds are not judged: a ratio is meaningless across zero,
        and a mark firing on arithmetic rather than evidence is worse than no mark.
        """
        low, high = self.range_low, self.range_high
        if low is None or high is None or low <= 0 or high <= 0:
            return False
        return max(low, high) / min(low, high) > IMPLAUSIBLE_SPAN

    @property
    def quotation_text(self) -> str:
        """Where curator quotations live, when an entry carries one."""
        return f"{self.comments}\n{self.measurement_method}".strip()


# See `Entry.spans_implausibly` for why this number and why it is ours.
IMPLAUSIBLE_SPAN = 1_000_000


def _number(value: Any) -> float | None:
    """Coerce to a number, or None.

    A corpus converted from a spreadsheet writes "" for an absent scalar, and may
    write numbers as strings. An empty string is not None, so left uncoerced it
    would satisfy the "has a value" branch and blank out every range-only entry.
    """
    if value is None or value == "":
        return None
    return float(value)


def _keywords(value: Any) -> tuple[str, ...]:
    """Keywords as a tuple, whether the corpus stores a list or a joined string.

    Passing a string to tuple() yields one entry per character, which would make
    every single-letter search match everything and every real term match nothing
    -- silently, since nothing raises.
    """
    if not value:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple(str(v) for v in value)


def _entry(raw: dict) -> Entry:
    return Entry(
        bnid=int(raw["bnid"]),
        property=(raw.get("property") or "").strip(),
        organism=(raw.get("organism") or "").strip(),
        units=(raw.get("units") or "").strip(),
        value=_number(raw.get("value")),
        range_low=_number(raw.get("range_low")),
        range_high=_number(raw.get("range_high")),
        reference=(raw.get("reference") or "").strip(),
        reference_pubmed_id=raw.get("reference_pubmed_id") or None,
        measurement_method=(raw.get("measurement_method") or "").strip(),
        comments=(raw.get("comments") or "").strip(),
        keywords=_keywords(raw.get("keywords")),
        range_qualified=bool(raw.get("range_qualified")),
        range_fused=bool(raw.get("range_fused")),
        # Read from the flag list, which is where the ingester reports the kind.
        # Absent, the value still says it was hedged -- less precisely, never wrongly.
        range_approximate="range_approximate" in (raw.get("parse_flags") or ()),
        range_one_sided="range_one_sided" in (raw.get("parse_flags") or ()),
    )


def load(path: str | Path | None) -> tuple[Entry, ...]:
    """Load a JSONL corpus. No path means no corpus -- there is no fallback."""
    if not path:
        raise CorpusUnavailable(
            "No corpus path supplied. The corpus is an external input and is not "
            "bundled with this project; pass its path explicitly."
        )
    p = Path(path)
    if not p.is_file():
        raise CorpusUnavailable(f"No corpus file at {p}.")
    entries = []
    with p.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_entry(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise CorpusUnavailable(f"{p}: line {number} is not a usable entry: {exc}") from exc
    if not entries:
        raise CorpusUnavailable(f"{p} contains no entries.")
    return tuple(entries)
