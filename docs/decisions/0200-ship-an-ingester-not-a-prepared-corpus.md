# ADR-0200: Ship an ingester, not a prepared corpus

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _(not yet opened — branch `feat/corpus-ingestion`)_

## Context

The ask agent reads a JSONL corpus of biological quantities. That corpus is derived from the
published BioNumbers export, whose licensing is unresolved, so it cannot be committed to this
repository — the constraint recorded as ADR-0170 on `feat/ask-agent`.

Until now the only way to give a reviewer a runnable corpus was to send them a prepared JSONL out of
band. That is awkward, it makes the corpus a thing only its author possesses, and passing the file
around is itself a quiet act of redistribution of data this project has no licence to redistribute.

The ingestion code already exists. It was written against the real 27 MB export and the quirks it
actually contains, in a private first-pass repository, and has produced a working corpus.

Three options were on the table:

1. **Commit the corpus.** Rejected outright — it is the redistribution the licensing forbids, and
   git history is permanent, so the mistake could not be taken back.
2. **Keep handing the file over privately.** Rejected. It does not scale past one author, and it
   leaves nobody able to verify that the corpus they were given is the corpus the code produces.
3. **Ship the ingester.** The reader fetches the public export themselves and builds the corpus
   locally.

## Decision

Ship the ingester in this repository, as `src/bionumbers_ingest/` with a `bionumbers-ingest`
console script and an `ingest` extra. Nothing derived from the export is committed: `data/` is
ignored, covering both the fetched source and every corpus and manifest built from it.

The port drops the first-pass repository's parquet output (ADR-0220) and pins its JSONL to the
contract `bionumbers_ask.corpus.load` actually enforces.

Two of the original's defaults are inverted, because both produce a corpus that looks complete and
is not: the whole file is processed rather than a 200-row sample, and the output file appears only
after a completed run rather than being written incrementally.

## Trade-off accepted

**Nobody can run the agent without first doing the fetch.** That is a real cost and it falls on
every new reader: clone, fetch a 27 MB file from a third-party site that may move or change, then
run the ingester before anything works. A committed corpus would have made the repository
self-contained and the agent runnable in one step.

The fetch also makes the corpus reproducible only as far as the source is stable. Two readers who
fetch on different days may build different corpora, and the export carries no version or date of
its own — which is why every run writes a provenance manifest and stamps each record with a digest
of the file it came from (ADR-0240). Without that, two corpora could not be told apart or dated.

In exchange, nothing unlicensed enters the repository or its history, the corpus stops being a
private artefact, and the transformation from published source to corpus becomes reviewable code
rather than an undocumented step someone once ran.
