"""The evaluation corpus: its record shape and a loader for it.

The corpus is a swappable, external input. It is never bundled with this package and never
committed to this repository — see `openspec/specs`, `grounding-benchmark`. A corpus file is
JSONL: one JSON object per line, with the fields documented on `CorpusEntry`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

NO_CORPUS_MESSAGE = (
    "No evaluation corpus was supplied. Pass the path to a JSONL corpus file "
    "(one JSON object per line). There is no bundled corpus to fall back on: the corpus is an "
    "external input and is deliberately not distributed with this package."
)


class CorpusError(Exception):
    """The corpus could not be loaded."""


class CorpusNotSuppliedError(CorpusError):
    """No corpus path was given, and no bundled corpus exists to fall back on."""

    def __init__(self, message: str = NO_CORPUS_MESSAGE) -> None:
        super().__init__(message)


class MalformedCorpusError(CorpusError):
    """A corpus line could not be read as an entry."""


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    """One curated quantity, with enough context to check it against its source.

    Only the fields the validator and the benchmark actually use are modelled; a corpus file may
    carry others, and they are ignored.
    """

    id: str
    """Stable identifier of the entry within its corpus."""

    property: str
    """What was measured, as the curator described it (e.g. "Diameter of microtubule")."""

    organism: str | None = None
    """Organism the measurement was made in, if recorded."""

    value_low: float | None = None
    """The claimed value; the lower bound when the claim is a range."""

    value_high: float | None = None
    """Upper bound when the claim is a range; None when the claim is a point value."""

    units: str | None = None
    """Units as written by the curator; None when the quantity is dimensionless."""

    source_id: str | None = None
    """Persistent identifier of the claimed source (e.g. "PMID:9843947")."""

    quotation: str | None = None
    """Verbatim text the curator quoted from the source."""

    quotation_location: str | None = None
    """Where in the source the curator placed it (e.g. "p.1719 left column 2nd paragraph")."""

    keywords: tuple[str, ...] = ()
    """Curator-assigned keywords, used by subset selection."""


def load_corpus(path: Path | str | None) -> list[CorpusEntry]:
    """Read a JSONL corpus file.

    Raises `CorpusNotSuppliedError` when no path is given — there is no bundled fallback — and
    `MalformedCorpusError`, naming the offending line, when a record cannot be read.
    """
    if path is None:
        raise CorpusNotSuppliedError

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CorpusError(f"No corpus file at {path}") from exc
    except IsADirectoryError as exc:
        raise CorpusError(f"Corpus path {path} is a directory, not a JSONL file") from exc
    except UnicodeDecodeError as exc:
        raise MalformedCorpusError(f"Corpus file {path} is not valid UTF-8") from exc

    entries: list[CorpusEntry] = []
    seen: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        entry = _parse_line(line, path, line_number)
        if entry.id in seen:
            raise MalformedCorpusError(
                f"{path} line {line_number}: duplicate entry id {entry.id!r}, "
                f"first seen on line {seen[entry.id]}"
            )
        seen[entry.id] = line_number
        entries.append(entry)
    return entries


def _parse_line(line: str, path: Path, line_number: int) -> CorpusEntry:
    where = f"{path} line {line_number}"
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MalformedCorpusError(f"{where}: not valid JSON ({exc.msg})") from exc
    if not isinstance(record, dict):
        raise MalformedCorpusError(f"{where}: expected a JSON object, got {type(record).__name__}")

    value_low = _number(record.get("value_low"), "value_low", where)
    value_high = _number(record.get("value_high"), "value_high", where)
    if value_high is not None and value_low is None:
        raise MalformedCorpusError(f"{where}: value_high given without value_low")

    return CorpusEntry(
        id=_required_text(record, "id", where),
        property=_required_text(record, "property", where),
        organism=_text(record.get("organism"), "organism", where),
        value_low=value_low,
        value_high=value_high,
        units=_text(record.get("units"), "units", where),
        source_id=_text(record.get("source_id"), "source_id", where),
        quotation=_text(record.get("quotation"), "quotation", where),
        quotation_location=_text(record.get("quotation_location"), "quotation_location", where),
        keywords=_keywords(record.get("keywords"), where),
    )


def _required_text(record: dict, key: str, where: str) -> str:
    if key not in record:
        raise MalformedCorpusError(f"{where}: missing required field {key!r}")
    value = _text(record[key], key, where)
    if value is None:
        raise MalformedCorpusError(f"{where}: required field {key!r} is empty")
    return value


def _text(value: object, key: str, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MalformedCorpusError(f"{where}: {key!r} must be a string, got {type(value).__name__}")
    stripped = value.strip()
    return stripped or None


def _number(value: object, key: str, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MalformedCorpusError(f"{where}: {key!r} must be a number, got {type(value).__name__}")
    return float(value)


def _keywords(value: object, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MalformedCorpusError(f"{where}: 'keywords' must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())
