"""Retrieval against Europe PMC, driven end to end over recorded responses."""

import json

import pytest

from bionumbers.cache import DocumentCache
from bionumbers.corpus import CorpusEntry
from bionumbers.europepmc import VERSION_OF_RECORD, EuropePMC
from bionumbers.retrieval import (
    ArtifactKind,
    RetrievedDocument,
    SourceIdentifier,
    Unavailable,
    UnavailabilityReason,
    resolve_identifier,
)
from europepmc_double import (
    NOT_INDEXED_PMID,
    OPEN_ACCESS_PMCID,
    OPEN_ACCESS_PMID,
    PAYWALLED_PMID,
    PREPRINT_ID,
    PREPRINT_WITHOUT_XML_ID,
    FakeEuropePMC,
    fixture,
    offline_client,
    preprint_versions,
)


@pytest.fixture
def api():
    return FakeEuropePMC()


@pytest.fixture
def provider(api):
    with api.client() as client:
        yield EuropePMC(client)


def pmid(value):
    return SourceIdentifier("PMID", value)


class TestOpenAccessFullText:
    def test_retrieves_the_version_of_record(self, provider):
        result = provider.retrieve(pmid(OPEN_ACCESS_PMID))

        assert isinstance(result, RetrievedDocument)
        assert result.artifact is ArtifactKind.VERSION_OF_RECORD
        assert result.artifact_id == OPEN_ACCESS_PMCID
        assert result.version == VERSION_OF_RECORD
        assert not result.is_preprint

    def test_returns_jats_xml(self, provider):
        result = provider.retrieve(pmid(OPEN_ACCESS_PMID))

        assert "JATS" in result.content[:400]
        assert "<article" in result.content
        assert "<body" in result.content
        assert result.content.rstrip().endswith("</article>")

    def test_records_where_the_text_came_from(self, provider):
        result = provider.retrieve(pmid(OPEN_ACCESS_PMID))

        assert result.retrieved_from.endswith(f"/{OPEN_ACCESS_PMCID}/fullTextXML")

    def test_carries_the_requested_identifier_through(self, provider):
        result = provider.retrieve(pmid(OPEN_ACCESS_PMID))

        assert result.identifier == pmid(OPEN_ACCESS_PMID)

    def test_does_not_look_for_a_preprint_when_the_article_is_open(self, provider, api):
        provider.retrieve(pmid(OPEN_ACCESS_PMID))

        assert not any("SRC:PPR" in url for url in api.requests)


class TestTypedUnavailability:
    def test_paywalled_article_reports_no_open_access(self, provider):
        result = provider.retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(result, Unavailable)
        assert result.reason is UnavailabilityReason.NO_OPEN_ACCESS

    def test_paywalled_article_is_never_fetched(self, provider, api):
        provider.retrieve(pmid(PAYWALLED_PMID))

        assert api.full_text_requests == []

    def test_unindexed_identifier_reports_no_full_text(self, provider):
        result = provider.retrieve(pmid(NOT_INDEXED_PMID))

        assert result.reason is UnavailabilityReason.NO_FULL_TEXT
        assert "not indexed" in result.detail

    def test_every_reason_carries_a_debuggable_detail(self, provider):
        for identifier in [pmid(PAYWALLED_PMID), pmid(NOT_INDEXED_PMID)]:
            result = provider.retrieve(identifier)

            assert result.detail
            assert identifier.value in result.detail

    def test_reasons_come_from_the_closed_set(self, provider):
        for identifier in [pmid(PAYWALLED_PMID), pmid(NOT_INDEXED_PMID)]:
            result = provider.retrieve(identifier)

            assert result.reason in set(UnavailabilityReason)

    def test_unresolvable_entries_are_retained_not_dropped(self, provider):
        entries = [
            CorpusEntry(id="a", property="p", source_id=f"PMID:{OPEN_ACCESS_PMID}"),
            CorpusEntry(id="b", property="p", source_id=None),
            CorpusEntry(id="c", property="p", source_id=f"PMID:{PAYWALLED_PMID}"),
            CorpusEntry(id="d", property="p", source_id="ISBN:978-0815344322"),
        ]

        outcomes = []
        for entry in entries:
            resolved = resolve_identifier(entry)
            outcomes.append(
                resolved if isinstance(resolved, Unavailable) else provider.retrieve(resolved)
            )

        assert len(outcomes) == len(entries)
        assert [type(outcome).__name__ for outcome in outcomes] == [
            "RetrievedDocument",
            "Unavailable",
            "Unavailable",
            "Unavailable",
        ]


class TestPreprintSubstitution:
    @pytest.fixture
    def provider_with_preprint(self, api):
        """The paywalled article's title search resolves to a real preprint with XML."""
        api.preprint_title_search = _title_search_matching(PAYWALLED_PMID)
        with api.client() as client:
            yield EuropePMC(client)

    def test_substitutes_a_preprint_for_a_paywalled_article(self, provider_with_preprint):
        result = provider_with_preprint.retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(result, RetrievedDocument)
        assert result.artifact is ArtifactKind.PREPRINT
        assert result.is_preprint

    def test_records_the_preprint_and_its_version(self, provider_with_preprint):
        result = provider_with_preprint.retrieve(pmid(PAYWALLED_PMID))

        assert result.artifact_id == PREPRINT_ID
        assert "bioRxiv" in result.version
        assert PREPRINT_ID in result.version

    def test_preprint_substitution_can_be_switched_off(self, api):
        api.preprint_title_search = _title_search_matching(PAYWALLED_PMID)
        with api.client() as client:
            provider = EuropePMC(client, allow_preprint_fallback=False)

            result = provider.retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(result, Unavailable)

    def test_a_different_paper_sharing_wording_is_not_substituted(self, api):
        api.preprint_title_search = json.dumps(
            {
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": PREPRINT_ID,
                            "source": "PPR",
                            "title": "A completely different paper about something else",
                            "isOpenAccess": "Y",
                            "firstPublicationDate": "2020-01-01",
                        }
                    ]
                },
            }
        )
        with api.client() as client:
            result = EuropePMC(client).retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(result, Unavailable)
        assert result.reason is UnavailabilityReason.NO_OPEN_ACCESS

    def test_preprint_without_xml_is_not_reported_as_retrieved(self, api):
        """Europe PMC flags these as having full text yet serves none."""
        api.preprint_title_search = json.dumps(
            {
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": PREPRINT_WITHOUT_XML_ID,
                            "source": "PPR",
                            "title": _paywalled_title(),
                            "isOpenAccess": "Y",
                            "firstPublicationDate": "2020-02-02",
                        }
                    ]
                },
            }
        )
        with api.client() as client:
            result = EuropePMC(client).retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(result, Unavailable)

    def test_falls_through_to_the_next_version_when_one_serves_no_xml(self, api):
        """The first-choice version has no XML; retrieval moves on rather than giving up."""
        api.preprint_title_search = json.dumps(
            {
                "hitCount": 2,
                "resultList": {
                    "result": [
                        {
                            "id": PREPRINT_WITHOUT_XML_ID,
                            "source": "PPR",
                            "title": _paywalled_title(),
                            "isOpenAccess": "Y",
                            "firstPublicationDate": "1980-01-01",
                        },
                        {
                            "id": PREPRINT_ID,
                            "source": "PPR",
                            "title": _paywalled_title(),
                            "isOpenAccess": "Y",
                            "firstPublicationDate": "1990-01-01",
                        },
                    ]
                },
            }
        )
        with api.client() as client:
            result = EuropePMC(client).retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(result, RetrievedDocument)
        assert result.artifact_id == PREPRINT_ID


class TestPreprintVersionChoice:
    """Closest to the version of record's publication date wins — design.md, "Preprint version
    selection". Revisit when the project moves to finding new numbers rather than benchmarking."""

    def _retrieve_with_versions(self, api, *dates):
        api.preprint_title_search = _versions_titled(_paywalled_title(), *dates)
        with api.client() as client:
            return EuropePMC(client).retrieve(pmid(PAYWALLED_PMID)), api

    def test_picks_the_version_closest_to_the_publication_date(self, api):
        # The paywalled fixture's article was published 1980-04-01, so the 1980-05-01 version is
        # nearest. 2020-01-01 is the newest and must lose — this is what separates the two rules.
        result, api = self._retrieve_with_versions(api, "1975-01-01", "1980-05-01", "2020-01-01")

        assert "1980-05-01" in result.version

    def test_a_later_version_can_win_when_it_is_closer(self, api):
        result, _ = self._retrieve_with_versions(api, "1970-01-01", "1980-07-01")

        assert "1980-07-01" in result.version

    def test_single_version_is_taken_regardless_of_distance(self, api):
        result, _ = self._retrieve_with_versions(api, "2021-09-09")

        assert "2021-09-09" in result.version


class TestCaching:
    def test_second_retrieval_makes_no_network_call(self, api, tmp_path):
        cache = DocumentCache(tmp_path / "cache")

        with api.client() as client:
            first = EuropePMC(client, cache=cache).retrieve(pmid(OPEN_ACCESS_PMID))
        assert isinstance(first, RetrievedDocument)
        assert api.requests, "the first retrieval should have hit the network"

        with offline_client() as client:
            second = EuropePMC(client, cache=cache).retrieve(pmid(OPEN_ACCESS_PMID))

        assert second == first

    def test_unavailable_outcomes_still_avoid_refetching_the_search(self, api, tmp_path):
        cache = DocumentCache(tmp_path / "cache")

        with api.client() as client:
            first = EuropePMC(client, cache=cache).retrieve(pmid(PAYWALLED_PMID))

        with offline_client() as client:
            second = EuropePMC(client, cache=cache).retrieve(pmid(PAYWALLED_PMID))

        assert second == first

    def test_without_a_cache_the_second_retrieval_refetches(self, api):
        with api.client() as client:
            provider = EuropePMC(client)
            provider.retrieve(pmid(OPEN_ACCESS_PMID))
            count_after_first = len(api.requests)
            provider.retrieve(pmid(OPEN_ACCESS_PMID))

        assert len(api.requests) > count_after_first

    def test_cache_survives_a_new_provider_and_a_new_process_boundary(self, api, tmp_path):
        cache_dir = tmp_path / "cache"

        with api.client() as client:
            EuropePMC(client, cache=DocumentCache(cache_dir)).retrieve(pmid(OPEN_ACCESS_PMID))

        with offline_client() as client:
            result = EuropePMC(client, cache=DocumentCache(cache_dir)).retrieve(
                pmid(OPEN_ACCESS_PMID)
            )

        assert isinstance(result, RetrievedDocument)

    def test_different_identifiers_do_not_share_a_cache_entry(self, api, tmp_path):
        cache = DocumentCache(tmp_path / "cache")

        with api.client() as client:
            provider = EuropePMC(client, cache=cache)
            provider.retrieve(pmid(OPEN_ACCESS_PMID))
            other = provider.retrieve(pmid(PAYWALLED_PMID))

        assert isinstance(other, Unavailable)


class TestIdentifierQueries:
    @pytest.mark.parametrize(
        ("identifier", "expected"),
        [
            (SourceIdentifier("PMID", "9722616"), "EXT_ID:9722616 AND SRC:MED"),
            (SourceIdentifier("PMCID", "PMC2132865"), "PMCID:PMC2132865"),
            (SourceIdentifier("DOI", "10.1083/jcb.1"), 'DOI:"10.1083/jcb.1"'),
        ],
    )
    def test_each_scheme_builds_its_query(self, api, identifier, expected):
        with api.client() as client:
            EuropePMC(client).retrieve(identifier)

        assert api.queries[0] == expected

    def test_an_unsupported_scheme_is_rejected(self, provider):
        with pytest.raises(ValueError, match="unsupported identifier scheme"):
            provider.retrieve(SourceIdentifier("ISBN", "978-0815344322"))


def _paywalled_title():
    payload = json.loads(fixture("search_paywalled.json"))
    return payload["resultList"]["result"][0]["title"]


def _title_search_matching(_pmid):
    """The recorded preprint response, retitled to match the paywalled article."""
    payload = json.loads(fixture("search_preprint_by_title.json"))
    payload["resultList"]["result"][0]["title"] = _paywalled_title()
    return json.dumps(payload)


def _versions_titled(title, *dates):
    """Several fetchable versions of one preprint, all titled to match the paywalled article."""
    payload = json.loads(preprint_versions(*dates))
    for result in payload["resultList"]["result"]:
        result["title"] = title
        result["id"] = PREPRINT_ID
    return json.dumps(payload)
