"""The answer sheet: what a person reads to decide whether the figures mean anything.

The tests worth having here are not about layout. They are about the two ways this
can be quietly wrong: writing corpus text somewhere git would take it, and
disagreeing with the scoring it claims to illustrate. A sheet that says an entry
was cited when the report counts it as missed is worse than no sheet, because it
is the artefact a reviewer trusts when the figures look odd.
"""

from __future__ import annotations

import pytest
from conftest import FIXTURE

from scinumbers_ask.answer_sheet import render_html, write_answer_sheet
from scinumbers_ask.corpus import Entry, load
from scinumbers_ask.evaluation import Provenance, Result, ResultsWouldBeCommitted
from scinumbers_ask.question_set import Question, Tier

PROVENANCE = Provenance(
    recorded_at="2026-09-11T00:00:00+00:00",
    model="fake/model",
    question_ceiling=1,
    run_budget=1,
    run_label="test",
    prompt_digest="p1",
    corpus_digest="c1",
    corpus_entries=6,
    code_version="git abc1234",
)


@pytest.fixture
def corpus():
    return load(FIXTURE)


def a_result(**kwargs) -> Result:
    base = dict(
        question_id="q1",
        repeat=1,
        question="how big?",
        answer="About 1 um^3 [[100003]].",
        expected_entries=(100003,),
        cited=(100003,),
        retrieved=(100003,),
        end_reason="answered",
        provenance=PROVENANCE,
    )
    base.update(kwargs)
    return Result(**base)


def a_question(**kwargs) -> Question:
    base = dict(
        question_id="q1",
        question="how big?",
        asked_properties=("Cell volume",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=(100003,),
    )
    base.update(kwargs)
    return Question(**base)


def test_a_sheet_is_refused_on_a_path_git_would_track(corpus):
    """The sheet tabulates entries, so it holds corpus text exactly as a results
    file does. The group 3-4 review recorded that *every later artefact of a run*
    needs this guard; a report rendered into the repository is one of them.

    `docs/` is tracked in this checkout and the test runs from its root, so the
    path resolves into the repository without naming it.
    """
    with pytest.raises(ResultsWouldBeCommitted):
        write_answer_sheet("docs/would-leak.html", (a_result(),), (a_question(),), corpus)


def test_a_sheet_is_written_where_git_would_not_track_it(tmp_path, corpus):
    """The guard must not refuse everything -- a refusal that always fires proves
    nothing about the one that matters."""
    target = tmp_path / "sheet.html"
    write_answer_sheet(target, (a_result(),), (a_question(),), corpus)
    assert "Cell volume" in target.read_text(encoding="utf-8")


def test_the_recorded_context_never_appears_in_the_sheet(corpus):
    """Three quarters of a results file is the verbatim text the agent was shown.
    It is kept for re-scoring and for the judge, not for a reader, and reproducing
    it would bury the answer it exists to support."""
    result = a_result(context=("SECRET CORPUS DUMP\tproperty\torganism", "more context"))
    page = render_html((result,), (a_question(),), corpus)
    assert "SECRET CORPUS DUMP" not in page
    assert "more context" not in page


def test_an_expected_entry_that_was_never_retrieved_is_marked_as_such(corpus):
    result = a_result(expected_entries=(100003, 100010), cited=(), retrieved=())
    page = render_html((result,), (a_question(expected_entries=(100003, 100010)),), corpus)
    assert "never retrieved" in page
    assert "2 of 2 never retrieved" in page
    # The entries are real, so the reader sees what was missed rather than an id.
    assert "Cell volume" in page and "Cell diameter" in page


def test_an_admissible_citation_is_marked_apart_from_an_unexpected_one(corpus):
    result = a_result(
        expected_entries=(100003,),
        cited=(100003, 100010, 100020),
        retrieved=(100003, 100010, 100020),
    )
    question = a_question(expected_entries=(100003,), admissible_entries=(100010,))
    page = render_html((result,), (question,), corpus)
    assert "admissible, cited" in page
    assert "cited, in neither list" in page


def test_a_result_whose_question_has_left_the_set_still_shows_its_answer(corpus):
    """A results file outlives the set. Dropping the section would silently
    shorten the sheet and nothing would say why."""
    page = render_html((a_result(question_id="gone"),), (a_question(),), corpus)
    assert "gone" in page
    assert "no longer in the set" in page


def test_the_tier_is_shown_beside_each_answer(corpus):
    """A reader comparing two runs needs to know which kind of question this was
    before deciding whether a change is a gain or a trade."""
    page = render_html((a_result(),), (a_question(tier=Tier.COMPOUND),), corpus)
    assert "compound" in page


def test_an_approximate_scalar_is_not_rendered_as_a_spread(corpus):
    """The corpus records an approximate scalar as a range whose ends are equal --
    111527 is "50000.0-50000.0" -- and printing it literally claims a spread the
    source never gave. The six-entry fixture holds none, so one is built here."""
    degenerate = Entry(
        entry_id=100099,
        property="Number of ribosomes",
        organism="Bacteria Escherichia coli",
        units="ribosomes/cell",
        value=None,
        range_low=50000.0,
        range_high=50000.0,
        reference="r",
        reference_pubmed_id=None,
        measurement_method="m",
        comments="",
        keywords=(),
        range_approximate=True,
    )
    page = render_html(
        (a_result(expected_entries=(100099,), cited=(100099,), retrieved=(100099,)),),
        (a_question(expected_entries=(100099,)),),
        (*corpus, degenerate),
    )
    assert "50000.0 ribosomes/cell" in page
    assert "50000.0–50000.0" not in page
    assert "~" in page  # the flag still says the source called it approximate
