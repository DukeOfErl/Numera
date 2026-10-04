"""Harvest mode: the instruction it sends, the labels it keeps, and what stays the pipeline's.

The article is real (the replisome fixture) and the model is scripted, as in
`test_bionumbers_extraction.py`, so the quote checker in the middle is doing its actual job.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bionumbers import harvest
from bionumbers.extraction import (
    INSTRUCTION,
    ClaimDraft,
    ExtractionOutput,
    QuoteDraft,
    extract,
    instruction_sha256,
)
from bionumbers.jats import read_jats
from bionumbers.records import CandidateKind, ClaimKind, Paper, PaperState
from bionumbers.spend import Ceiling, Ledger

FIXTURES = Path(__file__).parent / "fixtures" / "europepmc"
MEASURED_SENTENCE = "are present for 65 min on average"
PAPER = Paper(pmcid="PMC2288635", title="Replisome dynamics", year=2008, licence="CC BY")
USAGE = SimpleNamespace(
    input_tokens=61_000, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=900
)


@pytest.fixture(scope="module")
def article():
    return read_jats((FIXTURES / "fulltext_PMC2288635.xml").read_text(encoding="utf-8"))


class ScriptedModel:
    def __init__(self, *answers: ExtractionOutput) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def count_tokens(self, *, system, messages, output_format=None):
        return SimpleNamespace(input_tokens=61_000)

    def parse(self, *, system, messages, output_format, max_tokens):
        self.calls.append({"system": system, "messages": messages})
        return SimpleNamespace(parsed_output=self.answers.pop(0), usage=USAGE)


def a_draft(article, *, property_name: str, organism_name: str, property_class: str) -> ClaimDraft:
    passage = next(p.id for p in article.passages if MEASURED_SENTENCE in p.text)
    return ClaimDraft(
        property_in_paper="time replisomes are present",
        property_name=property_name,
        property_class=property_class,
        organism_name=organism_name,
        value="65",
        unit="min",
        kind=ClaimKind.SINGLE,
        candidate_kind=CandidateKind.MEASURED,
        quote=QuoteDraft(text=MEASURED_SENTENCE, passage_id=passage),
    )


def harvested(model, article):
    return extract(
        model,
        article,
        PAPER,
        question="",
        organism="",
        run_id="h1",
        ledger=Ledger(Ceiling()),
        instruction=harvest.HARVEST_INSTRUCTION,
        user=harvest.user_turn(),
    )


# --- the instruction ---------------------------------------------------------------------------


def test_the_harvest_instruction_keeps_every_rule_of_the_question_instruction_but_its_opening():
    """Built from it, not restated: the quoting rule, the claim categories, the citation-marker
    rule and the conditions are the same text in both modes."""
    opening, rules = INSTRUCTION.split("\n\n", 1)
    assert rules in harvest.HARVEST_INSTRUCTION
    assert opening not in harvest.HARVEST_INSTRUCTION
    assert "no single question" in harvest.HARVEST_INSTRUCTION


def test_the_bound_on_claims_is_in_the_instruction():
    assert f"AT MOST {harvest.MAX_CLAIMS} CLAIMS" in harvest.HARVEST_INSTRUCTION


def test_the_instruction_asks_for_a_latin_name_and_a_value_without_its_unit():
    """Both read off the first seed: "yeast" and "mouse" as species, and "about 45%" with a
    percent sign in the unit field as well."""
    assert "Latin binomial" in harvest.HARVEST_INSTRUCTION
    assert "THE VALUE FIELD HOLDS NO UNIT" in harvest.HARVEST_INSTRUCTION


def test_the_scope_travels_in_the_user_turn_and_names_every_class_and_exclusion():
    content = harvest.user_turn()["content"]
    for name, covers in harvest.PROPERTY_CLASSES:
        assert name in content and covers in content
    for kind in harvest.EXCLUDED:
        assert kind in content


def test_the_scope_hands_the_model_no_unit_and_no_magnitude():
    """The instruction forbids answering from what the model knows; a scope that named units or
    typical figures would be this module doing it for the model."""
    scope = harvest.user_turn()["content"]
    assert not any(character.isdigit() for character in scope)
    for unit in (" nm", " μm", " um", " min", " μM", " mM", " kDa"):
        assert unit + " " not in scope and unit + "," not in scope


def test_a_harvested_paper_is_fingerprinted_apart_from_a_questioned_one(article):
    result = harvested(ScriptedModel(ExtractionOutput(state="NOTHING_TO_EXTRACT")), article)

    assert result.fingerprint.instruction_sha256 == instruction_sha256(harvest.HARVEST_INSTRUCTION)
    assert result.fingerprint.instruction_sha256 != instruction_sha256()


# --- the call and the record ---------------------------------------------------------------------


def test_the_paper_is_still_the_cached_first_block_and_the_harvest_instruction_the_second(article):
    model = ScriptedModel(ExtractionOutput(state="NOTHING_TO_EXTRACT"))

    harvested(model, article)

    system = model.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[1]["text"] == harvest.HARVEST_INSTRUCTION
    assert model.calls[0]["messages"] == [harvest.user_turn()]


def test_a_harvested_claim_is_named_by_its_label_and_keeps_its_class_and_species(article):
    draft = a_draft(
        article,
        property_name="replication period",
        organism_name="Escherichia coli",
        property_class="TIME",
    )

    result = harvested(
        ScriptedModel(ExtractionOutput(state="CLAIMS_FOUND", claims=[draft])), article
    )

    assert result.state is PaperState.CLAIMS_FOUND
    (claim,) = result.claims
    assert claim.property_asked == "replication period"
    assert (claim.property_class, claim.organism_name) == ("TIME", "Escherichia coli")
    assert harvest.question_of(claim) == "replication period (Escherichia coli)"


def test_a_claim_with_no_label_falls_back_to_the_article_s_own_term(article):
    """The negative of the naming rule, varying the label: an empty one must not leave a claim
    with no name at all, since the review screen judges a text against it."""
    draft = a_draft(article, property_name="", organism_name="", property_class="")

    result = harvested(
        ScriptedModel(ExtractionOutput(state="CLAIMS_FOUND", claims=[draft])), article
    )

    (claim,) = result.claims
    assert claim.property_asked == "time replisomes are present"
    assert harvest.question_of(claim) == "time replisomes are present"


def test_a_question_still_names_the_claim_when_one_was_asked(article):
    """Question mode is untouched: the label the model may write does not displace the question."""
    draft = a_draft(
        article, property_name="replication period", organism_name="E. coli", property_class="TIME"
    )
    model = ScriptedModel(ExtractionOutput(state="CLAIMS_FOUND", claims=[draft]))

    result = extract(
        model,
        article,
        PAPER,
        question="time to replicate the chromosome",
        organism="Escherichia coli",
        run_id="q1",
        ledger=Ledger(Ceiling()),
    )

    assert result.claims[0].property_asked == "time to replicate the chromosome"
    assert model.calls[0]["system"][1]["text"] == INSTRUCTION


def test_a_fabricated_quote_is_dropped_in_harvest_mode_as_in_any_other(article):
    draft = a_draft(
        article, property_name="replication period", organism_name="E. coli", property_class="TIME"
    )
    invented = draft.model_copy(
        update={"quote": QuoteDraft(text="are present for 40 min on average", passage_id="p1")}
    )
    answer = ExtractionOutput(state="CLAIMS_FOUND", claims=[invented])

    result = harvested(ScriptedModel(answer, answer), article)

    assert result.claims == ()
    assert result.state is PaperState.NOTHING_TO_EXTRACT
