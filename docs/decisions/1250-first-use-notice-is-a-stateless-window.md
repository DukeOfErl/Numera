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

No state means no guarantee. **The repeat is systematic, not a rare edge:** ticks are
60 minutes apart and the window is 70, so a reader whose first event falls in the 10
minutes before a tick is reported by two consecutive runs -- about one reader in six,
every time. The same arithmetic is the tolerance: a gap of more than 70 minutes
between two runs loses a reader, so a tick may be at most about 10 minutes later than
its neighbour, and GitHub's schedule jitter can exceed that. The 70 minutes is a guess
until the real gaps between ticks are read out of the keepalive's run history (task
6.4); a wider window removes misses and adds repeats, which is the limit of a design
that keeps no state. A review suggested deduplicating against the standing issue's
existing comments instead; not done, to be decided with the gap data. A reader whose
first `signin.admitted` is **unstamped** cannot be attributed — the session id is a
hash of the address and the link, so the address cannot be recovered from it — and is
missed until they ask something. Two such rows exist, none recently.

**What was verified.** The first-seen semantics were run against real Postgres
(`tests/test_first_use_live.py`, 14 first-seen tests, run outside the sandbox because
libpq cannot resolve hosts inside it): a first sign-in, a first question, both in one
window (one row), a sign-in *and* a question that are not the first (not reported), a
returning reader asking for the first time (reported for asking only), a new sign-in
beside an old first question, one address in two spellings, records with no address,
the window boundary for both kinds, and other events.

Defects were then seeded into a copy of `first_use.py`, with a green baseline first
(2026-10-02). **Offline, 8 of 8 caught**: case-sensitive exclusion, a report that
always claims both firsts, a default window trimmed to an hour, the read-only setting
dropped, a zero window clamped instead of refused, a swallowed read failure, a header
printed on an empty report, exclusion applied to half a row. **In SQL, against the
real database, 8 of 8 caught after one fix**: "first" dropped, `min` turned into
`max`, no case-folding, empty addresses let through, the full outer join made inner,
a wrong event for questions, and the window ignored for sign-ins or for questions.
**The first run left one survivor — the window ignored for questions.** Every "not the
first" case I had written was a sign-in, so a reader who had ever asked a question would
have been reported every hour, and no test said otherwise. Three symmetric question
tests were added and the mutant then died. The mapping above is therefore the one
that was tested, not the one that was first written.

**Not verified:** the numbers above come from the `secrets.toml` database, not from
`alpha`, where the deployment writes; and the real distribution of delays between
ticks, which sets whether 70 minutes is enough (task 6.4).
