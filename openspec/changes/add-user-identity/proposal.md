## Why

Alpha testers are about to arrive, and the app cannot tell them apart: every
rating carries a NULL `user_email`, every question is funded by one shared key,
and anyone with the URL can ask. The two changes before this one made the trail
worth reading — a rating now sits beside the question and answer it judged — and
that is exactly why identity has to come now: those records are about to be a
person's, and the roadmap has kept a column empty for them since day one.

## What Changes

- **Sign-in.** Google, through Streamlit's own `st.login` (OIDC), with an
  allowlist of accounts the operator maintains outside the app. Signed in but not
  allowlisted is refused; enrolment is what grants reading and rating.
- **Roles and a grant table.** Five roles — student, scientist, senior
  scientist, dev, admin — and one permission, `dev panel`, as data,
  default-deny. The table was decided in `docs/roadmap.md` §WP3 on 2026-09-16
  and revised the same day: `read` and `feedback` were rows no role refused, and
  a permission exists only where some role is refused it. **The agent never
  receives the role or the account**; if it must one day know what is
  permitted, it is handed permissions, never the role.
- **A dev panel**, present for `dev panel` holders and absent for everyone else:
  this session's last five questions' trail records as a table. It exists so
  that enforcement has a deny direction to test, and because WP4 and WP5 will
  want the surface anyway.
- **One OpenRouter key per tester, minted by the operator** from a management
  key and looked up server-side. The tester never sees it. Each key carries its
  own credit cap with a monthly reset, so one tester's questions cannot spend
  another's money and an exhausted cap recovers on its own. A spent key already
  surfaces as its own ending (ADR-0600).
- **The agent takes its credential as a parameter** instead of reading a process
  global, and **one agent per browser session** instead of one per server — the
  corpus index stays shared, the thing holding a key does not.
- **Identity on every trail row, at write time, stamped by the driver at the
  sink.** `user_email` is finally written, and `user_role` is added beside it,
  recorded when the row is written and never looked up afterwards: a rating's
  weight is the weight at the moment it was given. The agent, the trace and the
  feedback module do not change for this — a filter on the trail's logger does.
- **A global cap on concurrent sessions.** Not per-IP — Streamlit's own docs say
  the client address must not be used for security. This protects the host, not
  the budget; cost is capped per key.
- **The notice says what is now kept about a person.** The existing sidebar
  sentence is extended — email and role join question, answer and entries — not
  duplicated.
- **BREAKING, for the hosted deployment only:** a reader who is not signed in
  and allowlisted is refused. A developer's machine with no `[auth]` configured
  behaves exactly as today, by the same rule the trail follows: configure nothing
  and nothing changes. The terminal driver is untouched.

## Capabilities

### New Capabilities

- `user-identity`: who a reader is, what they may do, and what the system keeps
  about them — sign-in and the allowlist, roles and the default-deny grant table,
  the per-tester credential and its cap, the dev panel, the concurrent-session
  cap, and the rule that an unconfigured deployment behaves as before.

### Modified Capabilities

- `agent-session`: the requirement *"The deterministic layer is logged under a
  per-question identifier"* — its "what is kept about a person, and why" clause
  now names the person: every record carries the account and the role it was
  written under, and the interface's statement of what is kept says so.
- `answer-feedback`: the requirement *"A rating names the question it is about,
  and outlives the session"* — the space it kept for the person who gave a rating
  is now filled, with the role they held at the time, recorded when the rating is
  written and never looked up afterwards.

## Impact

**Code.** `agent.py`: `default_model` takes the key rather than reading
`os.environ`, and `AskAgent` is constructed per session — nothing else changes
there. `web.py`: `resources()` splits — the repository stays
`@st.cache_resource`, the agent moves to session state — and gains the identity
filter, the panel's handler and the session registry. `streamlit_app.py`: the
sign-in gate before anything is drawn, the dev panel below run status.
`trail_store.py`: `user_role` column and the first `add column if not exists`;
`TrailHandler` reads the role off the record as it reads the email.
`trace.py` and `feedback.py`: untouched, and a test says so. `messages.py`: the
notice. Three new core-side modules, none importing Streamlit: `permissions.py`
(the table, as data), `authorization.py` (the refusal), `accounts.py` (the
account → role → key lookup). `tests/test_driver_independence.py` gains them.

**Dependencies.** `authlib>=1.3.2` in the `ask` extra — `st.login` needs it and
Streamlit does not bundle it. Installed Streamlit is 1.61.1; `st.login`,
`st.logout` and `st.user` are present and their current signatures are what the
design is written against.

**Configuration and secrets.** `[auth]` in `secrets.toml` (`redirect_uri`,
`cookie_secret`, `client_id`, `client_secret`, `server_metadata_url`); the
OpenRouter management key, which mints and must never itself be used to ask; the
account table's home. None of it enters the repository.

**Storage.** The trail table gains one column. The account → role → key mapping
needs a home; the design decides between the trail database and elsewhere, and
records the decision, because putting it in Neon makes the trail database hold
credentials for the first time.

**Reading it back.** `sql/feedback.sql` can group by tester and by role, which
is the first step towards the weighting the roles exist for.

**Deliberately unaffected.** The terminal driver: one operator, one key, no
roles. The evaluation harness: no identity, its rows keep a NULL account. What
the model is shown: identity is a record, never context.
