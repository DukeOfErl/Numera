# Tasks

**ADR block: `1100`–`1140`**, reconciled against CLAUDE.md's table, which is the
authority. `1100` is the decision to keep a provider configured but unoffered.

## 1. The door

- [x] 1.1 `messages.py`: the invitation sentence, and `"auth0"` → "Sign in".
- [x] 1.2 `web.py`: `OFFERED_PROVIDERS` and `offered_providers()`, narrowing what
      is drawn and widening back where that would leave no button at all.
- [x] 1.3 Tests. The three that asserted two buttons are **rewritten rather than
      deleted**: what they pinned is machinery this change keeps, so each now
      exercises it below the door — the two `st.login` call forms through the
      only-Google fallback, secrets order through the nothing-offered fallback,
      and `providers()` against `offered_providers()` directly.
- [x] 1.4 Fault seeding. Three seeds against a green baseline of 81, all fatal:
      the widening dropped (five tests, including the empty-door case), the
      narrowing dropped, and `OFFERED_PROVIDERS` widened to include the default.

## 2. What the door says is kept

- [x] 2.1 `messages.py`: `PRIVACY`, `PRIVACY_HEADING` and `PRIVACY_CONTACT` --
      the long form of `RECORDS_NOTE`, which stays as the one-line version.
- [x] 2.2 `web.py`: `draw_privacy()`, called under every door rather than only the
      sign-in one; and the same expander in the panel, since the two audiences
      cannot reach each other's copy.
- [x] 2.3 Tests: reachable without signing in, collapsed, present for a signed-in
      reader, present under a refusal.
- [x] 2.4 ADR-1110, and the spec delta on *What is kept about a person*.

## 3. The record

- [x] 3.1 Spec delta on `user-identity`: configured and offered become different
      things, and the guarantee becomes at least one way in.
- [x] 3.2 ADR-1100 filled in.
- [x] 3.3 README, the secrets example and CHANGELOG.
- [ ] 3.4 Full suite and ruff; then `/code-review` and the merge on approval.

## 4. What the operator must check

- [ ] 4.1 (operator) **Auth0's Google social connection must be enabled**, or
      withdrawing the Google button withdraws Google sign-in altogether. Auth0
      enables one by default using *its own development keys*, which are rate
      limited and show their own consent warning — the Google client this project
      already owns should be pasted into that connection instead.
- [ ] 4.2 (operator) **Publish the Google consent screen.** The App domain and the
      privacy policy both point at the app's own address, which is what this change
      makes true; publishing is what lifts the 100-tester cap and the weekly
      consent expiry (ADR-1110).
