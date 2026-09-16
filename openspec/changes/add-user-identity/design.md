## Context

See `proposal.md` — Why. `docs/roadmap.md` §WP3 holds the decisions taken before
this change was proposed and is not restated; what follows is how they land in
this codebase. The constraints that shape the approach:

- **Streamlit 1.61.1 is installed and ships `st.login`, `st.logout`, `st.user`**
  (read from the installed package, not from memory). `st.login` is OIDC only,
  configured under `[auth]` in `secrets.toml`; `st.user` exposes the token's
  claims (`email`, `name`) and `is_logged_in` — an attribute that **does not
  exist at all when `[auth]` is absent**, which is the hook for "unconfigured
  behaves as before". `authlib` is required and not installed; it goes in the
  `ask` extra.
- **`default_model()` reads `OPENROUTER_API_KEY` from `os.environ`** — a process
  global — and **`web.resources()` is `@st.cache_resource`**, so one `AskAgent`
  serves every browser session on the server. Both have to change before a key
  can be per person.
- **The agent takes no parameter naming its caller (ADR-0110).** Identity is not
  the caller; it is a fact about the person, carried for the record. It must not
  make the agent behave differently, and the design has to make that visibly
  true.
- **The trail already has the seams.** `QuestionTrace.record` puts fields in
  `extra`; `TrailHandler.emit` already reads `user_email` off the record and
  writes NULL. `feedback._record` goes through the same logger. The `trail`
  table has had a `user_email` column since ADR-0700.
- **Guards belong to the operation, not the caller.** The refusal lives in the
  function that does the thing; the driver keeps the wording.
- **Nothing on the core side may import Streamlit** — `test_driver_independence`
  asserts it over the source, and the three new modules are core.

## Goals / Non-Goals

**Goals.** A signed-in, enrolled reader with a role, a credential of their own,
identity on every record, a deny direction that can be tested, and a developer's
machine that notices none of it.

**Non-Goals, at the design level:**

- **Not a user-management page.** Enrolment is a row an operator inserts;
  `sql/accounts.sql` carries the DDL and an insert template. The roadmap says why
  `manage accounts` is not a permission.
- **Not encryption of stored credentials.** See the first decision, and the ADR
  it produces; it is a trade-off recorded, not an oversight.
- **Not key minting from the app.** The operator mints at OpenRouter and pastes
  the runtime key into the row. A helper script is a later convenience.
- **Not session persistence across restarts.** Still ephemeral, as the trail's
  README section says.

## Decisions

### Accounts live in the trail database, in their own table, keys in the clear

`accounts(email primary key, role, openrouter_key, issued_at, disabled)` in the
same Neon database as `trail`, read through the same engine. **ADR-0780.**

*Alternatives considered.* Streamlit secrets: a redeploy per tester, rejected in
the roadmap. A second database: a second URL in secrets, a second engine, a
second failure mode — for an isolation that the threat model does not need,
because the runtime keys are the least valuable thing in either database.
Encrypting the key column: defends against a reader of the database who lacks
the app's secrets, at the cost of a second secret and a decryption path on every
question. The keys are minted with a hard monthly cap and are revocable in one
call; the database URL is itself a secret; and the trail table beside it now
holds testers' questions verbatim, which is the more sensitive column. Accepted
in the clear, stated plainly.

**Consequence the ADR must carry:** the trail database now holds credentials.
Its URL was already treated as a secret; this is why it has to stay one.

### One agent per browser session, holding one credential; the repository stays shared

`web.resources()` keeps the corpus repository under `@st.cache_resource` — it is
the expensive index — and stops constructing the agent. `web.agent_for(state,
repo, account)` builds an `AskAgent` once per session into `st.session_state`,
with the account's key and identity passed at construction. `AskAgent` is cheap:
its saver is opened per `_saver()` call, and the checkpoint path stays shared.
**ADR-0820.**

`default_model(config, api_key: str | None)` takes the key. `None` falls back to
`os.environ`, which is what the CLI, the harness and an unconfigured deployment
pass — behaviour unchanged for all three. `AskAgent.__init__` gains
`api_key: str | None = None` and `identity: Identity | None = None`.

*Alternative considered:* threading identity through `ask(session_id, question,
identity)`. Rejected: `ask`'s signature is the port every adapter uses, and a
per-session agent already *is* one person's, so construction is the honest
place. It also keeps ADR-0110 visibly true — `ask` cannot vary on who is asking
because it does not receive who is asking.

### Identity is a value, and it travels on the trace

`Identity(email: str, role: Role)` in `permissions.py`. `QuestionTrace` gains
`user_email` and `user_role`, both defaulting to `""` and placed in `extra` by
`record()` — so `TrailHandler.emit`'s existing `or None` turns the absence into
NULL, exactly as it does for `session_id`. `start_question(...)` takes an
optional `identity`. `feedback.record_verdict/record_comment` take `identity`
and put the same two fields on their records.

**The role is written, not looked up.** `user_role text` joins `user_email` as a
column — not inside `detail` — because it is a first-class join key for the
weighting queries the roles exist for, and `user_email` already set the
precedent. **ADR-0810.** This is the first schema change since the table was
created; `_SCHEMA` gains `alter table {table} add column if not exists user_role
text` after the `create table if not exists`, run in the same `ensure_schema`
transaction, idempotent on every start.

### The grant table is data; the refusal is one function

`permissions.py`: `Role` and `Permission` enums, `GRANTS: dict[Role,
frozenset[Permission]]` — the table from the spec, with the pruning rule and
default-deny stated in the comment above it. `authorization.py`: `allowed(
identity, permission) -> bool` and `require(identity, permission)` raising
`Refused`, which carries the permission's name and nothing else. `None` identity
is refused everything. **ADR-0800.**

*Where `require` is called.* Inside the operation: `feedback.record_verdict` and
`record_comment` (the things that record), `web.answer` (the thing that asks; the
driver's single dispatch point), and the panel's data accessor. The page's
control-hiding is presentation and proves nothing; the tests drive the
operations directly with a role that lacks the grant.

*Alternative considered:* putting `require(READ)` inside `AskAgent.ask`.
Rejected on ADR-0110: the agent would then receive who is asking. `web.answer`
is the web adapter's operation, and the CLI has no identity by design.

### Enrolment is read once per session and refused loudly

`accounts.py`: `lookup(engine, email) -> Account | None`, one `select` with the
trail store's statement timeout. Called once per session at sign-in, result held
in `st.session_state`. A missing row → `signin.refused` written to the trail with
the email and no question id (the handler already accepts a null one) → the page
shows the not-enrolled message and nothing else. A row with `disabled` → the
same path. A row with no key → the account proceeds as its role but `web.answer`
refuses with the missing-credential wording. Re-reading per question was
considered and rejected: a role change mid-session taking effect on the next
question is not worth a database round trip per question, and the row is re-read
on the next sign-in.

**Fail-closed here, deliberately inverting the trail.** If the accounts table
cannot be read, nobody is enrolled. A tolerance that fails open would let a
database outage admit everyone. The page says the enrolment check is
unavailable, which is a different sentence from "not enrolled".

### The dev panel is a third sink on the same logger, filtered at render

`web.RecentTrail(logging.Handler)`: installed once per process beside the file
and durable sinks — after `trace.to_file`, for the same ordering reason
`install_trail` is — holding `dict[session_id, deque]` of formatted records,
trimmed so each session keeps the records of its last five `question_id`s.
`draw_dev_panel(state, identity)` calls `require(identity, DEV_PANEL)` and
renders that session's deque as `st.dataframe`. Presentation side: it lives in
`web.py` and imports only `logging`.

*Alternative considered:* reading back from the durable store. Rejected: it does
not exist on a developer's machine, which is where the panel is most used, and
the panel is about *this* session, which the in-process handler already
partitions by construction.

### The session cap is a heartbeat registry, and the design says what it is not

`web.SessionRegistry`, `@st.cache_resource`: `dict[session_id, last_seen]`,
touched on every rerun, pruned of entries older than `SESSION_IDLE_S` (default
600). A new session arriving when the live count is at `SCINUMBERS_MAX_SESSIONS`
(default 20) is shown the try-later message before sign-in is offered. **ADR-0790.**

This is an approximation and the ADR says so: Streamlit offers no reliable
disconnect hook, so a closed tab counts as live until its idle window passes.
The cap therefore admits *fewer* than the configured number in the worst case,
never more — the cheap direction, for a guard that protects the host.

Not per-IP, per the roadmap: `st.context.ip_address` is client-supplied.

### Unconfigured means untouched

`web.identity_configured() -> bool` is `"auth" in st.secrets`. When false:
no sign-in gate, `identity=None` everywhere, `api_key=None` (environment
fallback), records carry NULL as today, the sidebar says "no sign-in configured",
and the dev panel is shown — a session that is nobody's is the developer's. This
is the same rule the durable trail follows and is asserted through `AppTest`
with no `[auth]` in secrets, which is how every existing web test already runs.

### The notice is one sentence, extended

`messages.RECORDS_NOTE` becomes a function of whether identity is configured,
returning the existing sentence with "under your account and role" added when it
is. One place, both drivers; the CLI passes `False`.

## Risks / Trade-offs

**A credential in a database that also holds testers' questions** → Accepted
(ADR-0780). Mitigated by hard monthly caps, one-call revocation, and the database
URL already being a secret. Revisit if a key without a cap is ever stored, which
would change the calculus.

**`st.user` lifetime.** Streamlit reads the identity cookie at session start
and does not check token expiry. → A very long session keeps a stale identity;
accepted for alpha, noted in the ADR. `st.logout` is offered so a reader can
force it.

**One `AskAgent` per session means one per browser tab.** → Memory is a
`Config`, a repo reference and a path; negligible. The cost that mattered — the
index — stays shared.

**The accounts table cannot be reached** → fail closed; the page says the check
is unavailable. The trail's fail-open reasoning does not transfer: admitting
everyone during an outage is the expensive direction.

**The dev panel holds records in process memory** → bounded per session to the
last five questions, evicted with the registry's idle prune. A deployment with
many sessions holds at most `MAX_SESSIONS × 5 questions` of formatted lines.

**The heartbeat registry over-counts closed tabs** → admits fewer, never more.
Stated in ADR-0790 so nobody tunes the cap upward to compensate without knowing
why it seems low.

**Both directions of the grant table** → every permission test asserts a grant
*and* a refusal, and the refusal varies the dimension the rule reads — a role
that lacks it, an account with no role, `None`. A seeded canary ("the guard is
bypassed": `require` made a no-op in a copy) must fail a named test before the
change is believed. This is the one stage this project keeps seeding for; the
memory and the roadmap both say so.

## Migration Plan

1. Merge with no `[auth]` configured: behaviour identical, `ensure_schema` adds
   the `user_role` column on first start (idempotent; rows written before carry
   NULL, which is truthful).
2. Operator: create the Google OAuth client, put `[auth]` in the hosting
   platform's secrets, create the `accounts` table from `sql/accounts.sql`, mint
   one runtime key per tester at OpenRouter, insert the rows.
3. First hosted start with `[auth]` present: sign-in is enforced from that
   moment. Nothing to backfill — rows before have no account and cannot be given
   one.

Rollback: remove `[auth]` from secrets; the app is back to today's behaviour on
the next start. The `user_role` column stays, harmlessly NULL.

## Open Questions

- **Should the try-later page at the session cap be shown before or after
  sign-in?** Before, in this design, so the cap also bounds OAuth round trips.
  Either satisfies the spec; the choice does not change the tasks.
