"""Europe PMC as the source provider.

One API covers open-access full text and indexed bioRxiv/medRxiv preprints, and serves JATS XML
for both, so preprint substitution and version-of-record retrieval share a parser and no PDF text
extraction is needed. Confined behind the `retrieval` types so it can be swapped or supplemented.

Retrieval never circumvents an access control: a paywalled article yields `NO_OPEN_ACCESS`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

import httpx

from bionumbers.cache import DocumentCache
from bionumbers.retrieval import (
    ArtifactKind,
    RetrievalOutcome,
    RetrievedDocument,
    SourceIdentifier,
    UnavailabilityReason,
    Unavailable,
)

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

VERSION_OF_RECORD = "version of record"

_MARKUP = re.compile(r"<[^>]+>")
_QUERY_SPECIALS = re.compile(r'["\\:()\[\]{}]')


@dataclass(frozen=True, slots=True)
class _Record:
    """The subset of a Europe PMC search result this module uses."""

    id: str
    source: str
    pmcid: str | None
    title: str
    is_open_access: bool
    in_epmc: bool
    published: date | None
    publisher: str | None

    @classmethod
    def from_json(cls, raw: dict) -> _Record:
        details = raw.get("bookOrReportDetails") or {}
        return cls(
            id=str(raw.get("id", "")),
            source=str(raw.get("source", "")),
            pmcid=raw.get("pmcid"),
            title=_strip_markup(raw.get("title") or ""),
            is_open_access=raw.get("isOpenAccess") == "Y",
            in_epmc=raw.get("inEPMC") == "Y",
            published=_parse_date(raw.get("firstPublicationDate")),
            publisher=details.get("publisher"),
        )


class EuropePMC:
    """Retrieves openly accessible full text, or reports why it could not."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        cache: DocumentCache | None = None,
        base_url: str = DEFAULT_BASE_URL,
        allow_preprint_fallback: bool = True,
    ) -> None:
        self._client = client
        self._cache = cache
        self._base_url = base_url.rstrip("/")
        self._allow_preprint_fallback = allow_preprint_fallback

    def retrieve(self, identifier: SourceIdentifier) -> RetrievalOutcome:
        """Fetch the version of record if it is openly accessible, else an openly accessible
        preprint of the same work, else a typed reason."""
        records = self._search(self._identifier_query(identifier), cache_key=str(identifier))
        if not records:
            # The closed reason set has no "not indexed" member, and substituting a generic failure
            # is forbidden. No full text could be obtained, and the detail says exactly why.
            return Unavailable(
                UnavailabilityReason.NO_FULL_TEXT,
                f"{identifier} is not indexed in Europe PMC",
            )

        record = records[0]

        # The version of record is preferred over any preprint whenever it is openly accessible.
        if record.is_open_access and record.pmcid:
            content = self._fetch_full_text(record.pmcid, VERSION_OF_RECORD)
            if content is not None:
                return RetrievedDocument(
                    identifier=identifier,
                    artifact=ArtifactKind.VERSION_OF_RECORD,
                    artifact_id=record.pmcid,
                    version=VERSION_OF_RECORD,
                    content=content,
                    retrieved_from=self._full_text_url(record.pmcid),
                )

        preprint = self._find_preprint(identifier, record)
        if preprint is not None:
            return preprint

        if not record.is_open_access:
            return Unavailable(
                UnavailabilityReason.NO_OPEN_ACCESS,
                f"{identifier} is not open access and no openly accessible preprint was found",
            )
        return Unavailable(
            UnavailabilityReason.NO_FULL_TEXT,
            f"{identifier} exposes only metadata or an abstract",
        )

    def _find_preprint(
        self, identifier: SourceIdentifier, record: _Record
    ) -> RetrievedDocument | None:
        """Substitute an openly accessible preprint of the same work, when one exists.

        Version choice: the preprint published closest to the version of record's own publication
        date, because the curator read the published paper and that is the preprint nearest to what
        they saw. Revisit when this moves from benchmarking to finding new numbers — see design.md,
        "Preprint version selection".
        """
        if not self._allow_preprint_fallback or not record.title:
            return None

        candidates = [
            candidate
            for candidate in self._search(
                f'SRC:PPR AND TITLE:"{_escape_query(record.title)}"',
                cache_key=f"preprint-title:{record.title}",
            )
            if candidate.is_open_access and _titles_match(candidate.title, record.title)
        ]

        for candidate in _by_closeness(candidates, record.published):
            version = _preprint_version(candidate)
            content = self._fetch_full_text(candidate.id, version)
            if content is not None:
                return RetrievedDocument(
                    identifier=identifier,
                    artifact=ArtifactKind.PREPRINT,
                    artifact_id=candidate.id,
                    version=version,
                    content=content,
                    retrieved_from=self._full_text_url(candidate.id),
                )
        return None

    def _search(self, query: str, *, cache_key: str) -> list[_Record]:
        payload = self._get_json(
            "/search",
            {"query": query, "resultType": "core", "format": "json", "pageSize": "25"},
            cache_key=cache_key,
        )
        results = (payload.get("resultList") or {}).get("result") or []
        return [_Record.from_json(raw) for raw in results if isinstance(raw, dict)]

    def _get_json(self, path: str, params: dict[str, str], *, cache_key: str) -> dict:
        if self._cache is not None:
            cached = self._cache.get(cache_key, "search", suffix=".json")
            if cached is not None:
                return json.loads(cached)

        response = self._client.get(f"{self._base_url}{path}", params=params)
        response.raise_for_status()
        text = response.text
        if self._cache is not None:
            self._cache.put(cache_key, "search", text, suffix=".json")
        return json.loads(text)

    def _fetch_full_text(self, article_id: str, version: str) -> str | None:
        """Return JATS XML, or None when this article serves none.

        Europe PMC flags some preprints as having full text yet serves no XML for them, so the
        absence has to be probed rather than inferred from the metadata.
        """
        if self._cache is not None:
            cached = self._cache.get(article_id, version)
            if cached is not None:
                return cached

        response = self._client.get(self._full_text_url(article_id))
        content = response.text
        if response.is_error:
            # "No XML" is decided from the body, not the status. The service answered 404 for an
            # article without XML when the fixtures were first recorded and answers 500 today
            # (2026-09-18, a JSON error object); the next change of status code must not turn
            # every absent article into a run-stopping exception. An article body on an error
            # status is the one combination that *is* a service fault, and it still raises.
            if _looks_like_jats(content):
                response.raise_for_status()
            return None
        if not _looks_like_jats(content):
            return None
        if self._cache is not None:
            self._cache.put(article_id, version, content)
        return content

    def _full_text_url(self, article_id: str) -> str:
        return f"{self._base_url}/{article_id}/fullTextXML"

    @staticmethod
    def _identifier_query(identifier: SourceIdentifier) -> str:
        match identifier.scheme:
            case "PMID":
                return f"EXT_ID:{identifier.value} AND SRC:MED"
            case "PMCID":
                return f"PMCID:{identifier.value}"
            case "DOI":
                return f'DOI:"{identifier.value}"'
            case _:
                raise ValueError(f"unsupported identifier scheme {identifier.scheme!r}")


def _strip_markup(title: str) -> str:
    """Titles carry inline markup such as `<i>in vivo</i>`, which is not part of the title text."""
    return _MARKUP.sub("", title).strip()


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _escape_query(title: str) -> str:
    """Neutralise the query syntax's own punctuation. Non-ASCII is left alone: transliterating a
    Greek alpha to `a` turns a matching title search into zero hits."""
    return _QUERY_SPECIALS.sub(" ", title)


def _titles_match(candidate: str, wanted: str) -> bool:
    """Guard against a title search returning a different paper that merely shares wording."""
    return _normalise(candidate) == _normalise(wanted)


def _normalise(title: str) -> str:
    return re.sub(r"\W+", " ", title, flags=re.UNICODE).strip().casefold()


def _by_closeness(candidates: list[_Record], target: date | None) -> list[_Record]:
    """Closest to the target date first; newest first when there is no target. Undated candidates
    sort last either way."""
    if target is None:
        return sorted(
            candidates,
            key=lambda c: (c.published is not None, c.published or date.min),
            reverse=True,
        )
    return sorted(
        candidates,
        key=lambda c: (
            c.published is None,
            abs((c.published - target).days) if c.published else 0,
        ),
    )


def _preprint_version(record: _Record) -> str:
    publisher = record.publisher or "preprint"
    when = record.published.isoformat() if record.published else "undated"
    return f"{publisher} {when} ({record.id})"


_ROOT_ARTICLE = re.compile(
    r"""\A\s*(?:<\?xml[^>]*\?>\s*)?(?:<!DOCTYPE[^>]*>\s*)?<article[\s>]""", re.DOTALL
)


def _looks_like_jats(content: str) -> bool:
    """The document's root element is `<article>`.

    Not a substring search: `<article>` is also an HTML5 element, so an HTML error page can carry
    one in its first 4 kB and would have passed as a paper. The declaration and doctype are
    optional because Europe PMC serves both forms — with a JATS doctype for archive articles,
    with a bare XML declaration for others.
    """
    return _ROOT_ARTICLE.match(content[:4096]) is not None
