# ADR-0900: Extraction is a fixed pipeline with one model call per paper, not an agent loop

- **Status:** proposed
- **Date:** 2026-09-18
- **Pull request:** not yet opened — branch `feat/validator-prototype`

## Context

Stub. The validator prototype (`add-validator-prototype`) turns a property question into reviewed
numbers. The ask agent's shape — a tool-using loop over a retrieval index — was the obvious
template. The loop-engineering brief's rule is "if you can list every step, build a workflow, not a
loop", and here every step is known in advance: discover, fetch, read, extract, check, retry once,
choose a second text, store. A paper fits in one context, and chunking loses the Methods-to-Results
link that the scientist report identifies as the whole difficulty.

## Decision

Discovery → fetch → read → **one** structured extraction call → mechanical quote check → **one**
bounded retry → one second-text call → store. The paper sits in the system block under
`cache_control`; the extractor has no tools. See `design.md` D1 of the change.

## Trade-off accepted

To be completed with the options rejected and the first run's state distribution (task 9.2).
