"""The JATS reader, checked against XML read by hand.

Every expected string below was copied out of the fixture files, not out of the reader's output:
a table header, a paragraph's opening words, the identifiers in the front matter. Where a test
needs the id of a passage it searches for the passage by text, so that the id scheme stays the
reader's business and a renumbering cannot make a test assert the wrong container.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bionumbers.jats import Document, JatsUnreadable, Passage, read_jats, render_for_model
from bionumbers.records import Location

EUROPEPMC = Path(__file__).parent / "fixtures" / "europepmc"
HAND_WRITTEN = Path(__file__).parent / "fixtures" / "jats"


def _read(directory: Path, name: str) -> Document:
    return read_jats((directory / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def coxiella() -> Document:
    """PMC13248727: research article with a DOCTYPE, a `<back>`, three XHTML tables, both
    micro-sign code points and a MATERIALS AND METHODS section."""
    return _read(EUROPEPMC, "fulltext_PMC13248727.xml")


@pytest.fixture(scope="module")
def brief_report() -> Document:
    """PMC13340094: a brief report with no `<back>` and no methods section."""
    return _read(EUROPEPMC, "fulltext_PMC13340094.xml")


@pytest.fixture(scope="module")
def replisome() -> Document:
    """PMC2288635: abstract titled "Summary", methods titled "Experimental Procedures"."""
    return _read(EUROPEPMC, "fulltext_PMC2288635.xml")


def holding(doc: Document, phrase: str, kind: str | None = None) -> Passage:
    for passage in doc.passages:
        if phrase in passage.text and (kind is None or passage.kind == kind):
            return passage
    raise AssertionError(f"no passage of {doc.pmcid or doc.title!r} holds {phrase!r}")


# --- front matter -----------------------------------------------------------------------------


def test_identifiers_and_year_come_from_the_front_matter(coxiella):
    assert coxiella.pmcid == "PMC13248727"
    assert coxiella.pmid == "42053426"
    assert coxiella.doi == "10.1128/iai.00007-26"
    assert coxiella.year == 2026
    assert coxiella.title.startswith("Quantitative three-dimensional imaging of Coxiella burnetii")


def test_article_type_is_read_off_the_root(coxiella, brief_report):
    assert coxiella.article_type == "research-article"
    assert brief_report.article_type == "brief-report"


def test_a_bare_pmc_number_is_restated_in_pmc_form():
    doc = _read(HAND_WRITTEN, "paragraph_wrapping_table.xml")
    assert doc.pmcid == "PMC2"


def test_a_document_without_identifiers_reports_them_empty():
    doc = _read(HAND_WRITTEN, "spanning_headers.xml")
    assert (doc.pmcid, doc.pmid, doc.doi, doc.year) == ("", "", "", None)


# --- the methods gate -------------------------------------------------------------------------


def test_a_materials_and_methods_section_counts_as_methods(coxiella):
    assert coxiella.has_methods_section is True


def test_experimental_procedures_counts_as_methods(replisome):
    assert replisome.has_methods_section is True


def test_the_back_less_brief_report_reads_and_has_no_methods_section(brief_report):
    # Its body holds sections titled "Supplementary Material" and "Supplementary Materials",
    # which is the case that would admit it on the word "materials" alone.
    assert brief_report.passages
    assert brief_report.has_methods_section is False


# --- paragraphs and sections ------------------------------------------------------------------


def test_a_paragraph_carries_every_enclosing_section_title(coxiella):
    passage = holding(coxiella, "We previously used cryo-electron tomography (cryo-ET)")
    assert passage.kind == "p"
    assert passage.section_path == (
        "RESULTS",
        "FIB-SEM enables quantitative three-dimensional visualization of C. burnetii infection",
    )


def test_section_titles_are_passages_of_their_own(coxiella):
    passage = holding(coxiella, "MATERIALS AND METHODS", kind="title")
    assert passage.text == "MATERIALS AND METHODS"
    assert passage.section_path == ()


def test_the_abstract_paragraphs_are_passages_under_the_abstract_title(replisome):
    passage = holding(replisome, "A prevalent view of DNA replication has been that it is")
    assert passage.kind == "p"
    assert passage.section_path == ("Summary",)


def test_nothing_is_read_from_back(coxiella):
    # The acknowledgements live in `<back>`, as prose `<p>` elements that would otherwise read
    # like any other paragraph.
    assert "We thank Jennifer Aronson for critical reading" not in coxiella.text()


def test_a_bibliographic_xref_becomes_a_citation_token(coxiella):
    passage = holding(coxiella, "is the causative agent of Q fever, a zoonotic disease")
    assert "persistent infection ([ref 1])." in passage.text


def test_table_and_figure_xrefs_keep_their_visible_text(coxiella):
    passage = holding(coxiella, "occupied up to ~60% of the total imaged volume")
    assert "(Fig. 1 , 2 and Table 1)" in passage.text
    assert "[ref" not in passage.text.split("(Fig. 1 , 2")[1].split(")")[0]


def test_both_micro_signs_survive_unfolded(coxiella):
    # The paper writes the unit as U+03BC once and U+00B5 once in the same clause.
    passage = holding(coxiella, "the SCV is markedly shorter than the LCV")
    assert "0.2–0.5 μm vs ~1 µm" in passage.text


def test_whitespace_runs_collapse_and_inline_markup_vanishes(coxiella):
    passage = holding(coxiella, "We previously used cryo-electron tomography (cryo-ET)")
    assert "  " not in passage.text
    assert "<" not in passage.text
    assert "individual C. burnetii cells within CCVs" in passage.text


# --- tables -----------------------------------------------------------------------------------


def test_a_cell_resolves_to_its_headers_plus_its_text(coxiella):
    # TABLE 1, first body row: CCV 1 has 4 SCVs, 19 LCVs, 2 intermediates, 25 cells, 8.2 µm³.
    cell = holding(coxiella, "8.2", kind="td")
    assert cell.text == "8.2"
    assert cell.column_headers == ("Volume (µm³)",)
    assert cell.row_headers == ("1",)
    assert cell.section_path[-1] == "TABLE 1"
    assert cell.section_path[0] == "RESULTS"


def test_a_superscript_in_a_header_stays_a_superscript(coxiella):
    # `Volume (µm<sup>3</sup>)` in the fixture. Flattened to `m3)` it read as a different unit;
    # the reader now keeps the exponent as the character the paper printed.
    cell = holding(coxiella, "8.2", kind="td")
    assert cell.column_headers[0].endswith("m" + chr(0x00B3) + ")")


def test_an_exponent_in_a_value_keeps_its_meaning():
    """The 2026-09-21 review's finding 3, on a value rather than a header: `2.5 x 10<sup>8</sup>`
    must not become `2.5 x 108`, which is a different number that a wrong quote could match."""
    doc = _read(HAND_WRITTEN, "superscript_value.xml")
    cell = holding(doc, "2.5", kind="td")
    eight = chr(0x2078)
    assert cell.text == f"2.5 × 10{eight}"
    assert "108" not in doc.text()
    paragraph = holding(doc, "Cultures reached", kind="p")
    assert f"2.5 × 10{eight} cells mL{chr(0x207B)}{chr(0x00B9)}" in paragraph.text


def test_a_superscript_that_is_not_a_number_is_marked_with_a_caret():
    """A footnote letter has no superscript character; a caret says it was raised rather than
    letting `elsewherea` read as a word."""
    doc = _read(HAND_WRITTEN, "superscript_value.xml")
    paragraph = holding(doc, "Cultures reached", kind="p")
    assert paragraph.text.endswith("as compiled elsewhere^a.")
    cell = holding(doc, "2.5", kind="td")
    assert cell.column_headers[0].endswith(")^a")


def test_the_row_label_cell_is_a_passage_with_no_row_header(coxiella):
    cell = holding(coxiella, "8.2", kind="td")
    label = coxiella.passage(cell.id[: cell.id.rindex("c")] + "c1")
    assert label is not None
    assert label.text == "1"
    assert label.row_headers == ()
    assert label.column_headers == ("CCV",)


def test_a_table_caption_is_a_passage_under_the_table_label(coxiella):
    caption = holding(coxiella, "Statistics of the persistent infection", kind="caption")
    assert caption.section_path[-1] == "TABLE 1"


def test_a_table_without_thead_has_no_column_headers_and_no_special_first_row():
    doc = _read(HAND_WRITTEN, "table_without_thead.xml")
    glucose = holding(doc, "39 ± 1", kind="td")
    assert glucose.column_headers == ()
    assert glucose.row_headers == ("Glucose",)
    acetate = holding(doc, "55 ± 2", kind="td")
    assert acetate.row_headers == ("Acetate",)
    # The first row is data like any other, so the label cell of row 1 is itself a passage.
    assert holding(doc, "Glucose", kind="td").row_headers == ()


def test_a_paragraph_wrapping_a_table_does_not_repeat_the_cells():
    doc = _read(HAND_WRITTEN, "paragraph_wrapping_table.xml")
    paragraph = holding(doc, "Doubling times are given below.", kind="p")
    assert paragraph.text == (
        "Doubling times are given below. The glucose figure agrees with earlier work."
    )
    cell = holding(doc, "39 ± 1", kind="td")
    assert cell.row_headers == ("Glucose",)
    assert cell.column_headers == ("Doubling time (min)",)
    assert cell.section_path == ("Results", "Table 1")


def test_spanning_headers_are_expanded_across_the_columns_and_rows_they_cover():
    doc = _read(HAND_WRITTEN, "spanning_headers.xml")
    first = holding(doc, "39", kind="td")
    assert first.column_headers == ("Doubling time (min)", "Glucose")
    assert first.row_headers == ("MG1655",)
    second_row = holding(doc, "57", kind="td")
    assert second_row.column_headers == ("Doubling time (min)", "Acetate")
    # The row header spans two rows, so the second row is headed by it too rather than by its
    # own first cell.
    assert second_row.row_headers == ("MG1655",)
    assert holding(doc, "41", kind="td").row_headers == ("MG1655",)


# --- figures and supplementary material -------------------------------------------------------


def test_a_figure_caption_is_a_passage_under_the_figure_label(coxiella):
    caption = holding(coxiella, "FIB-SEM enables three-dimensional visualization of HeLa cells")
    assert caption.kind == "caption"
    assert caption.section_path[-1] == "Fig 1"


def test_supplementary_files_are_listed_once_each(coxiella, brief_report):
    assert coxiella.supplementary == (
        "iai.00007-26-s0001.docx",
        "iai.00007-26-s0002.docx",
        "iai.00007-26-s0003.mp4",
        "iai.00007-26-s0004.mp4",
        "iai.00007-26-s0005.mp4",
    )
    assert brief_report.supplementary == (
        "reviewer-comments.pdf",
        "spectrum.03512-25-s0001.xlsx",
        "spectrum.03512-25-s0002.pdf",
    )


# --- ids, lookup, rendering -------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "fulltext_PMC13248727.xml",
        "fulltext_PMC13340094.xml",
        "fulltext_PMC2288635.xml",
        "fulltext_PMC2132865.xml",
    ],
)
def test_ids_are_unique_and_identical_across_two_reads(name):
    xml = (EUROPEPMC / name).read_text(encoding="utf-8")
    first, second = read_jats(xml), read_jats(xml)
    ids = [passage.id for passage in first.passages]
    assert len(ids) == len(set(ids))
    assert ids == [passage.id for passage in second.passages]
    assert first == second


def test_every_kind_appears_in_the_table_bearing_paper(coxiella):
    assert {passage.kind for passage in coxiella.passages} == {"p", "td", "caption", "title"}


def test_passage_lookup_by_id(coxiella):
    cell = holding(coxiella, "8.2", kind="td")
    assert coxiella.passage(cell.id) is cell
    assert coxiella.passage("no-such-id") is None


def test_text_joins_every_passage_on_its_own_line(brief_report):
    assert brief_report.text().split("\n") == [p.text for p in brief_report.passages]


def test_render_is_deterministic_and_names_every_passage(coxiella):
    xml = (EUROPEPMC / "fulltext_PMC13248727.xml").read_text(encoding="utf-8")
    rendered = render_for_model(coxiella)
    assert rendered == render_for_model(read_jats(xml))
    lines = rendered.split("\n")
    assert len(lines) == len(coxiella.passages)
    for passage, line in zip(coxiella.passages, lines, strict=True):
        assert line.startswith(f"[{passage.id}] ")


def test_render_shows_a_cell_with_its_headers_first(coxiella):
    cell = holding(coxiella, "8.2", kind="td")
    line = next(
        line for line in render_for_model(coxiella).split("\n") if line.startswith(f"[{cell.id}]")
    )
    assert line.endswith(" :: row: 1 | column: Volume (µm³) | cell: 8.2")
    assert " > TABLE 1 :: " in line


def test_render_shows_a_paragraph_under_its_section_path(coxiella):
    passage = holding(coxiella, "We previously used cryo-electron tomography (cryo-ET)")
    line = next(
        line
        for line in render_for_model(coxiella).split("\n")
        if line.startswith(f"[{passage.id}]")
    )
    assert line == (
        f"[{passage.id}] RESULTS > FIB-SEM enables quantitative three-dimensional visualization "
        f"of C. burnetii infection :: {passage.text}"
    )


def test_location_carries_the_passage_fields(coxiella):
    cell = holding(coxiella, "8.2", kind="td")
    assert cell.location() == Location(
        passage_id=cell.id,
        section_path=cell.section_path,
        kind="td",
        row_headers=("1",),
        column_headers=("Volume (µm³)",),
    )


# --- refusals ---------------------------------------------------------------------------------


def test_a_non_article_root_is_unreadable():
    with pytest.raises(JatsUnreadable):
        read_jats('<?xml version="1.0"?><html><body><p>Not JATS</p></body></html>')


def test_unparseable_xml_is_unreadable():
    with pytest.raises(JatsUnreadable):
        read_jats("<article><body><p>never closed</body></article>")


def test_a_europe_pmc_error_body_is_unreadable():
    with pytest.raises(JatsUnreadable):
        read_jats("Internal Server Error")
