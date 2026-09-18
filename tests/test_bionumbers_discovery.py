"""Discovery: from a question's terms to articles that may be read, and their licences.

Driven over the recorded two-page cursor walk and the recorded full-text responses, so what is
asserted is the shape the service actually returns. Every rule here decides what the extractor is
allowed to read, which is why each has a case that must be *refused* as well as one that passes.
"""

import json
from datetime import date

import httpx
import pytest
from europepmc_double import (
    BRIEF_REPORT_PMCID,
    LINK_LICENCE_PMCID,
    TABLES_PMCID,
    FakeEuropePMC,
    fixture,
    offline_client,
    unreachable_client,
)

from bionumbers.cache import DocumentCache
from bionumbers.europepmc import (
    USER_AGENT,
    EuropePMC,
    FullText,
    NoFullText,
    build_query,
    http_client,
    licence_of,
)
from bionumbers.records import UNLICENSED

TERMS = '"doubling time" AND "Escherichia coli"'
SECTIONS = ("RESULTS", "TABLE")

# A holding page that would pass a substring search for `<article>`: HTML5 has that element too.
HOLDING_PAGE = (
    "<!DOCTYPE html><html><body><article><h1>502 Bad Gateway</h1></article></body></html>"
)


@pytest.fixture
def api():
    return FakeEuropePMC()


def search(provider, **overrides):
    """One question's walk, with the window the fixtures were recorded under."""
    arguments = dict(since_year=2020, until_year=2026, limit=8, sections=SECTIONS)
    arguments.update(overrides)
    return provider.search_open_access(TERMS, **arguments)


class TestTheQuery:
    """The query is recorded with the run and is what a result set can be reproduced from, so it
    is asserted as a whole string rather than by the presence of its parts."""

    def test_reproduces_the_query_the_service_recorded(self):
        """The fixtures were fetched with this query and the service echoes it back in every
        page, so the echo is an independent statement of what the clauses must be."""
        echoed = json.loads(fixture("search_oa_page1.json"))["request"]["queryString"]

        assert build_query(TERMS, since_year=2020, until_year=2026, sections=SECTIONS) == echoed

    def test_excludes_every_publication_type_that_is_not_a_research_article(self):
        query = build_query(TERMS, since_year=2020, until_year=2026)

        assert "AND NOT PUB_TYPE:review" in query
        assert 'AND NOT PUB_TYPE:"meta-analysis"' in query
        assert "AND NOT PUB_TYPE:editorial" in query
        assert "AND NOT PUB_TYPE:comment" in query

    def test_keeps_only_open_access_records_with_a_full_text_source(self):
        query = build_query(TERMS, since_year=2020, until_year=2026)

        assert "AND OPEN_ACCESS:Y" in query
        assert "AND (SRC:MED OR SRC:PMC)" in query

    def test_states_the_year_window_it_searched(self):
        query = build_query(TERMS, since_year=2005, until_year=2026)

        assert "AND PUB_YEAR:[2005 TO 2026]" in query

    def test_without_sections_the_terms_stand_alone(self):
        """The negative of the sections case: same terms, no restriction, so a `RESULTS:` prefix
        appearing here would mean the restriction is unconditional."""
        query = build_query(TERMS, since_year=2020, until_year=2026)

        assert query.startswith(f"({TERMS}) AND OPEN_ACCESS:Y")
        assert "RESULTS:" not in query

    def test_sections_restrict_the_terms_and_nothing_else(self):
        query = build_query(TERMS, since_year=2020, until_year=2026, sections=SECTIONS)
        unrestricted = build_query(TERMS, since_year=2020, until_year=2026)

        assert query.startswith(f"(RESULTS:({TERMS}) OR TABLE:({TERMS})) AND OPEN_ACCESS:Y")
        assert query.split("AND OPEN_ACCESS:Y")[1] == unrestricted.split("AND OPEN_ACCESS:Y")[1]

    def test_a_quoted_phrase_survives(self):
        """Phrase search is the difference between the property and the two words in one paper,
        so the quote is the one piece of punctuation that must reach the service."""
        query = build_query('"doubling time"', since_year=2020, until_year=2026)

        assert '("doubling time")' in query

    @pytest.mark.parametrize("punctuation", ["(", ")", "[", "]", "{", "}", ":", "\\"])
    def test_query_punctuation_in_the_terms_is_neutralised(self, punctuation):
        """A caller writes terms, not query syntax: an unescaped bracket is a parse error at the
        service and an unescaped colon silently becomes a field restriction."""
        query = build_query(f"volume{punctuation}cell", since_year=2020, until_year=2026)

        assert f"volume{punctuation}cell" not in query
        assert "(volume cell)" in query

    def test_the_window_defaults_to_this_year(self, api):
        with api.client() as client:
            EuropePMC(client).search_open_access(TERMS, since_year=2020, limit=1)

        assert f"TO {date.today().year}]" in api.queries[0]


class TestTheCursorWalk:
    def test_pages_by_cursor_from_the_start_mark(self, api):
        """Page two is requested with the cursor page one handed back — not with a page number,
        which would walk a result set being reindexed underneath it."""
        with api.client() as client:
            search(EuropePMC(client))

        assert api.cursors == ["*", json.loads(fixture("search_oa_page1.json"))["nextCursorMark"]]

    def test_keeps_exactly_the_limit_in_the_services_order(self, api):
        with api.client() as client:
            result = search(EuropePMC(client), limit=8)

        assert [paper.pmcid for paper in result.kept] == recorded_order()[:8]

    def test_the_limit_stopping_the_walk_is_recorded(self, api):
        with api.client() as client:
            result = search(EuropePMC(client), limit=8)

        assert result.more_existed

    def test_an_exhausted_index_is_not_recorded_as_more_existing(self, api):
        """The negative of the case above, varying what ended the walk rather than the outcome:
        the same two pages, a limit no page reaches, and an empty page after them."""
        with api.client() as client:
            result = search(EuropePMC(client), limit=100)

        assert len(result.kept) == len(recorded_order())
        assert not result.more_existed

    def test_the_walk_stops_at_the_first_empty_page(self, api):
        with api.client() as client:
            search(EuropePMC(client), limit=100)

        assert len(api.cursors) == 3, api.cursors

    def test_records_the_query_it_sent(self, api):
        with api.client() as client:
            result = search(EuropePMC(client))

        assert result.query == api.queries[0]

    def test_a_kept_record_carries_what_it_takes_to_cite_it(self, api):
        with api.client() as client:
            result = search(EuropePMC(client))

        first = json.loads(fixture("search_oa_page1.json"))["resultList"]["result"][0]
        paper = result.kept[0]
        assert (paper.pmcid, paper.pmid, paper.doi) == (first["pmcid"], first["pmid"], first["doi"])
        assert paper.year == int(first["pubYear"])

    def test_inline_markup_is_not_part_of_a_title(self, api):
        with api.client() as client:
            result = search(EuropePMC(client))

        titles = [paper.title for paper in result.kept]
        assert any("Weissella" in title for title in titles)
        assert not any("<i>" in title for title in titles)

    def test_discovery_claims_no_licence_it_has_not_read(self, api):
        """A lite record states none, and the document is not fetched yet."""
        with api.client() as client:
            result = search(EuropePMC(client))

        assert {paper.licence for paper in result.kept} == {UNLICENSED}


class TestWhatIsExcluded:
    """One page, one positive control, and one record per rule differing from the control in
    exactly the attribute that rule reads."""

    @pytest.fixture
    def excluded(self, api):
        api.search_pages = {"*": page(*self.records())}
        with api.client() as client:
            return dict(search(EuropePMC(client), limit=50).excluded)

    @pytest.fixture
    def kept(self, api):
        api.search_pages = {"*": page(*self.records())}
        with api.client() as client:
            return [paper.pmcid for paper in search(EuropePMC(client), limit=50).kept]

    @staticmethod
    def records():
        no_pmcid = keepable(id="no-pmcid")
        del no_pmcid["pmcid"]
        list_only_review = keepable(id="list-review", pubTypeList={"pubType": ["Review"]})
        del list_only_review["pubType"]
        return [
            keepable(id="control"),
            keepable(id="closed", isOpenAccess="N"),
            no_pmcid,
            keepable(id="preprint", source="PPR"),
            keepable(id="review", pubType="research-article; Review"),
            list_only_review,
        ]

    def test_a_record_the_rules_pass_is_kept(self, kept):
        """Without this every assertion below could be satisfied by excluding everything."""
        assert kept == [keepable(id="control")["pmcid"]]

    @pytest.mark.parametrize(
        ("identifier", "reason"),
        [
            ("closed", "not open access"),
            ("no-pmcid", "no PMCID"),
            ("preprint", "preprint"),
            ("review", "publication type review"),
            ("list-review", "publication type review"),
        ],
    )
    def test_each_dropped_record_is_recorded_with_its_reason(self, excluded, identifier, reason):
        assert excluded[identifier] == reason

    def test_nothing_excluded_is_also_kept(self, excluded, kept):
        assert not set(excluded) & set(kept)

    def test_a_review_stated_only_in_the_structured_field_is_still_a_review(self, excluded):
        """`pubTypeList` is what a core lookup carries and `pubType` what a lite record carries;
        reading one of the two lets a review through whichever shape is asked for."""
        assert "list-review" in excluded


class TestPoliteness:
    def test_the_module_s_client_identifies_the_project(self):
        with http_client() as client:
            assert client.headers["User-Agent"] == USER_AGENT

    def test_every_request_carries_the_user_agent(self, api):
        with api.polite_client() as client:
            provider = EuropePMC(client)
            search(provider)
            provider.fetch(TABLES_PMCID)

        assert api.requests
        assert {headers["user-agent"] for headers in api.headers} == {USER_AGENT}

    def test_a_repeated_search_is_served_from_the_cache(self, api, tmp_path):
        cache = DocumentCache(tmp_path / "cache")
        with api.client() as client:
            first = search(EuropePMC(client, cache=cache))
        assert api.requests, "the first walk should have hit the service"

        with offline_client() as client:
            second = search(EuropePMC(client, cache=cache))

        assert second == first

    def test_without_a_cache_the_second_search_asks_again(self, api):
        with api.client() as client:
            provider = EuropePMC(client)
            search(provider)
            after_first = len(api.requests)
            search(provider)

        assert len(api.requests) > after_first


class TestFetch:
    def test_an_article_is_returned_with_where_it_came_from(self, api):
        with api.client() as client:
            result = EuropePMC(client).fetch(TABLES_PMCID)

        assert isinstance(result, FullText)
        assert result.pmcid == TABLES_PMCID
        assert result.url.endswith(f"/{TABLES_PMCID}/fullTextXML")
        assert "<article" in result.xml[:4096]

    def test_the_recorded_error_for_an_article_without_xml_is_typed_not_raised(self, api):
        """The service answers 500 with a JSON error object for an article it holds no XML for.
        A run walking hundreds of candidates must record that and continue."""
        result = EuropePMC(api.client()).fetch("PMC13447829")

        assert isinstance(result, NoFullText)
        assert (result.reason, result.status) == ("no XML", 500)

    def test_the_same_status_with_an_article_body_is_a_service_fault(self, api):
        """Same status as the case above; only the body differs, which is the dimension the rule
        reads. A service that fails while handing back a paper has not told us the paper has no
        text."""
        api.full_text_overrides[TABLES_PMCID] = httpx.Response(
            500, text=fixture("fulltext_PMC13248727.xml")
        )
        with api.client() as client:
            result = EuropePMC(client).fetch(TABLES_PMCID)

        assert isinstance(result, NoFullText)
        assert (result.reason, result.status) == ("service error", 500)

    def test_a_page_that_is_not_an_article_is_typed_as_such(self, api):
        api.full_text_overrides[TABLES_PMCID] = httpx.Response(200, text=HOLDING_PAGE)
        with api.client() as client:
            result = EuropePMC(client).fetch(TABLES_PMCID)

        assert isinstance(result, NoFullText)
        assert (result.reason, result.status) == ("not an article", 200)

    def test_an_unreachable_service_is_its_own_reason(self):
        """Nothing was learned about this article, so it may not share a reason with an article
        the service answered about."""
        with unreachable_client() as client:
            result = EuropePMC(client).fetch(TABLES_PMCID)

        assert isinstance(result, NoFullText)
        assert (result.reason, result.status) == ("unreachable", None)

    def test_a_second_fetch_makes_no_request(self, api, tmp_path):
        cache = DocumentCache(tmp_path / "cache")
        with api.client() as client:
            first = EuropePMC(client, cache=cache).fetch(TABLES_PMCID)

        with offline_client() as client:
            second = EuropePMC(client, cache=cache).fetch(TABLES_PMCID)

        assert second == first

    def test_a_body_that_is_not_an_article_is_never_cached(self, api, tmp_path):
        """Cached, it would be served as this article's full text by every later run, and no
        request would be made that could notice."""
        cache = DocumentCache(tmp_path / "cache")
        api.full_text_overrides[TABLES_PMCID] = httpx.Response(200, text=HOLDING_PAGE)
        with api.client() as client:
            provider = EuropePMC(client, cache=cache)
            assert isinstance(provider.fetch(TABLES_PMCID), NoFullText)
            api.full_text_overrides.clear()
            second = provider.fetch(TABLES_PMCID)

        assert isinstance(second, FullText)
        assert "<article" in second.xml[:4096]


class TestLicence:
    def test_the_index_record_states_it(self):
        record = core_record("core_PMC13340094.json")

        assert licence_of(record, None) == "cc by"

    @pytest.mark.parametrize(
        ("name", "stated"),
        [
            ("fulltext_PMC13248727.xml", "https://creativecommons.org/licenses/by/4.0/"),
            ("fulltext_PMC13340094.xml", "https://creativecommons.org/licenses/by/4.0/"),
            ("fulltext_PMC2288635.xml", "https://creativecommons.org/licenses/by/3.0/"),
        ],
    )
    def test_the_document_states_it_in_whichever_layout_its_publisher_uses(self, name, stated):
        """The first fixture carries the machine-readable `ali:license_ref`; the other two state
        the licence only as a link in the prose, which is the layout a reader that stops at
        `ali:license_ref` reports as unlicensed."""
        assert licence_of(None, fixture(name)) == stated

    def test_an_href_on_the_license_element_is_read(self):
        """JATS allows it and no recorded paper here uses it, so the document is hand-built."""
        xml = (
            '<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta>'
            '<permissions><license xlink:href="https://creativecommons.org/licenses/by/2.0/">'
            "<license-p>Open Access</license-p></license></permissions>"
            "</article-meta></front></article>"
        )

        assert licence_of(None, xml) == "https://creativecommons.org/licenses/by/2.0/"

    def test_a_lite_record_falls_through_to_the_document(self):
        """A search record carries no `license` field at all. Treating that as "no licence" would
        mark every discovered paper unlicensed and stop its text at the cache."""
        lite = json.loads(fixture("search_oa_page1.json"))["resultList"]["result"][0]
        assert "license" not in lite

        assert licence_of(lite, fixture("fulltext_PMC2288635.xml")) == (
            "https://creativecommons.org/licenses/by/3.0/"
        )

    def test_the_record_wins_over_the_document(self):
        """The archive's own judgement, against a document whose prose says something else, so
        the assertion can tell which source was read."""
        assert licence_of({"license": "cc0"}, fixture("fulltext_PMC2288635.xml")) == "cc0"

    def test_a_document_stating_no_licence_is_unlicensed(self):
        xml = (
            "<article><front><article-meta><permissions>"
            "<copyright-statement>Copyright 2026 the authors.</copyright-statement>"
            "</permissions></article-meta></front></article>"
        )

        assert licence_of(None, xml) == UNLICENSED

    @pytest.mark.parametrize("record", [None, {}, {"license": ""}, {"license": "   "}])
    def test_nothing_stated_anywhere_is_unlicensed(self, record):
        assert licence_of(record, None) == UNLICENSED

    def test_a_body_that_is_not_an_article_states_nothing(self):
        assert licence_of(None, HOLDING_PAGE) == UNLICENSED

    def test_both_research_fixtures_are_openly_licensed(self):
        """These two sit in the repository as fixtures, which only their licence permits."""
        for pmcid in (TABLES_PMCID, BRIEF_REPORT_PMCID, LINK_LICENCE_PMCID):
            licence = licence_of(None, fixture(f"fulltext_{pmcid}.xml"))

            assert licence != UNLICENSED
            assert "creativecommons.org/licenses/by/" in licence


def recorded_order() -> list[str]:
    """The pmcids the service listed, in the order it listed them — the ranking the requirement
    says discovery keeps."""
    pages = ["search_oa_page1.json", "search_oa_page2.json"]
    return [
        record["pmcid"]
        for name in pages
        for record in json.loads(fixture(name))["resultList"]["result"]
    ]


def keepable(**overrides) -> dict:
    """A record the rules keep, in the shape the index writes one, with named attributes changed.

    Taken from a recorded result rather than written by hand: a rule reading a field a hand-built
    record never carried would have no negative case at all, and the test would look thorough.
    """
    record = dict(json.loads(fixture("search_oa_page1.json"))["resultList"]["result"][0])
    record.update(overrides)
    return record


def page(*records: dict, next_cursor: str = "") -> str:
    payload = {"hitCount": len(records), "resultList": {"result": list(records)}}
    if next_cursor:
        payload["nextCursorMark"] = next_cursor
    return json.dumps(payload)


def core_record(name: str) -> dict:
    return json.loads(fixture(name))["resultList"]["result"][0]
