import pytest

from bionumbers_ingest.parsing import iter_rows

HEADERS = [
    "bion_id",
    "Properties",
    "Organism",
    "Value",
    "Range",
    "Units",
    "Reference",
    "Reference PubMed ID",
    "Primary Source",
    "Primary Source PubMed ID",
    "Measurement Method",
    "Comments",
    "Entered By",
    "Keywords",
]


def test_headers_and_row_count(sample_html):
    rows = list(iter_rows(sample_html))
    # 7 rows follow the header: six records and one trailing padding row. The
    # reader yields every one of them; deciding which are data is cleaning's job.
    assert len(rows) == 7
    assert list(rows[0].keys()) == HEADERS


def test_escaped_markup_survives_the_read(sample_html):
    rows = list(iter_rows(sample_html))
    # The export's injected markup is HTML-escaped, and it must reach cleaning in
    # that form. A reader that unescaped here would hand cleaning a live tag and
    # hide which of the two forms the source actually used.
    assert "&lt;IMG SRC=" in rows[0]["Keywords"]
    assert "&gt;" in rows[0]["Keywords"]
    assert "<IMG" not in rows[0]["Keywords"]


def test_entities_are_not_converted(sample_html):
    rows = list(iter_rows(sample_html))
    # Same contract for character references: cleaning unescapes, not the reader.
    assert "&#181;" in rows[0]["Units"]
    assert "µ" not in rows[0]["Units"]


def test_text_marker_apostrophe_survives_the_read(sample_html):
    rows = list(iter_rows(sample_html))
    assert rows[0]["Range"] == "'1.94 to 2.72"
    assert rows[1]["Range"].startswith("'")


def test_padding_row_is_yielded_not_dropped(sample_html):
    rows = list(iter_rows(sample_html))
    assert rows[-1]["bion_id"] == "&nbsp;"


@pytest.mark.parametrize("limit,expected", [(1, 1), (2, 2), (7, 7), (99, 7)])
def test_limit(sample_html, limit, expected):
    assert len(list(iter_rows(sample_html, limit=limit))) == expected


@pytest.mark.parametrize("limit", [None, 0])
def test_no_limit_reads_every_row(sample_html, limit):
    assert len(list(iter_rows(sample_html, limit=limit))) == 7


def test_a_row_spanning_a_chunk_boundary_is_read_whole(sample_html, monkeypatch):
    # The streaming read is where a row can be torn in half. Every row in the
    # real export is 14 cells, so a short row here would mean the parser lost
    # part of one across a chunk edge.
    from bionumbers_ingest.parsing import html_table

    monkeypatch.setattr(html_table, "_CHUNK", 64)
    rows = list(iter_rows(sample_html))
    assert len(rows) == 7
    assert all(list(r.keys()) == HEADERS for r in rows)
    assert rows[0]["Range"] == "'1.94 to 2.72"


def test_a_row_with_the_wrong_cell_count_is_an_error(tmp_path):
    # All 14,298 rows of the published export carry exactly 14 cells, so a
    # mismatch is malformation. Zipping headers against a short row would drop
    # the missing columns silently, which is the failure this project cannot
    # afford: the record would look complete and be missing a field.
    bad = tmp_path / "short_row.html"
    bad.write_text(
        "<table><tr><td>a</td><td>b</td><td>c</td></tr><tr><td>1</td><td>2</td></tr></table>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="2 cells.*3 columns"):
        list(iter_rows(bad))


def test_a_row_with_too_MANY_cells_is_also_an_error(tmp_path):
    # The long direction, which a `<` comparison would let through: an extra cell
    # is dropped by zip rather than reported, so the record looks complete while
    # a column has silently shifted. Found by fault seeding — the short-row test
    # above passes even when the guard only catches short rows.
    bad = tmp_path / "long_row.html"
    bad.write_text(
        "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="3 cells.*2 columns"):
        list(iter_rows(bad))


def test_a_truncated_table_is_an_error_not_a_short_corpus(tmp_path):
    # An interrupted download yields every row it managed to parse and stops. That
    # is the failure the writer's own design calls unaffordable: a short corpus
    # loads cleanly and is missing entries nobody can enumerate.
    cut = tmp_path / "truncated.html"
    cut.write_text(
        "<table><tr><td>a</td><td>b</td></tr>"
        "<tr><td>1</td><td>2</td></tr>"
        "<tr><td>3</td><td>4",  # ends mid-row
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="truncated"):
        list(iter_rows(cut))


def test_a_well_formed_table_is_not_reported_as_truncated(sample_html):
    assert len(list(iter_rows(sample_html))) == 7


def test_expected_headers_are_checked_when_the_caller_supplies_them(sample_html):
    from bionumbers_ingest.model import EXPECTED_HEADERS

    assert len(list(iter_rows(sample_html, expect_headers=EXPECTED_HEADERS))) == 7


def test_a_renamed_column_is_an_error_rather_than_an_empty_corpus(tmp_path):
    # Renaming the identifier column makes every row fail the is-it-data test, so
    # the run writes an empty corpus and reports no error at all.
    renamed = tmp_path / "renamed.html"
    renamed.write_text(
        "<table><tr><td>id</td><td>Value</td></tr><tr><td>1</td><td>2</td></tr></table>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not the ones expected"):
        list(iter_rows(renamed, expect_headers=("bion_id", "Value")))


def test_an_end_tag_inside_a_cell_reaches_cleaning(tmp_path):
    # Dropping it joined the words either side AND left no tag for cleaning to
    # find, so a contaminated cell raised no markup flag at all.
    src = tmp_path / "endtag.html"
    src.write_text(
        "<table><tr><td>bion_id</td><td>Comments</td></tr>"
        "<tr><td>1</td><td>alpha</b>beta</td></tr></table>",
        encoding="utf-8",
    )
    assert list(iter_rows(src))[0]["Comments"] == "alpha</b>beta"


def test_a_reordered_header_is_accepted_because_fields_are_read_by_name(tmp_path):
    src = tmp_path / "reordered.html"
    src.write_text(
        "<table><tr><td>Value</td><td>bion_id</td></tr><tr><td>1</td><td>2</td></tr></table>",
        encoding="utf-8",
    )
    rows = list(iter_rows(src, expect_headers=("bion_id", "Value")))
    assert rows == [{"Value": "1", "bion_id": "2"}]
