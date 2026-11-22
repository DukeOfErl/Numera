"""The real-scale case the two-tier design exists for.

Skipped unless a corpus is supplied, since the corpus is an external input with
unresolved licensing and is not committed. Point NUMERA_CORPUS at a
JSONL corpus to exercise it:

    NUMERA_CORPUS=~/path/bionumbers.jsonl uv run pytest
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from numera_ask.corpus import load
from numera_ask.repository import DEFAULT_LIMIT, CorpusRepository

_path = os.environ.get("NUMERA_CORPUS", "")
_corpus = Path(_path).expanduser() if _path else None

pytestmark = pytest.mark.skipif(
    _corpus is None or not _corpus.is_file(),
    reason="set NUMERA_CORPUS to a JSONL corpus to run the scale checks",
)


@pytest.fixture(scope="module")
def repo() -> CorpusRepository:
    return CorpusRepository(load(_corpus))


def test_a_broad_search_stays_bounded_and_reports_the_true_total(repo):
    result = repo.search(property="number of")
    # The motivating measurement: a single-word property search matches far more
    # entries than any answer needs, and far more than a context window wants.
    assert result.total_matched > 1000
    assert len(result.rows) == DEFAULT_LIMIT
    assert result.truncated is True


def test_the_bounded_payload_is_orders_of_magnitude_smaller(repo):
    result = repo.search(property="number of")
    returned = sum(len(str(r)) for r in result.rows)
    # Full entries average roughly eight times a compact row; with this many
    # matches the difference is the whole point of the design.
    assert returned * 50 < result.total_matched * 1400


def test_an_abbreviated_binomial_reaches_the_real_stored_wording(repo):
    resolved = repo.aliases()["e. coli"]
    assert "Bacteria Escherichia coli" in resolved
    assert repo.search(organism="e. coli").total_matched > 1000
