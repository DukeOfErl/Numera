# Tasks

**ADR block: `1150`–`1190`**, reconciled against CLAUDE.md's table, which is the
authority. `1150` is the decision to store the handle and disable rather than
delete.

## 1. The handle

- [x] 1.1 `sql/accounts.sql`: `openrouter_key_hash`, in the `create table` and as
      an idempotent `alter` for databases that already exist.
- [x] 1.2 `accounts.insert` takes and writes it; `enrol` passes what `mint`
      returned instead of discarding it.

## 2. The withdrawal

- [x] 2.1 `accounts.disable`: one statement, disabling and returning the handle,
      unconditional so a hand-disabled row still yields it.
- [x] 2.2 `enrol.withdraw`: disable, then revoke, with the refusals that name
      which half did not happen.
- [x] 2.3 `scinumbers-withdraw`, sharing the branch-opening preamble with
      `scinumbers-enrol` rather than repeating it.
- [x] 2.4 Tests for both, including the order and the two partial states.
- [x] 2.5 Fault seeding: four seeds against a green baseline of 108, each
      caught by the one test named after it — the revoke failure swallowed,
      the missing-handle guard dropped, `disable` made conditional on
      `not disabled`, and `disable` reporting a withdrawal for an absent row.

## 3. The record

- [x] 3.1 Spec delta: the withdrawal requirement, and enrolment gains the
      obligation to record what makes it possible.
- [x] 3.2 ADR-1150.
- [x] 3.3 README, CHANGELOG, the CLAUDE.md module table.
- [x] 3.4 Full suite and ruff; then the merge on approval.

## 4. What the operator must do

- [x] 4.1 (operator) **Run `sql/accounts.sql` against every branch** — `alpha` and
      `dev` — before the next enrolment. The insert now names a column that older
      databases do not have, and the statement is idempotent.
- [ ] 4.2 (operator) The seven accounts enrolled before this have no handle. They
      withdraw as far as being refused; their keys come off at
      `openrouter.ai/settings/keys`, where each is named after its address.
