# ADR-1250: The first-use notice is a sibling command over a stateless window

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** none yet (`feat/first-use-notice`)

## Context

The operator enrols testers by hand and wants to know the first time each one is
seen signing in (`signin.admitted`) and the first time each one asks a question
(`question.asked`). Both are already in the trail. `scinumbers-pending` already
shows the shape of a scheduled, silent-when-empty harness command over the trail.

Two designs were on the table for "only the first time":

- **A. A marker row.** After reporting, write `operator.notified` into the trail
  and skip readers who have one.
- **B. A stateless window.** A reader is reported when their earliest event of that
  kind falls inside a window; nothing is written.

**What the trail actually carries** (read-only queries against the database that
`.streamlit/secrets.toml` names, 2026-10-02; the operator identifies it as `dev`,
and it holds rows labelled both `alpha` and `dev`):

- `question.asked`: 109 rows. **All 27 in account sessions (`acct:*`) carry
  `user_email`.** The other 82 are non-account sessions (local and CLI runs) and
  carry none, as designed — the stamp lands on a session that passed the door.
- `signin.admitted`: 28 rows, 26 with `user_email`. All 26 stamped admissions are in
  sessions that asked nothing, so the event does exist for a reader who only signs
  in. The two without an address are from 2026-09-26 and 2026-09-28, and **17 of 17
  since 2026-09-29 are stamped**. The operator reads the two as old code on `dev`;
  I could not find the cause from the code or history, and did not test that.
- 1,395 trail rows in all. The full-history aggregate this decision needs
  (`min(at)` per address per event, no bound on `at`) is a sequential scan of 0.2 ms.

## Decision

**A sibling module, `first_use.py`, with console script `scinumbers-first-use`,
and option B.**

- A sibling, not a flag on `pending`: it takes a database URL where `pending` takes
  the Neon control plane (ADR-1260), and it has its own silence contract and report.
  It *imports* `pending`'s timeouts rather than copying them — two copies of a
  timeout chosen for a cold Neon start are one that gets fixed and one that does not.
  It is a harness module (`HARNESS` in `test_driver_independence.py`).
- **"First" is derived**: `having min(at) > now() - window`, per event kind, over a
  lower-cased address. An earlier event pulls the minimum out of the window, so one
  predicate says both "an event in the window" and "none earlier".
- **The window is 70 minutes for an hourly schedule**, and the code says why:
  a repeated notice is the cheap error and a missed first reader the expensive one,
  so the window overlaps its neighbour. Trimming it to 60 removes the overlap and
  nothing fails until a tick is late.
- Both kinds come back in one statement, joined on the address, so a reader whose
  firsts both landed in the window is one line. Exclusions are applied after the
  join, so an excluded reader disappears whole.

**Option A was rejected.** It turns a read-only command that is safe to point at the
live branch into a writer; it gives at-most-once delivery that fails the wrong way
(the marker is written, the mail then fails, the reader is never reported); and it
needs a second credential with insert rights.

## Trade-off accepted

No state means no guarantee: a tick delayed past the window loses a reader, and a
tick inside the overlap repeats one. The 70 minutes is a guess until the real gaps
between ticks are read out of the keepalive's run history (task 6.4). A reader whose
first `signin.admitted` is **unstamped** cannot be attributed — the session id is a
hash of the address and the link, so the address cannot be recovered from it — and is
missed until they ask something. Two such rows exist, none recently.

**What was verified.** The first-seen semantics were run against real Postgres: a
first sign-in, a first question, both in one window (one row), a sign-in that is not
the first (not reported), a returning reader asking for the first time (reported for
asking only), one address in two spellings (one reader), records with no address,
the window boundary, and other events (`tests/test_first_use_live.py`, 11 tests,
run outside the sandbox because libpq cannot resolve hosts inside it). **Not yet
verified:** that the tests can fail — the seeded defects of task 4.1 have not been
run, so nothing here claims a particular mutant dies; and the numbers above come from
the `secrets.toml` database, not from `alpha`, where the deployment writes.
