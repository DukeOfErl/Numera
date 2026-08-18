"""The corpus is supplied, never bundled."""

from __future__ import annotations

import pytest

from bionumbers_ask.corpus import CorpusUnavailable, load

FIXTURE = "tests/fixtures/corpus_sample.jsonl"


@pytest.mark.parametrize("missing", [None, ""])
def test_no_path_is_refused_rather_than_defaulted(missing):
    with pytest.raises(CorpusUnavailable) as caught:
        load(missing)
    # The message must say why, since there is nothing to fall back to.
    assert "not bundled" in str(caught.value)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(CorpusUnavailable):
        load(tmp_path / "absent.jsonl")


def test_an_empty_file_is_refused(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CorpusUnavailable):
        load(empty)


def test_entries_load_with_values_ranges_and_quotations():
    entries = load(FIXTURE)
    assert len(entries) == 6
    by_id = {e.bnid: e for e in entries}
    assert by_id[100002].value_display == "1.0–1.1"
    assert by_id[100010].value_display == "5.0"
    assert "1.0 and 1.1" in by_id[100002].quotation_text


def test_unknown_fields_do_not_prevent_loading(tmp_path):
    line = '{"bnid": 1, "property": "p", "units": "u", "some_future_column": 7}\n'
    path = tmp_path / "extra.jsonl"
    path.write_text(line, encoding="utf-8")
    assert load(path)[0].bnid == 1
