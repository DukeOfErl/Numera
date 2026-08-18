"""The corpus record shape and its loader.

The corpus is an external input with unresolved licensing and must not be
committed, so it is supplied at run time and no copy is bundled. Only the fields
this project actually uses are modelled; anything else in the file is ignored,
so a corpus with extra columns still loads.
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

    @property
    def value_display(self) -> str:
        if self.value is not None:
            return str(self.value)
        # Both bounds are required: a half-open range rendered as "0.5–None" would
        # be handed to the model as this entry's value and could be cited.
        if self.range_low is not None and self.range_high is not None:
            return f"{self.range_low}–{self.range_high}"
        if self.range_low is not None:
            return f"at least {self.range_low}"
        if self.range_high is not None:
            return f"at most {self.range_high}"
        return "(no scalar value)"

    @property
    def quotation_text(self) -> str:
        """Where curator quotations live, when an entry carries one."""
        return f"{self.comments}\n{self.measurement_method}".strip()


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
