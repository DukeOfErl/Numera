# ADR-0220: JSONL only; the parquet output and `pyarrow` go

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _(not yet opened — branch `feat/corpus-ingestion`)_

## Context

The first-pass ingester wrote the corpus twice: as JSONL and as parquet, the latter pulling in
`pyarrow`. The parquet file had one purpose there — a canonical columnar form for a database that was
never chosen.

Nothing in this project reads it. `bionumbers_ask.corpus.load` reads JSONL line by line; the
grounding validator does not read the corpus at all. So the parquet output would be a second 27 MB
artefact with no reader, a substantial dependency to install for every reader of the corpus, and a
second serialization path.

That last point is the one that decided it. The output has to satisfy a contract owned by another
branch — twelve keys with exact types, where an absent scalar emitted as `""` rather than `null`
blanks out every range-only entry at the consumer. With two writers, the JSONL can satisfy that
contract while the parquet has drifted, and nothing compares them. The drift is silent in the
direction that matters.

## Decision

Write JSONL and nothing else. Drop `pyarrow` from the dependency list; the `ingest` extra needs only
`pydantic`.

The corpus is written to `<destination>.partial` and renamed into place after the last record, so a
failed or interrupted run leaves the previous corpus or nothing at all — never a truncated one.

## Trade-off accepted

**Analytical reads over the corpus get slower and clumsier.** A columnar file is the right shape for
"what is the distribution of units across 14,294 entries", and answering that now means parsing
14,294 JSON objects. Anyone wanting columnar access has to convert, and the conversion is theirs to
keep correct.

**A future consumer that wants parquet will have to re-add it**, and at that point the drift risk
above becomes real and needs a mitigation this ADR does not provide — most likely generating one
format from the other rather than writing both from the records.

In exchange there is one output path, one place the contract can be got wrong, and one artefact to
account for in the manifest. The dependency footprint of building a corpus drops to a single package.
