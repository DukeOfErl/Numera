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
| `add-grounding-validator` | `0040`–`0090` — `0040`, `0050` written |
| `add-ask-agent` | `0100`–`0190`, `0260`–`0290` |
| `add-corpus-ingestion` | `0200`–`0250` — all written |
| `add-corpus-autobuild` | `0300`–`0340` |
| `rename-to-scinumbers` | `0400`–`0450` |
| `add-answer-evaluation` | `0500`–`0550` — `0500`, `0510`, `0520`, `0530`, `0540` written |
| `add-answer-shape` | `0560`–`0590` |
| `add-provider-limit-ending` | `0600`–`0640` — `0600` written |
| `add-judged-faithfulness` | `0650`–`0690` |
| `add-durable-trail` | `0700`–`0730` |
| `add-answer-feedback` | `0740`–`0770` — `0740`, `0750`, `0760` written |
| `add-user-identity` | `0780`–`0830` — all written |
| `add-question-and-answer-records` | `0840`–`0870` |
| `add-validator-prototype` | `0930`–`0990` — `0930`, `0940`, `0950`, `0960`, `0970`, `0980`, `0990` written: block full, widen before the next. Its first three, written as `0900`–`0920`, collided with `add-open-enrolment` on `dev` and were renumbered `1520`, `1530`, `1540` on 2026-10-07, inside `add-harvest-prototype`'s block |
| `add-harvest-prototype` | `1500`–`1590` — `1500`, `1510` written, and `1520`–`1540` hold the validator's renumbered three; clear of every block on `dev` and the branches as of 2026-10-07 (highest `1350`–`1390`) |
| `add-ask-over-store` | `1600`–`1690` — `1600`, `1610` written |

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
(`validator`). All three are here now; the validator is a prototype (ADR-1520) and is described in
its own subsection below.

A fourth extra, `eval`, is **additive to `ask` rather than a package of its own**: the evaluation
harness lives in `scinumbers_ask` because it is an adapter over that agent, and the extra carries only
what is new. Install both: `uv sync --extra ask --extra eval`. The extra is currently empty:
`deepeval` left with the judged layer, which is now `add-judged-faithfulness`, and returns with it.
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
| `question_set.py` | The question set: the format, its reader, the entry shapes derived from the corpus, and the tier (`basic` / `compound` / `declining`) that keeps a gain in one kind of question from being paid for out of another |
| `evaluation.py` | The evaluation driver: asks, records one line per result, resumes, fingerprints what produced each, and refuses a results path git would track |
| `scoring.py` | Every score needing no model and no prose parser, as pure functions; the outlier check (ADR-0520) |
| `report.py` | Figures read out of a results file, never combined across model, prompt or corpus |
| `answer_sheet.py` | Every answer and the entries that bear on it, as HTML or PDF; never the recorded context |
| `eval_cli.py` | The evaluation command (`scinumbers-eval`): `check`, `run` and `report` |
| `trace.py` | The structured trail, one question id and one session id throughout |
| `trail_store.py` | The trail's durable destination: one append-only table, written best-effort (ADR-0700, ADR-0710) |
| `feedback.py` | A reader's judgement of an answer, recorded to the trail. **Presentation, not core** — see below |
| `permissions.py` | `Role`, `Permission`, `Identity`, and `GRANTS` — the default-deny table as data, with the pruning rule above it (ADR-0800) |
| `authorization.py` | `allowed` / `require` / `Refused`: the one refusal, called inside the operation it guards, never by the page |
| `accounts.py` | `lookup(engine, email)`: enrolment off one row, **fails closed** — the deliberate inverse of `trail_store` (ADR-0780) |

**`ask` wraps `_ask`, and the wrapper is where the records are written.** The
question, the answer and the evidence behind it are recorded as their events pass
through, not at the eight places inside `_ask` that can yield an `Answer` — seven
of those are endings, and a per-branch record is one the next branch forgets.
Each is written *before* its event is handed on, because Streamlit abandons the
generator mid-iteration on every rerun and code after a `yield` may never run
(ADR-0840). Add a ninth ending and it records itself; add a record beside a
`yield` and you have reintroduced the bug.

**The trail has three sinks and a filter, all on one logger**, and identity
stops at the driver. `.claude/rules/identity.md` carries both — where the
refusal lives, what the agent may never be handed, why the session is keyed on
the account rather than the link, and the install ordering that is load-bearing.
It loads when you touch any file sign-in goes near.

`feedback.py` sits on the **presentation** side of the dependency line, and that
placement is the guarantee rather than a filing choice: a comment is text a
stranger wrote, and the agent must not be able to reach it even by accident.
`test_driver_independence.py` asserts that no agent-core module imports it —
under `PRESENTATION`, which is wider than the `ADAPTERS` set the older test
checks, because a module can be presentation without being a driver (ADR-0750).

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

### `bionumbers` — the validator prototype

A **fixed pipeline, not an agent** (ADR-1520): discovery → fetch → JATS reader → one structured
extraction call → mechanical quote check → one retry → one second-text call → JSONL → Postgres → a
review page. Its own `CLAUDE.md` lives in `src/bionumbers/` with the module table and the four
rules a module will not tell you — the dependency direction holds there too, and only `review.py`
and the root `review_app.py` may import Streamlit or the ask package.

### `bionumbers_ingest` — the corpus pipeline

A **pipeline**: the two ends are the only modules that know a file format, and
nothing between them knows either. Its own `CLAUDE.md` lives in
`src/bionumbers_ingest/` — a module table, and five things reading one module
will not tell you, including that `cleaning.py` has been the densest source of
defects in the project. **Read it before changing anything in that package.**

It is there rather than here because it warns about a package the other two work
packages never touch, and this file is loaded into every session and every
subagent.

## What is planned, and in what order

`docs/roadmap.md` holds the work packages and their sequence — what is done, what
is next, and the reasons that would otherwise live only in a session transcript.
It records decisions already taken, not proposals. Read it before proposing a
change, and reconcile it when one lands; it names the severe findings that gate
later work (the SQLite ledger on Cloud Run, the LangSmith env var) where a change
author will meet them rather than rediscover them.

## Where the rest of the rules live

Under 200 lines is the target for this file, and everything below is either
scoped to the files it applies to or lives beside the code it describes. Nothing
was dropped — each moved whole.

`.claude/rules/` loads a file only when Claude touches a path its `paths:`
frontmatter matches, so these cost nothing on a session that never goes near them:

| Rule | Loads when you touch | Covers |
|---|---|---|
| `testing.md` | `tests/**`, `src/**/*.py` | how to run the suite (the `-m` trap), fault seeding, mutation testing, the negative-case rule |
| `specs.md` | `openspec/**` | what a spec delta must contain, and why each change archives as it completes |
| `streamlit-driver.md` | `streamlit_app.py`, `web.py`, their tests | why some things can only be seen through a whole script run |
| `identity.md` | `web.py`, `permissions.py`, `authorization.py`, `accounts.py`, their tests | where the refusal lives, what the agent is never handed, how a session is keyed |
| `lint-and-format.md` | `pyproject.toml`, `.pre-commit-config.yaml`, CI | the pin that must move in two places at once |
| `validator-prototype.md` | `src/bionumbers/**`, `review_app.py`, its tests and change | verify quietly, report only what fails |

`src/bionumbers_ingest/CLAUDE.md` and `src/bionumbers/CLAUDE.md` load when Claude reads a file in
that package
— the pipeline's shape, and five things one module will not tell you.

Two things deliberately **not** moved. The table above this section says who each
rule is addressed to, and it must reach every subagent whether or not that agent
touches a matching path. And the architecture and dependency-direction notes
apply to any change anywhere, so scoping them would mean loading them almost
always, at the cost of a lookup.

Imports (`@path`) would not have helped: imported files are expanded into context
at launch, so they organise without reducing anything.
