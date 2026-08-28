# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation upkeep — project override

This project follows the user-level documentation-upkeep conventions with one substitution: there is no `docs/REQUIREMENTS.md`. The behavioral spec — what the app must do, kept implementation-agnostic — lives in **`openspec/specs/`**, maintained through the OpenSpec workflow rather than as a hand-written document. Write behavioral requirements as spec deltas on a change; they are promoted into `openspec/specs/` when the change is archived. See [ADR-0030](docs/decisions/0030-openspec-specs-as-the-behavioral-record.md). Wherever the conventions say to update `docs/REQUIREMENTS.md`, update the OpenSpec specs instead.

## Parallel branches and ADR numbers

Two branches that each number ADRs from the current highest id will both claim the same numbers, and the second to merge conflicts. Before parallel work starts, give each branch a disjoint block.

**This file is the allocation's source of truth.** Recording it only in each change's `tasks.md` is what let the blocks drift: no branch can see another's copy, so a change that outgrows its block updates its own note and nothing else, and the next branch allocates against a stale ceiling. Keep the block in the change's `tasks.md` too — that is where someone implementing reads it — but reconcile against this table, and widen a block here first.

| Change | Block |
|---|---|
| `add-grounding-validator` | `0040`–`0090` |
| `add-ask-agent` | `0100`–`0190` |
| `add-corpus-ingestion` | `0200`–`0250` |

`0000`–`0030` exist as files; everything above is reserved, not yet written. `add-ask-agent` was originally given `0100`–`0150` and has since planned `0160` and `0170`, which is why its block is wider here than in its own `tasks.md` — that note and `add-grounding-validator`'s both still say `0150` and should be corrected when each next merges.

## Running the tests

`pytest` is offline by default: `addopts = "-m 'not network'"` deselects the `network` marker, so a green run may never have executed the tests that hit a real service. Run those explicitly with `pytest -m network`.

## Testing the tests

Two techniques, both scoped by consequence: spend the effort where a silent bug would be *unfalsifiable to the user* — parsers, retrieval, provenance — and not on drivers, rendering or config, where a bug announces itself the moment someone looks.

**Fault seeding** is the default, and the user-level conventions cover it: seed one realistic defect into a *copy* of the source and check that exactly the right test fails.

**Mutation testing** is the automated complement, and finds what seeding structurally cannot — code no test can distinguish. Run it at the end of a task, over the module just touched, via the **`mutation-test-module`** skill, which carries the recipe and this project's three setup gotchas. Not over the whole package (2,000+ mutants, hours) and never as a CI gate.

Its yield decays, and that is expected rather than a failure: a module's first run finds real gaps, later runs on settled code return mostly equivalent mutants. Once two or three consecutive runs turn up nothing but string-sentinel and default-argument survivors, stop running it on that area and reach for it again only when the code changes substantially. It is a tool for new and reworked code, not a standing gate.
