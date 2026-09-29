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

- **The door carries the privacy policy**, collapsed, and so does the side panel.
  Google will not take an OAuth consent screen out of Testing without a policy at a
  public address, and Testing caps testers at 100, admits only hand-added ones and
  expires their consent weekly. The door is already the unauthenticated page, so the
  app's own address is that public address and no second host is involved (ADR-1110).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-identity`: the requirement *"A reader signs in before anything is shown,
  and identity comes from the provider"* — being configured and being offered
  become different things, and the guarantee becomes that a visitor is always
  offered at least one way in rather than one per configured provider.
- `user-identity`: the requirement *"What is kept about a person, and that they are
  told"* — the fuller statement stops being deferred and becomes required, offered
  rather than imposed, and readable without signing in.

## Impact

**Code.** `messages.py`: the door's sentence, the Auth0 label, and `PRIVACY` with
its contact. `web.py`: a new `OFFERED_PROVIDERS` and `offered_providers()`, and
`draw_privacy()` called from `draw_closed_door`. `streamlit_app.py`: the same
expander in the panel. Nothing is deleted.

**Documentation.** README's sign-in section, `.streamlit/secrets.toml.example`,
`CHANGELOG.md`, ADR-1100 and ADR-1110.

**Deliberately unaffected.** Enrolment, the verified-address check, the trail, and
what a signed-in reader sees. This is the door's face, not its decisions.
