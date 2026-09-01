"""The entries table an answer is presented with.

Prose cannot be checked; a table beside it can. These tests cover the selection
and ordering, which every driver shares, and the terminal rendering, which follows
the reference database's results page so output can be compared against it by eye.
"""

from __future__ import annotations

import io

from conftest import agent_with

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import entries_table
from scinumbers_ask.citations import citations, format_citation
from scinumbers_ask.cli import render, run
from scinumbers_ask.events import AnswerEntries, CitationWarning

FIRST, SECOND = 100001, 100002


# -- the parser -----------------------------------------------------------


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
    # Both arguments, though either alone would produce this row. Arranging it with
    # `cited` only would make this test depend on the cited-first ordering, so a
    # change there would fail it with an IndexError about a missing row rather than
    # failing the test that owns ordering.
    row = entries_table.rows_for(repo, cited=(FIRST,), retrieved=(FIRST,))[0]
    assert row.property and row.organism and row.units and row.reference
    assert row.value, "a row with no value cannot be compared against the answer"


# -- rendering ------------------------------------------------------------


def test_nothing_is_rendered_when_there_is_nothing_to_show(repo):
    assert entries_table.render(()) == ""


def test_the_columns_appear_in_the_reference_order(repo):
    text = entries_table.render(entries_table.rows_for(repo, (FIRST,), (FIRST,)))
    header = text.splitlines()[0]
    positions = [header.index(t) for _, t, _ in entries_table.COLUMNS]
    assert positions == sorted(positions), header


def test_every_row_occupies_the_same_number_of_lines(repo):
    """Uniform height is what makes a long table scannable, and what the
    reference page does -- cells wrap to two lines, then truncate."""
    rows = entries_table.rows_for(repo, (FIRST, SECOND), (FIRST, SECOND))
    # Everything after the header and its rule, less the footnotes the table may
    # append below the rows. Cited, so no "nothing cited" notice stands between.
    body = [
        line
        for line in entries_table.render(rows).splitlines()[2:]
        if line != entries_table.NO_METHOD_LEGEND and not line.startswith("…")
    ]
    assert len(body) == 2 * entries_table.LINES_PER_ROW


def test_a_long_cell_is_truncated_rather_than_wrapped_further(repo):
    long_row = entries_table.Row(
        bnid=1,
        property="x " * 80,
        organism="o",
        value="1",
        units="μm",
        reference="r",
        cited=True,
    )
    lines = entries_table.render((long_row,)).splitlines()[2:]
    assert len(lines) == entries_table.LINES_PER_ROW
    assert "…" in lines[-1]


def test_showing_fewer_than_were_retrieved_says_so(repo):
    """A table silently showing five of fifty reads as the whole answer."""
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    text = entries_table.render(rows, limit=1, total=2)
    assert "showing 1 of 2 entries retrieved" in text


def test_what_the_corpus_matched_is_reported_beside_what_was_retrieved(repo):
    """The figure that says how much was never looked at.

    A search capped at fifty rows out of eighty-six matches has passed over
    thirty-six entries, and a table reporting only the fifty reads as though the
    corpus held nothing more.
    """
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    text = entries_table.render(rows, limit=1, total=2, matched=86, searches=1)
    assert "showing 1 of 2 entries retrieved; 86 matched" in text


def test_several_searches_are_counted_rather_than_merged():
    """Two searches may match the same entry, and beyond the row cap the
    identities are unknown -- so the total cannot be a union. Naming the number of
    searches is what stops the sum reading as one."""
    assert entries_table.summarise(5, 50, matched=214, searches=3) == (
        "… showing 5 of 50 entries retrieved; 214 matched across 3 searches"
    )


def test_no_matched_figure_when_nothing_was_searched(repo):
    """A question answered from fetches alone matched nothing; saying "0 matched"
    would read as a corpus with no such entries."""
    assert "matched" not in entries_table.summarise(1, 2, matched=0, searches=0)


def test_no_note_when_everything_retrieved_is_shown(repo):
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    assert "showing" not in entries_table.render(rows, limit=5, total=2)


def test_a_note_still_appears_when_more_matched_than_are_shown(repo):
    """Everything retrieved is on screen, and the corpus still held more."""
    rows = entries_table.rows_for(repo, (), (FIRST, SECOND))
    text = entries_table.render(rows, limit=5, total=2, matched=86, searches=1)
    assert "86 matched" in text


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
    from scinumbers_ask.events import Retrieval

    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    search = next(e for e in events if isinstance(e, Retrieval))
    assert search.detail["bnids"], "a driver cannot table entries it was never told about"
    assert len(search.detail["bnids"]) == search.detail["returned"]


def test_the_identifiers_are_not_printed_on_the_progress_line(repo, config, tmp_path):
    """Fifty of them would bury what the search was actually for."""
    from scinumbers_ask.events import Retrieval

    event = Retrieval(
        question_id="q",
        tool="search_entries",
        detail={"property": "Cell", "returned": 2, "bnids": (FIRST, SECOND)},
    )
    line = render(event)
    assert "Cell" in line and "returned=2" in line
    assert str(FIRST) not in line


# -- citing what was never retrieved -------------------------------------


def test_citing_an_entry_that_was_never_retrieved_is_reported(repo, config, tmp_path):
    """The failure this project exists to catch: a number from the model's memory,
    dressed as a citation.

    An answer given with no tool call at all is the purest form of it. This test
    previously asserted the opposite of its own name -- that no event was emitted --
    on the reasoning that an absent event was itself the signal. It is not one: the
    absence is indistinguishable from a question that never looked, and it also
    suppressed the citation check, so the fabrication was reported as a clean
    answer.
    """
    model = scripted(says(f"about 1 micrometre ({format_citation(SECOND)})"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))

    warning = next(e for e in events if isinstance(e, CitationWarning))
    assert warning.unretrieved == (SECOND,)
    entries = next(e for e in events if isinstance(e, AnswerEntries))
    assert (entries.cited, entries.retrieved) == ((SECOND,), ())


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


def test_no_cell_in_the_table_comes_from_the_model(repo, config, tmp_path):
    """The model chooses which entries are cited and nothing else.

    Every cell is read from the corpus, so a value in the table cannot disagree
    with the corpus even if the answer does -- which is the whole point of showing
    it. Here the answer states a wrong number and cites a real entry; the table
    must still show the corpus's value.
    """
    model = scripted(
        tool_call("get_entry", bnid=SECOND),
        says(f"about 4000 kilometres ({format_citation(SECOND)})"),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    entries = next(e for e in events if isinstance(e, AnswerEntries))
    table = render(entries, repo=repo)

    truth = repo.get(SECOND).entry
    assert truth.value_display in table
    assert "4000" not in table, "a figure from the answer reached the table"


def test_a_question_reports_what_its_searches_matched(repo, config, tmp_path):
    """Found by fault injection: nothing tested the agent's end of this.

    summarise() was covered, but the accumulation feeding it was not -- removing it
    left the whole suite green while the count line silently lost its most telling
    number.
    """
    model = scripted(tool_call("search_entries", property="Cell"), says("done"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    entries = next(e for e in events if isinstance(e, AnswerEntries))

    matched = next(
        e.detail["matched"] for e in events if getattr(e, "tool", "") == "search_entries"
    )
    assert entries.matched == matched
    assert entries.searches == 1
    assert entries.matched >= len(entries.retrieved)


def test_two_searches_are_summed_and_counted(repo, config, tmp_path):
    model = scripted(
        tool_call("search_entries", property="Cell"),
        tool_call("search_entries", property="diameter"),
        says("done"),
    )
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    entries = next(e for e in events if isinstance(e, AnswerEntries))

    per_search = [e.detail["matched"] for e in events if getattr(e, "tool", "") == "search_entries"]
    assert len(per_search) == 2
    assert entries.searches == 2
    assert entries.matched == sum(per_search)


def test_fetching_an_entry_is_not_counted_as_a_search(repo, config, tmp_path):
    """A question answered from fetches alone matched nothing, and must not claim
    a matched figure of zero as though the corpus were empty."""
    model = scripted(tool_call("get_entry", bnid=FIRST), says("done"))
    events = list(agent_with(repo, config, tmp_path, model).ask("s", "q"))
    entries = next(e for e in events if isinstance(e, AnswerEntries))
    assert (entries.searches, entries.matched) == (0, 0)
    assert "matched" not in (render(entries, repo=repo) or "")


# -- provenance, ordering and the cited/uncited break ----------------------


def _repo_of(*specs):
    """A repository over entries written for a test, where the fixture has no case."""
    from scinumbers_ask.corpus import Entry
    from scinumbers_ask.repository import CorpusRepository

    return CorpusRepository(
        tuple(
            Entry(
                bnid=bnid,
                property=prop,
                organism=organism,
                units="μm",
                value=1.0,
                range_low=None,
                range_high=None,
                reference="r",
                reference_pubmed_id=None,
                measurement_method=method,
                comments="",
                keywords=(),
            )
            for bnid, prop, organism, method in specs
        )
    )


def test_the_matched_count_is_dropped_when_every_match_was_retrieved():
    """Equal means nothing was left unlooked-at, so the second number only repeats
    the first -- and a reader who sees two numbers goes looking for the difference."""
    assert entries_table.summarise(5, 21, matched=21, searches=1) == (
        "… showing 5 of 21 entries retrieved"
    )
    assert "50 matched" in entries_table.summarise(5, 21, matched=50, searches=1)


def test_nothing_is_summarised_when_nothing_was_retrieved():
    """The line describes retrieval, so with no retrieval there is nothing to say --
    and "showing 0 of 0" reads as a failure rather than as a question answered
    without one."""
    assert entries_table.summarise(0, 0) == ""


def test_an_entry_whose_method_the_corpus_does_not_record_is_marked(repo):
    """A textbook page and a measurement over a thousand cells otherwise look
    identical in a table, and telling them apart is what a reader is here to do."""
    by_id = {row.bnid: row for row in entries_table.rows_for(repo, (), (FIRST, SECOND))}
    assert by_id[FIRST].method_recorded is True
    assert by_id[SECOND].method_recorded is False


def test_the_marker_and_its_legend_appear_only_when_a_marked_row_is_shown(repo):
    unmarked = entries_table.render(entries_table.rows_for(repo, (FIRST,), (FIRST,)))
    assert entries_table.NO_METHOD not in unmarked

    marked = entries_table.render(entries_table.rows_for(repo, (SECOND,), (SECOND,)))
    assert marked.splitlines()[2].startswith(f"{entries_table.NO_METHOD} ")
    assert marked.splitlines()[-1] == entries_table.NO_METHOD_LEGEND


def test_the_marker_is_not_appended_to_the_identifier(repo):
    """The id has to stay copyable, and will one day be a link."""
    row_line = entries_table.render(
        entries_table.rows_for(repo, (SECOND,), (SECOND,))
    ).splitlines()[2]
    assert f"{SECOND}" in row_line and f"{SECOND}{entries_table.NO_METHOD}" not in row_line


def test_uncited_entries_are_ordered_by_closeness_to_the_topic(repo):
    """Retrieval order for a single search is the corpus's own identifier order,
    which carries no relevance -- it is what put a chromosome in the top five of a
    question about a cell."""
    rows = entries_table.rows_for(
        repo,
        cited=(SECOND,),
        retrieved=(SECOND, 100020, 100010),
        question="what is the diameter of e. coli?",
    )
    # 100010 is another cell diameter and was retrieved last; 100020 counts
    # ribosomes and was retrieved first.
    assert [row.bnid for row in rows] == [SECOND, 100010, 100020]


def test_wording_a_property_repeats_from_its_organism_does_not_score():
    """The organism was matched before the search ran, so a property echoing it says
    nothing. Without the discount, "Diameter of fimbriae of E. coli" outranks every
    entry about the cell itself."""
    repo = _repo_of(
        (1, "Cell diameter", "Bacteria Escherichia coli", ""),
        (2, "Diameter of fimbriae of E. coli", "Bacteria Escherichia coli", ""),
    )
    # Retrieved in this order, so a promotion is what the assertion catches: without
    # the discount the fimbriae entry scores twice -- "diameter" and "coli" -- and
    # overtakes the cell entry, which scores once.
    rows = entries_table.rows_for(repo, cited=(), retrieved=(1, 2), question="diameter of e. coli")
    assert [row.bnid for row in rows] == [1, 2]


def test_the_cited_entries_wording_orders_the_rest(repo):
    """Found by mutation testing: dropping the cited entries from the topic
    vocabulary survived every test. That half is the whole point of the score --
    the question alone cannot say which object the answer settled on."""
    # No question at all, so the cited entry's property is the only signal there is.
    rows = entries_table.rows_for(repo, cited=(SECOND,), retrieved=(COUNT, YEAST), question="")
    uncited = [row.bnid for row in rows if not row.cited]
    assert uncited == [YEAST, COUNT], "the entry sharing the cited property should lead"


def test_the_question_wording_orders_the_rest_too(repo):
    """The other half, and it failed the same way: taking only the cited
    properties, and dropping the question, also survived."""
    rows = entries_table.rows_for(
        repo, cited=(SECOND,), retrieved=(MASS, COUNT), question="ribosomes"
    )
    uncited = [row.bnid for row in rows if not row.cited]
    assert uncited == [COUNT, MASS], "the entry matching the question should lead"


def test_entries_the_score_cannot_separate_keep_the_order_they_were_met_in():
    repo = _repo_of(
        (1, "Cell diameter", "Bacteria Escherichia coli", ""),
        (2, "Cell diameter", "Bacteria Escherichia coli", ""),
    )
    rows = entries_table.rows_for(repo, cited=(), retrieved=(2, 1), question="diameter")
    assert [row.bnid for row in rows] == [2, 1]


def test_a_row_cited_without_being_retrieved_is_marked(repo):
    """The entry exists, so nothing about the row looks wrong -- which is exactly the
    problem. Unmarked it sits among the cited entries as though the answer rested on
    it legitimately."""
    rows = entries_table.rows_for(repo, cited=(FIRST,), retrieved=())
    text = entries_table.render(rows)
    assert rows[0].retrieved is False
    assert text.splitlines()[2].startswith(entries_table.NOT_RETRIEVED)
    assert entries_table.NOT_RETRIEVED_LEGEND in text


def test_a_retrieved_row_carries_no_such_mark(repo):
    text = entries_table.render(entries_table.rows_for(repo, cited=(FIRST,), retrieved=(FIRST,)))
    assert entries_table.NOT_RETRIEVED not in text


def test_both_marks_can_apply_to_one_row(repo):
    """SECOND records no method and is cited without retrieval. Suppressing either
    mark because the other applies would hide a fact about the entry."""
    text = entries_table.render(entries_table.rows_for(repo, cited=(SECOND,), retrieved=()))
    assert entries_table.NOT_RETRIEVED in text and entries_table.NO_METHOD in text
    assert entries_table.NOT_RETRIEVED_LEGEND in text
    assert entries_table.NO_METHOD_LEGEND in text


def test_a_banner_separates_the_entries_the_answer_rests_on_from_the_rest(repo):
    """Both groups are shown -- what the corpus held and the answer passed over is
    part of the evidence -- but a reader must not have to work out which is which."""
    text = entries_table.render(entries_table.rows_for(repo, (FIRST,), (FIRST, SECOND)))
    lines = text.splitlines()
    banner = next(i for i, line in enumerate(lines) if entries_table.UNCITED_BANNER in line)
    assert f"{FIRST}" in "\n".join(lines[:banner])
    assert f"{SECOND}" in "\n".join(lines[banner:])


def test_a_table_where_nothing_was_cited_says_so_before_the_rows(repo):
    """Otherwise it renders exactly as a table whose top rows are the cited ones,
    and a reader takes the first row for the citation -- because everywhere else
    it is. The web driver said this from the start; the terminal did not."""
    nothing_cited = entries_table.render(entries_table.rows_for(repo, (), (FIRST, SECOND)))
    lines = nothing_cited.splitlines()
    assert lines[2] == entries_table.NOTHING_CITED
    assert entries_table.UNCITED_BANNER in lines[3], "the rows below it are still labelled"


def test_no_banner_and_no_notice_when_every_shown_entry_is_cited(repo):
    all_cited = entries_table.render(entries_table.rows_for(repo, (FIRST, SECOND), (FIRST, SECOND)))
    assert entries_table.UNCITED_BANNER not in all_cited
    assert entries_table.NOTHING_CITED not in all_cited


def test_the_banner_is_not_drawn_for_a_break_below_the_row_limit(repo):
    """It marks a break the reader can see, not one that was cut off."""
    text = entries_table.render(entries_table.rows_for(repo, (FIRST,), (FIRST, SECOND)), limit=1)
    assert entries_table.UNCITED_BANNER not in text


def test_one_implementation_reads_the_source_notation(repo):
    """Two parsers for one notation drifted once already: the corpus side read a run
    of identifiers and the answer side read only the first.

    There are two *callers* now -- an entry's prose and an answer -- and that is the
    point of the split. What must not come back is a second *implementation*: both
    route through the same function object, so a change to the notation cannot reach
    one caller and miss the other.
    """
    from scinumbers_ask import bionumbers, citations, repository

    assert repository.cross_references is bionumbers.cross_references
    assert citations.cross_references is bionumbers.cross_references
    assert repo.get(FIRST).cited_bnids == (102065, 104333)


# -- dimensional compatibility --------------------------------------------

MASS, COUNT, VOLUME, YEAST = 100030, 100020, 100003, 100010


def test_the_table_says_when_cited_entries_measure_different_kinds_of_thing(repo):
    """The mass-versus-count pair. A reader comparing an answer against the entries
    it cites needs to see that a range across these two is not a range."""
    rows = entries_table.rows_for(repo, cited=(MASS, COUNT), retrieved=(MASS, COUNT))
    text = entries_table.render(rows)
    assert "2 kinds of quantity" in text
    assert "dimensionless, mass" in text
    assert "not alternatives for one another" in text


def test_nothing_is_said_when_the_cited_entries_agree(repo):
    """Stated as a fact about the units, not a fault -- so it must be silent when
    there is no fact to state, or it becomes noise nobody reads."""
    text = entries_table.render(entries_table.rows_for(repo, (FIRST, SECOND), (FIRST, SECOND)))
    assert "kinds of quantity" not in text


def test_only_the_cited_entries_are_weighed(repo):
    """An uncited entry of another kind is not something the answer rests on, and
    flagging it would fire on almost every search."""
    text = entries_table.render(entries_table.rows_for(repo, (FIRST,), (FIRST, COUNT)))
    assert "kinds of quantity" not in text


def test_a_cited_entry_below_the_row_limit_still_counts(repo):
    """The answer rests on every entry it cited, not on the ones that happened to
    fit."""
    rows = entries_table.rows_for(repo, cited=(MASS, COUNT), retrieved=(MASS, COUNT))
    assert "2 kinds of quantity" in entries_table.render(rows, limit=1)


def test_a_number_is_never_split_across_two_lines(repo):
    """Split, "6800.0-72000.0" read as "6800.0-72000." above a lone "0" -- a value
    the corpus does not hold, shown with nothing to say it had been altered."""
    text = entries_table.render(entries_table.rows_for(repo, (COUNT,), (COUNT,)))
    value_column = next(w for field, _, w in entries_table.COLUMNS if field == "value")
    assert "6800.0–72000…" in text
    assert not any(line.strip() == "0" for line in text.splitlines())
    assert all(len(line) <= 106 for line in text.splitlines()), "a column overran"
    assert value_column == 13


def test_a_long_footnote_wraps_to_the_table(repo):
    """The number of dimensions is unbounded, and four already overran the rule. A
    footnote running past it reads as a line belonging to something else."""
    width = sum(w for _, _, w in entries_table.COLUMNS) + 2 * (len(entries_table.COLUMNS) - 1)
    cited = (VOLUME, COUNT, MASS, FIRST)
    text = entries_table.render(entries_table.rows_for(repo, cited, cited))
    assert all(len(line) <= width for line in text.splitlines()), "a line overran the rule"
    # Rejoined, because wrapping is exactly what splits the sentence.
    flat = " ".join(line.strip() for line in text.splitlines())
    assert "4 kinds of quantity (dimensionless, length, mass, volume)" in flat
    assert "not alternatives for one another" in flat


# -- the conditions that distinguish differing values ----------------------


def _row(bnid, method="", cited=True, value="1.0"):
    return entries_table.Row(
        bnid=bnid,
        property="Cell volume",
        organism="Bacteria Escherichia coli",
        value=value,
        units="μm^3",
        reference="r",
        cited=cited,
        method_recorded=bool(method),
        method=method,
    )


def test_the_methods_of_cited_entries_are_shown():
    """A reader checking why two cited entries give different numbers has nothing
    to go on otherwise: the table said only when a method was absent, so a textbook
    page and a count over a thousand cells were both just rows."""
    text = entries_table.render(
        (_row(1, "Transmission electron microscopy"), _row(2, "Coulter counter", value="9.0"))
    )
    assert "how the cited entries were measured:" in text
    assert "Transmission electron microscopy" in text
    assert "Coulter counter" in text


def test_one_cited_entry_has_nothing_to_be_distinguished_from():
    """The block answers "why do these differ", which a single entry does not ask."""
    text = entries_table.render((_row(1, "Transmission electron microscopy"),))
    assert "how the cited entries were measured" not in text


def test_the_methods_of_uncited_entries_are_not_shown():
    """The answer does not rest on them, and the block would then explain a
    difference the prose never claimed."""
    text = entries_table.render(
        (_row(1, "Electron microscopy"), _row(2, "Coulter counter", cited=False, value="9.0"))
    )
    assert "how the cited entries were measured" not in text


def test_an_entry_recording_no_method_is_left_out_but_still_marked():
    """Its absence is already carried by the marker; a blank line in the block
    would say the same thing twice and invite reading it as an empty method."""
    text = entries_table.render(
        (
            _row(1, "Electron microscopy"),
            _row(2, "Coulter counter", value="9.0"),
            _row(3, "", value="4.0"),
        )
    )
    block = text.split("how the cited entries were measured:")[1].splitlines()
    listed = [line for line in block if line.startswith("  BNID")]
    assert len(listed) == 2, "the entry with no method should not be listed"
    assert entries_table.bionumbers.label(3) not in text
    assert entries_table.NO_METHOD_LEGEND in text


def test_a_long_method_is_cut_to_the_table_and_says_so():
    """The median recorded method is 231 characters and the longest 2,382. No
    terminal table carries that, and a line running past the rule reads as
    something else."""
    long_method = "Coulter counter " * 40
    text = entries_table.render((_row(1, long_method), _row(2, "Microscopy", value="9.0")))
    width = sum(w for _, _, w in entries_table.COLUMNS) + 2 * (len(entries_table.COLUMNS) - 1)
    assert all(len(line) <= width for line in text.splitlines()), "a method line overran"
    assert "…" in text


# -- 8.7 and 8.8: what the source did not claim ---------------------------


def an_entry(**kwargs):
    from scinumbers_ask.corpus import Entry

    base = dict(
        bnid=1,
        property="p",
        organism="o",
        units="mg/L",
        value=None,
        range_low=8.0,
        range_high=8.0,
        reference="r",
        reference_pubmed_id=None,
        measurement_method="m",
        comments="",
        keywords=(),
    )
    base.update(kwargs)
    return Entry(**base)
    return Entry(**{**base, **kwargs})


def test_a_hedged_bound_is_not_displayed_as_an_exact_value():
    """The live failure this exists for: `<8` reaches the corpus as [8, 8] and
    printed as "8.0", which asserts an equality the source never made. A bound is a
    different claim, not a rounder one -- an MIC of `<8` means susceptible at or
    below 8, and the agent answered "is 8.0 mg/L" with the table agreeing."""
    assert an_entry(range_qualified=True).value_display == "8.0 (bounded, not exact)"
    assert an_entry(range_qualified=False).value_display == "8.0"


def test_the_span_rule_holds_at_its_own_threshold():
    """A millionfold exactly is not more than a millionfold. Tested on both sides
    because a threshold written `>=` where `>` was meant is invisible otherwise."""
    assert not an_entry(range_low=1.0, range_high=1_000_000.0).spans_implausibly
    assert an_entry(range_low=1.0, range_high=1_000_001.0).spans_implausibly


def test_the_span_rule_says_nothing_where_it_cannot_be_applied():
    """A ratio is meaningless across zero, and a mark firing on arithmetic rather
    than on evidence is worse than no mark."""
    for low, high in ((0.0, 1e30), (-1.0, 1e30), (None, 1e30), (1.0, None)):
        assert not an_entry(range_low=low, range_high=high).spans_implausibly


def test_the_real_entry_that_prompted_the_span_rule():
    """BNID 100550, `0.25-2.5e30`: parsed exactly as written, so `range_fused` does
    not mark it and correctly does not -- it is one cell, not two quantities."""
    entry = an_entry(range_low=0.25, range_high=2.5e30, range_fused=False)
    assert entry.spans_implausibly and not entry.range_fused


def test_each_flag_draws_its_own_mark_and_its_own_legend(repo):
    """Two marks and two sentences, never one of each. A record can carry either
    flag without the other, and "the source stated a bound" is not "these bounds may
    be different quantities" -- BNID 100420 carries both and is wrong in two ways."""
    row = entries_table.Row(
        bnid=1,
        property="p",
        organism="o",
        value="8.0",
        units="mg/L",
        reference="r",
        cited=True,
        qualified=True,
    )
    assert entries_table.QUALIFIED in row.markers()
    assert entries_table.FUSED not in row.markers()

    both = entries_table.Row(
        bnid=1,
        property="p",
        organism="o",
        value="1–2",
        units="u",
        reference="r",
        cited=True,
        qualified=True,
        fused=True,
    )
    rendered = entries_table.render((both,))
    assert entries_table.QUALIFIED_LEGEND in rendered
    assert entries_table.FUSED_LEGEND in rendered


def test_a_legend_is_absent_when_no_shown_row_carries_its_mark(repo):
    plain = entries_table.Row(
        bnid=1,
        property="p",
        organism="o",
        value="1",
        units="u",
        reference="r",
        cited=True,
    )
    rendered = entries_table.render((plain,))
    for legend in (
        entries_table.QUALIFIED_LEGEND,
        entries_table.FUSED_LEGEND,
        entries_table.IMPLAUSIBLE_LEGEND,
    ):
        assert legend not in rendered


def test_the_value_says_which_kind_of_hedge_the_source_used():
    """ "~20" is an approximation and "<8" is a bound. Calling the first "bounded"
    describes it wrongly while claiming to correct a description, which is a worse
    failure than the bare "20.0" it replaced -- it looks like a considered caveat."""
    approx = an_entry(range_low=20.0, range_high=20.0, range_qualified=True, range_approximate=True)
    bound = an_entry(range_qualified=True, range_one_sided=True)
    unspecified = an_entry(range_qualified=True)

    assert approx.value_display == "20.0 (approximate)"
    assert bound.value_display == "8.0 (a bound, not exact)"
    assert unspecified.value_display == "8.0 (bounded, not exact)", (
        "with no kind reported it says less, never something untrue"
    )
