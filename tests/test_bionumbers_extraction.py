"""Extraction: the instruction, the one retry, the six endings, and what reaches the record.

Two things are being tested here and they need different instruments. The *pipeline* is tested
against a scripted model, because the behaviour worth pinning -- what happens to a fabricated quote
-- is exactly what a real model will not produce on demand. The *article* is real throughout: every
quote a scripted answer carries is either copied out of the fixture or is a one-token change to a
sentence that is, so the checker in the middle is doing its actual job rather than comparing two
strings this file made up.

No figure or string below was taken from a run of the module. The fabricated quotes are built by
changing a digit in a real sentence, which is the failure ADR-0040 recorded (the textbook value
displacing the paper's), and the instruction's assertions come from the spec's "the model answers
from the article, not from what it knows".
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from bionumbers import quotes
from bionumbers.extraction import (
    INSTRUCTION,
    MAX_TOKENS,
    ClaimDraft,
    ConditionDraft,
    ExtractionOutput,
    QuoteDraft,
    RejectedDraft,
    RunFileWouldBeCommitted,
    extract,
    instruction_sha256,
    read_results,
    system_blocks,
    user_turn,
    write_results,
)
from bionumbers.jats import read_jats
from bionumbers.records import (
    CONDITION_FIELDS,
    CandidateKind,
    ClaimKind,
    Paper,
    PaperState,
    Provenance,
    Spend,
)
from bionumbers.spend import MODEL, Ceiling, Ledger, cost, projected_cost

FIXTURES = Path(__file__).parent / "fixtures" / "europepmc"

#: The probe's case (ADR-0040, design D7): this paper states 65 min for the replication period of
#: *E. coli*, where the textbook figure is 40. Both sentences below are copied out of the fixture.
MEASURED_SENTENCE = "are present for 65 min on average"
SECOND_SENTENCE = "replication initiation occurs within 5 min of replisome assembly"

#: The same sentences with one digit changed, which is what a model reciting a remembered value
#: produces. Neither is in the article, and the checker is what has to notice.
TEXTBOOK_SENTENCE = "are present for 40 min on average"
INVENTED_SENTENCE = "replication initiation occurs within 9 min of replisome assembly"

QUESTION = "time to replicate the chromosome"
ORGANISM = "Escherichia coli"
RUN_ID = "run-of-the-test"

PAPER = Paper(pmcid="PMC2288635", title="Replisome dynamics", year=2008, licence="CC BY")
ESSAY = Paper(pmcid="PMC13340094", title="Copper tolerance", year=2025, licence="CC BY")


@pytest.fixture(scope="module")
def article():
    return read_jats((FIXTURES / "fulltext_PMC2288635.xml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def essay():
    """The fixture with no methods section: a brief report under research-article metadata."""
    return read_jats((FIXTURES / "fulltext_PMC13340094.xml").read_text(encoding="utf-8"))


def passage_holding(doc, phrase: str) -> str:
    """The id of the passage the phrase sits in, read off the document rather than written down.

    The reader's id scheme is its own business; a test that hard-coded an id would be testing the
    reader. A phrase in no passage is the test's mistake and says so loudly.
    """
    wanted = quotes.fold(phrase)
    for passage in doc.passages:
        if wanted in quotes.fold(passage.text):
            return passage.id
    raise AssertionError(f"no passage of {doc.pmcid} contains {phrase!r}; the fixture has changed")


USAGE = SimpleNamespace(
    input_tokens=61_000,
    cache_creation_input_tokens=0,
    cache_read_input_tokens=0,
    output_tokens=1_200,
)


class ScriptedModel:
    """Answers from a queue, and keeps every request it was given.

    `counts` and `calls` are separate because the projection and the call are separate decisions:
    a paper stopped by the ceiling is counted and never called, and no other double can tell those
    apart.
    """

    def __init__(self, *answers: ExtractionOutput, input_tokens: int = 61_000, raises=None):
        self.answers = list(answers)
        self.input_tokens = input_tokens
        self.raises = raises
        self.calls: list[dict] = []
        self.counts: list[dict] = []

    def count_tokens(self, *, system, messages, output_format=None):
        self.counts.append({"system": system, "messages": messages})
        return SimpleNamespace(input_tokens=self.input_tokens)

    def parse(self, *, system, messages, output_format, max_tokens):
        self.calls.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        if self.raises is not None:
            raise self.raises
        assert self.answers, "the double was asked for more answers than the test queued"
        return SimpleNamespace(parsed_output=self.answers.pop(0), usage=USAGE)


def a_ledger(**bounds) -> Ledger:
    return Ledger(Ceiling(**bounds))


def a_claim(
    quote: str,
    passage_id: str,
    *,
    value: str,
    candidate_kind: CandidateKind = CandidateKind.MEASURED,
    unit: str = "min",
    kind: ClaimKind = ClaimKind.SINGLE,
    occurrences: tuple[QuoteDraft, ...] = (),
    conditions: tuple[ConditionDraft, ...] = (),
    inputs: tuple[QuoteDraft, ...] = (),
) -> ClaimDraft:
    """A drafted claim. `value` and `candidate_kind` are named at every call site on purpose: both
    are dimensions a rule below reads, and a default would hold them constant across the positive
    and negative cases alike."""
    return ClaimDraft(
        property_in_paper="time between replisome appearance and disappearance",
        value=value,
        unit=unit,
        kind=kind,
        candidate_kind=candidate_kind,
        quote=QuoteDraft(text=quote, passage_id=passage_id),
        occurrences=list(occurrences),
        conditions=list(conditions),
        inputs=list(inputs),
    )


def found(*claims: ClaimDraft, rejected: tuple[RejectedDraft, ...] = ()) -> ExtractionOutput:
    return ExtractionOutput(state="CLAIMS_FOUND", claims=list(claims), rejected=list(rejected))


def run(model, doc, paper=PAPER, ledger=None, **overrides):
    return extract(
        model,
        doc,
        paper,
        question=overrides.pop("question", QUESTION),
        organism=overrides.pop("organism", ORGANISM),
        run_id=overrides.pop("run_id", RUN_ID),
        ledger=ledger if ledger is not None else a_ledger(),
        **overrides,
    )


# --- 5.2 The instruction, and what it may not carry ----------------------------------------------

UNIT_TOKENS = ("min", "minutes", "µm", "um", "mM", "kDa", "hour")
_A_UNIT = re.compile(r"\b(" + "|".join(re.escape(token) for token in UNIT_TOKENS) + r")\b")


def leaks_prior_knowledge(text: str) -> tuple[bool, bool]:
    """(carries a magnitude, carries a unit) — the instrument the instruction is held to."""
    return (any(character.isdigit() for character in text), bool(_A_UNIT.search(text)))


def test_the_check_for_prior_knowledge_can_fail():
    """The canary for this file's own instrument. An instruction that named the textbook figure is
    exactly what the spec forbids, so the check must catch it -- otherwise the assertion below is a
    green light that means nothing."""
    assert leaks_prior_knowledge("Report the doubling time, typically about 40 min.") == (
        True,
        True,
    )
    assert leaks_prior_knowledge("Report what the article states.") == (False, False)


def test_the_instruction_supplies_no_expected_value_and_no_unit():
    """The spec's "the model answers from the article, not from what it knows". A magnitude needs a
    digit, so the instruction carries none at all -- a rule with no judgement in it, unlike "no
    canonical figure", which nobody can check by reading."""
    assert leaks_prior_knowledge(INSTRUCTION) == (False, False)


def test_the_instruction_names_no_property_and_no_organism():
    """They reach the model through the user turn only, so one instruction fingerprint covers every
    question and the items it produced can be grouped by it."""
    assert QUESTION not in INSTRUCTION
    assert ORGANISM not in INSTRUCTION


def test_the_instruction_says_that_nothing_to_extract_is_a_correct_answer():
    """The spec requires this in so many words: a paper with nothing in it must be reportable, or
    the pressure is on the model to find something."""
    assert "NOTHING_TO_EXTRACT" in INSTRUCTION
    assert "correct answer" in INSTRUCTION


def test_the_instruction_gives_the_citation_marker_the_last_word():
    """Design D2: the marker outranks the verb, which is why the reader keeps the markers at all."""
    assert "[ref N]" in INSTRUCTION
    assert "outranks" in INSTRUCTION


def test_the_instruction_names_every_category_state_and_condition_field_the_record_has():
    """The instruction and `records.py` are one vocabulary. A category the model is never told
    about is one it will never return, and the rejected pool the review's second texts are drawn
    from would quietly lose a type."""
    for category in CandidateKind:
        assert category.value in INSTRUCTION
    for state in Provenance:
        assert state.value in INSTRUCTION
    for name in CONDITION_FIELDS:
        assert name in INSTRUCTION
    for kind in ClaimKind:
        assert kind.value in INSTRUCTION


def test_the_paper_is_the_first_system_block_and_carries_the_cache_breakpoint(article):
    blocks = system_blocks(article)

    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert MEASURED_SENTENCE in blocks[0]["text"]


def test_the_instruction_follows_the_breakpoint_so_the_paper_prefix_is_shared(article):
    """The second-text call sends the same paper under a different instruction. Only a prefix
    that ends with the paper is one both calls can read from the cache."""
    blocks = system_blocks(article)

    assert blocks[1]["text"] == INSTRUCTION
    assert "cache_control" not in blocks[1]
    assert len(blocks) == 2


def test_the_two_model_calls_share_the_cached_paper_block(article):
    """Extraction's and the second text's first block must be byte-identical, or the paper is
    written to the cache twice and read from it never."""
    from bionumbers import distractor

    ours = system_blocks(article)[0]
    theirs = distractor.system_blocks(article)[0]
    assert ours == theirs


def test_the_user_turn_names_the_question_and_the_organism_and_nothing_measurable():
    turn = user_turn(QUESTION, ORGANISM)

    assert turn["role"] == "user"
    assert QUESTION in turn["content"]
    assert ORGANISM in turn["content"]
    assert leaks_prior_knowledge(turn["content"]) == (False, False)


# --- 5.3 Verification, the one retry, and what a failure costs ------------------------------------


def test_everything_that_verifies_reaches_the_model_only_once(article):
    """The negative case for the retry: a correction is sent because a quote failed, not because a
    correction is always sent."""
    model = ScriptedModel(
        found(a_claim(MEASURED_SENTENCE, passage_holding(article, MEASURED_SENTENCE), value="65"))
    )

    result = run(model, article)

    assert len(model.calls) == 1
    assert result.state is PaperState.CLAIMS_FOUND


def test_a_quote_the_article_does_not_contain_is_named_back_to_the_model_once(article):
    good = passage_holding(article, MEASURED_SENTENCE)
    model = ScriptedModel(
        found(
            a_claim(MEASURED_SENTENCE, good, value="65"),
            a_claim(INVENTED_SENTENCE, good, value="9"),
        ),
        found(a_claim(MEASURED_SENTENCE, good, value="65")),
    )

    run(model, article)

    assert len(model.calls) == 2
    correction = model.calls[1]["messages"][-1]
    assert correction["role"] == "user"
    assert "claim 2, quote" in correction["content"]
    assert "not verbatim" in correction["content"]
    # The model's own first answer is what the correction edits, so the failure is an edit rather
    # than a second extraction from scratch.
    assert model.calls[1]["messages"][-2]["role"] == "assistant"


def test_a_quote_that_fails_twice_drops_its_claim_and_leaves_the_others(article):
    good = passage_holding(article, MEASURED_SENTENCE)
    invented = a_claim(INVENTED_SENTENCE, good, value="9")
    model = ScriptedModel(
        found(a_claim(MEASURED_SENTENCE, good, value="65"), invented),
        found(a_claim(MEASURED_SENTENCE, good, value="65"), invented),
    )

    result = run(model, article)

    assert [claim.value for claim in result.claims] == ["65"]
    assert result.unverifiable == ("PMC2288635-2",)
    assert result.state is PaperState.CLAIMS_FOUND


def test_a_claim_whose_value_verifies_is_still_dropped_when_another_of_its_quotes_does_not(article):
    """Every quote, not only the value's: a claim keeping a condition quote nobody could find is a
    sentence a reviewer reads as the article's own. The claim goes whole, because a claim with its
    conditions removed is not the claim that was extracted."""
    good = passage_holding(article, MEASURED_SENTENCE)
    invented = a_claim(
        MEASURED_SENTENCE,
        good,
        value="65",
        occurrences=(QuoteDraft(text=TEXTBOOK_SENTENCE, passage_id=good),),
        conditions=(
            ConditionDraft(
                name="medium",
                provenance=Provenance.FROM_METHODS,
                quote=INVENTED_SENTENCE,
                passage_id=good,
            ),
        ),
    )
    model = ScriptedModel(found(invented), found(invented))

    result = run(model, article)

    assert result.claims == ()
    assert result.unverifiable == ("PMC2288635-1",)
    correction = model.calls[1]["messages"][-1]["content"]
    assert "occurrence 1" in correction
    assert "condition medium" in correction


def test_a_derived_claim_s_input_quotes_are_verified_too(article):
    """No test set `inputs` until a verifier seeded their verification away and nothing failed.
    A derived value's inputs are quotes like any other: invented, they drop the claim."""
    good = passage_holding(article, MEASURED_SENTENCE)
    derived = a_claim(
        MEASURED_SENTENCE,
        good,
        value="65",
        candidate_kind=CandidateKind.DERIVED,
        inputs=(QuoteDraft(text=INVENTED_SENTENCE, passage_id=good),),
    )
    model = ScriptedModel(found(derived), found(derived))

    result = run(model, article)

    assert len(model.calls) == 2, "the invented input is named back once"
    assert result.claims == ()
    assert result.unverifiable == ("PMC2288635-1",)


def test_a_derived_claim_with_real_inputs_keeps_them(article):
    good = passage_holding(article, MEASURED_SENTENCE)
    derived = a_claim(
        MEASURED_SENTENCE,
        good,
        value="65",
        candidate_kind=CandidateKind.DERIVED,
        inputs=(QuoteDraft(text=MEASURED_SENTENCE, passage_id=good),),
    )

    result = run(ScriptedModel(found(derived)), article)

    (claim,) = result.claims
    assert claim.candidate_kind is CandidateKind.DERIVED
    assert [quote.text for quote in claim.inputs] == [MEASURED_SENTENCE]


def test_a_ceiling_met_on_the_retry_discards_what_the_first_call_established(article):
    """The first call verified one claim and named one failure; the retry would cross the ceiling.
    The spec's "discarded rather than half-kept" is about exactly this moment, and the only other
    ceiling test stops before the first call, where there is nothing to keep."""
    good = passage_holding(article, MEASURED_SENTENCE)
    model = ScriptedModel(
        found(
            a_claim(MEASURED_SENTENCE, good, value="65"),
            a_claim(INVENTED_SENTENCE, good, value="9"),
        ),
        found(a_claim(MEASURED_SENTENCE, good, value="65")),
    )
    # One call fits and a second does not: the bound sits between one projection and one
    # projection plus what the first call actually cost. Derived from the constants rather than
    # written as a number, so a change to MAX_TOKENS moves it rather than silently retiring the
    # test (which is what happened when the cap went from 8,000 to 16,000).
    projected = projected_cost(MODEL, input_tokens=USAGE.input_tokens, max_tokens=MAX_TOKENS)
    spent = cost(MODEL, USAGE).usd
    ledger = a_ledger(per_paper=projected + spent / 2)

    result = run(model, article, ledger=ledger)

    assert len(model.calls) == 1, "the retry was refused before it was made"
    assert result.state is PaperState.CEILING_REACHED
    assert result.claims == () and result.unverifiable == ()
    assert result.spend.calls == 1, "what the first call cost is still on the record"


def test_every_quote_that_does_reach_the_record_verifies_against_the_article(article):
    """The positive half of the rule, over a mixed answer: what survives two rounds is verbatim,
    including the quotes of the rejected candidates the review draws its second texts from."""
    good = passage_holding(article, MEASURED_SENTENCE)
    second = passage_holding(article, SECOND_SENTENCE)
    answer = found(
        a_claim(
            MEASURED_SENTENCE,
            good,
            value="65",
            occurrences=(QuoteDraft(text=SECOND_SENTENCE, passage_id=second),),
            conditions=(
                ConditionDraft(
                    name="organism",
                    provenance=Provenance.BESIDE_VALUE,
                    quote=SECOND_SENTENCE,
                    passage_id=second,
                ),
            ),
        ),
        a_claim(TEXTBOOK_SENTENCE, good, value="40"),
        rejected=(
            RejectedDraft(
                value="5",
                unit="min",
                kind=CandidateKind.CITED,
                quote=QuoteDraft(text=SECOND_SENTENCE, passage_id=second),
                reason="stated with a citation marker",
            ),
        ),
    )
    model = ScriptedModel(answer, answer)

    result = run(model, article)

    checked = [
        quote
        for claim in result.claims
        for quote in (claim.quote, *claim.occurrences, *claim.inputs)
    ] + [candidate.quote for candidate in result.rejected]
    assert checked
    for quote in checked:
        assert isinstance(quotes.verify(quote.text, article), quotes.Verified)
    for claim in result.claims:
        for condition in claim.conditions:
            if condition.quote:
                assert isinstance(quotes.verify(condition.quote, article), quotes.Verified)


def test_a_rejected_candidate_with_an_unverifiable_quote_is_dropped_without_being_unverifiable(
    article,
):
    """`unverifiable` is a list of claim ids. A candidate has no id and is not a claim, so it goes
    quietly -- the pool it belongs to is allowed to come up short."""
    good = passage_holding(article, MEASURED_SENTENCE)
    answer = found(
        a_claim(MEASURED_SENTENCE, good, value="65"),
        rejected=(
            RejectedDraft(
                value="9",
                unit="min",
                kind=CandidateKind.CITED,
                quote=QuoteDraft(text=INVENTED_SENTENCE, passage_id=good),
                reason="cited",
            ),
        ),
    )
    model = ScriptedModel(answer, answer)

    result = run(model, article)

    assert result.rejected == ()
    assert result.unverifiable == ()
    assert len(result.claims) == 1


def test_a_rejected_candidate_that_verifies_is_kept(article):
    """The negative case for the drop above, varying the one dimension the rule reads -- whether
    the quote is in the article -- and nothing else."""
    good = passage_holding(article, MEASURED_SENTENCE)
    second = passage_holding(article, SECOND_SENTENCE)
    model = ScriptedModel(
        found(
            a_claim(MEASURED_SENTENCE, good, value="65"),
            rejected=(
                RejectedDraft(
                    value="5",
                    unit="min",
                    kind=CandidateKind.CITED,
                    quote=QuoteDraft(text=SECOND_SENTENCE, passage_id=second),
                    reason="cited",
                ),
            ),
        )
    )

    result = run(model, article)

    assert [candidate.value for candidate in result.rejected] == ["5"]


def test_a_value_the_article_did_not_measure_is_a_candidate_however_it_was_returned(article):
    """The spec's "only a value the paper measured or derived SHALL be a claim", enforced here
    rather than trusted to the instruction. Moved rather than dropped: it is a legitimate second
    text, and dropping it would reward dressing such sentences as claims."""
    good = passage_holding(article, MEASURED_SENTENCE)
    model = ScriptedModel(
        found(
            a_claim(MEASURED_SENTENCE, good, value="65", candidate_kind=CandidateKind.CITED),
            a_claim(SECOND_SENTENCE, passage_holding(article, SECOND_SENTENCE), value="5"),
        )
    )

    result = run(model, article)

    assert [claim.value for claim in result.claims] == ["5"]
    assert [(c.value, c.kind) for c in result.rejected] == [("65", CandidateKind.CITED)]


def test_a_condition_the_article_never_states_is_kept_with_no_quote_and_no_location(article):
    """The spec scenario: NOT_STATED with an empty quote is an answer, not a failed quote. Checking
    it would refuse the empty string and make "the article does not say" unreportable."""
    good = passage_holding(article, MEASURED_SENTENCE)
    model = ScriptedModel(
        found(
            a_claim(
                MEASURED_SENTENCE,
                good,
                value="65",
                conditions=(ConditionDraft(name="temperature", provenance=Provenance.NOT_STATED),),
            )
        )
    )

    result = run(model, article)

    (condition,) = result.claims[0].conditions
    assert (condition.provenance, condition.quote, condition.location) == (
        Provenance.NOT_STATED,
        "",
        None,
    )
    assert len(model.calls) == 1


def test_a_right_quote_with_a_wrong_passage_id_is_located_where_it_was_found(article):
    """Design D3: a location error is corrected, not refused. The quote is in the article, so the
    claim stands; the id the model named is not where it came from, so the id is not recorded."""
    named = passage_holding(article, SECOND_SENTENCE)
    actual = passage_holding(article, MEASURED_SENTENCE)
    assert named != actual, "the fixture no longer separates the two sentences"
    model = ScriptedModel(found(a_claim(MEASURED_SENTENCE, named, value="65")))

    result = run(model, article)

    assert result.claims[0].quote.location.passage_id == actual
    assert len(model.calls) == 1


def test_a_right_quote_with_the_right_passage_id_keeps_it(article):
    """The negative case for the correction: the same claim varying only the named id."""
    actual = passage_holding(article, MEASURED_SENTENCE)
    model = ScriptedModel(found(a_claim(MEASURED_SENTENCE, actual, value="65")))

    result = run(model, article)

    assert result.claims[0].quote.location.passage_id == actual


# --- 5.4 One named ending per paper ---------------------------------------------------------------


def claims_found(article):
    model = ScriptedModel(
        found(a_claim(MEASURED_SENTENCE, passage_holding(article, MEASURED_SENTENCE), value="65"))
    )
    return run(model, article), model


def nothing_to_extract(article):
    model = ScriptedModel(
        ExtractionOutput(
            state="NOTHING_TO_EXTRACT",
            reason="the property appears only as figure curves",
        )
    )
    return run(model, article), model


def not_a_research_article(essay):
    model = ScriptedModel()
    return run(model, essay, paper=ESSAY), model


def ceiling_reached(article):
    model = ScriptedModel(
        found(a_claim(MEASURED_SENTENCE, passage_holding(article, MEASURED_SENTENCE), value="65"))
    )
    return run(model, article, ledger=a_ledger(per_paper=0.0001)), model


def failed(article):
    model = ScriptedModel(
        raises=anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
    )
    return run(model, article), model


def test_a_paper_with_a_verified_claim_ends_in_claims_found(article):
    result, _ = claims_found(article)

    assert result.state is PaperState.CLAIMS_FOUND
    assert len(result.claims) == 1
    assert str(len(result.claims)) in result.reason


def test_a_paper_the_model_read_and_found_nothing_in_keeps_the_model_s_reason(article):
    """The spec keeps "states no value" apart from "could not be read", and the reason is the only
    place the difference is legible to whoever reads the run."""
    result, _ = nothing_to_extract(article)

    assert result.state is PaperState.NOTHING_TO_EXTRACT
    assert result.reason == "the property appears only as figure curves"


def test_a_paper_whose_every_claim_was_dropped_says_so_rather_than_saying_the_paper_is_empty(
    article,
):
    """Both routes end NOTHING_TO_EXTRACT and they are different facts about the run: one is about
    the article, the other about the model. The reason is what tells them apart."""
    good = passage_holding(article, MEASURED_SENTENCE)
    invented = found(a_claim(INVENTED_SENTENCE, good, value="9"))
    model = ScriptedModel(invented, invented)

    result = run(model, article)

    assert result.state is PaperState.NOTHING_TO_EXTRACT
    assert result.unverifiable == ("PMC2288635-1",)
    assert "dropped" in result.reason


def test_a_paper_with_no_methods_section_is_not_sent_to_the_model_at_all(essay):
    """The cheapest paper is the one not sent. An essay's numbers are other people's, and the whole
    ceiling would buy its reference list back as claims."""
    result, model = not_a_research_article(essay)

    assert result.state is PaperState.NOT_A_RESEARCH_ARTICLE
    assert (model.calls, model.counts) == ([], [])
    assert result.spend == Spend()


def test_a_paper_that_would_cross_its_ceiling_is_not_called_and_keeps_nothing(article):
    """The spec's "discarded rather than half-kept": the queued answer would have verified, and
    it is still not in the record, because a half paper in the review looks exactly like a whole
    one."""
    result, model = ceiling_reached(article)

    assert result.state is PaperState.CEILING_REACHED
    assert result.claims == ()
    assert model.calls == []
    assert result.spend == Spend()
    assert "ceiling" in result.reason


def test_a_service_error_ends_the_paper_and_names_what_happened(article):
    result, _ = failed(article)

    assert result.state is PaperState.FAILED
    assert "APIConnectionError" in result.reason


def test_an_unexpected_error_ends_the_paper_the_same_way(article):
    """FAILED is not only for the provider's own exception type: a run is tens of papers and any
    one of them may meet something nobody typed, which must cost that paper and not the run."""
    model = ScriptedModel(raises=RuntimeError("the schema could not be parsed"))

    result = run(model, article)

    assert result.state is PaperState.FAILED
    assert result.reason == "RuntimeError: the schema could not be parsed"


def test_a_response_the_adapter_could_not_read_is_still_paid_for(article):
    """The first live run had a paper end FAILED at $0.00 and no call: the adapter raised before
    the ledger heard about the usage. What the provider reported travels on the error."""

    class Refused(Exception):
        def __init__(self):
            super().__init__("output does not match the schema")
            self.usage = USAGE

    ledger = a_ledger()
    result = run(ScriptedModel(raises=Refused()), article, ledger=ledger)

    assert result.state is PaperState.FAILED
    assert result.spend.calls == 1
    assert result.spend.input_tokens == USAGE.input_tokens
    assert ledger.run.calls == 1


def test_a_range_may_span_more_than_two_conditions(article):
    """A pair type made a paper with a range over five antibiotic concentrations FAILED on the
    first live run; the record takes however many the paper has."""
    spanning = "followed in 50 cells every 5 min for 60 min"
    draft = ClaimDraft(
        **{
            **a_claim(spanning, passage_holding(article, spanning), value="5–60").model_dump(),
            "kind": ClaimKind.RANGE_OVER_CONDITIONS,
            "endpoint_conditions": ("0.25 ng/mL", "5 ng/mL", "50 ng/mL", "500 ng/mL", "control"),
        }
    )

    (claim,) = run(ScriptedModel(found(draft)), article).claims

    assert len(claim.endpoint_conditions) == 5


def test_a_verbatim_quote_that_does_not_state_the_value_is_a_failure_too(article):
    """The first live run: two claims of 346 h and 693 h quoting a sentence that says
    'nearly 200-fold'. Verbatim, and not the value. Named back once; dropped the second time."""
    good = passage_holding(article, MEASURED_SENTENCE)
    arithmetic = a_claim(MEASURED_SENTENCE, good, value="346.0", unit="h")
    model = ScriptedModel(found(arithmetic), found(arithmetic))

    result = run(model, article)

    assert len(model.calls) == 2
    assert "does not state the value" in model.calls[1]["messages"][-1]["content"]
    assert result.claims == ()
    assert result.unverifiable == ("PMC2288635-1",)


def test_every_state_but_unreadable_is_reachable_from_here(article, essay):
    """UNREADABLE is a fact about access, established by discovery before extraction is attempted,
    so this step must never produce it -- and must produce every other one."""
    produced = {
        result.state
        for result, _ in (
            claims_found(article),
            nothing_to_extract(article),
            not_a_research_article(essay),
            ceiling_reached(article),
            failed(article),
        )
    }

    assert produced == set(PaperState) - {PaperState.UNREADABLE}


# --- 5.5 The paper's value, not the famous one ----------------------------------------------------


def test_the_textbook_value_cannot_become_a_claim_because_the_article_never_states_it(article):
    """ADR-0040's recorded failure: this paper states 65 min where the textbook says 40, and the
    blind arm answered 40 with confidence. The instruction is where that is countered and the
    checker is where it is enforced -- so this holds whatever the model returns."""
    good = passage_holding(article, MEASURED_SENTENCE)
    answer = found(
        a_claim(MEASURED_SENTENCE, good, value="65"),
        a_claim(TEXTBOOK_SENTENCE, good, value="40"),
    )
    model = ScriptedModel(answer, answer)

    result = run(model, article)

    assert [claim.value for claim in result.claims] == ["65"]
    assert "65" in result.claims[0].quote.text
    for claim in result.claims:
        assert "40 min" not in claim.value
        assert "40 min" not in claim.quote.text
    assert result.unverifiable == ("PMC2288635-2",)


# --- 5.6 What produced a claim --------------------------------------------------------------------


def test_the_instruction_fingerprint_is_the_hash_of_the_instruction():
    """Computed independently here rather than compared to itself: the fingerprint's whole job is
    to change when the instruction does, and a test calling the same function twice cannot see
    whether it hashes anything at all."""
    assert instruction_sha256() == hashlib.sha256(INSTRUCTION.encode("utf-8")).hexdigest()
    assert instruction_sha256() != hashlib.sha256(b"").hexdigest()


def test_every_claim_and_the_paper_state_carry_what_produced_them(article):
    result, _ = claims_found(article)

    for fingerprint in (result.fingerprint, *[claim.fingerprint for claim in result.claims]):
        assert fingerprint.model == MODEL
        assert fingerprint.instruction_sha256 == instruction_sha256()
        assert fingerprint.article_id == PAPER.pmcid
        assert fingerprint.run_id == RUN_ID


def test_an_ending_with_no_claims_is_still_attributed(article):
    """Grouping by generator has to work for the endings too, or a comparison of state
    distributions would silently mix two models."""
    result, _ = ceiling_reached(article)

    assert result.fingerprint.run_id == RUN_ID
    assert result.fingerprint.instruction_sha256 == instruction_sha256()


def test_spend_is_recorded_for_the_paper_in_whatever_state_it_ends(article):
    good = passage_holding(article, MEASURED_SENTENCE)
    invented = a_claim(INVENTED_SENTENCE, good, value="9")
    model = ScriptedModel(
        found(a_claim(MEASURED_SENTENCE, good, value="65"), invented),
        found(a_claim(MEASURED_SENTENCE, good, value="65")),
    )

    result = run(model, article)

    assert result.spend.calls == 2
    assert result.spend.input_tokens == 2 * USAGE.input_tokens
    assert result.spend.usd > 0


def test_the_projection_is_asked_of_the_exact_request_before_every_call(article):
    """The bound is only as good as its call sites, so both calls must be projected -- the retry
    included, which is the one a "project once per paper" shortcut would miss."""
    good = passage_holding(article, MEASURED_SENTENCE)
    invented = a_claim(INVENTED_SENTENCE, good, value="9")
    model = ScriptedModel(found(invented), found(invented))

    run(model, article)

    assert len(model.counts) == len(model.calls) == 2
    for counted, called in zip(model.counts, model.calls, strict=True):
        assert counted["messages"] == called["messages"]
        assert counted["system"] == called["system"]
    assert model.calls[0]["max_tokens"] == MAX_TOKENS


# --- 5.7 The run file, and the path it may not be written to --------------------------------------


def two_results(article):
    return [claims_found(article)[0], nothing_to_extract(article)[0]]


def test_a_run_round_trips_through_its_file(tmp_path, article):
    results = two_results(article)

    path = write_results(results, tmp_path / "run-of-the-test")

    assert path.read_text(encoding="utf-8").strip().count("\n") == len(results) - 1
    assert read_results(path) == results


def test_a_run_file_git_would_track_is_refused_before_anything_is_written(article):
    """The one irreversible mistake this project can make. Every quote in the file is the article's
    own text, and three checkouts here share one origin, so a committed run publishes it."""
    tracked = Path(__file__).parent / "would-be-committed"

    with pytest.raises(RunFileWouldBeCommitted):
        write_results(two_results(article), tracked)

    assert not tracked.exists()


def test_a_run_file_outside_the_repository_is_written(tmp_path, article):
    """The negative case for the refusal, varying the dimension the guard reads -- whether git
    would track the path -- and nothing else. Without it the guard could be refusing everything."""
    path = write_results(two_results(article), tmp_path / "run")

    assert path.exists()
    assert not path.with_name(path.name + ".partial").exists()
