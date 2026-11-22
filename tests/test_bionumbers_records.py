"""The records survive the trip through JSON, which is the trip every run makes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from numera_validator.records import (
    CONDITION_FIELDS,
    DISTRACTOR_PREFERENCE,
    CandidateKind,
    Claim,
    ClaimKind,
    ConditionField,
    DistractorType,
    Fingerprint,
    Location,
    Paper,
    PaperResult,
    PaperState,
    Provenance,
    Quote,
    Spend,
)

FP = Fingerprint(model="m", instruction_sha256="abc", article_id="PMC1", run_id="r1")
CELL = Location(
    passage_id="tbl1-r2-c3",
    section_path=("Results", "Table 1"),
    kind="td",
    row_headers=("LB, 37 °C",),
    column_headers=("Doubling time (min)",),
)


def a_claim():
    return Claim(
        claim_id="c1",
        property_asked="doubling time",
        property_in_paper="generation time",
        value="39 ± 1",
        unit="min",
        kind=ClaimKind.WITH_UNCERTAINTY,
        candidate_kind=CandidateKind.MEASURED,
        quote=Quote(text="39 ± 1", location=CELL),
        conditions=(
            ConditionField(name="temperature", provenance=Provenance.FROM_METHODS, quote="37 °C"),
            ConditionField(name="medium", provenance=Provenance.NOT_STATED),
        ),
        fingerprint=FP,
    )


def test_a_paper_result_round_trips_through_json():
    result = PaperResult(
        paper=Paper(pmcid="PMC1", title="T", year=2026, licence="CC BY 4.0"),
        state=PaperState.CLAIMS_FOUND,
        claims=(a_claim(),),
        spend=Spend(input_tokens=10, usd=0.01, calls=1),
        fingerprint=FP,
    )

    assert PaperResult.model_validate_json(result.model_dump_json()) == result


def test_states_serialise_as_their_names():
    assert PaperState.UNREADABLE.value == "UNREADABLE"
    assert a_claim().model_dump()["kind"] == "WITH_UNCERTAINTY"


def test_records_are_frozen():
    with pytest.raises(ValidationError):
        a_claim().value = "40"  # type: ignore[misc]


def test_an_unknown_field_is_refused():
    """A run file from a later version must not be read as if it were this one."""
    with pytest.raises(ValidationError):
        Location.model_validate({"passage_id": "p1", "page": 3})


def test_the_preference_order_is_the_full_set_hardest_first():
    assert set(DISTRACTOR_PREFERENCE) == set(DistractorType)
    assert DISTRACTOR_PREFERENCE[0] is DistractorType.ADJACENT_CONDITION
    assert DISTRACTOR_PREFERENCE[-1] is DistractorType.DERIVATION_HALF


def test_method_is_one_of_the_condition_fields():
    assert "method" in CONDITION_FIELDS and CONDITION_FIELDS[0] == "organism"


def test_spend_adds():
    total = Spend(input_tokens=1, usd=0.5, calls=1).plus(
        Spend(cache_read_tokens=2, usd=0.25, calls=1)
    )

    assert (total.input_tokens, total.cache_read_tokens, total.usd, total.calls) == (1, 2, 0.75, 2)
