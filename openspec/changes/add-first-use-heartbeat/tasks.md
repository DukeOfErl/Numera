<!-- ADR block for this change: 1350–1390, reserved in CLAUDE.md. Write each ADR in the same
     task as the decision. Planned: 1350 the heartbeat is measured from the last delivery, in
     the workflow, with the standing issue as the state. -->

## 1. Confirm what GitHub returns (before any code)

- [x] 1.1 Read `gh issue view 1 --json createdAt,updatedAt,comments`, the exact-title list and the seven-day run count, read-only, timestamps and counts only (never bodies: real reports contain reader addresses). Done 2026-10-04: `createdAt` and `comments[]` as designed; the run count works. Record it in ADR-1350.

## 2. Tests first, from the spec scenarios

- [x] 2.1 Extend the stub `gh` in `tests/test_scheduled_workflows.py`: `issue view N --json … --jq` applies the caller's own `--jq` to a fixture (`GH_STUB_ISSUE_VIEW`); `run list` already applies `--jq`. Keep `issue list`'s existing behaviour.
- [x] 2.2 Write the failing tests by executing the "Tell the operator" step: a quiet week posts exactly one comment; less than seven days since the last delivery posts nothing; the issue's creation counts when it has no comments; the newest comment decides, whatever it was (report, test line, heartbeat); a heartbeat run is followed by silence for seven days; no standing issue posts nothing and creates nothing; a non-empty report is posted as before and no heartbeat is added; a `test` run posts its line and no heartbeat; the heartbeat opens with the owner's mention; it says the check *found* no new reader, states the check count (successes plus one) and its own time, and does not claim that none exist; a failing `gh issue view` fails the step. Assertions come from the spec text, not from running the step.

## 3. The step

- [x] 3.1 In `.github/workflows/first-use.yml` "Tell the operator": when the report is empty and not a test run, find the standing issue (exact title, as now); with none, exit quietly. Read the last delivery with `max(createdAt, comments[].createdAt)`; if fewer than 604800 seconds old, exit quietly. Otherwise count successful runs in the last seven days, add one, and post the heartbeat body (mention, time, finding, count, the "may be what is wrong" sentence) as a comment. Under `bash -e`, so any failed read fails the job.
- [x] 3.2 Update the workflow's header comment: silence is still the rule for a run with nothing to say, except one message per quiet week.

## 4. Prove the tests can fail (seed into a copy, green baseline first)

- [x] 4.1 Seed, each caught by the test written for it: a heartbeat on every run; the clock not reset by a real report (reads only the issue's creation); the clock read from the issue's creation only when comments exist; a heartbeat posted when no issue exists; the mention dropped; wording that asserts none exist; the count taken from the wrong workflow or without the "+ 1"; seven days compared as six or eight; a heartbeat added to a non-empty report; a heartbeat on a `test` run. Record which survived and what that means.

## 5. Documentation, in this change

- [x] 5.1 ADR-1350: the heartbeat in the workflow, measured from the last delivery, the issue as the state; the rejected alternatives; the assumptions (a person's comment resets the week; no issue means no heartbeat); what was and was not verified, including the 2026-10-04 read of GitHub's output.
- [x] 5.2 README (the first-use section), CHANGELOG `[Unreleased]`, and the `CLAUDE.md` ADR row.
- [x] 5.3 `openspec validate add-first-use-heartbeat --strict`, and diff the MODIFIED requirement against the promoted one (scenarios and paragraphs).

## 6. Hand over

- [ ] 6.1 Full suite once; commit; hand over. Merging and pushing are the operator's call; a scheduled workflow takes effect from `main`.
- [ ] 6.2 After the merge: the first real heartbeat is the live check, due about seven days after the last delivery (after 2026-10-10T21:56Z if nothing else is posted). Confirm it arrives and reads as intended.
- [ ] 6.3 Archive the change once its requirement has landed (`openspec archive`), per `.claude/rules/specs.md`.
