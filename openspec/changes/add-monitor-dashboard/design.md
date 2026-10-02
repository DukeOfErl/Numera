## Context

See proposal.md for why. The constraints that shape the approach:

- **The trail is one append-only table**, `trail(id, at, session_id, question_id,
  run_label, user_email, user_role, event, detail jsonb, prev_write_ms)`. A new
  kind of record is a new `event` value, never a migration (`trail_store.py`).
  The view reads this table exactly as it is.
- **Endings are scattered event names, not one record.** `ask` records
  `question.asked`, `answer.given` and `answer.evidence` as events pass through,
  but `QuestionEnded` itself is not written to the trail. A question's ending is
  therefore one of ten event names, and two of them carry the reason in their
  payload rather than in their name (decision 4).
- **Most of what a dashboard would want from Langfuse is already in the trail.**
  `question.answered` carries `spend_micro`, `model_calls` and `tool_calls`.
  `spend.increment` carries the model and the prompt and completion tokens per
  call. Time per question is the span between `question.asked` and the ending.
  What only Langfuse has — latency per model call, the span tree, the prompt as
  sent — is for looking into one question, and its UI does that better than
  anything rebuilt here.
- **Langfuse Hobby limits, read from langfuse.com/pricing on 2026-10-02:** Metrics
  API v2 is 100 requests per *day*; the general API is 30 per minute; data is
  accessible for 30 days; 2 alerts. Custom dashboards are included and do not
  count against the API limits.
- **Neon roles, read from neon.com/docs/manage/roles on 2026-10-02:** a role made
  in the console or through the API is a member of `neon_superuser`, which brings
  `pg_read_all_data` and `pg_write_all_data`. Such a role can never be read-only.
  A role made in SQL gets only the basic privileges of a new Postgres role, and
  its password needs at least 60 bits of entropy. Roles belong to a branch and
  are copied into branches made from it.
- **`accounts` holds `openrouter_key`.** A role that can read every table can read
  every tester's API key. `pending`'s enrolment query reads only `accounts.email`
  and `accounts.disabled`.
- **`test_driver_independence.py` allows exactly one module in `scinumbers_ask` to
  import Streamlit (`web`).**

## Goals / Non-Goals

**Goals:**

- One command shows the operator the alpha's state, read-only, from their laptop.
- The figures it shows are computed by plain functions that can be tested
  without Streamlit and without a database.
- When the application adds an ending, the view does not quietly miscount it.

**Non-Goals:**

- Deployment, a sign-in, or more than one viewer. If it is ever hosted, that is a
  new change with its own identity requirement.
- Any chart sourced from Langfuse. The Langfuse dashboards live in Langfuse.
- Alerting from this view. Langfuse's two Hobby alerts and `scinumbers-pending`'s
  cron mail are the alerting there is.
- Changing what the application records. In particular, recording a single
  `question.ended` row is considered below and deferred.
- Retention or deletion of anything the trail holds.

## Decisions

### 1. Its own package, `scinumbers_monitor`, and not a module of `scinumbers_ask` (ADR-1300)

The view reads a table. It does not drive the agent, does not put a question to
it, and has no business being able to. Placing it in `scinumbers_ask` would mean
either a second Streamlit importer there, breaking the single-importer test, or
listing it as a driver, which it is not.

As its own package, the dependency direction is plain: `scinumbers_monitor` may
import from `scinumbers_ask`, and nothing there imports it. It takes four things from there, and nothing else:

- `neon`, to resolve a branch name. It imports only the standard library.
- `hosted_trace.trace_id_for`, to derive a trace id. It is Langfuse's own
  `create_trace_id(seed=…)`, and a second copy of a derivation is one that drifts.
- `pending.waiting`, the door rule (decision 5).
- `trail_store`'s connect timeout and pool recycle, rather than new numbers.

The four are stated in one place, and a test asserts the package imports
nothing else from `scinumbers_ask`. If the view reached for `agent` or `web`,
that is the moment to stop and think.

*Alternatives:* a module in `scinumbers_ask` listed in `PRESENTATION` and
exempted from the single-importer test (weakens a guard to make room, and puts a
non-adapter in the adapters' set); a separate repository (duplicates the event
names and the schema, which then drift unseen).

No new extra. `ask` already carries Streamlit, SQLAlchemy, psycopg and Langfuse,
and charts use Streamlit's own (Altair ships with it). Add an extra only if a
dependency appears that `ask` does not have.

### 2. A role that can read `trail` and nothing else, made in SQL (ADR-1310)

`sql/monitor_role.sql` creates `scinumbers_monitor` with `LOGIN`, `CONNECT` on
the database, `USAGE` on `public`, `SELECT` on `trail`, and `SELECT (email,
disabled)` on `accounts`, a **column-level** grant. The door row reuses
`pending.waiting()`, and its enrolment query asks `accounts` whether an address
is enrolled and not disabled. Those two columns are all it reads, and the
addresses are already in the trail. `openrouter_key` and `openrouter_key_hash`
stay unreadable: Postgres refuses any statement that names an ungranted column,
`select *` included. The script deviates from Neon's documented read-only recipe
twice, deliberately:

- **No `SELECT ON ALL TABLES` and no default privileges.** That recipe would hand
  over every key in `accounts` today and every future table automatically. A
  table or column the view needs is granted by name, in the same change that
  reads it. The cheap direction is a view that errors on a missing grant, not
  one that can read keys.
- **`ALTER ROLE … SET default_transaction_read_only = on`** and a role-level
  `statement_timeout`. The grants already make writes impossible. These make the
  intent visible to anyone reading `\drds`, and bound a runaway query.

The script is idempotent: create if absent, then grant. The password is
supplied at run time with `psql -v` and never appears in the repository. It is
run once on `alpha`, and on `dev` for development. A branch made from either
inherits the role.

**How the view gets the password.** Neon's API reveals passwords for roles it
manages, and it is not documented whether that covers a role made in SQL.
Task 1.1 probes it. If it does, the view resolves the full URL by branch name
through `neon.connection_url(role="scinumbers_monitor")`, as `pending` does, and
nothing is kept locally. If it does not, the host still comes from the API by
branch name, and the password comes from `SCINUMBERS_MONITOR_DB_PASSWORD` in
the operator's environment. In neither case is a URL written to disk.

*Alternative:* connecting as `neondb_owner`, as `pending` does. It works today,
and it is exactly the "read-only because nobody wrote a write" the spec forbids.

### 3. Langfuse is linked, never queried (ADR-1320)

Each question row carries
`{LANGFUSE_BASE_URL}/project/{LANGFUSE_PROJECT_ID}/traces/{trace_id_for(question_id)}`.
The URL is built from the id; nothing calls Langfuse. The project id is a new
setting. The pattern is checked against a real trace in task 4.2 before it is
relied on.

The link is omitted for questions older than `TRACER_WINDOW_DAYS = 30`, the
Hobby access window.

*Why not query it:* 100 Metrics API requests a day is about fifteen page loads.
Its data is gone after 30 days, so any trend drawn from it is a trend over a
month that silently forgets. And the trail is the record (ADR-0750); the tracer
is a debugger. *The escape hatch, not built:* a nightly job that copies about
five Metrics API aggregates into a table of its own, well inside the daily
limit. It becomes worth building when someone wants per-call latency on the same
screen as the trail.

### 4. Endings classified from a declared map, with an unidentified bucket

The trail has no one-to-one map from end reason to event, so the map is keyed
by event:
`ENDING_EVENTS: dict[str, frozenset[str]]`, from each ending event to the end
reasons it can record. Most events record exactly one reason
(`question.answered` → `answered`, `spend.unpriceable` → `not_configured`, …).
Two record one of several, and name it in `detail["reason"]`:
`spend.limit_reached` (`spend_ceiling` | `run_budget`) and `provider.failed`
(`provider_failure` | `provider_limit`).

A question's ending is the **latest event that is a key of the map**. Its kind
is the set's single member, or `detail["reason"]` when it is a member of the
set. Records after the ending (`answer.given`, `answer.evidence`,
`feedback.*`) are ignored for classification; they follow `question.answered` in
time, because `ask` records them as events pass on to the driver. A question
with no mapped event, or whose `detail["reason"]` is missing or outside the
set, is **unidentified**, and the view shows its last recorded event.

Two tests keep the map honest. One asserts that the union of the sets is exactly
the set of `EndReason` values, so a new reason fails the suite until it is
mapped. The other asserts that every key is a string literal somewhere in
`src/scinumbers_ask/`, which catches a rename. A question recorded under an
ending added later, before the map knows it, still falls into unidentified,
never into answered. That is the spec's cheap direction.

*Considered and deferred:* having `ask` record one `question.ended` row with the
reason as events pass through, the ADR-0840 pattern. It would make
classification exact and self-maintaining, but it changes the application's
recording (an `agent-session` delta) and helps only rows written from now on.
The map is needed for history regardless. It is worth its own small change.

### 5. Plain functions over rows; Streamlit only draws

- `queries.py` holds the SQL: one statement per row of the view, parameterised
  by period, all `select`.
- `figures.py` holds pure functions from rows to the numbers shown, including
  the ending classification and the "rate beside its count" pairing.
- `app.py` is the only module that imports Streamlit.

Tests feed `figures.py` hand-built rows written from the spec, not output
photographed from a run. One live test runs every statement in `queries.py`
against a real branch under the read-only role, the way `test_trail_store_live`
and `test_pending_live` do. The offline double cannot reach SQL errors or grant
errors, and `pending`'s two defects were found only live.

The door row calls `pending.waiting(engine, …)` rather than restating its
queries. The spec says the rule *is* the daily check's, and one copy is how that
stays true.

### 6. No polling; cached reads; a refresh button

Each query result is cached with `st.cache_data(ttl=600)`, keyed on branch and
period. Nothing reruns on a timer. A **Refresh** button clears the cache. A
dashboard left open therefore issues no queries, and the Neon compute suspends
as it would without it.

### 7. Started by `scinumbers-monitor --branch <name>`, bound to localhost

The console script refuses without `--branch`, using `pending`'s wording pattern:
no default, because a silent answer from the wrong branch is worse than none. It
then execs `streamlit run` on `app.py` with `--server.address 127.0.0.1` and
`--server.headless true`, passing the branch through. The branch name is shown
in the page header and in the title of every row.

## Risks / Trade-offs

- **[A dashboard read wakes the database, and the next trail write looks warm.]**
  `prev_write_ms` after a quiet period is how cold starts are measured
  (ADR-0700). An operator opening the view just before a tester asks would mask
  one. → Accepted: it is human-paced and rare. The recording-health row says so
  beside the figure.
- **[A trace link for a question that was never traced.]** Tracing is per
  deployment (`SCINUMBERS_TRACING`), and the trail does not record per question
  whether a trace was sent. → The link may lead to "not found". Accepted for
  now: the trail cannot say more without an application change.
- **[The ending map lags a new `EndReason`.]** → The suite fails until it is
  mapped, and rows in the meantime land in unidentified.
- **[The Langfuse URL pattern changes.]** → One constant, checked in task 4.2.
  If it breaks, the link fails visibly.
- **[`pending`'s queries were tuned for a cron line.]** → `waiting()` takes an
  engine and returns rows. If its statement timeout (30 s) is too long for a
  page, that is passed in, not forked.
- **[Personal data on screen.]** Emails and comments. → Localhost only, no export
  button, no screenshots in the repository.

## Migration Plan

Nothing deployed changes. Operator steps, in order: run `sql/monitor_role.sql`
on `dev`, then on `alpha`. Set `LANGFUSE_PROJECT_ID` (and, depending on task 1.1,
`SCINUMBERS_MONITOR_DB_PASSWORD`). Configure the Langfuse dashboards and alerts
(task 6). Rollback is `drop role scinumbers_monitor` on each branch. The role owns
nothing, so it drops cleanly.

## Open Questions

- Whether Neon's API returns a connection URI for a role made in SQL. Task 1.1
  answers it, and either answer fits the design above.
- Which two Langfuse alerts are worth the Hobby allowance. Proposed: p95 latency
  of `ask` traces, and a count of error-level observations. Revisit once a week
  of alpha traffic has been seen in its dashboards.
