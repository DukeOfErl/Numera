"""A stand-in Europe PMC built from the recorded fixtures.

Responses are the real ones captured by `tests/fixtures/capture_europepmc.py`, so the tests
exercise the shapes the API actually returns while staying offline and deterministic. The double
counts requests, which is how the cache tests prove no network call was made.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from bionumbers.europepmc import http_client

FIXTURES = Path(__file__).parent / "fixtures" / "europepmc"

OPEN_ACCESS_PMID = "9722616"
OPEN_ACCESS_PMCID = "PMC2132865"
PAYWALLED_PMID = "6771086"
NOT_INDEXED_PMID = "99999999"
PREPRINT_ID = "PPR1218639"
PREPRINT_WITHOUT_XML_ID = "PPR1090496"

# The two papers the 2026-09-18 research inspected: a brief report with no `<back>` element and
# no methods section, and a research article with XHTML tables carrying both micro-sign code
# points. Both CC BY 4.0, which is what lets them sit in the repository as fixtures.
BRIEF_REPORT_PMCID = "PMC13340094"
TABLES_PMCID = "PMC13248727"

FULL_TEXT_FIXTURES = {
    OPEN_ACCESS_PMCID: "fulltext_PMC2132865.xml",
    PREPRINT_ID: "fulltext_PPR1218639.xml",
    BRIEF_REPORT_PMCID: "fulltext_PMC13340094.xml",
    TABLES_PMCID: "fulltext_PMC13248727.xml",
}
NO_XML_FIXTURE = "fulltext_missing_PPR1090496.json"

# A third CC BY paper, recorded because its licence is stated only as a link inside the prose.
LINK_LICENCE_PMCID = "PMC2288635"

EMPTY_RESULT = json.dumps({"hitCount": 0, "resultList": {"result": []}})


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def search_pages() -> dict[str, str]:
    """The recorded cursor walk: page one under `*`, page two under the cursor page one handed
    back. The second cursor is read out of the fixture rather than written here, so a re-recorded
    pair cannot leave the double serving page two for a cursor the service no longer issues."""
    page_one = fixture("search_oa_page1.json")
    return {
        "*": page_one,
        json.loads(page_one)["nextCursorMark"]: fixture("search_oa_page2.json"),
    }


def _search_fixture_for(query: str) -> str:
    if f"EXT_ID:{OPEN_ACCESS_PMID}" in query:
        return fixture("search_open_access.json")
    if f"EXT_ID:{PAYWALLED_PMID}" in query:
        return fixture("search_paywalled.json")
    if f"EXT_ID:{NOT_INDEXED_PMID}" in query:
        return fixture("search_not_indexed.json")
    if f"EXT_ID:{PREPRINT_WITHOUT_XML_ID}" in query:
        return fixture("search_preprint_without_xml.json")
    if "SRC:PPR" in query and "TITLE:" in query:
        return fixture("search_preprint_by_title.json")
    return EMPTY_RESULT


class FakeEuropePMC:
    """Serves the recorded fixtures over an `httpx` transport, and records what was requested."""

    def __init__(self, *, preprint_title_search: str | None = None) -> None:
        self.requests: list[str] = []
        self.queries: list[str] = []
        self.cursors: list[str] = []
        self.headers: list[httpx.Headers] = []
        self.full_text_requests: list[str] = []
        # Cursor -> response body. A test that wants a page of its own replaces the mapping;
        # a cursor with no page is the end of the walk, which is how the service behaves.
        self.search_pages: dict[str, str] = search_pages()
        # Lets a test point the title search at a hand-built multi-version response.
        self.preprint_title_search = preprint_title_search
        # Lets a test dictate the full-text response for one article, to vary the status and
        # the body independently — the two dimensions `_fetch_full_text` has to tell apart.
        self.full_text_overrides: dict[str, httpx.Response] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        self.headers.append(request.headers)

        if request.url.path.endswith("/search"):
            query = request.url.params.get("query", "")
            self.queries.append(query)
            cursor = request.url.params.get("cursorMark", "")
            if cursor:
                # A cursor walk. Europe PMC hands back a cursor for the page after the last one,
                # and that page is empty -- so an unknown cursor ends the walk rather than
                # failing, which is the case a limit-free walk has to terminate on.
                self.cursors.append(cursor)
                return httpx.Response(200, text=self.search_pages.get(cursor, EMPTY_RESULT))
            if "SRC:PPR" in query and "TITLE:" in query and self.preprint_title_search is not None:
                return httpx.Response(200, text=self.preprint_title_search)
            return httpx.Response(200, text=_search_fixture_for(query))

        if request.url.path.endswith("/fullTextXML"):
            article_id = request.url.path.split("/")[-2]
            self.full_text_requests.append(article_id)
            if article_id in self.full_text_overrides:
                return self.full_text_overrides[article_id]
            if article_id in FULL_TEXT_FIXTURES:
                return httpx.Response(200, text=fixture(FULL_TEXT_FIXTURES[article_id]))
            # Europe PMC serves no XML for many preprints and for every article that is not open
            # access. It answered 404 for those when this double was first written and answers
            # 500 with a JSON error object today; the recorded body is the real one.
            return httpx.Response(500, text=fixture(NO_XML_FIXTURE))

        raise AssertionError(f"unexpected request to {url}")

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def polite_client(self) -> httpx.Client:
        """The module's own client, with its requests served from the fixtures.

        The headers are what these tests read, so they are taken from `http_client` rather than
        written out again here: a copy would keep passing after the real client stopped
        identifying the project, which is the one thing it is for.
        """
        with http_client() as configured:
            headers = configured.headers
        return httpx.Client(transport=httpx.MockTransport(self.handler), headers=headers)


class OfflineTransport(httpx.BaseTransport):
    """Fails loudly on any request — proves a code path made no network call."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network call attempted: {request.url}")


def offline_client() -> httpx.Client:
    return httpx.Client(transport=OfflineTransport())


class UnreachableTransport(httpx.BaseTransport):
    """Every request fails the way a lost network does. `ConnectError` is an `httpx.TransportError`
    — the class discovery has to survive, as distinct from a service that answered badly."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed", request=request)


def unreachable_client() -> httpx.Client:
    return httpx.Client(transport=UnreachableTransport())


def preprint_versions(*published: str) -> str:
    """A title-search response carrying several versions of one preprint, newest listed first.

    Europe PMC exposes versions as separate PPR records with distinct dates, so this is the shape
    version selection actually has to choose between.
    """
    title = json.loads(fixture("search_preprint_by_title.json"))["resultList"]["result"][0]["title"]
    results = [
        {
            "id": f"PPR{900 + index}",
            "source": "PPR",
            "title": title,
            "isOpenAccess": "Y",
            "inEPMC": "Y",
            "firstPublicationDate": when,
            "bookOrReportDetails": {"publisher": "bioRxiv"},
        }
        for index, when in enumerate(published)
    ]
    return json.dumps({"hitCount": len(results), "resultList": {"result": results}})
