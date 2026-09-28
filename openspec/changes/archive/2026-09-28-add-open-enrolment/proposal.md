## Why

Only a Google account can sign in, and every new tester costs the operator three
hand steps in three consoles: list the address as a test user in Google Cloud,
mint a capped key at OpenRouter, insert the row in Neon. The first step also
caps the app at 100 testers and shuts out anyone whose address is not a Google
account — a real share of the biologists this is for. Enrolment was left as
"a helper script for later" in ADR-0780 and the roadmap; with the sign-in path
changing anyway, this is when to collapse the three steps into one.

## What Changes

- **A second identity provider, Auth0, beside Google.** Streamlit's `st.login`
  accepts any OpenID Connect provider, so Auth0 is a second named provider in
  secrets and a second button, "Sign in with email". Google stays as it is;
  nothing a current tester does changes. Auth0 is chosen over Neon Auth because
  Neon Auth is not an OIDC provider and Streamlit has no other way to set the
  identity cookie — the reasoning goes in an ADR.
- **Only a verified address opens the door.** Where sign-up is open, anyone can
  create an account under an enrolled tester's address; the provider's
  `email_verified` claim is what separates the two. A signed-in account whose
  address the provider has not verified is refused with its own sentence,
  distinct from "not enrolled", and a missing claim counts as unverified.
- **Enrolment becomes one command**, `scinumbers-enrol`: mint a runtime key at
  OpenRouter with a monthly cap, insert the `accounts` row into the Neon branch
  the operator names, print the row without the key. The branch is required
  and has no default — the operator will forget which environment is which
  exactly when adding a tester, and a default would be wrong then — so the
  command resolves the name through Neon's API rather than reading any file.
  It refuses an address already enrolled and refuses to issue an uncapped
  credential — ADR-0780's argument rests on the cap. If the row cannot be
  written, the key it minted is revoked, so a failure leaves nothing behind.
- **The Google consent screen moves to Production**, so a tester need not be
  listed by hand before signing in. An operator step, documented, not code.
- **Operator documentation**: the Auth0 tenant (database connection with
  sign-up open, email verification on), the secrets shape, the one-command
  enrolment, and the Google step.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-identity`: the requirement *"A reader signs in before anything is shown,
  and identity comes from the provider"* — more than one provider may be
  offered, an account is the same account whichever provider asserted it, and
  the provider must have verified the address. A new requirement beside it:
  *"Enrolling an account is one operator action, and it never issues an
  uncapped credential."*

## Impact

**Code.** `web.py`: the sign-in door draws one button per configured provider;
`admit` gains the verified-address refusal and a `Door` for it. `messages.py`:
the second button's label and the refusal's sentence. `accounts.py`: an insert
beside the lookup, the one module that knows the table. New `enrol.py`, core
side, no Streamlit: the OpenRouter Management API calls (mint, verify, revoke),
the Neon API calls (branch by name, connection URL), the orchestration, and the command's `main`; joins `HARNESS` in
`test_driver_independence.py` so the thing meant to run from a terminal can
never reach for the web driver. `pyproject.toml`: the `scinumbers-enrol` entry
point. No new dependency — `urllib` as `allowance.py` already uses.

**Configuration and secrets.** `[auth.auth0]` in the secrets box: `client_id`,
`client_secret`, `server_metadata_url`. For the command, three environment
variables in the operator's shell: `OPENROUTER_MANAGEMENT_KEY`, `NEON_API_KEY`
and `NEON_PROJECT_ID`. None enters the repository, and no database URL is
kept in a file — `secrets.toml.example`'s one-URL rule stands; the command
fetches the named branch's URL and holds it in memory for one insert.

**Storage.** None. The `accounts` table is unchanged.

**Documentation.** README §"Sign-in and enrolment"; `.streamlit/secrets.toml.example`
where it lives; `docs/roadmap.md` §WP3 (the helper script is no longer "left for
later"); CLAUDE.md's module table and ADR block; `CHANGELOG.md`; the conformance
mapping. ADRs `0880`–`0900` of block `0880`–`0920`.

**Deliberately unaffected.** The agent, the trail, feedback: identity still
stops at the driver. The terminal driver and the evaluation harness. Existing
Google testers: their button, their session key, their rows.
