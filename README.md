# SciNumbers ask

**How long is an E. coli cell? How many ribosomes does it carry?** Quantitative biology runs on
numbers like these, and the usual way to get one out of a language model is to ask and hope. A
plausible number arrives with no way to tell whether it was recalled, interpolated, or invented.

This agent answers only from a corpus you supply, and cites the entry behind every number it
reports. Where the corpus does not cover a question, it says so rather than answering from the
model's own knowledge. It is for people who need a figure they can defend.

Three commitments shape the design:

- **Provenance.** Every figure carries the identifier of the entry it came from, written `[[100002]]`
  so a citation can never be confused with a quantity, and those entries
  are shown beside the answer. A number the answer used but the corpus never returned is flagged as
  unsupported rather than quietly printed.
- **Precision.** Units are compared by dimension, so a length is never silently reconciled with a
  volume. Entries with no measurement method, no scalar value, or a value the source only bounded
  or approximated are marked — half the corpus has no method, and an answer should not hide that.
- **Reliability.** Spend is capped per question and per run, conversations are bounded by their
  token count, and every question ends with a stated reason and what it consumed. No tool can
  create, modify or delete an entry.

> **A prototype, not an instrument.** More careful than a general-purpose model, but
> not yet scientifically trustworthy: verify every number against the original source
> before relying on it. What has been measured is retrieval, not truth — see the
> evaluation below.

## How it works

The agent is a LangGraph loop with the corpus behind three tools. Its graph, generated from the
compiled object rather than drawn:

```mermaid
graph TD;
	__start__([__start__]):::first
	model(model)
	tools(tools)
	limit_before(ModelCallLimitMiddleware.before_model)
	limit_after(ModelCallLimitMiddleware.after_model)
	spend_after(SpendGate.after_model)
	__end__([__end__]):::last
	limit_after -.-> limit_before;
	limit_after -.-> __end__;
	limit_after -.-> tools;
	limit_before -.-> __end__;
	limit_before -.-> model;
	spend_after --> limit_after;
	__start__ --> limit_before;
	model --> spend_after;
	tools -.-> limit_before;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Most of the behaviour is invisible here: only `before_model`/`after_model` hooks become nodes, so
the retry, tool-error and spend middleware are wrappers around `model` and `tools` rather than
boxes. **[`docs/diagrams/architecture.md`](docs/diagrams/architecture.md)** has the middleware table
that lists them in nesting order, a sequence diagram of what happens during one question, and the
module dependency graph.

The agent is separated from the interfaces that drive it (ports and adapters): it emits events and
accepts questions, so the web page and — later — an evaluation harness are adapters over one agent,
with no mode flag inside it.

### Rating an answer

Each answer carries a thumbs up or down, at the foot of its prose and beside the entries it rests on.
**Rating is optional** — an answer nobody rates behaves exactly as it does today — and it is recorded
the moment it is clicked, because most people who rate do nothing else. A rating is final once given.

A thumbs **down** opens a comment box; approval does not, since the box asks what was wrong. The hint
asks you to name the identifier of any entry you think is wrong: rating individual table rows is not
built, and what people write about entries is the evidence for whether it should be.

**Comments are read by whoever runs the deployment, and are never sent to the model** — not to the
conversation, not to a prompt, not to the state a later question is answered from. A comment is the
one input to this system written to be read by the people running it, and a tool whose wrong answers
look like its right ones must not take instructions by that route.

Ratings are written to the durable trail below, under the same identifier as the question they judge,
so a judgement can be read beside what that question actually retrieved. If the write fails you are
not told and the conversation is not interrupted: the cost of a lost row is one row.

## Running it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

**1. Install.**

```bash
uv sync --extra ask --extra ingest
export OPENROUTER_API_KEY=...                  # the model is reached through OpenRouter
```

**2. Get the corpus.** Go to <https://bionumbers.hms.harvard.edu/resources.aspx> and click
**Download the BioNumbers database**. Put the resulting `BioNumbers.xls` in a directory **outside
this repository** — the data's licensing is unresolved, so nothing derived from it may enter a git
repository, and the build refuses to write anywhere git would track it.

**3. Start the app.** Point `SCINUMBERS_CORPUS` at where the corpus should go. Finding none
there and the export beside it, the app says what it is about to do and builds one — about a minute,
once.

```bash
export SCINUMBERS_CORPUS=~/bionumbers/bionumbers.jsonl   # BioNumbers.xls is in that directory
uv run streamlit run streamlit_app.py
```

Then ask something. `What is the minimal inhibitory concentration of kanamycin for E. coli?` is a
good first question: the source says `<8`, and the answer says so rather than reporting 8 as a
measurement.

### The commands, and where they live

`uv sync` installs the console scripts into the project's virtualenv, not onto
your `PATH`:

| Command | What it does |
| --- | --- |
| `scinumbers-ask` | the terminal driver: ask a question, see the entries behind the answer |
| `scinumbers-enrol` | enrol one tester: mint a capped credential and record the account |
| `scinumbers-eval` | the evaluation harness: `check`, `run`, `report` |
| `bionumbers-ingest` | build a corpus from the published export |
| `bionumbers` | **declared, not yet built.** The grounding validator's entry point, for a package this repository does not contain — running it raises `ModuleNotFoundError`. Left in place because the name belongs to that work package; see `docs/roadmap.md` |

A bare `scinumbers-enrol` is `command not found` until the virtualenv is on your
path. Three ways, in increasing permanence:

```bash
.venv/bin/scinumbers-enrol --help        # no setup; works from the repository root

source .venv/bin/activate                # this shell only, then bare names work
scinumbers-enrol --help

ln -sf "$PWD/.venv/bin/scinumbers-enrol" ~/.local/bin/   # permanent, one command
```

The symlink is the one to prefer for `scinumbers-enrol`, because enrolling a
tester is something you do from wherever you happen to be rather than from this
directory. `~/.local/bin` is on the default path on most systems; `echo $PATH`
will say. **Do not put `.venv/bin` itself on your `PATH`** — it would shadow
`python` and `pip` everywhere, for every project.

Every example below uses the bare name. Prefix `.venv/bin/` if you have not done
one of the above.

## Configuration

| Variable | Default | What it does |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | required; a question ends as `not_configured` without it |
| `SCINUMBERS_CORPUS` | — | required; path to the JSONL corpus |
| `SCINUMBERS_MODEL` | `anthropic/claude-opus-4.7` | the model, as an OpenRouter slug |
| `SCINUMBERS_QUESTION_CEILING_USD` | `0.60` | hard per-question limit; the warning is derived at 80% of it |
| `SCINUMBERS_RUN_BUDGET_USD` | `1.20` | total across every question in a run; where sign-in is configured, per account rather than shared |
| `SCINUMBERS_RUN` | `dev` | names the run spend is counted against; a new name starts a fresh budget |
| `SCINUMBERS_CHECKPOINTS` | `checkpoints/ask.sqlite` | where sessions persist |
| `SCINUMBERS_TRACE` | `logs/trace.jsonl` | the structured trail; `-` for stderr, empty to discard |
| `SCINUMBERS_MAX_SESSIONS` | `20` | how many browser sessions the deployment holds open at once; the next is told to try later |
| `SCINUMBERS_SESSION_IDLE_S` | `600` | how long a quiet session keeps its place before it is freed |
| `SCINUMBERS_TRACING` | off | `langfuse` turns hosted tracing on, and nothing else does; see below |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | — | all three required when tracing is on; the base URL names the region |

Every variable above is read from the process environment. A hosted deployment has
no shell to export one from, so **put it in the app's Secrets box as a top-level
key** — Streamlit promotes every top-level string, int or float in secrets to an
environment variable at server start, before the script runs (verified against the
installed Streamlit 1.61.1: `runtime/secrets.py`, `_maybe_set_environment_variable`,
called from `web/bootstrap.py`). The `[auth]` and `[connections.usage]` *sections*
below are the exception: a table is not promoted, and is read as `st.secrets`.

```toml
OPENROUTER_API_KEY = "sk-or-..."
SCINUMBERS_MODEL = "anthropic/claude-opus-4.7"
SCINUMBERS_RUN_BUDGET_USD = "1.20"
```

### The durable trail (hosted deployments only)

Locally the trail goes to a file (`SCINUMBERS_TRACE`). A Streamlit Cloud
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
([ADR-0710](docs/decisions/0710-recording-fails-open.md)). Conversations
themselves are still ephemeral: the trail outlives a redeploy, the checkpoints
do not.

**What it keeps about you:** your question, the answer, the identifiers of the
entries behind it, a per-question and a per-session identifier, and — where
sign-in is configured — your account and the role it held at the time. It is kept
so a rating can be read beside what that question actually retrieved, and it is
read by whoever operates the deployment. `sql/feedback.sql` query 8 finds
everything kept about one account. Deletion on request, and any retention limit,
are deferred until there are users rather than invited testers
([ADR-0840](docs/decisions/0840-what-a-question-s-trail-keeps.md),
[ADR-0810](docs/decisions/0810-the-role-is-written-at-record-time.md)).

### Hosted tracing (optional)

Each question can be sent to [Langfuse](https://langfuse.com) Cloud as one trace: the model's turns,
every tool call, tokens and timings. It is a debugger for one question, not a record — the trail is
where anything is read back from ([ADR-0750](docs/decisions/0750-feedback-is-recorded-here-not-at-the-tracer.md)).

It is **off unless you say so**: set `SCINUMBERS_TRACING = "langfuse"` and all three Langfuse keys,
as top-level keys in `.streamlit/secrets.toml` (above the first `[section]`) or in the environment.
The keys alone turn nothing on, an unrecognised value leaves it off and says so once, and a
`LANGSMITH_TRACING` left in the environment sends nothing anywhere
([ADR-1010](docs/decisions/1010-tracing-is-a-project-setting.md)).

- **Found by the question.** A trace's id is derived from the question's identifier, so a trail row
  or a rating leads straight to it. Traces are named `ask` and tagged `run:<SCINUMBERS_RUN>`;
  evaluation runs are tagged `eval` as well.
- **Who asked** appears only as a per-account digest keyed with `[auth]`'s `cookie_secret`, so it
  cannot be recomputed from a guessed address, and only where sign-in is configured. The session
  appears only as a digest too, since a session token from the link would open the conversation
  ([ADR-1020](docs/decisions/1020-attribution-is-an-opaque-digest-attached-by-the-driver.md)).
- **Ratings** are copied to the trace as scores (`reader_verdict`, `reader_comment`).
- **What leaves the host when it is on:** prompts, tool results, corpus text, answers, and readers'
  rating comments — free text a reader wrote, which may say anything. Sent to the region the base
  URL names; `https://cloud.langfuse.com` is the EU.
- **The free tier's allowance** is 50,000 units a month, a unit being a trace, a span or a score.
  One question measured 37 units (2026-09-25), so roughly 1,300 questions a month; questions with
  more tool calls cost more. `scinumbers-eval run` shows the month's usage and its own estimate
  before asking anything, and waits for a typed `yes` when more than half is used, when the run
  would not fit, or when either figure cannot be counted. That includes Langfuse being unreachable,
  and the run then cannot proceed unattended. The check is in `run_evaluation`, so any caller of it
  meets the same refusal. The count covers this Langfuse project
  only, which is exact while it is the organisation's only one.
- **A tracer fault never reaches a reader.** An unreachable or refusing Langfuse, including one
  whose allowance has run out, costs the traces and nothing else.

### Sign-in and enrolment (hosted deployments only)

With no `[auth]` section in secrets the app runs exactly as described above: no
sign-in, one `OPENROUTER_API_KEY` from the environment, records carrying no
account, and the side panel saying so. **Add `[auth]` and every visitor must sign
in and be enrolled before anything is drawn.** Signed in but not enrolled is
refused with one sentence and recorded, so the operator can enrol someone who
tried.

**The door draws a button for each provider the deployment *offers*,** which is not
necessarily each one it has configured: `web.OFFERED_PROVIDERS` names them, and it
currently names Auth0 alone. The Google client stays configured and every line of the multi-provider
machinery stays with it, because Auth0 signs a reader in with their Google account
anyway — so the second button was two routes to one thing. Restoring it is that
tuple ([ADR-1100](docs/decisions/1100-one-way-in-with-the-others-kept.md)).

**If you withdraw the Google button, enable Auth0's Google connection**, or you have
withdrawn Google sign-in altogether. Auth0 provides one by default using *its own
development keys*, which are rate-limited and show their own consent warning, so put
the Google client you already own into that connection.

**Every door carries the privacy policy**, collapsed, and so does the side panel:
what is recorded, what it is used for, which services it passes through, how long it
is kept, and where to write to see it or have it deleted. It is under the refusals
too — an attempt records an address whether or not it is admitted — and it is
readable without signing in, which is what lets the app's own address be the one
Google's consent screen points at
([ADR-1110](docs/decisions/1110-the-privacy-policy-is-the-door-itself.md)).

**Any address can sign in, and only a verified one is admitted.** The provider must
say it has verified the address, and one that says nothing counts as unverified,
because where sign-up is open anyone could otherwise register an enrolled tester's
address and be signed in as them. That refusal has a sentence of its own, separate from "not enrolled",
because the reader's next step is different
([ADR-0890](docs/decisions/0890-only-a-verified-address-opens-the-door.md)).
The address is the identity: a tester who used one provider yesterday and another
today keeps their role and their conversation
([ADR-0880](docs/decisions/0880-a-second-provider-beside-the-first.md)).

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
   ([ADR-1110](docs/decisions/1110-the-privacy-policy-is-the-door-itself.md)), so
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
4. **One command per tester.** `scinumbers-enrol` mints a capped runtime key at
   OpenRouter and inserts the row in one step (§"The commands, and where they live" says how to
   get it on your path; `.venv/bin/scinumbers-enrol` always works):

   ```bash
   OPENROUTER_MANAGEMENT_KEY=... NEON_API_KEY=... NEON_PROJECT_ID=... \
     scinumbers-enrol maria@example.org scientist --limit-usd 5 --branch alpha
   ```

   The three variables are read for that one invocation and the command keeps
   none of them: the management key is created at
   `openrouter.ai/settings/management-keys` and cannot itself ask questions, and
   the Neon API key and project id are how the branch's connection URL is fetched
   rather than written down. Every refusal happens before anything is minted, so
   a rehearsal costs nothing:

   ```bash
   scinumbers-enrol maria@example.org scientist --limit-usd 5
   # -> no branch named. The row has to land in the branch the deployed app reads...
   ```

   To rehearse against a real database without touching the deployment, enrol a
   throwaway address into `dev` with a one-cent cap, then delete the row and
   revoke the key.

   **If either credential is refused, the command says which and what to do**,
   rather than passing on `HTTP Error 401`. An expiring key is a reasonable thing
   to have and an unreadable failure is not, so a 401 or 403 from OpenRouter
   names the management key and where to make a new one, and one from Neon names
   `NEON_API_KEY` and `NEON_PROJECT_ID`. Any other status is reported as itself:
   a 502 read as an expired key would send you to replace a key that is fine.
   While the management key is refused, **withdrawing** a tester's credential
   stops working too — it is the same key — so do that from the OpenRouter
   dashboard.

#### Every secret this deployment needs, and who issues it

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
| Each tester's runtime key | the `accounts` table | minted by `scinumbers-enrol` | **Already stored** — that column is the source of truth, not a copy. Revoke at OpenRouter and re-enrol |

Two consequences worth stating. A **local** `.streamlit/secrets.toml` is not a
backup of the deployed one: it must carry the branch *this checkout* writes to, so
copying the deployment's values into it — even commented out — is the spare
credential the file's own rule forbids, and the line someone uncomments by
accident. And the last row means losing the accounts table costs every tester's
credential at once; Neon's point-in-time restore covers it, and re-enrolling is
the fallback.

#### Where to keep the operator's credentials

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
mkdir -p ~/.config/scinumbers
chmod 700 ~/.config/scinumbers
touch ~/.config/scinumbers/enrol.env
chmod 600 ~/.config/scinumbers/enrol.env      # before anything secret is in it
nano ~/.config/scinumbers/enrol.env           # or your editor
```

Three lines, no quotes and no `export`:

```
OPENROUTER_MANAGEMENT_KEY=sk-or-...
NEON_API_KEY=napi_...
NEON_PROJECT_ID=your-project-id
```

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
set -a; source ~/.config/scinumbers/enrol.env; set +a
: "${NEON_API_KEY:?not set — source ~/.config/scinumbers/enrol.env first}"
: "${NEON_PROJECT_ID:?not set — source ~/.config/scinumbers/enrol.env first}"

curl -sS -w '\nHTTP %{http_code}\n' https://console.neon.tech/api/v2/projects \
  -H "Authorization: Bearer $NEON_API_KEY"

curl -sS -w '\nHTTP %{http_code}\n' \
  "https://console.neon.tech/api/v2/projects/$NEON_PROJECT_ID/branches" \
  -H "Authorization: Bearer $NEON_API_KEY"
```

The status code is printed on purpose, and there is no `grep`. A pipeline that
filters for the field you want prints **nothing at all** when the call was
refused — the same empty output as a project with no branches — which is a check
that cannot tell you it failed. Read the status, then filter once you are getting
`HTTP 200`.

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

Verified against the live API on 2026-09-26: a wrong key, well formed or not,
gives `401`; an **empty** `Authorization` header gives `400 not authenticated`,
which is why the command refuses on an unset variable before it calls anything.
An organisation key lists projects with no `org_id` and returns `200`; a personal
key without one returns `400 org_id is required`, which is a different failure
wearing the same status code — read the message, not the number.

Then, in the shell where you are enrolling someone:

```bash
set -a; source ~/.config/scinumbers/enrol.env; set +a
scinumbers-enrol maria@example.org scientist --limit-usd 5 --branch alpha
```

**Write it with an editor rather than a heredoc.** Bash keeps a multi-line
command as a single history entry, so `cat > file <<'EOF'` puts the keys into
`~/.bash_history` — the one thing this file exists to avoid, arrived at by the
convenient route. An editor writes nothing to history; `cat > file` followed by
typing the lines and pressing Ctrl-D is fine too, because stdin is not history.
`chmod` comes **before** the content, so the file is never briefly world-readable
with a key already in it.

Outside the repository rather than gitignored inside it: three checkouts of this
project share one origin, git history is permanent, and a `.gitignore` is one
`git add -f` or one careless `git clean` away from not helping.

**The command itself reads nothing but the environment**, deliberately, and that
is not an oversight to fix by teaching it about this file. How the environment
gets populated is yours to choose — a file, a password manager, `pass`, a
one-off paste — and the command has one input either way. It is the same
reasoning that keeps it from reading `.streamlit/secrets.toml`, whose single URL
is the branch *this checkout* writes to.

   `--branch` names the database branch to enrol into and **has no default**: the
   row has to land where the deployed app reads, and a default would be wrong
   exactly when the operator is unsure which environment is which. The name is
   resolved through Neon's API, so no database URL is kept on disk. Nothing is
   issued without a positive cap, an address already enrolled is refused with its
   row untouched, and a key minted for a row that could not be written is
   withdrawn again
   ([ADR-0900](docs/decisions/0900-enrolment-mints-then-inserts-and-compensates.md)).
   Each tester's questions are then charged to their own key and capped by it; an
   enrolled account with no key can sign in but is told no credential has been
   issued. Nobody but the operator ever sees a key — not even in what the command
   prints
   ([ADR-0780](docs/decisions/0780-accounts-live-in-the-trail-database.md),
   [ADR-0820](docs/decisions/0820-one-agent-per-session-handed-a-credential-not-an-identity.md)).

**A reader who never receives their confirmation email can say so**, and that
request lands in the trail rather than sending anything: resending through the
identity provider needs a credential that could also create accounts, which is more
power than one message is worth. `sql/signin.sql` holds the three queries that
surface them — who asked, who gave up without asking, and who is verified and
waiting to be enrolled.

#### Checking daily who is stuck

`scinumbers-pending` reads those first and third queries and **prints nothing when
nothing is waiting**, which is what makes it usable from `cron`: mail arrives only
on the days something happened. A monitor that reports "0 pending" every morning is
one whose output stops being read, and then the morning it says 1 goes unread too.

```bash
scinumbers-pending --branch alpha              # silent unless somebody is still stuck
scinumbers-pending --branch alpha --hours 168  # only the last week
```

Daily, from the operator's own crontab (`crontab -e`):

```cron
0 9 * * * bash -lc 'set -a; . "$HOME/.config/scinumbers/enrol.env"; set +a;   "$HOME/AI Engineering/BioNumbers/.venv/bin/scinumbers-pending" --branch alpha'
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

**Five roles exist — student, scientist, senior scientist, dev and admin — as
foundations, built and tested now so that ratings can later be weighted by who
gave them.** Today they differ in one visible thing: dev and admin get an extra
**Dev** tab in the side panel, showing this session's recent trail. Permissions
are a default-deny table, and nothing about a role reaches the agent, so an
answer cannot depend on who asked
([ADR-0800](docs/decisions/0800-default-deny-and-the-pruning-rule.md)).

A deployment also holds at most `SCINUMBERS_MAX_SESSIONS` sessions open at once;
the next visitor is told to try again shortly, and no open session is ended to
make room ([ADR-0790](docs/decisions/0790-the-session-cap-is-a-heartbeat-registry.md)).

**With sign-in configured, your conversation follows your account** rather than
the `?session=` link — so opening the app again, on any tab, continues where you
were, and a link you hand to someone else starts them in their own session
instead of joining yours
([ADR-0830](docs/decisions/0830-the-session-is-keyed-on-the-account-not-the-link.md)).
Without sign-in the link is still the session, so a developer's bookmark behaves
exactly as it always has.

Spend is enforced, not merely reported: a question stops at its ceiling and presents what it had
established, marked incomplete, rather than being cut off mid-sentence. A limit is configured where
it binds — the number you set is the one that stops work
([ADR-0180](docs/decisions/0180-limits-named-where-they-bind.md)).

## Hosted deployment: what the deploy branch adds

**`deploy/streamlit-cloud` is never merged back.** It carries three changes `main` must
not have.

**Update it by merging `main` into it — do not rebase.** This branch has a second
writer: Streamlit Cloud's Codespaces integration pushes here (it added
`.devcontainer/`), and Cloud watches the ref. Rebasing means force-pushing, and a
force-push discards whatever arrived from the other side; `--force-with-lease` refused
exactly that once, which is the only reason the dev-container commit survived. The
instruction here used to say "rebase", written before anything else could write to it.

1. **The `ask` extra's packages are `[project].dependencies`.** Community Cloud picks
   a dependency file by precedence — `uv.lock` first — and runs `uv sync`, which does
   not install extras, and neither the platform nor `pyproject` can ask it to
   ([astral-sh/uv#16380](https://github.com/astral-sh/uv/issues/16380) is open). A
   deploy from `main` would start without Streamlit installed. The ingester stays an
   extra: the corpus arrives prebuilt, and `autobuild` degrades correctly without it.
2. **Secrets are copied into the environment** at the top of `streamlit_app.py`.
   Root-level secrets do become environment variables, but on first access, and the
   agent reads `os.environ` deep inside itself.
3. **The corpus is fetched into the container** by `scinumbers_ask/hosted.py` when
   `CORPUS_URL` is set, verified against `CORPUS_SHA256`, and renamed into place only
   once whole. A truncated download is valid JSONL that answers plausibly from
   whatever arrived, so an unverified corpus is refused — including when no digest is
   configured at all.

### Configuration this branch adds

| Secret | What it is |
| --- | --- |
| `CORPUS_URL` | the release asset's **API** URL: `https://api.github.com/repos/OWNER/REPO/releases/assets/<id>`. `browser_download_url` needs a session, not a token. |
| `CORPUS_TOKEN` | a fine-grained token, **Contents: Read-only on that one repository**, nothing else |
| `CORPUS_SHA256` | `sha256sum` of the corpus. Without it the app refuses to start rather than serving an unverified copy. |

Check the URL and token from a terminal before pasting them into the app's secrets:

```bash
curl -L -H "Authorization: Bearer $TOKEN" -H "Accept: application/octet-stream" \
  -o /tmp/corpus-check.jsonl "$CORPUS_URL"
sha256sum /tmp/corpus-check.jsonl && wc -l /tmp/corpus-check.jsonl   # expect 14294 lines
```

`curl -L` drops credentials on a cross-host redirect; urllib does not, and the signed
storage URL rejects a request still carrying an `Authorization` header — which is why
`hosted.py` strips it in a redirect handler. That path is the one thing the tests
cannot reach, so this curl is the check for it.

**Deploying**: Community Cloud, main file `streamlit_app.py`, branch
`deploy/streamlit-cloud`, and **Python 3.12 chosen in Advanced settings before the
first deploy** — it cannot be changed afterwards without deleting the app. A push to
this branch redeploys, whether or not the checks pass.

## Tests

```bash
uv run pytest                                  # 1,677 tests on a six-entry fixture; no API key needed
uv run pre-commit install                      # once per clone: ruff check and ruff format at each commit
```

The suite drives the real agent with scripted models rather than mocking the framework, so the
middleware, the checkpointer and the tool loop are exercised. Two suites are excluded by default
because they need something the repository does not carry:

```bash
SCINUMBERS_CORPUS=... uv run pytest -m corpus    # markers checked against a real corpus
OPENROUTER_API_KEY=...    uv run pytest -m network   # real model calls; costs about $0.01
```

## Evaluating the answers

The harness is a third adapter over the same agent — it asks a question set and records what came
back, with no mode flag and nothing the interactive drivers do not also get.

```bash
uv sync --extra ask --extra eval
scinumbers-eval check question-sets/first-set.jsonl      # is the set usable against this corpus?
scinumbers-eval run   question-sets/first-set.jsonl --repeats 3 \
    --results evaluations/baseline.results.jsonl         # asks, and appends one line per answer
scinumbers-eval report question-sets/first-set.jsonl \
    --results evaluations/baseline.results.jsonl --repeats 3 \
    --sheet evaluations/baseline.html                    # figures, and every answer with its entries
```

**A run resumes.** Results are appended as each question completes, so an interrupted run — a
budget, a provider, a person — loses only the question in flight. Running the same command again
asks what is missing and nothing else.

**No result holds a score.** Each line carries the question, the answer, the entries cited and
retrieved, the context the agent was shown and what produced it. Every figure is computed from
those, so a scoring rule can be changed and the whole baseline re-scored without re-asking a single
question. That has already paid for itself twice.

**Results never enter the repository.** Every record carries the retrieval results verbatim, so a
results file holds corpus text, which must not be committed (ADR-0170). The harness asks git whether
it would track the path and refuses to write if it would — and the answer sheet, which tabulates
entries, takes the same refusal.

### What it measures, by example

Ten questions, three repeats each, 2026-09-17 — the run that chose the default model
([full findings](docs/evaluations/2026-09-17-three-models.md)). Questions are tiered: `basic` is one
property of one organism, `compound` needs a comparison or a calculation.

| | Haiku 4.5 | **Opus 4.7** | MiniMax M2.7 |
|---|---:|---:|---:|
| Expected entries reaching the table | 53% | **65%** | 9% |
| — on `basic` questions | 70% | 68% | 12% |
| — on `compound` questions | 31% | **62%** | 6% |
| Unsupported questions correctly declined | 4 of 6 | **6 of 6** | 6 of 6 |
| Cost per 30 questions | $0.40 | $2.89 | $0.29 |

**The whole of Opus's lead is the compound questions** — on lookups the two Claude models are a tie.
So the model choice buys multi-organism comparisons and calculations, not better lookups, which is
what the tiering exists to show. The figure that is not about coverage: Haiku answered two of the six
unsupported questions with a quantity instead of saying the corpus does not hold it, which is the
failure this app is most meant to avoid.

Read no single repeat. The same comparison at one repeat each, that morning, had the two models a
point apart and looked like a tie.

Earlier runs are in [`docs/evaluations/`](docs/evaluations/2026-09-11-baseline.md). The judged
layer — a model separating an answer into claims — is deferred to `add-judged-faithfulness`: the
hand-labelled reference a judge must be validated against came back 29 sound of 30, and cannot gate
anything.

## What it does not do

Nothing writes to the corpus, and no tool can create, modify or delete an entry. The agent does not
retrieve literature or fetch papers. It is not given the name of whichever driver is calling it, so
it cannot behave one way for a person and another for a harness.

**The judged layer is not built.** Scoring citations against expected entries, scoring refusals on
unanswerable questions and reporting the spread across repeats all work; judging an answer's prose
claim by claim does not, and is deferred to `add-judged-faithfulness`. So the figures below are
deterministic: they say what was cited and retrieved, never whether a sentence is true.

**A rating does not change the answer it is about.** Nothing is retried, revised, re-retrieved or
withdrawn on account of a thumbs-down; the rating is evidence for whoever is improving the tool, and
it reaches them rather than the agent.

**The tracer is not the record, and nothing in it is masked.** Hosted tracing, when switched on,
sends a question's full text, tool results and answer to Langfuse; nothing is redacted, which was
accepted for corpus text. Traces are kept 30 days on the free tier and are never read back by the
app — ratings and the trail are.

**Enrolment is not managed from the app.** It is one command an operator runs (`scinumbers-enrol`). Adding a tester, assigning a role and issuing a
credential are rows and keys the operator writes by hand (`sql/accounts.sql`); there is no page for
it, and deliberately no permission that would pretend to gate one.

## For the course review

Sprint 3 asks for an agent with a clear purpose, real tools, a usable interface, error handling and
documentation. Those are covered above. Where the project went past the brief:

| Beyond the brief | Where |
|---|---|
| Deployed and multi-user, not a local demo: Streamlit Cloud with sign-in through any OpenID Connect provider and only verified addresses admitted, an enrolled account per tester funded by its own capped API key, and a Neon Postgres database behind it — the platform alone has an ephemeral disk and no notion of a user | ADR-0700, ADR-0780, ADR-0820, `hosted.py`, `accounts.py` |
| Provenance as a hard requirement, not a prompt instruction — citations are checked against what was actually retrieved, and unsupported ones flagged | `citations.py`, `entries_table.py` |
| The source's own notation restated only where the model reads it, never in the corpus — so the stored entry stays quotable | ADR-0420, `bionumbers.py` |
| Agentic retrieval over a 14,294-entry corpus: capped summaries with an honest total, then full entries on demand | ADR-0150, `tools.py` |
| Spend bounded twice over — a per-question ceiling and a run budget enforced in middleware, stopping the next call rather than reporting after the fact; and, where testers are enrolled, each one funded by their own OpenRouter key with its own monthly cap, issued from the accounts table | ADR-0120, ADR-0180, ADR-0820, `spend.py`, `accounts.py` |
| The agent separated from its drivers, so a web page and an evaluation harness run the identical agent with no mode flag | ADR-0110, `test_driver_independence.py` |
| Fault injection at the seams that fail silently — a spend ledger that cannot write, a marker whose condition can never fire | `test_spend.py`, `test_markers_against_corpus.py` |
| Decisions recorded as ADRs, and behaviour specified in OpenSpec rather than prose | `docs/decisions/`, `openspec/` |
| An evaluation whose records hold no scores, so a rule can be corrected and the whole baseline re-scored without re-asking a paid question | ADR-0530, ADR-0540, `scoring.py` |

Of the optional tasks: token usage and cost are displayed per question and per run; short- and
long-term memory are LangGraph checkpoints resumable across processes; the model is configurable and
reached through OpenRouter; and retrieval is agentic rather than a single similarity lookup.

**Measured:** the table under *Evaluating the answers* above. About two-thirds of what the corpus
holds for a question reaches the reader's table on the default model, and the gap is a failure of
search rather than of selection. The honest remaining gap is that nothing yet judges whether a
*sentence* is true.

## Where to read next

- [`docs/diagrams/architecture.md`](docs/diagrams/architecture.md) — the middleware stack, one
  question as a sequence, and which modules may depend on which
- `openspec/changes/add-ask-agent/proposal.md` — why an agent rather than a search box, what was
  deferred and why
- `src/scinumbers_ask/events.py` — the port: everything the agent emits and the one command it takes

To cite BioNumbers itself: Milo et al. *Nucl. Acids Res.* (2010) 38 (suppl 1): D750–D753.
