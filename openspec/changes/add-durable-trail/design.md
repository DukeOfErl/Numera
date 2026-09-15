# Design — add-durable-trail

## Context

See `proposal.md` — Why. The constraints that shape the approach:

- **The host's disk is not storage.** Streamlit Community Cloud's container
  filesystem does not survive a reboot or redeploy, and the app sleeps after 12
  hours of no traffic. Anything that must outlive a session leaves the container.
- **Writes happen on the render path.** Streamlit re-runs the script on every
  interaction, so a slow or hanging write degrades the page directly.
- **`trace.py` already has the right seam.** `QuestionTrace.run_config()` returns
  the `run_name` / `tags` / `metadata` shape, and `agent.py` merges it into the
  agent's config. Adding a key there is a change in one place.
- **The dependency direction is asserted by a test.** Adapters may reach into the
  core; the core may not reach back. A sink that imports Streamlit must not be
  importable from the agent's core, and `tests/test_driver_independence.py` will
  say so.

## Goals / Non-Goals

**Goals.** Records outlive the container. Every record names its session as well
as its question. A rendered item can be traced to the question that produced it.
A store that is down is invisible to the person asking.

**Non-Goals.** Not a metrics system, a dashboard, or an alerting path — the
records are read with SQL, by hand. Not a replacement for a hosted tracer, which
answers a different question. Not a move of the checkpoints or the spend ledger,
which stay in SQLite; only the trail moves, and only additively.

## Decisions

### D1. Neon serverless Postgres, over four alternatives

Chosen for one disqualifying property in each of the others, not on preference.

- **Supabase** — free projects pause after 1 week of inactivity (its own docs),
  with a 10–30 s cold start on the next request. For an alpha with intermittent
  testers, that breaks the app precisely during the lull when nobody is watching.
  The standard mitigation is a cron job whose only purpose is to stop the
  database being switched off. Verified 2026-09-14, not taken from memory.
- **Turso** — the free tier is excellent and there is no cold start at all, but
  the remote Python client its docs point at had a single release seven weeks
  old, its predecessor is archived, two others are deprecated, and the vendor's
  own roadmap announces the server going proprietary.
- **Firestore** — works, but no `GROUP BY`; counting moves into the client. The
  data here is counted.
- **Google Sheets** — genuinely viable at this volume and pleasant to eyeball,
  but no `GROUP BY`, and a service-account credential for the same setup cost.

Postgres also keeps the SQL we already write. `run_ledger.py`'s
`ON CONFLICT ... DO UPDATE SET x = x + excluded.x` is Postgres syntax that SQLite
adopted, so a later move of the ledger — out of scope here — would not be a
rewrite.

**Measured, not assumed** (from a developer machine in Europe against
`us-east-2`; PostgreSQL 18.6):

| | |
|---|---|
| connect, cold | 3.16 s |
| connect, warm | 1.90 s — the vendor documents "a few hundred milliseconds" |
| INSERT one row | 509 ms median |
| SELECT count(*) | 496 ms |
| GROUP BY | 493 ms |

All three statements costing the same is the tell that this is network
round-trips, not work. Community Cloud is US-hosted and same-region, so the
deployed figure should be far smaller — **and it is the deployed figure that
matters, so it must be measured rather than inferred from these.**

### D2. `st.connection("sql")`, over psycopg plus `@st.cache_resource`

Streamlit's own component, per the project convention of preferring the
library's. It caches the engine at **global scope across sessions**, so the
engine is built once per container rather than once per rerun — without which
every rerun would pay TCP, TLS and Postgres auth before its INSERT, which is
exactly the cost that would make writing on the render path untenable. It also
provides `.reset()` for a stale connection or an expired token, which a
hand-rolled equivalent would have to grow.

Two traps this commits us to avoiding, both verified against the docs:

- **`.query()` is never used for writes.** It caches like `@st.cache_data`, with
  no TTL by default. It exists for read dashboards. Writes go through
  `conn.session`.
- `pool_pre_ping` and `pool_recycle` are set, because the container sleeps after
  12 hours and the far side will have dropped every connection the engine
  believes it holds.

### D3. Fail open, and the refusal lives in the operation

Spelled out in the spec because it inverts the system's other write policy and an
inconsistency spotted later would be "fixed" the wrong way.

The swallow is **inside the recording function, not at the call site.** This is
`guard.py`'s lesson pointed the other way: that guard had to move out of the
driver because a refusal in one driver protects one caller. Here a *tolerance* in
one driver leaves the next caller — a harness, a test, a second interface —
holding an operation that raises. Same principle, opposite polarity.

No retry: an unreachable store hangs rather than failing fast, and a retry
doubles a half-second on the render path to buy a row that by construction does
not matter.

No buffering in `session_state` to flush later. It is the appealing answer and it
is wrong: session state dies with the container, which is *exactly* the storage
we are escaping.

A module-level failure counter, readable without grepping a log, so that "nothing
has been recorded for three weeks" is a question that can be answered. The hazard
of failing open is never the lost row.

### D4. Two sinks, not a replacement

The file sink stays and the durable sink is added beside it. A developer running
locally needs no database, and the existing tests read the file. Configuring no
destination must leave behaviour identical to today — otherwise the absence of
telemetry becomes an outage, which is the failure this design exists to prevent,
one level up.

### D5. One append-only table, not one per record type

`(id, ts, session_id, question_id, event_type, detail)` with `detail` as
`jsonb`. Append-only: no update, no delete. A new record type is a new
`event_type` value rather than a migration, and every question worth asking is a
`GROUP BY` over one table.

`user_email` is included from the start, nullable, and left null until
identity exists. It costs nothing now, and adding it later would leave the
earliest rows — from exactly the period most worth understanding — permanently
unattributable.

### D6. `session_id` into `run_config()`; `question_id` onto `Item`

`session_id` joins `question_id` and `run_label` in the metadata dict `trace.py`
already builds, so any tracer added later inherits it with no further change.

`question_id` onto `web.Item` is here rather than in the feedback change that
needs it, because it cannot be retrofitted onto items already rendered, and
because the alternative key is unsafe: the transcript's list index looks stable
(the list is append-only today) but `web.transcript` lives in session state
alone, so a reload of the same `?session=` restarts indices at 0 while the
conversation continues — and `(session, 0)` would then name two different
questions.

## Risks / Trade-offs

- **Deployed latency is unmeasured** → the figures above are an upper bound from
  the wrong continent. Measure from the deployed app before trusting them, and
  record the number rather than the reassurance.
- **Neon free-plan branches archive to S3 when inactive, with no published
  restore latency** → after a quiet week the first write may cost far more than
  the warm figure. Measure once after a real idle period.
- **A write on the render path is still a write on the render path** → bounded by
  an explicit short timeout and no retry, so the worst case is bounded rather
  than absent.
- **Two sinks means a record can reach one and not the other** → acceptable and
  deliberate: the file is a developer convenience, the table is the record.
- **The deploy branch promotes `ask` into `[project].dependencies`** → the new
  dependencies must reach that arrangement before the next deploy, or the app
  starts without SQLAlchemy. It is in that branch's documented contract; it is
  listed here because "documented" and "remembered" are different things.
- **A secret in one more place** → the connection URL carries a password. It goes
  in `.streamlit/secrets.toml`, now gitignored by path and by bare name, and in
  the Community Cloud secrets box. Never in the repository.

## Migration Plan

Additive throughout; there is nothing to migrate. The table is created on demand
(`CREATE TABLE IF NOT EXISTS`), matching how `run_ledger.py` already behaves.
Rollback is removing the configuration: with no destination configured the app
runs as it does today, which is the same path exercised by every existing test.

## Open Questions

- Retention. Rows are small and the volume is an alpha's, so nothing needs
  deciding now; it becomes a question when the free tier's 0.5 GB is in sight,
  and answering it later changes neither the spec nor the schema.
