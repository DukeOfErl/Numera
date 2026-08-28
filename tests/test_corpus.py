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


# -- coercion and shape tolerance (found by review) ------------------------


def _write(tmp_path, *rows):
    import json

    path = tmp_path / "c.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_an_empty_string_value_does_not_blank_out_a_range(tmp_path):
    # A spreadsheet-derived corpus writes "" for an absent scalar. Uncoerced, ""
    # is not None, so the range would never be shown and the row would be blank.
    path = _write(
        tmp_path,
        {
            "bnid": 1,
            "property": "p",
            "units": "u",
            "value": "",
            "range_low": 1.94,
            "range_high": 2.72,
        },
    )
    entry = load(path)[0]
    assert entry.value is None
    assert entry.value_display == "1.94–2.72"


def test_a_numeric_string_becomes_a_number(tmp_path):
    path = _write(tmp_path, {"bnid": 1, "property": "p", "units": "u", "value": "1.94"})
    assert load(path)[0].value == 1.94


def test_a_half_open_range_is_not_rendered_with_none(tmp_path):
    path = _write(tmp_path, {"bnid": 1, "property": "p", "units": "u", "range_low": 0.5})
    assert load(path)[0].value_display == "at least 0.5"
    path = _write(tmp_path, {"bnid": 2, "property": "p", "units": "u", "range_high": 9.0})
    assert load(path)[0].value_display == "at most 9.0"


def test_a_range_whose_bounds_are_equal_reads_as_a_single_number(tmp_path):
    """1,403 of the corpus's entries store one measurement as a range with equal
    bounds. "400.0-400.0" invites a reader to look for a spread that is not there."""
    path = _write(
        tmp_path,
        {"bnid": 1, "property": "p", "units": "nm", "range_low": 400.0, "range_high": 400.0},
    )
    assert load(path)[0].value_display == "400.0"


def test_keywords_given_as_a_string_are_split_not_exploded(tmp_path):
    # tuple("cell size") would give one entry per character, making every
    # single-letter search match everything and every real term match nothing.
    path = _write(
        tmp_path, {"bnid": 1, "property": "p", "units": "u", "keywords": "cell size,diameter"}
    )
    assert load(path)[0].keywords == ("cell size", "diameter")


def test_amounts_are_validated_rather_than_misread():
    from bionumbers_ask.config import usd

    assert usd("0.50") == 500_000
    for bad in ("", "-0.50", "abc"):
        with pytest.raises(ValueError):
            usd(bad)


def test_a_malformed_line_is_refused_with_its_line_number(tmp_path):
    # Coverage found this branch unexercised: a corpus half-written or truncated
    # would otherwise fail somewhere less obvious than at load.
    path = tmp_path / "broken.jsonl"
    path.write_text(
        '{"bnid": 1, "property": "p", "units": "u"}\nnot json at all\n', encoding="utf-8"
    )
    with pytest.raises(CorpusUnavailable, match="line 2"):
        load(path)


def test_an_entry_with_no_value_at_all_says_so(tmp_path):
    path = _write(tmp_path, {"bnid": 1, "property": "p", "units": "u", "table_link": "http://x"})
    assert load(path)[0].value_display == "(no scalar value)"
