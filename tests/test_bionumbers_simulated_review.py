"""The simulated review: what a model is shown at each step, which items a role is given, what
gets recorded.

Offline throughout. The model is a scripted double behind the same two-method protocol the
extraction step codes against, and the store is the real one over in-memory SQLite, so what these
cases read back is what a dashboard would.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select

from numera_validator import cli, review, simulated_review, store
from numera_validator.extraction import ProviderRefused
from numera_validator.records import (
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
    ReviewerRole,
    ReviewItem,
    SecondTextKind,
    TableCell,
    TableView,
)
from numera_validator.simulated_review import (
    Chosen,
    Judged,
    Reviewer,
    assigned,
    reveal,
    screen,
)
from numera_validator.spend import Ceiling, Unpriceable

QUESTION = "doubling time of Escherichia coli"
RUN = "run-1"
MODEL = "anthropic/claude-haiku-4.5"
FP = Fingerprint(model="opus", instruction_sha256="abc123", article_id="PMC1", run_id=RUN)
PAPER = Paper(pmcid="PMC1", pmid="39123456", title="A paper", year=2026, licence="CC BY 4.0")
SUPPORTING = "a doubling time of 39 min in rich medium"
SECOND = "21 min in minimal medium"

#: 1,000 tokens in and 100 out on Haiku 4.5 is $0.0015; the projection before a call is the
#: 1,000 counted tokens plus `MAX_OUTPUT_TOKENS` of output, $0.021.
USAGE = SimpleNamespace(input_tokens=1000, output_tokens=100)
ONE_CALL_USD = 0.0015
ONE_PROJECTION_USD = 0.001 + simulated_review.MAX_OUTPUT_TOKENS * 5e-6

STUDENT = Reviewer(role=ReviewerRole.STUDENT, model=MODEL)


def an_item(
    item_id: str = "i1",
    *,
    second_kind: SecondTextKind = SecondTextKind.DISTRACTOR,
    distractor_type: DistractorType | None = DistractorType.ADJACENT_CONDITION,
    tables: tuple[TableView, ...] = (),
) -> ReviewItem:
    """`second_kind` and `distractor_type` are parameters, never fixture constants: the screen
    must not read them and the tally must, so both cases have to be free to vary them alone."""
    return ReviewItem(
        item_id=item_id,
        question=QUESTION,
        claim=Claim(
            claim_id="c1",
            property_asked="doubling time",
            property_in_paper="generation time",
            value="39",
            unit="min",
            kind=ClaimKind.SINGLE,
            candidate_kind=CandidateKind.MEASURED,
            quote=Quote(text=SUPPORTING, location=Location(passage_id="p1")),
            conditions=(
                ConditionField(
                    name="medium", provenance=Provenance.BESIDE_VALUE, quote="rich medium (LB)"
                ),
            ),
            fingerprint=FP,
        ),
        paper=PAPER,
        supporting=Quote(text=SUPPORTING, location=Location(passage_id="p1")),
        second=Quote(text=SECOND, location=Location(passage_id="p2")),
        second_kind=second_kind,
        distractor_type=distractor_type,
        tables=tables,
    )


def label_of(item: ReviewItem, *, supporting: bool) -> str:
    """The label the page puts on the supporting text, or on the other one."""
    return next(t.label for t in review.texts_in_order(item) if t.is_supporting == supporting)


class Scripted:
    """Answers from a queue, an exception in the queue being raised instead, and every call
    kept, so a case can say what a model was shown and that a call never happened."""

    def __init__(self, *answers, answered_by: str | list[str] = "") -> None:
        self.answers = list(answers)
        self.answered_by = answered_by
        self.calls: list[dict] = []

    def count_tokens(self, *, system, messages, output_format=None):
        return SimpleNamespace(input_tokens=1000)

    def parse(self, *, system, messages, output_format, max_tokens):
        self.calls.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        by = self.answered_by
        if isinstance(by, list):
            # A router answers each call with a model of its choosing.
            by = by[len(self.calls) - 1]
        return SimpleNamespace(parsed_output=answer, usage=USAGE, raw={"model": by} if by else {})


def choosing(item: ReviewItem, *, supporting: bool = True, value_read: str = "39 min") -> Chosen:
    return Chosen(choice=label_of(item, supporting=supporting), value_read=value_read, comment="")


APPROVING = Judged(verdict="APPROVE", comment="")
DISAPPROVING = Judged(verdict="DISAPPROVE", comment="wrong medium")


def approving(item: ReviewItem) -> list:
    """Both steps of a clean approval, in the order the runner asks them."""
    return [choosing(item), APPROVING]


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    store.create_all(engine)
    yield engine
    engine.dispose()


def load(engine, *items: ReviewItem) -> None:
    result = PaperResult(paper=PAPER, state=PaperState.CLAIMS_FOUND, fingerprint=FP)
    store.load_run(engine, [result], items, question=QUESTION, run_id=RUN)


def decisions(engine):
    with engine.begin() as conn:
        return conn.execute(select(store.review_decision)).all()


# --- the two screens -------------------------------------------------------------------------


def test_the_first_screen_shows_the_quantity_the_paper_and_the_texts_and_withholds_the_rest():
    item = an_item()
    shown = screen(item)

    assert f"Quantity: {QUESTION}" in shown
    assert review.citation_line(PAPER) in shown
    first, second = review.texts_in_order(item)
    assert shown.index(f"Text {first.label}\n") < shown.index(f"Text {second.label}\n")
    assert shown.index(first.text) < shown.index(second.text)
    # The value, the paper's own name for the quantity and the conditions are the reveal's.
    assert "Value:" not in shown
    assert "generation time" not in shown
    assert "rich medium (LB)" not in shown
    assert "Organism" not in shown


def test_the_first_screen_is_the_same_whatever_kind_the_second_text_is():
    """The kind is what the reviewer is being measured against. An item whose second text is a
    distractor and one whose second text is a second occurrence must read alike."""
    distractor = an_item()
    occurrence = an_item(second_kind=SecondTextKind.SECOND_OCCURRENCE, distractor_type=None)
    parameter = an_item(distractor_type=DistractorType.PARAMETER)

    assert screen(distractor) == screen(occurrence) == screen(parameter)


def test_the_reveal_repeats_the_choice_and_adds_the_stored_entry():
    item = an_item()
    shown = reveal(item, store.Choice(True, "39 min", "SAME_NUMBER_DIFFERENT_UNIT"))
    assert "Your reading has the stored number but a different unit." in shown

    assert shown.startswith(screen(item))
    assert (
        f"You chose Text {label_of(item, supporting=True)} and read the value as: 39 min" in shown
    )
    assert "Value: 39 min" in shown
    assert "The paper calls it: generation time" in shown
    assert "Medium | beside the value | rich medium (LB)" in shown
    assert "Organism | not stated | —" in shown


def test_the_reveal_names_the_other_text_when_that_is_the_one_chosen():
    item = an_item()
    shown = reveal(item, store.Choice(chosen_supporting=False, value_read=""))

    assert (
        f"You chose Text {label_of(item, supporting=False)} and read the value as: (nothing)"
        in shown
    )


def test_a_table_is_drawn_whole_with_both_texts_cells_marked_alike():
    table = TableView(
        label="Table 3",
        caption="Doubling times",
        foot="Mean of three cultures.",
        rows=(
            (TableCell(text="Medium", header=True), TableCell(text="Time", header=True)),
            (TableCell(text="rich"), TableCell(text="39", passage_id="p1")),
            (TableCell(text="minimal"), TableCell(text="21", passage_id="p2")),
        ),
    )
    item = an_item(tables=(table,))
    shown = screen(item)

    assert "Table 3 Doubling times" in shown
    assert "Medium | Time" in shown
    assert f"rich | 39 [{label_of(item, supporting=True)}]" in shown
    assert f"minimal | 21 [{label_of(item, supporting=False)}]" in shown
    assert "Mean of three cultures." in shown


# --- which items a role reviews ------------------------------------------------------------


def test_a_share_of_none_reviews_nothing_and_a_share_of_all_reviews_everything():
    ids = [f"i{n}" for n in range(200)]
    nobody = Reviewer(ReviewerRole.STUDENT, MODEL, share=0.0)
    everybody = Reviewer(ReviewerRole.STUDENT, MODEL, share=1.0)

    assert not any(assigned(item_id, nobody) for item_id in ids)
    assert all(assigned(item_id, everybody) for item_id in ids)


def test_a_share_is_roughly_that_fraction_of_the_items_and_the_same_on_every_run():
    ids = [f"i{n}" for n in range(1000)]
    third = Reviewer(ReviewerRole.SCIENTIST, MODEL, share=0.3)

    chosen = [item_id for item_id in ids if assigned(item_id, third)]

    assert 250 <= len(chosen) <= 350
    assert chosen == [item_id for item_id in ids if assigned(item_id, third)]


def test_two_roles_draw_different_subsets_that_overlap():
    ids = [f"i{n}" for n in range(1000)]
    student = {i for i in ids if assigned(i, Reviewer(ReviewerRole.STUDENT, MODEL, share=0.5))}
    scientist = {i for i in ids if assigned(i, Reviewer(ReviewerRole.SCIENTIST, MODEL, share=0.5))}

    assert student != scientist
    # Independent draws at one half each overlap on about a quarter.
    assert 180 <= len(student & scientist) <= 320


def test_a_role_keeps_its_subset_when_another_model_plays_it():
    ids = [f"i{n}" for n in range(200)]
    one = Reviewer(ReviewerRole.STUDENT, MODEL, share=0.5)
    other = Reviewer(ReviewerRole.STUDENT, "openai/gpt-6.1-sol", share=0.5)

    assert [assigned(i, one) for i in ids] == [assigned(i, other) for i in ids]


@pytest.mark.parametrize("share", [-0.1, 1.5])
def test_a_share_outside_zero_to_one_is_refused(share):
    with pytest.raises(ValueError, match="between 0 and 1"):
        Reviewer(ReviewerRole.STUDENT, MODEL, share=share)


def test_a_simulated_reviewer_s_name_says_so_and_a_model_reviewing_as_itself_does_not():
    assert STUDENT.name == f"simulated-student:{MODEL}"
    assert Reviewer(ReviewerRole.AI, MODEL).name == f"ai:{MODEL}"


# --- a run ---------------------------------------------------------------------------------


@pytest.mark.parametrize("picks_supporting", [True, False])
def test_the_two_steps_make_one_row_with_the_choice_the_value_read_and_the_verdict(
    engine, picks_supporting
):
    item = an_item()
    load(engine, item)
    model = Scripted(
        choosing(item, supporting=picks_supporting, value_read="21 min"),
        DISAPPROVING,
        answered_by="some/routed-model",
    )

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: model)

    (row,) = decisions(engine)
    assert row.item_id == "i1"
    assert row.reviewer == STUDENT.name
    assert (row.reviewer_role, row.reviewer_model) == ("STUDENT", MODEL)
    assert row.answered_by == "some/routed-model"
    assert row.chosen_supporting is picks_supporting
    assert row.value_read == "21 min"
    assert (row.approved, row.comment, row.issue) == (False, "wrong medium", "")
    assert row.time_to_decide_s is not None
    (tally,) = summary.tallies
    assert (tally.approved, tally.disapproved, tally.issues) == (0, 1, 0)
    assert (tally.distractors, tally.distractors_caught) == (1, int(picks_supporting))
    assert tally.values_agreed == 0
    assert len(model.calls) == 2


def test_a_router_that_answers_the_two_steps_with_two_models_is_recorded_with_both(engine):
    item = an_item()
    load(engine, item)
    router = Reviewer(ReviewerRole.STUDENT, "typesafe/jev-router")
    model = Scripted(
        *approving(item), answered_by=["openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash"]
    )

    simulated_review.run(engine, [router], lambda model_id: model)

    (row,) = decisions(engine)
    assert row.reviewer_model == "typesafe/jev-router"
    assert row.answered_by == "openai/gpt-6-luna, deepseek/deepseek-v4.1-flash"


def test_the_second_step_is_asked_only_after_the_first_is_written_and_sees_the_reveal(engine):
    item = an_item()
    load(engine, item)
    model = Scripted(*approving(item))

    simulated_review.run(engine, [STUDENT], lambda model_id: model)

    first, second = model.calls
    assert first["system"] == simulated_review.CHOICE_INSTRUCTION
    assert first["messages"] == [{"role": "user", "content": screen(item)}]
    assert second["system"] == simulated_review.VERDICT_INSTRUCTION
    assert second["messages"] == [
        {"role": "user", "content": reveal(item, store.Choice(True, "39 min", "MATCHES"))}
    ]
    assert "Your reading matches the stored value." in second["messages"][0]["content"]
    assert "Value: 39 min" not in first["messages"][0]["content"]


def test_a_value_read_that_agrees_with_the_stored_one_is_counted(engine):
    one, two = an_item("i1"), an_item("i2")
    load(engine, one, two)
    model = Scripted(
        choosing(one, value_read="39 ± 1 min"),
        APPROVING,
        choosing(two, value_read="40 min"),
        APPROVING,
    )

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: model)

    assert summary.tallies[0].values_agreed == 1
    assert summary.tallies[0].approved == 2


def test_a_second_occurrence_has_no_right_answer_and_is_not_counted_as_one(engine):
    item = an_item(second_kind=SecondTextKind.SECOND_OCCURRENCE, distractor_type=None)
    load(engine, item)

    summary = simulated_review.run(engine, [STUDENT], lambda m: Scripted(*approving(item)))

    (tally,) = summary.tallies
    assert tally.approved == 1
    assert (tally.distractors, tally.distractors_caught) == (0, 0)


def test_an_issue_at_the_first_step_is_recorded_with_no_choice_and_no_second_call(engine):
    load(engine, an_item())
    model = Scripted(Chosen(choice="ISSUE", value_read="", comment="neither text states a time"))

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: model)

    (row,) = decisions(engine)
    assert row.issue == "neither text states a time"
    assert (row.chosen_supporting, row.approved, row.value_read) == (None, None, "")
    assert (row.reviewer_role, row.reviewer_model) == ("STUDENT", MODEL)
    assert summary.tallies[0].issues == 1
    assert len(model.calls) == 1


def test_an_issue_at_the_second_step_keeps_the_choice_and_the_value_read(engine):
    item = an_item()
    load(engine, item)
    model = Scripted(
        choosing(item, value_read="39 min"),
        Judged(verdict="ISSUE", comment="the stored unit is hours, the text says minutes"),
    )

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: model)

    (row,) = decisions(engine)
    assert (row.chosen_supporting, row.value_read) == (True, "39 min")
    assert row.approved is None
    assert row.issue == "the stored unit is hours, the text says minutes"
    assert (summary.tallies[0].issues, summary.tallies[0].approved) == (1, 0)


@pytest.mark.parametrize(
    "answers",
    [
        [Chosen(choice="ISSUE", value_read="", comment="  ")],
        [Chosen(choice="A", value_read="39", comment=""), Judged(verdict="ISSUE", comment="")],
    ],
)
def test_an_issue_with_no_text_writes_no_issue_and_is_reported(engine, answers):
    item = an_item()
    load(engine, item)
    if answers[0].choice == "A":
        answers[0] = choosing(item)

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: Scripted(*answers))

    assert all(row.issue == "" for row in decisions(engine))
    assert summary.tallies[0].failures == [("i1", "an issue with no text")]
    assert summary.tallies[0].issues == 0


def test_a_choice_with_no_value_read_is_refused_as_a_person_s_is(engine):
    """The page refuses the first step without a value (ADR-0970); the runner goes through the
    same rule, so no row opens with nothing read and a UNREADABLE agreement beside it."""
    item = an_item()
    load(engine, item)
    label = next(t.label for t in review.texts_in_order(item) if t.is_supporting)
    model = Scripted(Chosen(choice=label, value_read="  ", comment=""))

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: model)

    assert decisions(engine) == []
    assert summary.tallies[0].failures == [("i1", review.VALUE_REQUIRED)]
    assert len(model.calls) == 1, "the second step is never asked"


def test_the_model_is_shown_no_one_s_decision_and_no_role(engine):
    item = an_item()
    load(engine, item)
    store.record_decision(
        engine,
        "i1",
        reviewer="alice@example.org",
        chosen_supporting=True,
        approved=False,
        comment="alice thought the strain was wrong",
    )
    model = Scripted(*approving(item))

    simulated_review.run(engine, [STUDENT], lambda model_id: model)

    for call in model.calls:
        assert "alice" not in json.dumps(call)
        assert "student" not in call["system"].lower()


def test_only_the_items_assigned_to_a_role_are_reviewed(engine):
    items = [an_item(f"i{n:02d}") for n in range(40)]
    load(engine, *items)
    half = Reviewer(ReviewerRole.SCIENTIST, MODEL, share=0.5)
    expected = [item.item_id for item in items if assigned(item.item_id, half)]
    assert 0 < len(expected) < len(items)
    answers = [a for item in items if item.item_id in expected for a in approving(item)]
    model = Scripted(*answers)

    simulated_review.run(engine, [half], lambda model_id: model)

    assert [row.item_id for row in decisions(engine)] == expected
    assert len(model.calls) == 2 * len(expected)


def test_a_second_run_asks_about_nothing_already_decided(engine):
    one, two = an_item("i1"), an_item("i2")
    load(engine, one, two)
    simulated_review.run(engine, [STUDENT], lambda m: Scripted(*approving(one), *approving(two)))
    again = Scripted()

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: again)

    assert again.calls == []
    assert len(decisions(engine)) == 2
    assert summary.spend_usd == 0


def test_an_item_left_after_its_first_step_gets_only_its_second_on_the_next_run(engine):
    item = an_item()
    load(engine, item)
    cut_off = RuntimeError("timed out")
    simulated_review.run(engine, [STUDENT], lambda m: Scripted(choosing(item), cut_off))
    (row,) = decisions(engine)
    assert row.approved is None
    resumed = Scripted(APPROVING)

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: resumed)

    assert len(resumed.calls) == 1
    assert resumed.calls[0]["system"] == simulated_review.VERDICT_INSTRUCTION
    (row,) = decisions(engine)
    assert (row.chosen_supporting, row.value_read, row.approved) == (True, "39 min", True)
    assert summary.tallies[0].approved == 1
    # The choice was counted on the run that made it, not again.
    assert summary.tallies[0].distractors == 0


def test_each_reviewer_decides_for_itself_so_an_item_can_carry_two_ratings(engine):
    item = an_item()
    load(engine, item)
    senior = Reviewer(ReviewerRole.SENIOR_SCIENTIST, "anthropic/claude-opus-5.5")
    models = {
        MODEL: Scripted(*approving(item)),
        senior.model: Scripted(choosing(item), DISAPPROVING),
    }

    simulated_review.run(engine, [STUDENT, senior], models.__getitem__)

    by_role = {row.reviewer_role: row.approved for row in decisions(engine)}
    assert by_role == {"STUDENT": True, "SENIOR_SCIENTIST": False}


def test_a_failed_first_call_writes_nothing_is_charged_and_does_not_stop_the_next_item(engine):
    one, two = an_item("i1"), an_item("i2")
    load(engine, one, two)
    unreadable = RuntimeError("output does not match Chosen")
    unreadable.usage = USAGE
    model = Scripted(unreadable, *approving(two))

    summary = simulated_review.run(engine, [STUDENT], lambda model_id: model)

    assert [row.item_id for row in decisions(engine)] == ["i2"]
    (tally,) = summary.tallies
    assert tally.failures == [("i1", "RuntimeError: output does not match Chosen")]
    assert summary.spend_usd == pytest.approx(3 * ONE_CALL_USD)
    assert tally.spend_usd == pytest.approx(3 * ONE_CALL_USD)
    assert summary.stopped == ""


def test_a_refusal_of_the_account_stops_the_run_and_every_later_reviewer(engine):
    load(engine, an_item("i1"), an_item("i2"))
    senior = Reviewer(ReviewerRole.SENIOR_SCIENTIST, "anthropic/claude-opus-5.5")
    asked: list[str] = []

    def model_for(model_id: str) -> Scripted:
        asked.append(model_id)
        return Scripted(ProviderRefused("HTTP 402 from OpenRouter: no credit"))

    summary = simulated_review.run(engine, [STUDENT, senior], model_for)

    assert decisions(engine) == []
    assert "402" in summary.stopped
    assert asked == [MODEL]
    assert len(summary.tallies) == 1


def test_the_run_budget_stops_the_run_before_the_call_that_would_cross_it(engine):
    one, two = an_item("i1"), an_item("i2")
    load(engine, one, two)
    model = Scripted(*approving(one), *approving(two))
    # Room for the first item's two calls, not for the second item's first projection.
    budget = 2 * ONE_CALL_USD + ONE_PROJECTION_USD - ONE_CALL_USD / 2

    summary = simulated_review.run(
        engine, [STUDENT], lambda model_id: model, ceiling=Ceiling(per_paper=1.0, per_run=budget)
    )

    assert [(row.item_id, row.approved) for row in decisions(engine)] == [("i1", True)]
    assert len(model.calls) == 2
    assert "run ceiling" in summary.stopped
    assert summary.spend_usd == pytest.approx(2 * ONE_CALL_USD)


def test_a_decision_over_its_own_ceiling_is_skipped_and_the_run_goes_on(engine):
    load(engine, an_item("i1"), an_item("i2"))
    model = Scripted()

    summary = simulated_review.run(
        engine,
        [STUDENT],
        lambda model_id: model,
        ceiling=Ceiling(per_paper=ONE_PROJECTION_USD / 2, per_run=1.0),
    )

    assert model.calls == []
    assert decisions(engine) == []
    assert summary.stopped == ""
    assert [item_id for item_id, _ in summary.tallies[0].failures] == ["i1", "i2"]


def test_a_model_with_no_price_is_refused_before_any_model_is_built(engine):
    load(engine, an_item())
    built: list[str] = []

    with pytest.raises(Unpriceable, match="nobody/unpriced"):
        simulated_review.run(
            engine,
            [STUDENT, Reviewer(ReviewerRole.SCIENTIST, "nobody/unpriced")],
            lambda model_id: built.append(model_id),
        )

    assert built == []
    assert decisions(engine) == []


def test_a_row_the_store_cannot_write_stops_the_run(engine, monkeypatch):
    one, two = an_item("i1"), an_item("i2")
    load(engine, one, two)
    model = Scripted(*approving(one), *approving(two))

    def refuse(*args, **kwargs):
        raise store.DecisionNotSaved("OperationalError: connection refused")

    monkeypatch.setattr(store, "record_choice", refuse)

    with pytest.raises(store.DecisionNotSaved):
        simulated_review.run(engine, [STUDENT], lambda model_id: model)

    assert len(model.calls) == 1


# --- the command ---------------------------------------------------------------------------


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path}/review.sqlite"
    engine = store.engine_from_url(url)
    store.create_all(engine)
    yield SimpleNamespace(url=url, engine=engine)
    engine.dispose()


def test_the_command_runs_each_reviewer_and_prints_a_summary_marked_simulated(
    database, monkeypatch, capsys
):
    item = an_item()
    load(database.engine, item)
    monkeypatch.setattr(cli, "_model", lambda model_id: Scripted(*approving(item)))

    code = cli.main(["simulate-review", "--reviewer", f"student={MODEL}", "--db-url", database.url])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["simulated"] is True
    assert printed["reviewers"][0]["approved"] == 1
    assert printed["reviewers"][0]["values_agreed"] == 1
    assert printed["reviewers"][0]["reviewer"] == STUDENT.name
    assert [row.reviewer_role for row in decisions(database.engine)] == ["STUDENT"]


def test_a_reviewer_is_a_role_a_model_and_an_optional_share():
    reviewer = cli._reviewer_from("senior_scientist=some/model:free@0.25")
    assert reviewer == Reviewer(ReviewerRole.SENIOR_SCIENTIST, "some/model:free", share=0.25)
    assert cli._reviewer_from(f"AI={MODEL}").share == 1.0


@pytest.mark.parametrize("spec", ["professor=some/model", "student", "student=", "=some/model"])
def test_the_command_refuses_a_reviewer_it_cannot_read(database, monkeypatch, capsys, spec):
    monkeypatch.setattr(cli, "_model", lambda model_id: pytest.fail("no model should be built"))

    code = cli.main(["simulate-review", "--reviewer", spec, "--db-url", database.url])

    assert code == 2
    assert "ROLE=MODEL" in capsys.readouterr().err


def test_the_command_refuses_a_model_with_no_price(database, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_model", lambda model_id: pytest.fail("no model should be built"))

    code = cli.main(
        ["simulate-review", "--reviewer", "student=nobody/unpriced", "--db-url", database.url]
    )

    assert code == 2
    assert "nobody/unpriced" in capsys.readouterr().err


def test_the_command_without_a_database_says_which_variable(monkeypatch, capsys):
    monkeypatch.delenv(cli.DB_URL_ENV, raising=False)

    code = cli.main(["simulate-review", "--reviewer", f"student={MODEL}"])

    assert code == 2
    assert cli.DB_URL_ENV in capsys.readouterr().err


def test_the_command_reports_a_stop_and_says_how_to_continue(database, monkeypatch, capsys):
    load(database.engine, an_item())
    refused = Scripted(ProviderRefused("HTTP 402 from OpenRouter: no credit"))
    monkeypatch.setattr(cli, "_model", lambda model_id: refused)

    code = cli.main(["simulate-review", "--reviewer", f"student={MODEL}", "--db-url", database.url])

    assert code == 3
    assert "Run it again" in capsys.readouterr().err
