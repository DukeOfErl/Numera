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

## Tests

```bash
uv run pytest                                  # 1,559 tests on a six-entry fixture; no API key needed
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

## The validator prototype (`bionumbers`)

The ask agent answers from a curated corpus. The validator goes the other way: from a **property
question** to the open-access literature, out of which it extracts candidate numbers with their
verbatim evidence and puts each one in front of a person. It is a prototype, built to be rebuilt
against what reviewers and papers actually do; what it must get right is the review screen and the
record it leaves behind ([`proposal.md`](openspec/changes/add-validator-prototype/proposal.md)).

Three commands and a page:

```bash
uv sync --extra ask --extra validator          # the review page imports the ask app's sign-in door
export BIONUMBERS_OPENROUTER_API_KEY=...       # its own OpenRouter key, so its spend is readable apart from the ask app's

bionumbers discover "doubling time" --organism "Escherichia coli" --since 2015 --limit 20
bionumbers extract <run-id> --ceiling 2 --budget 40
bionumbers status <run-id>
bionumbers load <run-id> --db-url "$BIONUMBERS_REVIEW_DB_URL"   # after applying sql/review.sql once
streamlit run review_app.py
```

- **Harvest** is the other way in (ADR-0950): `bionumbers harvest <run-id> --pmcids PMC1,PMC2`
  starts a run from papers chosen ahead of any question, and `extract` then asks each one for
  the numbers worth reusing, at most twenty per paper. `--scope` names the domain whose classes
  of value are wanted — `biology` (the default, cells and molecules), `organismal` (bodies,
  physiology, life history, genomes), `biophysics`, `chemistry` or `physics`
  (ADR-1500).
- **Curate** loads BioNumbers' own entries as the top trust tier, beside the harvested ones:
  `bionumbers curate --corpus ~/bionumbers/bionumbers.jsonl` keeps the yeast and cytoskeleton
  entries that are measured and referenced and that nothing in the record marks doubtful — no
  fused or one-sided range, a readable unit, no "rule of thumb" (ADR-1510).
- **Discover** searches Europe PMC for open-access research articles with a PMCID — reviews,
  editorials, comments and preprints excluded by metadata — fetches each paper's JATS XML into
  `data/europepmc/`, and records the licence. A paper without XML is recorded with the status the
  service gave, never as an error and never as "states nothing".
- **Extract** reads each paper into passages (table cells carry their headers; citation markers stay
  visible as `[ref N]`) and makes **one** structured call per paper — the paper in a cached prefix,
  no tools, no agent loop. Every quote is checked mechanically against the paper; a failure goes
  back to the model once, a second failure drops the claim. A second call picks the other text a
  reviewer will see. Each paper ends in one of six named states; the spend ceiling is **$2 per
  paper** and the call that would cross it is not made.
- **The review page** shows one claim at a time: the question, the value as the paper states it,
  the citation, the conditions and method each quoted with where it came from (beside the value,
  from Methods, by reference, supplementary only, not stated), and **two texts** from the paper,
  each as the paper wrote it with nothing in it emphasised. When a text is a table cell, the whole
  table is drawn beneath the two texts with its caption, both texts' cells marked alike. The
  reviewer must choose which text fits the value and, separately, approve or disapprove. The second
  text is a distractor or a second legitimate occurrence; which it was is stored and never shown.
  Decisions are written the moment they are given and the write fails closed: a reviewer whose
  decision could not be saved is told so and keeps the item.

What it does not read: supplementary files, figure images, PDFs. What it does not do: verify an
existing BioNumbers entry (that is `add-grounding-validator`), score reviewer agreement, or route to
cheaper models. Sequence diagrams: [`architecture.md` §7](docs/diagrams/architecture.md).

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

**There is no tracing instrumentation yet.** LangSmith or Langfuse — per-question traces with
per-user attribution, and ratings pushed as scores — is planned and deliberately not enabled:
`langsmith` is already present as a transitive dependency, and turning tracing on ships prompts,
tool results and corpus text to a third-party service. That is a decision to take deliberately
rather than by setting an environment variable.

**Enrolment is not managed from the app.** Adding a tester, assigning a role and issuing a
credential are rows and keys the operator writes by hand (`sql/accounts.sql`); there is no page for
it, and deliberately no permission that would pretend to gate one.

## For the course review

Sprint 3 asks for an agent with a clear purpose, real tools, a usable interface, error handling and
documentation. Those are covered above. Where the project went past the brief:

| Beyond the brief | Where |
|---|---|
| Deployed and multi-user, not a local demo: Streamlit Cloud with Google sign-in, an enrolled account per tester funded by its own capped API key, and a Neon Postgres database behind it — the platform alone has an ephemeral disk and no notion of a user | ADR-0700, ADR-0780, ADR-0820, `hosted.py`, `accounts.py` |
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
