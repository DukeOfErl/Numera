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

- [x] 1.1 ADR stubs `0780`–`0820`, committed before anything else.
- [x] 1.2 `permissions.py`: `Role`, `Permission` (one member, `DEV_PANEL`),
      `Identity`, and `GRANTS` as data — the table exactly as the spec states
      it, with default-deny, the pruning rule, and why `read` and `feedback` are
      not rows written in the comment above it. Imports nothing from Streamlit.
- [x] 1.3 `authorization.py`: `allowed(identity, permission)` and
      `require(identity, permission)` raising `Refused`. `None` is refused. The
      refusal carries the permission's name and nothing about the account.
- [x] 1.4 Tests, both directions: dev and admin are granted `DEV_PANEL`; each
      of student, scientist and senior scientist is refused it; `None` is
      refused it. The refused *roles* are the test — a test that only refuses
      `None` has not exercised the table.
- [x] 1.5 Test: the table covers every `Role` and names only known
      `Permission`s — asserted against the enums, not counted, for the reason
      `tests/agent_endings.py` gives.
- [x] 1.6 Add `permissions`, `authorization`, `accounts` to the core side of
      `tests/test_driver_independence.py`; confirm the test fails if any of them
      imports Streamlit (seed it, in a copy). *Done for `permissions` and
      `authorization` as `IDENTITY_CORE`; `accounts` is added in 2.2 when its
      file exists. Seeded `import streamlit` into a copy of `permissions.py`:
      failed `test_the_identity_modules_are_core_and_that_is_deliberate`,
      `test_no_agent_module_reaches_for_the_web_framework[permissions]` and
      `test_only_the_web_driver_knows_the_web_framework`; 56 others passed.*
- [x] 1.7 `verifier` on group 1. Ask specifically: would any test still pass if
      `GRANTS` granted `DEV_PANEL` to every role? Measure by making it so in a
      copy.

      *PASS WITH FINDINGS. All-grant table: 6 of 11 failed, no survivor claims
      the deny direction. Found and fixed: the docstring's claim that the
      identity-free modules could not import `permissions` was false (core-to-
      core imports were allowed; now forbidden by name for those three); the
      unknown-role default and the five role values were pinned by nothing (now
      tested).*
## 2. Accounts and the schema

- [x] 2.1 `sql/accounts.sql`: the `accounts` table DDL and an insert template
      with placeholder values. No secret, no real email.
- [x] 2.2 `accounts.py`: `Account` and `lookup(engine, email) -> Account | None`,
      one select under the trail store's statement timeout. **Fail closed:** an
      unreachable table raises `EnrolmentUnavailable`, distinct from "not
      enrolled". Say why in the docstring — the trail's fail-open reasoning does
      not transfer.
- [x] 2.3 Tests with an engine double: enrolled → `Account`; absent → `None`;
      disabled → `None`; engine raises → `EnrolmentUnavailable`, not `None`. The
      last is the one that matters.
- [x] 2.4 `trail_store._SCHEMA` gains `alter table … add column if not exists
      user_role text`, in the same `ensure_schema` transaction. Test it runs
      idempotently on a table that already has the column and on one that does
      not (`test_trail_store_live.py`, network marker, for the real DDL).
      *Written, and now run: `.venv/bin/python -m pytest -m network` on the
      developer's machine, 2026-09-16 — 18 passed, 1 skipped, with all five of
      `test_trail_store_live.py` green, so the `alter ... add column if not
      exists` is exercised against real Postgres on a table created in the
      pre-`user_role` shape. It could not be run from the sandbox, which has no
      route to 5432; while that was true the same DDL, insert and select were
      run by hand against Neon `dev` over SQL-over-HTTP, along with
      `sql/accounts.sql`'s DDL and `accounts._SELECT`.*
- [x] 2.5 `TrailHandler.emit` reads `user_role` off the record the way it reads
      `user_email`; `_INSERT` writes it. Test: a record with identity writes both
      columns; one without writes NULL for both — not `''`.
- [x] 2.6 `verifier` on group 2.

      *PASS WITH FINDINGS. Every named mutant killed by the test whose name
      claims it, including fail-closed. Found and fixed: a lookup returning the
      typed email rather than the row's survived (now tested).*
## 3. Identity stamped at the sink, and a credential per agent

- [x] 3.1 `default_model(config, api_key=None)`: the key as a parameter, `None`
      falling back to the environment. `AskAgent.__init__(…, api_key=None)` and
      nothing else. `ask`'s signature does not change.
- [x] 3.2 Test: two agents constructed with different keys send different keys
      to the provider (assert on the model double's construction, not on the
      environment). Test: `api_key=None` reads the environment exactly as
      before.
- [x] 3.3 `web.IdentityStamp(logging.Filter)` over a process-wide
      `session_id → Identity` registry: stamps `user_email` and `user_role` onto
      every record whose session is known. Installed once, after
      `trace.to_file`, pinned the way `test_web_driver_trail.py` pins that
      ordering. Presentation side; imports `logging` only. *Installed on the
      logger, not a handler, so it survives `trace.configure`; the test asserts
      that outcome (`test_the_stamp_survives_the_file_sink_being_configured_afterwards`)
      rather than pinning an order that is not load-bearing for a filter.*
- [x] 3.4 `TrailHandler.emit` reads `user_role` the way it reads `user_email`
      (task 2.5). Test through the trail, not the events: two sessions under two
      identities → each session's records carry its own email and role, so a
      constant or a shared stamp cannot pass.
- [x] 3.5 Test: feedback records are stamped **without `feedback.py` changing** —
      a verdict recorded in a stamped session carries the identity; one recorded
      with no registry entry carries NULL for both, not `''`.
- [x] 3.6 Structural test, in `test_driver_independence.py`: `agent.py`,
      `trace.py` and `feedback.py` name none of `Identity`, `user_role`,
      `user_email`. Seed a violation in a copy and watch it fail.
- [x] 3.7 Test, the spec's scenario: the same question asked under two roles
      hands the agent and the model identical inputs (`model.seen`, tool calls),
      with the positive control that the question itself reached the model.
- [x] 3.8 ADR-0810 and ADR-0820 written out. ADR-0820 records the principle for
      later: if the agent must ever know what is permitted, it is handed
      permissions, never the role.
- [x] 3.9 `verifier` on group 3. Ask: is there any path — parameter, field,
      import, global — by which the role could reach `agent.py`?

      *PASS WITH FINDINGS. Parameter, field and relative import: closed. Open at
      the time: `import scinumbers_ask.web` — the import rule split on the first
      dot and read it as the package, so the registry was reachable from
      `agent.py` and a role written to the trail went unnoticed. Fixed in the
      rule (`_reached`); re-seeded, now fails the dependency test. String-key
      access (`getattr`, `globals()`) stays invisible, and needs one of the
      closed doors first — recorded in the test.*
## 4. The gate, the notice, and the unconfigured deployment

- [x] 4.1 `authlib>=1.3.2` in the `ask` extra; `uv lock`; `.streamlit/
      secrets.toml.example` gains the `[auth]` block with placeholders and the
      note that `redirect_uri` ends in `/oauth2callback`.
- [x] 4.2 `web.identity_configured()`; `web.current_identity(engine)`:
      not-configured → `None` with configured=False; configured and not signed in
      → sign-in offered; signed in → `accounts.lookup`, held in session state;
      absent/disabled → `signin.refused` recorded and the not-enrolled message;
      `EnrolmentUnavailable` → the check-unavailable message, which is a
      different sentence.
- [x] 4.3 `web.resources()` returns the repository only; `web.agent_for(state,
      repo, account)` builds the per-session agent. Test through `AppTest` that
      two sessions get two agents and one repository (`test_web_driver.py` has
      the cache-hit test to extend).
- [x] 4.4 `streamlit_app.py`: the gate before anything is drawn; sign-out and
      "signed in as" in the sidebar; the identity registry entry made at
      sign-in; the missing-credential refusal in `web.answer` when the account
      has no key. No permission check on asking or rating — enrolment is the
      gate, and there is nothing for a check to refuse. *Deviation, recorded:
      the refusal is in `web.agent_for`, not `web.answer`. An agent built with
      `api_key=None` falls back to the environment's key, so a page-level
      refusal would leave the operation able to spend it; `agent_for` returns
      `None` and builds nothing, and the page keeps the wording. The test
      asserts on what was built, not on the page.*
- [x] 4.5 `messages.records_note(identity_configured)`; the CLI passes `False`;
      the sidebar shows the extended sentence when configured. Test the literal
      fragments, both variants.
- [x] 4.6 `AppTest`, no `[auth]`: behaviour identical to today — a question is
      answered without sign-in, records carry no account, the sidebar says no
      sign-in is configured. This is the regression guard for every existing
      web test, so it runs first.
- [x] 4.7 `AppTest`, `[auth]` configured (monkeypatch `st.secrets` and
      `st.user`): not signed in → sign-in and nothing else; signed in, not
      enrolled → refused and recorded; enrolled → answered. Read
      `.claude/rules/streamlit-driver.md` first: when things are drawn is a
      whole-script-run question.
- [x] 4.8 `verifier` on group 4.

      *PASS WITH FINDINGS. Eight of nine mutants caught; the money path is
      asserted on what was built. Found and fixed: a refusal on a session that
      had admitted another account was stamped with that account (registry now
      forgotten before the lookup); `_sign_out` and the no-secrets-file branch
      had no test (now tested). Noted, not changed: the escaping scan exempts
      `CONSTANT.format(...)`, so the signed-in caption is wrapped by discipline
      rather than by the scan.*
## 5. The dev panel

- [x] 5.1 `web.RecentTrail` handler: per-session deque trimmed to the last five
      question ids; installed once per process after `trace.to_file`, like
      `install_trail`, and pinned the same way `test_web_driver_trail.py` pins
      that ordering.
- [x] 5.2 `web.draw_dev_panel(state, identity)`: `require(identity, DEV_PANEL)`
      *(landed as `dev_panel_rows(admission, session_id)`, the accessor holding
      `require`, and `draw_dev_panel` over it; unconfigured is given the rows)*
      inside it; below run status; `st.dataframe` of when / question / event /
      detail; present and empty on a fresh session.
- [x] 5.3 Tests, both directions through `AppTest`: a dev's page has the section;
      a student's page has **no** such section — assert on the absence of the
      element, not on a disabled one. A fresh dev session shows it empty.
- [x] 5.4 Test: two sessions' panels show only their own records. Vary the
      question text between them so a shared buffer cannot pass.
- [x] 5.5 Test: the panel's contents do not reach the model (positive control
      first).
- [x] 5.6 `verifier` on group 5.

      *PASS WITH FINDINGS. Both canaries reproduced with the same ids as 7.1;
      "absent, not disabled" pinned. Found and fixed: "below the run status" and
      the sink install's idempotence were claims with no test (now tested).*
## 6. The session cap

- [x] 6.1 `web.SessionRegistry` under `@st.cache_resource`: touch on every
      rerun, prune idle, `SCINUMBERS_MAX_SESSIONS` and `SESSION_IDLE_S` from the
      environment with the defaults the design names. *The idle variable is
      `SCINUMBERS_SESSION_IDLE_S`, prefixed like every other setting here,
      rather than the design's bare `SESSION_IDLE_S`.*
- [x] 6.2 The try-later page at the cap, shown before sign-in. Test: the
      (N+1)th session sees it, an existing session is untouched, and a session
      that goes idle frees a place. Nothing reads `st.context.ip_address`; assert
      that over the source.
- [x] 6.3 ADR-0790 written out, including that the registry over-counts closed
      tabs and therefore admits fewer, never more.

## 7. Seeding, once, where it counts

- [x] 7.1 Into a **copy**: make `authorization.require` a no-op. Exactly the
      group-1 refusal tests and the group-5 absence test must fail, and nothing
      else. Name them in the task text when done. Then: grant `DEV_PANEL` to
      `student` in the copy — the student-has-no-panel test must fail. Then:
      pass the role into `AskAgent` in the copy — the structural test in 3.6
      must fail.
      *Done 2026-09-16, full offline suite on each self-contained copy (1,377
      tests). Three failures are copy artefacts common to all three and absent
      from the working tree — `test_specs_were_found`,
      `test_no_requirement_is_claimed_that_the_specs_do_not_contain` (no
      `openspec/` in the copy) and
      `test_a_results_file_git_would_track_is_refused_before_it_is_written` (the
      copy is not a git repository). Beyond those:*
      - *`require` a no-op — 10:*
        `test_permissions.py::test_each_tester_role_is_refused_the_dev_panel[student|scientist|senior scientist]`,
        `::test_no_identity_is_refused`,
        `::test_the_refusal_names_the_permission_and_nothing_about_the_account`;
        `test_web_driver_dev_panel.py::test_a_tester_s_page_has_no_such_section[student|scientist|senior scientist]`,
        `::test_the_accessor_refuses_a_tester_and_no_identity_but_gives_a_dev_the_rows`,
        `::test_the_refusal_does_not_depend_on_the_caller`.
      - *`DEV_PANEL` granted to student — 5:*
        `test_permissions.py::test_each_tester_role_is_refused_the_dev_panel[student]`,
        `::test_the_two_populations_partition_the_roles`,
        `::test_the_refusal_names_the_permission_and_nothing_about_the_account`;
        `test_web_driver_dev_panel.py::test_a_tester_s_page_has_no_such_section[student]`,
        `::test_the_accessor_refuses_a_tester_and_no_identity_but_gives_a_dev_the_rows`.
      - *`role` parameter on `AskAgent` — 3:*
        `test_driver_independence.py::test_identity_never_enters_the_agent_the_trail_or_the_feedback[agent]`,
        `::test_the_agent_takes_no_parameter_naming_its_caller`,
        `test_identity_never_reaches_the_agent.py::test_the_agent_holds_the_key_and_nothing_else_about_the_person`.
      *The group-5 verifier reproduced the first two sets independently and
      found the same ids. Two further side doors the group-3 verifier opened —
      `import scinumbers_ask.web` in `agent.py`, and `from .permissions import
      …` in all three identity-free modules — survived until the import rule
      was repaired; both re-seeded and both now fail.*
- [x] 7.2 Run the full suite once, at the end. Not per group. *1,388 passed,
      3 skipped (network), 40 deselected, 103 s. One earlier run, made while
      three canary suites ran in parallel, failed a single AppTest identity test
      that passed alone and in the same order on the rerun — the 30 s AppTest
      timeout under load, not an ordering fault.*

## 8. The record

- [x] 8.1 ADR-0780 and ADR-0800 written out (the others land with their groups).
- [x] 8.2 Spec-conformance mapping for the new capability and the two modified
      requirements' new scenarios. A scenario that merely executes is a gap, not
      a pass; say which is which.
      *Five named in the `COVERED` comment: sign-out's next visit, enrolled-after-
      refusal, two testers under one exhausted cap, records-found-by-account
      (query 8, by hand), credential-never-shown beyond the drawn elements.*
- [x] 8.3 `sql/feedback.sql`: a per-tester and a per-role query, left joins as
      before. Run against `dev`.
      *Queries 6, 7 and 8 added and run over SQL-over-HTTP on 2026-09-16: 25
      verdicts, all `(null, null)` / `(no sign-in)`; the `user_role` column was
      added to the live `dev` table by the same idempotent `alter` that
      `ensure_schema` runs.*
- [x] 8.4 `README.md`: sign-in, enrolment, what is now kept about a person,
      the operator's steps from the design's migration plan. `CHANGELOG.md`.
      `docs/diagrams/architecture.md`: the three new core modules and the
      per-session agent. `CLAUDE.md` module table and the `PRESENTATION`/core
      sets.
- [x] 8.5 `docs/roadmap.md` §WP3 points at this change and its ADRs rather than
      describing them. Its "Deferred, deliberately" section gains the
      unconfigured-deployment-sees-the-panel decision, with the condition that
      reopens it.
- [x] 8.6 `openspec validate add-user-identity --strict`, archive, then diff
      each promoted requirement against its delta mechanically — archive refuses
      a dropped scenario and says nothing about dropped prose.
      *Done 2026-09-16: valid under `--strict`; archived as
      `2026-09-16-add-user-identity` (+8, ~2, -0). Mechanical diff: all 8
      `user-identity` requirements and the 2 MODIFIED ones promoted byte-for-byte
      from their deltas; `agent-session` 13→13 and `answer-feedback` 5→5
      requirements, none lost, none outside the delta changed.*
