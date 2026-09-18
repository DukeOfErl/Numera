# ADR-0900: Extraction is a fixed pipeline with one model call per paper, not an agent loop

- **Status:** proposed — becomes *accepted* with the first live run's state distribution (task 8.2)
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
