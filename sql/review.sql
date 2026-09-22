-- The review store: the papers a run touched, the items a reviewer is shown, and what they decided.
--
-- Three tables of their own, in the same Neon database as `trail` and `accounts`, on the `dev`
-- branch for development and a fresh branch once there are real reviewers. They are not rows in
-- `trail`: that is an append-only event log with a `detail` blob and a writer that swallows every
-- failure, and a decision is a first-class record with a foreign key whose writer must fail closed.
-- Both differences are the point (ADR-0930); one table would have to lose one of them.
--
-- `bionumbers.store` declares the same columns as SQLAlchemy Core tables and is the only writer.
-- **This file and that module must agree**, and nothing enforces it at runtime — a column added in
-- one alone passes every test and is missing where it matters — so `tests/test_bionumbers_store.py`
-- parses this file and compares the names. Keep one column per line for that reason.
--
-- The three JSON columns are `text`, not `jsonb`, and that is a decision rather than an oversight.
-- They hold `model_dump_json()` output and are read back through `model_validate_json`, never
-- queried by key, so `jsonb` would buy indexing nobody uses; and Core's `insert()` binds a Python
-- string as `text`, which Postgres will not assign to a `jsonb` column without an explicit cast
-- that a Core insert cannot express. The trail pays that cast in hand-written SQL; here there is
-- nothing to pay it for.
--
-- Nothing in this file is destructive: every statement is `if not exists`, so it is safe to run
-- against a database that already holds decisions. Additive changes go at the end as
-- `alter table ... add column if not exists`, the way `trail` gained `user_role`. Keep one column per
-- line, and table constraints on lines of their own after the columns.

-- One row per article per run, whatever its ending — `NOTHING_TO_EXTRACT` and `UNREADABLE` are
-- findings about the literature and are kept, not dropped. Keyed by run *and* article: two
-- questions asked of the same paper are two extractions with two states, and keyed by article
-- alone the second was silently skipped on load.
--
-- `licence` is here so a reader can see on what terms the paper's text was allowed in at all. A
-- paper whose licence is `UNLICENSED` may still have this row: it is bibliography and a state.
-- `bionumbers.store.load_run` refuses to write any *item* for it, because an item carries the
-- paper's own sentences and those are never written past the disk cache.
create table if not exists review_paper (
    run_id           text not null,
    pmcid            text not null,
    question         text not null,
    pmid             text not null default '',
    doi              text not null default '',
    title            text not null default '',
    year             integer,
    licence          text not null default 'UNLICENSED',
    state            text not null,
    reason           text not null default '',
    spend_usd        double precision not null default 0,
    spend_json       text not null default '{}',
    fingerprint_json text not null default '{}',
    loaded_at        timestamptz not null default now(),
    primary key (run_id, pmcid)
);

-- One row per screen. `item_json` is the whole `ReviewItem` and is what the page renders from; the
-- columns beside it are the ones a later analysis groups by — kind, type, question, run — so that
-- measuring distractor difficulty does not mean parsing every blob. Where a column and the JSON
-- disagree, the JSON is the one the reviewer saw.
--
-- `second_kind` and `distractor_type` are recorded and never shown (ADR-0920): they are what lets
-- the rebuild separate attention from ambiguity, and showing them would tell the reviewer the
-- answer.
create table if not exists review_item (
    item_id         text primary key,
    run_id          text not null,
    question        text not null,
    pmcid           text not null,
    claim_id        text not null,
    value           text not null,
    unit            text not null default '',
    claim_kind      text not null,
    second_kind     text not null,
    distractor_type text,
    item_json       text not null,
    created_at      timestamptz not null default now(),
    foreign key (run_id, pmcid) references review_paper (run_id, pmcid)
);

-- What one reviewer decided about one item. `reviewer` is the signed-in account's address, and
-- null where no identity is configured — which `user-identity` already allows and this task
-- repeats: the decision is recorded with no account and nothing else about it differs.
--
-- There is deliberately **no** unique constraint on `(item_id, reviewer)`. Postgres treats nulls as
-- distinct, so it would hold for a signed-in reviewer and quietly not hold for an anonymous one,
-- and a rule that applies to some rows reads as though it applies to all. `store.next_item` is the
-- enforcement, and it treats both the same way.
--
-- `time_to_decide_s` is nullable because the page may not have a start time to subtract from — a
-- reloaded tab, a session resumed. It is here because it costs one column and the rebuild's
-- attention analysis cannot be reconstructed later from rows that never carried it.
create table if not exists review_decision (
    id                bigserial primary key,
    item_id           text not null references review_item (item_id),
    reviewer          text,
    chosen_supporting boolean not null,
    approved          boolean not null,
    comment           text not null default '',
    decided_at        timestamptz not null default now(),
    time_to_decide_s  double precision
);

-- Serving the next item asks, per item, whether this reviewer has a row for it. That is the query
-- every page load makes, and it is the only one whose latency a person waits on.
create index if not exists review_decision_item_reviewer on review_decision (item_id, reviewer);

-- How far a run has got, without reading any paper text.
--
-- select p.state, count(distinct i.item_id) as items, count(d.id) as decisions
-- from review_paper p
--   left join review_item i on i.run_id = p.run_id and i.pmcid = p.pmcid
--   left join review_decision d on d.item_id = i.item_id
-- group by p.state order by items desc;

-- Where reviewers disagree with the extractor: the disapprovals, newest first. These are the rows
-- worth reading by eye — an unfair distractor and a wrongly quoted claim both land here.
--
-- select d.decided_at, d.reviewer, d.chosen_supporting, d.comment, i.value, i.unit, i.pmcid
-- from review_decision d join review_item i on i.item_id = d.item_id
-- where not d.approved order by d.decided_at desc;
