# ADR-1270: The first-use notice is delivered as a comment on one standing issue

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** none yet (`feat/first-use-notice`)

## Context

The notice has to reach the operator without the operator asking, from a scheduled
GitHub Actions job. Options: a transactional-email API (a new account and a secret
that can send mail as the operator), or GitHub itself — a comment on an issue mails
the owner. The repository already uses the second for `keepalive-digest`, because
GitHub's own per-run failure mail is switched off for the account.

That switch matters here: **a failing `first-use` run would be silent**, and the
spec requires that a failure to read be loud, never indistinguishable from "nobody
new".

## Decision

- `first-use.yml` runs hourly (`23 * * * *`: off the top of the hour and off
  keepalive's `:17`). A non-empty report becomes a comment on the one open issue
  titled `first use`, created if absent; an empty report touches GitHub not at all.
  It needs `issues: write` and the built-in token, and **one secret**, the read-only
  database URL (ADR-1260). It holds no mail credential of any kind.
- **`keepalive-digest.yml` is widened** to a list of workflows (`keepalive.yml`,
  `first-use.yml`), reports each by name, and its standing issue is retitled
  `scheduled workflow problems`. A failing or silent first-use job reaches the
  operator once a day, through the same two conditions as before: runs that failed,
  and no runs at all (a paused schedule looks exactly like a passing one).
- A `test` dispatch input posts one marked line, so the mail path can be seen to
  work end to end without waiting for a reader.
- The operator's own and test addresses are the repository **variable**
  `FIRST_USE_EXCLUDE`, not literals in the file.

## Trade-off accepted

The whole delivery rests on one assumption **that has not been shown for this
account**: that GitHub emails the owner about a comment the Actions bot made. The bot
opens the issue, so the owner is not "participating" in it, and under GitHub's default
"Participating and @mentions" setting a comment alone would not mail anyone (GitHub's
documentation does not address a bot-opened thread; this is my understanding, not
something I verified). **So every comment begins with `@<repository owner>`**, in both
`first-use.yml` and `keepalive-digest.yml`: a mention is what that setting does notify
on, so no watch level has to be changed. For a repository owned by an organisation this
names the organisation, which is not what is wanted -- revisit if it ever moves.

**Verified 2026-10-03:** a manual run of `first-use` with `test` ticked, from `main`,
delivered the marked comment to the operator as mail (subject text received:
"TEST -- first-use mail check, 2026-10-03T21:56Z. Nobody arrived."). That shows the
whole chain for the first time -- the workflow ran on GitHub, read `alpha` through the
read-only role, posted to the standing issue, and the mail arrived with the mention in
place. It does not show *which* mechanism delivered it: whether the mention alone is
enough, or the account's watch settings would have delivered it anyway, was not
tried. Not yet seen: the digest's mail (same mechanism, never triggered), and a real
arrival.

Delivery is also up to an hour late and can be missed or repeated (ADR-1250), and a
failure notice is up to a day late — acceptable for a "someone arrived" message,
not for an alarm.

**What was verified.** `tests/test_scheduled_workflows.py` *executes* the shell steps
against a stub `gh` and real `jq`: a quiet hour makes no call at all; a report is one
comment on the existing issue and never a second issue; the first report opens it; the
digest reports a failing first-use run by name, reports a workflow that never ran, and
does not count a cancelled run; every comment, from either workflow, begins with the
owner's mention and still carries the report. Twenty defects were then seeded into a copy of the
workflows (a dropped silence guard, an issue per report, the digest forgetting
first-use or the no-run case, a colliding or daily schedule, a Neon or mail secret,
extra write permission, a floating runner, a committed address, the report printed to
the log, the test input defaulting on, the mention dropped, hard-coded, or posted with no
report, the digest commenting when empty) with a green baseline first; each was caught by
the test written for it. **Not verified:** that the workflow runs on GitHub's runners
at all (it cannot until it is on `main`), and the mail.
