"""A stand-in Europe PMC built from the recorded fixtures.

Responses are the real ones captured by `tests/fixtures/capture_europepmc.py`, so the tests
exercise the shapes the API actually returns while staying offline and deterministic. The double
counts requests, which is how the cache tests prove no network call was made.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

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

EMPTY_RESULT = json.dumps({"hitCount": 0, "resultList": {"result": []}})


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


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
        self.full_text_requests: list[str] = []
        # Lets a test point the title search at a hand-built multi-version response.
        self.preprint_title_search = preprint_title_search
        # Lets a test dictate the full-text response for one article, to vary the status and
        # the body independently — the two dimensions `_fetch_full_text` has to tell apart.
        self.full_text_overrides: dict[str, httpx.Response] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)

        if request.url.path.endswith("/search"):
            query = request.url.params.get("query", "")
            self.queries.append(query)
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


class OfflineTransport(httpx.BaseTransport):
    """Fails loudly on any request — proves a code path made no network call."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network call attempted: {request.url}")


def offline_client() -> httpx.Client:
    return httpx.Client(transport=OfflineTransport())


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
