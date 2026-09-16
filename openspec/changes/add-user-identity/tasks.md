# Tasks

**ADR block: `0780`–`0830`.** Reconciled against CLAUDE.md's table, which is the
authority. Allocate by creating the stub and committing it early. Planned:
`0780` accounts in the trail database (keys in the clear, and why); `0790` the
session cap is a heartbeat registry, not per-IP; `0800` default-deny and the
pruning rule; `0810` role written at record time; `0820` one agent per session,
credential as a parameter.

**Testing policy for this change** — different from the last two. Auth is where
this project keeps a canary and does not skip seeding (`.claude/rules/testing.md`;
the memory "verification instrument by stage"). A wrongly denied permission
produces a complaint in minutes; a wrongly granted one produces nothing at all.

**The negative-case rule bites hardest here.** Every permission test asserts both
directions, and the deny case varies *the dimension the rule reads* — a role that
lacks the grant, an enrolled account with no role, `None` — never merely a
different outcome. The grant table is a classification rule: after any change to
it, measure both populations, not the one you meant to move.

**A read-only `verifier` reviews each group** and is told to measure, not
re-read: coverage of the module under the one test that claims it, counters on
doubles, both populations of the table. Its brief already says so.

## 1. The table and the refusal

- [ ] 1.1 ADR stubs `0780`–`0820`, committed before anything else.
- [ ] 1.2 `permissions.py`: `Role`, `Permission`, `Identity`, and `GRANTS` as
      data — the table exactly as the spec states it, with default-deny and the
      pruning rule written in the comment above it. Imports nothing from
      Streamlit.
- [ ] 1.3 `authorization.py`: `allowed(identity, permission)` and
      `require(identity, permission)` raising `Refused`. `None` is refused
      everything. The refusal carries the permission's name and nothing about the
      account.
- [ ] 1.4 Tests, both directions, per permission: for `read`, `feedback` and
      `dev panel`, one role that holds it passes and one that lacks it is refused.
      For `dev panel` the refused role must be a *tester* role, not `None` — a
      test that only refuses `None` has not exercised the table.
- [ ] 1.5 Test: an account with no role is refused `read`. Vary the dimension:
      the same email with a role passes, without one is refused.
- [ ] 1.6 Test: the table covers every `Role` and names only known `Permission`s
      — asserted against the enums, not counted, for the reason
      `tests/agent_endings.py` gives.
- [ ] 1.7 Add `permissions`, `authorization`, `accounts` to the core side of
      `tests/test_driver_independence.py`; confirm the test fails if any of them
      imports Streamlit (seed it, in a copy).
- [ ] 1.8 `verifier` on group 1. Ask specifically: would any test still pass if
      `GRANTS` granted everything to everyone? Measure by making it so in a copy.

## 2. Accounts and the schema

- [ ] 2.1 `sql/accounts.sql`: the `accounts` table DDL and an insert template
      with placeholder values. No secret, no real email.
- [ ] 2.2 `accounts.py`: `Account` and `lookup(engine, email) -> Account | None`,
      one select under the trail store's statement timeout. **Fail closed:** an
      unreachable table raises `EnrolmentUnavailable`, distinct from "not
      enrolled". Say why in the docstring — the trail's fail-open reasoning does
      not transfer.
- [ ] 2.3 Tests with an engine double: enrolled → `Account`; absent → `None`;
      disabled → `None`; engine raises → `EnrolmentUnavailable`, not `None`. The
      last is the one that matters.
- [ ] 2.4 `trail_store._SCHEMA` gains `alter table … add column if not exists
      user_role text`, in the same `ensure_schema` transaction. Test it runs
      idempotently on a table that already has the column and on one that does
      not (`test_trail_store_live.py`, network marker, for the real DDL).
- [ ] 2.5 `TrailHandler.emit` reads `user_role` off the record the way it reads
      `user_email`; `_INSERT` writes it. Test: a record with identity writes both
      columns; one without writes NULL for both — not `''`.
- [ ] 2.6 `verifier` on group 2.

## 3. Identity on the trace, and a credential per agent

- [ ] 3.1 `QuestionTrace` gains `user_email`/`user_role` (default `""`),
      `record()` puts them in `extra`; `start_question(…, identity=None)`.
- [ ] 3.2 `default_model(config, api_key=None)`: the key as a parameter, `None`
      falling back to the environment. `AskAgent.__init__(…, api_key=None,
      identity=None)`; `ask` threads identity into `start_question`. `ask`'s
      signature does not change.
- [ ] 3.3 Test: two agents constructed with different keys send different keys
      to the provider (assert on the model double's construction, not on the
      environment). Test: `api_key=None` reads the environment exactly as
      before.
- [ ] 3.4 Test: every record of a question asked through an agent with identity
      carries email and role — through the trail, not the events, and varying the
      identity between two questions so a constant cannot pass.
- [ ] 3.5 `feedback.record_verdict/record_comment` take `identity`; the two
      fields land on their records. Test both with identity and without.
- [ ] 3.6 Test: identity does not reach the model. Follow
      `test_nothing_recorded_here_reaches_the_model` with its positive control;
      the needle is the email.
- [ ] 3.7 ADR-0810 and ADR-0820 written out.
- [ ] 3.8 `verifier` on group 3. Ask: is there any path by which identity could
      change what the agent does, not only what it records?

## 4. The gate, the notice, and the unconfigured deployment

- [ ] 4.1 `authlib>=1.3.2` in the `ask` extra; `uv lock`; `.streamlit/
      secrets.toml.example` gains the `[auth]` block with placeholders and the
      note that `redirect_uri` ends in `/oauth2callback`.
- [ ] 4.2 `web.identity_configured()`; `web.current_identity(engine)`:
      not-configured → `None` with configured=False; configured and not signed in
      → sign-in offered; signed in → `accounts.lookup`, held in session state;
      absent/disabled → `signin.refused` recorded and the not-enrolled message;
      `EnrolmentUnavailable` → the check-unavailable message, which is a
      different sentence.
- [ ] 4.3 `web.resources()` returns the repository only; `web.agent_for(state,
      repo, account)` builds the per-session agent. Test through `AppTest` that
      two sessions get two agents and one repository (`test_web_driver.py` has
      the cache-hit test to extend).
- [ ] 4.4 `streamlit_app.py`: the gate before anything is drawn; sign-out and
      "signed in as" in the sidebar; `require(identity, READ)` inside
      `web.answer`; the missing-credential refusal when the account has no key.
- [ ] 4.5 `messages.records_note(identity_configured)`; the CLI passes `False`;
      the sidebar shows the extended sentence when configured. Test the literal
      fragments, both variants.
- [ ] 4.6 `AppTest`, no `[auth]`: behaviour identical to today — a question is
      answered without sign-in, records carry no account, the sidebar says no
      sign-in is configured. This is the regression guard for every existing
      web test, so it runs first.
- [ ] 4.7 `AppTest`, `[auth]` configured (monkeypatch `st.secrets` and
      `st.user`): not signed in → sign-in and nothing else; signed in, not
      enrolled → refused and recorded; enrolled → answered. Read
      `.claude/rules/streamlit-driver.md` first: when things are drawn is a
      whole-script-run question.
- [ ] 4.8 `verifier` on group 4.

## 5. The dev panel

- [ ] 5.1 `web.RecentTrail` handler: per-session deque trimmed to the last five
      question ids; installed once per process after `trace.to_file`, like
      `install_trail`, and pinned the same way `test_web_driver_trail.py` pins
      that ordering.
- [ ] 5.2 `web.draw_dev_panel(state, identity)`: `require(identity, DEV_PANEL)`
      inside it; below run status; `st.dataframe` of when / question / event /
      detail; present and empty on a fresh session.
- [ ] 5.3 Tests, both directions through `AppTest`: a dev's page has the section;
      a student's page has **no** such section — assert on the absence of the
      element, not on a disabled one. A fresh dev session shows it empty.
- [ ] 5.4 Test: two sessions' panels show only their own records. Vary the
      question text between them so a shared buffer cannot pass.
- [ ] 5.5 Test: the panel's contents do not reach the model (positive control
      first).
- [ ] 5.6 `verifier` on group 5.

## 6. The session cap

- [ ] 6.1 `web.SessionRegistry` under `@st.cache_resource`: touch on every
      rerun, prune idle, `SCINUMBERS_MAX_SESSIONS` and `SESSION_IDLE_S` from the
      environment with the defaults the design names.
- [ ] 6.2 The try-later page at the cap, shown before sign-in. Test: the
      (N+1)th session sees it, an existing session is untouched, and a session
      that goes idle frees a place. Nothing reads `st.context.ip_address`; assert
      that over the source.
- [ ] 6.3 ADR-0790 written out, including that the registry over-counts closed
      tabs and therefore admits fewer, never more.

## 7. Seeding, once, where it counts

- [ ] 7.1 Into a **copy**: make `authorization.require` a no-op. Exactly the
      group-1 refusal tests and the group-5 absence test must fail, and nothing
      else. Name them in the task text when done. Then: grant `DEV_PANEL` to
      `student` in the copy — the student-has-no-panel test must fail.
- [ ] 7.2 Run the full suite once, at the end. Not per group.

## 8. The record

- [ ] 8.1 ADR-0780 and ADR-0800 written out (the others land with their groups).
- [ ] 8.2 Spec-conformance mapping for the new capability and the two modified
      requirements' new scenarios. A scenario that merely executes is a gap, not
      a pass; say which is which.
- [ ] 8.3 `sql/feedback.sql`: a per-tester and a per-role query, left joins as
      before. Run against `dev`.
- [ ] 8.4 `README.md`: sign-in, enrolment, what is now kept about a person,
      the operator's steps from the design's migration plan. `CHANGELOG.md`.
      `docs/diagrams/architecture.md`: the three new core modules and the
      per-session agent. `CLAUDE.md` module table and the `PRESENTATION`/core
      sets.
- [ ] 8.5 `docs/roadmap.md` §WP3 points at this change and its ADRs rather than
      describing them.
- [ ] 8.6 `openspec validate add-user-identity --strict`, archive, then diff
      each promoted requirement against its delta mechanically — archive refuses
      a dropped scenario and says nothing about dropped prose.
