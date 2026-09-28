## Context

See `proposal.md` — Why. What shapes the approach, all read from the installed
code or the providers' current documentation on 2026-09-18, not remembered:

- **Streamlit 1.61.1's `st.login(provider)` takes any OIDC provider.** Shared
  settings (`redirect_uri`, `cookie_secret`) live in `[auth]`; a named provider
  is a sub-table `[auth.<name>]` with `client_id`, `client_secret`,
  `server_metadata_url`; `st.login()` with no name means the default provider,
  whose credentials sit directly in `[auth]` — which is where Google's are
  today. Names may not contain underscores (`auth_util.py`).
- **`st.user` is the ID token's claims, whole.** The callback route stores
  `token["userinfo"]` plus `origin`, `is_logged_in` and `provider`
  (`starlette_auth_routes.py`, line 616). So `email_verified` and `provider`
  are there for the asking, and `signed_in_email` already reads the dict.
- **Neon Auth is managed Better Auth, and not an OIDC provider.** Its roadmap
  lists email/password, OTP, magic link, social login, JWT and an admin API;
  nothing acts as an authorization server for a third-party app, and the SDKs
  are JS only. Streamlit sets its identity cookie in exactly one place — the
  `st.login` callback — and has no first-party way to set another. Together:
  wiring Neon Auth in means a hand-built sign-in form whose session dies on
  reload. That is the decision this design does *not* take.
- **Auth0 is a plain OIDC provider.** Discovery at
  `https://<tenant>.<region>.auth0.com/.well-known/openid-configuration`, a
  "Regular Web Application" gives a client id and secret, callback URLs are an
  allowlist. A database connection with sign-up open lets anyone register an
  address; Auth0 sends the verification mail and sets `email_verified` in the ID
  token. Magic links are not supported under Universal Login; email/password
  with verification is the flow.
- **Google in "Testing" caps the app at 100 listed test users** and makes each
  one an operator step. Google's own page on when verification is not needed
  leaves it ambiguous whether an unverified app in Production shows a
  click-through warning for `openid email profile`. The step is an operator's,
  and the doc says to try one address first.
- **OpenRouter's Management API** (`docs/roadmap.md` §WP3 table, verified
  2026-09-16): `POST /api/v1/keys` with `name`, `limit`, `limit_reset`;
  `DELETE /api/v1/keys/{hash}`; the response carries the key once, under
  `key`, and the `hash` that names it afterwards. A management key mints and
  cannot itself ask.
- **`accounts.lookup` case-folds and the unique index is on `lower(email)`**,
  so "already enrolled" is a case-insensitive question and a second insert
  fails on the index — which is the guard to lean on, not a select-then-insert.
- **The secrets file holds exactly one database URL, the branch this checkout
  writes to.** An operator's laptop points at `dev`; the row has to land in the
  branch the deployed app reads. The command cannot read its URL from that file
  without either the wrong branch or a spare URL on disk.
- **Neon's API resolves a branch to a URL in two calls**, but takes the branch
  by id: `GET /projects/{id}/branches?search=` filters by partial name or id,
  and `GET /projects/{id}/connection_uri` needs `branch_id`, `database_name`
  and `role_name`, with `pooled=true` for the `-pooler` host.
- **Guards belong to the operation.** The command's `main` keeps the wording;
  `enrol()` keeps every refusal, so a test or a second caller meets them too.

## Goals / Non-Goals

**Goals.** Any address can sign in, and only a verified one gets through. A
tester is enrolled by one command that cannot leave an uncapped key or an
orphaned one behind, and cannot write into a branch the operator did not name.
Nothing a Google tester does today changes.

**Non-Goals, at the design level:**

- **Not Neon Auth**, for the reason above. If Neon ships an OIDC provider,
  it becomes one more `[auth.<name>]` sub-table and nothing here changes.
- **Not retiring the Google client** behind Auth0's Google social connection.
  It would give one button, at the cost of every current tester re-consenting
  through a new tenant. One button can come later; today two is honest.
- **Not withdrawal, re-keying or role changes from the command.** Each is an
  `update` in `sql/accounts.sql` with a template; the command does the one
  thing that needs two systems to agree.
- **Not a sign-up gate of the app's own** (invite codes, an allowlist at the
  provider). Enrolment is the gate, as before; open sign-up at Auth0 costs
  nothing because an unenrolled account is refused at the door.

## Decisions

### A second named provider beside the default, never in place of it — ADR-0880

Auth0 goes under `[auth.auth0]`; Google stays as the default provider in
`[auth]` untouched. The door draws one button per configured provider:
`web.providers()` reads `st.secrets["auth"]` once — the default is present when
`client_id` is in the section itself, and each sub-table that is a mapping is a
named one. Labels come from `messages.py` keyed by provider name, the default
keeping today's "Sign in with Google"; an unknown name gets "Sign in with
<name>", so a third provider costs a secrets edit and nothing else.

*Alternatives considered.* Neon Auth: not OIDC, see Context; a hand-rolled
form and a session that dies on reload. Replace Google with Auth0 and add
Google as a social connection there: one button, but every current tester
re-consents through a new tenant and the Google client's Production question
moves to Auth0's dev keys, which show their own warning. Microsoft as the
second provider: still an account the tester may not have.

### Only a verified address opens the door, and absence is "not verified" — ADR-0890

`admit` gains one check before the enrolment lookup: the asserted claims must
carry `email_verified` and it must be true. Otherwise `Door.UNVERIFIED`, its own
sentence in `messages.py`, recorded through the same path as a refused sign-in
so the operator sees who tried. **A missing claim refuses.** Google always sends
the claim; Auth0 sends it; a provider that does not is one whose accounts this
app cannot tell from impersonation, and the expensive direction here is a wrong
admission that looks ordinary. The check reads the claims dict, not `st.user`
directly, so `signed_in_email` stays a one-liner and the rule is testable
without Streamlit.

*Alternative considered.* Configure Auth0 to refuse login until verified (an
Action), and trust the provider. Rejected as the *only* guard: it protects one
caller, at one provider, by a setting nothing in this repository can see. The
Action is worth setting too — it gives the reader Auth0's own "verify first"
page — but the refusal belongs to the operation.

### The session key is the address, so a second provider is not a second account

`effective_session` already derives the key from the account (ADR-0830). The
`provider` claim is not part of the key and not stamped on the trail. A tester
who used Google yesterday and email today continues the same conversation with
the same role. Nothing to build; a test to write.

### Enrolment is mint-then-insert with compensation, and every refusal is in `enrol()` — ADR-0900

`enrol.py`, core side, no Streamlit, `urllib` as `allowance.py` uses:

- `mint(management_key, *, name, limit_usd, opener)` posts to
  `/api/v1/keys` with `{"name": name, "limit": limit_usd, "limit_reset":
  "monthly"}` and returns `(key, hash, echoed)`. It **checks the echo**: if the
  response's `limit` is not the amount asked or `limit_reset` is not `monthly`,
  it revokes what it just made and raises. A verification that cannot fail is
  not one; the first live run has to show the echo can disagree (a `limit` of
  the wrong shape, in a copy) before the check is believed.
- `revoke(management_key, hash, *, opener)` deletes.
- `accounts.insert(engine, email, role, key)` — beside `lookup`, because the
  table's knowledge stays in one module. It runs the insert and lets the
  `lower(email)` unique index refuse a duplicate, translated to
  `AlreadyEnrolled`. No select first: two operators enrolling the same address
  at once would both pass a select.
- `enrol(engine, management_key, email, role, limit_usd, *, opener)` is the
  operation: refuses `limit_usd` that is not `> 0` **before** minting
  (`Uncapped`); validates `role` against `Role`; mints; inserts; on any
  insert failure revokes and re-raises as `NothingEnrolled`; if the revoke
  fails too, raises `KeyLeftBehind` naming the hash. Returns the `Account`
  without the key in its report form.
- `main()` is the `scinumbers-enrol` entry point: `EMAIL ROLE --limit-usd N
  --branch NAME`. Reads `OPENROUTER_MANAGEMENT_KEY`, `NEON_API_KEY` and
  `NEON_PROJECT_ID` from the environment and refuses without any of them,
  saying which. Resolves the branch (next decision) before minting, so a
  wrong branch name costs nothing. Prints the address, the role, the cap and
  the branch; never the key, never the hash on success.

*Alternatives considered.* Insert first, then mint and update the row with the
key: a row with a NULL key admits the tester to a "no credential issued" door
mid-way, and a failed mint leaves an account that looks deliberately keyless.
Select-then-insert for the duplicate check: racy, and the index is already
there. A `--dry-run`: nothing to rehearse that the refusals do not already
cover before any side effect.

### The operator names the branch, every time, and the command resolves it through Neon's API

`--branch NAME` is required and has no default. Without it the command refuses
before doing anything, and the refusal says why: the row has to land in the
branch the deployed app reads, and a default would be the wrong one exactly
when the operator has forgotten which that is. `dev` is a legitimate name for
a local rehearsal; it is never assumed.

Resolution, verified against api-docs.neon.tech on 2026-09-18:

1. `GET https://console.neon.tech/api/v2/projects/{project}/branches?search=NAME`
   with `Authorization: Bearer $NEON_API_KEY`. `search` matches partially, so
   the command requires **exactly one branch whose `name` equals `NAME`**; none
   or several is a refusal that lists the names it did find.
2. `GET .../projects/{project}/connection_uri?branch_id=...&database_name=...
   &role_name=...&pooled=true`. The response's `uri` is a standard Postgres
   URL; the scheme is rewritten to `postgresql+psycopg://` — the same rule the
   secrets example states for a URL copied from the console — and the engine is
   built through `trail_store.engine_from_url` so the connect timeout is set.
   The URL is held in memory for the one insert and printed nowhere.

The project id comes from `NEON_PROJECT_ID`, the API key from `NEON_API_KEY`;
`--database` and `--role` default to Neon's own defaults (`neondb`,
`neondb_owner`) and are flags because a project can rename either. The command
refuses without either variable, naming the missing one.

The command **does not read `.streamlit/secrets.toml`.** That file's one URL is
the branch the *checkout* writes to, which on a laptop is `dev`, and enrolling
into `dev` is the silent wrong write this project's one-URL rule exists to
prevent: the deployed app looks the tester up in `alpha`, says "not enrolled",
and the operator finds the row in the table they can see.

*Alternatives considered.* `SCINUMBERS_ACCOUNTS_URL` pasted for the one
invocation: no second secret, but a paste the operator has to get right each
time, and nothing stops the `dev` URL being pasted. A default branch: the
failure this decision exists to make impossible. Reading the deployed app's
secrets box: not reachable from a laptop.

### `enrol` joins `HARNESS`

It runs unattended from a terminal and must never reach for the web driver or
Streamlit. `test_driver_independence.py`'s `HARNESS` set is exactly that rule,
and the set decides by subtraction what counts as core, so the name goes in as
the file lands (CLAUDE.md, Architecture).

## Risks / Trade-offs

- **A provider that omits `email_verified` shuts its users out** → by design;
  the sentence says why and the operator can see the refusal in the trail.
- **Open sign-up at Auth0 invites noise** → an unenrolled verified account is
  refused as today, and each attempt is recorded, which is the enrolment
  queue the operator wanted anyway. Auth0's free tier bounds cost; if
  registrations become abuse, close sign-up and invite from the dashboard —
  a tenant setting, not a code change.
- **Auth0's default sender is for testing** → fine for alpha testers; the README
  says a real sender is a tenant setting before wider use.
- **Google to Production may show a click-through warning** → the doc says to
  try one address first; if the warning is unacceptable, Google testers stay
  listed and only email testers gain — the change still holds.
- **The management key can mint unlimited keys, and the Neon API key can read
  every branch's password** → both live in the operator's shell, are never
  stored beside the app, and `mint` refuses to create a key without a cap.
- **A partial `search` match resolves the wrong branch** → exact-name equality
  on the returned list, exactly one, or a refusal that shows what was found.
- **`limit_reset` may not be accepted on create** → `mint` reads the echo and
  falls back to a `PATCH` once; if the echo still disagrees it revokes and
  refuses. The live check (task 2.9, `network` marker) is what proves this.
- **`email_verified` arrives as a string from some providers** → the check
  accepts exactly the boolean `True` and the string `"true"`, nothing else;
  a test pins both and pins that `"false"`, `1` and absence refuse.

## Migration Plan

1. Land the code with the door unchanged for a deployment whose `[auth]` has no
   sub-table: one button, the Google flow, plus the verified-address check that
   Google always passes.
2. Operator: create the Auth0 application, add `[auth.auth0]` to the deployed
   app's secrets box, add the callback URL at Auth0. The second button appears.
3. Operator: enrol the first non-Google tester with `scinumbers-enrol`.
4. Operator: switch the Google consent screen to Production; sign in from an
   unlisted Google address to see what a tester sees.
5. Rollback: delete `[auth.auth0]` from secrets and the button is gone; the
   verified-address check stays, and is a no-op for Google.

## Open Questions

- Whether Auth0's Universal Login is set to "identifier first" or the classic
  email+password form — a tenant setting that changes nothing here.
- The default cap in dollars for a tester. The command requires the number and
  the README suggests one; deciding it needs the first month's spend.
