"""The scoring functions: pure, exact, and the place a wrong figure looks right.

Every assertion here comes from a requirement or from the rule's own stated
direction of error, never from running the function and writing down what it said.
Where a rule classifies, both directions are tested -- the one it is meant to catch
and the one it must not.
"""

from __future__ import annotations

import pytest
from conftest import FIXTURE

from scinumbers_ask.corpus import Entry, load
from scinumbers_ask.evaluation import Result
from scinumbers_ask.question_set import Question
from scinumbers_ask.repository import CorpusRepository
from scinumbers_ask.scoring import (
    MIN_PEERS,
    OUTLIER_FACTOR,
    Spread,
    asked_terms,
    citation_score,
    cites_in_full,
    correctly_declined,
    grounding_score,
    outliers_among_peers,
    peers_too_few,
    quantity_score,
    representative_value,
    spread,
    stability,
    unsupported_score,
)


def a_result(**kwargs) -> Result:
    base = dict(question_id="q1", repeat=1, question="how big?", answer="an answer")
    base.update(kwargs)
    return Result(**base)


def a_question(**kwargs) -> Question:
    base = dict(
        question_id="q1",
        question="how big?",
        asked_properties=("Cell diameter",),
        asked_organisms=("Bacteria Escherichia coli",),
        expected_entries=(100002,),
    )
    base.update(kwargs)
    return Question(**base)


def an_entry(**kwargs) -> Entry:
    base = dict(
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
    base.update(kwargs)
    return Entry(**base)


# -- 4.1: cited against expected -------------------------------------------------


def test_an_answer_citing_every_expected_entry_scores_as_such():
    score = citation_score(a_result(expected_entries=(1, 2), cited=(1, 2), retrieved=(1, 2)))
    assert score.all_expected_cited
    assert (score.expected, score.cited_expected) == (2, 2)


def test_an_unexpected_citation_is_reported_and_is_not_an_error():
    """The corpus may support the answer through entries the set does not list: a
    question set is a claim about which entries suffice, not about which exist."""
    score = citation_score(a_result(expected_entries=(1,), cited=(1, 9), retrieved=(1, 9)))
    assert score.unexpected == (9,)
    assert score.all_expected_cited


def test_a_missed_entry_is_split_by_whether_it_was_ever_retrieved():
    """Two different failures -- one of selection, one of search -- and a single
    "missed" count would hide which is happening."""
    score = citation_score(a_result(expected_entries=(1, 2), cited=(), retrieved=(1,)))
    assert score.passed_over == (1,)
    assert score.never_retrieved == (2,)


def test_a_question_expecting_nothing_is_not_reported_as_fully_cited():
    """An unsupported question expects no entries, and "0 of 0" must not read as a
    pass in the same column as an answer that cited everything asked of it."""
    assert not citation_score(a_result(expected_entries=(), cited=())).all_expected_cited


# -- 4.2: the asked organism and property ----------------------------------------


@pytest.fixture
def repo() -> CorpusRepository:
    return CorpusRepository(load(FIXTURE))


def test_an_abbreviated_search_counts_as_searching_for_the_organism(repo):
    """Resolved the way the corpus's own search resolves it. String equality would
    score a search for "E. coli" as not a search for "Escherichia coli" -- the
    resolution's success reported as the agent's failure."""
    result = a_result(retrievals=({"tool": "search_entries", "organism": "E. coli"},))
    assert asked_terms(result, a_question(), repo).searched_organism


def test_searching_for_another_organism_does_not_count(repo):
    """The direction that matters: a right number for the wrong organism cites
    correctly and answers a different question."""
    result = a_result(retrievals=({"tool": "search_entries", "organism": "yeast"},))
    assert not asked_terms(result, a_question(), repo).searched_organism


def test_a_keyword_counts_as_looking_for_the_property(repo):
    """The tools accept either, and an agent that found the right entries by
    keyword has still looked for the property."""
    result = a_result(retrievals=({"tool": "search_entries", "keyword": "Cell diameter"},))
    assert asked_terms(result, a_question(), repo).searched_property


def test_a_search_for_an_unrelated_property_does_not_count(repo):
    result = a_result(retrievals=({"tool": "search_entries", "property": "Doubling time"},))
    assert not asked_terms(result, a_question(), repo).searched_property


def test_a_question_asking_about_two_organisms_counts_either(repo):
    """A comparison asks about both, so searching for one of them is looking for
    what was asked. Requiring both would score the first retrieval of a comparison
    as a miss."""
    question = a_question(asked_organisms=("Bacteria Escherichia coli", "Planarian"))
    result = a_result(retrievals=({"tool": "search_entries", "organism": "E. coli"},))
    assert asked_terms(result, question, repo).searched_organism


def test_what_the_agent_settled_on_is_counted_apart_from_what_it_searched(repo):
    """An agent can search correctly and cite a neighbour, or never search for the
    organism and still reach the right entry by keyword. One figure could not say
    which happened."""
    result = a_result(
        retrievals=({"tool": "search_entries", "organism": "E. coli"},), cited=(100002,)
    )
    scored = asked_terms(result, a_question(), repo)
    assert scored.searched_organism
    assert (scored.cited, scored.cited_with_organism, scored.cited_with_property) == (1, 1, 1)


def test_a_citation_the_corpus_does_not_hold_is_not_counted_as_carrying_anything(repo):
    result = a_result(cited=(999999,))
    scored = asked_terms(result, a_question(), repo)
    assert (scored.cited, scored.cited_with_organism) == (1, 0)


# -- 4.3: whether a quantity was stated ------------------------------------------


def test_a_citation_and_a_digit_are_both_signals():
    assert quantity_score(a_result(answer="about 1.0 um [[100002]]")).by_citation
    assert quantity_score(a_result(answer="about 1.0 um")).by_digit
    assert quantity_score(a_result(answer="about 1.0 um")).states_quantity


def test_prose_with_no_number_at_all_states_no_quantity():
    answer = "The corpus does not record this quantity for that organism."
    assert not quantity_score(a_result(answer=answer)).states_quantity


def test_an_unsupported_question_answered_with_a_figure_is_a_fabrication():
    scored = unsupported_score(a_result(answer="roughly 300 of them"))
    assert scored.fabricated and not scored.declined


def test_an_unsupported_question_declined_in_words_alone_is_a_decline():
    scored = unsupported_score(a_result(answer="I could not find this in the corpus."))
    assert scored.declined and not scored.fabricated


def test_the_quantity_rule_over_flags_and_that_is_the_direction_chosen():
    """A refusal reading "I searched 2 wordings" is marked as stating a quantity.

    Asserted rather than merely accepted: a wrongly flagged decline is a line in a
    list someone reads, and a wrongly passed fabrication is the failure the project
    exists to prevent. If this test ever has to change, the cheap direction has
    been swapped for the expensive one.
    """
    scored = unsupported_score(a_result(answer="I searched 2 wordings and found nothing."))
    assert scored.fabricated


# -- 4.4: the agent's own warnings ------------------------------------------------


def test_the_agents_warnings_are_counted_not_recomputed():
    result = a_result(unknown_citations=(999999,), unretrieved_citations=(5,))
    scored = grounding_score(result)
    assert scored.grounding_failures == 2
    assert scored.unknown_citations == (999999,)


def test_a_refusal_that_searched_first_is_a_correct_decline():
    result = a_result(answer="Not in the corpus.", retrievals=({"tool": "search_entries"},))
    assert correctly_declined(result)


def test_a_refusal_with_no_search_behind_it_is_never_a_correct_decline():
    """ "Not in the corpus" and "not looked for" are different statements, and an
    answer cannot be read to tell them apart."""
    result = a_result(answer="Not in the corpus.", ungrounded_refusal=True)
    assert not correctly_declined(result)
    assert not correctly_declined(a_result(answer="Not in the corpus.", retrievals=()))


def test_a_record_claiming_both_a_refusal_and_a_search_is_scored_conservatively():
    """A state the agent cannot produce, and a record can.

    `UngroundedRefusal` means no retrieval happened, so the two signals agree in
    anything the agent writes -- fault seeding showed that dropping the flag from
    this rule changes nothing, because the retrieval count alone carries it. The
    clause stays because scoring reads *files*, which can be hand-edited or
    written by another tool, and because a later widening of what counts as
    ungrounded would otherwise silently start passing here. Conservative in the
    direction that matters: a refusal the agent itself called ungrounded is never
    promoted to a correct decline.
    """
    contradictory = a_result(
        answer="Not in the corpus.",
        ungrounded_refusal=True,
        retrievals=({"tool": "search_entries"},),
    )
    assert not correctly_declined(contradictory)


def test_an_answer_stating_a_quantity_is_not_a_decline_however_it_was_reached():
    result = a_result(answer="about 1.0 um", retrievals=({"tool": "search_entries"},))
    assert not correctly_declined(result)


# -- 4.6: a follow-up standing on its own ----------------------------------------


def test_a_follow_up_stating_a_figure_with_no_citation_does_not_cite_in_full():
    assert not cites_in_full(a_result(answer="about 1.0 um", cited=()))


def test_a_follow_up_that_cites_its_own_entries_does():
    assert cites_in_full(a_result(answer="about 1.0 um [[100002]]", cited=(100002,)))


def test_a_follow_up_that_states_no_quantity_is_not_marked_for_citing_nothing():
    """A refusal has nothing to cite, and scoring it as failing to cite in full
    would count the same refusal twice under two different failures."""
    assert cites_in_full(a_result(answer="Not in the corpus.", cited=()))


# -- 4.5: the outlier check ------------------------------------------------------


def yeast_population() -> tuple[Entry, ...]:
    """The case this check exists for, from the reviewer page of 2026-09-04:
    eight entries between 1.76 and 3.3, and one at 10.3."""
    peers = [
        an_entry(entry_id=i, value=value)
        for i, value in enumerate((1.76, 2.0, 2.2, 2.5, 2.7, 3.0, 3.3, 2.9), start=1)
    ]
    return tuple(peers) + (an_entry(entry_id=99, value=10.3),)


def test_the_entry_that_motivated_the_check_is_flagged():
    """10.3 against a peer maximum of 3.3 is 3.1 times outside. An order-of-
    magnitude threshold would have missed the very answer this exists for."""
    (flagged,) = outliers_among_peers((99,), yeast_population())
    assert flagged.entry_id == 99
    assert flagged.peer_low == 1.76 and flagged.peer_high == 3.3
    assert flagged.outside_by > OUTLIER_FACTOR


def test_an_entry_inside_its_peers_interval_is_not_flagged():
    """The other direction. Every entry in the population must pass, or the check
    reports a list nobody can act on."""
    population = yeast_population()
    inside = tuple(entry.entry_id for entry in population if entry.entry_id != 99)
    assert outliers_among_peers(inside, population) == ()


def test_an_entry_just_inside_the_factor_is_not_flagged():
    """The boundary is a choice, so it is asserted from the rule rather than from
    the code: at the factor exactly, an entry is not outside it."""
    peers = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=2.0 * OUTLIER_FACTOR),)
    assert outliers_among_peers((99,), population) == ()


def test_a_value_inside_a_skewed_population_is_not_flagged_though_it_beats_the_median():
    """Why the comparison is against the interval and not the median.

    Peers at 1, 1, 1, 1 and 10: the median is 1 and the observed range is 1 to 10.
    A value of 5 is five times the median and yet well inside what the corpus
    already records for this quantity, so it is not an outlier. A median rule would
    flag it -- and on these small skewed populations the median is pulled by the
    very entry the check is looking for, while the interval is not.
    """
    peers = tuple(
        an_entry(entry_id=i, value=value)
        for i, value in enumerate((1.0, 1.0, 1.0, 1.0, 10.0), start=1)
    )
    population = peers + (an_entry(entry_id=99, value=5.0),)
    assert outliers_among_peers((99,), population) == ()


def test_a_value_far_below_its_peers_is_flagged_too():
    peers = tuple(an_entry(entry_id=i, value=10.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=0.5),)
    (flagged,) = outliers_among_peers((99,), population)
    assert flagged.outside_by > OUTLIER_FACTOR


def test_a_property_with_too_few_peers_is_not_judged_and_says_so():
    """An absence that reads as a pass is the failure this exists to prevent."""
    peers = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS))
    population = peers + (an_entry(entry_id=99, value=100.0),)
    assert outliers_among_peers((99,), population) == ()
    assert peers_too_few((99,), population) == (99,)


def test_peers_are_the_same_property_for_the_same_organism():
    """Another organism's entries are not peers: comparing across them would flag
    every legitimate difference between species."""
    others = tuple(
        an_entry(entry_id=i, value=2.0, organism="Bacteria Escherichia coli")
        for i in range(1, MIN_PEERS + 2)
    )
    population = others + (an_entry(entry_id=99, value=100.0),)
    assert outliers_among_peers((99,), population) == ()
    assert peers_too_few((99,), population) == (99,)


def test_a_zero_or_negative_value_is_not_judged():
    """A ratio across zero is meaningless, and a mark firing on arithmetic rather
    than on evidence is worse than no mark -- the rule `Entry.spans_implausibly`
    already applies to the corpus's own bounds."""
    assert representative_value(an_entry(value=0.0)) is None
    assert representative_value(an_entry(value=-1.0)) is None


def test_an_entry_with_only_a_range_is_compared_by_its_midpoint():
    assert representative_value(an_entry(value=None, range_low=1.0, range_high=3.0)) == 2.0


def test_an_entry_with_no_usable_number_is_reported_as_unjudged():
    peers = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS + 2))
    population = peers + (an_entry(entry_id=99, value=None),)
    assert peers_too_few((99,), population) == (99,)


# -- 4.7: spread and stability ----------------------------------------------------


def test_a_spread_reports_the_aggregate_and_how_far_it_moved():
    assert spread((1.0, 3.0, 2.0)) == Spread(mean=2.0, low=1.0, high=3.0, repeats=3)


def test_a_spread_over_no_values_is_unknown_rather_than_zero():
    """Zero would be a figure, and a figure here would be read as a measurement."""
    assert spread(()) is None


def test_a_question_citing_different_entries_across_repeats_is_unstable():
    """Averaging the repeats away would hide exactly the questions where a change
    cannot be told from luck."""
    results = (
        a_result(repeat=1, cited=(1, 2)),
        a_result(repeat=2, cited=(1,)),
    )
    (reported,) = stability(results)
    assert reported.unstable and reported.repeats == 2


def test_a_question_citing_the_same_entries_in_a_different_order_is_stable():
    """Citation order is not a difference in what the answer rests on."""
    results = (a_result(repeat=1, cited=(1, 2)), a_result(repeat=2, cited=(2, 1)))
    (reported,) = stability(results)
    assert not reported.unstable


def test_each_question_is_reported_separately():
    results = (
        a_result(question_id="q1", repeat=1, cited=(1,)),
        a_result(question_id="q1", repeat=2, cited=(2,)),
        a_result(question_id="q2", repeat=1, cited=(3,)),
    )
    reported = {item.question_id: item for item in stability(results)}
    assert reported["q1"].unstable
    assert not reported["q2"].unstable
