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
| `add-corpus-ingestion` | `0200`–`0250` — `0200`, `0210`, `0220`, `0230`, `0240` written |

**This table is the authority, not a scan of `docs/decisions/`.** A scan cannot see uncommitted ADRs on another branch: `git ls-tree` reads committed trees, and each branch is checked out in its own worktree, so a number can be spent and still invisible from here. At the time of writing `add-ask-agent` has written `0100`–`0180` — uncommitted — leaving `0190` as the last number in its block. Never conclude a number is free because no file for it turns up.

**Allocate by creating the file.** Copy the template to the number you are claiming and commit that stub early, rather than writing the ADR at the end of the change. A ceiling only holds if claiming the number and writing the file are the same step; a block widened in a note that only your own branch reads is how the last drift happened. Reconcile each change's `tasks.md` against this table when it merges.

## Running the tests

`pytest` is offline by default: `addopts = "-m 'not network'"` deselects the `network` marker, so a green run may never have executed the tests that hit a real service. Run those explicitly with `pytest -m network`.

## Architecture

Three work packages, three packages under `src/`, one dependency extra each, so no two branches edit
the same source tree: `bionumbers_ingest` (`ingest`), `bionumbers_ask` (`ask`), `bionumbers`
(`validator`). Only the ingester exists on this branch.

`bionumbers_ingest` is a **pipeline**, and the shape is load-bearing: the two ends are the only
modules that know a file format, and nothing between them knows either.

| Module | Role |
|---|---|
| `parsing/html_table.py` | source format in — streams `<tr>` rows, preserving raw inner HTML |
| `cleaning.py` | one raw row → one record; the only place that unescapes or strips |
| `model.py` | the record, plus `EXPECTED_HEADERS` |
| `validation.py` | the run report |
| `provenance.py` | source fingerprint and manifest |
| `io.py` | JSONL out, renamed into place on success |
| `ingest.py` | wires the pipeline together |
| `cli.py` | the command |

Diagram: [`docs/diagrams/architecture.md`](docs/diagrams/architecture.md).

Four things about it that reading one module will not tell you:

- **The reader preserves raw HTML deliberately.** The export's injected markup arrives
  HTML-escaped, so a reader that unescaped would hand cleaning a live tag and destroy the evidence of
  which form the source used. Unescaping happens once, in `cleaning`, before markup is stripped.
- **An angle bracket is not evidence of markup.** The export contains exactly one HTML element and
  uses `<` as a less-than sign in prose. A tag is recognised only by a real HTML element name.
- **Records are buffered, not streamed, between cleaning and the writer**, because each carries a
  digest of the whole source, which is unknown until the last byte. Roughly 70 MB; ADR-0240.
- **Two booleans are the contract with `add-ask-agent`**, not the flag names: `range_fused` and
  `range_qualified`. `parse_flags` is cleaning's own vocabulary and may change. ADR-0230.

## Testing the tests

Two techniques, both scoped by consequence: spend the effort where a silent bug would be *unfalsifiable to the user* — parsers, retrieval, provenance — and not on drivers, rendering or config, where a bug announces itself the moment someone looks.

**Fault seeding** is the default, and the user-level conventions cover it: seed one realistic defect into a *copy* of the source and check that exactly the right test fails.

**Mutation testing** is the automated complement, and finds what seeding structurally cannot — code no test can distinguish. Run it at the end of a task, over the module just touched, via the **`mutation-test-module`** skill, which carries the recipe and this project's three setup gotchas. Not over the whole package (2,000+ mutants, hours) and never as a CI gate.

Its yield decays, and that is expected rather than a failure: a module's first run finds real gaps, later runs on settled code return mostly equivalent mutants. Once two or three consecutive runs turn up nothing but string-sentinel and default-argument survivors, stop running it on that area and reach for it again only when the code changes substantially. It is a tool for new and reworked code, not a standing gate.
