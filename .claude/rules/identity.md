---
paths:
  - "src/scinumbers_ask/web.py"
  - "src/scinumbers_ask/permissions.py"
  - "src/scinumbers_ask/authorization.py"
  - "src/scinumbers_ask/accounts.py"
  - "streamlit_app.py"
  - "tests/test_web_driver_identity*.py"
  - "tests/test_web_driver_dev_panel.py"
  - "tests/test_web_driver_session_cap.py"
  - "tests/test_permissions.py"
  - "tests/test_accounts.py"
  - "tests/test_identity_never_reaches_the_agent.py"
---

<!-- Moved out of CLAUDE.md, which targets under 200 lines. Scoped to the files
     sign-in actually touches, so a session that never goes near them pays
     nothing. The module table and the dependency direction stay in CLAUDE.md;
     what is here is the shape of identity, which only these files need. -->

# Who a reader is, and where that stops

**Identity stops at the driver.** `web.admit` decides the door once per account
per session and **fails closed** when the accounts table cannot be read — the
deliberate inverse of the trail's fail-open, because a tolerance here would let
a database outage admit everyone (ADR-0780). An enrolled account with no
credential meets a door of its own, so the page has exactly one gate and
`agent_for` can never return an agent that falls back to the environment's key.

**The agent is handed a credential and nothing else about the person.** Not the
account, not the role. `agent.py`, `trace.py` and `feedback.py` name none of
`Identity`, `Role`, `role`, `email`, `account`, `user_role`, `user_email`, and
may not import `permissions`, `authorization` or `accounts` —
`test_driver_independence.py` parses their source and fails on either. A
verifier opened both doors before those assertions existed: a `role` parameter
on the constructor, and `import scinumbers_ask.web` reading the registry. If
the agent must one day know what is permitted, hand it **permissions**, never
the role (ADR-0820).

**The session is keyed on the account, not on the link** (ADR-0830).
`?session=` is recovered from the URL and shared by anyone given it, so under
sign-in `web.effective_session` derives the key from the account instead.
Everything downstream — the identity stamp, the dev panel's rows, the cap's
heartbeat, the checkpoint thread — uses that key. Keying any of them on the URL
token again reintroduces a class of silent bug: one reader's records attributed
to another, one reader's trail shown to another, a session stranded by the OAuth
redirect that drops the query string. Where identity is **not** configured the
URL token remains the session, and that is what keeps a developer's machine
bookmarkable.

**Identity is re-established on every rerun**, not once at sign-in
(`web.establish_identity`). A session pruned for idleness loses its stamp, and a
held admission short-cuts the lookup; without re-establishing, a still-signed-in
tab recorded no account at all while the sidebar went on naming one.

**Ending a session is one operation.** `web.end_session` clears the identity
stamp, the panel's rows and the cap's place together. There were three stores
kept in step by hand and a sign-out that cleared one, which left the next
account on that tab able to read the last one's questions. A new per-session
store joins `end_session` rather than the next exit path that remembers it.

**The refusal belongs to the operation.** The one `require` in the system is
inside `web.dev_panel_rows`, the accessor that produces what the permission
guards — not on the page that draws the section. A page that hides a control has
enforced nothing, and the spec says the refusal must not depend on who asks.

**Default-deny, and the pruning rule** (ADR-0800). `GRANTS` lists what each role
holds; absence is refusal. A permission exists **only where some role is refused
it** — otherwise its deny direction can be tested against nobody, and a row
nobody can be refused teaches the reader the table is decoration.

**A deployment with no `[auth]` runs exactly as before** — not a branch, but the
absence of a registry entry — and sees the dev panel. That last part is a
deferred decision, recorded in `docs/roadmap.md` with the condition that
reopens it.

# The trail's sinks, and the one ordering that matters

`trace.py` writes to a logger. `trail_store.py` attaches as a second handler,
`web.RecentTrail` (the dev panel) as a third, and `web.IdentityStamp` — a
`logging.Filter` keyed by `session_id` — stamps `user_email` and `user_role`
onto every record of a signed-in session before any handler sees it. No call
site knows about any of them, which is how the three modules above stay free of
identity.

- **Recording fails open, deliberately inverting the spend gate** — the
  reasoning, and why it is a spec requirement rather than a code convention, is
  ADR-0710.
- **Handlers must be installed after `trace.to_file`**, which calls `configure`,
  which clears the logger's handlers. Above it, a sink is attached and then
  discarded: an app that looks configured and records nothing.
  `test_web_driver_trail.py` pins the order for both handlers. The **filter** is
  exempt — `configure` leaves filters alone — and a test asserts that outcome
  rather than a comment claiming it.
- **The role is written when the record is, never looked up afterwards**
  (ADR-0810): a rating's weight is the weight the role carried when it was given.
