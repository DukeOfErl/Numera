# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Who each rule is addressed to

This file reaches a subagent exactly as it reaches the session that spawned one:
the CLAUDE.md hierarchy is part of a subagent's context, and nothing in it says
which role is reading. So a rule written to stop the orchestrator hesitating gets
executed by six workers in parallel — and the forceful wording that makes it work
on the orchestrator is what makes it dangerous in a worker. "Do not ask first"
overcomes a hesitancy a worker does not have.

**Orchestrator only.** A subagent must not act on these. `.claude/agents/writer.md`
repeats the list, because a marker here is a weaker signal than an instruction in
the agent's own prompt — and most of these rules live in the user-level
conventions, which this file cannot annotate.

| Rule | Where | What a worker does with it |
|---|---|---|
| A green suite at a section boundary *is* the commit | user-level | Several writers committing into one worktree, racing |
| Suggest `/code-review` before a merge; a retro after | user-level | Six suggestions, nobody owning the merge |
| Periodically ask what work exists only on this disk | user-level | Noise, once per agent |
| Scout and fundraise probes at a lull | user-level | A funding probe mid-task |
| Update README, CHANGELOG, diagrams and specs together | Documentation upkeep | Parallel edits to shared files, conflicting by construction |
| ADR block allocation | Parallel branches and ADR numbers | Every worker claims the same next number |
| Run mutation testing at the end of a task | Testing the tests | Six mutation runs, hours of compute |

**Everyone, orchestrator and worker alike:** the Architecture section, the
dependency direction, `Running the tests`, `Lint and format`, the spec-delta
rules, and the comment register. Those describe the code and how to touch it
safely, which is the same job whoever is doing it.

**One rule is missing rather than misaddressed:** nothing here says *do not run
the full suite*. It takes about a minute, and a fan-out of workers each running
it repeatedly is pure waste. The orchestrator runs it once at the end; a worker
verifies its own file with the one test file it was given, or an import.

A subagent receives its own system prompt, the task it was sent, this hierarchy,
and a git-status snapshot — **not** the conversation, and not the orchestrator's
memory. Anything a worker needs, its brief has to carry: see
`docs/subagent-brief-template.md`.

## Documentation upkeep — project override

This project follows the user-level documentation-upkeep conventions with one substitution: there is no `docs/REQUIREMENTS.md`. The behavioral spec — what the app must do, kept implementation-agnostic — lives in **`openspec/specs/`**, maintained through the OpenSpec workflow rather than as a hand-written document. Write behavioral requirements as spec deltas on a change; they are promoted into `openspec/specs/` when the change is archived. See [ADR-0030](docs/decisions/0030-openspec-specs-as-the-behavioral-record.md). Wherever the conventions say to update `docs/REQUIREMENTS.md`, update the OpenSpec specs instead.

## Parallel branches and ADR numbers

Two branches numbering ADRs from the current highest id both claim the same
numbers, and the second to merge conflicts. Give each branch a disjoint block
before parallel work starts.

**This file is the allocation's source of truth.** Keep the block in the change's
`tasks.md` too — that is where an implementer reads it — but reconcile against
this table and widen a block *here* first. Recording it only in `tasks.md` is
what let the blocks drift: no branch can see another's copy.

| Change | Block |
|---|---|
| `add-grounding-validator` | `0040`–`0090` |
| `add-ask-agent` | `0100`–`0190`, `0260`–`0290` |
| `add-corpus-ingestion` | `0200`–`0250` — all written |
| `add-corpus-autobuild` | `0300`–`0340` |
| `rename-to-scinumbers` | `0400`–`0450` |
| `add-answer-evaluation` | `0500`–`0550` — `0500`, `0510`, `0520` written |
| `add-answer-shape` | `0560`–`0590` |
| `add-provider-limit-ending` | `0600`–`0640` — `0600` written |
| `add-durable-trail` | `0700`–`0730` |
| `add-answer-feedback` | `0740`–`0770` — reserved, change not yet proposed |
| `add-user-identity` | `0780`–`0830` — reserved, change not yet proposed |

Gaps between blocks are deliberate — room to widen without renumbering. The last
two rows are reserved **before their changes exist**, because a change gets
proposed while the previous one is still open, which is exactly when a branch
allocates against a ceiling it can no longer see.

**This table is the authority, never a scan of `docs/decisions/`.** A scan cannot
see uncommitted ADRs on another branch — `git ls-tree` reads committed trees, and
each branch has its own worktree — so a number can be spent and invisible from
here. `add-ask-agent`'s first block was uncommitted for two sessions, which is how
a scan came to report those numbers as free. **Never conclude a number is free
because no file for it turns up.**

**Allocate by creating the file**, committing the stub early: a ceiling only holds
if claiming the number and writing the file are the same step.

**Widen, never renumber.** `add-ask-agent` holds `0100`–`0190` *and* `0260`–`0290`
because its first block ran out mid-change. Written ADRs are cited from code
comments and commit messages; renumbering breaks every citation to buy contiguity
nothing needs.

**Write each ADR with the change that makes the decision, never as a batch at the
end.** Deferring them to a documentation group produces retroactive ADRs, by which
time the rejected options — the part worth recording — are gone, and what survives
is a description of the code.

## Architecture

Three work packages, three packages under `src/`, one dependency extra each, so no two branches edit
the same source tree: `bionumbers_ingest` (`ingest`), `scinumbers_ask` (`ask`), `bionumbers`
(`validator`). The ingester and the ask agent are both here; the validator is not yet.

A fourth extra, `eval`, is **additive to `ask` rather than a package of its own**: the evaluation
harness lives in `scinumbers_ask` because it is an adapter over that agent, and the extra carries only
what is new (`deepeval`, for the judged layer alone). Install both: `uv sync --extra ask --extra eval`.
A deterministic evaluation run needs none of DeepEval, which is why it is separable at all.

Diagrams — including the agent's graph generated from the compiled object — are in
`docs/diagrams/architecture.md`. Regenerate that graph whenever middleware changes.

**Ports and adapters.** `agent.py` emits events (`events.py`) and accepts a
question; it never touches an interface and never blocks for input. `cli.py` and
`web.py` are adapters over it, and the evaluation harness is the third — it asks
a question set, records what came back, and reports on it; the judged layer is
still to come. The agent takes no
parameter naming its caller, so it cannot behave one way for a person and another
for a harness (ADR-0110).

**Two modules reach for the ingester, not one.** `autobuild` builds a corpus when
only an export exists. `evaluation` imports `bionumbers_ingest.guard` to refuse a
results path git would track: every result carries the retrieval results verbatim,
so a results file holds corpus text, and that guard is the one thing standing
between an evaluation and the single irreversible mistake this project can make
(ADR-0170, ADR-0250). It is imported rather than reimplemented deliberately — two
copies of that guard would be one that gets fixed and one that does not — and it
refuses to write at all if the ingester is absent, because the cheap direction for
an irreversible mistake is to stop.

**The dependency direction is the one rule with teeth.** Adapters may reach into
the core; the core may not reach back. Nothing in Python enforces this — an
`import streamlit` in the tool layer would run perfectly — so
`tests/test_driver_independence.py` asserts it over the source. `entries_table.py`
and `messages.py` are shared *by* the drivers and count as presentation, which is
why a rule both the table and the model need (the implausible-span test) lives on
`Entry` rather than in the table.

The harness modules are named in that test's `HARNESS` set and carry one extra
rule: they may not reach for an interactive driver either, or the thing meant to
run unattended would need a terminal. **Add a new harness module to that set as it
lands** — the set also decides, by subtraction, which modules count as the agent's
core, and a test there refuses a name with no file behind it.

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
| `cli.py` / `web.py` | The two interactive adapters |
| `question_set.py` | The evaluation's question set: the format, its reader, and the entry shapes derived from the corpus |
| `evaluation.py` | The evaluation driver: asks, records one line per result, resumes, fingerprints what produced each, and refuses a results path git would track |
| `scoring.py` | Every score needing no model and no prose parser, as pure functions; the outlier check (ADR-0520) |
| `report.py` | Figures read out of a results file, never combined across model, prompt or corpus |
| `eval_cli.py` | The evaluation command (`scinumbers-eval`): `check`, `run` and `report` |
| `trace.py` | The structured trail, one question id and one session id throughout |
| `trail_store.py` | The trail's durable destination: one append-only table, written best-effort (ADR-0700, ADR-0710) |

**The trail has two sinks.** `trace.py` writes to a logger; `trail_store.py`
attaches to that logger as a second handler, so no call site knows about it. Two
things a reader will otherwise get wrong:

- **Recording fails open, deliberately inverting the spend gate** — the reasoning,
  and why it is a spec requirement rather than a code convention, is ADR-0710.
- **`install` must come after `trace.to_file`**, which calls `configure`, which
  clears the logger's handlers. Above it, the sink is attached and then discarded:
  an app that looks configured and records nothing. `test_web_driver_trail.py`
  pins the order; nothing below the driver can see it.

`trail_store` is core rather than presentation by decision, not by subtraction —
`test_driver_independence.py` names it and says why. The connect timeout is the
one guard here the *caller* owns, because libpq takes it at engine construction;
the statement timeout belongs to the operation as usual.

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

A **pipeline**: the two ends are the only modules that know a file format, and
nothing between them knows either. Its own `CLAUDE.md` lives in
`src/bionumbers_ingest/` — a module table, and five things reading one module
will not tell you, including that `cleaning.py` has been the densest source of
defects in the project. **Read it before changing anything in that package.**

It is there rather than here because it warns about a package the other two work
packages never touch, and this file is loaded into every session and every
subagent.

## Specs and the code that is meant to satisfy them

`openspec validate --strict` checks that a spec is well formed. It does not check
that anything implements it, and the difference has already cost this project
once: `grounded-answering` required bounding "the number of tool calls made in
answering a single question" while the code bounded *model* calls, and the two
only came apart when a model batched several tool calls into one hop.

`tests/test_spec_conformance.py` maps each requirement to the tests that assert
it, and fails when a requirement is neither mapped nor recorded as a gap. **Add
the mapping entry in the same change that adds the requirement**, the way ADRs
are written with the decision rather than collected at the end.

Be clear about what it proves. It catches a requirement nothing claims, and a
claim naming a test that no longer exists. It does **not** catch a test that
claims a requirement and checks the wrong thing — which is exactly what happened
above. What it buys is the requirement's words sitting next to the name of the
test asserting them, where a reader comparing the two can see the mismatch. A
review aid, not a proof. (Which files it reads, and why not recursively, is in
that file's own docstring.)

### A spec delta is the requirement's full new text

A `MODIFIED` block is the **entire requirement as it will now read**, not the
part being changed. Copy the current requirement out of `openspec/specs/` and
edit that copy. Writing out only the paragraphs a change cares about deletes
everything else, and the delta has no baseline to diff against, so it reads as an
addition.

**`openspec archive` refuses a dropped scenario and says nothing about dropped
prose.** That is the whole exposure. `rename-to-scinumbers`'s delta was caught
dropping three scenarios; the same block silently dropped three paragraphs of
requirement text, and nothing would ever have reported it. So after writing a
`MODIFIED` block, diff it against the current requirement mechanically —
scenarios *and* paragraphs.

**Archive each change as it completes.** `MODIFIED` requires its target to be in
`openspec/specs/` already, so changes archive in the order their requirements
landed; letting several pile up turns that into a blocker discovered at the end.
`--skip-specs` is not the way out — it archives the change while promoting
nothing, which is the only reason to archive.

## Lint and format: automatic, and pinned in two places

`ruff check` and `ruff format` run at every commit through `.pre-commit-config.yaml`, and in CI
(`.github/workflows/checks.yml`) over the whole tree. A fresh clone or a new worktree needs
`uv run pre-commit install` once — the hook lives in `.git/hooks`, which worktrees share, so one
install covers all of them.

**The rev in `.pre-commit-config.yaml` and the `ruff` pin in `pyproject.toml` must move together.**
Ruff's formatter output can change between minor releases, so a range in one place and a pin in the
other is how eight files came to be unformatted while `ruff check` stayed green for weeks. The
pre-commit rev is the arbiter: CI runs the hooks, not the venv's ruff, so a local ruff that has
wandered is reported rather than silently committing churn.

CI **reports, it does not gate.** Streamlit Cloud deploys a branch tip whether or not the checks
pass, so a green tick is a smoke alarm and not a lock. It also cannot run the two marked suites,
which is the point of the paragraph below.

## Running the tests

A repeated-run harness -- fault seeding, mutation testing -- should exclude the `slow` marker as well, and must write the **whole** expression: `pytest -m "not network and not corpus and not slow"`. A second `-m` replaces `addopts` rather than ANDing with it, so `-m "not slow"` alone re-selects `network` and `corpus` and the run gets *slower* -- silently. 63s becomes 34s written correctly.

`pytest` is offline by default and runs on the six-entry fixture: `addopts = "-m 'not network and not corpus' -p no:deepeval"` deselects both markers, so a green run may never have executed the tests that hit a real service or the ones that check a marker can fire against a real corpus. Run those explicitly with `pytest -m network` and `SCINUMBERS_CORPUS=... pytest -m corpus`.

`-p no:deepeval` is there because the `eval` extra installs DeepEval, which registers a pytest plugin that prints a teardown line after every run — including runs that touch none of its code. Collection is unaffected; it is the output that moved, and "the suite output is unchanged" is not checkable if it depends on which extras a developer installed. Harmless where DeepEval is absent, since `-p no:<name>` for an uninstalled plugin is not an error — which matters because this file is shared by all three work packages. Group 6 of `add-answer-evaluation` may want DeepEval's own pytest integration back; that means overriding `addopts` in that run, and the whole expression has to be written out, exactly as with `-m`.

## Testing the tests

Two techniques, both scoped by consequence: spend the effort where a silent bug would be *unfalsifiable to the user* — parsers, retrieval, provenance — and not on drivers, rendering or config, where a bug announces itself the moment someone looks.

**Fault seeding** is the default, and the user-level conventions cover it: seed one realistic defect into a *copy* of the source and check that exactly the right test fails.

**A negative case has to differ from the positive one in the dimension the rule actually reads.** This is narrower than "test both directions", and it is what three blind tests in this project had in common — each read correctly and proved nothing, and each was found by seeding rather than by review. `_is_out_of_credit` checks `status_code == 402`; its negatives were `RuntimeError` and `TimeoutError`, which carry no status at all, so the mutant `status_code is not None` — under which every 429 and 502 would permanently close the run — passed all 905 tests. The negatives had to be real `APIStatusError`s at 429, 502 and 401. Before writing a negative case, name the dimension the predicate reads and check the case varies *that*, not merely the outcome.

**No coverage claim before the mutant dies.** Do not write "both directions are pinned" in an ADR, a task list or a commit message until a seeded defect has actually failed the test you are crediting. ADR-0600 asserted it and was wrong, and the claim then stood in the record as a reason not to look again — which is worse than saying nothing, because a false all-clear retires the suspicion that would have found the gap. Write the claim after the seeding, and name the mutant that died.

**Mutation testing** is the automated complement, and finds what seeding structurally cannot — code no test can distinguish. Run it at the end of a task, over the module just touched, via the **`mutation-test-module`** skill, which carries the recipe and this project's four setup gotchas. Not over the whole package (2,000+ mutants, hours) and never as a CI gate.

Its yield decays, and that is expected rather than a failure: a module's first run finds real gaps, later runs on settled code return mostly equivalent mutants. Once two or three consecutive runs turn up nothing but string-sentinel and default-argument survivors, stop running it on that area and reach for it again only when the code changes substantially. It is a tool for new and reworked code, not a standing gate.

**Yield decays per instrument, not absolutely, and that distinction has already been paid for.** `cleaning.py` was reviewed by reading seven times, with findings each time and no downward trend: 9, 11, 6, 5, 5, 5, 7. The sixth pass caught a defect the fifth pass had *introduced*, and the seventh — after mutation testing had run over the same module — still found a HIGH. Reading the same code again is the instrument with the fastest decay; a lens it cannot use (mutation testing, a scoped adversarial review, a question about a second caller) resets the yield. So "the last pass found little" is evidence about the instrument, not about the code, and the move is to switch lenses rather than to conclude the module is clean.

## When something is drawn is a driver-level question

A change to *when* an element is created, relative to the rest of a script run, cannot be seen below
the driver. `web.items_for` decides what the page says and is tested directly (ADR-0100), but the
order and the lifetime of the elements themselves belong to `streamlit_app.py`, which Streamlit
re-runs from the top on every interaction. **Drive the real script through `AppTest` for those.**

There is a production incident to cite. The "this run is over" banner was decided before
`st.chat_input`, so on the run that ended the conversation the ending did not exist yet and the
banner appeared one interaction late — never, for a reader who stopped there. `run_is_over` and
`ends_the_run` were correct throughout and every item-level test passed; the first real question put
to the deployed app found it. The same blindness hides an element drawn unconditionally that should
not have been drawn at all, which is how the empty "Retrieval" box survived.

This does not contradict the scoping rule above. Driver bugs still announce themselves to the first
person who looks, so they do not earn a seeding budget — the point is only that the person looking
has to be looking at a whole script run, and `AppTest` is the cheapest thing that is.
