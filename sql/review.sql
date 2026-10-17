-- The review store: the papers a run touched, the items a reviewer is shown, and what they decided.
--
-- Three tables of their own, in the same Neon database as `trail` and `accounts`, on the `dev`
-- branch for development and a fresh branch once there are real reviewers. They are not rows in
-- `trail`: that is an append-only event log with a `detail` blob and a writer that swallows every
-- failure, and a decision is a first-class record with a foreign key whose writer must fail closed.
-- Both differences are the point (ADR-0930); one table would have to lose one of them.
--
-- `numera_validator.store` declares the same columns as SQLAlchemy Core tables and is the only writer.
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
-- `numera_validator.store.load_run` refuses to write any *item* for it, because an item carries the
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
    domain           text not null default 'biology',
    topic            text not null default '',
    -- The bibliographic record as one CSL-JSON item (ADR-1750): authors, journal, volume, issue,
    -- pages, date and identifiers, read from the paper's front matter. The application formats
    -- the citation a reader sees from it. Empty until `numera-validator upgrade-store --data` fills it
    -- from the cached full text; nothing here can, since no row holds the authors.
    csl_json         text not null default '',
    primary key (run_id, pmcid)
);
alter table review_paper add column if not exists csl_json text not null default '';

-- The same two for a database that predates them (ADR-0980). `domain` is the harvest scope the
-- paper was read under, in `fingerprint_json` as `scope`; runs from before scopes are biology.
alter table review_paper add column if not exists domain text not null default 'biology';
alter table review_paper add column if not exists topic text not null default '';
-- ... and filled, as `store.upgrade` fills them for SQLite: a paper the loader filed before the
-- columns existed sits at the default, which would show a physics harvest under biology.
update review_paper
   set domain = fingerprint_json::json ->> 'scope'
 where coalesce(fingerprint_json::json ->> 'scope', '') <> ''
   and domain <> fingerprint_json::json ->> 'scope';
update review_paper p
   set topic = i.topic
  from (
        select distinct on (run_id, pmcid) run_id, pmcid,
               coalesce(item_json::json -> 'paper' ->> 'topic', '') as topic
          from review_item
       ) i
 where p.run_id = i.run_id and p.pmcid = i.pmcid and p.topic = '' and i.topic <> '';

-- A paper a reviewer set aside — "not my field" — and is not offered to them again. Kept rather
-- than dropped: a paper nobody wanted is a finding about the pool. Only a person skips; the
-- simulated reviewers never read this table.
create table if not exists review_skip (
    id         bigserial primary key,
    reviewer   text,
    run_id     text not null,
    pmcid      text not null,
    skipped_at timestamptz not null default now(),
    foreign key (run_id, pmcid) references review_paper (run_id, pmcid)
);

-- One row per screen. `item_json` is the whole `ReviewItem` and is what the page renders from; the
-- columns beside it are the ones a later analysis groups by — kind, type, question, run — so that
-- measuring distractor difficulty does not mean parsing every blob. Where a column and the JSON
-- disagree, the JSON is the one the reviewer saw.
--
-- `second_kind` and `distractor_type` are recorded and never shown (ADR-1540): they are what lets
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
    -- The entry's property as a reader is shown it (ADR-1700): the harvest's "measure of object"
    -- name, or the question a questioned run asked. Written on load; for older items by
    -- `bionumbers name-properties`, never into item_json, which stays what the reviewer saw.
    property        text not null default '',
    foreign key (run_id, pmcid) references review_paper (run_id, pmcid)
);
alter table review_item add column if not exists property text not null default '';

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
--
-- A decision is taken in two steps (ADR-0970), on one row. First the reviewer chooses a text and
-- writes the value they read from it, *before* the stored value is shown: `chosen_supporting` and
-- `value_read` are set, `approved` is null — an *open* row, and the item is still theirs to
-- finish. Then the stored value and conditions are revealed and they approve or disapprove:
-- `approved` is set and the row is complete. `value_read` is the one figure here the extractor's
-- answer cannot have steered, and the reviewer's agreement with the stored value is read by
-- comparing the two.
--
-- A reviewer may raise an issue instead at either step: the item cannot be judged as it stands.
-- `issue` holds the text and `approved` stays null; `chosen_supporting` is null if no text had
-- been chosen yet. A verdict is never stored beside an issue. `numera_validator.store` has one writer
-- per step and no other way in; there is no check constraint, since one cannot be added to a
-- deployed table by an idempotent statement and a rule only fresh databases enforce reads as one
-- they all do.
--
-- `answered_by` is the model the provider says answered, where it differs from `reviewer_model`:
-- a router names itself in the request and the routed model in the reply. Null for a person.
-- `value_agreement` is how `value_read` stands to the stored value — MATCHES,
-- SAME_NUMBER_DIFFERENT_UNIT, DIFFERS or UNREADABLE (`numera_validator.readings`) — computed when the
-- choice is written, so a person's reading and a model's are compared the same way.
--
-- `reviewer_role` is the rung of the trust ladder the reviewer stands on (`AI`, `STUDENT`,
-- `SCIENTIST`, `SENIOR_SCIENTIST`), null where none was recorded. `reviewer_model` is the model id
-- when a model decided, null for a person. **A row with a model and a role other than `AI` is a
-- simulated review** — a model standing in for a person of that role (ADR-0960) — and any figure
-- drawn from such rows has to say so. An entry's trust tier is read off these rows, never stored.
create table if not exists review_decision (
    id                bigserial primary key,
    item_id           text not null references review_item (item_id),
    reviewer          text,
    chosen_supporting boolean,
    approved          boolean,
    comment           text not null default '',
    decided_at        timestamptz not null default now(),
    time_to_decide_s  double precision,
    issue             text not null default '',
    reviewer_role     text,
    reviewer_model    text,
    value_read        text not null default '',
    answered_by       text,
    value_agreement   text
);

-- The same, for a database created before the issue outcome and the reviewer's role existed.
alter table review_decision add column if not exists issue text not null default '';
alter table review_decision add column if not exists reviewer_role text;
alter table review_decision add column if not exists reviewer_model text;
alter table review_decision alter column chosen_supporting drop not null;
alter table review_decision alter column approved drop not null;
alter table review_decision add column if not exists value_read text not null default '';
alter table review_decision add column if not exists answered_by text;
alter table review_decision add column if not exists value_agreement text;

-- Serving the next item asks, per item, whether this reviewer has a row for it. That is the query
-- every page load makes, and it is the only one whose latency a person waits on.
create index if not exists review_decision_item_reviewer on review_decision (item_id, reviewer);

-- BioNumbers' own entries as the curated tier (ADR-1510): measured, referenced, and with nothing
-- in the entry itself that gives cause for doubt — no fused or one-sided range, a readable unit,
-- no "rule of thumb". Shown beside harvested entries at the top of the trust order. Replaced whole
-- on every load by `numera-validator curate`: no decision points at a curated entry. The corpus these
-- come from is an external input with unresolved licensing; this table is a copy of part of it.
create table if not exists curated_entry (
    entry_id    integer primary key,
    property    text not null,
    organism    text not null default '',
    value       double precision,
    range_low   double precision,
    range_high  double precision,
    units       text not null,
    approximate boolean not null default false,
    reference   text not null default '',
    pubmed_id   text not null,
    method      text not null,
    comments    text not null default '',
    loaded_at   timestamptz not null default now()
);

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

-- What each rung of the ladder has said about each item. `simulated` is the label a figure built
-- on this must carry.
--
-- select d.item_id, d.reviewer_role, d.reviewer_model,
--        d.reviewer_model is not null and d.reviewer_role <> 'AI' as simulated,
--        d.approved, d.chosen_supporting, d.issue
-- from review_decision d order by d.item_id, d.decided_at;
