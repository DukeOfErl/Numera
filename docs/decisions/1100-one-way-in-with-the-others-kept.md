# ADR-1100: One way in, with the rest kept configured but not offered

- **Status:** accepted
- **Date:** 2026-09-28
- **Pull request:** _pending — `feat/one-way-in`_

## Context

ADR-0880 put a second identity provider beside the Google client so that an address
which is not a Google account could sign in, and the door drew a button for each
configured provider. That was right while the two reached different populations.

It stopped being right once Auth0 was actually configured. Auth0 signs a reader in
with their Google account through its own Google connection, so the two buttons are
two routes to the same accounts — and the reader has to choose between them knowing
nothing that would inform the choice. The labels made it worse rather than better:
"Sign in with Google" and "Sign in with email" describe *methods*, which reads as a
consequential decision about how their identity will be held.

Three options for withdrawing the second button:

- **Delete the Google client from secrets.** No code changes at all: `providers()`
  finds one provider and draws one button. But restoring it means re-establishing
  the client's credentials in the deployment's secrets box, and the thing being
  withdrawn is a button, not a client.
- **Delete the multi-provider code.** It was written, reviewed, seeded and
  mutation-tested three weeks ago; deleting it to draw one button means writing it
  again when a third provider arrives — and this project has already learned that
  Neon Auth may one day be an OIDC provider (ADR-0880), at which point it is one
  sub-table.
- **Keep everything and narrow what is drawn.**

## Decision

**`OFFERED_PROVIDERS` in `web.py` names which configured providers the door draws,
and it is `("auth0",)`.** Google's client stays in secrets, `providers()` still
finds it, `st.login()` would still use it, and the tests still exercise both call
forms and the ordering. Restoring the button is that tuple and nothing else.

**A door with no button is never the right answer**, so `offered_providers()` widens
back twice. If nothing configured is offered — a developer's machine with only the
Google client — every configured provider is drawn instead of none. And `[auth]`
present with no credentials anywhere still draws the default, because `st.login()`
then raises Streamlit's own "credentials are missing" error naming the keys: the
visitor is stuck either way and the operator is not.

The spec follows: being *configured* and being *offered* become different things,
and the guarantee becomes that a visitor is always offered at least one way in
rather than one per configured provider.

Two wordings change with it. The door says **why** there is a door — "Use of this
app is by invitation only since you are using the developer's budget" — because the
button already says what to do, and a stranger needs the reason. Naming the budget
is the honest form: this is one person's money, which is also why every account is
capped (ADR-0780). And the remaining button says just **"Sign in"**, since there is
no longer another method to distinguish it from.

## Trade-off accepted

**Dead configuration, deliberately.** A provider sits in secrets that nothing draws,
which is exactly the kind of thing that rots unnoticed. Two things hold it: the
tests exercise the machinery through the widening paths rather than through the
Google button, so it cannot silently stop working; and `OFFERED_PROVIDERS` is one
line with the reason above it.

**The operator must enable Auth0's Google connection**, or withdrawing this button
withdraws Google sign-in altogether. Auth0 provides one by default using *its own
development keys*, which are rate-limited and show their own consent warning, so the
Google client this project already owns belongs in that connection. That is an
operator step and it is in `tasks.md`, not something the code can check.

**A reader's route changes.** Somebody who signed in through the Google button
before will now sign in through Auth0, which is a different provider asserting the
same address — so they sign in once more, and continue as the same reader with the
same role and conversation, because the address is the identity and not the route to
it (ADR-0880).
