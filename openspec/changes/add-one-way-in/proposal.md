## Why

The door asks a visitor to sign in without saying why there is a door, and then
offers two buttons that reach the same accounts. A reader who was not invited reads
"Sign in to ask a question" as a system that has not recognised them yet and tries
again; and a reader who was invited has to choose between Google and email when
Auth0 signs them in with their Google account either way.

## What Changes

- **The sentence says why, not what.** "Use of this app is by invitation only since
  you are using the developer's budget." The button already says what to do, and
  the reason is the part a stranger needs. Naming the budget is also the honest
  form: this is one person's money, which is why every account is capped.
- **One button, labelled "Sign in".** The Google button is withdrawn because Auth0
  authenticates a reader with their Google account anyway, so the choice was
  between two routes to one thing. With one button the label no longer has to
  distinguish a method.
- **The Google client stays configured, and every line of the multi-provider
  machinery stays.** `providers()` still finds it, `st.login()` would still use it,
  and the tests still exercise both call forms and the ordering. What changed is
  which of the configured providers the door draws — one tuple, `OFFERED_PROVIDERS`.
  Switching back is that tuple and nothing else.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-identity`: the requirement *"A reader signs in before anything is shown,
  and identity comes from the provider"* — being configured and being offered
  become different things, and the guarantee becomes that a visitor is always
  offered at least one way in rather than one per configured provider.

## Impact

**Code.** `messages.py`: the door's sentence and the Auth0 label. `web.py`: a new
`OFFERED_PROVIDERS` and `offered_providers()`, and one call site in
`draw_closed_door`. Nothing is deleted.

**Documentation.** README's sign-in section, `.streamlit/secrets.toml.example`,
`CHANGELOG.md`, ADR-1100.

**Deliberately unaffected.** Enrolment, the verified-address check, the trail, and
what a signed-in reader sees. This is the door's face, not its decisions.
