# ADR-0700: Neon serverless Postgres holds the durable trail

- **Status:** accepted
- **Date:** 2026-09-15
- **Pull request:** _pending — `feat/question-id-trail`_

## Context

The trail is written to `logs/trace.jsonl` inside a Streamlit Community Cloud
container, whose filesystem does not survive a reboot or redeploy. Every record
from every real session had been discarded, so `agent-session`'s requirement to
log under a per-question identifier was satisfied in-process and its stated
purpose — "investigable after the fact" — was defeated. The failures that
requirement names are intermittent, so the run worth investigating is almost
never the one still in progress.

Anything that outlives a session therefore has to leave the container. Four
alternatives were on the table, and each was rejected for a specific
disqualifying property rather than on preference:

- **Supabase.** Free projects pause after one week of inactivity, with a 10–30 s
  cold start on the next request. Verified against its own docs on 2026-09-14
  rather than recalled: a prior project hit exactly this, and combined with
  fail-closed logic the app refused every user after a quiet week. The standard
  mitigation is a scheduled job whose only purpose is to stop the database being
  switched off. It also carries four documented gotchas we would re-inherit —
  prepared statements unusable through the transaction pooler (failing only after
  the sixth execution, so no test catches it), an IPv6-only direct connection
  unreachable from Streamlit Cloud, passwords needing percent-encoding, and a
  `statement_timeout` accepted and then silently ignored.
- **Turso.** The free tier is the best of the four and there is no cold start at
  all. Disqualified by its client and its direction: the remote Python client its
  own docs point at had a single release seven weeks old, the predecessor is
  archived, two others are deprecated — and Turso's roadmap announces edge
  replicas discontinued and the server going proprietary.
- **Firestore.** No `GROUP BY`. The data here exists to be counted.
- **Google Sheets.** Genuinely viable at this volume and pleasant to read by eye,
  but no `GROUP BY` either, and a service-account credential for the same setup
  cost.

## Decision

Neon serverless Postgres, US region, reached through `st.connection("sql")` — the
engine cached at global scope across sessions, so it is built once per container
rather than once per rerun.

Measured against the live endpoint rather than assumed (PostgreSQL 18.6, from a
developer machine in Europe against `us-east-2`): cold connect 3.16 s, warm
connect 1.90 s, INSERT 509 ms, `SELECT count(*)` 496 ms, `GROUP BY` 493 ms. All
three statements costing the same is the tell that this is network round-trips
rather than work. **These are an upper bound from the wrong continent** — the
deployed figure, from a US-hosted container in the same region, is the one that
matters and is not yet known.

Two behaviours of the pooler were established empirically, because the Supabase
precedent is a parameter that looked configured and was not:

- `options=-c statement_timeout=…` is **refused** at startup, loudly, with a doc
  link. Better than being ignored.
- `SET LOCAL statement_timeout` inside the transaction works, reports back the
  value set, **fires**, and does not leak to the next borrower of a pooled
  connection. Neon's own default is `0` — unlimited — so without it a hung
  statement hangs for ever.

## Trade-off accepted

A 5-minute idle suspend that cannot be disabled, whose resume the vendor
documents as "a few hundred milliseconds" and which we measured at 1.9 s warm
from Europe. Acceptable because the app itself sleeps after 12 hours, so nobody
waiting for a cold Streamlit container will notice the database.

Unquantified and knowingly carried: free-plan branches archive to S3 when
inactive, and Neon publishes no restore latency. After a genuinely quiet week the
first write may cost far more than the warm figure. This is measured by recording
each write's duration on the row rather than by a scheduled probe — a job that
pings the database on a timer keeps it warm and destroys the condition being
measured, which is the same self-defeating shape that ruled out Supabase.

We also accept a second place a secret lives: the connection URL carries a
password, held in `.streamlit/secrets.toml` and the Community Cloud secrets box,
never in the repository.

## Open after deployment

Two measurements belong to this decision and could not be taken before it was
deployed. They are recorded here rather than in the change's task list, because
that list is archived when the change completes and this file is not.

1. **INSERT latency from the deployed app.** The figures above are from a
   developer machine in Europe against `us-east-2`; Community Cloud is US-hosted
   and same-region, so they are an upper bound and not the number. Replace them
   here when measured, and say which is which — an unmeasured reassurance in a
   decision record is worse than an admitted gap.
2. **The first write after a genuinely idle week.** Free-plan branches archive to
   S3 when inactive and Neon publishes no restore latency. This is read out of
   `prev_write_ms` paired with the gap between row timestamps, never by a
   scheduled probe: pinging on a timer keeps the database warm and destroys the
   condition being measured.

A heartbeat reporting whether anything was recorded in the last seven days is
worth adding **after** (2) has a figure, and not before — a heartbeat is traffic,
and adding it first forecloses the measurement permanently.
