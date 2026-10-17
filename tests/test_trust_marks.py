"""Stars beside citations and in the entries table, drawn by the application (ADR-1630).

Built over the invented store in `store_double`, whose decisions are stated there; expected stars
come from the scale in design D6, not from running the code.
"""

from __future__ import annotations

import re

import pytest
import store_double

from bionumbers.tiers import Tier, Trust
from scinumbers_ask import cli, entries_table, objections, store_corpus, trust_marks, web
from scinumbers_ask.events import Answer, AnswerEntries
from scinumbers_ask.repository import CorpusRepository
from scinumbers_ask.tools import ToolBudget, build_tools
from scinumbers_ask.trace import start_question

#: PMC1000001-1: scientist (simulated), disputed. -4: nobody approved, disputed. -2: AI.
SCIENTIST_SIMULATED_DISPUTED = "#★★★☆☆⚠️"
NOBODY_DISPUTED = "☆☆☆☆☆⚠️"


@pytest.fixture
def store_repo(tmp_path):
    return CorpusRepository(store_corpus.load(store_double.build(tmp_path / "s.sqlite")))


@pytest.mark.parametrize(
    "trust, drawn",
    [
        (Trust(Tier.CURATED), "★★★★★"),
        (Trust(Tier.SENIOR_SCIENTIST), "★★★★☆"),
        (Trust(Tier.SCIENTIST, simulated=True), "#★★★☆☆"),
        (Trust(Tier.STUDENT, disputed=True), "★★☆☆☆⚠️"),
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


def test_the_web_superscript_reads_a_label_and_carries_its_stars(store_repo):
    item = web.item_for(
        Answer(question_id="q", text="488 µM [[PMC1000001-1]] [[100001]]."), store_repo
    )
    drawn = web.answer_markdown(item.text, dict(item.stars))
    # The identifier is footnoted; the stars, `#` and `⚠️` are at the prose's size, outside it.
    sup = '<sup style="opacity: 0.6; font-size: 0.72em;">'
    assert (
        f"{sup}PMC1000001-1</sup> {SCIENTIST_SIMULATED_DISPUTED} {sup}100001</sup> ★★★★★." in drawn
    )
    footnoted = re.findall(r"<sup[^>]*>(.*?)</sup>", drawn)
    assert footnoted == ["PMC1000001-1", "100001"]
    assert "[[" not in drawn, "a label left as raw brackets"


def test_a_run_holding_a_group_that_is_not_a_citation_still_draws_the_ones_that_are():
    """`[[Table 1]]` stays as written; `[[100002]]` beside it is still a superscript."""
    drawn = web.answer_markdown("8 nm [[100002]], [[Table 1]]")
    assert ">100002</sup>" in drawn and "[[Table 1]]" in drawn
    assert "[[100002]]" not in drawn


def test_an_uncertain_reading_shows_the_paper_s_words_in_the_value_cell(store_repo):
    """No number was taken from `10–20`, and the paper's words are still what the cell shows."""
    (row,) = web._frame(_rows(store_repo, ("PMC1000001-4",)))
    assert row["Value"] == "10–20"
    assert entries_table.NO_SCALAR not in row[""]


def test_a_group_that_is_not_a_citation_is_not_drawn_as_one():
    assert "<sup" not in web.answer_markdown("see [[Table 1]]")
    assert web.answer_markdown("see [[Table 1]]") == "see [[Table 1]]"


def test_a_corpus_file_answer_item_carries_no_stars(repo):
    item = web.item_for(Answer(question_id="q", text="1 μm [[100002]]"), repo)
    assert item.stars == ()
    assert ">100002</sup>" in web.answer_markdown(item.text, dict(item.stars))


def test_the_simulated_mark_s_legend_line_is_not_drawn_as_a_heading():
    """It begins with `#`, which markdown reads as a heading."""
    assert trust_marks.SIMULATED_LEGEND.startswith("#")
    assert web.markdown_line(trust_marks.SIMULATED_LEGEND).startswith("\\#")
    assert web.markdown_line(trust_marks.SCALE_LEGEND) == trust_marks.SCALE_LEGEND


# -- in the entries table -----------------------------------------------------


def _rows(repo, cited):
    return entries_table.rows_for(repo, cited, cited)


def test_the_web_table_puts_the_marks_first_and_trust_before_the_id(store_repo):
    rows = _rows(store_repo, ("PMC1000001-2", "PMC1000001-4"))
    frame = web._frame(rows)
    assert list(frame[0]) == [
        "",
        "Property",
        "Organism",
        "Value",
        "Units",
        "Trust",
        "ID",
        "Reference",
    ]
    calculated, uncertain = frame
    # -2 records no method in the fixture, so it carries that mark as well.
    assert calculated[""] == entries_table.NO_METHOD + entries_table.CALCULATED
    assert calculated["Property"] == "Filament spacing", "the property holds only the property"
    assert calculated["Trust"] == "★☆☆☆☆"
    assert entries_table.READING_UNCERTAIN in uncertain[""]
    assert uncertain["Trust"] == NOBODY_DISPUTED
    legend = web._legend(rows)
    assert entries_table.CALCULATED_LEGEND in legend
    assert entries_table.READING_UNCERTAIN_LEGEND in legend
    assert trust_marks.SCALE_LEGEND in legend


def test_a_corpus_file_web_table_has_marks_but_no_trust_column(repo):
    frame = web._frame(_rows(repo, (100002,)))
    assert list(frame[0])[0] == ""
    assert "Trust" not in frame[0]


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


def test_the_web_trust_cell_carries_the_objections_after_the_stars(store_with_objections):
    rows = _rows(store_with_objections, ("PMC1000001-1", "PMC1000001-2"))
    disputed, approved = web._frame(rows)
    assert (
        disputed["Trust"]
        == f"{SCIENTIST_SIMULATED_DISPUTED} student: {store_double.REVIEWER_ISSUE}"
    )
    assert approved["Trust"] == "★☆☆☆☆", "an entry nobody objected to shows only its stars"
    assert trust_marks.DISPUTED_LEGEND in web._legend(rows)
    assert trust_marks.DISPUTED_LEGEND == (
        "⚠️ : a reviewer objected to this entry. "
        "Double click the rating in the table to find out why"
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
