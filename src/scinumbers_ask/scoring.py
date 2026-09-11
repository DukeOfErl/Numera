"""Every score that needs no model and no parser over prose.

Pure functions from records to figures: no I/O, no corpus loading, no clock. That
is what lets a scoring rule be changed and the whole baseline re-scored without
asking a single question again -- the difference between a rule being cheap to fix
and being unaffordable.

**Nothing here reads a number out of an answer.** `states_quantity` asks whether a
digit is present, which is a character test; the value-and-unit check is deferred
with its reasoning in the proposal. Everything else reads the events, the citation
set, the question set and the corpus.

**Which direction each rule errs, said where the rule is.** Several of these
classify, and a change to any of them moves records both ways. Each function says
which direction it chose and why, and `4.10` counts both directions against the
first real run rather than trusting the choice.
"""

from __future__ import annotations

from dataclasses import dataclass

from .citations import citations
from .corpus import Entry
from .entries_table import rows_for
from .evaluation import Result
from .events import EndReason, QuestionEnded
from .messages import STOP_THE_RUN
from .question_set import Question
from .repository import CorpusRepository


@dataclass(frozen=True)
class CitationScore:
    """What an answer brought to the reader, against what the question expected.

    Tasks 4.1 and 4.13, under ADR-0530. **An expected entry discharges by reaching
    the entries table, not by being cited in the prose.** The table lists every
    retrieved entry, cited ones first, so reaching it is what the reader actually
    gets; requiring prose citation of every expected entry fails every good answer
    to a question the corpus answers ten times over -- and after the expected lists
    were widened to cover every spelling of a property, that is most of them.

    Both figures are kept. Prose citation is what a reader follows, so it stays as
    a secondary; it is simply no longer the pass.
    """

    expected: int
    #: Expected and retrieved, so the reader was shown it. The headline.
    reached_the_table: int
    #: Expected and never retrieved. A failure of *search*.
    never_retrieved: tuple[int, ...]
    #: Expected and cited in the prose. Secondary to reaching the table.
    cited_expected: int
    #: Expected, retrieved, not cited. **Not an error on its own**: with the
    #: expected set covering every spelling of a property, an answer citing some
    #: and leaving the rest to the table is the intended shape. Task 6.10 asks a
    #: judge whether a particular omission changed the answer.
    passed_over: tuple[int, ...]
    #: Cited and recorded as admissible -- a different property that still answers.
    #: Neither a hit nor an error; counted apart so `unexpected` means something.
    admissible_cited: tuple[int, ...]
    #: Cited and in neither list. Reported, never counted as an error: the corpus
    #: may support an answer through entries the set does not record.
    unexpected: tuple[int, ...]
    #: Where each expected entry sits in the table the reader would have seen,
    #: ascending. An entry at rank 40 reached the table and no reader will see it,
    #: which is a *ranking* failure and needs a different fix from a search one.
    ranks: tuple[int, ...]

    @property
    def all_expected_reached_the_table(self) -> bool:
        """The pass. False when a question expects nothing -- a false-premise
        question is scored on its admissible list, not on this."""
        return self.expected > 0 and not self.never_retrieved

    @property
    def deepest_rank(self) -> int | None:
        """How far down a reader would have had to look. `None` when none reached."""
        return max(self.ranks) if self.ranks else None


def citation_score(result: Result, question: Question, repo: CorpusRepository) -> CitationScore:
    """The question and the repository are required, not optional.

    `admissible_entries` lives on the question and is deliberately not copied into
    a result, and the rank comes from the table's own ordering. A signature that
    defaulted either would let a caller silently score without them -- every
    admissible citation reported as unexpected, every rank absent -- and the
    figures would look ordinary.
    """
    expected = set(result.expected_entries)
    cited = set(result.cited)
    retrieved = set(result.retrieved)
    admissible = set(question.admissible_entries)

    # The table as a reader would have seen it, from the module that builds it
    # rather than a second ordering that can drift from the first.
    order = [
        row.entry_id for row in rows_for(repo, result.cited, result.retrieved, result.question)
    ]
    place = {entry_id: index + 1 for index, entry_id in enumerate(order)}

    return CitationScore(
        expected=len(expected),
        reached_the_table=len(expected & retrieved),
        never_retrieved=tuple(sorted(expected - retrieved)),
        cited_expected=len(expected & cited),
        passed_over=tuple(sorted((expected & retrieved) - cited)),
        admissible_cited=tuple(sorted(cited & admissible)),
        unexpected=tuple(sorted(cited - expected - admissible)),
        ranks=tuple(sorted(place[e] for e in expected & retrieved if e in place)),
    )


@dataclass(frozen=True)
class AskedTerms:
    """Whether the agent looked for what was asked, and what it settled on. 4.2.

    Two figures, kept apart because they fail differently: an agent can search
    correctly and cite a neighbour, or never search for the organism and still
    reach the right entry through a keyword.
    """

    searched_organism: bool
    searched_property: bool
    cited: int
    cited_with_organism: int
    cited_with_property: int


def asked_terms(result: Result, question: Question, repo: CorpusRepository) -> AskedTerms:
    """Resolved the way the corpus's own search resolves, never by string equality.

    **This over-credits a broad search argument.** A retrieval for the property
    "Cell" selects `Cell volume` among many others, so it agrees with an asked
    property of `Cell volume` and counts as having searched for it. The strict
    alternative -- requiring the argument to select no more than the asked term
    does -- would score a legitimate broadening as a miss, and a search that
    starts wide and narrows is normal behaviour rather than an error. So the
    lenient direction is taken here and task 4.10 counts both directions against
    the first real run; do not tighten it without that measurement.
    """
    asked_organisms = {
        stored for term in question.asked_organisms for stored in repo.resolve_organism(term)
    }
    asked_properties = {
        stored for term in question.asked_properties for stored in repo.resolve_property(term)
    }

    searched_organism = False
    searched_property = False
    for retrieval in result.retrievals:
        organism = retrieval.get("organism")
        if organism and repo.resolve_organism(str(organism)) & asked_organisms:
            searched_organism = True
        # A property or a keyword: the corpus tools accept either, and an agent
        # that found the right entries by keyword has still looked for the
        # property. Scoring only the `property` argument would call that a miss.
        for key in ("property", "keyword"):
            term = retrieval.get(key)
            if term and repo.resolve_property(str(term)) & asked_properties:
                searched_property = True

    # `get` answers with a `FullEntry` wrapper, not an `Entry`; reading the fields
    # off the wrapper would have raised rather than quietly scoring zero, but only
    # once a test cited a real entry.
    cited_entries = [
        found.entry for found in (repo.get(i) for i in result.cited) if found is not None
    ]
    return AskedTerms(
        searched_organism=searched_organism,
        searched_property=searched_property,
        cited=len(result.cited),
        cited_with_organism=sum(1 for entry in cited_entries if entry.organism in asked_organisms),
        cited_with_property=sum(1 for entry in cited_entries if entry.property in asked_properties),
    )


@dataclass(frozen=True)
class QuantityScore:
    """Whether an answer stated a quantity at all. Task 4.3."""

    by_citation: bool
    by_digit: bool

    @property
    def states_quantity(self) -> bool:
        return self.by_citation or self.by_digit


def quantity_score(result: Result) -> QuantityScore:
    """Two cheap signals, and a flag on either.

    A character test, not a number parser -- which is what keeps this module free
    of the deferred reader over prose.

    **The rule over-flags, and that is the cheap direction.** A refusal reading "I
    searched for 2 wordings" is marked as stating a quantity. A wrongly flagged
    decline is a line in a list someone reads; a wrongly passed fabrication is the
    failure this whole project exists to prevent. Every flagged answer is listed in
    the report so the over-flagging stays visible and measurable.
    """
    return QuantityScore(
        by_citation=bool(citations(result.answer)),
        by_digit=any(character.isdigit() for character in result.answer),
    )


@dataclass(frozen=True)
class UnsupportedScore:
    """How an unsupported question was answered. Task 4.3."""

    declined: bool
    fabricated: bool


def unsupported_score(result: Result) -> UnsupportedScore:
    stated = quantity_score(result).states_quantity
    return UnsupportedScore(declined=not stated, fabricated=stated)


@dataclass(frozen=True)
class GroundingScore:
    """The agent's own warnings, counted rather than judged. Task 4.4.

    Nothing here is computed from the answer: these are facts the agent
    established about itself and emitted, and the harness's job is to count them.
    """

    unknown_citations: tuple[int, ...]
    unretrieved_citations: tuple[int, ...]
    ungrounded_refusal: bool
    claimed_searching: bool
    retrievals: int

    @property
    def grounding_failures(self) -> int:
        return len(self.unknown_citations) + len(self.unretrieved_citations)


def grounding_score(result: Result) -> GroundingScore:
    return GroundingScore(
        unknown_citations=result.unknown_citations,
        unretrieved_citations=result.unretrieved_citations,
        ungrounded_refusal=result.ungrounded_refusal,
        claimed_searching=result.claimed_searching,
        retrievals=len(result.retrievals),
    )


def correctly_declined(result: Result) -> bool:
    """A refusal that searched first, as opposed to one that did not. Task 4.4.

    "Not in the corpus" and "not looked for" are different statements, and an
    answer cannot be read to tell them apart. A refusal with no retrieval behind it
    rests on the model's prior about what the corpus contains, so it is counted as
    an ungrounded refusal and never as a correct decline.
    """
    return (
        not quantity_score(result).states_quantity
        and not result.ungrounded_refusal
        and len(result.retrievals) > 0
    )


def cites_in_full(result: Result) -> bool:
    """Whether a follow-up stands on its own. Task 4.6.

    Deterministic and partial, deliberately. An answer that states a quantity and
    carries no citation of its own is relying on something outside itself, which is
    exactly what a follow-up must not do. What this cannot see is an answer that
    cites *something* while still leaning on a figure introduced earlier; that is a
    judgement, and it belongs to the judged layer.
    """
    if not quantity_score(result).states_quantity:
        return True
    return bool(result.cited)


# How far outside its peers' interval a value has to sit to be reported, and how
# many peers are needed before the comparison is made at all.
#
# **Two, not an order of magnitude.** The case this check exists for is yeast
# nuclear volume: eight entries between 1.76 and 3.3, and one at 10.3, which is
# 3.1 times the peers' maximum. A tenfold rule would miss the very answer that
# motivated the check.
#
# **Against the peers' interval, not their median.** The design's starting form was
# a ratio to the median, and this departs from it: these populations are small and
# skewed, so a central estimate is pulled by the outlier it is meant to find, while
# the observed interval is not. The interval is also what the report shows a reader
# anyway, so the figure and the evidence for it are the same thing.
#
# Both numbers are chosen, not derived. Task 4.10 counts what they flag and what
# they let through against the first real run. ADR-0520 records the reasoning,
# including the population that rules a median out: peers at 1, 1, 1, 1 and 10
# have a median of 1, so a value of 5 is five times it and still inside the range
# the corpus already records.
OUTLIER_FACTOR = 2.0
MIN_PEERS = 4


@dataclass(frozen=True)
class Outlier:
    """A cited entry at odds with the corpus's other entries for the same quantity."""

    entry_id: int
    value: float
    peers: int
    peer_low: float
    peer_high: float
    #: How far outside the peers' interval it sits, as a factor. Above 1 by
    #: construction: at or below the factor it would not be reported.
    outside_by: float


def representative_value(entry: Entry) -> float | None:
    """The one number to compare an entry by, or `None` if it has no usable one.

    A scalar where there is one, otherwise the midpoint of a range. Zero and
    negative values are refused for the reason `Entry.spans_implausibly` refuses
    them: a ratio across zero is meaningless, and a mark firing on arithmetic
    rather than on evidence is worse than no mark.
    """
    if entry.value is not None:
        return entry.value if entry.value > 0 else None
    if entry.range_low is not None and entry.range_high is not None:
        middle = (entry.range_low + entry.range_high) / 2
        return middle if middle > 0 else None
    return None


def _values_by_quantity(entries: tuple[Entry, ...]) -> dict[tuple[str, str], list[float]]:
    """Usable values grouped by the quantity they measure: property and organism.

    Built once instead of scanning the corpus for every cited entry. The report
    calls the two peer functions for the group and again for each tag and each
    shape, so the old shape was O(results x cited x entries x buckets) -- tens of
    millions of comparisons on a real corpus with both breakdowns asked for.
    """
    grouped_values: dict[tuple[str, str], list[float]] = {}
    for entry in entries:
        value = representative_value(entry)
        if value is not None:
            grouped_values.setdefault((entry.property, entry.organism), []).append(value)
    return grouped_values


def _peers_of(entry: Entry, index: dict[tuple[str, str], list[float]]) -> list[float]:
    """The other entries' values for the same quantity.

    One copy of this entry's own value is removed rather than the entry being
    excluded by identity: two entries can record the same number, and dropping
    every match would shrink the population the floor is measured against.
    """
    values = list(index.get((entry.property, entry.organism), ()))
    own = representative_value(entry)
    if own is not None and own in values:
        values.remove(own)
    return values


def outliers_among_peers(cited: tuple[int, ...], entries: tuple[Entry, ...]) -> tuple[Outlier, ...]:
    """Cited entries whose value sits far outside their peers'. Task 4.5.

    Peers are the corpus's other entries recording the same property for the same
    organism. The answer's prose is never read: the inputs are the citation set and
    the corpus, which is what makes this cheap enough to survive in a change that
    has no parser.

    **Reported, never scored.** An outlier is a fact about the corpus, not about
    the answer: the entry may be measuring something its neighbours are not, which
    is exactly the yeast case. What this buys is that the figure appears in a list
    a person reads, beside the interval its peers occupy.

    Silent where a property has fewer than `MIN_PEERS` peers -- and the report says
    the comparison could not be made, rather than leaving an absence that reads as
    a pass.
    """
    by_id = {entry.entry_id: entry for entry in entries}
    index = _values_by_quantity(entries)
    found = []
    for entry_id in cited:
        entry = by_id.get(entry_id)
        if entry is None:
            continue
        value = representative_value(entry)
        if value is None:
            continue
        peer_values = _peers_of(entry, index)
        if len(peer_values) < MIN_PEERS:
            continue
        low, high = min(peer_values), max(peer_values)
        if value > high * OUTLIER_FACTOR:
            outside = value / high
        elif value < low / OUTLIER_FACTOR:
            outside = low / value
        else:
            continue
        found.append(
            Outlier(
                entry_id=entry.entry_id,
                value=value,
                peers=len(peer_values),
                peer_low=low,
                peer_high=high,
                outside_by=outside,
            )
        )
    return tuple(found)


def peers_too_few(cited: tuple[int, ...], entries: tuple[Entry, ...]) -> tuple[int, ...]:
    """Cited entries the outlier comparison could not be made for.

    Reported beside the outliers so that "nothing flagged" is distinguishable from
    "nothing could be judged" -- an absence that reads as a pass is the failure
    this exists to prevent.
    """
    by_id = {entry.entry_id: entry for entry in entries}
    index = _values_by_quantity(entries)
    unjudged = []
    for entry_id in cited:
        entry = by_id.get(entry_id)
        if entry is None or representative_value(entry) is None:
            unjudged.append(entry_id)
            continue
        if len(_peers_of(entry, index)) < MIN_PEERS:
            unjudged.append(entry_id)
    return tuple(unjudged)


@dataclass(frozen=True)
class Spread:
    """A figure across repeats: the aggregate, and how far it moved. Task 4.7."""

    mean: float
    low: float
    high: float
    repeats: int

    @property
    def moved(self) -> bool:
        return self.high != self.low


def spread(values: tuple[float, ...]) -> Spread | None:
    """`None` for no values: a spread over nothing is not zero, it is unknown."""
    if not values:
        return None
    return Spread(
        mean=sum(values) / len(values),
        low=min(values),
        high=max(values),
        repeats=len(values),
    )


@dataclass(frozen=True)
class Stability:
    """Whether a question answered the same way twice. Task 4.7."""

    question_id: str
    repeats: int
    unstable: bool
    cited_sets: tuple[tuple[int, ...], ...]


def stability(results: tuple[Result, ...]) -> tuple[Stability, ...]:
    """A question whose cited entries differ across repeats is reported unstable.

    The agent is not deterministic, so a single run measures a trajectory. Averaging
    the repeats away would hide exactly the questions where a change cannot be
    told from luck.
    """
    per_question: dict[str, list[Result]] = {}
    for result in results:
        per_question.setdefault(result.question_id, []).append(result)
    reported = []
    for question_id, group in per_question.items():
        sets = tuple(tuple(sorted(set(result.cited))) for result in group)
        reported.append(
            Stability(
                question_id=question_id,
                repeats=len(group),
                unstable=len(set(sets)) > 1,
                cited_sets=sets,
            )
        )
    return tuple(reported)


@dataclass(frozen=True)
class Bounds:
    """Which limits a question ran into, however it ended."""

    at_spend_ceiling: bool
    at_tool_bound: bool
    at_retrieval_bound: bool


def bounds_reached(result: Result) -> Bounds:
    """Whether a question had room left, borrowing the event's own definitions.

    The ending event is rebuilt from the recorded fields rather than the three
    comparisons being written out again here. They are the agent's definitions of
    "no room for another call", and a second copy would drift from them the first
    time one changed -- invisibly, because both would still return a boolean.
    """
    ending = QuestionEnded(
        question_id=result.question_id,
        reason=EndReason.ANSWERED,
        spend=result.spend,
        run_spend=result.run_spend,
        model=result.model,
        tool_calls=result.tool_calls,
        model_calls=result.model_calls,
        call_limit=result.call_limit,
        tool_call_limit=result.tool_call_limit,
        spend_ceiling=result.spend_ceiling,
        run_budget=result.run_budget,
    )
    return Bounds(
        at_spend_ceiling=ending.at_spend_ceiling,
        at_tool_bound=ending.at_tool_bound,
        at_retrieval_bound=ending.at_retrieval_bound,
    )


@dataclass(frozen=True)
class RunGroup:
    """What a set of results has in common, and what may never be averaged across.

    A reworded prompt moves every figure; a rebuilt corpus changes what there was
    to find; a different model is a different system. Grouping by all four is what
    makes "never combined" structural rather than a convention someone remembers.
    """

    model: str
    prompt_digest: str
    corpus_digest: str
    corpus_entries: int
    code_version: str


def group_of(result: Result) -> RunGroup:
    provenance = result.provenance
    if provenance is None:
        # A record with no provenance cannot be compared with one that has it, so
        # it gets its own group rather than joining any other.
        return RunGroup("unknown", "unknown", "unknown", 0, "unknown")
    return RunGroup(
        model=provenance.model,
        prompt_digest=provenance.prompt_digest,
        corpus_digest=provenance.corpus_digest,
        corpus_entries=provenance.corpus_entries,
        code_version=provenance.code_version,
    )


def grouped(results: tuple[Result, ...]) -> dict[RunGroup, tuple[Result, ...]]:
    groups: dict[RunGroup, list[Result]] = {}
    for result in results:
        groups.setdefault(group_of(result), []).append(result)
    return {group: tuple(members) for group, members in groups.items()}


def grounded_failures_of(result: Result) -> int:
    """The agent's own grounding failures for one result, counted.

    A named function rather than the report reaching through `grounding_score`, so
    the definition of "a grounding failure" has one home.
    """
    return grounding_score(result).grounding_failures


# Endings that mean the question never reached the model: everything that closes a
# run, plus the two failures that leave an answer nobody produced.
#
# **Built from the drivers' own set rather than listed again here.** This module
# had its own copy, and it went stale the day `PROVIDER_LIMIT` was added: a
# question refused because the key had no credit left recorded the agent's "no
# credit" notice as its answer, and that answer was then scored -- an unpaid
# invoice reported as the model's behaviour. A third adapter deciding for itself
# which endings are final is how they come to disagree, which is the argument the
# set was shared for.
NEVER_ASKED = frozenset(STOP_THE_RUN) | {
    EndReason.PROVIDER_FAILURE,
    EndReason.INTERNAL_ERROR,
}


def reached_the_model(result: Result) -> bool:
    """Whether the question was actually put to the model and came back.

    **The scored population, and getting it wrong is the unfalsifiable direction.**
    An unsupported question that crashed records an empty answer, and an empty
    answer states no quantity, so it scored as a *correct refusal* -- an
    infrastructure failure inflating the headline refusal figure for a question
    the model never saw. A question refused on the run budget is worse: its answer
    is the budget message, whose dollar figures contain digits, so it scored as a
    fabrication.

    Excluded rather than counted as failures of the agent, and reported apart, so
    that "20 of 20 declined" cannot be built out of questions nobody asked.
    """
    return not result.failure and result.end_reason not in NEVER_ASKED


def asked(results: tuple[Result, ...]) -> tuple[Result, ...]:
    return tuple(result for result in results if reached_the_model(result))


def never_asked(results: tuple[Result, ...]) -> tuple[Result, ...]:
    return tuple(result for result in results if not reached_the_model(result))
