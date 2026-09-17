"""The answer sheet: what a person reads to decide whether the figures mean anything.

The tests worth having here are not about layout. They are about the two ways this
can be quietly wrong: writing corpus text somewhere git would take it, and
disagreeing with the scoring it claims to illustrate. A sheet that says an entry
was cited when the report counts it as missed is worse than no sheet, because it
is the artefact a reviewer trusts when the figures look odd.
"""

from __future__ import annotations

from pathlib import Path

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

    **Skipped outside a real checkout, not failed.** The guard asks git whether it
    would track the path, so the question is unanswerable in a copied tree -- which
    is where fault seeding and mutation testing run. A copy that reported this as a
    failure would bury the seeded defect it was actually looking for.
    """
    if not (Path.cwd() / "docs").is_dir() or not (Path.cwd() / ".git").exists():
        pytest.skip("not a checkout with a tracked docs/: git cannot be asked here")
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


def test_an_expected_entry_that_never_reached_the_table_is_marked_as_such(corpus):
    result = a_result(expected_entries=(100003, 100010), cited=(), retrieved=())
    page = render_html((result,), (a_question(expected_entries=(100003, 100010)),), corpus)
    assert "never retrieved" in page
    assert "2 of 2 never reached it" in page
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


# -- What the branch review of 2026-09-16 found ---------------------------------


def test_the_value_shown_is_the_one_the_reader_s_table_showed(corpus):
    """`Entry.value_display` prefers a scalar over a range; re-deriving it here
    checked the range first, so an entry carrying both -- 7.4 over 7.1-7.7, the
    ordinary shape of a value with a spread -- read one way in the table and
    another on the sheet. Fidelity to that table is the whole claim of the rank
    column, and the value column was breaking it."""
    both = Entry(
        entry_id=100077,
        property="Cell length",
        organism="Bacteria Escherichia coli",
        units="um",
        value=7.4,
        range_low=7.1,
        range_high=7.7,
        reference="r",
        reference_pubmed_id=None,
        measurement_method="m",
        comments="",
        keywords=(),
    )
    page = render_html(
        (a_result(expected_entries=(100077,), cited=(100077,), retrieved=(100077,)),),
        (a_question(expected_entries=(100077,)),),
        (*corpus, both),
    )
    assert "7.4 um" in page
    assert "7.1–7.7" not in page


def test_a_unit_carrying_markup_is_escaped(corpus):
    """The corpus is an external input, and its prose is documented to use `<` as
    a less-than sign. Every sibling field was escaped and this one was not."""
    awkward = Entry(
        entry_id=100078,
        property="Cell length",
        organism="Bacteria Escherichia coli",
        units="<unit>",
        value=3.0,
        range_low=None,
        range_high=None,
        reference="r",
        reference_pubmed_id=None,
        measurement_method="m",
        comments="",
        keywords=(),
    )
    page = render_html(
        (a_result(expected_entries=(100078,), cited=(100078,), retrieved=(100078,)),),
        (a_question(expected_entries=(100078,)),),
        (*corpus, awkward),
    )
    assert "&lt;unit&gt;" in page
    assert "3.0 <unit>" not in page


def test_a_negative_bullet_keeps_its_sign(corpus):
    """`lstrip(" -*")` strips a character set, not a marker, so a bullet reading
    "- -20 °C" rendered as "20 °C" -- a silent sign inversion in the artefact a
    person reads to judge answers."""
    page = render_html(
        (a_result(answer="Findings:\n- -20 °C is the storage temperature."),),
        (a_question(),),
        corpus,
    )
    assert "-20 °C" in page


def test_one_header_is_not_put_on_answers_from_several_runs(corpus):
    """A results file is appended to and resumed, and a resume may cross a model
    change or a corpus rebuild. `report.render` groups for this reason; the sheet
    has one header, so it must refuse to caption runs it cannot describe."""
    from dataclasses import replace

    other = replace(PROVENANCE, model="other/model", corpus_digest="c2")
    page = render_html((a_result(), a_result(repeat=2, provenance=other)), (a_question(),), corpus)
    assert "2 different runs" in page
    assert "fake/model" not in page


def test_one_header_is_given_when_every_answer_shares_a_run(corpus):
    """The other direction: a refusal that always fires would say nothing."""
    page = render_html((a_result(), a_result(repeat=2)), (a_question(),), corpus)
    assert "fake/model" in page
    assert "different runs" not in page
