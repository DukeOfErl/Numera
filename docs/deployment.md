# Deploying and operating Numera

For whoever runs the hosted app. A deployment is the app on Streamlit Community Cloud, sign-in
through Auth0, a Neon Postgres database for accounts, the trail and reviews, models through
OpenRouter, and optionally Langfuse for tracing; the [README](../README.md#the-platform) has the
picture and the reasons. Running Numera on your own machine needs none of this: see the
[development guide](development.md). Settings are described there too, under
[Configuration](development.md#configuration).

## The durable trail

The trail is the record of every question, its answer, the evidence behind it and any rating.
Locally it goes to a file (`NUMERA_TRACE`). A Streamlit Cloud
container's disk does not survive a redeploy, so the deployment writes it to a
Neon Postgres database instead. `.streamlit/secrets.toml.example` carries the
shape, and the three things a URL copied from a provider's console usually gets
wrong:

```toml
[connections.usage]
url = "postgresql+psycopg://USER:PASSWORD@HOST-pooler.REGION.provider.tech/DB?sslmode=require"
```

The table is created on first use; there is nothing to migrate, and configuring
nothing leaves the app running exactly as before, without a trail.

Recording never blocks a question. If a write fails you are not told and the
conversation carries on — a lost row costs less than a reader stopped by a
telemetry fault, which is the deliberate opposite of the spend limits
([ADR-0710](decisions/0710-recording-fails-open.md)). Conversations
themselves are still ephemeral: the trail outlives a redeploy, the checkpoints
do not.

**What it keeps about you:** your question, the answer, the identifiers of the
entries behind it, a per-question and a per-session identifier, and — where
sign-in is configured — your account and the role it held at the time. It is kept
so a rating can be read beside what that question actually retrieved, and it is
read by whoever operates the deployment. `sql/feedback.sql` query 8 finds
everything kept about one account. Deletion on request, and any retention limit,
are deferred until there are users rather than invited testers
([ADR-0840](decisions/0840-what-a-question-s-trail-keeps.md),
[ADR-0810](decisions/0810-the-role-is-written-at-record-time.md)).

## Hosted tracing (optional)

Each question can be sent to [Langfuse](https://langfuse.com) Cloud as one trace: the model's turns,
every tool call, tokens and timings. It is a debugger for one question, not a record — the trail is
where anything is read back from ([ADR-0750](decisions/0750-feedback-is-recorded-here-not-at-the-tracer.md)).

It is **off unless you say so**: set `NUMERA_TRACING = "langfuse"` and all three Langfuse keys,
as top-level keys in `.streamlit/secrets.toml` (above the first `[section]`) or in the environment.
The keys alone turn nothing on, an unrecognised value leaves it off and says so once, and a
`LANGSMITH_TRACING` left in the environment sends nothing anywhere
([ADR-1010](decisions/1010-tracing-is-a-project-setting.md)).

- **Found by the question.** A trace's id is derived from the question's identifier, so a trail row
  or a rating leads straight to it. Traces are named `ask` and tagged `run:<NUMERA_RUN>`;
  evaluation runs are tagged `eval` as well.
- **Who asked** appears only as a per-account digest keyed with `[auth]`'s `cookie_secret`, so it
  cannot be recomputed from a guessed address, and only where sign-in is configured. The session
  appears only as a digest too, since a session token from the link would open the conversation
  ([ADR-1020](decisions/1020-attribution-is-an-opaque-digest-attached-by-the-driver.md)).
- **Ratings** are copied to the trace as scores (`reader_verdict`, `reader_comment`).
- **What leaves the host when it is on:** prompts, tool results, corpus text, answers, and readers'
  rating comments — free text a reader wrote, which may say anything. Sent to the region the base
  URL names; `https://cloud.langfuse.com` is the EU.
- **The free tier's allowance** is 50,000 units a month, a unit being a trace, a span or a score.
  One question measured 37 units (2026-09-25), so roughly 1,300 questions a month; questions with
  more tool calls cost more. `numera-eval run` shows the month's usage and its own estimate
  before asking anything, and waits for a typed `yes` when more than half is used, when the run
  would not fit, or when either figure cannot be counted. That includes Langfuse being unreachable,
  and the run then cannot proceed unattended. The check is in `run_evaluation`, so any caller of it
  meets the same refusal. The count covers this Langfuse project
  only, which is exact while it is the organisation's only one.
- **A tracer fault never reaches a reader.** An unreachable or refusing Langfuse, including one
  whose allowance has run out, costs the traces and nothing else.

## Sign-in and enrolment

The sign-in page, called *the door* below, is the only thing a visitor sees before being
admitted.

With no `[auth]` section in secrets the app runs as it does locally ([development guide](development.md)): no
sign-in, one `OPENROUTER_API_KEY` from the environment, records carrying no
account, and the side panel saying so. **Add `[auth]` and every visitor must sign
in and be enrolled before anything is drawn.** Signed in but not enrolled is
refused with one sentence and recorded, so the operator can enrol someone who
tried.

**The sign-in door plays a demo** under the button: a question typed out and an
answer streamed back, on a loop. Each is a question actually put to the agent and its
answer (ADR-1210), shortened for the door with every edit recorded beside it
(ADR-1220), in `src/numera_ask/door_demo.json` (ADR-1200). The third shows mouse
cell volumes as a text chart, drawn by `bin/door-demo-chart` rather than by the app,
which cannot plot yet (ADR-1230). Each answer stays up
for 7 s, with the caret blinking, before the next question replaces it; a browser
set to reduced motion shows each example whole.

**The door draws a button for each provider the deployment *offers*,** which is not
necessarily each one it has configured: `web.OFFERED_PROVIDERS` names them, and it
currently names Auth0 alone. The Google client stays configured and every line of the multi-provider
machinery stays with it, because Auth0 signs a reader in with their Google account
anyway — so the second button was two routes to one thing. Restoring it is that
tuple ([ADR-1100](decisions/1100-one-way-in-with-the-others-kept.md)): the
labels follow the button count by themselves, so a lone button says "Sign in" and
two or more say what tells them apart.

**A provider left half-configured is reported rather than silently dropped.** A
sub-table with no `client_id` — a rotation in the secrets box that wrote the secret
and not the id — is invisible to `providers()`, so the door would widen back to the
withdrawn button with nothing said. It still widens, because a door with no button
is never right, but the operator gets a line on stderr naming the section.

**If you withdraw the Google button, enable Auth0's Google connection**, or you have
withdrawn Google sign-in altogether. Auth0 provides one by default using *its own
development keys*, which are rate-limited and show their own consent warning, so put
the Google client you already own into that connection.

**Every door carries the privacy policy**, collapsed — and only the doors:
what is recorded, where it is kept (the database *and* the app's own filesystem),
which services it passes through, how long it is kept, and where to write to see it
or have it deleted. It is under the refusals too — including the session cap, which
turns a reader away *after* recording their sign-in — and it is
readable without signing in, which is what lets the app's own address be the one
Google's consent screen points at
([ADR-1110](decisions/1110-the-privacy-policy-is-the-door-itself.md)).

**Any address can sign in, and only a verified one is admitted.** The provider must
say it has verified the address, and one that says nothing counts as unverified,
because where sign-up is open anyone could otherwise register an enrolled tester's
address and be signed in as them. That refusal has a sentence of its own, separate from "not enrolled",
because the reader's next step is different
([ADR-0890](decisions/0890-only-a-verified-address-opens-the-door.md)).
The address is the identity: a tester who used one provider yesterday and another
today keeps their role and their conversation
([ADR-0880](decisions/0880-a-second-provider-beside-the-first.md)).

Enrolment happens outside the app — there is no page for it, and so no permission
gates it. The operator's steps, in order:

1. **Identity providers.** Keep the Google OAuth client under `[auth]`, and add
   any OpenID Connect provider as a sub-table. For email sign-in this deployment
   uses Auth0.

   **Two choices at tenant creation are permanent, and the defaults are wrong for
   this project** (Auth0's docs, read 2026-09-26: "The tenant name cannot be
   changed after creation", and no procedure is offered for moving a region):

   - **Region: EU.** What the tenant holds is testers' addresses and passwords —
     personal data belonging to European scientists — so keeping it in the EU is
     the simpler position to defend to an institution.
   - **Name: type over the suggested one.** Auth0 offers something like
     `dev-kzi63k4oj51iewcb`. Without a custom domain, Universal Login runs on
     `<tenant>.eu.auth0.com`, so that string is what a reader sees in the address
     bar *while typing a password* — which reads as phishing, and a careful
     person stops. It is also baked into `server_metadata_url` below, so changing
     your mind means a new tenant and a re-paste. Lowercase, digits and hyphens,
     3–63 characters, globally unique.

   Then: **Applications → Applications → Create Application → Regular Web
   Applications**; set **Allowed Callback URLs** to `<your app>/oauth2callback`
   and **Allowed Logout URLs** to **that same `/oauth2callback` URL** — not the
   app's root — under **Settings → Application URIs**; leave the database connection's sign-up open and require
   email verification; and put `client_id`, `client_secret` (both under
   **Settings → Basic Information**) and the tenant's
   `.well-known/openid-configuration` under `[auth.auth0]`.

   **Leave the database connection's sign-ups enabled.** With them disabled you
   create every tester's Auth0 user by hand, which is the third-console step this
   command exists to remove — Auth0's user list simply becomes the Google
   test-user list. Open sign-up is safe here because two refusals already stand in
   front of it: an unverified address is refused (ADR-0890) and an unenrolled one
   is refused and recorded. The cost is noise in the user list, and if bots ever
   make that a problem, disabling sign-ups is a dashboard setting rather than a
   code change.

   **`[auth]` stays, and its own keys must come *before* any sub-table.** This is
   TOML, not Streamlit: after a `[auth.auth0]` header every bare key belongs to
   that sub-table until the next header, so a `redirect_uri` written below it
   becomes `auth.auth0.redirect_uri` and sign-in breaks **for every provider**
   with a message about a missing key. `redirect_uri` and `cookie_secret` are
   shared and required whichever button is clicked, and `[auth]`'s remaining keys
   are the Google client as the unnamed default provider.

   ```toml
   [auth]
   redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
   cookie_secret = "a long random string"
   client_id = "....apps.googleusercontent.com"
   client_secret = "..."
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

   [auth.auth0]
   client_id = "..."
   client_secret = "..."
   server_metadata_url = "https://YOUR-TENANT.eu.auth0.com/.well-known/openid-configuration"
   ```

   **Both allowed-URL lists get the `/oauth2callback` address, including the
   logout one.** Streamlit sends the callback URL as `post_logout_redirect_uri`
   rather than the app's root — "some providers seem to require URL to be in a
   whitelist", says its own comment (`starlette_auth_routes.py`, installed
   1.61.1). An Auth0 tenant that lists only the root answers a sign-out with
   "Oops!, something went wrong" on its own error page, which reads like an outage
   and is a missing allowlist entry.

   **Developing locally, write the port as `{port}`** —
   `http://localhost:{port}/oauth2callback`. Streamlit substitutes `server.port`
   at runtime, so the value cannot drift from the port the app is served on, which
   matters as soon as something else on the machine has taken 8501. Register the
   *concrete* URL at the provider, one per port you use; forgetting
   `--server.port` then produces a callback-mismatch error from the provider
   rather than a silent wrong redirect.

   Order has a second, harmless effect: buttons are drawn in secrets order with
   the default first, so the above gives Google then email.

   **To put another provider above Google, name Google too.** The unnamed default
   is always drawn first, so it cannot be reordered in place — but a provider is
   only "the default" because its credentials sit among `[auth]`'s own keys, and
   moving them into `[auth.google]` makes it an ordinary named provider. `[auth]`
   then holds nothing but the shared settings, and both buttons come from
   sub-tables in the order written:

   ```toml
   [auth]
   redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
   cookie_secret = "a long random string"

   [auth.auth0]
   client_id = "..."
   client_secret = "..."
   server_metadata_url = "https://YOUR-TENANT.eu.auth0.com/.well-known/openid-configuration"

   [auth.google]
   client_id = "....apps.googleusercontent.com"
   client_secret = "..."
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
   ```

   Nothing in the code changes, and the Google button keeps its label. One thing
   to expect: the identity cookie records which provider signed a reader in, so
   anyone signed in through the old unnamed route will be asked to sign in again
   once. Their account, role and conversation are unaffected — the address is the
   identity, not the route to it (ADR-0880).

   A custom domain — login on `login.example.org` rather than
   `<tenant>.eu.auth0.com` — is available at no charge but needs a card on file
   for verification. Not worth doing before there are testers; it is the route if
   the `auth0.com` address becomes a problem.
   `.streamlit/secrets.toml.example` has the shape. Auth0's default mail sender
   is for testing; a real sender is a tenant setting before wider use, and an
   Auth0 Action refusing login until verified is worth setting too — the app
   refuses anyway, but Auth0's own page says it better.
2. **The Google consent screen → Publish app**, so a tester need not be added as
   a test user by hand. In "Testing" the cap is 100 listed addresses and each
   tester's consent expires after seven days. Google's own guidance is ambiguous
   about whether an unverified app in production shows a click-through warning
   for `openid email profile`, so sign in once from an address that is not on the
   test-user list and see what a tester would see before inviting anyone.

   **The Publish button stays greyed out until Branding is complete**, and what
   completes it is the App domain: the home page and the privacy policy. Both are
   the app's own address — the door is a public page and it carries the policy
   ([ADR-1110](decisions/1110-the-privacy-policy-is-the-door-itself.md)), so
   no second host and no extra authorised domain is involved. Set
   `messages.PRIVACY_CONTACT` to the address a reader should write to before
   publishing; it is a public disclosure, not a detail.

   **Do not upload a logo.** With only `openid email profile` the app needs no
   verification at all — but a logo obliges brand verification, which is a review
   with a wait, in exchange for an icon. Every link entered must sit under an
   authorised domain, and Google enforces that on Save, so entering them and
   reading the error is the check.
3. **The `accounts` table** in the same database as the trail, from
   `sql/accounts.sql`.
4. **One command per tester.** `numera-enrol` mints a capped runtime key at
   OpenRouter and inserts the row in one step ([the development guide](development.md#the-commands-and-where-they-live) says how to
   get it on your path; `.venv/bin/numera-enrol` always works):

   ```bash
   OPENROUTER_MANAGEMENT_KEY=... NEON_API_KEY=... NEON_PROJECT_ID=... \
     numera-enrol maria@example.org scientist --limit-usd 5 --branch alpha
   ```

   The three variables are read for that one invocation and the command keeps
   none of them: the management key is created at
   `openrouter.ai/settings/management-keys` and cannot itself ask questions, and
   the Neon API key and project id are how the branch's connection URL is fetched
   rather than written down. Every refusal happens before anything is minted, so
   a rehearsal costs nothing:

   ```bash
   numera-enrol maria@example.org scientist --limit-usd 5
   # -> no branch named. The account has to be acted on in the branch the deployed app reads...
   ```

   To rehearse against a real database without touching the deployment, enrol a
   throwaway address into `dev` with a one-cent cap, then withdraw it.

5. **One command to withdraw one**, taking the same three variables and the same
   required `--branch`:

   ```bash
   numera-withdraw maria@example.org --branch alpha
   ```

   It disables the row and revokes the credential, **in that order**. Either alone
   leaves access open: a refused account can still spend its key, which is held in
   the clear and was given to the person, and a revoked key under an account still
   admitted reads to that person as the app being broken. If the revoke fails, the
   account stays refused and the command names the key so you can revoke it at
   `openrouter.ai/settings/keys`
   ([ADR-1150](decisions/1150-withdrawing-an-account-keeps-the-row.md)).

   **The row is kept, disabled.** The trail rows that account wrote keep their
   attribution, and the table is how you see who once had access.

   **Accounts enrolled before September 2026 have no handle stored**, so they
   withdraw only as far as being refused; the command says so, and their keys come
   off at the dashboard, where each is named after its address. Run
   `sql/accounts.sql` against every branch before the next enrolment — it is
   idempotent and adds the column this depends on.

   **If either credential is refused, the command says which and what to do**,
   rather than passing on `HTTP Error 401`. An expiring key is a reasonable thing
   to have and an unreadable failure is not, so a 401 or 403 from OpenRouter
   names the management key and where to make a new one, and one from Neon names
   `NEON_API_KEY` and `NEON_PROJECT_ID`. Any other status is reported as itself:
   a 502 read as an expired key would send you to replace a key that is fine.
   While the management key is refused, **withdrawing** a tester's credential
   stops working too — it is the same key — so do that from the OpenRouter
   dashboard.

## What enrolment guarantees

`numera-enrol`'s `--branch` names the database branch to enrol into and **has no default**: the
row has to land where the deployed app reads, and a default would be wrong
exactly when the operator is unsure which environment is which. The name is
resolved through Neon's API, so no database URL is kept on disk. Nothing is
issued without a positive cap, an address already enrolled is refused with its
row untouched, and a key minted for a row that could not be written is
withdrawn again
([ADR-0900](decisions/0900-enrolment-mints-then-inserts-and-compensates.md)).
Each tester's questions are then charged to their own key and capped by it; an
enrolled account with no key can sign in and review, but is told no key has been
assigned and so cannot ask. Nobody but the operator ever sees a key — not even in
what the command prints
([ADR-0780](decisions/0780-accounts-live-in-the-trail-database.md),
[ADR-0820](decisions/0820-one-agent-per-session-handed-a-credential-not-an-identity.md)).

## Every secret this deployment needs, and who issues it

**No value in this table belongs in the repository**, and none of them needs
backing up: each is re-obtainable from the service that issued it. What is hard to
reconstruct is *this table* — which secret exists, which console holds it, and
what breaks without it — so it lives here and the values live in a password
manager.

| Secret | Where it lives | Who issues it | Lost or rotated |
| --- | --- | --- | --- |
| `OPENROUTER_API_KEY` | secrets box, top level | openrouter.ai | New key. The one credential a deployment without sign-in uses; unused where every account has its own |
| `[connections.usage]` `url` | secrets box | Neon console, the branch's **Connect** dialog | Fetch it again. Carries the password, so it is never written down anywhere else |
| `[auth]` `cookie_secret` | secrets box | you — any long random string | Any new string. Replacing it signs everyone out and nothing worse |
| `[auth]` Google `client_id` / `client_secret` | secrets box | Google Cloud → APIs & Services → Credentials | Rotate there |
| `[auth.auth0]` `client_id` / `client_secret` | secrets box | Auth0 → Applications → your app → Settings | Rotate there |
| `OPENROUTER_MANAGEMENT_KEY` | the operator's shell only | openrouter.ai/settings/management-keys | New key. Never in the secrets box: the app has no use for it, and it can mint credentials |
| `NEON_API_KEY` | the operator's shell only | Neon → organisation **Settings** → **API keys** | New key. Also never in the secrets box |
| `NEON_PROJECT_ID` | the operator's shell only | Neon → project → **Settings** → **General** | Not a secret; copy it again |
| Each tester's runtime key | the `accounts` table | minted by `numera-enrol` | **Already stored** — that column is the source of truth, not a copy. Revoke at OpenRouter and re-enrol |

Two consequences worth stating. A **local** `.streamlit/secrets.toml` is not a
backup of the deployed one: it must carry the branch *this checkout* writes to, so
copying the deployment's values into it — even commented out — is the spare
credential the file's own rule forbids, and the line someone uncomments by
accident. And the last row means losing the accounts table costs every tester's
credential at once; Neon's point-in-time restore covers it, and re-enrolling is
the fallback.

## Where to keep the operator's credentials

Not on the command line, once you are doing this more than once: every
invocation lands in your shell history, which is the one place a secret is
easiest to forget about.

Not exported from `~/.bashrc` either. The management key can mint unlimited
runtime keys, and putting it in every shell's environment means every process
you ever run — other projects, other tools, anything that dumps its environment
on a crash — is holding it.

**A file outside the repository, loaded when you want it.** Present in the one
shell that asked for it, and nowhere else:

```bash
mkdir -p ~/.config/numera
chmod 700 ~/.config/numera
touch ~/.config/numera/enrol.env
chmod 600 ~/.config/numera/enrol.env      # before anything secret is in it
nano ~/.config/numera/enrol.env           # or your editor
```

Three lines, no quotes and no `export`:

```
OPENROUTER_MANAGEMENT_KEY=sk-or-...
NEON_API_KEY=napi_...
NEON_PROJECT_ID=your-project-id
```

Outside the repository rather than gitignored inside it: three checkouts of this
project share one origin, git history is permanent, and a `.gitignore` is one
`git add -f` or one careless `git clean` away from not helping.

Where each comes from (Neon's console, read 2026-09-26):

| Value | Where |
| --- | --- |
| `OPENROUTER_MANAGEMENT_KEY` | `openrouter.ai/settings/management-keys`. It mints runtime keys and cannot itself call a model. An expiry is optional and supported |
| `NEON_API_KEY` | **Prefer an organisation key** if the project belongs to an organisation: the organisation → **Settings** → **API keys**. It scopes every request to that organisation, so no `org_id` is needed anywhere. A *personal* key (profile menu → **Settings** → **API keys**, prefix `napi_`) requires `org_id` on the list-projects call and refuses with `400 org_id is required` without it. Either kind is **shown once**, and the console offers no expiry — they last until revoked |
| `NEON_PROJECT_ID` | The project → **Settings** → **General**, with a copy button. Two words and digits, like `sparkling-bread-74230014` — **not** the `ep-…` form Neon's own docs give as an example, which is an endpoint id |

Check both before you need them, which also tells you the exact branch name to
pass to `--branch`. **Load the file in this shell first**, and let the shell say
so if you have not:

```bash
set -a; source ~/.config/numera/enrol.env; set +a
: "${NEON_API_KEY:?not set — source ~/.config/numera/enrol.env first}"
: "${NEON_PROJECT_ID:?not set — source ~/.config/numera/enrol.env first}"

curl -sS -w '\nHTTP %{http_code}\n' https://console.neon.tech/api/v2/projects \
  -H "Authorization: Bearer $NEON_API_KEY"

curl -sS -w '\nHTTP %{http_code}\n' \
  "https://console.neon.tech/api/v2/projects/$NEON_PROJECT_ID/branches" \
  -H "Authorization: Bearer $NEON_API_KEY"
```

To check the connection-URL call as well, **discard the body**: its response
carries the branch's password, and a check that prints it has put a live
credential into your scrollback and your terminal's history to verify a number.

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  "https://console.neon.tech/api/v2/projects/$NEON_PROJECT_ID/connection_uri\
?branch_id=BRANCH_ID&database_name=neondb&role_name=neondb_owner&pooled=true" \
  -H "Authorization: Bearer $NEON_API_KEY"
```

`200` means the `--database` and `--role-name` defaults suit the project and
neither flag is needed.

`HTTP 401` from the first call means the key; from the second, the project id.
The command cannot make that distinction from inside — an expired key and a key
that cannot see the project are refused identically — so its message names both.

Then, in the shell where you are enrolling someone:

```bash
set -a; source ~/.config/numera/enrol.env; set +a
numera-enrol maria@example.org scientist --limit-usd 5 --branch alpha
```

**The command itself reads nothing but the environment**, deliberately, and that
is not an oversight to fix by teaching it about this file. How the environment
gets populated is yours to choose — a file, a password manager, `pass`, a
one-off paste — and the command has one input either way. It is the same
reasoning that keeps it from reading `.streamlit/secrets.toml`, whose single URL
is the branch *this checkout* writes to.

## Readers who never receive their confirmation email

**A reader who never receives their confirmation email can say so**, and that
request lands in the trail rather than sending anything: resending through the
identity provider needs a credential that could also create accounts, which is more
power than one message is worth. `sql/signin.sql` holds the three queries that
surface them — who asked, who gave up without asking, and who is verified and
waiting to be enrolled.

## Checking daily who is stuck

`numera-pending` reads those first and third queries and **prints nothing when
nothing is waiting**, which is what makes it usable from `cron`: mail arrives only
on the days something happened. A monitor that reports "0 pending" every morning is
one whose output stops being read, and then the morning it says 1 goes unread too.

```bash
numera-pending --branch alpha              # silent unless somebody is still stuck
numera-pending --branch alpha --hours 168  # only the last week
```

Daily, from the operator's own crontab (`crontab -e`):

```cron
0 9 * * * bash -lc 'set -a; . "$HOME/.config/numera/enrol.env"; set +a;   "$HOME/AI Engineering/Numera/.venv/bin/numera-pending" --branch alpha'
```

**It reports only what is still stuck.** A problem that resolved itself stops
appearing, and no state is kept to achieve that — the trail already says who got
through. A session records `signin.admitted` on arrival, stamped with the account
like every other record, so admission is observable; and an address later seen as
`signin.refused` got past *verification*, because that door sits behind the
verified check. So "never got the email" clears on any later sign of verification,
and "verified but not enrolled" clears on a later admitted session.

**Enrolment is read from the accounts table, not inferred.** A review caught the
first version asking the trail whether somebody had signed in again — which a tester
who was enrolled and never came back never does, and which an enrolled account with
*no credential* cannot do at all, because that door stops the page before anything
is recorded. So the enrolment queue asks the authority: an address with no enabled
row. A withdrawn account counts as not enrolled, exactly as it does at the door.

Anything unresolved keeps being reported until it is fixed, which is what makes the
daily mail worth opening: the list is the work, and it empties as the work is done.
`--hours` bounds how far back to look, thirty days by default, so an address
abandoned months ago ages out instead of nagging forever; a span that could match
nothing is refused rather than answered with silence.

It reads the trail and the accounts table and touches no provider, so give the cron
line **only the two Neon variables**. It needs nothing else, and a management key in
a scheduled job's environment is a credential that can mint keys sitting in a process
that only reads.

On WSL, `cron` is not running by default (`sudo service cron start`, and see your
distribution's notes on starting it at boot). Without it, run the command by hand;
it costs one line and two seconds.

## Keeping the deployed app awake

Streamlit Community Cloud hibernates an app after
12 hours without a visitor, and the first reader afterwards waits through a cold
start. `.github/workflows/keepalive.yml` runs hourly and `bin/keepalive.py` visits the
app in a headless browser, clicks the sleep screen's button if it is showing, and
fails unless the door renders. A failed run would mail once an hour, so
`keepalive-digest.yml` is the notice instead: once a day it comments on one standing
issue, "scheduled workflow problems", if any run failed or none ran at all (GitHub pauses
scheduled workflows after 60 days without repository activity). Switch GitHub's own
failure mail off under Settings > Notifications > Actions, or both will reach you.
It needs no secrets. GitHub runs scheduled workflows from the default branch only, which is `main`.

## Hearing when a reader first arrives

`numera-first-use` reports each reader the first time they are seen signing in and the first
time they ask a question — one line per reader, with both firsts together when they fall in the
same window — and, like `numera-pending`, **prints nothing when nobody is new**
([ADR-1250](decisions/1250-first-use-notice-is-a-stateless-window.md)). It keeps no state:
"first" is read out of the trail (an event in the window and none earlier for that address), so the
window has to be right. GitHub runs this "hourly" schedule every 4-7 hours, so the workflow looks
back to when the **previous successful run** began, plus six minutes
([ADR-1290](decisions/1290-the-first-use-window-follows-the-schedule.md)): nobody falls in a
gap, and only the overlap repeats. By hand, `--minutes` sets it, defaulting to seven hours.

It is scheduled hourly in the **private repository `DukeOfErl/numera-ops`** (`first-use.yml` there),
not in this one: this repository is public, and the job names readers
([ADR-2050](decisions/2050-the-first-use-alert-runs-in-a-private-repository.md)). It checks
this repository's code out and comments on one standing issue there, `first use`, which mails the
owner through GitHub — no mail account. Every comment begins with an `@` mention of
the repository owner, because the Actions bot opens the issue and so the owner would not otherwise be
"participating" in it. It holds **one secret, the URL of a role that
can read three columns of the trail and nothing else**, never the Neon API key
([ADR-1260](decisions/1260-the-scheduled-job-holds-a-read-only-role.md)). Setting it up, once:

1. On the Neon branch the deployment writes to (`alpha`), run `sql/first_use_reader.sql` after
   replacing the token `<PASSWORD>` with a real password in single quotes (left unedited it is
   a syntax error, on purpose). Roles are per branch.
2. In `DukeOfErl/numera-ops`, add the secrets `NUMERA_TRAIL_READ_URL` (that role's URL,
   `postgresql+psycopg://…`) and `FIRST_USE_EXCLUDE` (your own and test addresses,
   comma-separated; a secret, and the job masks each address in it before using it, since
   Actions masks only a secret's whole value).
3. Enable the workflow in `numera-ops`, run it by hand with **`test`** ticked, and check that the
   mail arrives
   ([ADR-1270](decisions/1270-first-use-reaches-the-operator-through-a-standing-issue.md)).

By hand: `NUMERA_TRAIL_READ_URL=… numera-first-use --minutes 1440 --exclude me@example.org`.
`numera-ops` has its own daily digest, so a run that fails or never happens reaches you once a day.

**A quiet week is told apart from a broken check.** After seven days with nothing delivered to you
— a report, a `test` line or an earlier message of this kind all count — the workflow posts one
comment saying the check *found* no new readers in that time, when it ran, and how many checks
completed. It reports an observation and does not claim nobody exists; if you expected someone, the
check may be what is wrong
([ADR-1350](decisions/1350-a-quiet-week-sends-one-message.md)). With no standing issue yet there
is nothing to count from, so none is sent until the first post creates it. A comment you write on the
issue also restarts the week.

**Reader addresses go into that issue comment, in the private `numera-ops`**, never into this
repository's issues or logs
([ADR-2050](decisions/2050-the-first-use-alert-runs-in-a-private-repository.md), superseding
[ADR-1280](decisions/1280-reader-addresses-appear-in-an-issue-so-the-repository-stays-private.md));
the report is written to a file, never to the run's log, and the exclusion list is a secret there.
`tests/test_scheduled_workflows.py` fails if a workflow here ever reads the trail again.

## Roles, sessions and spend

**Five roles exist — student, scientist, senior scientist, dev and admin — as
foundations, built and tested now so that ratings can later be weighted by who
gave them.** Today they differ in one visible thing: dev and admin get an extra
**Dev** section in the side panel, showing this session's recent trail. Permissions
are a default-deny table, and nothing about a role reaches the agent, so an
answer cannot depend on who asked
([ADR-0800](decisions/0800-default-deny-and-the-pruning-rule.md)).

A deployment also holds at most `NUMERA_MAX_SESSIONS` sessions open at once;
the next visitor is told to try again shortly, and no open session is ended to
make room ([ADR-0790](decisions/0790-the-session-cap-is-a-heartbeat-registry.md)).

**With sign-in configured, your conversation follows your account** rather than
the `?session=` link — so opening the app again, on any tab, continues where you
were, and a link you hand to someone else starts them in their own session
instead of joining yours
([ADR-0830](decisions/0830-the-session-is-keyed-on-the-account-not-the-link.md)).
Without sign-in the link is still the session, so a developer's bookmark behaves
exactly as it always has.

Spend is enforced, not merely reported: a question stops at its ceiling and presents what it had
established, marked incomplete, rather than being cut off mid-sentence. A limit is configured where
it binds — the number you set is the one that stops work
([ADR-0180](decisions/0180-limits-named-where-they-bind.md)).
