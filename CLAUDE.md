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
| `add-ask-agent` | `0100`–`0190`, `0260`–`0290` |
| `add-corpus-ingestion` | `0200`–`0250` — all written |
| `add-corpus-autobuild` | `0300`–`0340` |
| `rename-to-scinumbers` | `0400`–`0450` |

**This table is the authority, not a scan of `docs/decisions/`.** A scan cannot see uncommitted ADRs on another branch: `git ls-tree` reads committed trees, and each branch is checked out in its own worktree, so a number can be spent and still invisible from here. `add-ask-agent` has written `0100`–`0190` and holds a second range, `0260`–`0290`, because its first block ran out while the change was still open. A block is extended rather than renumbered: the ADRs already written are referenced from code comments and commit messages, and renumbering would break every one of those references to buy contiguity that nothing needs. Its first block was also uncommitted for two sessions, which is how a scan came to report those numbers as free. Never conclude a number is free because no file for it turns up.

**Allocate by creating the file.** Copy the template to the number you are claiming and commit that stub early, rather than writing the ADR at the end of the change. A ceiling only holds if claiming the number and writing the file are the same step; a block widened in a note that only your own branch reads is how the last drift happened. Reconcile each change's `tasks.md` against this table when it merges.

**Write each ADR with the change that makes the decision, never as a batch at the end.** A task
list that defers all of them to a documentation group produces retroactive ADRs, and by then the
options that were rejected -- the part worth recording -- are gone, and what survives is a
description of the code.

## Architecture

Three work packages, three packages under `src/`, one dependency extra each, so no two branches edit
the same source tree: `bionumbers_ingest` (`ingest`), `scinumbers_ask` (`ask`), `bionumbers`
(`validator`). The ingester and the ask agent are both here; the validator is not yet.

Diagrams — including the agent's graph generated from the compiled object — are in
`docs/diagrams/architecture.md`. Regenerate that graph whenever middleware changes.

**Ports and adapters.** `agent.py` emits events (`events.py`) and accepts a
question; it never touches an interface and never blocks for input. `cli.py` and
`web.py` are adapters over it, and the evaluation harness will be a third. The
agent takes no parameter naming its caller, so it cannot behave one way for a
person and another for a harness (ADR-0110).

**The dependency direction is the one rule with teeth.** Adapters may reach into
the core; the core may not reach back. Nothing in Python enforces this — an
`import streamlit` in the tool layer would run perfectly — so
`tests/test_driver_independence.py` asserts it over the source. `entries_table.py`
and `messages.py` are shared *by* the drivers and count as presentation, which is
why a rule both the table and the model need (the implausible-span test) lives on
`Entry` rather than in the table.

| Module | Holds |
|---|---|
| `agent.py` | The graph, the system prompt, the middleware list, the event stream |
| `events.py` | The port: everything the agent emits, and the one command it takes |
| `tools.py` | The corpus tools the model calls, and `ToolBudget` (ADR-0260) |
| `spend.py` | `SpendGate` (a `wrap_model_call` middleware), the ledger, projection |
| `run_ledger.py` | Run spend, in sqlite beside the checkpoints, written as deltas |
| `corpus.py` | `Entry`, the loader, and the judgements that belong to a value |
| `repository.py` | Indexes, search, vocabulary, the alias index (ADR-0130) |
| `units.py` | Three-valued dimensional compatibility (ADR-0160) |
| `citations.py` | The delimited citation form `[[nnnnnn]]`, written and parsed (ADR-0410) |
| `bionumbers.py` | The only module that names BioNumbers: its `BNID` notation, read and restated (ADR-0420) |
| `entries_table.py` | Rows, marks and legends — shared by both drivers |
| `messages.py` | Wording both drivers use, and `STOP_THE_RUN` |
| `cli.py` / `web.py` | The two adapters |
| `trace.py` | The structured trail, one question id throughout |

**Patterns, named where they are used.** Ports and adapters (above). Repository
(`repository.py`). Middleware, LangChain's own rather than hand-rolled — the spend
gate is a `wrap_model_call`, and retry, tool-error and call-limit middleware are
all stock. The event stream is a generator, so a driver decides when to consume.

**Limits, and which is which.** `RUN_CALL_LIMIT` bounds model calls;
`TOOL_CALL_LIMIT` bounds retrievals and is enforced in the tools because a model
batches several into one hop; `question_ceiling` and `run_budget` bound spend;
`CONVERSATION_BOUND` bounds a session's tokens. Each is configured where it binds
and reported when it is reached (ADR-0180).

### `bionumbers_ingest` — the corpus pipeline

A **pipeline**, and the shape is load-bearing: the two ends are the only modules that know a file
format, and nothing between them knows either.

| Module | Role |
|---|---|
| `parsing/html_table.py` | source format in — streams `<tr>` rows, preserving raw inner HTML |
| `cleaning.py` | one raw row → one record; the only place that unescapes or strips |
| `model.py` | the record, plus `EXPECTED_HEADERS` |
| `validation.py` | the run report |
| `provenance.py` | source fingerprint and manifest |
| `io.py` | JSONL out, renamed into place on success |
| `ingest.py` | wires the pipeline together |
| `guard.py` | the refusal to write where git would track the output |
| `resolve.py` | find a corpus, or the export that would produce one |
| `cli.py` | the command |

Five things about it that reading one module will not tell you:

- **The reader preserves raw HTML deliberately.** The export's injected markup arrives
  HTML-escaped, so a reader that unescaped would hand cleaning a live tag and destroy the evidence of
  which form the source used. Unescaping happens once, in `cleaning`, before markup is stripped.
- **An angle bracket is not evidence of markup.** The export contains exactly one HTML element and
  uses `<` as a less-than sign in prose. A tag is recognised only by a real HTML element name.
- **Records are buffered, not streamed, between cleaning and the writer**, because each carries a
  digest of the whole source, which is unknown until the last byte. Roughly 70 MB; ADR-0240.
- **Four booleans are the contract with `scinumbers_ask`**, not the flag names: `range_fused`,
  `range_qualified`, `range_one_sided` and `range_approximate`. `parse_flags` is cleaning's own
  vocabulary and may change — the last two became fields because the consumer was reading them out of
  that list by name, where a rename would have turned them silently false. ADR-0230.
- **The git-tracking refusal is in `guard.py`, called by `ingest()`, not by the command.** It lived
  in `cli.py` and so protected one caller; the operation invoked as a library wrote 20 MB onto a
  committable path in silence. A guard in a driver is a guard for one
  driver; ADR-0250.
- **`cleaning.py` has been the densest source of defects in the project**, and every one of them
  produced a plausible number rather than an error. Seven review passes, fault seeding and mutation
  testing each found more; treat a change there as needing all three, and **measure both directions**
  — a fix that stops over-flagging usually starts under-flagging, and only the second is dangerous.


## Specs and the code that is meant to satisfy them

`openspec validate --strict` checks that a spec is well formed. It does not check
that anything implements it, and the difference has already cost this project
once: `grounded-answering` required bounding "the number of tool calls made in
answering a single question" while the code bounded *model* calls, and the two
only came apart when a model batched several tool calls into one hop.

`tests/test_spec_conformance.py` maps each requirement to the tests that assert
it, and fails when a requirement is neither mapped nor explicitly recorded as a
gap. **Add the mapping entry in the same change that adds the requirement**, the
way ADRs are written with the decision rather than collected at the end.

Be clear about what it proves. It catches a requirement nothing claims, and a
claim naming a test that no longer exists. It does not catch a test that claims a
requirement and checks the wrong thing -- which is exactly what happened above.
What it buys is that the requirement's words sit next to the name of the test
asserting them, where a reader comparing the two can see the mismatch. A review
aid, not a proof.

## Running the tests

`pytest` is offline by default and runs on the six-entry fixture: `addopts = "-m 'not network and not corpus'"` deselects both markers, so a green run may never have executed the tests that hit a real service or the ones that check a marker can fire against a real corpus. Run those explicitly with `pytest -m network` and `SCINUMBERS_CORPUS=... pytest -m corpus`.

## Testing the tests

Two techniques, both scoped by consequence: spend the effort where a silent bug would be *unfalsifiable to the user* — parsers, retrieval, provenance — and not on drivers, rendering or config, where a bug announces itself the moment someone looks.

**Fault seeding** is the default, and the user-level conventions cover it: seed one realistic defect into a *copy* of the source and check that exactly the right test fails.

**Mutation testing** is the automated complement, and finds what seeding structurally cannot — code no test can distinguish. Run it at the end of a task, over the module just touched, via the **`mutation-test-module`** skill, which carries the recipe and this project's three setup gotchas. Not over the whole package (2,000+ mutants, hours) and never as a CI gate.

Its yield decays, and that is expected rather than a failure: a module's first run finds real gaps, later runs on settled code return mostly equivalent mutants. Once two or three consecutive runs turn up nothing but string-sentinel and default-argument survivors, stop running it on that area and reach for it again only when the code changes substantially. It is a tool for new and reworked code, not a standing gate.

**Yield decays per instrument, not absolutely, and that distinction has already been paid for.** `cleaning.py` was reviewed by reading seven times, with findings each time and no downward trend: 9, 11, 6, 5, 5, 5, 7. The sixth pass caught a defect the fifth pass had *introduced*, and the seventh — after mutation testing had run over the same module — still found a HIGH. Reading the same code again is the instrument with the fastest decay; a lens it cannot use (mutation testing, a scoped adversarial review, a question about a second caller) resets the yield. So "the last pass found little" is evidence about the instrument, not about the code, and the move is to switch lenses rather than to conclude the module is clean.
