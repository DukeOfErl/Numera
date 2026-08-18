"""Smoke tests against the real Europe PMC.

Deselected by default so the suite stays offline and deterministic. Run them when the recorded
fixtures might have drifted from the live API:

    uv run pytest -m network
"""

import httpx
import pytest

from bionumbers.europepmc import EuropePMC
from bionumbers.retrieval import (
    ArtifactKind,
    RetrievedDocument,
    Unavailable,
    UnavailabilityReason,
    SourceIdentifier,
)
from europepmc_double import NOT_INDEXED_PMID, OPEN_ACCESS_PMCID, OPEN_ACCESS_PMID, PAYWALLED_PMID

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def provider():
    with httpx.Client(timeout=60.0) as client:
        yield EuropePMC(client, allow_preprint_fallback=False)


def test_open_access_article_is_retrieved(provider):
    result = provider.retrieve(SourceIdentifier("PMID", OPEN_ACCESS_PMID))

    assert isinstance(result, RetrievedDocument), getattr(result, "detail", "")
    assert result.artifact is ArtifactKind.VERSION_OF_RECORD
    assert result.artifact_id == OPEN_ACCESS_PMCID
    assert "<body" in result.content


def test_paywalled_article_reports_no_open_access(provider):
    result = provider.retrieve(SourceIdentifier("PMID", PAYWALLED_PMID))

    assert isinstance(result, Unavailable)
    assert result.reason is UnavailabilityReason.NO_OPEN_ACCESS


def test_unindexed_identifier_reports_no_full_text(provider):
    result = provider.retrieve(SourceIdentifier("PMID", NOT_INDEXED_PMID))

    assert isinstance(result, Unavailable)
    assert result.reason is UnavailabilityReason.NO_FULL_TEXT


def test_doi_resolves_to_the_same_article(provider):
    result = provider.retrieve(SourceIdentifier("DOI", "10.1083/jcb.142.4.1053"))

    assert isinstance(result, RetrievedDocument), getattr(result, "detail", "")
    assert result.artifact_id == OPEN_ACCESS_PMCID
