"""A harvested paper's reference, in Chicago author-date from its CSL-JSON (ADR-1640).

Expected shapes come from the Chicago Manual of Style, 18th edition, author-date reference lists
(surname first for the first author only, "and" before the last, the year after the names, the
title in quotes; seven or more authors given as the first three and "et al."), and from the two
departures ADR-1640 records -- not from running the formatter.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
import store_double

from numera_ask import entries_table, references, store_corpus
from numera_ask.repository import CorpusRepository
from numera_ask.tools import ToolBudget, build_tools
from numera_ask.trace import start_question


def _chicago(**changes) -> str | None:
    record = {**store_double.ACTIN_CSL, **changes}
    return references.chicago(json.dumps({k: v for k, v in record.items() if v is not None}))


def test_a_reference_reads_in_chicago_author_date():
    drawn = _chicago()
    assert drawn.startswith("Inventa, A., B. C. Fictor, and C. Madeup. 2009. ")
    assert "Journal of Invented Biology 12 (3)" in drawn
    assert drawn.endswith("https://doi.org/10.0000/invented.1.")


def test_the_title_stays_as_the_paper_wrote_it():
    """Title case would print `Cdc15` and `S. Pombe` -- a gene and a species misnamed."""
    assert "“Invented actin in S. pombe cdc15 mutants.”" in _chicago()


def test_seven_authors_are_the_first_three_and_et_al():
    many = [{"family": f"Author{i}", "given": "Zed"} for i in range(1, 8)]
    drawn = _chicago(author=many)
    assert drawn.startswith("Author1, Z., Z. Author2, Z. Author3, et al. 2009.")
    assert "Author4" not in drawn


@pytest.mark.parametrize(
    "record",
    [
        "",
        "not json",
        json.dumps({**store_double.ACTIN_CSL, "author": None}),
        json.dumps({k: v for k, v in store_double.ACTIN_CSL.items() if k != "author"}),
        # A collaboration's name: citeproc-py 0.11.1 does not support literal names.
        json.dumps({**store_double.ACTIN_CSL, "author": [{"literal": "Invented Consortium"}]}),
        # No type: citeproc raised UnboundLocalError. A date in strings, or only `raw`: it
        # printed "Edition." where the year belongs (code review, 2026-10-17).
        json.dumps({k: v for k, v in store_double.ACTIN_CSL.items() if k != "type"}),
        json.dumps({**store_double.ACTIN_CSL, "issued": {"date-parts": [["2009", "5"]]}}),
        json.dumps({**store_double.ACTIN_CSL, "issued": {"raw": "2009-05"}}),
    ],
)
def test_a_record_that_cannot_be_formatted_faithfully_is_not(record):
    assert references.chicago(record) is None


def _rows(path, ids):
    repo = CorpusRepository(store_corpus.load(path))
    return repo, {row.entry_id: row for row in entries_table.rows_for(repo, ids, ids)}


def test_the_table_shows_chicago_where_the_store_has_the_record(tmp_path):
    path = store_double.with_references(
        store_double.build(tmp_path / "s.sqlite"),
        {store_double.ACTIN.pmcid: store_double.ACTIN_CSL},
    )
    _, rows = _rows(path, ("PMC1000001-1", "PMC2000002-1", store_double.CURATED_ID))
    assert rows["PMC1000001-1"].reference == _chicago()
    # A paper the store has no record for, and a curated entry, keep the reference as stored.
    assert rows["PMC2000002-1"].reference.startswith("Invented optics paper (2015)")
    assert rows[store_double.CURATED_ID].reference == "Invented reference"


def test_a_store_without_the_column_still_loads_with_plain_references(tmp_path):
    """A store written before `add-paper-references`: the table as it was, with no column."""
    path = store_double.build(tmp_path / "s.sqlite")
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(review_paper)")}
        if "csl_json" in columns:
            conn.execute("ALTER TABLE review_paper DROP COLUMN csl_json")
    _, rows = _rows(path, ("PMC1000001-1",))
    assert rows["PMC1000001-1"].reference.startswith("Invented actin paper (2009)")


def test_the_model_is_never_handed_the_authors(tmp_path):
    """Told to name no paper, it is not given the names to write (ADR-1640)."""
    path = store_double.with_references(
        store_double.build(tmp_path / "s.sqlite"),
        {store_double.ACTIN.pmcid: store_double.ACTIN_CSL},
    )
    repo = CorpusRepository(store_corpus.load(path))
    tools = {
        t.name: t for t in build_tools(repo, start_question("dev"), lambda e: None, ToolBudget(99))
    }
    shown = tools["get_entry"].invoke({"entry_id": "PMC1000001-1"})
    shown += tools["search_entries"].invoke({"property": "F-actin"})
    for author in ("Inventa", "Fictor", "Madeup", "Journal of Invented Biology"):
        assert author not in shown, author


def test_a_record_citeproc_raises_on_keeps_the_plain_reference(monkeypatch):
    def raises(*args, **kwargs):
        raise KeyError("something citeproc did not expect")

    monkeypatch.setattr(references, "CitationStylesBibliography", raises)
    assert references.chicago(json.dumps(store_double.ACTIN_CSL)) is None
