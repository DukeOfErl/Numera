"""Resolution of a corpus entry's reference to a persistent identifier."""

import pytest

from bionumbers.corpus import CorpusEntry
from bionumbers.retrieval import (
    ArtifactKind,
    RetrievedDocument,
    SourceIdentifier,
    Unavailable,
    UnavailabilityReason,
    count_by_reason,
    resolve_identifier,
)


def entry(source_id=None, **kwargs):
    return CorpusEntry(id="1", property="Diameter of microtubule", source_id=source_id, **kwargs)


class TestResolvesIdentifiers:
    @pytest.mark.parametrize(
        "raw",
        ["PMID:9722616", "pmid: 9722616", "PubMed:9722616", "PMID 9722616", "9722616"],
    )
    def test_pubmed_identifiers(self, raw):
        assert resolve_identifier(entry(raw)) == SourceIdentifier("PMID", "9722616")

    @pytest.mark.parametrize("raw", ["PMC2132865", "PMCID:PMC2132865", "pmc2132865"])
    def test_pmc_identifiers(self, raw):
        assert resolve_identifier(entry(raw)) == SourceIdentifier("PMCID", "PMC2132865")

    @pytest.mark.parametrize(
        "raw",
        [
            "10.1083/jcb.142.4.1053",
            "doi:10.1083/jcb.142.4.1053",
            "DOI: 10.1083/jcb.142.4.1053",
            "https://doi.org/10.1083/jcb.142.4.1053",
        ],
    )
    def test_dois(self, raw):
        assert resolve_identifier(entry(raw)) == SourceIdentifier("DOI", "10.1083/jcb.142.4.1053")

    def test_surrounding_whitespace_is_tolerated(self):
        assert resolve_identifier(entry("  PMID:9722616  ")).value == "9722616"

    def test_identifier_renders_for_reporting(self):
        assert str(resolve_identifier(entry("PMID:9722616"))) == "PMID:9722616"


class TestTypedResolutionFailures:
    def test_missing_identifier_is_unresolved(self):
        outcome = resolve_identifier(entry(None))

        assert outcome == Unavailable(
            UnavailabilityReason.UNRESOLVED_REFERENCE, "entry 1 carries no source identifier"
        )

    def test_blank_identifier_is_unresolved(self):
        outcome = resolve_identifier(entry("   "))

        assert outcome.reason is UnavailabilityReason.UNRESOLVED_REFERENCE

    @pytest.mark.parametrize(
        "raw",
        [
            "ISBN:978-0815344322",
            "Molecular Biology of the Cell, 4th edition (book)",
            "PhD thesis, University of Cambridge",
            "US Patent 4,683,202",
            "http://example.org/some-table",
            "personal communication with the author",
        ],
    )
    def test_non_article_sources_are_typed(self, raw):
        outcome = resolve_identifier(entry(raw))

        assert outcome.reason is UnavailabilityReason.NON_ARTICLE_SOURCE
        assert raw in outcome.detail

    @pytest.mark.parametrize("raw", ["see figure 3", "Alberts et al", "n/a", "???"])
    def test_free_text_is_unresolved(self, raw):
        outcome = resolve_identifier(entry(raw))

        assert outcome.reason is UnavailabilityReason.UNRESOLVED_REFERENCE

    def test_a_doi_url_is_not_mistaken_for_a_web_page(self):
        """`https://` marks a non-article source, but a DOI URL is still a resolvable article."""
        outcome = resolve_identifier(entry("https://doi.org/10.1083/jcb.142.4.1053"))

        assert isinstance(outcome, SourceIdentifier)

    def test_failure_names_the_entry_for_debugging(self):
        outcome = resolve_identifier(CorpusEntry(id="109811", property="x", source_id=None))

        assert "109811" in outcome.detail


class TestCounting:
    def test_counts_are_broken_down_by_reason(self):
        outcomes = [
            Unavailable(UnavailabilityReason.NO_OPEN_ACCESS, ""),
            Unavailable(UnavailabilityReason.NO_OPEN_ACCESS, ""),
            Unavailable(UnavailabilityReason.UNRESOLVED_REFERENCE, ""),
        ]

        counts = count_by_reason(outcomes)

        assert counts[UnavailabilityReason.NO_OPEN_ACCESS] == 2
        assert counts[UnavailabilityReason.UNRESOLVED_REFERENCE] == 1

    def test_every_reason_is_reported_even_at_zero(self):
        counts = count_by_reason([])

        assert set(counts) == set(UnavailabilityReason)
        assert all(count == 0 for count in counts.values())

    def test_documents_are_not_counted_as_unavailable(self):
        document = RetrievedDocument(
            identifier=SourceIdentifier("PMID", "1"),
            artifact=ArtifactKind.VERSION_OF_RECORD,
            artifact_id="PMC1",
            version="version of record",
            content="<article/>",
            retrieved_from="http://example",
        )

        assert sum(count_by_reason([document]).values()) == 0
