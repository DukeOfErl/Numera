## Context

`first-use.yml` runs on GitHub's schedule, which in practice fires every 4-7 hours
(ADR-1290). Its "Tell the operator" step posts a comment on one standing issue, `first
use`, only when the command's report is non-empty (or a test run asks for a line); an
empty report touches GitHub not at all. See proposal.md for why that silence is
ambiguous.

What GitHub returns, read on 2026-10-04 for issue #1 (timestamps only, no bodies):
`gh issue view 1 --json createdAt,comments` gives `createdAt` and a `comments` array
(empty at the time, so the issue's own creation, 2026-10-03T21:56:21Z, was the last
delivery). `gh issue list --json number,title,createdAt` carries `createdAt` too, and
`gh run list --workflow first-use.yml --status success --created ">=…"` counted 3 runs
in the previous seven days. All timestamps are ISO-8601 UTC with a trailing `Z`, which
sort correctly as strings.

## Goals / Non-Goals

**Goals:**
- One message about weekly while nothing is delivered, saying what the check found.
- No new state, credential, permission or schedule.
- A failed check never produces it.

**Non-Goals:**
- Not an alarm. The digest already reports a workflow that failed or never ran; this
  reports a check that ran and found nothing, at about a week's latency.
- Not a change to the command, the query, or the window (ADR-1290).
- Not a per-reader or per-day summary.

## Decisions

**1. In the workflow's delivery step, not in the command.** The command's contract is
"prints nothing when nobody is new", pinned by the requirement and by tests (ADR-1250).
A heartbeat needs three things the command should not know: the standing issue, the run
history, and the clock of the last delivery. Putting it in the step that already knows
all three keeps the command a pure read of the trail. *Rejected:* a flag on the command
(it would have to reach GitHub); a separate weekly workflow (a second schedule, subject to
the same throttling, and a second place for the issue lookup to drift).

**2. The seven days are measured from the last delivery, read from the issue.**
`max(createdAt of the issue, createdAt of each comment)`, via
`gh issue view N --json createdAt,comments --jq '[.createdAt, .comments[].createdAt] | max'`.
Any comment counts — a real report, a `test` line, an earlier heartbeat — so a report
restarts the week and heartbeats space themselves. The issue is the state, as GitHub's run
history is for the window (ADR-1290); nothing is written to the trail or the repository.
*Assumption, flagged:* a comment a person writes on that issue also restarts the week.
Restricting to the bot's comments would need the bot's login, which `gh` has spelled
differently across versions; the cost of the simpler rule is a heartbeat delayed by a week.

**3. Only when the report is empty, not on a test run, and only when the issue exists.**
A non-empty report is itself a delivery. A `test` run already posts. With no standing issue
there is nothing to measure from, so the first post creates it and starts the clock
(*assumption, flagged*): the alternative, creating the issue with a heartbeat, would make
the first run after a merge announce "no new readers" before any week has passed.

**4. The message states an observation, with the check's own numbers.**
```
@<owner>

This check ran at <UTC time>. It found no new readers in the last 7 days.
<N> checks completed in that time, this one included. If you expected someone, the check
may be what is wrong, not the readers.
```
N is the count of successful runs in the last seven days **plus one** (the running job is
not yet a success). The wording says what was *found*, never that nobody exists; a test pins
both. "When the last one ran" in the requirement is this run's own time.

**5. It follows a successful query, so it also says the check is alive.** The step runs after
the command under `bash -e`; a failed read fails the job (and the digest reports it) before
any heartbeat is considered. A heartbeat therefore means: the workflow ran, the trail was
readable, and nobody new was found. `concurrency: first-use` (not cancelling) already queues
overlapping runs, so a second run reads the comment the first posted.

## Risks / Trade-offs

- **About one mail a week when quiet** → accepted: it is the point. A busy week sends none.
- **Latency of a week plus scheduling slop** → acceptable for "is it alive", not an alarm;
  the digest covers a workflow that stops.
- **A person's comment on the issue delays a heartbeat** → accepted (Decision 2).
- **If the standing issue is closed or deleted**, `gh issue list --state open` finds none and
  no heartbeat is sent until a report recreates it → the digest still sees the runs; noted in
  the README.
- **GitHub's JSON shape could change** → the stub in the tests follows the shape read on
  2026-10-04, and a failed `jq` fails the step loudly rather than posting nothing.

## Migration Plan

1. Merge to `dev` and `main` (a change to a scheduled workflow takes effect from `main`).
2. No operator setup. The first real heartbeat is due seven days after the last delivery —
   after 2026-10-10T21:56Z if nothing else is posted — and is the live check.
3. Rollback: revert the workflow step; the issue keeps whatever was posted.
