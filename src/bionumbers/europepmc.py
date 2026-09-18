"""Europe PMC as the source provider.

One API covers open-access full text and indexed bioRxiv/medRxiv preprints, and serves JATS XML
for both, so preprint substitution and version-of-record retrieval share a parser and no PDF text
extraction is needed. Confined behind the `retrieval` types so it can be swapped or supplemented.

Retrieval never circumvents an access control: a paywalled article yields `NO_OPEN_ACCESS`.

Two entry points, one service. `retrieve` answers about a single claimed citation and is the
entry-driven half. `search_open_access` and `fetch` are discovery's half: from a question's terms
to the articles that may be read, each with its full text in hand or a typed reason there is none.
They differ in what they do with a fault -- `retrieve` raises it at its one caller, discovery
records it and walks on -- and that difference is the only reason they are not one method.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

import httpx
from lxml import etree

from bionumbers.cache import DocumentCache
from bionumbers.records import UNLICENSED, Paper
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

USER_AGENT = (
    "BioNumbers-validator/0.1 (research prototype; https://github.com/DukeOfErl/BioNumbers)"
)

#: The publication types discovery will not read, in the spelling the query sends. One list, two
#: enforcement points -- the query clause below and `_exclusion_reason` -- so the index's filter
#: and this module's cannot drift apart.
_EXCLUDED_PUB_TYPES = ("review", "meta-analysis", "editorial", "comment")

#: The service's own ceiling on a page; asking for more is an error, not a larger page.
_MAX_PAGE_SIZE = 100

_ALI = "http://www.niso.org/schemas/ali/1.0/"
_XLINK = "http://www.w3.org/1999/xlink"
_NAMESPACES = {"ali": _ALI, "xlink": _XLINK}

_MARKUP = re.compile(r"<[^>]+>")
_QUERY_SPECIALS = re.compile(r'["\\:()\[\]{}]')
_TERM_SPECIALS = re.compile(r"[\\:()\[\]{}]")


def http_client(timeout: float = 60.0) -> httpx.Client:
    """The client every request to this service should go through.

    Europe PMC is free and asks callers to say who they are; a client built at a call site is
    anonymous by default, and nothing would report that. Attaching the header here means a new
    caller is polite by construction rather than by remembering.
    """
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})


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


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One question's walk of the index: what may be read, what was dropped, and whether the
    limit -- rather than the index -- ended it."""

    query: str
    """Exactly what was sent, recorded with the run so a result set can be reproduced."""

    kept: tuple[Paper, ...]
    """Licence still `UNLICENSED`: a lite record does not state one, and the document does."""

    excluded: tuple[tuple[str, str], ...]
    """(record id, reason) for every record dropped after the index returned it. An exclusion is
    *out of scope*, never *unconfirmed* -- nothing was read, so nothing is claimed."""

    more_existed: bool


@dataclass(frozen=True, slots=True)
class FullText:
    pmcid: str
    xml: str
    url: str


@dataclass(frozen=True, slots=True)
class NoFullText:
    """Why an article's text could not be read. Never an exception: discovery walks hundreds of
    candidates and one absent document must not end the run."""

    pmcid: str
    reason: str
    """`no XML`, `not an article`, `service error` or `unreachable`."""

    status: int | None
    """The status observed, or None when no response was obtained at all."""


def build_query(
    terms: str, *, since_year: int, until_year: int, sections: tuple[str, ...] = ()
) -> str:
    """The query discovery sends, exactly as it is recorded with the run.

    Built here rather than at the call site because the spec requires the terms *actually sent* to
    be kept with the run, and a query assembled in two places is a query that can be recorded as
    one thing and sent as another.

    `sections` restricts the terms to named parts of the article (`RESULTS`, `TABLE`): where a
    number is stated is most of what distinguishes a measurement from a mention of one.
    """
    escaped = _escape_terms(terms)
    if sections:
        clause = " OR ".join(f"{section}:({escaped})" for section in sections)
    else:
        clause = escaped
    excluded = " ".join(f"AND NOT PUB_TYPE:{_quoted(kind)}" for kind in _EXCLUDED_PUB_TYPES)
    return (
        f"({clause}) AND OPEN_ACCESS:Y AND (SRC:MED OR SRC:PMC) "
        f"{excluded} AND PUB_YEAR:[{since_year} TO {until_year}]"
    )


def licence_of(record: dict | None, xml: str | None) -> str:
    """The licence as the index or the document states it, else `UNLICENSED`.

    The index record wins where it has one: a `core` lookup carries the archive's own judgement
    (`cc by`), while `<permissions>` is publisher prose that the three fixtures here already write
    three different ways. A `lite` record carries no `license` field at all, which is why an
    absent field falls through to the document instead of standing for "no licence" -- the
    difference decides whether a paper's text may be written past the disk cache.
    """
    if record is not None:
        stated = record.get("license")
        if isinstance(stated, str) and stated.strip():
            return stated.strip()
    if not xml:
        return UNLICENSED
    root = _parse_xml(xml)
    if root is None:
        return UNLICENSED
    for element in root.xpath("//*[local-name()='permissions']/*[local-name()='license']"):
        # Three layouts, all real. The NISO `ali:license_ref` is machine-readable and says so
        # (PMC13248727); an href on `<license>` itself is the older archive form; a bare link
        # inside the prose is all two of the three fixtures give (PMC13340094, PMC2288635), so a
        # reader that stops at the first two returns UNLICENSED for papers that are plainly CC BY.
        ref = element.xpath("string(ali:license_ref)", namespaces=_NAMESPACES).strip()
        if ref:
            return ref
        href = (element.get(f"{{{_XLINK}}}href") or "").strip()
        if href:
            return href
        links = element.xpath(".//*[local-name()='ext-link']/@xlink:href", namespaces=_NAMESPACES)
        for link in links:
            if str(link).strip():
                return str(link).strip()
    return UNLICENSED


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

    def search_open_access(
        self,
        terms: str,
        *,
        since_year: int,
        limit: int,
        sections: tuple[str, ...] = (),
        until_year: int | None = None,
    ) -> SearchResult:
        """Walk the index for a question's candidates, keeping only what may be read.

        `resultType=lite` because nothing in the core record decides keep-or-drop, and the lite
        record is a fraction of the size; the licence is read from the document later. Paging is
        by cursor rather than page number, which is the service's own guidance: a page number
        walks a result set that is being reindexed under it.
        """
        query = build_query(
            terms,
            since_year=since_year,
            # The current year rather than an open-ended range: an open end lets ahead-of-print
            # records for next year in, and the recorded query must state the window it used.
            until_year=until_year if until_year is not None else date.today().year,
            sections=sections,
        )
        page_size = min(limit, _MAX_PAGE_SIZE)
        cursor = "*"
        kept: list[Paper] = []
        excluded: list[tuple[str, str]] = []
        more_existed = False

        while len(kept) < limit:
            payload = self._get_json(
                "/search",
                {
                    "query": query,
                    "resultType": "lite",
                    "format": "json",
                    "pageSize": str(page_size),
                    "cursorMark": cursor,
                },
                # The cursor and the page size are part of the key: two runs of the same query
                # with different limits page differently, and one's second page is not the
                # other's.
                cache_key=f"{query}|{cursor}|{page_size}",
            )
            results = (payload.get("resultList") or {}).get("result") or []
            if not results:
                break
            for raw in results:
                if not isinstance(raw, dict):
                    continue
                if len(kept) == limit:
                    more_existed = True
                    break
                reason = _exclusion_reason(raw)
                if reason:
                    excluded.append((_record_id(raw), reason))
                    continue
                kept.append(_paper_from(raw))

            following = str(payload.get("nextCursorMark") or "")
            if len(kept) >= limit:
                # The limit ended the walk. Whether the service really had more cannot be known
                # without another request when the limit lands exactly on a page boundary, and
                # the two errors do not cost the same: an unwarranted "more existed" is a
                # footnote, while an unwarranted "the index was exhausted" tells a reader the
                # question's coverage was complete when it was not.
                more_existed = more_existed or bool(following)
                break
            if not following or following == cursor:
                break
            cursor = following

        return SearchResult(
            query=query,
            kept=tuple(kept),
            excluded=tuple(excluded),
            more_existed=more_existed,
        )

    def fetch(self, pmcid: str) -> FullText | NoFullText:
        """The article's JATS XML, or a typed reason there is none.

        Nothing here raises for an absence or for a service fault: discovery walks every kept
        candidate, and a run that stops at the first article without XML reports nothing about the
        rest. `retrieve` takes the opposite decision for the same faults, and says why.
        """
        try:
            outcome, _ = self._full_text(pmcid, VERSION_OF_RECORD)
        except httpx.TransportError:
            # An unreachable service is the one absence that says nothing at all about the
            # article, which is why it is its own reason rather than "no XML".
            return NoFullText(pmcid, "unreachable", None)
        return outcome

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

        `retrieve`'s half of the fault decision: a service fault raises here, because this method
        answers about one identifier that a caller asked for by name, and reporting a fault to it
        as "this article has no full text" is a claim about access that was never established.
        `fetch` records the same fault and walks on, for the opposite reason.
        """
        outcome, response = self._full_text(article_id, version)
        if isinstance(outcome, FullText):
            return outcome.xml
        if outcome.reason == "service error" and response is not None:
            response.raise_for_status()
        return None

    def _full_text(
        self, article_id: str, version: str
    ) -> tuple[FullText | NoFullText, httpx.Response | None]:
        """One request, classified once, for both callers. The response travels back so a caller
        that wants to raise can raise the real thing rather than a reconstruction of it; it is
        None when the cache answered and no request was made."""
        url = self._full_text_url(article_id)
        if self._cache is not None:
            cached = self._cache.get(article_id, version)
            if cached is not None:
                return FullText(article_id, cached, url), None

        response = self._client.get(url)
        content = response.text
        if response.is_error:
            # "No XML" is decided from the body, not the status. The service answered 404 for an
            # article without XML when the fixtures were first recorded and answers 500 today
            # (2026-09-18, a JSON error object); the next change of status code must not turn
            # every absent article into a run-stopping exception. An article body on an error
            # status is the one combination that *is* a service fault.
            if _looks_like_jats(content):
                return NoFullText(article_id, "service error", response.status_code), response
            return NoFullText(article_id, "no XML", response.status_code), response
        if not _looks_like_jats(content):
            # Deliberately not cached. An HTML holding page written under this article's key
            # would be served as its full text by every later run, and no request would be made
            # that could notice.
            return NoFullText(article_id, "not an article", response.status_code), response
        if self._cache is not None:
            self._cache.put(article_id, version, content)
        return FullText(article_id, content, url), response

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


def _escape_terms(terms: str) -> str:
    """The same neutralisation for a caller's search terms, except for the double quote.

    A title is a literal to be matched; terms are written by whoever is asking the question, and
    `"doubling time"` as a phrase finds a different set of papers from the two words anywhere in
    one. So the quote survives and everything else that means something to the query language
    does not. Non-ASCII is left alone for the reason `_escape_query` gives.
    """
    return _TERM_SPECIALS.sub(" ", terms)


def _quoted(pub_type: str) -> str:
    """Only the hyphenated type is quoted, as the service's own echo of the query shows: a bare
    hyphen reads as an exclusion operator, so `NOT PUB_TYPE:meta-analysis` is not what it looks
    like."""
    return f'"{pub_type}"' if "-" in pub_type else pub_type


def _record_id(raw: dict) -> str:
    """What an exclusion is recorded against. The index's own `id` is the one field every record
    has; the others are how a reader would recognise it."""
    return str(raw.get("id") or raw.get("pmcid") or raw.get("pmid") or "")


def _pub_types(raw: dict) -> list[str]:
    """Every publication type the record states, folded for comparison.

    Both fields, because the index writes them in two shapes: `pubType` is one string holding
    several (`research-article; journal article`) and appears on a lite record, while
    `pubTypeList` is the structured form and appears on a core lookup. Reading one of the two
    means a review passes whenever discovery happens to ask for the other shape.
    """
    stated: list[str] = []
    text = raw.get("pubType")
    if isinstance(text, str):
        stated.extend(part.strip() for part in text.split(";"))
    listed = raw.get("pubTypeList")
    if isinstance(listed, dict):
        entries = listed.get("pubType") or []
        if isinstance(entries, list):
            stated.extend(str(part).strip() for part in entries)
    return [part.casefold() for part in stated if part.strip()]


def _exclusion_reason(raw: dict) -> str:
    """Why this record may not be read, or an empty string when it may.

    Repeated on the client although the query already excludes all four types: the query is the
    index's judgement of its own metadata, and the metadata is what is being trusted here. The
    two directions do not cost the same -- a wrongly excluded paper is one candidate out of a few
    hundred, while a review kept is a number attributed to a paper that only quoted it -- so the
    publication-type test matches on a substring and errs towards excluding.
    """
    if raw.get("isOpenAccess") != "Y":
        return "not open access"
    if not raw.get("pmcid"):
        return "no PMCID"
    if str(raw.get("source") or "").upper() == "PPR":
        # Discovery starts from the version of record; a preprint's values may differ from the
        # published paper's, and the reviewer would have no way to see that they had.
        return "preprint"
    for stated in _pub_types(raw):
        for excluded in _EXCLUDED_PUB_TYPES:
            if excluded in stated:
                return f"publication type {stated}"
    return ""


def _paper_from(raw: dict) -> Paper:
    """The index record as the pipeline's own `Paper`. The licence is left `UNLICENSED`: a lite
    record does not state one, and asserting a licence nothing stated is the error that matters
    here."""
    return Paper(
        pmcid=str(raw.get("pmcid") or ""),
        pmid=str(raw.get("pmid") or ""),
        doi=str(raw.get("doi") or ""),
        title=_strip_markup(str(raw.get("title") or "")),
        year=_year_of(raw.get("pubYear")),
    )


def _year_of(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _parse_xml(xml: str) -> etree._Element | None:
    """Parse for the licence, and be hard to stop.

    Bytes rather than the string: lxml refuses a `str` carrying an encoding declaration, and
    Europe PMC serves one. `recover=True` because an article whose DOCTYPE names entities this
    parser will not fetch (`no_network`) must still yield its licence -- discarding a readable
    paper over its prologue is the expensive direction, and the licence is a single attribute
    near the top of the document.
    """
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, load_dtd=False)
    try:
        return etree.fromstring(xml.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError:
        return None


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
