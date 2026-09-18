"""The second text: what is admitted, what is refused, and what the page may never leak.

Tasks 6.1-6.3, over the scientist report's own examples -- a doubling time stated in a table row
and restated three ways in the prose: rounded in the Discussion, converted to hours in a model, and
converted to seconds in a second measurement. Each of those is an item that would measure nothing,
and each has to be refused by a different clause of `excluded_forms`.

The article here is hand-built rather than read from the fixture XML, for the reason
`test_bionumbers_quotes.py` gives about the checker: what is under test is the arithmetic that
decides admissibility, and an arithmetic rule exercised only through the JATS reader shares the
reader's mistakes. Its passages are written the way the reader produces them -- table cells as the
cell text with the headers beside it, bibliographic markers as `[ref N]` tokens.

The negative cases each vary the dimension its rule actually reads: a longer digit run for the
word-boundary rule, an unknown unit for the conversion rule, an occurrence stated in words for the
folded-equality rule (which no numeric form can catch), an invented span for the verification rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from bionumbers.distractor import (
    SECOND_TEXT_INSTRUCTION,
    Candidate,
    admissible,
    choose_second_text,
    excluded_forms,
    texts_on_the_page,
)
from bionumbers.records import (
    CandidateKind,
    Claim,
    ClaimKind,
    ConditionField,
    DistractorType,
    Fingerprint,
    Location,
    NotReviewable,
    Paper,
    Provenance,
    Quote,
    ReviewItem,
    SecondTextKind,
)
from bionumbers.spend import Ceiling, Ledger

QUESTION = "What is the doubling time of Escherichia coli?"
PAPER = Paper(pmcid="PMC9000001", title="Division timing in glucose and acetate", year=2026)


@dataclass(frozen=True)
class _Passage:
    id: str
    text: str
    kind: str = "p"
    section_path: tuple[str, ...] = ()
    row_headers: tuple[str, ...] = ()
    column_headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Document:
    passages: tuple[_Passage, ...] = ()

    def text(self) -> str:
        return "\n".join(passage.text for passage in self.passages)

    def passage(self, passage_id: str) -> _Passage | None:
        return next((p for p in self.passages if p.id == passage_id), None)


DOUBLING = ("Doubling time (min)",)

ARTICLE = _Document(
    passages=(
        _Passage(
            id="t1-r1",
            text="39 ± 1",
            kind="td",
            section_path=("Results", "Table 1"),
            row_headers=("Glucose",),
            column_headers=DOUBLING,
        ),
        _Passage(
            id="t1-r2",
            text="55 ± 2",
            kind="td",
            section_path=("Results", "Table 1"),
            row_headers=("Acetate",),
            column_headers=DOUBLING,
        ),
        _Passage(
            id="p-results",
            text=(
                "Cells grown in glucose minimal medium divided with a doubling time of "
                "39 ± 1 min (Table 1)."
            ),
            section_path=("Results",),
        ),
        _Passage(
            id="p-discussion",
            text=(
                "Earlier work gives 30–40 min for the same strain in comparable medium [ref 12]."
            ),
            section_path=("Discussion",),
        ),
        _Passage(
            id="p-model",
            text="The simulation assumed a division time of 0.65 h throughout [ref 7].",
            section_path=("Discussion",),
        ),
        _Passage(
            id="p-microscopy",
            text="Followed by microscopy, the same cultures took 2340 s to divide.",
            section_path=("Results",),
        ),
        _Passage(
            id="p-cited",
            text="Wang and colleagues report 25 min for the same organism in rich medium [ref 3].",
            section_path=("Discussion",),
        ),
        _Passage(
            id="p-length",
            text="Cell length at division averaged 2.4 µm in the same cultures.",
            section_path=("Results",),
        ),
        _Passage(
            id="p-threshold",
            text="A detection threshold of 120 min was applied to every time course.",
            section_path=("Methods",),
        ),
        _Passage(
            id="p-words",
            text="Division took roughly forty minutes under these conditions.",
            section_path=("Discussion",),
        ),
    )
)

FINGERPRINT = Fingerprint(
    model="claude-opus-4-7", instruction_sha256="0" * 64, article_id=PAPER.pmcid, run_id="r-1"
)


def _quote(passage_id: str, text: str) -> Quote:
    passage = ARTICLE.passage(passage_id)
    assert passage is not None, f"no passage {passage_id!r} in the article"
    return Quote(
        text=text,
        location=Location(
            passage_id=passage_id,
            section_path=passage.section_path,
            kind=passage.kind,
            row_headers=passage.row_headers,
            column_headers=passage.column_headers,
        ),
    )


def _claim(value: str, unit: str, *, quote: Quote, occurrences: tuple[Quote, ...] = ()) -> Claim:
    """A claim with its value, unit, quote and occurrences always given explicitly.

    None of the four has a default on purpose: every rule under test reads one of them, and a
    helper that filled one would hold it constant across the positive and the negative case, which
    is how a test comes to prove nothing.
    """
    return Claim(
        claim_id="c-1",
        property_asked="doubling time",
        property_in_paper="division time",
        value=value,
        unit=unit,
        kind=ClaimKind.WITH_UNCERTAINTY,
        candidate_kind=CandidateKind.MEASURED,
        quote=quote,
        occurrences=occurrences,
        conditions=(
            ConditionField(
                name="medium",
                provenance=Provenance.FROM_METHODS,
                quote="glucose minimal medium",
                location=Location(passage_id="p-results"),
            ),
        ),
        fingerprint=FINGERPRINT,
    )


TABLE_CELL = _quote("t1-r1", "39 ± 1")
PROSE = _quote("p-results", "a doubling time of 39 ± 1 min")
IN_WORDS = _quote("p-words", "Division took roughly forty minutes under these conditions.")


@pytest.fixture
def claim() -> Claim:
    """The table cell is the claim's most precise statement of the value, which is the shape the
    scientist report found in every paper with a table. Nothing is recorded as an occurrence here;
    the tests that need one pass it."""
    return _claim("39 ± 1", "min", quote=TABLE_CELL)


class ScriptedModel:
    """The provider, scripted: it returns the candidates a test names and records what it was sent.

    `count_tokens` and `parse` are the whole of the `Model` protocol, so a test can assert that the
    projection happened before the call rather than instead of it -- `parsed` stays empty when the
    ledger refuses.
    """

    def __init__(self, *candidates: Candidate, input_tokens: int = 12_000) -> None:
        self.candidates = list(candidates)
        self.input_tokens = input_tokens
        self.counted: list[tuple[object, object]] = []
        self.parsed: list[tuple[object, object]] = []

    def count_tokens(self, *, system: object, messages: object, output_format: object):
        self.counted.append((system, messages))
        return SimpleNamespace(input_tokens=self.input_tokens)

    def parse(self, *, system: object, messages: object, output_format: object, max_tokens: int):
        self.parsed.append((system, messages))
        return SimpleNamespace(
            parsed_output=output_format(candidates=self.candidates),
            usage=SimpleNamespace(
                input_tokens=200,
                output_tokens=400,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=self.input_tokens - 200,
            ),
        )


def _candidate(passage_id: str, kind: DistractorType) -> Candidate:
    """A candidate quoting a whole passage of the article, so only its type and its admissibility
    vary between the cases below."""
    passage = ARTICLE.passage(passage_id)
    assert passage is not None, f"no passage {passage_id!r} in the article"
    return Candidate(passage_id=passage_id, text=passage.text, type=kind)


ADJACENT_ROW = _candidate("t1-r2", DistractorType.ADJACENT_CONDITION)
CITED = _candidate("p-cited", DistractorType.CITED)
PARAMETER = _candidate("p-threshold", DistractorType.PARAMETER)
DIFFERENT_QUANTITY = _candidate("p-length", DistractorType.DIFFERENT_QUANTITY)
ROUNDED_IN_DISCUSSION = _candidate("p-discussion", DistractorType.CITED)
CONVERTED_TO_HOURS = _candidate("p-model", DistractorType.PARAMETER)
CONVERTED_TO_SECONDS = _candidate("p-microscopy", DistractorType.ADJACENT_CONDITION)


def _choose(model: ScriptedModel, claim: Claim, ledger: Ledger | None = None):
    return choose_second_text(
        model,
        ARTICLE,
        claim,
        PAPER,
        question=QUESTION,
        ledger=ledger if ledger is not None else Ledger(Ceiling()),
    )


# --- the forms a value may not be restated in ---


def test_the_forms_of_a_value_with_an_uncertainty():
    """The brief's worked example. `1` is the uncertainty, not the value: excluding it would refuse
    every candidate mentioning a single anything, and the claim is about 39."""
    forms = excluded_forms("39 ± 1", "min")

    assert "39" in forms  # as written
    assert "40" in forms  # 39 at one significant figure, which is how a Discussion restates it
    assert "0.65" in forms  # 39 min in hours
    assert "2340" in forms  # 39 min in seconds, at three significant figures
    assert "1" not in forms
    assert "" not in forms


def test_both_ends_of_a_range_are_the_value():
    """A range over conditions asserts both endpoints, so restating either one restates the
    claim -- unlike an uncertainty, where only the central value is asserted."""
    forms = excluded_forms("20–40", "min")

    assert {"20", "40"} <= forms


def test_a_value_is_excluded_at_every_smaller_precision():
    assert {"2.13", "2.1", "2"} <= excluded_forms("2.13", "µm")
    assert {"39.4", "39", "40"} <= excluded_forms("39.4", "min")


def test_an_unparseable_unit_leaves_the_numeric_forms_and_nothing_else():
    """The negative for the conversion rule, varying the one thing that rule reads: the unit. A
    unit pint cannot parse must not lose the numeric forms as well -- the refusal is per form."""
    assert excluded_forms("39", "widgets") == frozenset({"39", "40"})
    assert {"0.65", "2340"} <= excluded_forms("39", "min")


# --- admissibility ---


def test_a_different_value_in_the_same_unit_is_admitted(claim):
    assert admissible("The lag phase lasted 55 ± 2 min before growth resumed.", claim)


def test_a_rounded_restatement_is_refused(claim):
    """The Discussion's "30–40 min" for a "39 ± 1 min" claim. The clause that fires is the
    significant-figure rounding: 39 at one significant figure is 40, and "40" stands alone in the
    candidate. The range endpoint "30" is not the claim's and plays no part."""
    assert "40" in excluded_forms(claim.value, claim.unit)

    assert not admissible("Earlier work gives 30–40 min for the same strain [ref 12].", claim)


@pytest.mark.parametrize(
    ("value", "restatement"),
    [
        ("39", "The simulation assumed a division time of 0.65 h throughout."),
        ("39", "The same cultures took 2340 s to divide."),
        ("55", "Growth in acetate was modelled with a 0.92 h division time."),
    ],
)
def test_a_converted_restatement_is_refused(value: str, restatement: str):
    claim = _claim(value, "min", quote=TABLE_CELL)

    assert not admissible(restatement, claim)


def test_a_number_inside_a_longer_number_is_not_the_value():
    """The negative for the word-boundary rule, varying what that rule reads: the digits either
    side. 139 is not 39 and 2390 s is not 2340 s, and a rule that cannot tell them apart would
    refuse most of a numerate paper."""
    claim = _claim("39", "min", quote=TABLE_CELL)

    assert admissible("Colony counts reached 139 min after inoculation.", claim)
    assert admissible("The dead time of the stage was 2390 s.", claim)


def test_a_recorded_occurrence_is_not_a_distractor():
    """The clause no numeric form can reach: an occurrence stating the value in words carries no
    excluded form at all, and is still the same measurement."""
    claim = _claim("39 ± 1", "min", quote=TABLE_CELL, occurrences=(IN_WORDS,))

    assert not admissible(IN_WORDS.text, claim)


def test_a_sentence_without_the_value_is_admitted_whatever_is_recorded():
    """The negative for the occurrence rule, varying membership of `occurrences` rather than the
    text: the same claim, a different sentence with no digits at all."""
    claim = _claim("39 ± 1", "min", quote=TABLE_CELL, occurrences=(IN_WORDS,))

    assert admissible("Growth was slower in acetate than in glucose.", claim)


def test_the_supporting_quote_is_never_its_own_distractor(claim):
    assert not admissible(claim.quote.text, claim)


def test_an_empty_text_is_refused(claim):
    assert not admissible("", claim)
    assert not admissible("   \n ", claim)


# --- selection ---


def test_an_adjacent_table_row_becomes_the_distractor(claim):
    """The spec's first scenario: the table states the property for several conditions, so a row
    for a different condition is the distractor, and the item records the type."""
    model = ScriptedModel(ADJACENT_ROW, ROUNDED_IN_DISCUSSION)

    item = _choose(model, claim)

    assert isinstance(item, ReviewItem)
    assert item.second.text == "55 ± 2"
    assert item.second_kind is SecondTextKind.DISTRACTOR
    assert item.distractor_type is DistractorType.ADJACENT_CONDITION
    assert item.supporting == claim.quote
    # A table cell reaches the page as its headers and the cell, never as the whole table.
    assert item.second.location.row_headers == ("Acetate",)
    assert item.second.location.column_headers == DOUBLING


def test_a_candidate_restating_the_value_is_never_the_item(claim):
    """The spec's second scenario, through the whole path rather than through `admissible`: three
    candidates, each a restatement, and the one sound candidate is the one that survives."""
    model = ScriptedModel(
        ROUNDED_IN_DISCUSSION, CONVERTED_TO_HOURS, CONVERTED_TO_SECONDS, DIFFERENT_QUANTITY
    )

    item = _choose(model, claim)

    assert isinstance(item, ReviewItem)
    assert item.distractor_type is DistractorType.DIFFERENT_QUANTITY


@pytest.mark.parametrize(
    ("offered", "wanted"),
    [
        ((PARAMETER, CITED), DistractorType.CITED),
        ((CITED, ADJACENT_ROW), DistractorType.ADJACENT_CONDITION),
        ((PARAMETER, DIFFERENT_QUANTITY), DistractorType.DIFFERENT_QUANTITY),
    ],
)
def test_the_hardest_admissible_type_is_taken(claim, offered, wanted):
    """`DISTRACTOR_PREFERENCE` is hardest first, and the order candidates arrive in must not
    decide: each pair is offered in the order that would give the wrong answer if it did."""
    item = _choose(ScriptedModel(*offered), claim)

    assert isinstance(item, ReviewItem)
    assert item.distractor_type is wanted


def test_an_invented_candidate_is_never_used_even_alone(claim):
    """A span that is not in the article fails `quotes.verify` and is dropped, however good a
    distractor it would make -- everything on the screen is a checked quote."""
    invented = Candidate(
        passage_id="p-results",
        text="In glycerol the doubling time was 71 min.",
        type=DistractorType.ADJACENT_CONDITION,
    )

    result = _choose(ScriptedModel(invented), claim)

    assert isinstance(result, NotReviewable)
    assert "not verbatim" in result.reason


def test_a_second_occurrence_is_used_when_no_distractor_survives():
    """The spec's third scenario. Every candidate restates the value, so the item is built from the
    paper's own second statement of it and the kind says so."""
    claim = _claim("39 ± 1", "min", quote=TABLE_CELL, occurrences=(PROSE,))
    model = ScriptedModel(ROUNDED_IN_DISCUSSION, CONVERTED_TO_HOURS, CONVERTED_TO_SECONDS)

    item = _choose(model, claim)

    assert isinstance(item, ReviewItem)
    assert item.second == PROSE
    assert item.second_kind is SecondTextKind.SECOND_OCCURRENCE
    assert item.distractor_type is None


def test_no_admissible_second_text_means_no_item(claim):
    """The spec's fourth scenario: no item is created, and the claim is recorded as not reviewable
    with the reason -- an ending that can be counted later, not a silent drop."""
    model = ScriptedModel(ROUNDED_IN_DISCUSSION, CONVERTED_TO_SECONDS)

    result = _choose(model, claim)

    assert isinstance(result, NotReviewable)
    assert result.claim_id == claim.claim_id
    assert result.reason


def test_an_unverifiable_occurrence_is_no_fallback():
    """The negative for the fallback, varying what the fallback reads: an occurrence recorded
    against a passage that does not contain it is not a second statement of anything."""
    invented = Quote(text="The doubling time was 39 min.", location=Location(passage_id="p-words"))
    claim = _claim("39 ± 1", "min", quote=TABLE_CELL, occurrences=(invented,))

    result = _choose(ScriptedModel(CONVERTED_TO_SECONDS), claim)

    assert isinstance(result, NotReviewable)


# --- the call itself ---


def test_the_article_is_the_cached_first_block_and_the_instruction_the_second(claim):
    """Prompt caching is a prefix match, so the article comes first and carries `cache_control`:
    put the instruction first and this call pays full input rate for the whole article, which the
    run summary reports as a cached fraction that quietly drops."""
    model = ScriptedModel(ADJACENT_ROW)

    _choose(model, claim)

    system, _ = model.parsed[0]
    assert len(system) == 2
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Cells grown in glucose minimal medium" in system[0]["text"]
    assert system[1]["text"] == SECOND_TEXT_INSTRUCTION
    assert "cache_control" not in system[1]
    # The same two objects were priced and then sent: a projection taken on a different request is
    # a projection of nothing.
    assert model.counted[0] == model.parsed[0]


def test_the_model_is_told_the_value_and_its_quote_and_nothing_about_a_decision(claim):
    """The spec's last requirement, as a negative: decisions measure this selector, so no word of
    one may reach it. Asserted over the instruction as well as the messages, because the
    instruction is where a helpful sentence about what a reviewer will be asked would land."""
    model = ScriptedModel(ADJACENT_ROW)

    _choose(model, claim)

    _, messages = model.parsed[0]
    sent = "\n".join(str(message["content"]) for message in messages)
    assert claim.value in sent
    assert claim.quote.text in sent
    assert claim.quote.location.passage_id in sent
    for word in ("approve", "disapprove", "verdict", "chosen"):
        assert word not in sent.lower()
        assert word not in SECOND_TEXT_INSTRUCTION.lower()


def test_the_instruction_names_every_type_of_distractor():
    """The five types are the record's vocabulary; a type the instruction does not name is one the
    model cannot return, and the distribution of wrong answers by type would be silently short of
    a column."""
    for kind in DistractorType:
        assert kind.value in SECOND_TEXT_INSTRUCTION


def test_the_call_is_priced_and_recorded_against_the_paper(claim):
    ledger = Ledger(Ceiling())

    _choose(ScriptedModel(ADJACENT_ROW), claim, ledger)

    assert ledger.paper(PAPER.pmcid).calls == 1
    assert ledger.paper(PAPER.pmcid).usd > 0
    assert ledger.paper(PAPER.pmcid).cache_read_tokens > 0


def test_a_call_that_would_cross_the_ceiling_is_never_made(claim):
    """Projected before, not measured after: a ceiling checked once the call has returned has
    already been crossed."""
    model = ScriptedModel(ADJACENT_ROW)

    result = _choose(model, claim, Ledger(Ceiling(per_paper=0.0)))

    assert isinstance(result, NotReviewable)
    assert result.reason == "ceiling reached"
    assert model.parsed == []


# --- what the page may show (6.3) ---


@pytest.mark.parametrize(
    "occurrences", [(), (PROSE,)], ids=["distractor-item", "second-occurrence-item"]
)
def test_the_kind_and_type_are_on_the_item_and_in_neither_text(occurrences):
    """Recorded and never shown (design D5): the kind is what lets the rebuild measure attention
    separately from ambiguity, and a reviewer who could see it would be answering a different
    question. Both kinds of item are checked, since only one of them has a type to leak."""
    claim = _claim("39 ± 1", "min", quote=TABLE_CELL, occurrences=occurrences)
    candidates = (
        (ADJACENT_ROW,) if not occurrences else (ROUNDED_IN_DISCUSSION, CONVERTED_TO_SECONDS)
    )

    item = _choose(ScriptedModel(*candidates), claim)

    assert isinstance(item, ReviewItem)
    assert item.second_kind is (
        SecondTextKind.SECOND_OCCURRENCE if occurrences else SecondTextKind.DISTRACTOR
    )
    assert (item.distractor_type is None) is bool(occurrences)
    rendered = texts_on_the_page(item)
    assert rendered == (item.supporting.text, item.second.text)
    for text in rendered:
        for kind in SecondTextKind:
            assert kind.value not in text
        for distractor_type in DistractorType:
            assert distractor_type.value not in text
