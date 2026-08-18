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
        if self.range_low is not None:
            return f"{self.range_low}–{self.range_high}"
        return "(no scalar value)"

    @property
    def quotation_text(self) -> str:
        """Where curator quotations live, when an entry carries one."""
        return f"{self.comments}\n{self.measurement_method}".strip()


def _entry(raw: dict) -> Entry:
    return Entry(
        bnid=int(raw["bnid"]),
        property=(raw.get("property") or "").strip(),
        organism=(raw.get("organism") or "").strip(),
        units=(raw.get("units") or "").strip(),
        value=raw.get("value"),
        range_low=raw.get("range_low"),
        range_high=raw.get("range_high"),
        reference=(raw.get("reference") or "").strip(),
        reference_pubmed_id=raw.get("reference_pubmed_id") or None,
        measurement_method=(raw.get("measurement_method") or "").strip(),
        comments=(raw.get("comments") or "").strip(),
        keywords=tuple(raw.get("keywords") or ()),
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
