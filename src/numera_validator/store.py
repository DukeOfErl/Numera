"""The review store: three tables of its own and the curated tier, and a writer that fails closed.

The trail (`numera_ask.trail_store`) is an append-only event log whose writer swallows every
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

No Streamlit and nothing from `numera_ask` (design D9): the page builds the engine through
`st.connection`, which caches it across sessions, and hands it over.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
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
    ForeignKeyConstraint,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    text,
    true,
    update,
)
from sqlalchemy import inspect as sa_inspect

from numera_validator import curated, readings
from numera_validator.curated import Refusal
from numera_validator.records import UNLICENSED, PaperResult, ReviewerRole, ReviewItem

#: Seconds to wait for a connection to be established.
#:
#: The same value as `numera_ask.trail_store.CONNECT_TIMEOUT_S`, copied rather than imported:
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

#: The domain a paper is filed under when its run predates harvest scopes: every such run was
#: a biology question or a yeast-and-cytoskeleton harvest.
DEFAULT_DOMAIN = "biology"

#: One row per article *per run*, whatever its ending -- `NOTHING_TO_EXTRACT` and `UNREADABLE`
#: are findings and are kept. Keyed by the run as well as the article: two questions asked of
#: the same paper are two extractions with two states, and keyed by article alone the second
#: was silently skipped on load (code review of 2026-09-21, finding 4). `licence` is carried so
#: a reader of the table can see on what terms the paper's text was allowed here at all;
#: `load_run` refuses to write any item for a paper whose licence is `UNLICENSED`.
review_paper = Table(
    "review_paper",
    METADATA,
    Column("run_id", Text, primary_key=True),
    Column("pmcid", Text, primary_key=True),
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
    # What a reviewer may choose to be shown (ADR-0980). `domain` is the harvest scope the paper
    # was read under -- `biology`, `organismal`, `biophysics`, `chemistry`, `physics` -- with the
    # runs from before scopes existed read as biology; `topic` is the harvester's label for the
    # paper's subject ("planarians", "cytoskeleton"), empty where none was given. Columns rather
    # than reads of the JSON beside them because the serving query filters on them, and a JSON
    # path is spelled differently on the two backends.
    Column("domain", Text, nullable=False, default=DEFAULT_DOMAIN),
    Column("topic", Text, nullable=False, default=""),
    # The paper's bibliographic record as CSL-JSON, for the citation a reader is shown (ADR-1750).
    Column("csl_json", Text, nullable=False, default=""),
)

#: A paper a reviewer set aside -- "not my field" -- and is not offered again. Recorded rather
#: than dropped: a paper nobody wanted is itself a finding about the pool. Only a person skips;
#: the simulated reviewers never read this table (ADR-0980).
review_skip = Table(
    "review_skip",
    METADATA,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("reviewer", Text),
    Column("run_id", Text, nullable=False),
    Column("pmcid", Text, nullable=False),
    Column("skipped_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["run_id", "pmcid"], ["review_paper.run_id", "review_paper.pmcid"]),
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
    Column("pmcid", Text, nullable=False),
    Column("claim_id", Text, nullable=False),
    Column("value", Text, nullable=False),
    Column("unit", Text, nullable=False, default=""),
    Column("claim_kind", Text, nullable=False),
    Column("second_kind", Text, nullable=False),
    Column("distractor_type", Text),
    Column("item_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # The entry's property as a reader is shown it: the harvest's "measure of object" name
    # (ADR-1700). Written on load from the claim, empty where the parts made no name or a
    # question was asked, until `fill_properties` names it -- and never into `item_json`, which
    # stays what the reviewer saw.
    Column("property", Text, nullable=False, default=""),
    ForeignKeyConstraint(["run_id", "pmcid"], ["review_paper.run_id", "review_paper.pmcid"]),
)

#: What a reviewer decided -- or the issue they raised instead -- once per item per reviewer,
#: written in two steps (ADR-0970): the choice of text with the value the reviewer read from it,
#: *then*, once the stored value is revealed, the verdict. One row carries both; between the two
#: steps it is an *open* row (`approved` null, `issue` empty) and the item is still this
#: reviewer's to finish. `reviewer` is null where no identity is
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
    # `approved` is null on an open row and on an issue row; `chosen_supporting` is null only on
    # an issue raised before any text was chosen. A verdict is never stored beside an issue: a
    # reviewer who says the item cannot be judged has given none. No check constraint says so --
    # one could not be added to a deployed table by an idempotent statement, and a rule some
    # databases enforce reads as one all of them do -- so the writers below are the enforcement:
    # each can only write its own shape.
    Column("chosen_supporting", Boolean),
    Column("approved", Boolean),
    Column("comment", Text, nullable=False, default=""),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("time_to_decide_s", Float),
    Column("issue", Text, nullable=False, default=""),
    # The value the reviewer read off the text they chose, written *before* the stored value is
    # shown to them: the one figure here that an extractor's answer cannot have steered.
    Column("value_read", Text, nullable=False, default=""),
    # The rung of the trust ladder the reviewer stands on (`records.ReviewerRole`), null where
    # none was recorded. `reviewer_model` is the model id when a model decided and null for a
    # person: a row with a model and a role other than `AI` is a *simulated* review, and every
    # figure drawn from it has to say so (ADR-0960).
    Column("reviewer_role", Text),
    Column("reviewer_model", Text),
    # The model the provider says answered, where that differs from `reviewer_model`: a router
    # names itself in the request and another model in the reply. Comma-joined when the two
    # steps were answered by different ones. Null for a person.
    Column("answered_by", Text),
    # How `value_read` stands to the stored value (`readings.Agreement`), computed when the
    # choice is written, so every driver records it the same way. Null on an issue raised before
    # a choice, and on rows from before the two steps existed.
    Column("value_agreement", Text),
)


#: BioNumbers' own entries, where nothing about them gives cause for doubt (ADR-1510): the
#: curated tier, shown beside harvested entries at the top of the trust order. Keyed by the BNID,
#: and replaced whole on every load -- a curated entry has no decision pointing at it, so a
#: reload that restates one restates nothing a reviewer saw.
curated_entry = Table(
    "curated_entry",
    METADATA,
    Column("entry_id", Integer, primary_key=True),
    Column("property", Text, nullable=False),
    Column("organism", Text, nullable=False, default=""),
    Column("value", Float),
    Column("range_low", Float),
    Column("range_high", Float),
    Column("units", Text, nullable=False),
    Column("approximate", Boolean, nullable=False, default=False),
    Column("reference", Text, nullable=False, default=""),
    Column("pubmed_id", Text, nullable=False),
    Column("method", Text, nullable=False),
    Column("comments", Text, nullable=False, default=""),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class Preference:
    """What a human reviewer asked to be shown (ADR-0980): papers of one domain, of one topic,
    and never a paper they skipped. Passed by the page to the serving query; the simulated
    review never builds one, so a model keeps drawing its assigned subset whatever a person
    set aside. `None` for a field means no restriction on it; an instance with both `None`
    still honours the reviewer's skips, which is what makes it a person's."""

    domain: str | None = None
    topic: str | None = None


@dataclass(frozen=True)
class Choice:
    """A reviewer's open first step on an item: which text, the value they read from it, and
    how that reading stands to the stored value."""

    chosen_supporting: bool
    value_read: str
    value_agreement: str | None = None


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


#: The two names a SQLite rebuild of `review_decision` goes through. `__old` is what the first
#: version of `upgrade` renamed the table to; a file holding one was left mid-rebuild by it.
_OLD_DECISIONS = "review_decision__old"
_NEW_DECISIONS = "review_decision__new"


def upgrade(engine: Any) -> dict[str, int]:
    """Bring a database loaded under an earlier schema up to this one, in place.

    `create_all` adds missing *tables* and nothing else, so a SQLite file loaded before
    `review_decision.value_read` or `review_paper.domain` existed keeps working for reads and
    fails on the first write. This adds each missing column with its default, then fills
    `domain` from the paper's fingerprint and `topic` from any of its items' records -- the two
    facts the loader now writes on load and older rows never had -- and `value_agreement` on
    every choice that read a value before it was computed. Idempotent: a second run adds nothing and
    refills the same values. For Postgres the same statements live in
    `sql/review.sql`; this is for the local files the demo is reviewed from.

    Returns what it did, by name, so the caller can say so.
    """
    done = {"columns_added": 0, "papers_filled": 0, "tables_rebuilt": 0, "choices_compared": 0}
    create_all(engine)
    # SQLite cannot drop a NOT NULL constraint, and the first schema declared `approved` and
    # `chosen_supporting` NOT NULL -- which an issue row and an open row both violate. The one
    # way is the documented one: a fresh table, copy, drop the old, rename the new.
    if engine.dialect.name == "sqlite":
        inspector = sa_inspect(engine)
        leftover = [n for n in (_OLD_DECISIONS, _NEW_DECISIONS) if inspector.has_table(n)]
        if leftover:
            # An earlier rebuild stopped between its steps. Every decision may be in that table
            # and nowhere else; refusing is the only answer that cannot lose them.
            raise RuntimeError(
                f"{leftover[0]} exists: a previous upgrade was interrupted; recover the "
                "decisions from it by hand before running again"
            )
        present = {c["name"]: c for c in inspector.get_columns(review_decision.name)}
        if any(
            not present[name]["nullable"]
            for name in ("approved", "chosen_supporting")
            if name in present
        ):
            # Built beside the old table and swapped in last, so the old table stands until the
            # copy is complete: a failure before the drop leaves everything where it was, and a
            # failure after it leaves the copy, which the refusal above then names.
            fresh = MetaData()
            review_item.to_metadata(fresh)
            new_table = review_decision.to_metadata(fresh, name=_NEW_DECISIONS)
            new_table.create(engine)
            with engine.begin() as conn:
                # Every column the new table has: the old ones copied, the new ones at their
                # defaults, since a Core default is Python-side and the insert below is not.
                names, values = [], []
                for column in review_decision.columns:
                    names.append(column.name)
                    if column.name in present:
                        values.append(column.name)
                    elif column.default is not None and isinstance(column.default.arg, str):
                        values.append(repr(column.default.arg))
                    else:
                        values.append("NULL")
                conn.execute(
                    text(
                        f"insert into {_NEW_DECISIONS} ({', '.join(names)}) "
                        f"select {', '.join(values)} from {review_decision.name}"
                    )
                )
            with engine.begin() as conn:
                conn.execute(text(f"drop table {review_decision.name}"))
                conn.execute(text(f"alter table {_NEW_DECISIONS} rename to {review_decision.name}"))
            done["tables_rebuilt"] += 1
    present = {
        table.name: {column["name"] for column in sa_inspect(engine).get_columns(table.name)}
        for table in METADATA.sorted_tables
    }
    with engine.begin() as conn:
        for table in METADATA.sorted_tables:
            for column in table.columns:
                if column.name in present[table.name]:
                    continue
                typename = column.type.compile(engine.dialect)
                default = column.default.arg if column.default is not None else None
                clause = f"alter table {table.name} add column {column.name} {typename}"
                if default is not None:
                    clause += (
                        f" not null default {default!r}"
                        if isinstance(default, str)
                        else f" default {default!r}"
                    )
                conn.execute(text(clause))
                done["columns_added"] += 1
        papers = conn.execute(
            select(review_paper.c.run_id, review_paper.c.pmcid, review_paper.c.fingerprint_json)
        ).all()
        for run_id, pmcid, fingerprint_json in papers:
            try:
                scope = json.loads(fingerprint_json or "{}").get("scope") or ""
            except ValueError:
                scope = ""
            topic = ""
            item_json = conn.execute(
                select(review_item.c.item_json)
                .where(review_item.c.run_id == run_id, review_item.c.pmcid == pmcid)
                .limit(1)
            ).scalar()
            if item_json:
                try:
                    topic = json.loads(item_json).get("paper", {}).get("topic") or ""
                except ValueError:
                    topic = ""
            conn.execute(
                update(review_paper)
                .where(review_paper.c.run_id == run_id, review_paper.c.pmcid == pmcid)
                .values(domain=scope or DEFAULT_DOMAIN, topic=topic)
            )
            done["papers_filled"] += 1
        uncompared = conn.execute(
            select(
                review_decision.c.id,
                review_decision.c.value_read,
                review_item.c.value,
                review_item.c.unit,
            )
            .join(review_item, review_item.c.item_id == review_decision.c.item_id)
            .where(
                review_decision.c.value_agreement.is_(None),
                review_decision.c.chosen_supporting.is_not(None),
                # A row from before the two steps read no value; that is null, not UNREADABLE.
                review_decision.c.value_read != "",
            )
        ).all()
        for row_id, value_read, value, unit in uncompared:
            conn.execute(
                update(review_decision)
                .where(review_decision.c.id == row_id)
                .values(value_agreement=readings.compare(value_read, value, unit).value)
            )
            done["choices_compared"] += 1
    return done


def fill_references(engine: Any, csl_json_for: Callable[[str], str]) -> int:
    """Give every paper without a bibliographic record the one `csl_json_for(pmcid)` returns.

    For a store loaded before `csl_json` existed; `upgrade` adds the column and cannot fill it,
    since the record is in the paper's full text and not in any row. A paper already holding one
    is left as it is, and one the callable answers empty for stays empty -- so a run over a
    partial cache fills what it can and the next run fills the rest. Returns the rows written.
    """
    with engine.begin() as conn:
        _bound(conn)
        unfilled = conn.execute(
            select(review_paper.c.run_id, review_paper.c.pmcid).where(review_paper.c.csl_json == "")
        ).all()
        written = 0
        for run_id, pmcid in unfilled:
            record = csl_json_for(pmcid)
            if not record:
                continue
            conn.execute(
                update(review_paper)
                .where(review_paper.c.run_id == run_id, review_paper.c.pmcid == pmcid)
                .values(csl_json=record)
            )
            written += 1
    return written


def fill_properties(engine: Any, property_for: Callable[[ReviewItem], str]) -> int:
    """Give every item without a property the name `property_for(item)` returns.

    For a store loaded before `review_item.property` existed. An item already named is not
    asked about; one the callable answers empty for stays empty, so a run can be repeated until
    every item is named. Each name is written as it is decided, so a run that stops keeps what it
    had named. Returns the rows written.
    """
    with engine.begin() as conn:
        _bound(conn)
        unnamed = conn.execute(
            select(review_item.c.item_id, review_item.c.item_json).where(
                review_item.c.property == ""
            )
        ).all()
    written = 0
    for item_id, item_json in unnamed:
        named = property_for(ReviewItem.model_validate_json(item_json))
        if not named:
            continue
        with engine.begin() as conn:
            _bound(conn)
            conn.execute(
                update(review_item).where(review_item.c.item_id == item_id).values(property=named)
            )
        written += 1
    return written


def engine_from_url(url: str, **kwargs: Any) -> Engine:
    """An engine with this module's own timeouts, for a caller without Streamlit.

    The review page gets its engine from `st.connection`; this exists for the CLI, the loader and
    the live tests. `connect_timeout` is set here because libpq takes it at connect time -- an
    unreachable host is where a write actually hangs, and the statement timeout does nothing for
    it.
    """
    connect_args = dict(kwargs.pop("connect_args", {}))
    if not url.startswith("sqlite"):
        # libpq's keyword; sqlite3 rejects it as unknown. SQLite is the local and test backend, and
        # a file on disk has no host to time out on.
        connect_args = {"connect_timeout": CONNECT_TIMEOUT_S} | connect_args
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
        present_papers = set(
            conn.execute(
                select(review_paper.c.pmcid).where(review_paper.c.run_id == run_id)
            ).scalars()
        )
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
        # passes. Within this run: a paper another run loaded is not this run's paper.
        known = present_papers | {row["pmcid"] for row in new_papers}
        for item in items:
            if item.paper.pmcid not in known:
                raise ValueError(
                    f"item {item.item_id} names paper {item.paper.pmcid}, which has no row "
                    f"in run {run_id}"
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


def load_curated(engine: Any, corpus: Iterable[dict]) -> tuple[int, Counter[Refusal]]:
    """Replace the curated tier with the corpus entries that pass `curated.refusal`.

    Returns how many rows the tier now holds and how many entries were refused for each reason.
    Takes the corpus's own lines and runs the refusal here, in the operation, rather than taking
    already-built entries: a `CuratedEntry` is a plain model any caller can construct, so a
    loader that trusted the type would admit whatever a second caller built by hand (code review
    of 2026-10-07, finding 10).
    """
    kept, refused = curated.select(corpus)
    now = datetime.now(UTC)
    rows = [{**entry.model_dump(), "loaded_at": now} for entry in kept]
    with engine.begin() as conn:
        conn.execute(curated_entry.delete())
        if rows:
            conn.execute(insert(curated_entry), rows)
    return len(rows), refused


def next_item(
    engine: Any, reviewer: str | None, preference: Preference | None = None
) -> ReviewItem | None:
    """The next item this reviewer has not decided, or None when none remain.

    `preference` narrows the pool to the domain and topic a person chose and leaves out the
    papers they skipped; without one -- the simulated review -- every item is in the pool.

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
        partition_by=(review_item.c.run_id, review_item.c.pmcid), order_by=review_item.c.item_id
    )
    ordered = select(
        review_item.c.item_id,
        review_item.c.item_json,
        review_item.c.run_id,
        review_item.c.pmcid,
        position.label("position"),
    ).subquery()
    # An item this reviewer has chosen a text for but not yet judged comes first, whatever its
    # position: the reveal belongs to the choice just made, and an item left half-done is one
    # whose second step would otherwise be made from memory of a screen seen items ago.
    statement = (
        select(ordered.c.item_json)
        .where(
            _undecided(ordered.c.item_id, reviewer),
            _preferred(ordered.c.run_id, ordered.c.pmcid, reviewer, preference),
        )
        .order_by(
            _has_open_row(ordered.c.item_id, reviewer).desc(),
            ordered.c.position,
            ordered.c.pmcid,
            ordered.c.run_id,
        )
        .limit(1)
    )
    with engine.begin() as conn:
        _bound(conn)
        row = conn.execute(statement).first()
    return None if row is None else ReviewItem.model_validate_json(row.item_json)


def domains(engine: Any) -> list[str]:
    """Every domain a loaded paper is filed under, sorted, for the page's filter."""
    with engine.begin() as conn:
        _bound(conn)
        return sorted(conn.scalars(select(review_paper.c.domain).distinct()))


def topics(engine: Any, domain: str | None = None) -> list[str]:
    """Every topic a loaded paper carries, sorted, the empty one left out -- within one domain
    when given, so a reviewer who chose physics is not offered planarians."""
    statement = select(review_paper.c.topic).distinct().where(review_paper.c.topic != "")
    if domain is not None:
        statement = statement.where(review_paper.c.domain == domain)
    with engine.begin() as conn:
        _bound(conn)
        return sorted(conn.scalars(statement))


def skip_paper(engine: Any, reviewer: str | None, *, run_id: str, pmcid: str) -> None:
    """Set a paper aside for this reviewer: none of its items is offered to them again.

    Recorded, not dropped (ADR-0980), and failing closed like a decision: a skip that did not
    reach the table would offer the same paper on the next screen, and a reviewer told it was
    set aside would have been told a falsehood.
    """
    with _closed(engine) as conn:
        known = select(review_paper.c.pmcid).where(
            review_paper.c.run_id == run_id, review_paper.c.pmcid == pmcid
        )
        if conn.execute(known).first() is None:
            raise DecisionNotSaved(f"no paper {pmcid!r} in run {run_id!r}")
        conn.execute(
            insert(review_skip).values(
                reviewer=reviewer, run_id=run_id, pmcid=pmcid, skipped_at=datetime.now(UTC)
            )
        )


def open_choice(engine: Any, item_id: str, reviewer: str | None) -> Choice | None:
    """This reviewer's first step on the item, if they have taken it and not the second."""
    with engine.begin() as conn:
        _bound(conn)
        row = conn.execute(_open_row(item_id, reviewer)).first()
    if row is None:
        return None
    return Choice(bool(row.chosen_supporting), row.value_read, row.value_agreement)


def remaining(engine: Any, reviewer: str | None, preference: Preference | None = None) -> int:
    """How many items this reviewer has still to decide, within their preference if any."""
    statement = (
        select(func.count())
        .select_from(review_item)
        .where(
            _undecided(review_item.c.item_id, reviewer),
            _preferred(review_item.c.run_id, review_item.c.pmcid, reviewer, preference),
        )
    )
    with engine.begin() as conn:
        _bound(conn)
        return int(conn.execute(statement).scalar_one())


def undecided_items(
    engine: Any, reviewer: str | None, *, keep: Callable[[str], bool] | None = None
) -> list[ReviewItem]:
    """Every item this reviewer has not decided, in item-id order -- those whose id `keep` accepts,
    where one is given. The filter runs on the id before the record is parsed, so a role with a
    tenth of the items pays for a tenth; it is a draw on the id, not a `Preference`.

    For a reviewer that is handed a batch rather than one screen at a time -- the simulated
    review. Not interleaved across papers the way `next_item` is: that ordering exists because a
    person remembers the previous screen, and a model call carries nothing from one item to the
    next. Takes no `Preference` on purpose: a domain, a topic and a skip are a person's choices
    (ADR-0980), and a model that could be handed them would review a pool a person shaped.
    """
    statement = (
        select(review_item.c.item_id, review_item.c.item_json)
        .where(_undecided(review_item.c.item_id, reviewer))
        .order_by(review_item.c.item_id)
    )
    with engine.begin() as conn:
        _bound(conn)
        rows = conn.execute(statement).all()
    return [
        ReviewItem.model_validate_json(row.item_json)
        for row in rows
        if keep is None or keep(row.item_id)
    ]


def record_choice(
    engine: Any,
    item_id: str,
    *,
    reviewer: str | None,
    chosen_supporting: bool,
    value_read: str,
    time_to_decide_s: float | None = None,
    reviewer_role: ReviewerRole | None = None,
    reviewer_model: str | None = None,
    answered_by: str | None = None,
) -> None:
    """The first step: which text, and the value read from it, before the stored value is shown.

    Opens the row `record_verdict` or `record_issue` will complete. Refused -- `DecisionNotSaved`
    -- when this reviewer already has any row on the item: a second choice would either overwrite
    a verdict or stand beside one, and both are a decision the record cannot explain. Fails closed
    (ADR-0930) like every writer here.
    """
    with _closed(engine) as conn:
        _known(conn, item_id)
        if conn.execute(_any_row(item_id, reviewer)).first() is not None:
            raise DecisionNotSaved(f"{reviewer!r} has already chosen on {item_id!r}")
        stored = conn.execute(
            select(review_item.c.value, review_item.c.unit).where(review_item.c.item_id == item_id)
        ).one()
        conn.execute(
            insert(review_decision).values(
                item_id=item_id,
                reviewer=reviewer,
                chosen_supporting=chosen_supporting,
                approved=None,
                comment="",
                issue="",
                value_read=value_read,
                value_agreement=readings.compare(value_read, stored.value, stored.unit).value,
                decided_at=datetime.now(UTC),
                time_to_decide_s=time_to_decide_s,
                reviewer_role=reviewer_role.value if reviewer_role else None,
                reviewer_model=reviewer_model,
                answered_by=answered_by,
            )
        )


def record_verdict(
    engine: Any,
    item_id: str,
    *,
    reviewer: str | None,
    approved: bool,
    comment: str = "",
    time_to_decide_s: float | None = None,
    answered_by: str | None = None,
) -> None:
    """The second step: the verdict, once the stored value and conditions have been revealed.

    Completes this reviewer's open row on the item; `DecisionNotSaved` when there is none, because
    a verdict with no choice before it is the one-step decision the blind design exists to avoid.
    The time adds to the choice's, so `time_to_decide_s` is the whole item's.
    """
    with _closed(engine) as conn:
        _known(conn, item_id)
        row = conn.execute(_open_row(item_id, reviewer)).first()
        if row is None:
            raise DecisionNotSaved(f"{reviewer!r} has no open choice on {item_id!r} to judge")
        conn.execute(
            update(review_decision)
            .where(review_decision.c.id == row.id)
            .values(
                approved=approved,
                comment=comment,
                decided_at=datetime.now(UTC),
                time_to_decide_s=_added(row.time_to_decide_s, time_to_decide_s),
                answered_by=_joined(row.answered_by, answered_by),
            )
        )


def record_decision(
    engine: Any,
    item_id: str,
    *,
    reviewer: str | None,
    chosen_supporting: bool,
    approved: bool,
    comment: str = "",
    time_to_decide_s: float | None = None,
    reviewer_role: ReviewerRole | None = None,
    reviewer_model: str | None = None,
) -> None:
    """Both steps in one write, for a driver that showed the value with the texts.

    The form the first review page used, kept for the rows it wrote and the tests that read them;
    the page and the simulated review now take the two steps apart. Fails closed (ADR-0930):
    every failure becomes `DecisionNotSaved` with the cause chained, and there is no path that
    returns quietly without a row. An unknown `item_id` is a failure of the same kind, not a
    no-op: a reviewer told "saved" would have been told a falsehood.
    """
    _write_decision(
        engine,
        item_id,
        reviewer=reviewer,
        chosen_supporting=chosen_supporting,
        approved=approved,
        comment=comment,
        issue="",
        time_to_decide_s=time_to_decide_s,
        reviewer_role=reviewer_role.value if reviewer_role else None,
        reviewer_model=reviewer_model,
    )


def record_issue(
    engine: Any,
    item_id: str,
    *,
    reviewer: str | None,
    issue: str,
    time_to_decide_s: float | None = None,
    reviewer_role: ReviewerRole | None = None,
    reviewer_model: str | None = None,
    answered_by: str | None = None,
) -> None:
    """Write one raised issue, or raise. The third outcome, at either step.

    Raised before any text was chosen, it is a row with the choice and the verdict null; raised
    after the choice, it completes the open row, keeping the choice and the value read and
    leaving the verdict null -- a reviewer who says the item cannot be judged has given none.
    Either way the item is not offered to this reviewer again. Fails closed like every writer.

    Raises `ValueError` for an issue with no text. That refusal is here rather than in a caller
    because there are two callers, the page and the simulated review, and an issue row with
    nothing in it is indistinguishable from a decision that lost both its halves.
    """
    if not issue.strip():
        raise ValueError("an issue needs its text: an empty one says nothing was wrong")
    with _closed(engine) as conn:
        _known(conn, item_id)
        row = conn.execute(_open_row(item_id, reviewer)).first()
        if row is not None:
            conn.execute(
                update(review_decision)
                .where(review_decision.c.id == row.id)
                .values(
                    issue=issue,
                    decided_at=datetime.now(UTC),
                    time_to_decide_s=_added(row.time_to_decide_s, time_to_decide_s),
                    answered_by=_joined(row.answered_by, answered_by),
                )
            )
            return
        # No open row: either nothing yet, or a completed one. A second row for one reviewer
        # would read as approving and disputing at once (`tiers`), so the operation refuses it
        # as `record_choice` does.
        if conn.execute(_any_row(item_id, reviewer)).first() is not None:
            raise DecisionNotSaved(f"{reviewer!r} has already decided {item_id!r}")
        conn.execute(
            insert(review_decision).values(
                item_id=item_id,
                reviewer=reviewer,
                chosen_supporting=None,
                approved=None,
                comment="",
                issue=issue,
                decided_at=datetime.now(UTC),
                time_to_decide_s=time_to_decide_s,
                reviewer_role=reviewer_role.value if reviewer_role else None,
                reviewer_model=reviewer_model,
                answered_by=answered_by,
            )
        )


def _write_decision(engine: Any, item_id: str, **values: Any) -> None:
    with _closed(engine) as conn:
        _known(conn, item_id)
        conn.execute(
            insert(review_decision).values(item_id=item_id, decided_at=datetime.now(UTC), **values)
        )


@contextmanager
def _closed(engine: Any) -> Iterator[Any]:
    """One bounded transaction whose every failure is `DecisionNotSaved` (ADR-0930).

    The swallow the trail store performs is what this must never do -- and it is an easy
    inversion to make by accident, which is why the two modules say so in each other's direction.
    """
    try:
        with engine.begin() as conn:
            _bound(conn)
            yield conn
    except DecisionNotSaved:
        raise
    except Exception as exc:
        raise DecisionNotSaved(f"{type(exc).__name__}: {exc}") from exc


def _known(conn: Any, item_id: str) -> None:
    known_item = select(review_item.c.item_id).where(review_item.c.item_id == item_id)
    if conn.execute(known_item).first() is None:
        raise DecisionNotSaved(f"no review item {item_id!r}")


def _by_reviewer(reviewer: str | None):
    """`reviewer IS NULL` for the unsigned-in reviewer, never a comparison to a bound NULL, which
    matches nothing and would re-offer every item for ever (see `_undecided`)."""
    if reviewer is None:
        return review_decision.c.reviewer.is_(None)
    return review_decision.c.reviewer == reviewer


def _any_row(item_id: str, reviewer: str | None):
    return select(review_decision.c.id).where(
        review_decision.c.item_id == item_id, _by_reviewer(reviewer)
    )


def _open_row(item_id: str, reviewer: str | None):
    return select(review_decision).where(
        review_decision.c.item_id == item_id, _by_reviewer(reviewer), _is_open()
    )


def _is_open():
    """A row with a choice and neither a verdict nor an issue."""
    return (
        review_decision.c.approved.is_(None)
        & (review_decision.c.issue == "")
        & review_decision.c.chosen_supporting.is_not(None)
    )


def _has_open_row(item_id_column: Any, reviewer: str | None):
    return (
        select(review_decision.c.id)
        .where(review_decision.c.item_id == item_id_column, _by_reviewer(reviewer), _is_open())
        .exists()
    )


def _added(so_far: float | None, more: float | None) -> float | None:
    if so_far is None:
        return more
    return so_far if more is None else so_far + more


def _joined(so_far: str | None, more: str | None) -> str | None:
    names = [name for name in (so_far, more) if name]
    return ", ".join(dict.fromkeys(names)) or None


def _preferred(
    run_column: Any, pmcid_column: Any, reviewer: str | None, preference: Preference | None
):
    """The paper is one this reviewer asked for and has not skipped; everything, with no
    preference."""
    if preference is None:
        return true()
    wanted = [review_paper.c.run_id == run_column, review_paper.c.pmcid == pmcid_column]
    if preference.domain is not None:
        wanted.append(review_paper.c.domain == preference.domain)
    if preference.topic is not None:
        wanted.append(review_paper.c.topic == preference.topic)
    skipped_by = (
        review_skip.c.reviewer.is_(None) if reviewer is None else review_skip.c.reviewer == reviewer
    )
    skipped = select(review_skip.c.id).where(
        review_skip.c.run_id == run_column, review_skip.c.pmcid == pmcid_column, skipped_by
    )
    return select(review_paper.c.pmcid).where(*wanted).exists() & ~skipped.exists()


def _undecided(item_id_column: Any, reviewer: str | None):
    """No *completed* row for this item by this reviewer: a verdict given, or an issue raised. An
    open row -- a choice awaiting its verdict -- leaves the item undecided, and `next_item` serves
    it first.

    The `None` reviewer is a reviewer in its own right -- an unsigned-in deployment, where the
    spec says the decision is recorded with no account and nothing else differs -- so it must
    match `reviewer IS NULL` rather than be compared to a bound NULL, which matches nothing and
    would re-offer every item for ever. Written out rather than left to SQLAlchemy's implicit
    `== None`, so that a reader tidying it into a parameter sees what they are removing.
    """
    # A column rather than `literal(1)`: an untyped parameter in the select list of a correlated
    # EXISTS is the kind of thing a backend is free to refuse, and nothing here needs the constant.
    decided = select(review_decision.c.id).where(
        review_decision.c.item_id == item_id_column,
        _by_reviewer(reviewer),
        review_decision.c.approved.is_not(None) | (review_decision.c.issue != ""),
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
        "domain": result.fingerprint.scope or DEFAULT_DOMAIN,
        "topic": paper.topic,
        "csl_json": paper.csl_json,
    }


def _item_row(item: ReviewItem, *, question: str, run_id: str, now: datetime) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "run_id": run_id,
        # The item's own question, not the run's: a harvested run asks none, and each of
        # its items is named by the quantity it holds.
        "question": item.question or question,
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
        "property": item.claim.property,
    }
