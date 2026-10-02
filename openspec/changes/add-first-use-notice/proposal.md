## Why

The operator enrols testers by hand and has no way of knowing when one of them
actually *uses* the app. The first sign-in and the first question are the moments
worth knowing about — a tester who signs in and asks nothing is a different problem
from one who never arrives — and the trail already records both. Today the only way
to notice is to read the trail.

## What Changes

- A new harness command, sibling of `scinumbers-pending`, that reports each reader
  **the first time they are seen**: once for their first sign-in (`signin.admitted`)
  and once for their first question (`question.asked`). When both firsts for the same
  reader fall inside one run's window, one message covers both.
- It is **silent when nothing is new** — prints nothing, exits 0 — so a scheduled
  run produces output only on an hour when someone arrived.
- It is **stateless and read-only**. "First" is derived from the trail (an event in
  the window with no earlier event of that kind for the same address), so it writes
  nothing and is safe to point at the live branch. The cost is a window, not a
  marker: a skipped tick can miss a reader, an overlapping one can repeat one.
- It reads the trail through a **dedicated read-only Postgres role**, via a database
  URL in the environment — not through the Neon control plane. The scheduled job
  therefore never holds the organisation-scoped Neon API key. The change ships the
  SQL that creates the role, for the operator to run once.
- An **hourly GitHub Actions workflow** (`first-use.yml`) runs it and comments on one
  standing issue, which mails the owner through GitHub. No mail credentials.
- The operator's own and test addresses can be **excluded**.
- `keepalive-digest` widens to cover this workflow too: GitHub's per-run failure mail is
  off, so without it a failing first-use job would be silent.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-identity`: adds requirements (no existing requirement changes) — the operator
  is told when a reader is first seen signing in and first asking a question, each
  at most once per reader per window, silently when nothing is new, and the job that
  asks holds a credential that can only read.

## Impact

- **Code:** a new harness module under `src/scinumbers_ask/` and a console script in
  `pyproject.toml`; named in the `HARNESS` set in `tests/test_driver_independence.py`.
  No agent-core, driver or schema change — both events are already written.
- **Database:** a one-time `create role` with `select` on the trail table only,
  run by the operator in Neon. `sql/` gains the script.
- **CI:** one new scheduled workflow, one repository secret (the read-only URL).
  Scheduled workflows run from `main` only, and GitHub may delay or skip a tick.
- **Privacy:** reader email addresses appear in an issue comment and in the Actions
  log. Acceptable while the repository is private; recorded as an ADR because making
  it public would publish them.
- **Docs:** README, CHANGELOG, `CLAUDE.md` module table, ADRs `1250`–`1290`.
