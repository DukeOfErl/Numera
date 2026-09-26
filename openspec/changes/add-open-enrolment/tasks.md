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
      alone, which is the one test claiming absence. **Seed B** → killed
      `test_an_unverified_address_is_refused_with_its_own_sentence` and
      `test_an_unverified_address_is_never_looked_up`. **Seed C** (added,
      unplanned) `providers()` always offering `"default"` → killed
      `test_providers_reads_the_default_and_every_sub_table` and
      `test_a_provider_with_no_label_still_gets_a_button`.*

      ***Correction, from the verifier (1.8).** Seed B was described above as
      "the check moved below the enrolment lookup", and that description is
      wrong: what was actually seeded replaced the whole block — check, record
      and all — with a bare check lower down, so the second kill was the missing
      `signin.unverified` record rather than the moved check. Moving the block
      intact, at either natural placement, kills only
      `test_an_unverified_address_is_never_looked_up`. The verifier tried to
      reproduce the note and could not, which is the whole reason a kill list is
      written down. **A seed has to be recorded as the diff it was, not as the
      defect it was meant to represent.***
- [x] 1.8 `verifier` on group 1: would any test still pass if `admit` admitted
      an unverified address? Measure by making it so in a copy.

      *PASS WITH FINDINGS. It confirmed its canary, then answered the question
      directly: deleting the check kills three tests, and four loosened
      predicates (`bool(value)`, `value is not None`, `value != False`,
      `str(value).lower() == "true"`) all die. **No survivor on the claim
      itself.** It also measured both populations rather than reading them,
      which is more than was asked: an identical probe on `admit` in trees built
      from this commit and its parent gives 38 tests reaching an open door
      before and 40 after, with the "admitted before, not after" set **empty**.
      The refused population grew by exactly the new door, 0 → 3.*

      *Six gaps, all now closed and each re-seeded to prove the fix:*

      *• **`st.login`'s argument was unpinned in both directions** — forcing
      `(provider,)` for everything and forcing `()` for everything each passed
      every test, while a comment two lines above asserted the two calls are not
      synonyms. Now pinned by clicking both buttons and reading what `st.login`
      was handed.*

      *• **The unverified door's "Sign out" could be deleted with nothing
      failing**, although its sentence tells the reader to sign in again. The
      `NO_CREDENTIAL` door has carried that assertion since it existed. Added.*

      *• **Order among named providers was unpinned**, so the docstring's "in
      the order secrets lists them" was decoration. The first fix did not work:
      one case with `zeta` before `auth0` is satisfied by reverse-sorting
      anyway — the case varied the outcome without varying what the rule reads.
      **Both orderings** are now fixtures, which no sort can satisfy; forward-
      and reverse-sorted both die.*

      *• **`providers()`'s non-mapping branch was executed by no test** in the
      whole 1603-test suite. Covered.*

      *• **Task 1.6's second clause had no artifact.** "The `provider` claim is
      not stamped on any trail record" was marked done with nothing asserting
      it. Now a test, and honestly labelled: it passes vacuously today because
      nothing reads that claim, and it exists for the day someone stamps it.*

      *• **The Seed B note was not reproducible**, corrected above.*

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
- [x] 2.9 (operator, `network` marker) One live mint against OpenRouter with a
      $0.01 cap into a throwaway name, read the echo, then revoke — recording
      in the ADR whether `limit_reset` is honoured on create or needed the
      `PATCH`. The one live run this change needs.

      *Run 2026-09-26, into the `dev` branch. Minted, row written, and
      `GET /api/v1/keys` reported `"limit": 0.01, "limit_reset": "monthly"`.
      **OpenRouter honours `limit_reset` on create**, so the `PATCH` retry has
      never run against the real provider — tested and mutation-covered, but
      unexercised in anger. ADR-0900 says so rather than implying the retry is
      known to work.*

      *The operator path was confirmed in the same run, and two things in it were
      wrong in the documentation beforehand: a **personal** Neon key refuses the
      list-projects call with `400 org_id is required` where an **organisation**
      key needs no such parameter and reaches both endpoints the command uses;
      and Neon's docs give `ep-cool-darkness-123456` as a project-id example,
      which is the shape of an endpoint id rather than a project id. Both
      corrected in the README, both found by running it rather than by reading.*

      *No `network`-marked test was added. The value here was the one-off answer
      about the provider's create-side behaviour, which is now in the ADR; a
      standing test would mint a real key on every marked run to re-answer a
      question already answered.*
- [x] 2.10 `verifier` on group 2: measure that no test passes if `enrol()` mints
      before checking the cap, and that `KeyLeftBehind` carries the hash.

      *PASS WITH FINDINGS, and the findings were worth the run. It confirmed its
      own canary first, then measured what holds: mint-before-insert is pinned
      (the reversed order killed four tests — **this is the seed 2.8 asked for
      and did not record**, so it is recorded here), `KeyLeftBehind` carrying
      the hash is pinned, and `neon.branch_id`'s exact match is the best-defended
      thing in the change (three tests die on "take the first").*

      *Four real gaps, all now closed and each re-seeded to prove the fix:*

      *• **A measured survivor.** `_same_amount` with strict `==` passed the
      whole suite. `5 == 5.0` in Python, so an int/float fixture cannot tell the
      two implementations apart and the function's stated reason for existing
      was untested. Now pinned by an echo of `"5"` (dies) and by echoes that are
      not numbers at all (dies).*

      *• **Three regions no test executed**, each behind a docstring claiming
      behaviour: `_same_amount`'s unreadable-echo branch, `_revoke_quietly`'s
      except (whose sentence about not hiding the original failure had no
      artifact), and `main`'s except around `enrol` — so no `enrol`-level
      refusal was ever driven through the command. All three now covered; the
      three modules are at 100% line coverage, which here means the branches
      exist rather than that they are asserted.*

      *• **A test that reached the real Neon control plane.** Deleting the
      `--branch` guard let `test_the_command_refuses_without_a_branch_and_says_why`
      out to `console.neon.tech` — its doubles covered `branch_id` and `enrol`
      but not `connection_url`, while its assertion read as "nothing was
      called". The double is now as wide as the claim. An unmarked test making a
      live call is the more serious half of this.*

      *• **Half an assertion that could not fail.** `HASH not in said` on the
      success path is unfalsifiable — `main` holds an `Account`, which carries no
      hash. Made real by driving `KeyLeftBehind` through `main` and asserting the
      hash **is** there and the key is not.*

## 3. Documentation and the record

- [x] 3.1 README §"Sign-in and enrolment": the operator's steps rewritten —
      Auth0 application (Regular Web App, callback `<app>/oauth2callback`,
      database connection with sign-up open and email verification required,
      the optional Action refusing unverified login), `[auth.auth0]` in the
      secrets box, `scinumbers-enrol` replacing step 3, and the Google consent
      screen to Production with the try-one-address note. Say that only a
      verified address is admitted, and why.
- [x] 3.2 `.streamlit/secrets.toml.example` (where it lives — check `dev` and
      `deploy/streamlit-cloud`): the `[auth.auth0]` shape with the Auth0
      discovery URL, commented like `[auth]`.
- [x] 3.3 `docs/roadmap.md` §WP3: the helper script is done; "any email" is
      done; note the Google step and what remains deferred.
- [x] 3.4 CLAUDE.md: `enrol.py` row in the module table; the `accounts.py`
      row says lookup *and* insert; the ADR table row shows which of
      `0880`–`0900` are written.
- [x] 3.5 `CHANGELOG.md` under Unreleased: Added (second provider, the
      command), Changed (verified address required).
- [x] 3.6b `docs/diagrams/architecture.md` (added; the change did not plan it):
      3b redrawn — the verification check is before the lookup, and that order is
      the claim ADR-0890 rests on — and a new 3c for the enrolment command's two
      side effects and its compensation. **Not rendered**: no mermaid CLI is
      installed and npm is unreachable from this sandbox, so the blocks were
      checked structurally only. A previous commit on this repo had to fix a 3b
      that did not parse, so this is worth someone's eye before merge.
- [x] 3.6 `tests/test_spec_conformance.py`: map the modified requirement's new
      scenarios and the added requirement to the tests from groups 1 and 2;
      record as gaps the ones AppTest cannot drive (an actual second-provider
      round trip; the live mint).
- [x] 3.7 ADRs `0880`, `0890`, `0900` filled in — each with the alternatives it
      rejected and, for `0890` and `0900`, the mutant that died. Status
      accepted, this branch as the pull request.

## 3b. Mutation testing (added; the change did not plan it)

- [x] 3b.1 `mutmut` over `enrol.py`, via the `mutation-test-module` skill. Three
      runs, survivors diffed **by name** rather than by count.

      *109 survivors → 94, fifteen killed, none newly surviving. Two real
      findings and one class:*

      *• **`limit_usd > 0` could be widened to `> 1`** with nothing failing, so
      a fifty-cent cap would have been refused for no stated reason. The spec
      says "no cap or a cap that is not positive", which puts the boundary at
      zero — so the assertion comes from the requirement, not from running the
      code. Killed.*

      *• **The class only this tool finds here: the double checked a request's
      shape and never its credential.** `management_key` could be replaced by
      `None` at six call sites — including all four compensating revokes, where
      `_revoke_quietly` swallows the failure by design — and the whole suite
      stayed green. Against the real provider every one of those is a 401: the
      key is minted and then neither recorded nor withdrawn, which is precisely
      the outcome ADR-0900 is arranged to avoid. Fixed in the **double**, which
      now refuses an unauthenticated call the way OpenRouter does, rather than by
      repeating an assertion in eight tests. Also pinned: that the compensating
      revoke *succeeded* rather than merely was attempted, since a swallowed
      failure satisfies "a DELETE was sent".*

      *• The timeout was unasserted — `timeout=None`, and the argument dropped
      entirely, both survived. An operator waiting at a prompt has to meet a
      failure rather than a hang. Pinned.*

      *What is left is the noise the skill names: 32 argparse help strings, 32
      print strings in `main`, and the rest string-literal case and `XX`
      sentinel flips in error messages. That is a clean stopping point for this
      module.*

      *Worth recording: several mutants made **real outbound calls** to
      `openrouter.ai` and `console.neon.tech`, which the sandbox refused. That is
      a mutant-only condition rather than a defect in shipped code, but it is the
      same shape as the review's finding about a double narrower than its
      assertion — an unmarked test can reach the network when the code around it
      moves.*

- [ ] 3b.2 `mutmut` over `neon.py` and `accounts.py` — **not run.** `enrol.py`
      took three runs at about ten minutes each and the run was stopped before
      these two. Both are small (30 and 43 statements) and both are at 100% line
      coverage under their own tests, which says the lines execute and not that
      they are asserted. `neon.branch_id`'s exact-name match is the guard against
      the silent wrong write and was seeded by hand and by a verifier, so it is
      the best-defended thing in the change; `accounts.insert`'s SQLSTATE rule
      was seeded after the review. Neither is unexamined, but neither has had
      this instrument.

## 3c. The operator's own credentials (added; from a question, not the plan)

- [x] 3c.1 A refused management key or Neon API key says which credential and
      what to do, in `_post` and `_get` so mint, patch, revoke and both branch
      calls are covered by one guard. Any status other than 401/403 is reported
      as itself.

      *Asked because the operator put an expiry on the management key and wanted
      to know whether a reader would ever meet it. **They cannot** — the
      management key is read by `enrol.py` alone, readers are handed their own
      runtime key, and `mint` sets no expiry on those. But the operator met a
      bare `HTTP Error 401: No auth credentials found`, naming nothing.*

      *Four seeds against a green baseline of 50, each direction: widening
      `REFUSING_STATUSES` to include 429/500/502/503 killed all four
      status-code negatives; removing the translation killed the message tests
      in both modules. **The negatives vary the status code**, which is the
      dimension the rule reads — the same shape as `_is_out_of_credit` in
      `.claude/rules/testing.md`, where negatives carrying no status at all let
      a fatal mutant through.*

      *Also documented: where to keep the three values. Not the command line
      (shell history), not `~/.bashrc` (a key that mints unlimited keys, in
      every process), but a mode-600 file outside the repository loaded on
      demand. **The command still reads nothing but the environment**, and that
      is deliberate rather than an omission to fix later — the same reasoning
      that keeps it away from `.streamlit/secrets.toml`.*

## 4. Landing

- [x] 4.1 Full suite once, at the end (`.venv/bin/python -m pytest`); ruff.

      *1603 passed, 3 skipped, 46 deselected. The first full run failed one test
      the three-file runs could never reach:
      `test_no_text_reaches_the_page_unescaped[web.py:747]`, because an
      unlabelled provider's button carries a name out of secrets to the page and
      a `$` there opens inline mathematics. Now through `as_text`. Worth
      recording as the case for running the whole suite once rather than the
      files a change touched.*
- [ ] 4.2 Suggest `/code-review` on the branch, then merge to `dev` on the
      user's approval; archive the change so the delta is promoted.

      *Review run at `high`. Seven findings, all acted on; each fix seeded into
      a copy against a green baseline of 134, and each killed exactly the test
      claiming it.*

      *• **`providers()` called any mapping a provider.** `client_kwargs` is a
      documented mapping under `[auth]` — the installed Streamlit lifts it into
      the default provider's own section — so the door grew a third button that
      could not work. The discriminator is now `client_id`, which is one of the
      three keys `validate_auth_credentials` requires. Taken from the record,
      not reasoned from the shape. Two cases shared that root: a sub-table
      literally called `default` produced two buttons with one key, which is a
      `StreamlitDuplicateElementKey` and takes the whole door down; and `[auth]`
      with no credentials anywhere drew a sentence and **no button**, where the
      old code at least reached Streamlit's own "credentials are missing" error.
      The button is drawn again in that case, deliberately: the visitor is stuck
      either way and the operator is not.*

      *• **`MintFailed` promised revocation it did not perform.** With a hash
      returned and no key, a capped credential existed at OpenRouter and this
      process was the only thing that knew its handle. It is withdrawn now; with
      no hash the operator is told to look at the dashboard rather than
      reassured.*

      *• **A `PATCH` that could not be sent escaped `mint` un-revoked.** The two
      *checked* failures withdrew the key; the transport failure between them did
      not, and `enrol` could not compensate because no `Minted` was returned.*

      *• **A false claim in `test_spec_conformance.py`**: the note said the
      provider honouring `limit_reset` on create was covered by a
      `network`-marked live check. There is no such test. That is the worst kind
      of note in this project — it retires the suspicion that would find the
      surprise — and it is corrected to say the thing is unverified.*

      *• **`providers()` raised on a secrets file with no `[auth]`**, where its
      own docstring promised an empty list. `_is_not_configured` matches
      Streamlit's error types by design and a plain `KeyError` is not one, so
      the `KeyError` is caught where it happens rather than by widening that
      predicate.*

      *• **Every `IntegrityError` was reported as "already enrolled."** Right
      against today's schema and wrong the day a `check` constraint is added,
      when the operator is sent looking for a row that is not there while the
      minted key is silently withdrawn. Narrowed to SQLSTATE `23505`, which is
      the database's own code and survives the index being renamed.*

      *• **Diagram 3c drew the cap and role checks before the Neon lookup; the
      code ran them after**, so `--limit-usd 0` cost two live control-plane calls
      before refusing. Here the drawing was the better design, so the code moved
      to match it: `checked()` is one expression of the rule, run by `enrol`
      because the guard belongs to the operation and by the command first so a
      typo is free.*

      *• A non-finding worth acting on: the unverified refusal was recorded on
      **every rerun**, the only door charging the trail an insert per click. The
      decision still runs fresh — it must, because `end_session` does not clear
      it — and the record is now held.*
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
