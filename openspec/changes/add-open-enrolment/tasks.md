# Tasks

**ADR block: `0880`–`0920`**, added to CLAUDE.md's allocation table as task 0.1
— the table is the authority, `tasks.md` the copy an implementer reads.
Planned: `0880` a second provider beside the first, and why not Neon Auth;
`0890` only a verified address opens the door, absence refuses; `0900`
enrolment is mint-then-insert with compensation, and never uncapped. Written
with the decision, not batched.

**Testing policy.** Auth is where this project keeps a canary and does not skip
seeding (`.claude/rules/testing.md`). Two rules bite here: the verified-address
check is a classification rule, so *both* populations are measured — the ones it
now refuses and the ones it still admits — and the negative cases vary the
dimension the rule reads (the claim's value and its presence), never merely the
outcome. `enrol()`'s refusals are the guards with teeth; a `verifier` measures
them by seeding rather than reading.

**Operator tasks are marked (operator)** — they happen in a console, not the
repository, and the implementer's job is to leave the instructions right.

## 0. Allocation

- [x] 0.1 CLAUDE.md: add `add-open-enrolment` | `0880`–`0920` to the ADR table;
      ADR stubs `0880`, `0890`, `0900` from the template, committed first.

## 1. The door

- [x] 1.1 `messages.py`: `SIGN_IN_LABELS` — `"default"` → "Sign in with Google",
      `"auth0"` → "Sign in with email" — and `UNVERIFIED`, the sentence for an
      address the provider has not verified, distinct in wording from
      `NOT_ENROLLED` and naming the reader's next step.
- [x] 1.2 `web.providers() -> list[str]`: `"default"` when `[auth]` itself
      carries `client_id`, then each sub-table name that is a mapping, in
      secrets order. Tests with a secrets double: Google only; Google and
      auth0; auth0 only; `[auth]` absent → empty.
- [x] 1.3 `draw_closed_door`: one button per provider, `st.login` for the
      default and `st.login(name)` otherwise. Update the AppTest that asserts
      `["Sign in with Google"]` and add the two-button case. The label for an
      unknown name is "Sign in with <name>".
- [x] 1.4 `web.address_verified(claims: Mapping) -> bool`: `True` for the
      boolean `True` and the string `"true"` under `email_verified`; `False`
      for `"false"`, `False`, `1`, `None` and a missing key. Pure, no
      Streamlit. Tests enumerate every one of those — the negatives vary the
      value and its presence.
- [x] 1.5 `Door.UNVERIFIED` and the check in `admit`, before the lookup, so an
      unverified address never reaches the accounts table. Recorded through the
      same path as a refused sign-in. AppTest: unverified → the `UNVERIFIED`
      sentence and no question input; verified and unenrolled → `NOT_ENROLLED`
      as before; verified and enrolled → the page. **Measure both populations**:
      every existing identity AppTest that signs in must now carry
      `email_verified: True` in its `st.user` double — grep for `is_logged_in`
      doubles and count them before and after.
- [x] 1.6 Test: the same address asserted with `provider: "auth0"` and with
      `provider: "default"` yields the same `effective_session` key and the
      same account; the `provider` claim is not stamped on any trail record
      (extend `test_identity_never_reaches_the_agent.py` or the stamp test).
- [x] 1.7 Fault seeding, in a copy: `address_verified` returning `True` for a
      missing key; `admit` checking after the lookup instead of before. Name
      the tests that fail in the task note; write ADR-0890's claim after.

      *Copy at `$TMPDIR/seed-g1`, `assets/` symlinked in — without it
      `LOGO = Path(__file__).parents[2]` misses and the mark test fails, so the
      first baseline was one-red and no verdict could be read from it. Green
      baseline 106 passed. **Seed A** `claims.get("email_verified", True)` →
      killed `test_address_verified_reads_the_claim_and_refuses_its_absence`,
      alone, which is the one test claiming absence. **Seed B** the check moved
      below the enrolment lookup → killed
      `test_an_unverified_address_is_refused_with_its_own_sentence` and
      `test_an_unverified_address_is_never_looked_up`. **Seed C** (added,
      unplanned) `providers()` always offering `"default"` → killed
      `test_providers_reads_the_default_and_every_sub_table` and
      `test_a_provider_with_no_label_still_gets_a_button`.*
- [ ] 1.8 `verifier` on group 1: would any test still pass if `admit` admitted
      an unverified address? Measure by making it so in a copy.

## 2. The command

- [x] 2.1 `accounts.insert(engine, email, role, key) -> Account`: one insert
      under the statement timeout; an integrity error on `accounts_email_lower`
      becomes `AlreadyEnrolled`; any other failure raises as itself. Module
      docstring: "`lookup` is the whole module" is no longer true — say what the
      second function is and why it lives here. Tests with an engine double:
      inserted; duplicate → `AlreadyEnrolled`; other error → not
      `AlreadyEnrolled`.
- [x] 2.2 `enrol.py`: `mint`, `revoke`, the exceptions (`Uncapped`,
      `AlreadyEnrolled` re-exported, `NothingEnrolled`, `KeyLeftBehind`), and
      `enrol()`. `mint` checks the echo (`limit`, `limit_reset`), tries one
      `PATCH` if `limit_reset` came back wrong, and revokes and raises if the
      echo still disagrees. `urllib` with an injectable `opener`, as
      `allowance.py`.
- [x] 2.3 Tests for `enrol()` with an opener double and an engine double, each
      refusal in its own test: `limit_usd` of `0`, `-1` and `None` → `Uncapped`
      **and the opener was never called**; bad role → refused before minting;
      duplicate → `AlreadyEnrolled` **and the minted key was revoked** (assert
      the `DELETE` on the opener); insert raises → `NothingEnrolled` and a
      `DELETE`; insert raises and `DELETE` fails → `KeyLeftBehind` naming the
      hash; echo with wrong `limit` → revoked and refused; echo with wrong
      `limit_reset` → one `PATCH`, then accepted if it agrees.
- [x] 2.4 `neon.py` (or a section of `enrol.py` if it stays under ~80
      lines): `branch_id(api_key, project, name, *, opener)` — `search=name`,
      then exactly one exact `name` match or `BranchNotFound` listing what was
      found; `connection_url(api_key, project, branch_id, *, database, role,
      opener)` — `pooled=true`, scheme rewritten to `postgresql+psycopg://`.
      Tests with an opener double: exact match among partial matches picks the
      exact one; no match → refused listing the partials; two exact matches
      (cannot happen at Neon, but the rule must hold) → refused; the URL comes
      back with the rewritten scheme and the `-pooler` host untouched.
- [x] 2.5 `main()`: `EMAIL ROLE --limit-usd N --branch NAME`, `--database`
      and `--role` with Neon's defaults. **`--branch` is required with no
      default**; argparse's own error is replaced by a sentence saying the row
      has to land in the branch the deployed app reads and that no branch is
      assumed. Refuses without `OPENROUTER_MANAGEMENT_KEY`, `NEON_API_KEY` or
      `NEON_PROJECT_ID`, naming the missing one. Resolves the branch before
      minting. Prints address, role, cap and branch on success and the
      refusal's sentence otherwise; exit codes. Tests: no `--branch` → the
      notice and nothing called on either opener; each missing variable; an
      unknown branch → refused and the OpenRouter opener never called; a
      success whose stdout does not contain the key, the hash or the URL
      (assert on the doubles' values, not on a fixed string).
- [x] 2.6 `pyproject.toml`: `scinumbers-enrol = "scinumbers_ask.enrol:main"`.
- [x] 2.7 `test_driver_independence.py`: `enrol` joins `HARNESS`. Seed
      `import streamlit` into a copy and name the tests that fail.

      *Seeded: killed `test_only_the_web_driver_knows_the_web_framework`.
      `neon` deliberately stays in the core — stdlib only, and the core side is
      the stricter placement.*
- [x] 2.8 Fault seeding, in a copy, over `enrol()`: `limit_usd >= 0` in place
      of `> 0`; insert before mint; revoke skipped on insert failure. Each must
      kill exactly the test that claims it. Write ADR-0900's claims after.

      *Copy at `$TMPDIR/seed-g2`, and **the harness had to be fixed before any
      verdict could be read from it**: the first arrangement copied `tests/` but
      set no `PYTHONPATH`, so the static guard read the copy while every runtime
      test imported the real package — four seeds "survived" and the table was
      clean. It survived only because the streamlit seed *did* die, which is the
      canary that said the other four could not have. The harness now aborts
      rather than print a table it did not earn, and needs both the copied tests
      and the path. Green baseline 119 passed.*

      *Against that: **E** `>= 0` for `> 0` → killed
      `test_a_credential_is_never_issued_without_a_cap[0]` and `[0.0]`, and
      rightly not `[-1]` or `[None]`. **F** the revoke removed → killed all
      three of the could-not-be-written tests. **G** the cap echo unchecked →
      killed `test_a_cap_that_comes_back_wrong_is_revoked_and_refused`. **H**
      (added) nothing minted at all → killed four, including the happy path.*
- [ ] 2.9 (operator, `network` marker) One live mint against OpenRouter with a
      $0.01 cap into a throwaway name, read the echo, then revoke — recording
      in the ADR whether `limit_reset` is honoured on create or needed the
      `PATCH`. The one live run this change needs.
- [ ] 2.10 `verifier` on group 2: measure that no test passes if `enrol()` mints
      before checking the cap, and that `KeyLeftBehind` carries the hash.

## 3. Documentation and the record

- [ ] 3.1 README §"Sign-in and enrolment": the operator's steps rewritten —
      Auth0 application (Regular Web App, callback `<app>/oauth2callback`,
      database connection with sign-up open and email verification required,
      the optional Action refusing unverified login), `[auth.auth0]` in the
      secrets box, `scinumbers-enrol` replacing step 3, and the Google consent
      screen to Production with the try-one-address note. Say that only a
      verified address is admitted, and why.
- [ ] 3.2 `.streamlit/secrets.toml.example` (where it lives — check `dev` and
      `deploy/streamlit-cloud`): the `[auth.auth0]` shape with the Auth0
      discovery URL, commented like `[auth]`.
- [ ] 3.3 `docs/roadmap.md` §WP3: the helper script is done; "any email" is
      done; note the Google step and what remains deferred.
- [ ] 3.4 CLAUDE.md: `enrol.py` row in the module table; the `accounts.py`
      row says lookup *and* insert; the ADR table row shows which of
      `0880`–`0900` are written.
- [ ] 3.5 `CHANGELOG.md` under Unreleased: Added (second provider, the
      command), Changed (verified address required).
- [ ] 3.6 `tests/test_spec_conformance.py`: map the modified requirement's new
      scenarios and the added requirement to the tests from groups 1 and 2;
      record as gaps the ones AppTest cannot drive (an actual second-provider
      round trip; the live mint).
- [ ] 3.7 ADRs `0880`, `0890`, `0900` filled in — each with the alternatives it
      rejected and, for `0890` and `0900`, the mutant that died. Status
      accepted, this branch as the pull request.

## 4. Landing

- [ ] 4.1 Full suite once, at the end (`.venv/bin/python -m pytest`); ruff.
- [ ] 4.2 Suggest `/code-review` on the branch, then merge to `dev` on the
      user's approval; archive the change so the delta is promoted.
- [ ] 4.3 (operator) Auth0: create the tenant and application, set the callback
      and logout URLs to the deployed app, open sign-up, require verification.
      Put `[auth.auth0]` in the deployed app's secrets box.
- [ ] 4.4 (operator) Google Cloud console: OAuth consent screen → Publish app.
      Sign in from an unlisted Google address and record what it shows.
- [ ] 4.5 (operator) Merge `dev` into `deploy/streamlit-cloud` and push it —
      the deploy branch is already 51 commits ahead of origin from last night's
      unpushed merge, so the deployed app is behind on more than this.
- [ ] 4.6 (operator) Create a Neon API key for the operator's shell; note
      `NEON_PROJECT_ID`. Enrol the first non-Google tester with
      `scinumbers-enrol ... --branch alpha` and have them sign in.
