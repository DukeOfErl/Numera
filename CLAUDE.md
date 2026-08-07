# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## LLM Coding Guidelines (Karpathy-inspired)

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Git project management

**All work happens on a branch, scoped to an explicit work package.** A work package is a one- or two-sentence statement of the goal and what "done" looks like — small enough to live on a single branch and merge as a unit.

- **Branch; don't work on `dev`/`main`.** Each work package gets a dedicated branch off `dev` (or off a daughter branch, for sub-work that builds on still-unmerged work). Integration happens only through the merge flow, which requires the user's explicit approval (a `git merge` / `gh pr merge` guardrail lives in the user's settings).
- **No branch → stop and advise, don't start editing.** When changes are requested but nothing is open to hold them — the current branch is `dev`/`main`, or a branch whose work package doesn't cover the request — first help the user define a clear work package (goal + done-criteria) and open a dedicated branch for it (propose a name and scope). Begin the changes only once that branch exists.
- **Drift → flag it, don't silently absorb it.** While a work package is in progress, watch for scope drift: an unrelated fix, a second feature creeping in, or growth well beyond the stated goal. When it happens, say so explicitly ("this is drifting from *&lt;work package&gt;*") and propose how to proceed — typically one of: (a) move the extra work to its own branch off `dev`, (b) consciously widen the current work package if the addition genuinely belongs to it, or (c) defer/stash the tangent. Let the user choose.
- **Keep branches focused and short-lived** so they stay reviewable and merge cleanly.

**Never commit secrets.** API keys, tokens, passwords, private keys, connection strings, and service-account credentials must never enter the repository — not in code, config, tests, fixtures, notebooks, or commit messages. Read them from the environment or a secrets manager, and commit only a `.env.example` with placeholder values. Check `git status` and the staged diff before every commit; when a file is unfamiliar or machine-generated, look at its contents rather than trusting its name. The same rule covers the datasets and credentials of third parties.

If a secret does get committed, **treat it as compromised and rotate it immediately** — rewriting history is not sufficient, because the value may already have been pushed, cloned, cached, or indexed. Rotate first, then clean the history.

## Documentation upkeep

When a change alters the architecture or user-visible functionality in a major way (new module, new pipeline, new UI capability, changed data flow), update **all three** docs in the same change — they serve different readers and go stale independently:

- **`README.md`** — what the app does and how to use it (for users and new developers)
- **`docs/diagrams/`** — the user/developer diagrams (currently `docs/diagrams/architecture.md`), updated **following the principles in `docs/diagrams/DIAGRAMS.md`** (one diagram per story, sequence diagrams for temporal flows, ~7±2 boxes each), together with the references to these diagrams from `README.md`
- **`CLAUDE.md`** — this file's Architecture section (how the code is organized, for coding agents)

The behavioral spec — what the app must do, kept implementation-agnostic — lives in **`openspec/specs/`**, maintained through the OpenSpec workflow rather than as a hand-written document. Write behavioral requirements as spec deltas on a change; they are promoted into `openspec/specs/` when the change is archived. See [ADR-0030](docs/decisions/0030-openspec-specs-as-the-behavioral-record.md).

Small fixes and internal refactors that don't change behavior or structure don't need this.

**Architecture Decision Records (`docs/decisions/`).** When a decision shapes the project in a way worth remembering — a non-obvious technical choice, an accepted trade-off, a convention, a reversal — record it as an ADR. Copy `docs/decisions/0000-decision-template.md` to `docs/decisions/NNNN-concise-kebab-name.md`, where `NNNN` is the highest existing id **plus 10** (the first real ADR is `0010-…`; `0000` is the reserved template). Gap numbering leaves room to slot a later decision between two existing ones. Fill in status, date, the pull request, and the context / decision / trade-off. Write the ADR as part of the same change that makes the decision — not retroactively.

**Changelog (`CHANGELOG.md`).** Keep `CHANGELOG.md` (project root, Keep a Changelog format) current as work progresses: for any user-visible or otherwise notable change (new capability, changed behavior, removal, fix), add a bullet under `## [Unreleased]` in the appropriate Added / Changed / Removed / Fixed group. Move those bullets into a versioned section when a release is tagged.

