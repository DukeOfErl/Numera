# ADR-0880: A second identity provider beside the first, never in place of it

- **Status:** accepted
- **Date:** 2026-09-18
- **Pull request:** _pending — `feat/open-enrolment`_

## Context

Sign-in was Google and only Google (ADR-0780, README §"Sign-in and enrolment"),
which shuts out every tester whose working address is not a Google account — a
real share of the biologists this is for. The Google side also caps the app: an
OAuth consent screen in "Testing" admits at most 100 addresses and each one is a
row the operator adds by hand in a console, with the tester's consent expiring
after seven days.

Four options were on the table.

- **Neon Auth.** Attractive because the accounts table is already in Neon. It is
  managed Better Auth: email/password, email OTP, magic link, social login, JWT,
  an admin plugin — and, read from its own overview and roadmap on 2026-09-18,
  **not an OpenID Connect provider**. Streamlit's `st.login` speaks OIDC and
  nothing else, and Streamlit sets its identity cookie in exactly one place, the
  `/oauth2callback` route; `st.context.cookies` is read-only. So adopting Neon
  Auth means a hand-built sign-in form posting to its REST API, a JWT verified
  against its JWKS, and a session held in `st.session_state` — which dies on
  every browser reload. Its SDKs are JavaScript only and its roadmap lists
  "standalone frontend + backend" as not yet supported.
- **Replace the Google client with Auth0**, using Auth0's Google social
  connection to keep Google sign-in. One button rather than two. Every current
  tester re-consents through a new tenant, and the unverified-app warning moves
  from Google's consent screen to Auth0's development keys, which show one of
  their own.
- **Microsoft as the second provider.** Still an account a tester may not have.
- **Auth0 as a second OIDC provider beside the existing Google client.**

## Decision

**Auth0 under `[auth.auth0]` in secrets, with the Google client left exactly
where it is as the default provider.** `web.providers()` reads the `[auth]`
section once and returns `"default"` when `client_id` sits in the section itself,
followed by every sub-table; `draw_closed_door` draws one button per provider,
labelled from `messages.SIGN_IN_LABELS` and falling back to "Sign in with
&lt;name&gt;". `st.login()` is called with no argument for the default and with
the name otherwise — Streamlit treats those as different calls, and "default" is
not a synonym for the unnamed form.

The address is the identity. The `provider` claim is not part of the session key
(ADR-0830 keys it on the account) and is not stamped on the trail, so a tester
who used Google yesterday and email today keeps their role and their
conversation.

## Trade-off accepted

**Two buttons instead of one**, and two consent screens to keep configured. That
is the price of not making every existing tester re-consent, and it buys an
honest statement: each button is the provider it says it is.

**A third identity provider is now a secrets edit plus, at most, one row in
`SIGN_IN_LABELS`.** That is deliberate, and it means the door's shape is decided
by a file this repository does not contain. `providers()` reads the section it is
given and draws what is there; a mistyped sub-table becomes a button nobody can
use rather than an error.

**Auth0 is a dependency on a hosted service with a free tier.** If it becomes
unacceptable, the Google client still works and the section is deleted — the
verified-address check (ADR-0890) is the only thing that stays, and it is a
no-op for Google.

**If Neon ever ships an OIDC provider, this decision does not have to be
revisited** — it becomes one more `[auth.<name>]` sub-table. That is the main
reason for preferring a second provider over a hand-built form.
