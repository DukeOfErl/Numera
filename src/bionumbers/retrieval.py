"""Provider-independent retrieval types, and resolution of a corpus entry to an identifier.

Retrieval either yields a document or a typed reason it could not. Nothing is dropped and no
generic failure stands in for a known cause — see `openspec/specs`, `source-retrieval`,
"Unavailability is typed and never silent".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from bionumbers.corpus import CorpusEntry


class UnavailabilityReason(StrEnum):
    """The closed set of reasons a claimed source could not be examined."""

    NON_ARTICLE_SOURCE = "NON_ARTICLE_SOURCE"
    """The reference names a book, thesis, or database — something with no article identifier."""

    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
    """The reference is absent or is free text no identifier could be determined from."""

    NO_FULL_TEXT = "NO_FULL_TEXT"
    """The article was found, but only metadata or an abstract is available."""

    NO_OPEN_ACCESS = "NO_OPEN_ACCESS"
    """The article's full text exists but sits behind an access restriction."""


class ArtifactKind(StrEnum):
    """Which artifact of a work was actually examined."""

    VERSION_OF_RECORD = "VERSION_OF_RECORD"
    PREPRINT = "PREPRINT"


@dataclass(frozen=True, slots=True)
class SourceIdentifier:
    """A persistent document identifier."""

    scheme: str
    """One of `PMID`, `PMCID`, `DOI`."""

    value: str

    def __str__(self) -> str:
        return f"{self.scheme}:{self.value}"


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    """Machine-readable full text, and a record of exactly which artifact it came from."""

    identifier: SourceIdentifier
    """The identifier the caller asked for."""

    artifact: ArtifactKind

    artifact_id: str
    """Identifier of the artifact actually fetched — equal to the requested one for a version of
    record, and the preprint's own identifier when a preprint was substituted."""

    version: str
    """Human-readable version label, e.g. `version of record` or `bioRxiv 2020-01-31`. Recorded so
    that a value differing between preprint and published article is attributable to version
    drift rather than to a validator defect."""

    content: str
    """JATS XML."""

    retrieved_from: str
    """URL the content came from."""

    @property
    def is_preprint(self) -> bool:
        return self.artifact is ArtifactKind.PREPRINT


@dataclass(frozen=True, slots=True)
class Unavailable:
    """A typed reason no document could be examined."""

    reason: UnavailabilityReason
    detail: str
    """Human-readable specifics, for debugging a wrong verdict without re-running the pipeline."""


RetrievalOutcome = RetrievedDocument | Unavailable
"""Every retrieval yields exactly one of these."""


_PMID = re.compile(r"^(?:pmid|pubmed)\s*[:\s]\s*(\d+)$", re.IGNORECASE)
_PMCID = re.compile(r"^(?:pmcid\s*[:\s]\s*)?(PMC\d+)$", re.IGNORECASE)
_DOI = re.compile(r"^(?:doi\s*[:\s]\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", re.IGNORECASE)
_BARE_DIGITS = re.compile(r"^\d{1,8}$")

_NON_ARTICLE_MARKERS = (
    "isbn",
    "book",
    "thesis",
    "dissertation",
    "patent",
    "url",
    "http://",
    "https://",
    "personal communication",
)


def resolve_identifier(entry: CorpusEntry) -> SourceIdentifier | Unavailable:
    """Resolve a corpus entry's claimed reference to a persistent identifier.

    Returns `Unavailable` rather than guessing: a best-guess retrieval would attribute evidence to
    a document the curator never cited.
    """
    raw = (entry.source_id or "").strip()
    if not raw:
        return Unavailable(
            UnavailabilityReason.UNRESOLVED_REFERENCE,
            f"entry {entry.id} carries no source identifier",
        )

    lowered = raw.lower()
    if any(marker in lowered for marker in _NON_ARTICLE_MARKERS) and not _DOI.match(raw):
        return Unavailable(
            UnavailabilityReason.NON_ARTICLE_SOURCE,
            f"entry {entry.id} cites a non-article source: {raw!r}",
        )

    if match := _PMID.match(raw):
        return SourceIdentifier("PMID", match.group(1))
    if match := _PMCID.match(raw):
        return SourceIdentifier("PMCID", match.group(1).upper())
    if match := _DOI.match(raw):
        return SourceIdentifier("DOI", match.group(1))
    if _BARE_DIGITS.match(raw):
        return SourceIdentifier("PMID", raw)

    return Unavailable(
        UnavailabilityReason.UNRESOLVED_REFERENCE,
        f"entry {entry.id} has an unrecognised source identifier: {raw!r}",
    )


def count_by_reason(outcomes: list[RetrievalOutcome]) -> dict[UnavailabilityReason, int]:
    """Break unavailable outcomes down by typed reason, reporting every reason including zeroes."""
    counts = {reason: 0 for reason in UnavailabilityReason}
    for outcome in outcomes:
        if isinstance(outcome, Unavailable):
            counts[outcome.reason] += 1
    return counts
