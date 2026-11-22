"""The property is one name: the measure of the object (ADR-1700)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from test_bionumbers_store import QUESTION, RUN, a_result, an_item

from numera_validator import naming, store
from numera_validator.records import ReviewItem
from numera_validator.spend import Ceiling

USAGE = SimpleNamespace(input_tokens=500, output_tokens=30, cache_read_input_tokens=0)


# --- the join -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("measure", "measured_object", "named"),
    [
        (
            "Average length",
            "F-actin filaments in non-contracting rings",
            "Average length of F-actin filaments in non-contracting rings",
        ),
        ("diameter", "cytokinetic actin rings", "Diameter of cytokinetic actin rings"),
        (" Doubling time ", " Escherichia coli in LB ", "Doubling time of Escherichia coli in LB"),
    ],
)
def test_the_name_is_the_measure_of_the_object(measure, measured_object, named):
    assert naming.property_name(measure, measured_object) == named


@pytest.mark.parametrize(
    ("measure", "measured_object"),
    [
        ("Average length", ""),
        ("", "cytokinetic actin rings"),
        ("   ", "cytokinetic actin rings"),
        ("Length", "actin filament length"),  # the object says the measure
        ("Cytokinetic ring diameter", "cytokinetic ring"),  # the measure says the object
        ("Diameter", "diameter"),
        ("length", "Actin Filament LENGTH"),  # case does not hide the repeat
    ],
)
def test_a_part_missing_or_repeated_makes_no_name(measure, measured_object):
    assert naming.property_name(measure, measured_object) == ""


# --- the backfill ---------------------------------------------------------------------------


class _Namer:
    """Answers the backfill's calls from a queue and keeps what it was asked."""

    def __init__(self, *answers: naming.PropertyOutput) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def count_tokens(self, *, system, messages, output_format=None):
        return SimpleNamespace(input_tokens=500)

    def parse(self, *, system, messages, output_format, max_tokens):
        self.calls.append({"system": system, "content": messages[0]["content"]})
        assert output_format is naming.PropertyOutput
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(parsed_output=answer, usage=USAGE, raw={"model": "m"})


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    store.create_all(engine)
    store.load_run(
        engine,
        [a_result()],
        [an_item("i1"), an_item("i2"), an_item("i3")],
        question=QUESTION,
        run_id=RUN,
    )
    with engine.begin() as conn:
        conn.execute(store.review_item.update().values(property=""))
    return engine


def _properties(engine) -> dict[str, str]:
    with engine.begin() as conn:
        items = store.review_item.c
        return dict(conn.execute(select(items.item_id, items.property)).all())


def test_the_backfill_names_each_unnamed_item_and_records_what_it_refused(engine):
    model = _Namer(
        naming.PropertyOutput(measure="Doubling time", measured_object="Escherichia coli"),
        naming.PropertyOutput(measure="Doubling time", measured_object=""),
        naming.PropertyOutput(measure="Generation time", measured_object="E. coli in LB"),
    )

    done = naming.backfill(engine, model, "anthropic/claude-sonnet-5.5")

    assert done.named == 2
    assert done.refused == [naming.Refusal("i2", "Doubling time", "")]
    assert done.failed == [] and done.stopped == ""
    assert done.spend_usd > 0, "every call is on the ledger"
    assert _properties(engine) == {
        "i1": "Doubling time of Escherichia coli",
        "i2": "",
        "i3": "Generation time of E. coli in LB",
    }


def test_the_model_sees_the_entry_and_not_the_paper(engine):
    model = _Namer(*[naming.PropertyOutput(measure="m", measured_object="o")] * 3)

    naming.backfill(engine, model, "anthropic/claude-sonnet-5.5")

    content = model.calls[0]["content"]
    item = an_item("i1")
    assert item.claim.quote.text in content
    assert f"{item.claim.value} {item.claim.unit}" in content
    assert item.claim.property_in_paper in content
    assert item.paper.title in content
    assert "Earlier label: doubling time" in content
    assert model.calls[0]["system"] == naming.BACKFILL_INSTRUCTION
    assert naming.MEASURE_RULE in naming.BACKFILL_INSTRUCTION
    assert naming.OBJECT_RULE in naming.BACKFILL_INSTRUCTION


def test_a_named_item_is_not_asked_about_again(engine):
    first = _Namer(*[naming.PropertyOutput(measure="m", measured_object="o")] * 3)
    naming.backfill(engine, first, "anthropic/claude-sonnet-5.5")

    second = _Namer()
    done = naming.backfill(engine, second, "anthropic/claude-sonnet-5.5")

    assert done.named == 0 and second.calls == []


def test_one_failed_call_costs_one_item_its_name_and_the_run_goes_on(engine):
    model = _Namer(
        naming.PropertyOutput(measure="m", measured_object="o"),
        RuntimeError("boom"),
        naming.PropertyOutput(measure="m", measured_object="o"),
    )

    done = naming.backfill(engine, model, "anthropic/claude-sonnet-5.5")

    assert done.named == 2
    assert done.failed == ["i2: RuntimeError: boom"]
    assert _properties(engine)["i2"] == ""


def test_the_run_budget_stops_the_run_and_keeps_what_was_named(engine):
    model = _Namer(*[naming.PropertyOutput(measure="m", measured_object="o")] * 3)

    done = naming.backfill(
        engine, model, "anthropic/claude-sonnet-5.5", ceiling=Ceiling(per_paper=1.0, per_run=0.009)
    )

    # Each call projects $0.007 (500 in, 600 out at Sonnet's prices) and costs $0.0013; the
    # third would cross the bound.
    assert done.stopped
    assert done.named == 2
    assert len(model.calls) == done.named
    assert sum(1 for name in _properties(engine).values() if name) == done.named


def test_a_reviewed_item_s_record_is_not_rewritten(engine):
    before = {row.item_id: row.item_json for row in _rows(engine)}
    model = _Namer(*[naming.PropertyOutput(measure="m", measured_object="o")] * 3)

    naming.backfill(engine, model, "anthropic/claude-sonnet-5.5")

    assert {row.item_id: row.item_json for row in _rows(engine)} == before
    assert all(ReviewItem.model_validate_json(j) for j in before.values())


def _rows(engine):
    with engine.begin() as conn:
        return conn.execute(select(store.review_item)).all()
