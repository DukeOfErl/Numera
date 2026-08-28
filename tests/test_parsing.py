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
