# ADR-1350: A quiet week sends one message, measured from the last delivery

- **Status:** accepted
- **Date:** 2026-10-04
- **Pull request:** none yet (`feat/first-use-heartbeat`)

## Context

The first-use notice is silent when nobody is new (ADR-1250), so a quiet week and a broken
check look the same: no mail either way. This was not hypothetical. The check ran for a day
with a window that saw a quarter of arrivals (ADR-1290) and nothing said so; the operator
noticed because they were testing it.

The workflow's delivery step posts a comment on one standing issue only when there is
something to say. It already has `actions: read` and `issues: write`.

## Decision

After **seven days with nothing delivered**, the delivery step posts one comment saying the
check found no new readers, and the check does nothing else differently.

- **In the workflow, not the command.** `scinumbers-first-use` still prints nothing when
  nobody is new; that silence is a requirement (`user-identity`) and is pinned by tests. The
  heartbeat needs the standing issue, the run history and the clock of the last delivery, all
  of which the step already knows and the command should not.
- **The seven days are measured from the last delivery: the newest of the issue's creation
  and its comments**, via `gh issue view N --json createdAt,comments --jq '[.createdAt,
  .comments[].createdAt] | max'`. A report, a `test` line and an earlier heartbeat all restart
  the week, so heartbeats space themselves and a busy week sends none. **The issue is the
  state**; nothing is written to the trail, the database or the repository.
- **The message states what the check found, with its own numbers:** "This check ran at
  <UTC>. It found no new readers in the last 7 days. N checks completed in that time, this one
  included. If you expected someone, the check may be what is wrong, not the readers." N is
  the count of successful runs in the last seven days plus one for the run that is writing it.
  It reports an observation and never claims that nobody exists; a test pins both.
- **It follows a successful query.** The step runs after the command under `bash -e`; a failed
  read fails the job (and the digest reports it) before a heartbeat is considered. A heartbeat
  therefore also means: the workflow ran and the trail was readable.

**Assumptions, flagged:**
1. A comment a person writes on the issue also restarts the week. Restricting it to the bot's
   comments would need the bot's login, which `gh` has spelled differently across versions;
   the cost of the simpler rule is a heartbeat delayed by a week.
2. **With no standing issue there is no heartbeat.** The first post creates the issue and
   starts the clock. Creating the issue with a heartbeat would announce "no new readers"
   before any week had passed.

*Rejected:* a separate weekly workflow (a second schedule, with the same throttling, and a
second place for the issue lookup to drift); a flag on the command (it would have to reach
GitHub); a marker row in the trail (it makes a read-only command a writer, ADR-1250).

## Trade-off accepted

About one extra mail a week in a quiet period. It is not an alarm: the latency is a week plus
the schedule's slop, and a workflow that stops entirely sends no heartbeat at all, which is
what the digest is for (it reports a workflow that failed or never ran). If the standing issue
is closed or deleted there is nothing to measure from, so no heartbeat is sent until a report
recreates it. A person's comment on the issue delays one by a week (assumption 1).

**What was verified.** Against GitHub, read-only, on 2026-10-04 (timestamps and counts only,
never bodies, because real reports contain reader addresses): `gh issue view 1 --json
createdAt,comments` returns `createdAt` and a `comments` array; the step's own `--jq` returned
the issue's creation time when it had no comments; the seven-day run count returned 3; and the
exact-title filter found issue #1. In the tests, the step is *executed* against a stub `gh`
that applies the caller's own `--jq` with real `jq`: a quiet week delivers exactly one message
and opens with the mention; six days and ten minutes short of seven deliver nothing, ten past
deliver one; the newest comment decides whatever it was, and old comments do not postpone a
due message; a message just delivered is not repeated by the next run; no standing issue
delivers nothing and the step still succeeds; a real report is delivered as before with no
heartbeat added; a `test` run posts only its line; the wording observes and never asserts that
none exist; the count is successes plus one and asks for this workflow's successful runs in
the last week; a failed read fails the step. Sixteen defects were then seeded into a copy,
each with a green baseline first, and each was caught by the test written for it: a message on
every quiet run, the clock read from the issue's creation only or from the oldest delivery,
six or eight days, a message with no issue, the mention dropped, wording that asserts none
exist, the count without this run / of another workflow / of any run / ignoring the week, the
message replacing a real report or a test line, a swallowed failed read, a new issue each time.
One blind spot was found by reasoning before seeding rather than by a survivor: a failing step
would have hidden "a message with no issue", so that test now also asserts the step succeeds.

**Not verified:** a real heartbeat on GitHub's runners. It cannot come before seven days after
the last delivery (after 2026-10-10T21:56Z if nothing else is posted), and that arrival is the
live check.
