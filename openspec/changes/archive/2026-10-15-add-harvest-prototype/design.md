## Context

The validator pipeline (ADR-1520) is a fixed sequence: fetch, read the JATS into passages, one
structured extraction call with the paper as a cached prefix, a mechanical quote check, one retry,
one second-text call per claim. Harvest reuses all of it. What it changes is the first paragraph of
the instruction and the user turn — a scope where the question was — plus a bound on claims.

## Goals / Non-Goals

**Goals:** enough harvested entries, in four domains, for a demo of the store and its trust order;
a curated tier to stand at the top of that order; records that say what produced each entry.

**Non-Goals:** the ask agent over the store, the dashboards, the simulated review (its own
change), a controlled vocabulary of property names, and any parsing of value strings into numbers.

## Decisions

- **One instruction, one scope per domain (ADR-1500).** Alternatives: one broad scope (asks a
  biology paper for transition temperatures), or an instruction per domain (forks the quoting rule
  four ways). The scope is data in the user turn, so the cached paper prefix is shared.
- **The domain lives on the fingerprint**, not in a new column: it is part of what produced a
  claim, it travels with every claim into the store's JSON, and no schema change is needed.
- **The curated tier is a table of its own (ADR-1510)**, not review items: a BioNumbers entry has
  no quote from a paper to show a reviewer. Its admission rule leans to refusal, because a wrong
  entry at the top of the trust order costs more than a missing one.
- **The licence of a hand-chosen paper comes from the index.** Discovery already prefers the
  index's record; harvest had none, and six of twenty CC papers stated their licence in prose.
- **The answering model is read from the provider's response**, because routers and dated builds
  answer under names other than the one requested.

## Risks / Trade-offs

- [The chemistry and physics scopes are written from a handful of papers] → recorded in ADR-1500;
  revisit after the first runs in each domain.
- [The instruction's condition fields are biological] → physics claims name their own conditions;
  nothing normalises them yet.
- [The doubt words for the curated tier are narrow] → a curator's doubt phrased otherwise passes;
  the rule checks only that the record does not itself admit doubt.
- [`curated_entry` holds a copy of corpus entries whose licensing is unresolved] → the database is
  local or private; sharing it is a decision for Yoav.

## Migration Plan

`sql/review.sql` gains `create table if not exists curated_entry`, safe on a database with
decisions. Old harvested runs read as biology. No rollback beyond dropping the table.
