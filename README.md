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

> **A prototype, not an instrument.** More careful than a general-purpose model, but unevaluated
> and not scientifically trustworthy: verify every number against the original source before
> relying on it.

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

## Configuration

| Variable | Default | What it does |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | required; a question ends as `not_configured` without it |
| `SCINUMBERS_CORPUS` | — | required; path to the JSONL corpus |
| `SCINUMBERS_MODEL` | `anthropic/claude-haiku-4.5` | the model, as an OpenRouter slug |
| `SCINUMBERS_QUESTION_CEILING_USD` | `0.60` | hard per-question limit; the warning is derived at 80% of it |
| `SCINUMBERS_RUN_BUDGET_USD` | `1.20` | total across every question in a run |
| `SCINUMBERS_RUN` | `dev` | names the run spend is counted against; a new name starts a fresh budget |
| `SCINUMBERS_CHECKPOINTS` | `checkpoints/ask.sqlite` | where sessions persist |
| `SCINUMBERS_TRACE` | `logs/trace.jsonl` | the structured trail; `-` for stderr, empty to discard |
| `SCINUMBERS_MAX_SESSIONS` | `20` | how many browser sessions the deployment holds open at once; the next is told to try later |
| `SCINUMBERS_SESSION_IDLE_S` | `600` | how long a quiet session keeps its place before it is freed |

### The durable trail (hosted deployments only)

`SCINUMBERS_TRACE` writes to a file, which is enough on your own machine and
nothing at all on a host whose container filesystem does not survive a redeploy.
There, every record from every real session is discarded — the trail is written
correctly and then thrown away, which is the failure it exists to prevent, one
layer further out.

To keep it, add a Postgres connection to `.streamlit/secrets.toml` (and to the
hosting platform's own secrets box). `.streamlit/secrets.toml.example` carries
the shape and the three things a URL copied from a provider's console usually
gets wrong:

```toml
[connections.usage]
url = "postgresql+psycopg://USER:PASSWORD@HOST-pooler.REGION.provider.tech/DB?sslmode=require"
```

The table is created on first use; there is nothing to migrate. **Configure
nothing and the app behaves exactly as it does today** — refusing to start
without a telemetry database would make the absence of telemetry an outage.

Two properties worth knowing before you rely on it:

- **A failed write never fails a question.** This is the deliberate opposite of
  the spend limits, which stop work when they cannot be established: proceeding
  past a spend limit costs unbounded real money, proceeding past a failed
  telemetry write costs one row. Failures are reported to the operator's log and
  counted, never to the person asking
  ([ADR-0710](docs/decisions/0710-recording-fails-open.md)).
- **Conversations are still ephemeral.** The trail outlives a redeploy; the
  checkpoints do not. A hosted session that survives a restart is a separate
  decision and has not been made.

**What the trail keeps about you.** Your question, the answer you were given and the
identifiers of the entries behind it, under a per-question identifier and the
identifier of your session — and, where sign-in is configured, the account you
were signed in as and the role it held at the time. They are kept because a rating
on an answer nobody can read is worth nothing, and they are read by whoever
operates the deployment in order to improve it. The app says that exchanges are
logged in its own side panel and on the terminal's first line; this section is
the thorough version, and a fuller notice shown before use is deferred until
there are users rather than invited testers
([ADR-0840](docs/decisions/0840-what-a-question-s-trail-keeps.md),
[ADR-0810](docs/decisions/0810-the-role-is-written-at-record-time.md)).
`sql/feedback.sql` is how it is read back; its query 8 finds everything kept about
one account. A request path for deleting it, and any retention limit, are
deliberately deferred until there is somebody to ask.

### Sign-in and enrolment (hosted deployments only)

With no `[auth]` section in secrets the app runs exactly as described above: no
sign-in, one `OPENROUTER_API_KEY` from the environment, records carrying no
account, and the side panel saying so. **Add `[auth]` and every visitor must sign
in with Google and be enrolled before anything is drawn.** Signed in but not
enrolled is refused with one sentence and recorded, so the operator can enrol
someone who tried.

Enrolment happens outside the app — there is no page for it, and so no permission
gates it. The operator's steps, in order:

1. Create a Google OAuth client and put its values under `[auth]` in the hosting
   platform's secrets box; `.streamlit/secrets.toml.example` has the shape, and
   `redirect_uri` must end in `/oauth2callback`.
2. Create the `accounts` table in the same database as the trail, from
   `sql/accounts.sql`.
3. For each tester, mint a runtime key at OpenRouter with a monthly limit
   (Management API, `limit_reset: monthly`) and insert a row: email, one of the
   five roles, the key. Each tester's questions are then charged to their own
   key and capped by it; an enrolled account with no key can sign in but is told
   no credential has been issued. Nobody but the operator ever sees a key
   ([ADR-0780](docs/decisions/0780-accounts-live-in-the-trail-database.md),
   [ADR-0820](docs/decisions/0820-one-agent-per-session-handed-a-credential-not-an-identity.md)).

The five roles — student, scientist, senior scientist, dev, admin — differ today
in one thing: the side panel is a tab strip, and dev and admin get a second
**Dev** tab beside the entries, showing this session's trail for its last five
questions. The three tester roles get no such tab, and no strip at all. Nothing about the role reaches the agent, so an answer cannot depend on
who asked
([ADR-0800](docs/decisions/0800-default-deny-and-the-pruning-rule.md)). The
roles exist now so that ratings can later be weighted by who gave them.

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

## Tests

```bash
uv run pytest                                  # 917 tests on a six-entry fixture; no API key needed
uv run pre-commit install                      # once per clone: ruff check and ruff format at each commit
```

The suite drives the real agent with scripted models rather than mocking the framework, so the
middleware, the checkpointer and the tool loop are exercised. Two suites are excluded by default
because they need something the repository does not carry:

```bash
SCINUMBERS_CORPUS=... uv run pytest -m corpus    # markers checked against a real corpus
OPENROUTER_API_KEY=...    uv run pytest -m network   # real model calls; costs about $0.01
```

## What it does not do

Nothing writes to the corpus, and no tool can create, modify or delete an entry. The agent does not
retrieve literature or fetch papers. It is not given the name of whichever driver is calling it, so
it cannot behave one way for a person and another for a harness.

**The evaluation harness is not built.** Scoring citations against expected entries and scoring
refusals on unanswerable questions are specified in `openspec/changes/add-ask-agent/tasks.md`
(group 9) and unticked. That is why the prototype warning above says what it says.

**A rating does not change the answer it is about.** Nothing is retried, revised, re-retrieved or
withdrawn on account of a thumbs-down; the rating is evidence for whoever is improving the tool, and
it reaches them rather than the agent.

**Ratings given before 2026-09-16 name answers nobody can read.** The trail now records the question
as asked, the answer as given and the entries behind it, so a rating can be read next to what it
judged — but a trail cannot be backfilled, and the ratings collected before that change name
questions whose words were never kept anywhere
([ADR-0840](docs/decisions/0840-what-a-question-s-trail-keeps.md)). Ratings given before sign-in
was configured — and every rating on a deployment without it — carry no account either.

**Enrolment is not managed from the app.** Adding a tester, assigning a role and issuing a
credential are rows and keys the operator writes by hand (`sql/accounts.sql`); there is no page for
it, and deliberately no permission that would pretend to gate one.

## For the course review

Sprint 3 asks for an agent with a clear purpose, real tools, a usable interface, error handling and
documentation. Those are covered above. Where the project went past the brief:

| Beyond the brief | Where |
|---|---|
| Provenance as a hard requirement, not a prompt instruction — citations are checked against what was actually retrieved, and unsupported ones flagged | `citations.py`, `entries_table.py` |
| The source's own notation restated only where the model reads it, never in the corpus — so the stored entry stays quotable | ADR-0420, `bionumbers.py` |
| Agentic retrieval over a 14,294-entry corpus: capped summaries with an honest total, then full entries on demand | ADR-0150, `tools.py` |
| Spend enforced in middleware — a per-question ceiling and a run budget that stop the next call rather than reporting after the fact | ADR-0120, ADR-0180, `spend.py` |
| The agent separated from its drivers, so a web page and an evaluation harness run the identical agent with no mode flag | ADR-0110, `test_driver_independence.py` |
| Fault injection at the seams that fail silently — a spend ledger that cannot write, a marker whose condition can never fire | `test_spend.py`, `test_markers_against_corpus.py` |
| Decisions recorded as ADRs, and behaviour specified in OpenSpec rather than prose | `docs/decisions/`, `openspec/` |

Of the optional tasks: token usage and cost are displayed per question and per run; short- and
long-term memory are LangGraph checkpoints resumable across processes; the model is configurable and
reached through OpenRouter; and retrieval is agentic rather than a single similarity lookup.

**Not done, and the honest gap:** there is no evaluation report. Nothing here has been measured
against expected answers.

## Where to read next

- [`docs/diagrams/architecture.md`](docs/diagrams/architecture.md) — the middleware stack, one
  question as a sequence, and which modules may depend on which
- `openspec/changes/add-ask-agent/proposal.md` — why an agent rather than a search box, what was
  deferred and why
- `src/scinumbers_ask/events.py` — the port: everything the agent emits and the one command it takes

To cite BioNumbers itself: Milo et al. *Nucl. Acids Res.* (2010) 38 (suppl 1): D750–D753.
