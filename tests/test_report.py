"""The report. Mostly tests of what it refuses to imply.

A wrong figure here is the most dangerous output in the project: it is the thing a
person reads and acts on, and it looks exactly the same whether it is right or
not. So the assertions below are about the sentences that stop a reader drawing a
conclusion the data does not support -- a partial run said to be partial, groups
never averaged together, and a comparison that could not be made said out loud
rather than left as an absence.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import write_all_shapes_corpus

from scinumbers_ask.corpus import Entry, load
from scinumbers_ask.evaluation import Provenance, Result
from scinumbers_ask.question_set import Question
from scinumbers_ask.report import render

PROVENANCE = Provenance(
    recorded_at="2026-09-05T09:00:00+00:00",
    model="fake/model",
    question_ceiling=600_000,
    run_budget=1_200_000,
    run_label="test",
    prompt_digest="prompt0000000001",
    corpus_digest="corpus0000000001",
    corpus_entries=6,
    code_version="git abc1234",
)


AN_ENTRY = Entry(
    entry_id=1,
    property="Nuclear volume",
    organism="Fungi Saccharomyces cerevisiae",
    units="um^3",
    value=2.0,
    range_low=None,
    range_high=None,
    reference="r",
    reference_pubmed_id=None,
    measurement_method="m",
    comments="",
    keywords=(),
)


def a_question(identifier: str = "q1", **kwargs) -> Question:
    base = dict(
        question_id=identifier,
        question="how big?",
        asked_properties=("Cell volume",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=(1,),
    )
    base.update(kwargs)
    return Question(**base)


def a_result(identifier: str = "q1", **kwargs) -> Result:
    base = dict(
        question_id=identifier,
        repeat=1,
        question="how big?",
        answer="1.0 um^3 [[1]]",
        expected_entries=(1,),
        cited=(1,),
        retrieved=(1,),
        end_reason="answered",
        spend=1_000,
        run_spend=1_000,
        model="fake/model",
        provenance=PROVENANCE,
    )
    base.update(kwargs)
    return Result(**base)


@pytest.fixture
def corpus(tmp_path) -> tuple[Entry, ...]:
    return load(write_all_shapes_corpus(tmp_path))


def test_an_empty_results_file_is_reported_as_empty_not_as_zeros(corpus):
    """Zeros would be figures, and figures are read as measurements."""
    text = render((), (a_question(),), corpus)
    assert "No results yet" in text
    assert "0%" not in text


def test_a_complete_run_is_not_marked_partial(corpus):
    text = render((a_result(),), (a_question(),), corpus, repeats=1)
    assert "PARTIAL" not in text


def test_a_partial_run_says_so_before_any_figure(corpus):
    """A partial file that reads as complete is how a report comes to describe a
    set it never finished asking."""
    text = render((a_result(),), (a_question("q1"), a_question("q2")), corpus, repeats=1)
    assert "PARTIAL: 1 of 2 expected results are absent" in text
    assert text.index("PARTIAL") < text.index("expected entries cited")


def test_a_run_stopped_on_its_budget_is_distinguished_from_a_completed_one(corpus):
    stopped = a_result("q2", end_reason="run_budget", answer="", cited=())
    text = render((a_result(), stopped), (a_question(), a_question("q2")), corpus)
    assert "is not a completed run" in text


def test_a_run_closed_by_a_spent_key_is_not_reported_as_completed(corpus):
    """The report was written when the run budget was the only closing ending.

    `PROVIDER_LIMIT` was added later, the driver learned to stop on the whole
    shared set, and this line kept comparing against `run_budget` alone -- so a run
    cut short because the API key had no credit left read as a run that finished.
    That is the first thing this module's docstring says it refuses to do.
    """
    spent = a_result("q2", end_reason="provider_limit", answer="", cited=())
    text = render((a_result(), spent), (a_question(), a_question("q2")), corpus)
    assert "is not a completed run" in text
    assert "provider_limit 1" in text


def test_a_failed_question_is_named(corpus):
    failed = a_result("q2", failure="RuntimeError: the provider fell over")
    text = render((a_result(), failed), (a_question(), a_question("q2")), corpus)
    assert "1 question(s) failed" in text and "q2" in text


def test_figures_are_never_combined_across_a_different_prompt_or_corpus(corpus):
    """A reworded prompt moves every figure and a rebuilt corpus changes what
    there was to find. One average over both would describe neither."""
    other = replace(PROVENANCE, prompt_digest="prompt0000000002")
    text = render(
        (a_result(), a_result("q2", provenance=other)),
        (a_question(), a_question("q2")),
        corpus,
    )
    assert "prompt0000000001" in text and "prompt0000000002" in text
    assert "are not combined" in text


def test_one_group_needs_no_warning_about_combining(corpus):
    text = render((a_result(),), (a_question(),), corpus)
    assert "are not combined" not in text


def test_the_two_kinds_of_missed_entry_are_reported_apart(corpus):
    """One failure of selection, one of search. A single "missed" count would hide
    which is happening."""
    missed = a_result(expected_entries=(1, 2), cited=(), retrieved=(1,))
    text = render((missed,), (a_question(expected_entries=(1, 2)),), corpus)
    assert "passed over (retrieved, not cited): 1" in text
    assert "never retrieved: 1" in text


def test_an_unexpected_citation_is_reported_as_not_an_error(corpus):
    text = render((a_result(cited=(1, 2)),), (a_question(),), corpus)
    assert "cited but not expected: 1" in text
    assert "not counted as errors" in text


def test_a_fabrication_on_an_unsupported_question_is_listed_with_its_answer(corpus):
    """The quantity rule over-flags by design, so the list is what keeps the
    over-flagging visible and measurable rather than merely accepted."""
    question = a_question("q9", unsupported=True, expected_entries=())
    fabricated = a_result("q9", answer="roughly 300 of them", cited=(), expected_entries=())
    text = render((fabricated,), (question,), corpus)
    assert "unsupported questions declined: 0 of 1" in text
    assert "for reading" in text
    assert "roughly 300 of them" in text


def test_the_report_says_the_two_decline_figures_have_one_cause(corpus):
    """A refusal reading "I searched 3 wordings and found nothing" is flagged as
    stating a quantity *and* dropped from the refusals-that-searched-first count.
    Both are the digit rule, and a reader seeing two zeros should not read them as
    two independent findings."""
    question = a_question("q9", unsupported=True, expected_entries=())
    declined = a_result(
        "q9",
        answer="I searched 3 wordings and found nothing.",
        cited=(),
        expected_entries=(),
        retrievals=({"tool": "search_entries"},),
    )
    text = render((declined,), (question,), corpus)
    assert "one rule, two figures" in text
    assert "refusals that searched first: 0" in text


def test_a_set_with_no_unsupported_questions_says_refusal_is_unmeasured(corpus):
    """Silence would read as "no fabrications", which is a figure this run cannot
    produce."""
    text = render((a_result(),), (a_question(),), corpus)
    assert "refusal is unmeasured" in text


def test_an_outlier_is_listed_with_the_interval_its_peers_occupy():
    """Reported, not scored: an outlier is a fact about the corpus, and the entry
    may be measuring something its neighbours are not."""
    peers = [
        replace(AN_ENTRY, entry_id=i, value=value)
        for i, value in enumerate((1.76, 2.0, 2.5, 3.0, 3.3), start=1)
    ]
    entries = tuple(peers) + (replace(AN_ENTRY, entry_id=99, value=10.3),)
    text = render(
        (a_result(cited=(99,), expected_entries=(99,)),),
        (a_question(expected_entries=(99,)),),
        entries,
    )
    assert "at odds with their peers" in text
    assert "entry 99 at 10.3" in text
    assert "1.76-3.3" in text


def test_a_comparison_that_could_not_be_made_is_said_rather_than_omitted():
    """An absence that reads as a pass is the failure this line exists to prevent.

    Two peers is below the floor, so nothing can be said about whether the cited
    entry is an outlier -- and the report has to say that rather than print a
    silence a reader would take for a clean result.
    """
    entries = tuple(
        replace(AN_ENTRY, entry_id=i, value=value) for i, value in enumerate((2.0, 2.1), start=1)
    ) + (replace(AN_ENTRY, entry_id=99, value=500.0),)
    text = render(
        (a_result(cited=(99,), expected_entries=(99,)),),
        (a_question(expected_entries=(99,)),),
        entries,
    )
    assert "could not be made for 1 cited entry" in text
    assert "at odds with their peers" not in text


def test_spend_in_this_session_is_reported_apart_from_the_runs_total(corpus):
    """A resumed run's ledger carries what earlier sessions spent, so one figure
    would report the run's total as this session's."""
    earlier = replace(PROVENANCE, recorded_at="2026-09-04T09:00:00+00:00")
    text = render(
        (
            a_result(provenance=earlier, spend=5_000, run_spend=5_000),
            a_result("q2", run_spend=6_000),
        ),
        (a_question(), a_question("q2")),
        corpus,
    )
    assert "spend in this session" in text
    assert "total spend across the run" in text
    assert "earlier sessions included" in text


def test_how_often_each_bound_was_reached_is_reported(corpus):
    at_bound = a_result(tool_calls=20, tool_call_limit=20, model_calls=12, call_limit=12)
    text = render((at_bound,), (a_question(),), corpus)
    assert "retrievals 1" in text and "model calls 1" in text


def test_figures_per_tag_are_given_on_request(corpus):
    tagged = a_question(tags=("comparison",))
    text = render((a_result(),), (tagged,), corpus, by_tag=True)
    assert "per tag:" in text and "comparison (1 results)" in text


def test_figures_per_entry_shape_are_given_on_request(corpus):
    """The buckets overlap on purpose: an entry lacking a scalar and a method is
    both, and forcing a choice would hide one of them."""
    text = render((a_result(),), (a_question(),), corpus, by_shape=True)
    assert "per entry shape" in text
    assert "complete (1 results)" in text


def test_a_result_whose_question_has_left_the_set_does_not_break_the_report(corpus):
    """A results file outlives the set that produced it. Refusing to report would
    let an edited set destroy a paid-for run, and inventing an expectation for the
    missing question would be worse than reporting it as unexpected."""
    text = render((a_result("gone"),), (a_question(),), corpus)
    assert "expected entries cited" in text


# -- What the branch review of group 4 found -------------------------------------


def test_figures_per_shape_survive_a_result_that_recorded_a_retrieval(corpus):
    """`--by-shape` crashed on every real results file.

    De-duplicating results by hashing them raised `TypeError`, because
    `Result.retrievals` is a tuple of dicts. Every result from an actual run
    records a retrieval, so the flag worked only on synthetic records that had
    none -- which is what the other tests here build.
    """
    with_retrieval = a_result(retrievals=({"tool": "search_entries", "property": "Cell volume"},))
    text = render((with_retrieval,), (a_question(),), corpus, by_shape=True)
    assert "per entry shape" in text


def test_a_crashed_question_is_not_scored_as_a_correct_refusal(corpus):
    """The unfalsifiable direction: an infrastructure failure inflating the
    headline refusal figure for a question the model never saw.

    A crashed question records an empty answer, an empty answer states no
    quantity, and an unsupported question that states no quantity was counted as
    correctly declined.
    """
    question = a_question("q9", unsupported=True, expected_entries=())
    crashed = a_result(
        "q9",
        answer="",
        cited=(),
        expected_entries=(),
        failure="APIConnectionError: boom",
        end_reason="provider_failure",
    )
    text = render((crashed,), (question,), corpus)
    assert "never reached the model" in text
    assert "unsupported questions declined: 1 of 1" not in text


def test_a_question_refused_on_the_run_budget_is_not_scored_as_a_fabrication(corpus):
    """Its answer is the budget message, whose dollar figures contain digits, so
    the digit rule read it as a stated quantity."""
    question = a_question("q9", unsupported=True, expected_entries=())
    refused = a_result(
        "q9",
        answer="This run has spent $1.20 against a $1.20 budget, so no further questions.",
        cited=(),
        expected_entries=(),
        end_reason="run_budget",
    )
    text = render((refused,), (question,), corpus)
    assert "never reached the model" in text
    assert "for reading" not in text


def test_a_run_where_nothing_was_answered_scores_nothing_and_says_so(corpus):
    failed = a_result(failure="APIConnectionError: boom", end_reason="provider_failure")
    text = render((failed,), (a_question(),), corpus)
    assert "nothing was answered, so there is nothing to score" in text
    assert "expected entries cited" not in text


def test_the_cost_of_a_question_that_never_reached_the_model_is_still_reported(corpus):
    """It is excluded from the scores, not from the ledger: the spend happened."""
    refused = a_result(end_reason="run_budget", spend=3_000, run_spend=3_000)
    text = render((refused,), (a_question(),), corpus)
    assert "spend in this session" in text
    assert "endings: run_budget 1" in text


def test_a_question_no_longer_in_the_set_is_left_out_of_the_asked_terms_figures(corpus):
    """A stand-in question asks about "(unknown)", which resolves to nothing, so
    each such result was an unavoidable miss in a denominator it did not belong
    in."""
    searched = a_result(retrievals=({"tool": "search_entries", "organism": "E. coli"},))
    text = render((searched, a_result("gone")), (a_question(),), corpus)
    # One of one, not one of two: the stray result is out of the denominator, and
    # its absence is stated rather than left to be inferred from the count.
    assert "searched for the asked organism: 1 of 1" in text
    assert "the current set no longer holds" in text
