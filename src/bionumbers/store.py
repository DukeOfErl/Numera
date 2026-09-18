"""The review store: three tables of its own, and a writer that fails closed.

The trail (`scinumbers_ask.trail_store`) is an append-only event log whose writer swallows every
failure. This is the inverse on both counts, and both inversions are design D8 (ADR-0930). A
decision is not telemetry beside a product -- it *is* the product, the one thing this prototype
exists to collect -- so `record_decision` raises `DecisionNotSaved` on any failure and the page
keeps the item open. A dropped trail row costs one row of a dataset read by eye; a dropped decision
costs a reviewer's judgement, and nothing downstream would ever know it was missing.

SQLAlchemy Core rather than the ORM: three tables, no object graph, and the same statements have to
run against SQLite (the offline tests) and Postgres (the deployment). That portability is why the
JSON columns are `Text` holding `model_dump_json()` output -- read back through
`model_validate_json`, never queried by key, so a `jsonb` column would buy indexing nobody uses at
the price of a cast Core's `insert()` cannot express.

`sql/review.sql` is the deployed schema and carries the operator's prose; the tables here are the
same columns, for `create_all` against a fresh database. Drift between the two is silent -- a
column added here alone works in every test and is absent where it matters -- so
`tests/test_bionumbers_store.py` parses that file and compares the names.

No Streamlit and nothing from `scinumbers_ask` (design D9): the page builds the engine through
`st.connection`, which caches it across sessions, and hands it over.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    text,
)

from bionumbers.records import UNLICENSED, PaperResult, ReviewItem

#: Seconds to wait for a connection to be established.
#:
#: The same value as `scinumbers_ask.trail_store.CONNECT_TIMEOUT_S`, copied rather than imported:
#: the validator's core modules may not depend on the ask package (design D9), and one integer is
#: the cheaper of the two prices. Like there, it is the one guard the *caller* owns, because libpq
#: takes it at connect time and it cannot be enforced from inside an operation that already has an
#: engine -- hence `engine_from_url`, for every caller that is not the Streamlit page.
CONNECT_TIMEOUT_S = 5

#: Per-transaction statement timeout, in milliseconds, on Postgres.
#:
#: Higher than the trail's 2 s, and the asymmetry is deliberate. There a statement that runs long
#: is abandoned and the row is lost, which is the cheap direction; here abandoning it *is* the
#: failure, so the reviewer is made to wait a little longer before being told the decision was not
#: saved. Neon's own default is `0` -- unlimited -- so without this a hung statement hangs for
#: ever, and a reviewer with a spinning page has no way to tell that from a slow one.
STATEMENT_TIMEOUT_MS = 5000

METADATA = MetaData()

#: One row per article the run touched, whatever its ending -- `NOTHING_TO_EXTRACT` and
#: `UNREADABLE` are findings and are kept. `licence` is carried so a reader of the table can see
#: on what terms the paper's text was allowed here at all; `load_run` refuses to write any item
#: for a paper whose licence is `UNLICENSED`.
review_paper = Table(
    "review_paper",
    METADATA,
    Column("pmcid", Text, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("question", Text, nullable=False),
    Column("pmid", Text, nullable=False, default=""),
    Column("doi", Text, nullable=False, default=""),
    Column("title", Text, nullable=False, default=""),
    Column("year", Integer),
    Column("licence", Text, nullable=False, default=UNLICENSED),
    Column("state", Text, nullable=False),
    Column("reason", Text, nullable=False, default=""),
    Column("spend_usd", Float, nullable=False, default=0.0),
    Column("spend_json", Text, nullable=False, default="{}"),
    Column("fingerprint_json", Text, nullable=False, default="{}"),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)

#: One row per screen. The columns beside `item_json` are the ones a later analysis groups by --
#: kind, type, question, run -- so that measuring distractor difficulty does not mean parsing every
#: JSON blob. `item_json` is the whole `ReviewItem`, and is what the page renders from: a column
#: and the JSON disagreeing is a bug, and the JSON is the one that was shown.
review_item = Table(
    "review_item",
    METADATA,
    Column("item_id", Text, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("question", Text, nullable=False),
    Column("pmcid", Text, ForeignKey("review_paper.pmcid"), nullable=False),
    Column("claim_id", Text, nullable=False),
    Column("value", Text, nullable=False),
    Column("unit", Text, nullable=False, default=""),
    Column("claim_kind", Text, nullable=False),
    Column("second_kind", Text, nullable=False),
    Column("distractor_type", Text),
    Column("item_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

#: What a reviewer decided, once per item per reviewer. `reviewer` is null where no identity is
#: configured, which `user-identity` already allows and this spec repeats: the decision is recorded
#: with no account and nothing else about it differs.
#:
#: No unique constraint on `(item_id, reviewer)`, deliberately. Postgres treats nulls as distinct,
#: so such a constraint would hold for a signed-in reviewer and quietly not hold for an anonymous
#: one -- a rule that applies to some rows is worse than none, because it reads as if it applies to
#: all. `next_item` is the enforcement, and it treats both the same way.
review_decision = Table(
    "review_decision",
    METADATA,
    # `with_variant` because SQLite auto-increments only a column declared exactly `INTEGER
    # PRIMARY KEY`; `BIGINT PRIMARY KEY` is an ordinary NOT NULL column there and the insert would
    # fail. Postgres gets the wide type, which is what `sql/review.sql` declares.
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("item_id", Text, ForeignKey("review_item.item_id"), nullable=False),
    Column("reviewer", Text),
    Column("chosen_supporting", Boolean, nullable=False),
    Column("approved", Boolean, nullable=False),
    Column("comment", Text, nullable=False, default=""),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("time_to_decide_s", Float),
)


class DecisionNotSaved(RuntimeError):
    """A decision did not reach the table. The item stays open and the reviewer is told.

    Raised for every failure alike -- an unreachable database, a refused insert, an item id that
    is not there -- because the page's answer is the same for all of them and a caller that had to
    distinguish them would be a caller that could get one wrong. What separates them is the
    chained cause, which is for the operator's log.
    """


def create_all(engine: Any) -> None:
    """Create the three tables if they are absent.

    For SQLite in the tests and for a fresh database. The deployed Postgres schema is
    `sql/review.sql`, which carries the comments an operator needs and is not generated from here.
    """
    METADATA.create_all(engine)


def engine_from_url(url: str, **kwargs: Any) -> Engine:
    """An engine with this module's own timeouts, for a caller without Streamlit.

    The review page gets its engine from `st.connection`; this exists for the CLI, the loader and
    the live tests. `connect_timeout` is set here because libpq takes it at connect time -- an
    unreachable host is where a write actually hangs, and the statement timeout does nothing for
    it.
    """
    connect_args = {"connect_timeout": CONNECT_TIMEOUT_S} | kwargs.pop("connect_args", {})
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args, **kwargs)


def load_run(
    engine: Any,
    results: Iterable[PaperResult],
    items: Iterable[ReviewItem],
    *,
    question: str,
    run_id: str,
) -> int:
    """Load one run's papers and items. Returns the number of items inserted.

    Idempotent by identifier: a paper already present is left exactly as it was, and an item id
    already present is skipped. Re-running a load must not rewrite the row a reviewer's decision
    already points at -- a second extraction of the same paper can reach a different state, and
    updating it in place would silently restate what the reviewer was shown.

    Raises `ValueError` for an item whose paper is `UNLICENSED`, and for one whose paper has no row
    here and none in this call. Nothing is written when either fires: a half-loaded run is worse
    than none, and the caller re-runs it after dropping the item.
    """
    results = list(results)
    items = list(items)

    # The refusal is the spec's "its text is never written past the cache", and it belongs here
    # rather than in the loader's caller: a second caller -- a test, a re-load, the CLI -- would
    # not inherit a guard written into the first. A pmcid counts as unlicensed if *either* the
    # run's result or the item's own copy of the paper says so; the two can only disagree through
    # a bug, and refusing is the direction that costs a re-run rather than a licence breach.
    unlicensed = {r.paper.pmcid for r in results if r.paper.licence == UNLICENSED}
    unlicensed |= {i.paper.pmcid for i in items if i.paper.licence == UNLICENSED}
    for item in items:
        if item.paper.pmcid in unlicensed:
            raise ValueError(
                f"{item.paper.pmcid} is {UNLICENSED}: no item may be loaded for it "
                f"(item {item.item_id})"
            )

    now = datetime.now(UTC)
    with engine.begin() as conn:
        present_papers = set(conn.scalars(select(review_paper.c.pmcid)))
        new_papers = [
            _paper_row(result, question=question, run_id=run_id, now=now)
            for result in results
            if result.paper.pmcid not in present_papers
        ]
        if new_papers:
            conn.execute(insert(review_paper), new_papers)

        # SQLite does not enforce foreign keys unless asked to, so an item pointing at no paper
        # would load there and be refused only in production. The guard is here so both backends
        # answer the same way, and it is checked after the papers so a run loading both at once
        # passes.
        known = present_papers | {row["pmcid"] for row in new_papers}
        for item in items:
            if item.paper.pmcid not in known:
                raise ValueError(
                    f"item {item.item_id} names paper {item.paper.pmcid}, which has no row"
                )

        present_items = set(conn.scalars(select(review_item.c.item_id)))
        new_items = [
            _item_row(item, question=question, run_id=run_id, now=now)
            for item in items
            if item.item_id not in present_items
        ]
        if new_items:
            conn.execute(insert(review_item), new_items)
    return len(new_items)


def next_item(engine: Any, reviewer: str | None) -> ReviewItem | None:
    """The next item this reviewer has not decided, or None when none remain.

    Interleaved across papers: the spec's reason is that a reviewer who sees a paper's items in a
    row learns its conditions from the previous screen, and then judges the next one from memory
    rather than from the text. The order is by each item's position *within* its paper first and
    by paper second, so the first item of every paper comes before the second of any.

    The numbering is computed over every item, not over the undecided ones. Numbering the
    survivors renumbers them after each decision -- the second item of a three-item paper becomes
    a first, ties with the other paper's first, and the paper is served in a block anyway. That is
    the bug this ordering exists to prevent, and it looks correct until you follow four items
    through.
    """
    position = func.row_number().over(
        partition_by=review_item.c.pmcid, order_by=review_item.c.item_id
    )
    ordered = select(
        review_item.c.item_id,
        review_item.c.item_json,
        review_item.c.pmcid,
        position.label("position"),
    ).subquery()
    statement = (
        select(ordered.c.item_json)
        .where(_undecided(ordered.c.item_id, reviewer))
        .order_by(ordered.c.position, ordered.c.pmcid)
        .limit(1)
    )
    with engine.begin() as conn:
        _bound(conn)
        row = conn.execute(statement).first()
    return None if row is None else ReviewItem.model_validate_json(row.item_json)


def remaining(engine: Any, reviewer: str | None) -> int:
    """How many items this reviewer has still to decide."""
    statement = (
        select(func.count())
        .select_from(review_item)
        .where(_undecided(review_item.c.item_id, reviewer))
    )
    with engine.begin() as conn:
        _bound(conn)
        return int(conn.execute(statement).scalar_one())


def record_decision(
    engine: Any,
    item_id: str,
    *,
    reviewer: str | None,
    chosen_supporting: bool,
    approved: bool,
    comment: str = "",
    time_to_decide_s: float | None = None,
) -> None:
    """Write one decision, or raise. Returns only when the row is committed.

    Fails closed (ADR-0930): every failure becomes `DecisionNotSaved` with the cause chained, and
    there is no path that returns quietly without a row. The swallow the trail store performs is
    what this must never do -- and it is an easy inversion to make by accident, which is why the
    two modules say so in each other's direction.

    An unknown `item_id` is a failure of the same kind, not a no-op: it means the page is offering
    an item this database does not have, and a reviewer who was told "saved" would have been told
    a falsehood.
    """
    try:
        with engine.begin() as conn:
            _bound(conn)
            known_item = select(review_item.c.item_id).where(review_item.c.item_id == item_id)
            if conn.execute(known_item).first() is None:
                raise DecisionNotSaved(f"no review item {item_id!r}")
            conn.execute(
                insert(review_decision).values(
                    item_id=item_id,
                    reviewer=reviewer,
                    chosen_supporting=chosen_supporting,
                    approved=approved,
                    comment=comment,
                    decided_at=datetime.now(UTC),
                    time_to_decide_s=time_to_decide_s,
                )
            )
    except DecisionNotSaved:
        raise
    except Exception as exc:
        raise DecisionNotSaved(f"{type(exc).__name__}: {exc}") from exc


def _undecided(item_id_column: Any, reviewer: str | None):
    """No decision row for this item by this reviewer.

    The `None` reviewer is a reviewer in its own right -- an unsigned-in deployment, where the
    spec says the decision is recorded with no account and nothing else differs -- so it must
    match `reviewer IS NULL` rather than be compared to a bound NULL, which matches nothing and
    would re-offer every item for ever. Written out rather than left to SQLAlchemy's implicit
    `== None`, so that a reader tidying it into a parameter sees what they are removing.
    """
    by_reviewer = (
        review_decision.c.reviewer.is_(None)
        if reviewer is None
        else review_decision.c.reviewer == reviewer
    )
    # A column rather than `literal(1)`: an untyped parameter in the select list of a correlated
    # EXISTS is the kind of thing a backend is free to refuse, and nothing here needs the constant.
    decided = select(review_decision.c.id).where(
        review_decision.c.item_id == item_id_column, by_reviewer
    )
    return ~decided.exists()


def _bound(conn: Any) -> None:
    """Bound the statement, where the backend has such a thing.

    Postgres only: SQLite has no statement timeout and rejects the syntax, so an unconditional
    `SET LOCAL` would make every offline test fail on a guard meant for production. `SET LOCAL` is
    scoped to the transaction and cannot leak onto the next borrower of a pooled connection.
    """
    if conn.dialect.name == "postgresql":
        conn.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))


def _paper_row(result: PaperResult, *, question: str, run_id: str, now: datetime) -> dict[str, Any]:
    paper = result.paper
    return {
        "pmcid": paper.pmcid,
        "run_id": run_id,
        "question": question,
        "pmid": paper.pmid,
        "doi": paper.doi,
        "title": paper.title,
        "year": paper.year,
        "licence": paper.licence,
        "state": result.state.value,
        "reason": result.reason,
        "spend_usd": result.spend.usd,
        "spend_json": result.spend.model_dump_json(),
        "fingerprint_json": result.fingerprint.model_dump_json(),
        "loaded_at": now,
    }


def _item_row(item: ReviewItem, *, question: str, run_id: str, now: datetime) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "run_id": run_id,
        "question": question,
        "pmcid": item.paper.pmcid,
        "claim_id": item.claim.claim_id,
        "value": item.claim.value,
        "unit": item.claim.unit,
        "claim_kind": item.claim.kind.value,
        "second_kind": item.second_kind.value,
        "distractor_type": item.distractor_type.value if item.distractor_type else None,
        # The whole record, because the page renders from it and a later analysis must be able to
        # see exactly what was on the screen -- including the second text's kind, which the
        # reviewer never saw (D5).
        "item_json": item.model_dump_json(),
        "created_at": now,
    }
