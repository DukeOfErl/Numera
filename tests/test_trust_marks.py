"""Stars beside citations and in the entries table, drawn by the application (ADR-1630).

Built over the invented store in `store_double`, whose decisions are stated there; expected stars
come from the scale in design D6, not from running the code.
"""

from __future__ import annotations

import dataclasses
import re
from html.parser import HTMLParser

import pytest
import store_double

from numera_ask import cli, entries_table, objections, store_corpus, trust_marks, web
from numera_ask.events import Answer, AnswerEntries
from numera_ask.repository import CorpusRepository
from numera_ask.tools import ToolBudget, build_tools
from numera_ask.trace import start_question
from numera_validator.tiers import Tier, Trust

#: PMC1000001-1: scientist (simulated), disputed. -4: nobody approved, disputed. -2: AI.
#: `sim` after the stars, then the caution (ADR-1850's order, the canvas's).
SCIENTIST_SIMULATED_DISPUTED = "★★★☆☆ sim ⚠️"
NOBODY_DISPUTED = "☆☆☆☆☆ ⚠️"


@pytest.fixture
def store_repo(tmp_path):
    return CorpusRepository(store_corpus.load(store_double.build(tmp_path / "s.sqlite")))


@pytest.mark.parametrize(
    "trust, drawn",
    [
        (Trust(Tier.CURATED), "★★★★★"),
        (Trust(Tier.SENIOR_SCIENTIST), "★★★★☆"),
        (Trust(Tier.SCIENTIST, simulated=True), "★★★☆☆ sim"),
        (Trust(Tier.STUDENT, disputed=True), "★★☆☆☆ ⚠️"),
        (Trust(Tier.AI), "★☆☆☆☆"),
        (Trust(Tier.NONE), "☆☆☆☆☆"),
        (None, ""),
    ],
)
def test_each_tier_draws_on_one_scale_with_its_marks(trust, drawn):
    assert trust_marks.stars(trust) == drawn


def test_the_legend_explains_only_the_marks_shown():
    assert trust_marks.legend([None, None]) == [], "a corpus file explains nothing"
    plain = trust_marks.legend([Trust(Tier.CURATED)])
    assert plain == [trust_marks.SCALE_LEGEND]
    both = trust_marks.legend([Trust(Tier.SCIENTIST, simulated=True, disputed=True)])
    assert both == [
        trust_marks.SCALE_LEGEND,
        trust_marks.SIMULATED_LEGEND,
        trust_marks.DISPUTED_LEGEND,
    ]


# -- beside a citation --------------------------------------------------------


def test_the_terminal_draws_stars_after_each_citation_and_leaves_the_legend_to_the_table(
    store_repo,
):
    text = cli.render(Answer(question_id="q", text="488 µM [[PMC1000001-1]]."), store_repo)
    assert f"[[PMC1000001-1]] {SCIENTIST_SIMULATED_DISPUTED}." in text
    # Said once, under the entries table (the user's call, 2026-10-16), not under the answer too.
    assert trust_marks.SCALE_LEGEND not in text
    table = entries_table.render(_rows(store_repo, ("PMC1000001-1",)))
    flat = " ".join(line.strip() for line in table.splitlines())  # legend lines wrap to the rule
    assert trust_marks.SIMULATED_LEGEND in flat
    # A terminal cannot open a cell, so its dispute line points at the list, not a double click.
    assert trust_marks.DISPUTED_LEGEND_TERMINAL in flat
    assert "Double click" not in flat


def test_a_group_citing_several_entries_names_each_beside_its_stars(store_repo):
    text = cli.render(Answer(question_id="q", text="[[PMC1000001-1, 100001]]"), store_repo)
    assert (
        f"[[PMC1000001-1, 100001]] (PMC1000001-1 {SCIENTIST_SIMULATED_DISPUTED}; 100001 ★★★★★)"
        in text
    )


def test_a_corpus_file_answer_draws_as_it_did(repo):
    """No tier, no stars and no legend: the answer is printed exactly as before this change."""
    assert (
        cli.render(Answer(question_id="q", text="1 μm [[100002]]"), repo) == "\n1 μm [[100002]]\n"
    )


def test_stars_the_model_wrote_do_not_become_the_tier(store_repo):
    """The model is told not to write stars; if it does, the drawn ones still follow the citation,
    read from the store, and the model's own are left as text it wrote."""
    text = cli.render(Answer(question_id="q", text="[[PMC1000001-4]] ★★★★★"), store_repo)
    assert f"[[PMC1000001-4]] {NOBODY_DISPUTED} ★★★★★" in text


def test_a_citation_is_a_pill_with_its_number_and_its_stars(store_repo):
    """ADR-1850: the number, then the stars, `sim` and the caution; the identifier on hover."""
    item = web.item_for(
        Answer(question_id="q", text="488 µM [[PMC1000001-1]] and 2 µm [[100001]]."), store_repo
    )
    drawn = web.answer_markdown(item.text, dict(item.stars), {"PMC1000001-1": 4, "100001": 7})
    assert re.sub(r"<[^>]+>", "", drawn) == (
        f"488 µM 4 {SCIENTIST_SIMULATED_DISPUTED} and 2 µm 7 ★★★★★."
    )
    assert 'title="PMC1000001-1"' in drawn and 'title="BNID 100001"' in drawn
    assert "[[" not in drawn and "<sup" not in drawn


def test_a_group_citing_several_entries_is_a_pill_for_each(store_repo):
    item = web.item_for(Answer(question_id="q", text="[[PMC1000001-1, 100001]]"), store_repo)
    drawn = web.answer_markdown(item.text, dict(item.stars), {"PMC1000001-1": 1, "100001": 2})
    assert drawn.count('class="sn-pill"') == 2


def test_an_identifier_the_session_has_not_numbered_is_left_as_written():
    """`[[Table 1]]` and an id the corpus does not hold get no pill; one beside them still does."""
    drawn = web.answer_markdown("8 nm [[100002]], [[999999]], [[Table 1]]", {}, {"100002": 1})
    assert drawn.count('class="sn-pill"') == 1
    assert "[[999999]]" in drawn and "[[Table 1]]" in drawn and "[[100002]]" not in drawn


def test_a_group_that_is_not_a_citation_is_not_drawn_as_one():
    assert web.answer_markdown("see [[Table 1]]") == "see [[Table 1]]"


def test_a_corpus_file_pill_is_the_number_alone(repo):
    item = web.item_for(Answer(question_id="q", text="1 μm [[100002]]"), repo)
    assert item.stars == ()
    drawn = web.answer_markdown(item.text, dict(item.stars), {"100002": 3})
    assert re.sub(r"<[^>]+>", "", drawn) == "1 μm 3"


def test_the_simulated_mark_is_sim_not_a_hash():
    """`#` collided with papers' "#1–#4" ring labels beside a citation (ADR-1850)."""
    assert trust_marks.SIMULATED == "sim"
    assert "#" not in trust_marks.stars(Trust(Tier.SCIENTIST, simulated=True))
    assert trust_marks.SIMULATED_LEGEND.startswith("sim")


def test_a_tier_is_said_in_words_where_the_entry_is_opened():
    assert trust_marks.tier_words(Trust(Tier.CURATED)) == "Curated in BioNumbers"
    assert trust_marks.tier_words(Trust(Tier.AI)) == "Approved by an AI reviewer"
    assert (
        trust_marks.tier_words(Trust(Tier.SCIENTIST, simulated=True, disputed=True))
        == "Approved by a scientist (simulated review); a reviewer objected"
    )
    assert trust_marks.tier_words(Trust(Tier.NONE)) == "Not yet approved by any reviewer"
    assert trust_marks.tier_words(None) == ""


# -- in the entries table -----------------------------------------------------


def _rows(repo, cited):
    return entries_table.rows_for(repo, cited, cited)


def table_cells(markup: str) -> list[list[str]]:
    """The evidence list's rows as cell texts, tags stripped: the header row first."""

    class Cells(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: list[list[str]] = []
            self.cell: list[str] | None = None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.rows.append([])
            elif tag in ("td", "th"):
                self.cell = []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.cell is not None:
                self.rows[-1].append(" ".join("".join(self.cell).split()))
                self.cell = None

        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)

    parsed = Cells()
    parsed.feed(markup)
    return parsed.rows


def test_the_evidence_list_is_number_entry_value_trust_id(store_repo):
    """ADR-1850: the canvas's five columns; units with the value, the marks after it."""
    rows = _rows(store_repo, ("PMC1000001-2", "PMC1000001-4"))
    head, calculated, uncertain = table_cells(
        web.evidence_html(rows, {"PMC1000001-2": 3, "PMC1000001-4": 5})
    )
    assert head == ["#", "Entry", "Value", "Trust", "ID"]
    # -2 records no method in the fixture, so it carries that mark as well as the calculated one.
    assert calculated[0] == "3"
    assert calculated[1].startswith("Filament spacing"), "the property leads its cell"
    assert calculated[2] == f"7.1 ± 0.4 nm{entries_table.NO_METHOD}{entries_table.CALCULATED}"
    assert calculated[3] == "★☆☆☆☆"
    assert calculated[4] == "PMC1000001-2"
    # The paper's own words, read or not; its marks after them.
    assert uncertain[2].startswith("10–20 s") and entries_table.READING_UNCERTAIN in uncertain[2]
    assert uncertain[3] == NOBODY_DISPUTED
    legend = web._legend(rows)
    assert entries_table.CALCULATED_LEGEND in legend
    assert entries_table.READING_UNCERTAIN_LEGEND in legend
    # The trust scale is pinned once for the page, not repeated under each list.
    assert trust_marks.SCALE_LEGEND not in legend


def test_the_organism_and_first_author_year_sit_under_the_property(tmp_path):
    path = store_double.with_references(
        store_double.build(tmp_path / "s.sqlite"),
        {store_double.ACTIN.pmcid: store_double.ACTIN_CSL},
    )
    repo = CorpusRepository(store_corpus.load(path))
    _, row = table_cells(web.evidence_html(_rows(repo, ("PMC1000001-1",)), {"PMC1000001-1": 1}))
    assert row[1].startswith("F-actin concentration")
    assert row[1].endswith("mouse · Inventa et al. 2009")


def test_a_cell_is_escaped_and_a_value_never_breaks(store_repo):
    rows = _rows(store_repo, ("PMC1000001-2",))
    markup = web.evidence_html([dataclasses.replace(rows[0], property="<b>bold</b>")], {})
    assert "<b>bold</b>" not in markup and "&lt;b&gt;bold&lt;/b&gt;" in markup
    assert 'class="sn-v"' in markup and "\n" not in markup, "one line: nothing read as markdown"


def test_a_corpus_file_evidence_list_has_no_trust_column(repo):
    (head, row) = table_cells(web.evidence_html(_rows(repo, (100002,)), {"100002": 1}))
    assert head == ["#", "Entry", "Value", "ID"]
    assert row[3] == "BNID 100002"


def test_an_uncertain_reading_shows_the_paper_s_words_in_the_value_cell(store_repo):
    """No number was taken from `10–20`, and the paper's words are still what the cell shows."""
    _, row = table_cells(web.evidence_html(_rows(store_repo, ("PMC1000001-4",)), {}))
    assert row[2].startswith("10–20")
    assert entries_table.NO_SCALAR not in row[2]


def test_the_terminal_table_puts_the_marks_first_and_trust_before_the_id(store_repo):
    text = entries_table.render(_rows(store_repo, ("PMC1000001-2",)))
    header = text.splitlines()[0]
    assert header.index("Units") < header.index("Trust") < header.index("ID")
    row = text.splitlines()[2]
    assert row.startswith(entries_table.NO_METHOD + entries_table.CALCULATED + " ")
    assert "★☆☆☆☆" in row
    assert entries_table.CALCULATED_LEGEND in text
    assert trust_marks.SCALE_LEGEND.split(" · ")[0] in text


def test_a_corpus_file_terminal_table_has_no_trust_column(repo):
    text = entries_table.render(_rows(repo, (100002,)))
    assert "Trust" not in text.splitlines()[0]
    assert "★" not in text and "☆" not in text


def test_the_entries_behind_a_store_answer_reach_the_page_with_their_stars(store_repo):
    event = AnswerEntries(
        question_id="q", cited=("PMC1000001-1",), retrieved=("PMC1000001-1", "PMC2000002-1")
    )
    table = web.item_for(event, store_repo).table
    trust = {row.entry_id: row.stars for row in table.rows}
    assert trust == {"PMC1000001-1": SCIENTIST_SIMULATED_DISPUTED, "PMC2000002-1": "☆☆☆☆☆"}


def test_the_terminal_shows_a_label_whole_since_it_cannot_open_a_cell(store_repo):
    """Cut to the BNID width, `PMC1000001-1` and `PMC1000001-1.2` both read `PMC100…`."""
    text = entries_table.render(_rows(store_repo, ("PMC1000001-1", "PMC1000001-1.2")))
    assert "PMC1000001-1 " in text and "PMC1000001-1.2" in text
    rule = text.splitlines()[1]
    assert all(len(line) <= len(rule) for line in text.splitlines()[:6])


# -- what objecting reviewers said (ADR-1630) ---------------------------------

A = f"{store_double.RUN_A}-{store_double.ACTIN.pmcid}"


@pytest.fixture
def store_with_objections(tmp_path):
    path = store_double.build(tmp_path / "s.sqlite")
    repo = CorpusRepository(store_corpus.load(path))
    objections.attach(repo, objections.load(path))
    return repo


def test_the_objections_are_the_decisions_that_disputed_an_entry(tmp_path):
    """Per `store_double.build`: -1 drew an issue from a student, -4 a student's disapproval; the
    approvals and the undecided optics value draw nothing."""
    found = objections.load(store_double.build(tmp_path / "s.sqlite"))
    assert found == {
        f"{A}-1-item": (f"student: {store_double.REVIEWER_ISSUE}",),
        f"{A}-4-item": (f"student: {store_double.REVIEWER_COMMENT}",),
    }


def test_the_trust_cell_carries_the_stars_alone_and_the_legend_says_open_the_entry(
    store_with_objections,
):
    """ADR-1850: the objections moved to the opened entry; the cell keeps the stars and caution."""
    rows = _rows(store_with_objections, ("PMC1000001-1", "PMC1000001-2"))
    assert rows[0].objections == (f"student: {store_double.REVIEWER_ISSUE}",)
    _, disputed, approved = table_cells(web.evidence_html(rows, {}))
    assert disputed[3] == SCIENTIST_SIMULATED_DISPUTED
    assert store_double.REVIEWER_ISSUE not in web.evidence_html(rows, {})
    assert approved[3] == "★☆☆☆☆"
    assert trust_marks.DISPUTED_LEGEND in trust_marks.FULL_LEGEND
    assert trust_marks.DISPUTED_LEGEND == (
        "⚠️ : a reviewer objected to this entry. Open the entry to read why"
    )


def test_the_terminal_lists_the_objections_under_its_table(store_with_objections):
    text = entries_table.render(_rows(store_with_objections, ("PMC1000001-4",)))
    assert "objections raised:" in text
    assert f"PMC1000001-4  student: {store_double.REVIEWER_COMMENT}" in text


def test_the_model_never_sees_an_objection(store_with_objections):
    """The objections are attached for the tables; the tools still hand the model none of them."""
    tools = {
        t.name: t
        for t in build_tools(
            store_with_objections, start_question("dev"), lambda e: None, ToolBudget(99)
        )
    }
    shown = tools["get_entry"].invoke({"entry_id": "PMC1000001-1"})
    shown += tools["search_entries"].invoke({"property": "F-actin"})
    for marker in store_double.NEVER_SHOWN:
        assert marker not in shown, marker


def test_a_corpus_file_has_no_objections(repo):
    assert all(row.objections == () for row in _rows(repo, (100002,)))
