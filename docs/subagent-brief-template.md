# Subagent brief — template

A subagent gets its own system prompt, the message you send it, the CLAUDE.md
hierarchy, and a git-status snapshot. It does **not** get the conversation, and
it does not get this session's memory. Everything it needs has to be in the brief
or in a file the brief names.

Copy the shape below. The headings are not decoration — each one exists because
its absence caused a specific failure in a comparable project.

---

## Where you are

- Absolute worktree path: `…`
- **Never `cd`.** Use absolute paths. A relative path after a `cd` is undecidable
  against this project's tool-permission rules and will block on a prompt — which
  gets diagnosed as an allowlist problem, twice, before anyone reads the prompt
  text.
- You have no conversation history. Everything you need is here or in the
  documents this brief names. Do not ask for context; if it is missing, say so.

## What you are changing

- The **one** file you may edit: `…`
- Other agents are editing theirs concurrently. Do not edit any other file.
- The contract you code against, verbatim:

  ```python
  …exact public signatures…
  ```

## What "done" looks like

- The named test file that is the specification: `tests/…`
- Read it first. **Do not edit it.** If a test looks wrong, say so and stop.
- Verify cheaply — that one test file, or
  `python -c "import numera_ask.<module>"`. Do not run the full suite.

## What the work actually involves

> The paragraph above is the easy half. The list below is what gets skipped while
> reporting success — so each item is a requirement, not a suggestion.

1. …
2. …
3. …

Name here, in advance, the two or three things a plausible-looking
implementation would leave out. This is the single highest-value section of the
brief: it is the difference between "the tests pass" and "the thing works", and
naming a requirement is cheaper than discovering it was skipped.

## How to stop

Report the blocker and stop. Do not weaken a test, skip a requirement silently,
or implement something narrower and describe it as complete.

## What to return

The JSON shape from your agent definition, and nothing after it. `blocked` is a
string when you could not finish and `null` otherwise — a field, so that "I could
not do this" cannot be skimmed past in prose.

---

## Notes for whoever writes the brief

- **Fix the measures before the run, not after.** Picking what counts as success
  after seeing the result is how a comparison becomes a justification.
- **Front-load the contract.** One agent returning the exact public signatures,
  interpolated verbatim into every downstream brief, is what lets several agents
  edit several files concurrently without conflicts. It is the mechanism, not a
  nicety.
- **A workflow is as good as its author's plan; a team can notice the plan was
  wrong.** A scripted fan-out cannot ask "is this tested, is this test any good,
  should the spec say something different" unless a phase contains that question.
  Use fan-out against a settled contract. When the contract is still open, do the
  work in conversation.
- **Verification tools stay; verification instructions go.** Current model
  guidance is to remove "double-check your work" and "re-verify before
  responding" from prompts — they are redundant now and cost tokens. That is not
  an argument against the verifier agent, which is a separate reader with its own
  toolset. Do not pad a writer's brief with self-checking language.
