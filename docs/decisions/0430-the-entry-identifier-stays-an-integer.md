# ADR-0430: The entry identifier stays an integer, the corpus key changes, and how a widening would work

- **Status:** accepted
- **Date:** 2026-09-01
- **Pull request:** _pending — feat/scinumbers-citation-form_

## Context

The identifier field was `bnid` — BioNumbers' name for it — in a package no longer
named for that database, and in a project whose second corpus will not be
BioNumbers. Two questions had to be answered together: what the field is called, and
what type it holds.

On the type, the case for widening to `str` now was real. A field typed `int` cannot
hold `CHEBI:15377`, a DOI, a UUID, or an identifier with leading zeros; once there
are two sources, a bare `100002` is ambiguous and wants either a `(source, id)` pair
threaded everywhere or a `bionumbers:100002` token; and `int(raw["bnid"])` *raises*
on a non-numeric identifier, so such a corpus is unloadable rather than degraded.
Widening is also cheapest during a rename that touches these lines anyway.

Against it: no second source exists, and none is close. The project's own standing
rule is to build nothing speculative. The runtime guard `int()` provides at the
corpus boundary would be lost — `str()` accepts `""` — and this repository runs no
type checker, so nothing static would replace it.

## Decision

**The identifier stays `int`, and the field is renamed `entry_id`.** Speculative
generality loses to a rule this project already holds; the widening is recorded here
instead of built.

**The corpus key changes too**, so `raw["bnid"]` does not survive in a package that
is otherwise free of the source's vocabulary. A corpus written by an older ingester
is **refused by name** (`CorpusOutOfDate`, a `CorpusUnavailable` subclass) with a
sentence saying what changed and what to do. A read-only compatibility alias was
rejected: it is a branch that would outlive its usefulness and keep two wire formats
quietly alive. The refusal is not optional, because `autobuild` never rebuilds a
corpus that exists (`is_ready`), so such a file reaches the loader on every start
with nothing in the app able to repair it.

**A widening to `str` would touch exactly four places**, and this is the list:

1. `corpus._entry` — the `int()` coercion, which is also the only runtime check that
   an identifier is well formed. Widening must replace it with an explicit
   non-empty check, or `""` becomes a valid key and `repo.get("")` starts succeeding.
2. `repository._by_id` — the index, and the duplicate-identifier check built on it.
3. `entries_table.COLUMNS` — the `ID` column's width is `7`, tuned to six digits.
4. **Both** citation parsers: `citations._identifier`'s coercion, and
   `bionumbers.py`'s digit-based reading. The delimited answer form itself needs no
   change — that is what ADR-0410 bought — but tolerance means the source's
   digit-shaped rules are still reachable from the answer path.

## Trade-off accepted

**Every corpus already on disk stops loading.** The user's 14,294-entry corpus is
refused until rebuilt, which needs the export re-downloaded if it is no longer
around. Accepted because the project is pre-release with one user and a rebuild is
about a minute; not accepted silently, which is what the refusal message is for.

**The default test suite cannot see this.** It runs on the six-entry fixture, whose
keys changed in the same commit, so it goes green while every real corpus is broken.
Only `-m corpus` against a corpus built by the *old* ingester catches it. That check
was run by hand against the real corpus, and the refusal has its own tests.

**Trace records change shape.** `bnid` and `bnids` become `entry_id` and
`entry_ids`, so `logs/trace.jsonl` written before this is read differently by
anything parsing those keys.

**The widening gets more expensive the longer it waits.** Each new consumer of the
corpus contract adds a place to change. The list above is the mitigation, and it is
only worth anything if it is kept true.
