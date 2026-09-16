# Roadmap

What is planned, in what order, and why — so none of it lives only in a session
transcript. **This file records decisions already taken.** It is not a proposal:
each work package below was agreed in conversation, and the detail belongs in its
OpenSpec change once that change is written.

Last reconciled: 2026-09-16, against the session that ran 2026-09-12 → 2026-09-16.

The governing goal is **multi-user alpha on a hosted deployment**: a handful of
named testers asking real questions, leaving usable judgements, against a corpus
whose answers can be traced afterwards.

## Order, and why it is this order

`durable trail → feedback → auth + roles → usage events + hosted tracing`

Feedback was deliberately moved **ahead of** auth. Without a way to capture what a
tester thinks, an alpha is a demo with extra steps, and the reason for having
users at all is much weaker. The cost accepted: feedback written before auth lands
carries a NULL `user_email`. That column exists from day one precisely so those
early rows are not permanently unattributable.

The trail had to come first regardless. Feedback keyed on anything but
`question_id` is wrong — the transcript's list index restarts at 0 when a session
is reopened while the conversation continues, so position names two different
questions — and an identifier cannot be retrofitted onto records already
collected.

---

## Done

### WP1 — Durable trail + `question_id` through the transcript
`add-durable-trail`, archived 2026-09-15. ADR-0700, ADR-0710.

The trail was being written to a file inside an ephemeral container, so every
search, alias resolution and spend increment from every real session was
discarded. Now also written to Neon Postgres, best-effort: recording **fails
open**, deliberately inverting the spend gate, because the cost of a lost row is
one row and the cost of failing closed is a reader blocked by a telemetry fault.

---

## In progress

### WP2 — Feedback capture
`add-answer-feedback`, 35/39 tasks. ADR-0740, ADR-0750, ADR-0760.

Thumbs up/down per answer, comment box on thumbs-down only, keyed on
`question_id`, stored as `feedback.verdict` / `feedback.comment` rows in the same
append-only `trail` table. Read back with `sql/feedback.sql`.

**Per-entry rating was scoped out on purpose, not forgotten.** The original ask
was a thumb per table row. One rating per answer ships first so we learn what
people actually complain about before building a UI for it; the comment hint asks
readers to name a problematic entry's ID, and those comments are the evidence for
whether per-entry rating is worth building. Nothing here forecloses it.

Remaining: verifier pass on the widget groups, README/CHANGELOG, archive, and the
deferred cosmetic below.

---

## Next

### WP2.5 — The question and the answer in the trail
**`add-question-and-answer-records`**, proposed 2026-09-16. ADR block `0840`–`0870`.
Planning artifacts complete; not implemented. Small, and blocking the value of WP2.

The trail records `question_id` but neither the question nor the answer, so a
thumbs-down says "answer `c23c83c16324` was wrong" with no way to learn what it
was answering. The text is on the events already (`QuestionStarted.question`,
`AnswerEntries.question`) for the drivers' sake; it simply never reaches
`trace.record`. This is a gap, not a decision — no comment anywhere argues for
omitting it.

Needs, all keyed on the existing `question_id`:

- the question as asked
- the answer as given
- **every entry id the answer was built on** — cited and retrieved both, which
  `AnswerEntries` already carries

Today only a partial reconstruction is possible: `search` rows hold the property,
organism and keyword terms plus the matching entry ids, so you can see what was
looked for but not what was asked.

Belongs to the trail, not to feedback, and wants a spec requirement of its own —
storing what people type is a decision to write down rather than slip in.

### WP3 — Auth, roles and the session cap
Reserved as `add-user-identity`, ADR block `0780`–`0830`. Not yet proposed.

- Google OAuth via `st.login`, `authlib>=1.3.2` in the `ask` extra.
- Five roles — student, scientist, senior scientist, dev, admin — with a
  `{Role: set[Permission]}` grant table. Permissions discussed: read, rate an
  entry, suggest a problem, rate AI prose, query aggregated results, ask for
  calculations, suggest an edit, edit with provenance. Roles later weight ratings
  and gate human review of the AI-generated database.
- `authorization.py` / `permissions.py` split, neither importing Streamlit.
- **Rate limiting means a global concurrent-session cap, not per-IP.** Streamlit's
  own docs say `st.context.ip_address` must not be used for security — it is
  trivially spoofed, and behind a proxy the client supplies `X-Forwarded-For`
  itself, so a per-IP limiter rate-limits honest users only. With each tester's
  spend capped at their own key, a limiter protects the *host* (RAM, CPU,
  instances), not cost. Worth stating in the ADR, because "rate limiting" reads as
  a cost control and here it is precisely not one.

**API keys: one per user, minted by the operator.** Not a shared key, and not a
key a tester supplies. OpenRouter's Management API mints runtime keys from a
management key, each with its own hard credit cap — which is exactly the shape
wanted: per-user spend isolation without anyone handing over a credential.

Verified against openrouter.ai/docs/features/provisioning-api-keys on 2026-09-16
(the feature is now called **Management API Keys**; a management key is created at
openrouter.ai/settings/management-keys and cannot itself call completion
endpoints):

| | |
|---|---|
| Endpoints | `GET/POST /api/v1/keys`, `GET/PATCH/DELETE /api/v1/keys/{hash}` |
| Fields | `name`, `limit` (credit cap), `disabled`, `limit_reset` (`daily`/`weekly`/`monthly`), `include_byok_in_limit` |
| Usage | per key: `usage`, `usage_daily`, `usage_weekly`, `usage_monthly`, `limit_remaining` |

**The tester never sees the key.** The operator mints one per allowlisted account
and the app looks it up server-side. That is what keeps this clear of Streamlit
Cloud's terms, which are about accepting *third-party* credentials — an earlier
note in this file claimed those terms ruled out per-user keys at all, which was
wrong. Nothing is accepted from anyone; the operator's own key is subdivided.

Consequences, none of them free:

- **`agent.py` has to change, not just the driver.** `default_model()` reads
  `OPENROUTER_API_KEY` from `os.environ` at call time — a process global. The
  credential must become a parameter threaded from the driver.
- **`web.resources()` is `@st.cache_resource`, so one `AskAgent` is shared by
  every browser session on the server.** The corpus repository should stay shared
  — it is the expensive index — but the agent must not be, or one tester's key
  funds another's questions.
- **Where the keys live.** A mapping from account to key, and it cannot be
  Streamlit secrets without a redeploy per tester. Neon is the obvious home, and
  that makes the trail database hold credentials, which it does not today.
  Decide deliberately when WP3 is proposed.
- **`limit_reset: monthly` means a tester who exhausts their cap recovers on its
  own.** Worth using: the alternative is the operator servicing an unlock request.
- **The ending already exists.** A spent key surfaces as its own ending
  (ADR-0600), so the refusal path for an exhausted per-user cap is built.

### WP4 — Usage events + hosted tracing
Depends on WP1 and WP3. Not yet proposed.

**Both the tally table and a hosted tracer were agreed — they are not
alternatives.** The table is the system of record; the tracer is a debugger.

- The usage-events table and its queries, with per-user attribution.
- LangSmith (or Langfuse) enabled **deliberately**, with `user_id` in the run
  metadata. `QuestionTrace.run_config()` already returns the `RunnableConfig`
  shape both read, and `agent.py` already merges it — per-user attribution is one
  more key in an existing dict, not a new mechanism.
- Per-answer verdicts pushed as scores with `extend_trace_retention=True`.
- Install the LangSmith skills: https://docs.langchain.com/langsmith/skills (or the langfuse skills)

**Why the tracer cannot be the record.** Feedback is a child of a run, the free
tier expires traces at 14 days, and max retention was cut 400 → 180 days on
2026-09-14. A rating that dies with its trace is not evidence.

⚠ **`langsmith` 0.11.0 is already installed** as a transitive dependency of
`langchain-core`. Tracing is off only because `LANGSMITH_TRACING` is unset —
setting that one variable, by anyone, at any time, immediately ships full prompts,
tool results and corpus text to a US-hosted service. Exposing corpus entries was
accepted; the point is that it must be a decision, not an env var nobody chose.

### WP5 — Cloud Run, and the ledger that has to move first
Not now. Revisit when the alpha outgrows Community Cloud.

**Per-user keys change what this costs, but do not retire it.** With a hard cap at
OpenRouter per key, the outer bound on spend is enforced server-side by someone
else, so a multiplied `run_budget` no longer risks unbounded money. What it still
does is report a bound that is not real — and `run_budget` is what the sidebar
shows a reader. A wrong figure on screen is a smaller problem than an unbounded
bill and a larger one than nothing.

**The severe finding, recorded here so the deploy cannot happen without meeting
it:** `run_ledger` and the LangGraph checkpoints share one SQLite file. Cloud Run's
filesystem does not persist and is not shared, so N instances means N independent
ledgers each starting at zero — a `run_budget` of $1.20 becomes N × $1.20 with N
chosen by an autoscaler. **A spend guard that multiplies by an unbounded
autoscaling factor is worse than no guard**, because the code, the tests and the
sidebar all keep reporting a bound that no longer exists. Conversations vanish the
same way, silently.

GCS Fuse and Filestore do not fix it — SQLite needs POSIX locking, and you get
corruption rather than an error. `max-instances=1` plus session affinity stops the
multiplication at the cost of capping capacity. The real fix is moving
`run_ledger` to Firestore, whose atomic `Increment` maps exactly onto the existing
delta-write design, comfortably inside Always Free. **This lands before the
deploy, not after.** Terraform was mentioned as a possibility, not decided.

---

## Separate lines of work, already open

Not part of the multi-user push; listed so the board is complete.

| Change | State |
|---|---|
| `add-answer-evaluation` | 23/43 — the evaluation harness and its judged layer |
| `add-provider-limit-ending` | 29/31 |
| `add-answer-shape` | 0/10 — an answer leads with its quantitative conclusion |

---

## Environments

One Neon project (`sparkling-bread-74230014`), one branch per environment. Branches
are copy-on-write, so the free tier absorbs several.

| Branch | For | Create when |
|---|---|---|
| `production` | the deployed app | exists |
| `dev` | local development | now — see below |
| `test` | the `network`-marked live tests | now, if those tests are ever automated |
| `alpha` | the first named testers | when there are testers |
| `beta` | a wider group | when there is a wider group |

**`dev` is the one that matters today.** `run_label` is currently the only thing
separating local runs from real feedback, it is a text column in the same table,
and it only works if every query remembers to filter on it — `sql/feedback.sql`
queries 2, 3 and 4 do not. The asymmetry decides it: a wrong row in a dev database
costs nothing, a dev row counted as real feedback corrupts the one dataset this
whole feature exists to produce.

It is a configuration change, not a code change. Local `.streamlit/secrets.toml`
points at `dev`; the Community Cloud secrets box points at `production`. They are
already independent — currently just aimed at the same place.

**`test` earns its own branch rather than sharing `dev`.** `test_trail_store_live.py`
creates tables and inserts rows; pointed at `dev` it would pollute the database a
human is also reading by eye, which is how a test row becomes a puzzling
observation.

**No branch per feature.** Neon branching invites it, and it is the wrong unit
here: the schema is one table, and a feature branch buys isolation from a schema
change that is not happening.

---

## Deferred, deliberately

| Item | Why it is waiting |
|---|---|
| Per-entry ratings | Gated on what WP2's comments actually say |
| Grey thumbs | Cosmetic; the colour rule may not be matching. Raised 2026-09-15 |
| `ToolCallLimitMiddleware` | Deferred in `add-ask-agent` for unexpected consequences seen in `interv_preper`. Worth re-checking against the stock middleware, since the project prefers the library's own components |
| Terraform | Mentioned for a Google Cloud deploy; no decision taken |
