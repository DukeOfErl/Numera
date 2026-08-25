"""The entries table an answer is presented with.

Prose cannot be checked; a table beside it can. These tests cover the selection
and ordering, which every driver shares, and the terminal rendering, which follows
the reference database's results page so output can be compared against it by eye.
"""

from __future__ import annotations

import io

import pytest

from bionumbers_ask import entries_table
from bionumbers_ask.citations import citations, format_citation
from bionumbers_ask.cli import render, run
from bionumbers_ask.events import AnswerEntries, CitationWarning

from agent_doubles import says, scripted, tool_call
from conftest import agent_with

FIRST, SECOND = 100001, 100002


# -- the parser -----------------------------------------------------------


def test_a_bare_number_is_not_a_citation():
    """The reason the format is stated at all: a six-digit quantity is not an id."""
    assert citations("the cell holds 100000 ribosomes") == ()
    assert citations("100000 ribosomes (BNID 106576)") == (106576,)


@pytest.mark.parametrize(
    "text",
    ["BNID 100002", "bnid100002", "BNID: 100002", "bnid #100002", "BNID-100002"],
)
def test_the_marker_is_required_but_the_glue_is_not(text):
    """Permissive glue on purpose: the form is asked of the model, so it is a
    preference, not a control. A parser rejecting "BNID: x" would score a good
    answer as uncited, and a false negative in evaluation is the worse error."""
    assert citations(text) == (100002,)


def test_citations_keep_their_order_without_repeating():
    assert citations("BNID 3 then BNID 1 then BNID 3") == (3, 1)


def test_the_written_form_is_the_form_that_parses():
    """Otherwise the prompt, the drivers and the scorer could drift apart."""
    assert citations(format_citation(100002)) == (100002,)


# -- selection and ordering ----------------------------------------------


def test_cited_entries_come_before_the_rest(repo):
    rows = entries_table.rows_for(repo, cited=(SECOND,), retrieved=(FIRST, SECOND))
    assert [r.bnid for r in rows] == [SECOND, FIRST]
    assert [r.cited for r in rows] == [True, False]


def test_an_identifier_that_is_not_in_the_corpus_is_left_out(repo):
    """A fabricated citation has no row to show; the warning event reports it."""
    rows = entries_table.rows_for(repo, cited=(999999,), retrieved=(FIRST,))
    assert [r.bnid for r in rows] == [FIRST]


def test_an_entry_retrieved_twice_appears_once(repo):
    rows = entries_table.rows_for(repo, cited=(FIRST,), retrieved=(FIRST, FIRST))
    assert [r.bnid for r in rows] == [FIRST]


def test_a_row_carries_every_column_the_reader_needs(repo):
    row = entries_table.rows_for(repo, cited=(FIRST,), retrieved=())[0]
    assert row.property and row.organism and row.units and row.reference
    assert row.value, "a row with no value cannot be compared against the answer"


# -- rendering ------------------------------------------------------------


def test_nothing_is_rendered_when_there_is_nothing_to_show(repo):
    assert entries_table.render(()) == ""


def test_the_columns_appear_in_the_reference_order(repo):
    text = entries_table.render(entries_table.rows_for(repo, (FIRST,), ()))
    header = text.splitlines()[0]
    positions = [header.index(t) for _, t, _ in entries_table.COLUMNS]
    assert positions == sorted(positions), header


def test_every_row_occupies_the_same_number_of_lines(repo):
    """Uniform height is what makes a long table scannable, and what the
    reference page does -- cells wrap to two lines, then truncate."""
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    body = entries_table.render(rows).splitlines()[2:]
    assert len(body) == 2 * entries_table.LINES_PER_ROW


def test_a_long_cell_is_truncated_rather_than_wrapped_further(repo):
    long_row = entries_table.Row(
        bnid=1, property="x " * 80, organism="o", value="1",
        units="μm", reference="r", cited=True,
    )
    lines = entries_table.render((long_row,)).splitlines()[2:]
    assert len(lines) == entries_table.LINES_PER_ROW
    assert "…" in lines[-1]


def test_showing_fewer_than_were_retrieved_says_so(repo):
    """A table silently showing five of fifty reads as the whole answer."""
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    text = entries_table.render(rows, limit=1, total=2)
    assert "showing 1 of 2 entries retrieved" in text


def test_no_note_when_everything_retrieved_is_shown(repo):
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    assert "showing" not in entries_table.render(rows, limit=5, total=2)


# -- through the driver ---------------------------------------------------


def test_the_table_follows_the_answer_in_the_terminal(repo, config, tmp_path):
    out = io.StringIO()
    model = scripted(
        tool_call("search_entries", property="Cell"),
        says(f"about 1 micrometre ({format_citation(SECOND)})"),
    )
    run(agent_with(repo, config, tmp_path, model), "s", ["how wide?"], out, repo=repo)

    text = out.getvalue()
    assert text.index("about 1 micrometre") < text.index("Property"), text
    assert str(SECOND) in text


def test_the_table_is_skipped_when_the_driver_has_no_corpus(repo):
    """The event carries identifiers, so a driver without the corpus shows nothing
    rather than inventing rows."""
    event = AnswerEntries(question_id="q", cited=(FIRST,), retrieved=(FIRST,))
    assert render(event, repo=None) is None
    assert render(event, repo=repo) is not None


def test_the_search_reports_which_entries_it_returned(repo, config, tmp_path):
    """What makes both the table and the citation check possible."""
    from bionumbers_ask.events import Retrieval

    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    search = next(e for e in events if isinstance(e, Retrieval))
    assert search.detail["bnids"], "a driver cannot table entries it was never told about"
    assert len(search.detail["bnids"]) == search.detail["returned"]


def test_the_identifiers_are_not_printed_on_the_progress_line(repo, config, tmp_path):
    """Fifty of them would bury what the search was actually for."""
    from bionumbers_ask.events import Retrieval

    event = Retrieval(question_id="q", tool="search_entries",
                      detail={"property": "Cell", "returned": 2, "bnids": (FIRST, SECOND)})
    line = render(event)
    assert "Cell" in line and "returned=2" in line
    assert str(FIRST) not in line


# -- citing what was never retrieved -------------------------------------


def test_citing_an_entry_that_was_never_retrieved_is_reported(repo, config, tmp_path):
    """The failure this project exists to catch: a number from the model's memory,
    dressed as a citation. Silent otherwise."""
    model = scripted(says(f"about 1 micrometre ({format_citation(SECOND)})"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    # No tool was called, so nothing was retrieved -- and with nothing retrieved
    # there is no evidence event at all, which is itself the signal.
    assert not any(isinstance(e, AnswerEntries) for e in events)


def test_a_citation_absent_from_the_corpus_is_named(repo, config, tmp_path):
    model = scripted(
        tool_call("search_entries", property="Cell"),
        says("about 1 micrometre (BNID 999999)"),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    warning = next(e for e in events if isinstance(e, CitationWarning))
    assert warning.unknown == (999999,)
    assert "not in the corpus" in render(warning)


def test_a_real_entry_cited_without_being_retrieved_is_named(repo, config, tmp_path):
    """It exists, so nothing about the answer looks wrong -- but this question
    never put it in front of the model."""
    model = scripted(
        tool_call("get_entry", bnid=FIRST),
        says(f"about 1 micrometre ({format_citation(SECOND)})"),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    warning = next(e for e in events if isinstance(e, CitationWarning))
    assert warning.unretrieved == (SECOND,)
    assert "without being retrieved" in render(warning)


def test_citing_an_entry_seen_only_in_a_search_row_is_not_flagged(repo, config, tmp_path):
    """A compact row carries the identifier, property, value and units, so it is
    enough to cite from. Requiring a full fetch would flag good answers."""
    model = scripted(
        tool_call("search_entries", property="Cell"),
        says(f"about 1 micrometre ({format_citation(SECOND)})"),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    assert not any(isinstance(e, CitationWarning) for e in events)
