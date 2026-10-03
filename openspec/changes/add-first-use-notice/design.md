## Context

`scinumbers-pending` (`pending.py`) already answers "who is waiting on the operator"
from the trail: read-only SQL aggregates, its own connect and statement timeouts,
silent when nothing is waiting, a failure printed and exit 1. It reaches the
database through the Neon control plane (`neon.branch_id` / `neon.connection_url`),
which needs the organisation-scoped Neon API key.

Both events this change needs are already written: `signin.admitted` by
`web.establish_identity` (so a reader who asks nothing is still observable,
ADR-0810) and `question.asked` by the agent. `user_email` is stamped on every record
of a session that passed the door. See proposal.md for motivation.

The scheduled side already has a pattern: `keepalive.yml` runs hourly, and
`keepalive-digest.yml` turns failures into one comment on a standing issue — GitHub's
own per-run failure mail is switched off for the account.

## Goals / Non-Goals

**Goals:**
- Report each reader once per first (sign-in, question), combined when both land in one
  window; silent otherwise; read-only; no new state.
- A scheduled job whose credential can read the trail and nothing more.
- A failure of the job itself is not silent.

**Non-Goals:**
- Not a notification system: no per-reader history, no unsubscribe, no digest of
  activity beyond "first seen".
- No marker rows, no writes of any kind (see Decision 2).
- No change to the agent, the drivers, the schema or what the trail records.
- Not an uptime monitor for the app; `keepalive` does that.

## Decisions

**1. A sibling module, `first_use.py`, not a mode of `pending.py`.** Pattern: *harness
command over the trail* — the same shape as `pending`, `enrol` and `evaluation`, and a
member of the `HARNESS` set in `tests/test_driver_independence.py`. A `--first-use`
flag on `pending` would put two credential paths in one `main` (control plane versus a
plain URL) and two silence contracts in one report. It *imports* `pending`'s
`STATEMENT_TIMEOUT_MS`, `CONNECT_TIMEOUT_S` and the `trail_store.engine_from_url`
constructor rather than copying them: two copies of a timeout chosen for a cold Neon
start are one that gets fixed and one that does not. Console script
`scinumbers-first-use`. *Alternative rejected:* extending `pending` — smaller diff,
wrong seam.

**2. Stateless window (option B), not a marker row (option A).** "First" is derived:
```sql
select lower(user_email) as address, min(at) as first_at
from {table}
where event = :event and user_email is not null and user_email <> ''
group by 1
having min(at) > now() - make_interval(mins => :minutes)
```
once per event kind, joined on address so one row says what was first seen. The
window is `--minutes`, default 70 for an hourly schedule. **A repeated notice is the
cheap error and a missed first reader the expensive one**, so the window is longer
than the interval and the code says so where the default is set — otherwise the next
person trims it to "exactly an hour" and the overlap that absorbs a skipped tick is
gone. Option A (write `operator.notified` rows after reporting) was rejected: it makes
a read-only, point-it-at-production command a writer; it gives at-most-once delivery
that fails the *wrong* way when the mail then fails; and it needs a second credential
with insert rights. *What it costs:* a tick delayed past the window loses a reader,
and a tick inside the overlap repeats one. The delays actually seen are measured from
the keepalive's run history before the default is trusted (tasks).

*A scan the window cannot bound.* "No earlier event" needs the whole history, so unlike
`pending` the aggregate cannot be limited by `at`. It is filtered by `event` and run
under the 30 s statement timeout; at current trail size that is a table scan of a few
thousand rows. The role cannot create an index; if the live test shows it is slow, an
index on `(event, at)` is a schema change the operator makes, not this command.

**3. A read-only role and a database URL, not the Neon API key.** The command reads
`SCINUMBERS_TRAIL_READ_URL` (a `postgresql+psycopg://` URL) and never touches `neon.py`.
`sql/first_use_reader.sql` creates a login role with `select` on three columns of the trail (`at`, `event`, `user_email`)
— **not on `accounts`**, because nothing here reads it, and a grant that nothing needs
is the one that gets abused. The password is a placeholder in the file and set by the
operator. Pattern: *least-privilege credential per caller* — the guard belongs to the
credential, not to the command's good behaviour (a bug in the command still cannot
write). Neon keeps roles per branch, so the role is created on the branch the
deployment writes to, and the secret's URL names that branch.
*Alternative rejected:* the Neon API key in a secret — it can delete the project.

**4. Output and exit contract copied from `pending`.** One block per reader on stdout,
nothing when no one is new, exit 0; any failure to read prints a sentence to stderr and
exits 1; a non-positive window or a missing URL exits 2. A reader line:
`address — signed in 14:03, first question 14:09`, with only the firsts that fall in the
window. Exclusions: repeatable `--exclude ADDRESS`, compared lower-cased, applied in
Python after the query (a handful of addresses; no reason to build SQL from them).

**5. Delivery through a standing issue, and the failure path through the digest.**
`first-use.yml` runs the command; a non-empty report becomes a comment on one open
issue titled `first use` (created if absent) — the same `gh issue` calls the digest
uses, `issues: write`, the built-in token. A comment on an issue the bot opened mails
the owner only if the owner is watching the repository, which is *unverified for this
account*: the workflow takes a `test` dispatch input that posts a clearly-marked test
line, and the first task of the rollout is to see that mail arrive (the digest rests
on the same assumption and has never delivered one either).

Because GitHub's failure mail is off, **a failing `first-use` run would be silent** —
the spec requires it not to be. So `keepalive-digest.yml` widens from one workflow to a
list (`keepalive.yml`, `first-use.yml`), reports each by name, and its standing issue
is retitled `scheduled workflow problems`. Same two conditions as today: failed runs,
and no runs at all.

The cron is `23 * * * *` — off the top of the hour and off keepalive's `:17`. A
`concurrency` group keeps two ticks from overlapping. The excluded addresses come from
a repository *variable* (`FIRST_USE_EXCLUDE`), not the workflow file.

**6. Privacy, recorded as a decision.** The issue comment carries reader addresses; the
command writes its report to a file, so the Actions log does not. The issue is visible to
repository collaborators only while the repository is private; making it public publishes
them. ADR in block `1250`–`1290`, and the
workflow carries a comment saying so beside the line that prints them.

## Risks / Trade-offs

- **A reader lost to a delayed tick** → window longer than the interval; measure real
  delays from run history; widen with `--minutes` (no code change) if they exceed it.
- **A reader reported twice** → accepted, named as the cheaper error in code and spec.
- **Owner never receives the issue mail** → test dispatch input; verify before
  relying on it; the fallback is the owner subscribing to the issue.
- **The read-only role missing on the target branch** → the first run fails loudly
  (exit 1), which the widened digest turns into one comment; the live test also
  asserts the role cannot write or read another table.
- **Slow full-history scan as the trail grows** → 30 s timeout surfaces it as a
  failure, not silence; index is the escape hatch.
- **Reader addresses in logs** → private repository only; ADR.
- **Scheduled workflows run from `main` only and GitHub pauses them after 60 days
  without activity** → the widened digest already reports "no runs at all".

## Migration Plan

1. Operator creates the role on the deployment's Neon branch (`sql/first_use_reader.sql`)
   and sets its password.
2. Operator adds the repository secret `SCINUMBERS_TRAIL_READ_URL` and variable
   `FIRST_USE_EXCLUDE`.
3. Merge to `dev`, then `main`; push (scheduled workflows exist only on `main`).
4. Run `first-use` by hand with `test: true`; confirm the mail arrives; run it once
   plain and confirm it is silent.
5. Rollback: disable the workflow in the Actions tab and `drop role`; nothing else was
   changed, so there is nothing to undo in the data.

## Open Questions

None that change the build. The deployment writes to the Neon branch **`alpha`**
(stated by the operator, 2026-10-02), so the role is created there and the secret's
URL names that branch; `dev` and `production` get neither.
