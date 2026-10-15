# ADR-1520: Extraction is a fixed pipeline with one model call per paper, not an agent loop

- **Status:** accepted (first live run 2026-09-18/19, below)
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

The validator prototype (`add-validator-prototype`) turns a property question into reviewed
numbers. The ask agent's shape — a tool-using loop over a retrieval index, with middleware for spend
and retries — was the obvious template, and the project already knows how to build and test it.

Against it: every step of this job is known in advance. Discover, fetch, read, extract, check, retry
once, choose a second text, store. The loop-engineering brief's rule is "if you can list every
step, build a workflow, not a loop", and its five failure modes (no exit, context rot, thrashing,
reward hacking, fake success) are mostly impossible for a pipeline with a fixed step count. A paper
of 40–150 kB fits in one context. And the scientist report's central finding is that the
difficulty is the link between Methods (conditions) and Results (values), pages apart — which is
exactly what chunking or per-section retrieval loses.

Options on the table:

1. A tool-using agent over the paper: `find`, `read_section`, `quote` tools, loop until done.
2. Chunked map-reduce: extract per section, merge.
3. One structured call with the whole paper in a cached prefix, a mechanical check, one retry.

## Decision

Option 3. Discovery → fetch → JATS reader → **one** structured-output extraction call → mechanical
quote check → **one** bounded retry with the failures named → **one** second-text call on the same
cached paper → JSONL → Postgres. The extractor has no tools. The paper sits in the first system
block under `cache_control` so the retry and the second-text call read it at the cached rate. Spend
is projected before each of the up-to-three calls and a call that would cross the $2 per-paper
ceiling is not made (D6).

## Trade-off accepted

*Given up:* the agent's ability to go and look again. If the extractor misses a value, nothing
re-reads the paper; the paper ends `NOTHING_TO_EXTRACT` and the miss is a false negative the
rebuild can measure but this version cannot recover. Also given up: reuse of the ask app's
`SpendGate`, which is LangChain middleware; the projection-then-report shape is kept, the code is
not.

*Bought:* a cost that is bounded by construction (three calls, one paper each), no exit problem,
no context rot, and a failure surface small enough that the two loop failures that *can* occur here
— reward hacking of the quote check, and fake success — each have a named counter (the second text
and the reviewer; the checker as arbiter rather than the model's own report).

*Not decided here:* whether one call is enough for long papers with many values. `MAX_TOKENS` is
8,000; a truncated answer is a `FAILED` paper, not a partial one, and the run summary will show how
often that happens.

## What the first live run showed (2026-09-18/19)

Question "doubling time", organism *Escherichia coli*, Europe PMC search restricted to Results and
Table sections, 2015 onwards, twelve open-access papers, Opus 4.7 through OpenRouter.

| | |
|---|---|
| States | `CLAIMS_FOUND` 2, `NOTHING_TO_EXTRACT` 10, `FAILED` 0 after the fixes below (1 before) |
| Spend | $2.40 for the twelve; $0.11–0.47 per single-call paper; $0.91 for the paper with 11 claims and 12 calls |
| Caching | confirmed by the usage blocks: 81 % of input tokens read from cache on the 12-call paper, 7 % over the run because ten papers needed one call |
| Items | 12 review items from 12 claims; 11 with an adjacent-condition distractor from the same table, 1 with a cited-value distractor |

What it corrected in the pipeline, each now a test: a range over conditions may span more than
two; a refused output is still paid for; the checker reduces a rendered table cell to its cell and
requires the quote to *state the value* (two claims had quoted "nearly 200-fold" for values of
346 h and 693 h that were the model's arithmetic); the output cap is 16,000 tokens because the
correction call, which replays the first answer, was cut at 8,000.

What it did not settle, and is left for the rebuild: discovery precision. Ten of the twelve
papers were about other organisms that mention *E. coli* in passing; the query design, not the
pipeline, decides that.
