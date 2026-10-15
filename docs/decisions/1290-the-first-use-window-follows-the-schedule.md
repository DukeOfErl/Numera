# ADR-1290: The first-use window runs from the previous successful run

- **Status:** accepted
- **Date:** 2026-10-04
- **Pull request:** none yet (`fix/first-use-window-from-last-run`)

## Context

ADR-1250 chose a stateless window of 70 minutes for an hourly schedule, reasoning that
a repeat is the cheap error and that ten spare minutes would absorb a late tick. It
left the real tick delays to be measured after a week (task 6.4).

The first real data came in a day, from the operator's own test (2026-10-04, read from
GitHub's run history, read-only):

- `keepalive` ran 7 scheduled intervals over about 32 hours where hourly would give 32.
  Median gap 4 h 32 m, longest 6 h 18 m; **every gap exceeded 70 minutes**.
- `first-use` itself ran at 01:41Z and 08:32Z, 6 h 51 m apart, and posted nothing:
  neither window contained an arrival.
- The standing issue had no comments; the "TEST" mail the operator received was the
  issue's creation.

GitHub throttles scheduled workflows, so the schedule is a hint and not a clock. A
70-minute window over ticks 4-7 hours apart sees roughly a quarter of arrivals; the
operator's own test fell in a gap and produced no mail. The failure ADR-1250 named as
the expensive one was the normal case.

## Decision

**The window is "since the previous successful run", read from GitHub, plus six minutes.**

- Before running the command, the workflow asks `gh run list --workflow first-use.yml
  --status success --limit 1` for when the last success began, and passes the time since
  then as `--minutes`. Six minutes are added so a run that queued before it started cannot
  open a gap between two windows.
- **With no earlier success** it passes nothing, and the command's own default applies:
  `DEFAULT_MINUTES`, now **420 (7 hours)** -- the operator's choice, to match how often the
  schedule really fires. The longest gap seen was 6 h 51 m, so the margin is nine
  minutes; acceptable only because it is a fallback.
- **A failed or cancelled run is not a success**, so the next run covers its gap. A run
  whose comment could not be posted fails the job, so it is not a success either.
- **Capped at 7 days**, so a long outage becomes one large first report and not an
  unbounded query.
- The workflow gains `actions: read`. It is read-only and the only addition; the one write
  permission is still `issues`.
- The database stays read-only and the command keeps no state. The state is GitHub's own
  run history, which the workflow already depends on.

*Rejected:* a longer fixed window plus **deduplicating against the standing issue's
comments** (read what was already posted, drop those readers). It would remove misses but
reintroduce repeats on every run, and it needs parsing of free-text comments. *Rejected:*
an external scheduler that calls `workflow_dispatch` on the hour -- more reliable, but a new
credential (a token that can start workflows) for a notice that tolerates being hours late.

## Trade-off accepted

The window now depends on GitHub keeping its run history. It does so for about 90 days by
default; if a run is deleted the next window falls back to seven hours or reaches further
back, which only repeats readers. A manual `workflow_dispatch` that succeeds also counts
as "the previous run", which is correct, because it queried the trail too.

Repeats shrink to the six-minute overlap plus however long a run waited before starting.
Notices can still arrive hours after the event: the schedule is a hint, and nothing here
makes it hourly. `keepalive` is subject to the same throttling; its gaps (longest 6 h 18 m)
are inside Streamlit's 12-hour sleep limit, but the margin is thinner than "hourly" implies.

**What was verified.** The step is executed in `tests/test_scheduled_workflows.py` against
a stub `gh` and a stub `uv`: three hours since the last success gives about 186 minutes; two
minutes gives at least eight (the overlap); the newest success decides, not an older one;
no earlier success passes no `--minutes`; a month's outage is capped at 10,080; only
successful runs of this workflow are asked for; exclusions still pass; the report lands in a
file; a failing command fails the step. Eleven defects were seeded into a copy -- the fixed
window restored, the cap and the overlap removed, the oldest success used, any run counted,
a window passed with no earlier run, the fallback shrunk to 70 or 60 minutes, `actions:
write`, a swallowed failure, the wrong workflow's history -- each with a green baseline, and
each was caught by the test written for it. **Not verified:** the behaviour on GitHub's
runners (the next scheduled run is the first), and that the operator's own test arrival will
be reported -- a reader who arrived before the previous run's window is not recovered by this
change.
