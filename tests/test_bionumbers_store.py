"""The review store against SQLite, and its DDL against a real Postgres.

Everything the store decides -- who is offered what, what is refused, what a failed write does --
is asserted offline against an in-memory SQLite database. Two things SQLite cannot answer are left
to the one `network`-marked case at the bottom: whether `sql/review.sql` is valid Postgres, and
whether a Core insert's parameters fit the column types that file declares.
"""

from __future__ import annotations

import re
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, insert, select, text
from sqlalchemy.exc import OperationalError

from bionumbers import store
from bionumbers.records import (
    UNLICENSED,
    CandidateKind,
    Claim,
    ClaimKind,
    DistractorType,
    Fingerprint,
    Location,
    Paper,
    PaperResult,
    PaperState,
    Quote,
    ReviewerRole,
    ReviewItem,
    SecondTextKind,
    Spend,
)

QUESTION = "doubling time of Escherichia coli"
RUN = "run-1"
FP = Fingerprint(model="opus", instruction_sha256="abc123", article_id="PMC1", run_id=RUN)
SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "review.sql"
SECRETS = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"


def a_paper(pmcid: str = "PMC1", *, licence: str = "CC BY 4.0") -> Paper:
    """`licence` is a parameter and never a fixture constant: it is the field `load_run`'s refusal
    reads, so the case that tests the refusal must be free to vary it and nothing else."""
    return Paper(
        pmcid=pmcid, pmid="39123456", doi="10.1/abc", title="A paper", year=2026, licence=licence
    )


def a_claim(claim_id: str = "c1") -> Claim:
    return Claim(
        claim_id=claim_id,
        property_asked="doubling time",
        property_in_paper="generation time",
        value="39",
        unit="min",
        kind=ClaimKind.SINGLE,
        candidate_kind=CandidateKind.MEASURED,
        quote=Quote(text="a doubling time of 39 min", location=Location(passage_id="p1")),
        fingerprint=FP,
    )


def an_item(item_id: str = "i1", paper: Paper | None = None, claim_id: str = "c1") -> ReviewItem:
    return ReviewItem(
        item_id=item_id,
        question=QUESTION,
        claim=a_claim(claim_id),
        paper=paper or a_paper(),
        supporting=Quote(text="a doubling time of 39 min", location=Location(passage_id="p1")),
        second=Quote(text="21 min in minimal medium", location=Location(passage_id="p2")),
        second_kind=SecondTextKind.DISTRACTOR,
        distractor_type=DistractorType.ADJACENT_CONDITION,
    )


def a_result(
    paper: Paper | None = None, state: PaperState = PaperState.CLAIMS_FOUND
) -> PaperResult:
    return PaperResult(
        paper=paper or a_paper(),
        state=state,
        spend=Spend(input_tokens=50_000, usd=0.42, calls=2),
        fingerprint=FP,
    )


@pytest.fixture
def engine():
    """In-memory SQLite, one database per test, created through the store's own `create_all` --
    so a column the module forgot fails here rather than passing against a hand-written schema."""
    engine = create_engine("sqlite://")
    store.create_all(engine)
    yield engine
    engine.dispose()


def rows(engine, table):
    with engine.begin() as conn:
        return conn.execute(select(table)).all()


# --- loading -------------------------------------------------------------------------------


def test_a_run_loads_its_papers_and_items(engine):
    inserted = store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    assert inserted == 1
    (paper,) = rows(engine, store.review_paper)
    assert (paper.pmcid, paper.state, paper.licence) == ("PMC1", "CLAIMS_FOUND", "CC BY 4.0")
    assert paper.spend_usd == pytest.approx(0.42)
    (item,) = rows(engine, store.review_item)
    assert (item.item_id, item.pmcid, item.claim_id) == ("i1", "PMC1", "c1")
    assert (item.value, item.unit, item.second_kind) == ("39", "min", "DISTRACTOR")
    assert item.distractor_type == "ADJACENT_CONDITION"
    assert ReviewItem.model_validate_json(item.item_json) == an_item("i1")


def test_loading_the_same_run_twice_inserts_nothing_the_second_time(engine):
    """Re-running a load is how a partial run is finished; it must neither duplicate nor rewrite."""
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    again = store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    assert again == 0
    assert len(rows(engine, store.review_paper)) == 1
    assert len(rows(engine, store.review_item)) == 1


def test_a_second_load_still_inserts_an_item_that_is_new(engine):
    """The negative of idempotence: what is skipped is a known item id, not "the second call"."""
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    inserted = store.load_run(
        engine,
        [a_result()],
        [an_item("i1"), an_item("i2", claim_id="c2")],
        question=QUESTION,
        run_id=RUN,
    )

    assert inserted == 1
    assert {row.item_id for row in rows(engine, store.review_item)} == {"i1", "i2"}


def test_a_second_run_on_the_same_paper_loads_its_own_row_and_items(engine):
    """A second question asked of a paper already loaded (the 2026-09-21 review's finding 4).
    Keyed by article alone, its paper row was skipped as "already present" and its items were
    refused for naming a paper with no row -- silently, in a run that looked loaded."""
    store.load_run(
        engine, [a_result()], [an_item("run-1-PMC1-1-item")], question=QUESTION, run_id="run-1"
    )

    inserted = store.load_run(
        engine,
        [a_result(state=PaperState.NOTHING_TO_EXTRACT)],
        [an_item("run-2-PMC1-1-item", claim_id="run-2-PMC1-1")],
        question="lag time of Escherichia coli",
        run_id="run-2",
    )

    assert inserted == 1
    papers = rows(engine, store.review_paper)
    assert {(row.run_id, row.pmcid, row.state) for row in papers} == {
        ("run-1", "PMC1", "CLAIMS_FOUND"),
        ("run-2", "PMC1", "NOTHING_TO_EXTRACT"),
    }
    assert {row.run_id for row in rows(engine, store.review_item)} == {"run-1", "run-2"}


def test_an_item_of_one_run_cannot_lean_on_another_run_s_paper_row(engine):
    """The negative of the case above, varying the run: the paper row an item needs is its own
    run's, so a run that loaded no papers is refused even where another run loaded that paper."""
    store.load_run(engine, [a_result()], [], question=QUESTION, run_id="run-1")

    with pytest.raises(ValueError, match="run-2"):
        store.load_run(engine, [], [an_item("i1")], question=QUESTION, run_id="run-2")

    assert rows(engine, store.review_item) == []


def test_no_item_is_loaded_for_an_unlicensed_paper(engine):
    """Its text is never written past the disk cache, and an item carries the paper's own
    sentences. The refusal names the paper, because an operator has to find it."""
    paper = a_paper(licence=UNLICENSED)
    items = [an_item("i1", paper)]

    with pytest.raises(ValueError, match="PMC1"):
        store.load_run(engine, [a_result(paper)], items, question=QUESTION, run_id=RUN)

    assert rows(engine, store.review_item) == []


def test_an_unlicensed_paper_still_gets_its_own_row(engine):
    """The bibliography and the state are a finding about the literature, not the paper's text."""
    paper = a_paper(licence=UNLICENSED)
    result = a_result(paper, PaperState.NOTHING_TO_EXTRACT)

    store.load_run(engine, [result], [], question=QUESTION, run_id=RUN)

    (row,) = rows(engine, store.review_paper)
    assert (row.pmcid, row.licence, row.state) == ("PMC1", UNLICENSED, "NOTHING_TO_EXTRACT")


def test_an_item_whose_paper_has_no_row_is_refused(engine):
    """SQLite does not enforce the foreign key, so the operation enforces it and both backends
    answer the same way."""
    store.load_run(engine, [a_result()], [], question=QUESTION, run_id=RUN)

    with pytest.raises(ValueError, match="PMC9"):
        store.load_run(engine, [], [an_item("i1", a_paper("PMC9"))], question=QUESTION, run_id=RUN)

    assert rows(engine, store.review_item) == []


# --- serving -------------------------------------------------------------------------------


def test_an_item_a_reviewer_has_decided_is_not_offered_to_them_again(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    assert store.next_item(engine, "alice@example.org").item_id == "i1"
    store.record_decision(
        engine, "i1", reviewer="alice@example.org", chosen_supporting=True, approved=True
    )

    assert store.next_item(engine, "alice@example.org") is None


def test_an_item_one_reviewer_has_decided_is_still_offered_to_another(engine):
    """Every item is reviewed; "none twice" is per reviewer. This differs from the case above in
    the reviewer alone, which is the field the rule reads."""
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)
    store.record_decision(
        engine, "i1", reviewer="alice@example.org", chosen_supporting=True, approved=True
    )

    assert store.next_item(engine, "bob@example.org").item_id == "i1"


def test_no_sign_in_is_its_own_reviewer(engine):
    """A deployment with no identity records no account, and that absence has to behave as one
    reviewer -- not as everyone, and not as nobody."""
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    assert store.next_item(engine, None).item_id == "i1"
    store.record_decision(engine, "i1", reviewer=None, chosen_supporting=True, approved=True)

    assert store.next_item(engine, None) is None
    assert store.next_item(engine, "alice@example.org").item_id == "i1"


def test_items_are_served_interleaved_across_papers(engine):
    """Three items from one paper and one from another are served A, B, A, A.

    Grouped by paper -- A, A, A, B -- the second screen's conditions are remembered from the
    first, and the reviewer judges from memory rather than from the text in front of them.
    """
    a, b = a_paper("PMCA"), a_paper("PMCB")
    items = [an_item("A-1", a), an_item("A-2", a, "c2"), an_item("A-3", a, "c3"), an_item("B-1", b)]
    store.load_run(engine, [a_result(a), a_result(b)], items, question=QUESTION, run_id=RUN)

    served = []
    while (item := store.next_item(engine, "alice@example.org")) is not None:
        served.append(item.item_id)
        store.record_decision(
            engine,
            item.item_id,
            reviewer="alice@example.org",
            chosen_supporting=True,
            approved=True,
        )

    assert served == ["A-1", "B-1", "A-2", "A-3"]


def test_remaining_counts_down_for_the_reviewer_who_decided(engine):
    a = a_paper("PMCA")
    store.load_run(
        engine,
        [a_result(a)],
        [an_item("A-1", a), an_item("A-2", a, "c2")],
        question=QUESTION,
        run_id=RUN,
    )

    assert store.remaining(engine, "alice@example.org") == 2
    store.record_decision(
        engine, "A-1", reviewer="alice@example.org", chosen_supporting=False, approved=False
    )

    assert store.remaining(engine, "alice@example.org") == 1
    assert store.remaining(engine, "bob@example.org") == 2


def test_nothing_is_offered_when_nothing_is_loaded(engine):
    assert store.next_item(engine, "alice@example.org") is None
    assert store.remaining(engine, "alice@example.org") == 0


# --- deciding ------------------------------------------------------------------------------


def test_a_decision_holds_the_choice_the_verdict_the_comment_the_reviewer_and_a_time(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_decision(
        engine,
        "i1",
        reviewer="alice@example.org",
        chosen_supporting=False,
        approved=False,
        comment="the second text is about a different strain",
        time_to_decide_s=31.5,
    )

    (row,) = rows(engine, store.review_decision)
    assert row.item_id == "i1"
    assert row.reviewer == "alice@example.org"
    assert row.chosen_supporting is False
    assert row.approved is False
    assert row.comment == "the second text is about a different strain"
    assert row.time_to_decide_s == pytest.approx(31.5)
    assert row.decided_at is not None


def test_a_decision_without_sign_in_records_no_account_and_nothing_else_differs(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_decision(
        engine, "i1", reviewer=None, chosen_supporting=True, approved=True, comment="clear"
    )

    (row,) = rows(engine, store.review_decision)
    assert row.reviewer is None
    assert (row.chosen_supporting, row.approved, row.comment) == (True, True, "clear")


def test_a_decision_made_by_a_person_records_no_role_no_model_and_no_issue(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_decision(
        engine, "i1", reviewer="alice@example.org", chosen_supporting=True, approved=True
    )

    (row,) = rows(engine, store.review_decision)
    assert (row.reviewer_role, row.reviewer_model, row.issue) == (None, None, "")


def test_a_decision_holds_the_role_and_the_model_that_made_it(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_decision(
        engine,
        "i1",
        reviewer="simulated-student:some/model",
        chosen_supporting=True,
        approved=False,
        reviewer_role=ReviewerRole.STUDENT,
        reviewer_model="some/model",
    )

    (row,) = rows(engine, store.review_decision)
    assert (row.reviewer_role, row.reviewer_model) == ("STUDENT", "some/model")
    assert (row.chosen_supporting, row.approved) == (True, False)


def test_an_issue_holds_its_text_and_neither_a_choice_nor_a_verdict(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_issue(
        engine,
        "i1",
        reviewer="alice@example.org",
        issue="neither text states 39 min",
        time_to_decide_s=12.0,
        reviewer_role=ReviewerRole.SCIENTIST,
    )

    (row,) = rows(engine, store.review_decision)
    assert row.issue == "neither text states 39 min"
    assert row.chosen_supporting is None
    assert row.approved is None
    assert row.comment == ""
    assert (row.reviewer, row.reviewer_role, row.reviewer_model) == (
        "alice@example.org",
        "SCIENTIST",
        None,
    )
    assert row.time_to_decide_s == pytest.approx(12.0)


@pytest.mark.parametrize("empty", ["", "   ", "\n"])
def test_an_issue_with_no_text_is_refused_and_writes_nothing(engine, empty):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    with pytest.raises(ValueError, match="needs its text"):
        store.record_issue(engine, "i1", reviewer="alice@example.org", issue=empty)

    assert rows(engine, store.review_decision) == []


def test_an_issue_on_an_unknown_item_is_not_saved_and_says_so(engine):
    with pytest.raises(store.DecisionNotSaved, match="i-nope"):
        store.record_issue(engine, "i-nope", reviewer="alice@example.org", issue="garbled unit")

    assert rows(engine, store.review_decision) == []


def test_an_issue_after_a_verdict_is_refused_and_the_row_stands(engine):
    """Once per item per reviewer holds for an issue too: a second row would make one reviewer
    both approve and dispute the entry, which no tier rule can read."""
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)
    store.record_choice(engine, "i1", reviewer="a", chosen_supporting=True, value_read="39")
    store.record_verdict(engine, "i1", reviewer="a", approved=True)

    with pytest.raises(store.DecisionNotSaved, match="already decided"):
        store.record_issue(engine, "i1", reviewer="a", issue="garbled after all")

    (row,) = rows(engine, store.review_decision)
    assert (row.approved, row.issue) == (True, "")


def test_an_interrupted_rebuild_is_refused_rather_than_read_as_empty():
    """A file left mid-rebuild holds every decision in the side table and none in the real one;
    an upgrade that created an empty table and reported success would be the silent loss."""
    engine, old = an_old_database()
    with engine.begin() as conn:
        conn.execute(text("alter table review_decision rename to review_decision__old"))

    with pytest.raises(RuntimeError, match="review_decision__old"):
        store.upgrade(engine)


def test_an_item_a_reviewer_raised_an_issue_on_is_not_offered_to_them_again(engine):
    store.load_run(
        engine, [a_result()], [an_item("i1"), an_item("i2")], question=QUESTION, run_id=RUN
    )

    store.record_issue(engine, "i1", reviewer="alice@example.org", issue="garbled unit")

    assert store.next_item(engine, "alice@example.org").item_id == "i2"
    assert store.next_item(engine, "bob@example.org").item_id == "i1"


def test_undecided_items_are_all_of_a_reviewer_s_open_items_and_no_one_else_s(engine):
    store.load_run(
        engine,
        [a_result()],
        [an_item("i3"), an_item("i1"), an_item("i2")],
        question=QUESTION,
        run_id=RUN,
    )
    store.record_decision(engine, "i2", reviewer="alice", chosen_supporting=True, approved=True)
    store.record_issue(engine, "i3", reviewer="bob", issue="garbled unit")

    assert [item.item_id for item in store.undecided_items(engine, "alice")] == ["i1", "i3"]
    assert [item.item_id for item in store.undecided_items(engine, "bob")] == ["i1", "i2"]
    assert [item.item_id for item in store.undecided_items(engine, None)] == ["i1", "i2", "i3"]


# --- what a person may choose, and a model may not --------------------------------------------


def a_physics_result(pmcid: str = "PMC2") -> PaperResult:
    return PaperResult(
        paper=a_paper(pmcid),
        state=PaperState.CLAIMS_FOUND,
        fingerprint=Fingerprint(
            model="opus", instruction_sha256="abc", article_id=pmcid, run_id=RUN, scope="physics"
        ),
    )


def two_domains(engine) -> None:
    """PMC1 under the default domain (a fingerprint with no scope), PMC2 under physics."""
    store.load_run(
        engine,
        [a_result(), a_physics_result()],
        [an_item("i1"), an_item("i2", paper=a_paper("PMC2"))],
        question=QUESTION,
        run_id=RUN,
    )


def test_a_paper_s_domain_is_its_harvest_scope_and_biology_where_the_run_predates_scopes(engine):
    two_domains(engine)

    by_pmcid = {row.pmcid: row.domain for row in rows(engine, store.review_paper)}
    assert by_pmcid == {"PMC1": "biology", "PMC2": "physics"}
    assert store.domains(engine) == ["biology", "physics"]
    assert store.topics(engine) == []


def test_a_domain_preference_narrows_what_is_served_and_counted(engine):
    two_domains(engine)
    physics = store.Preference(domain="physics")

    assert store.next_item(engine, "alice", physics).item_id == "i2"
    assert store.remaining(engine, "alice", physics) == 1
    assert store.remaining(engine, "alice", store.Preference()) == 2
    assert store.next_item(engine, "alice", store.Preference(domain="chemistry")) is None


def test_a_topic_preference_reads_the_paper_s_topic(engine):
    two_domains(engine)
    with engine.begin() as conn:
        conn.execute(
            store.review_paper.update()
            .where(store.review_paper.c.pmcid == "PMC2")
            .values(topic="planarians")
        )

    assert store.topics(engine) == ["planarians"]
    assert store.topics(engine, "physics") == ["planarians"]
    assert store.topics(engine, "biology") == []
    assert store.next_item(engine, "alice", store.Preference(topic="planarians")).item_id == "i2"
    assert store.remaining(engine, "alice", store.Preference(topic="yeast")) == 0


def test_a_skipped_paper_is_not_offered_to_that_reviewer_again_and_still_is_to_others(engine):
    two_domains(engine)

    store.skip_paper(engine, "alice", run_id=RUN, pmcid="PMC1")

    assert store.next_item(engine, "alice", store.Preference()).item_id == "i2"
    assert store.remaining(engine, "alice", store.Preference()) == 1
    assert store.next_item(engine, "bob", store.Preference()).item_id == "i1"
    (skip,) = rows(engine, store.review_skip)
    assert (skip.reviewer, skip.run_id, skip.pmcid) == ("alice", RUN, "PMC1")
    assert skip.skipped_at is not None


def test_without_a_preference_a_skip_changes_nothing(engine):
    """The simulated review passes none: a model is never handed a person's choices."""
    two_domains(engine)
    store.skip_paper(engine, "alice", run_id=RUN, pmcid="PMC1")

    assert store.next_item(engine, "alice").item_id == "i1"
    assert store.remaining(engine, "alice") == 2
    assert [i.item_id for i in store.undecided_items(engine, "alice")] == ["i1", "i2"]


def test_the_unsigned_in_reviewer_s_skips_are_their_own(engine):
    two_domains(engine)
    store.skip_paper(engine, None, run_id=RUN, pmcid="PMC1")

    assert store.next_item(engine, None, store.Preference()).item_id == "i2"
    assert store.next_item(engine, "alice", store.Preference()).item_id == "i1"


def test_skipping_a_paper_that_is_not_there_is_refused(engine):
    two_domains(engine)

    with pytest.raises(store.DecisionNotSaved, match="PMC9"):
        store.skip_paper(engine, "alice", run_id=RUN, pmcid="PMC9")

    assert rows(engine, store.review_skip) == []


# --- upgrading an older file -------------------------------------------------------------------


def an_old_database() -> tuple[Any, MetaData]:
    """A SQLite file as `create_all` wrote it before domain, topic, value_read, answered_by and
    review_skip existed: the same tables, those columns and that table left out."""
    engine = create_engine("sqlite://")
    old = MetaData()
    dropped = {"domain", "topic", "value_read", "answered_by", "value_agreement"}
    for table in store.METADATA.sorted_tables:
        if table.name == "review_skip":
            continue
        Table(
            table.name,
            old,
            *[
                Column(
                    column.name,
                    column.type,
                    primary_key=column.primary_key,
                    # The first schema required a verdict and a choice on every row.
                    nullable=column.nullable
                    and column.name not in {"approved", "chosen_supporting"},
                    default=column.default.arg if column.default is not None else None,
                )
                for column in table.columns
                if column.name not in dropped
            ],
        )
    old.create_all(engine)
    return engine, old


def test_upgrade_adds_the_missing_columns_and_table_and_fills_domain_and_topic():
    engine, old = an_old_database()
    item = an_item("i2", paper=a_paper("PMC2").model_copy(update={"topic": "crystals"}))
    with engine.begin() as conn:
        now = datetime.now(UTC)
        conn.execute(
            insert(old.tables["review_paper"]),
            [
                {
                    "run_id": RUN,
                    "pmcid": "PMC2",
                    "question": "q",
                    "state": "CLAIMS_FOUND",
                    "fingerprint_json": '{"scope": "physics"}',
                    "loaded_at": now,
                },
                {
                    "run_id": RUN,
                    "pmcid": "PMC1",
                    "question": "q",
                    "state": "CLAIMS_FOUND",
                    "fingerprint_json": "{}",
                    "loaded_at": now,
                },
            ],
        )
        conn.execute(
            insert(old.tables["review_item"]).values(
                item_id="i2",
                run_id=RUN,
                question="q",
                pmcid="PMC2",
                claim_id="c1",
                value="39",
                claim_kind="SINGLE",
                second_kind="DISTRACTOR",
                item_json=item.model_dump_json(),
                created_at=now,
            )
        )

        conn.execute(
            insert(old.tables["review_decision"]).values(
                item_id="i2",
                reviewer="bob",
                chosen_supporting=True,
                approved=True,
                comment="kept",
                decided_at=now,
                issue="",
            )
        )

    done = store.upgrade(engine)

    # Two added by hand (domain, topic); value_read and answered_by came with the rebuild.
    assert done == {
        "columns_added": 2,
        "papers_filled": 2,
        "tables_rebuilt": 1,
        "choices_compared": 0,
    }
    by_pmcid = {row.pmcid: (row.domain, row.topic) for row in rows(engine, store.review_paper)}
    assert by_pmcid == {"PMC1": ("biology", ""), "PMC2": ("physics", "crystals")}
    (kept,) = rows(engine, store.review_decision)
    assert (kept.reviewer, kept.approved, kept.comment, kept.value_read) == (
        "bob",
        True,
        "kept",
        "",
    )
    assert kept.value_agreement is None, "a one-step row read no value: nothing to compare"
    # The upgraded file takes the writers that needed the new columns, the nullable verdict
    # and the new table.
    store.record_choice(engine, "i2", reviewer="alice", chosen_supporting=True, value_read="39")
    store.record_issue(engine, "i2", reviewer="carol", issue="garbled")
    store.skip_paper(engine, "alice", run_id=RUN, pmcid="PMC1")
    assert store.upgrade(engine) == {
        "columns_added": 0,
        "papers_filled": 2,
        "tables_rebuilt": 0,
        "choices_compared": 0,
    }, "idempotent"


# --- two steps -----------------------------------------------------------------------------


def test_a_choice_opens_the_row_with_the_value_read_and_no_verdict(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_choice(
        engine,
        "i1",
        reviewer="alice",
        chosen_supporting=True,
        value_read="39 min",
        time_to_decide_s=20.0,
        reviewer_role=ReviewerRole.STUDENT,
        reviewer_model="some/router",
        answered_by="some/model-a",
    )

    (row,) = rows(engine, store.review_decision)
    assert (row.chosen_supporting, row.value_read, row.approved, row.issue) == (
        True,
        "39 min",
        None,
        "",
    )
    assert row.value_agreement == "MATCHES", "computed by the store against the item's value"
    assert (row.reviewer_role, row.reviewer_model, row.answered_by) == (
        "STUDENT",
        "some/router",
        "some/model-a",
    )
    assert store.open_choice(engine, "i1", "alice") == store.Choice(True, "39 min", "MATCHES")
    assert store.open_choice(engine, "i1", "bob") is None


@pytest.mark.parametrize(
    ("value_read", "agreement"),
    [
        ("39", "MATCHES"),
        ("39 h", "SAME_NUMBER_DIFFERENT_UNIT"),
        ("21", "DIFFERS"),
        ("", "UNREADABLE"),
    ],
)
def test_the_agreement_is_whatever_the_reading_says_against_the_stored_value(
    engine, value_read, agreement
):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    store.record_choice(engine, "i1", reviewer="a", chosen_supporting=True, value_read=value_read)

    assert store.open_choice(engine, "i1", "a").value_agreement == agreement


def test_a_verdict_completes_the_open_row_and_adds_its_time_and_its_answerer(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)
    store.record_choice(
        engine,
        "i1",
        reviewer="alice",
        chosen_supporting=False,
        value_read="21 min",
        time_to_decide_s=20.0,
        answered_by="some/model-a",
    )

    store.record_verdict(
        engine,
        "i1",
        reviewer="alice",
        approved=False,
        comment="wrong medium",
        time_to_decide_s=5.0,
        answered_by="some/model-b",
    )

    (row,) = rows(engine, store.review_decision)
    assert (row.chosen_supporting, row.value_read) == (False, "21 min")
    assert (row.approved, row.comment) == (False, "wrong medium")
    assert row.time_to_decide_s == pytest.approx(25.0)
    assert row.answered_by == "some/model-a, some/model-b"
    assert store.open_choice(engine, "i1", "alice") is None


def test_the_same_answerer_twice_is_named_once(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)
    store.record_choice(
        engine, "i1", reviewer="alice", chosen_supporting=True, value_read="39", answered_by="m"
    )
    store.record_verdict(engine, "i1", reviewer="alice", approved=True, answered_by="m")

    (row,) = rows(engine, store.review_decision)
    assert row.answered_by == "m"


def test_a_verdict_without_a_choice_before_it_is_refused(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)

    with pytest.raises(store.DecisionNotSaved, match="no open choice"):
        store.record_verdict(engine, "i1", reviewer="alice", approved=True)

    assert rows(engine, store.review_decision) == []


def test_a_second_choice_on_the_same_item_is_refused(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)
    store.record_choice(engine, "i1", reviewer="alice", chosen_supporting=True, value_read="39")

    with pytest.raises(store.DecisionNotSaved, match="already chosen"):
        store.record_choice(
            engine, "i1", reviewer="alice", chosen_supporting=False, value_read="21"
        )

    assert len(rows(engine, store.review_decision)) == 1
    # Another reviewer's first step on the same item is not a second choice.
    store.record_choice(engine, "i1", reviewer="bob", chosen_supporting=False, value_read="21")
    assert len(rows(engine, store.review_decision)) == 2


def test_an_item_with_an_open_choice_is_still_the_reviewer_s_and_is_served_first(engine):
    store.load_run(
        engine,
        [a_result()],
        [an_item("i1"), an_item("i2"), an_item("i3")],
        question=QUESTION,
        run_id=RUN,
    )
    store.record_choice(engine, "i3", reviewer="alice", chosen_supporting=True, value_read="39")

    assert store.next_item(engine, "alice").item_id == "i3"
    assert store.remaining(engine, "alice") == 3
    assert [i.item_id for i in store.undecided_items(engine, "alice")] == ["i1", "i2", "i3"]
    store.record_verdict(engine, "i3", reviewer="alice", approved=True)
    assert store.next_item(engine, "alice").item_id == "i1"
    assert store.remaining(engine, "alice") == 2


def test_an_issue_after_the_choice_keeps_the_choice_and_leaves_no_verdict(engine):
    store.load_run(engine, [a_result()], [an_item("i1")], question=QUESTION, run_id=RUN)
    store.record_choice(
        engine,
        "i1",
        reviewer="alice",
        chosen_supporting=True,
        value_read="39 min",
        time_to_decide_s=10.0,
    )

    store.record_issue(
        engine,
        "i1",
        reviewer="alice",
        issue="the stored value is 93, the text says 39",
        time_to_decide_s=4.0,
    )

    (row,) = rows(engine, store.review_decision)
    assert (row.chosen_supporting, row.value_read) == (True, "39 min")
    assert row.approved is None
    assert row.issue == "the stored value is 93, the text says 39"
    assert row.time_to_decide_s == pytest.approx(14.0)
    assert store.open_choice(engine, "i1", "alice") is None
    assert store.next_item(engine, "alice") is None


def test_a_decision_on_an_unknown_item_is_not_saved_and_says_so(engine):
    """The page would be offering an item this database does not have. Telling the reviewer it was
    saved would be a falsehood, and returning quietly is that falsehood."""
    with pytest.raises(store.DecisionNotSaved, match="i-nope"):
        store.record_decision(
            engine, "i-nope", reviewer="alice@example.org", chosen_supporting=True, approved=True
        )

    assert rows(engine, store.review_decision) == []


def test_a_decision_that_cannot_reach_the_database_raises_with_the_cause():
    """Fails closed, the inverse of the trail store: the exception is what keeps the item open.

    A real engine that genuinely cannot connect -- a path no database can be opened at -- rather
    than a stubbed one, so what is asserted is the failure the driver actually raises.
    """
    unreachable = create_engine("sqlite:////nonexistent/directory/review.db")

    with pytest.raises(store.DecisionNotSaved) as caught:
        store.record_decision(
            unreachable, "i1", reviewer="alice@example.org", chosen_supporting=True, approved=True
        )

    assert isinstance(caught.value.__cause__, OperationalError)
    assert "OperationalError" in str(caught.value)
    unreachable.dispose()


class UnreachableEngine:
    """A database that is not there. `begin()` reaches for a connection, which is where a real
    engine fails: an unreachable host, a refused password, a pool that cannot be filled."""

    def connect(self):
        raise OSError("connection refused")

    def begin(self):
        self.connect()


def test_a_failure_of_any_kind_becomes_a_refusal_and_is_never_swallowed():
    """`DecisionNotSaved` for everything, not only for what SQLAlchemy raises. The failure the
    store must never make is the trail store's -- returning as though the row had been written."""
    with pytest.raises(store.DecisionNotSaved) as caught:
        store.record_decision(
            UnreachableEngine(),
            "i1",
            reviewer=None,
            chosen_supporting=True,
            approved=True,
        )

    assert isinstance(caught.value.__cause__, OSError)
    assert "connection refused" in str(caught.value)


# --- the deployed schema -------------------------------------------------------------------


_TABLE = re.compile(r"create table if not exists (\w+)\s*\((.*?)\n\);", re.DOTALL)


def sql_columns() -> dict[str, set[str]]:
    """The column names `sql/review.sql` declares, per table. One column per line, by convention
    stated in that file's header, which is what makes this parse a fair reading of it."""
    declared: dict[str, set[str]] = {}
    for name, body in _TABLE.findall(SQL_PATH.read_text()):
        columns = set()
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            if line.startswith(("primary key", "foreign key", "unique", "constraint")):
                continue  # a table constraint, on its own line by the file's convention
            columns.add(line.split()[0])
        declared[name] = columns
    return declared


def test_the_deployed_schema_declares_exactly_the_columns_the_store_writes():
    """A drift test. `store.py`'s tables are the writer and `sql/review.sql` is what a deployment
    actually has; a column added to one alone passes every other case in this file and is missing
    in the only place it matters."""
    declared = sql_columns()
    # The parser first: an equality against an empty set would pass for the wrong reason.
    assert "chosen_supporting" in declared["review_decision"], "the .sql parse found no columns"

    assert set(declared) == set(store.METADATA.tables)
    for name, table in store.METADATA.tables.items():
        assert declared[name] == {column.name for column in table.columns}, name


@pytest.mark.network
def test_the_ddl_is_valid_postgres_and_takes_the_rows_the_store_writes():
    """Two things SQLite cannot answer, and a double would answer wrongly.

    A syntax error in `sql/review.sql`, or a column type the store's own parameters do not fit --
    the text-versus-jsonb decision in that file's header is exactly of that kind -- would survive
    every offline case here. Everything runs inside one transaction and is rolled back, so the DDL
    leaves no tables and the rows no residue, whatever the database already held.
    """
    url = _live_url()
    pmcid = f"PMCTEST{uuid.uuid4().hex[:8]}"
    item_id = f"item-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    # The store's own row builders, so what is bound here is what `load_run` binds: the point of
    # the case is those parameters meeting the column types `sql/review.sql` declares.
    paper_row = store._paper_row(a_result(a_paper(pmcid)), question=QUESTION, run_id=RUN, now=now)
    item_row = store._item_row(
        an_item(item_id, a_paper(pmcid)), question=QUESTION, run_id=RUN, now=now
    )

    engine = store.engine_from_url(url)
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                for statement in _sql_statements(SQL_PATH.read_text()):
                    conn.execute(text(statement))
                conn.execute(insert(store.review_paper), paper_row)
                conn.execute(insert(store.review_item), item_row)
                conn.execute(
                    insert(store.review_decision).values(
                        item_id=item_id,
                        reviewer=None,
                        chosen_supporting=True,
                        approved=True,
                        comment="live ddl check",
                        decided_at=now,
                        time_to_decide_s=1.0,
                    )
                )
                query = select(store.review_item.c.item_json).where(
                    store.review_item.c.item_id == item_id
                )
                stored = conn.execute(query).one()
                assert ReviewItem.model_validate_json(stored.item_json).item_id == item_id
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _live_url() -> str:
    """Skipped, not failed, where nothing is configured: a contributor without a database must not
    see a red suite. The same source the trail store's live tests read."""
    if not SECRETS.exists():
        pytest.skip("no .streamlit/secrets.toml; nothing to connect to")
    try:
        return tomllib.loads(SECRETS.read_text())["connections"]["usage"]["url"]
    except (KeyError, tomllib.TOMLDecodeError):
        pytest.skip("no [connections.usage] url configured")


def _sql_statements(sql: str) -> list[str]:
    """The file split into statements, with its comments dropped. No string literal in it holds a
    semicolon, which is what makes the naive split safe."""
    stripped = "\n".join(line.split("--")[0] for line in sql.splitlines())
    return [statement.strip() for statement in stripped.split(";") if statement.strip()]
