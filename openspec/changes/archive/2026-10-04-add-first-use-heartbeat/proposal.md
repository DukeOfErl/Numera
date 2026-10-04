## Why

The first-use notice is silent when nobody is new, by design. That makes a quiet week and
a broken check look identical: no email either way. The operator found this out the hard
way — the check ran for a day with a window that saw a quarter of arrivals, and nothing
distinguished "nobody came" from "the check is not working". A message that says the check
*found* no new readers turns the absence of mail into something that can be noticed.

## What Changes

- When **seven days have passed with nothing delivered** to the operator, the workflow
  posts **one** message saying the check found no new readers in that time, how many
  successful checks ran, and when the last one ran. It does not claim there are none —
  it reports what the check saw, and says that if someone was expected the check may be
  what is wrong.
- **Seven days are measured from the last delivery**: the most recent of the standing
  `first use` issue's creation and its comments, whatever they were — a real report, a
  manual test line, or an earlier heartbeat. A real report resets the clock; while nothing
  is new a heartbeat arrives about weekly; it is never repeated run after run.
- The standing issue is the state. Nothing is added to the trail, the database, or the
  repository, which keeps the command read-only and keeps GitHub's own record as the one
  place to look.
- It is delivered like the reports: a comment on the standing issue opening with the
  owner's @mention.
- **The command is unchanged.** `scinumbers-first-use` still prints nothing when nobody is
  new; the heartbeat belongs to the workflow's delivery step, so the command's silence
  contract is untouched.
- **Assumption, flagged:** if the standing issue does not exist yet, there is nothing to
  measure from and no heartbeat is posted; the first post creates the issue and starts the
  clock.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-identity`: the requirement that a new reader's arrival reaches the operator on a
  schedule currently says a run in which nobody is new delivers nothing. It changes to:
  delivers nothing, except that after seven days with no delivery the operator receives one
  message saying that no new reader was found.

## Impact

- **Code:** none under `src/`. One step in `.github/workflows/first-use.yml` ("Tell the
  operator") and tests in `tests/test_scheduled_workflows.py`.
- **Permissions:** none new — `actions: read` and `issues: write` are already held.
- **Spec:** one MODIFIED requirement in `user-identity`, carried as its full new text.
- **Docs:** README's first-use section, CHANGELOG, the workflow header comment, ADR-1350.
- **Operator:** one extra mail about weekly in a quiet period, and none in a busy one.
