"""The scoring functions: pure, exact, and the place a wrong figure looks right.

Every assertion here comes from a requirement or from the rule's own stated
direction of error, never from running the function and writing down what it said.
Where a rule classifies, both directions are tested -- the one it is meant to catch
and the one it must not.

**Mutation testing, 2026-09-07: 338 mutants, 25 knowingly left alive.** The first
run had 57 survivors and most were real -- fault seeding had passed over all of
them, because a seed encodes a belief and nobody had a belief about, for instance,
`bounds_reached` having no direct test at all. What it found: every field of the
event `bounds_reached` rebuilds could be nulled; each part of the provenance
carried "never combine two runs" alone, so nulling any one merged runs that differ
in it; the `property` key was read from a retrieval by a literal no test
exercised; a one-sided range was never given to `representative_value`, which
would have raised on it; `MIN_PEERS` was never tested at exactly the floor; and
every `continue` in the two peer functions could be a `break`, which would have
silenced the outlier check for everything cited after the first entry it could not
judge. It also found a field with no reader at all -- `Outlier.peer_median`, left
over from the median comparison ADR-0520 rejected -- which is now gone.

The 25 that remain, and why each is not worth a test: thirteen permute the
sentinel strings in the no-provenance fallback, where the contract is that the
group is *distinct* and not what it is called; five null fields of the event
`bounds_reached` rebuilds that its three properties do not read, and the
constructor requires them; two rewrite a `dict.get` default that cannot be reached,
since the index is built from the same entries the lookup keys come from; two turn
a `False` initialiser into `None`, which is falsy either way; and the rest are
equivalent boolean rewrites. Zero control-flow flips survive, which is the line
worth holding.
"""

from __future__ import annotations

import pytest
from conftest import FIXTURE

from scinumbers_ask.corpus import Entry, load
from scinumbers_ask.evaluation import Provenance, Result
from scinumbers_ask.events import EndReason
from scinumbers_ask.messages import STOP_THE_RUN
from scinumbers_ask.question_set import Question
from scinumbers_ask.repository import CorpusRepository
from scinumbers_ask.scoring import (
    MIN_PEERS,
    OUTLIER_FACTOR,
    Spread,
    asked_terms,
    bounds_reached,
    citation_score,
    cites_in_full,
    correctly_declined,
    grounding_score,
    group_of,
    grouped,
    outliers_among_peers,
    peers_too_few,
    quantity_score,
    reached_the_model,
    representative_value,
    spread,
    stability,
    unsupported_score,
)

A_PROVENANCE = Provenance(
    recorded_at="2026-09-07T09:00:00+00:00",
    model="fake/model",
    question_ceiling=600_000,
    run_budget=1_200_000,
    run_label="test",
    prompt_digest="prompt0000000001",
    corpus_digest="corpus0000000001",
    corpus_entries=6,
    code_version="git abc1234",
)


def a_result(**kwargs) -> Result:
    base = dict(
        question_id="q1",
        repeat=1,
        question="how big?",
        answer="an answer",
        provenance=A_PROVENANCE,
    )
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


def a_repo(*entry_ids: int) -> CorpusRepository:
    """A corpus holding exactly these identifiers, so `rows_for` can rank them.
    `rows_for` drops an identifier the corpus does not hold, and a rank silently
    absent is the shape of a ranking figure that reports nothing."""
    return CorpusRepository(tuple(an_entry(entry_id=i) for i in entry_ids))


def test_every_expected_entry_reaching_the_table_is_the_pass():
    """ADR-0530: the table lists every retrieved entry, so reaching it is what the
    reader gets. Prose citation is reported beside it and is no longer the pass."""
    score = citation_score(
        a_result(expected_entries=(1, 2), cited=(1,), retrieved=(1, 2)),
        a_question(expected_entries=(1, 2)),
        a_repo(1, 2),
    )
    assert score.all_expected_reached_the_table
    assert (score.expected, score.reached_the_table) == (2, 2)
    # The half that used to be the pass: one of two, and not a failure.
    assert (score.cited_expected, score.passed_over) == (1, (2,))


def test_an_expected_entry_never_retrieved_fails_the_table_check():
    """A failure of search, and the only thing that fails the headline."""
    score = citation_score(
        a_result(expected_entries=(1, 2), cited=(1,), retrieved=(1,)),
        a_question(expected_entries=(1, 2)),
        a_repo(1, 2),
    )
    assert not score.all_expected_reached_the_table
    assert score.never_retrieved == (2,)
    assert score.passed_over == ()


def test_an_admissible_citation_is_neither_a_hit_nor_unexpected():
    """Its whole job: a different property that still answers, so that a citation
    outside both lists means something."""
    score = citation_score(
        a_result(expected_entries=(1,), cited=(1, 5, 9), retrieved=(1, 5, 9)),
        a_question(expected_entries=(1,), admissible_entries=(5,)),
        a_repo(1, 5, 9),
    )
    assert score.admissible_cited == (5,)
    assert score.unexpected == (9,)
    assert score.cited_expected == 1


def test_the_rank_of_each_expected_entry_in_the_table_is_reported():
    """Reaching the table is not being seen. `rows_for` puts cited entries first,
    so an expected entry the answer passed over sits behind every cited one --
    and a driver showing five rows would not show it."""
    score = citation_score(
        a_result(expected_entries=(7,), cited=(1, 2, 3), retrieved=(1, 2, 3, 7)),
        a_question(expected_entries=(7,)),
        a_repo(1, 2, 3, 7),
    )
    assert score.ranks == (4,)
    assert score.deepest_rank == 4


def test_a_question_expecting_nothing_does_not_pass_the_table_check():
    """An unsupported question expects no entries, and a false-premise question
    expects none either. "0 of 0" must not read as a pass in the same column as an
    answer that brought every expected entry to the reader."""
    score = citation_score(
        a_result(expected_entries=(), cited=()),
        a_question(expected_entries=(), unsupported=True),
        a_repo(),
    )
    assert not score.all_expected_reached_the_table
    assert score.deepest_rank is None


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


def test_a_plain_string_matches_a_set_of_endings():
    """Load-bearing, undocumented until now, and silent if it breaks.

    Two guards compare a `Result`'s `end_reason` -- a plain string, because a
    record has to be readable without this package -- against sets of `EndReason`
    members. That works only because `EndReason` mixes in `str`, which precedes
    `Enum` in the MRO and therefore supplies `__hash__`. `Enum.__hash__` hashes the
    member *name*, so a plain `Enum` would make every one of those comparisons
    return `False`: the report would stop warning about closed runs and the scoring
    would start scoring questions the model never saw, with nothing raising.
    """
    assert issubclass(EndReason, str)
    assert EndReason.__hash__ is str.__hash__
    assert "run_budget" in {EndReason.RUN_BUDGET}
    assert all(str(reason) in STOP_THE_RUN for reason in STOP_THE_RUN)


@pytest.mark.parametrize("closing", sorted(str(reason) for reason in STOP_THE_RUN))
def test_no_ending_that_closes_the_run_is_scored_as_the_models_answer(closing):
    """Each of these records the agent's own notice as the answer text.

    The set had its own copy here and went stale the day `PROVIDER_LIMIT` arrived:
    a question refused because the key had no credit left was scored, so an unpaid
    invoice was reported as the model's behaviour. Parametrised over the shared set
    so the next ending added to it cannot slip past this test either.
    """
    assert not reached_the_model(a_result(end_reason=closing, answer="no credit left"))


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


def all_ids(population: tuple[Entry, ...]) -> tuple[int, ...]:
    """Every entry in the population, as the question's expected list.

    Under ADR-0540 peers come from the question's expected entries rather than from
    the whole corpus, so a test that wants the old "compare against everything
    here" shape says so explicitly.
    """
    return tuple(entry.entry_id for entry in population)


def yeast_population() -> tuple[Entry, ...]:
    """The case this check exists for, from the specimen answers of 2026-09-04:
    eight entries between 1.76 and 3.3, and one at 10.3."""
    peers = [
        an_entry(entry_id=i, value=value)
        for i, value in enumerate((1.76, 2.0, 2.2, 2.5, 2.7, 3.0, 3.3, 2.9), start=1)
    ]
    return tuple(peers) + (an_entry(entry_id=99, value=10.3),)


def test_the_entry_that_motivated_the_check_is_flagged():
    """10.3 against a peer maximum of 3.3 is 3.1 times outside. An order-of-
    magnitude threshold would have missed the very answer this exists for."""
    (flagged,) = outliers_among_peers((99,), all_ids(yeast_population()), yeast_population())
    assert flagged.entry_id == 99
    assert flagged.peer_low == 1.76 and flagged.peer_high == 3.3
    assert flagged.outside_by > OUTLIER_FACTOR


def test_an_entry_inside_its_peers_interval_is_not_flagged():
    """The other direction. Every entry in the population must pass, or the check
    reports a list nobody can act on."""
    population = yeast_population()
    inside = tuple(entry.entry_id for entry in population if entry.entry_id != 99)
    assert outliers_among_peers(inside, all_ids(population), population) == ()


def test_an_entry_just_inside_the_factor_is_not_flagged():
    """The boundary is a choice, so it is asserted from the rule rather than from
    the code: at the factor exactly, an entry is not outside it."""
    peers = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=2.0 * OUTLIER_FACTOR),)
    assert outliers_among_peers((99,), all_ids(population), population) == ()


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
    assert outliers_among_peers((99,), all_ids(population), population) == ()


def test_a_value_far_below_its_peers_is_flagged_too():
    peers = tuple(an_entry(entry_id=i, value=10.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=0.5),)
    (flagged,) = outliers_among_peers((99,), all_ids(population), population)
    assert flagged.outside_by > OUTLIER_FACTOR


def test_an_entry_with_a_twin_still_counts_its_twin_as_a_peer():
    """The peer index groups by value, so removing "this entry's value" has to
    remove one copy and not every match -- two entries can record the same number,
    and dropping both would shrink the population the floor is measured against.
    """
    twins = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS + 2))
    population = twins + (an_entry(entry_id=99, value=100.0),)
    assert peers_too_few((1,), all_ids(population), population) == ()
    (flagged,) = outliers_among_peers((99,), all_ids(population), population)
    assert flagged.peers == MIN_PEERS + 1


def test_a_property_with_too_few_peers_is_not_judged_and_says_so():
    """An absence that reads as a pass is the failure this exists to prevent."""
    peers = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS))
    population = peers + (an_entry(entry_id=99, value=100.0),)
    assert outliers_among_peers((99,), all_ids(population), population) == ()
    assert peers_too_few((99,), all_ids(population), population) == (99,)


def test_peers_are_the_same_property_for_the_same_organism():
    """Another organism's entries are not peers: comparing across them would flag
    every legitimate difference between species."""
    others = tuple(
        an_entry(entry_id=i, value=2.0, organism="Bacteria Escherichia coli")
        for i in range(1, MIN_PEERS + 2)
    )
    population = others + (an_entry(entry_id=99, value=100.0),)
    assert outliers_among_peers((99,), all_ids(population), population) == ()
    assert peers_too_few((99,), all_ids(population), population) == (99,)


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
    assert peers_too_few((99,), all_ids(population), population) == (99,)


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


# -- What mutation testing found -------------------------------------------------


def test_a_matching_property_argument_counts_as_looking_for_the_property():
    """The `property` key was read from the retrieval by a literal no test
    exercised: every test here searched by *keyword*, or by a property that was
    meant not to match. Rewriting the literal to nonsense changed nothing."""
    repo = CorpusRepository(load(FIXTURE))
    result = a_result(retrievals=({"tool": "search_entries", "property": "Cell diameter"},))
    assert asked_terms(result, a_question(), repo).searched_property


def test_the_grounding_score_carries_every_signal_the_agent_emitted():
    """Each field was a pass-through that no assertion read, so any of them could
    have been dropped. `ungrounded_refusal` in particular decides whether a
    refusal can be a correct decline."""
    result = a_result(
        ungrounded_refusal=True,
        claimed_searching=True,
        retrievals=({"tool": "search_entries"}, {"tool": "list_values"}),
    )
    scored = grounding_score(result)
    assert scored.ungrounded_refusal is True
    assert scored.claimed_searching is True
    assert scored.retrievals == 2


def test_stability_reports_the_entries_each_repeat_cited():
    """The verdict is the headline and the sets are the evidence for it; a reader
    told "unstable" and shown nothing cannot act on it."""
    results = (a_result(repeat=1, cited=(1, 2)), a_result(repeat=2, cited=(1,)))
    (reported,) = stability(results)
    assert reported.cited_sets == ((1, 2), (1,))


def test_each_bound_is_read_from_the_endings_own_definition():
    """`bounds_reached` had no direct test at all -- the only assertions were on
    the report's rendering of it, so every field of the event it rebuilds could
    have been dropped or nulled."""
    at_tools = a_result(tool_calls=20, tool_call_limit=20)
    at_calls = a_result(model_calls=12, call_limit=12)
    at_spend = a_result(spend=600_000, spend_ceiling=600_000)
    assert bounds_reached(at_tools).at_tool_bound
    assert bounds_reached(at_calls).at_retrieval_bound
    assert bounds_reached(at_spend).at_spend_ceiling


def test_room_to_spare_is_not_reported_as_a_bound():
    """The other direction, and the one that matters: an answer produced with room
    left is a different thing from one produced at a limit, and reporting every
    answer as bounded would retire the distinction."""
    with_room = a_result(
        tool_calls=3,
        tool_call_limit=20,
        model_calls=2,
        call_limit=12,
        spend=1_000,
        spend_ceiling=600_000,
    )
    reached = bounds_reached(with_room)
    assert not (reached.at_tool_bound or reached.at_retrieval_bound or reached.at_spend_ceiling)


def test_a_bound_of_zero_is_not_a_bound_that_was_reached():
    """An unrecorded limit reads as zero, and `0 >= 0` would report every question
    as having exhausted a limit nobody set."""
    unrecorded = a_result(tool_calls=0, tool_call_limit=0, model_calls=0, call_limit=0)
    reached = bounds_reached(unrecorded)
    assert not (reached.at_tool_bound or reached.at_retrieval_bound)


def test_a_result_with_no_provenance_is_never_grouped_with_one_that_has_it():
    """A record that cannot say what produced it cannot be compared with one that
    can, so it gets its own group instead of joining any other -- the alternative
    is averaging it into figures it may not belong to."""
    known = a_result(provenance=A_PROVENANCE)
    unknown = a_result(question_id="q2", provenance=None)
    groups = grouped((known, unknown))
    assert len(groups) == 2
    assert group_of(unknown) != group_of(known)


def test_results_from_the_same_run_share_one_group():
    """The other direction: grouping that separated identical runs would print
    every question apart and refuse to combine any of them."""
    assert len(grouped((a_result(), a_result(question_id="q2")))) == 1


def test_a_one_sided_range_has_no_representative_value():
    """594 entries in the corpus record a bound rather than a range. Averaging one
    bound with a missing one is not a midpoint, and the arithmetic would raise
    rather than answer."""
    assert representative_value(an_entry(value=None, range_low=2.0, range_high=None)) is None
    assert representative_value(an_entry(value=None, range_high=2.0, range_low=None)) is None


def test_a_midpoint_of_exactly_zero_is_not_judged():
    """The boundary the rule states: zero is not judged, and a range of -1 to 1
    has a midpoint of exactly zero."""
    assert representative_value(an_entry(value=None, range_low=-1.0, range_high=1.0)) is None


def test_a_midpoint_below_one_is_still_a_value():
    """The other side of that boundary. Sub-unit values are ordinary here -- cell
    volumes in cubic micrometres -- and refusing them would silence the check on
    much of the corpus."""
    assert representative_value(an_entry(value=None, range_low=0.4, range_high=0.6)) == 0.5


def test_exactly_the_peer_floor_is_enough_to_judge():
    """`MIN_PEERS` is the number needed, not the number to exceed. Off by one, the
    check goes quiet on every population sitting exactly at the floor."""
    peers = tuple(an_entry(entry_id=i, value=2.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=100.0),)
    assert peers_too_few((99,), all_ids(population), population) == ()
    assert len(outliers_among_peers((99,), all_ids(population), population)) == 1


def test_the_factor_reported_is_how_far_outside_the_entry_sits():
    """Asserted as a number, not just as "more than the threshold": the figure is
    what a reader judges the entry by, and a multiplication in place of the
    division would still have been "more than the threshold"."""
    (flagged,) = outliers_among_peers((99,), all_ids(yeast_population()), yeast_population())
    assert flagged.outside_by == pytest.approx(10.3 / 3.3)


def test_a_value_at_the_low_boundary_is_not_flagged():
    """The low side of the interval, which only the high side had covered."""
    peers = tuple(an_entry(entry_id=i, value=4.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=4.0 / OUTLIER_FACTOR),)
    assert outliers_among_peers((99,), all_ids(population), population) == ()


def test_an_unjudgeable_citation_does_not_stop_the_ones_after_it():
    """Skipping the rest of the citation list instead of one entry: every
    `continue` here could have been a `break`, and a single entry with no usable
    number would have silenced the check for everything cited alongside it."""
    population = yeast_population() + (an_entry(entry_id=50, value=None),)
    flagged = outliers_among_peers((50, 99), all_ids(population), population)
    assert [outlier.entry_id for outlier in flagged] == [99]
    assert peers_too_few((50, 99), all_ids(population), population) == (50,)


@pytest.mark.parametrize(
    "field,other",
    [
        ("model", "another/model"),
        ("prompt_digest", "prompt0000000002"),
        ("corpus_digest", "corpus0000000002"),
        ("corpus_entries", 7),
        ("code_version", "git def5678"),
    ],
)
def test_every_part_of_the_provenance_separates_one_run_from_another(field, other):
    """ "Never combined across model, prompt or corpus" is a requirement, and each
    field carried it alone. Nulling any one of them merged two runs that differ in
    it -- the figures would be averaged and the report would say they came from one
    system.
    """
    from dataclasses import replace as with_field

    first = a_result()
    second = a_result(question_id="q2", provenance=with_field(A_PROVENANCE, **{field: other}))
    assert group_of(first) != group_of(second)
    assert len(grouped((first, second))) == 2


def test_a_citation_the_corpus_does_not_hold_does_not_stop_the_check():
    """The other `continue` in the loop. One stale identifier in a citation list
    would have silenced the outlier check for every entry cited after it."""
    population = yeast_population()
    flagged = outliers_among_peers((999999, 99), all_ids(population), population)
    assert [outlier.entry_id for outlier in flagged] == [99]


def test_the_factor_below_the_interval_is_also_how_far_outside_it_sits():
    """The low side of the figure, asserted as a number for the reason the high
    side is: a multiplication would also have been "more than the threshold"."""
    peers = tuple(an_entry(entry_id=i, value=10.0) for i in range(1, MIN_PEERS + 1))
    population = peers + (an_entry(entry_id=99, value=2.0),)
    (flagged,) = outliers_among_peers((99,), all_ids(population), population)
    assert flagged.outside_by == pytest.approx(10.0 / 2.0)


def test_neither_a_lonely_entry_nor_an_ordinary_one_stops_the_check_after_it():
    """The last two `continue`s in the loop, and they matter for the same reason
    the others do: the outlier is usually not the first entry an answer cites.

    The first cited entry here has no peers at all, the second sits inside its
    peers' interval, and the third is the outlier. With either `continue` turned
    into a `break`, the check reports nothing at all for this answer -- which is
    indistinguishable from an answer with nothing wrong in it.
    """
    # Lonely by *unit*, which is what separates pools under ADR-0540. It used to
    # be lonely by property, and that no longer isolates anything: a pool is keyed
    # on organism and unit, because property wording is exactly what made the old
    # rule judge nothing at all.
    lonely = an_entry(entry_id=40, property="Doubling time", units="min", value=30.0)
    population = yeast_population() + (lonely,)
    flagged = outliers_among_peers((40, 1, 99), all_ids(population), population)
    assert [outlier.entry_id for outlier in flagged] == [99]


def test_every_citation_that_could_not_be_judged_is_reported_not_just_the_first():
    """The count is what the report puts in front of a reader, so stopping at the
    first would understate how much of an answer went unchecked."""
    population = yeast_population() + (
        an_entry(entry_id=50, value=None),
        an_entry(entry_id=51, value=None),
    )
    assert peers_too_few((50, 51), all_ids(population), population) == (50, 51)


def test_an_entry_the_question_does_not_expect_is_not_a_peer():
    """The claim ADR-0540 actually makes, and nothing asserted it.

    Every other test here passes the whole population as the expected list, so
    removing the restriction entirely left the suite green -- the negative case
    never varied the dimension the rule reads. Here the corpus holds eight further
    entries of the same organism and unit that the question does *not* expect, and
    they must not enter the pool: with them, 10.3 sits inside a 1.76-40.0 interval
    and nothing is flagged.
    """
    expected = yeast_population()
    strangers = tuple(
        an_entry(entry_id=i, value=value)
        for i, value in enumerate((12.0, 15.0, 20.0, 25.0, 30.0, 35.0, 38.0, 40.0), start=200)
    )
    population = expected + strangers
    cited, wanted = (99,), all_ids(expected)

    (flagged,) = outliers_among_peers(cited, wanted, population)
    assert flagged.entry_id == 99
    assert flagged.peer_high == 3.3, "a stranger entered the pool and raised the interval"
    assert flagged.peers == 8

    # And the other direction: expecting them makes 10.3 ordinary, which is what
    # the expected list is for -- it decides what this entry is being compared to.
    assert outliers_among_peers(cited, all_ids(population), population) == ()


def test_an_unexpected_citation_is_still_judged_against_what_was_expected():
    """A cited entry need not itself be expected. It keeps the whole pool, because
    it is compared against the question's entries rather than its own neighbours --
    which is what lets the check see a citation the set did not anticipate."""
    # 30.0: the expected pool runs to 10.3 (entry 99 is in it), so the value has to
    # clear 2x that to be an outlier at all. 12.0 would not, and would test nothing.
    population = yeast_population() + (an_entry(entry_id=300, value=30.0),)
    wanted = all_ids(yeast_population())
    (flagged,) = outliers_among_peers((300,), wanted, population)
    assert flagged.entry_id == 300
    # All nine expected entries, none removed: 300 is not in the pool, so there is
    # no copy of it to take out. Removing a coincidentally equal value instead was
    # a real defect, and only a citation from outside the expected list shows it.
    assert flagged.peers == 9
    assert flagged.peer_high == 10.3
