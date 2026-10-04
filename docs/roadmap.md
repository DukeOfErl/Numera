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

### WP2 — Feedback capture
`add-answer-feedback`, archived 2026-09-16 (`openspec/changes/archive/
2026-09-16-add-answer-feedback`), merged to `dev` as `cadd4a7`. ADR-0740,
ADR-0750, ADR-0760.

Thumbs up/down per answer, comment box on thumbs-down only, keyed on
`question_id`, stored as `feedback.verdict` / `feedback.comment` rows in the same
append-only `trail` table. Read back with `sql/feedback.sql`.

**Per-entry rating was scoped out on purpose, not forgotten.** The original ask
was a thumb per table row. One rating per answer ships first so we learn what
people actually complain about before building a UI for it; the comment hint asks
readers to name a problematic entry's ID, and those comments are the evidence for
whether per-entry rating is worth building. Nothing here forecloses it.

### WP2.5 — The question and the answer in the trail
**`add-question-and-answer-records`**, implemented 2026-09-16 on
`feat/question-and-answer-records`. ADR block `0840`–`0870`;
[ADR-0840](decisions/0840-what-a-question-s-trail-keeps.md) is the decision and
carries the reasoning this entry used to hold.

Three records on the existing `trail` table, keyed on the existing `question_id`
and needing no migration: `question.asked`, `answer.given` and `answer.evidence`
(cited and retrieved kept separable). Written in `agent.ask`, which now wraps the
work as `_ask`, so every one of the eight branches that can yield an `Answer`
records it — seven of them are endings, and an ending is exactly the answer a
reader rates down.

`sql/feedback.sql` query 2 now shows a rating beside the question it judged and
the answer it judged; 2b shows the evidence behind it.

**Not backfillable, and that is the whole reason this went before WP3.** The
ratings already on `dev` predate it and name questions whose words were never
kept anywhere; those columns are null for them for ever.

## Next

### WP3 — Auth, roles and the session cap
Built as `add-user-identity` on `feat/user-identity` (2026-09-16); moves to Done
at merge. The reasoning that used to live here is now where an implementer reads
it — this section points rather than repeats:

- **What the system must do:** `openspec/specs/user-identity/spec.md`, plus the
  two scenarios each added to `agent-session` and `answer-feedback`; the change
  itself is archived under `openspec/changes/archive/2026-09-16-add-user-identity/`.
- **Accounts in the trail database, keys in the clear, enrolment fails closed** —
  ADR-0780. **The session cap is a heartbeat registry, never per-address, and
  protects the host rather than the budget** — ADR-0790. **Default-deny, the
  pruning rule, and why the table has one column** — ADR-0800; the eight
  permissions considered and the seven dropped are listed there. **The role is a
  column written at record time** — ADR-0810. **One agent per session, handed a
  credential and never an identity; if the agent must ever know what is
  permitted, it is handed permissions, never the role** — ADR-0820.
- **The grant table itself** is `GRANTS` in `src/scinumbers_ask/permissions.py`,
  with the rule for growing it in the comment above.
- **Operator's steps** — the identity providers, `[auth]` in secrets, the
  `accounts` table from `sql/accounts.sql`, one capped OpenRouter key per tester
  — are in `README.md` §"Sign-in and enrolment".

**Since `add-open-enrolment` (2026-09-18):** sign-in is no longer Google-only —
any OpenID Connect provider is a sub-table in secrets and gets its own button,
and only an address the provider says it has verified is admitted (ADR-0880,
ADR-0890). The helper script below is no longer "left for later": it is
`scinumbers-enrol`, which mints the capped key and inserts the row in one step
and names the database branch every time (ADR-0900). Two operator steps remain
outside the repository and are in the README: creating the Auth0 tenant, and
publishing the Google consent screen so testers need not be listed by hand.

Kept here because it is operational reference an ADR would bury: OpenRouter's
**Management API Keys**, verified against openrouter.ai/docs/features/provisioning-api-keys
on 2026-09-16. A management key is created at openrouter.ai/settings/management-keys
and cannot itself call completion endpoints.

| | |
|---|---|
| Endpoints | `GET/POST /api/v1/keys`, `GET/PATCH/DELETE /api/v1/keys/{hash}` |
| Fields | `name`, `limit` (credit cap), `disabled`, `limit_reset` (`daily`/`weekly`/`monthly`), `include_byok_in_limit` |
| Usage | per key: `usage`, `usage_daily`, `usage_weekly`, `usage_monthly`, `limit_remaining` |

Use `limit_reset: monthly`: a tester who exhausts their cap recovers on their own
instead of the operator servicing an unlock. A spent key already surfaces as its
own ending (ADR-0600). The tester never sees the key; nothing is accepted from
anyone, the operator's own credit is subdivided — which is what keeps this clear
of Streamlit Cloud's terms about accepting third-party credentials.

Left for later, on purpose: the deletion path and any retention limit for what is
kept about a person (the spec says why: nobody to ask yet); re-reading enrolment
mid-session; withdrawal, re-keying and role changes from the command rather than
from `sql/accounts.sql`. The helper script itself has landed — see above.

### WP4 — Usage events + hosted tracing
Depends on WP1 and WP3. **Split:** hosted tracing is built as `add-hosted-tracing`
on `feat/hosted-tracing` (Langfuse Cloud EU, ADR-1000–1020, 2026-09-25) and moves to
Done at merge. The usage-events table is still to propose, as its own change.

**Both the tally table and a hosted tracer were agreed — they are not
alternatives.** The table is the system of record; the tracer is a debugger.

- The usage-events table and its queries, with per-user attribution.
- LangSmith (or Langfuse) enabled **deliberately**, with `user_id` in the run
  metadata. `QuestionTrace.run_config()` already returns the `RunnableConfig`
  shape both read, and `agent.py` already merges it — per-user attribution is one
  more key in an existing dict, not a new mechanism.
- Per-answer verdicts pushed as scores. (Langfuse has no retention flag; see ADR-1000.)
- Install the LangSmith skills: https://docs.langchain.com/langsmith/skills (or the langfuse skills)

**Why the tracer cannot be the record.** Feedback is a child of a run, the free
tier expires traces at 14 days, and max retention was cut 400 → 180 days on
2026-09-14. A rating that dies with its trace is not evidence.

⚠ **`langsmith` 0.11.0 is already installed** as a transitive dependency of
`langchain-core`. Tracing is off only because `LANGSMITH_TRACING` is unset —
setting that one variable, by anyone, at any time, immediately ships full prompts,
tool results and corpus text to a US-hosted service. Exposing corpus entries was
accepted; the point is that it must be a decision, not an env var nobody chose.
**Closed by `add-hosted-tracing`:** the agent's stream runs with LangSmith's own
tracing refused whatever the environment says, for every caller (ADR-1010).

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
| `add-door-demo` | archived 2026-10-04 — the sign-in door plays a three-example demo, the third with a script-drawn chart; citations are grey superscripts on the door and in the app (ADR-1210–1240) |
| _app-drawn charts_ | not proposed — the agent returns numbers and the application draws the chart. A model-drawn text chart misplaced every bar on its own axis (ADR-1210). Deferred by Yoav; the door's third example stands in with a script-drawn chart, to be redrawn by the app when this lands (ADR-1230) |

---

## Environments

One Neon project (`sparkling-bread-74230014`), one branch per environment. Branches
are copy-on-write, so the free tier absorbs several.

| Branch | For | Create when |
|---|---|---|
| `production` | the deployed app | exists |
| `dev` | local development | now — see below |
| `test` | the `network`-marked live tests | now, if those tests are ever automated |
| `alpha` | the first named testers | when there are testers, from an empty `production` |
| `beta` | a wider group | when there is a wider group |

**`dev` is the one that matters today, and the reason is worse than it looked.**
An earlier version of this file said `run_label` was separating local runs from
real feedback. It is not separating anything: `SCINUMBERS_RUN` is set nowhere —
not in `.streamlit/`, not in any deployment config — so `config.py` and
`feedback.py` both fall back to `"dev"`, and *every* row in the table says `dev`
whether it came from a laptop or the deployed app. There is no discriminator at
all, only the timestamp.

So physical separation is not the tidier of two options, it is the only one. The
asymmetry settles the rest: a wrong row in a dev database costs nothing, a dev row
counted as real feedback corrupts the one dataset this whole feature exists to
produce, and `sql/feedback.sql` queries 2, 3 and 4 filter on nothing.

**`production` is already contaminated and should be emptied, not inherited.**
It holds every test question asked while this was being built. Branching `dev`
off it is still right — that is how the history is kept, and a dev branch is
where that history belongs — but `production` should then be cleared, so it
starts empty for the first real user rather than answering its first query with
a year of our own typing. Nothing in it is real, and `dev` holds the copy.

The order matters and only in one direction: **create `dev` first**, which
snapshots the data, and clear `production` after. Neon branches are copy-on-write
from a point in time, so a later delete on `production` cannot reach `dev`.

**Worth doing anyway: set `SCINUMBERS_RUN` per environment.** The code already
reads it; nothing sets it. Separate branches make it belt-and-braces rather than
load-bearing, which is the right relationship — a row that says where it came
from is cheap, and a row that has to be *inferred* from which database it is in
is one migration away from being unattributable.

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

- **The interface says only that exchanges are logged, not what is kept about a
  person.** The side-panel notice is one line — "All app exchange is logged for
  product development" — rather than the enumeration of question,
  answer, entries, account and role it carried for one release. That list was
  accurate and too long to read, and it sat above the controls a tester came
  for. The obligation is not dropped: when there are real users rather than
  invited testers, what is kept about a person is shown **once, before use**,
  where a person will read it, which is the right shape for it and the wrong
  shape for a side panel. The `user-identity` spec carries the condition.
  README's "what the trail keeps about you" is the thorough version meanwhile.
  (2026-09-16)
- **The dev panel is shown to an unconfigured deployment** (no `[auth]`), because
  that is a developer's machine and the panel holds only the session's own
  trail. Decide again before the panel shows anything an operator would not want
  a URL-holder to see if `[auth]` were forgotten — a cross-session view, spend
  figures. The `user-identity` spec carries the condition. (2026-09-16)

| Item | Why it is waiting |
|---|---|
| Per-entry ratings | Gated on what WP2's comments actually say |
| Grey thumbs | Cosmetic; the colour rule may not be matching. Raised 2026-09-15 |
| `ToolCallLimitMiddleware` | Deferred in `add-ask-agent` for unexpected consequences seen in `interv_preper`. Worth re-checking against the stock middleware, since the project prefers the library's own components |
| Terraform | Mentioned for a Google Cloud deploy; no decision taken |
