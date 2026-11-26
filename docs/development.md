# Developing Numera

How to run Numera locally, the command-line tools, every setting, the tests, the evaluation harness
and the harvesting and review pipeline. The [README](../README.md) says what the project is; hosting it with
sign-in is in the [deployment guide](deployment.md).

## Running it locally

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

**3. Start the app.** Point `NUMERA_CORPUS` at where the corpus should go. Finding none
there and the export beside it, the app says what it is about to do and builds one — about a minute,
once.

```bash
export NUMERA_CORPUS=~/bionumbers/bionumbers.jsonl   # BioNumbers.xls is in that directory
uv run streamlit run streamlit_app.py
```

Then ask something. `What is the minimal inhibitory concentration of kanamycin for E. coli?` is a
good first question: the source says `<8`, and the answer says so rather than reporting 8 as a
measurement.

### Asking from the terminal

The web page is the main interface. The same agent can also be asked from a terminal:

```bash
uv run numera-ask                                   # a conversation, one question per line
uv run numera-ask --ask "How long is an E. coli cell?"   # one question, then exit
```

## The commands, and where they live

`uv sync` installs the console scripts into the project's virtualenv, not onto
your `PATH`:

| Command | What it does |
| --- | --- |
| `numera-ask` | the terminal driver: ask a question, see the entries behind the answer |
| `numera-enrol` | enrol one tester: mint a capped credential and record the account |
| `numera-withdraw` | withdraw one tester: disable the account and revoke its credential |
| `numera-pending` | list who is stuck at sign-in; silent when nobody is |
| `numera-first-use` | list readers seen for the first time; silent when nobody is new |
| `numera-eval` | the evaluation harness: `check`, `run`, `report` |
| `bionumbers-ingest` | build a corpus from the published export |
| `numera-validator` | the harvesting and review pipeline: `harvest`, `extract`, `load`, `curate`, `simulate-review`, `status`, `upgrade-store`, and the dormant `discover` (see [Harvesting and review](#harvesting-and-review)) |

One package keeps the old name on purpose. `bionumbers_ingest` and its command read BioNumbers' own
export, so they are named for the source they adapt; everything named for the project says Numera
(ADR-0400, ADR-1900).

A bare `numera-enrol` is `command not found` until the virtualenv is on your
path. Three ways, in increasing permanence:

```bash
.venv/bin/numera-enrol --help        # no setup; works from the repository root

source .venv/bin/activate                # this shell only, then bare names work
numera-enrol --help

ln -sf "$PWD/.venv/bin/numera-enrol" ~/.local/bin/   # permanent, one command
```

The symlink is the one to prefer for `numera-enrol`, because enrolling a
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
| `NUMERA_CORPUS` | — | path to the JSONL corpus; required unless `NUMERA_STORE` is set. Today that is BioNumbers' own export as converted by `bionumbers-ingest`: the name says what the agent reads, not where the entries came from, so a second source in the same format would use it too |
| `NUMERA_STORE` | — | path to the harvest store (a SQLite file), read instead of a corpus file: numbers harvested from papers, with their reviews, beside the curated BioNumbers entries. See [the README](../README.md#where-the-numbers-come-from). The store is read once at start, so reviewers' later decisions appear after a restart; evaluation and the answer sheet still read a corpus file only. Setting both is refused |
| `NUMERA_MODEL` | `anthropic/claude-opus-4.7` | the model, as an OpenRouter slug |
| `NUMERA_QUESTION_CEILING_USD` | `0.60` | hard per-question limit; the warning is derived at 80% of it |
| `NUMERA_RUN_BUDGET_USD` | `1.20` | total across every question in a run; where sign-in is configured, per account rather than shared |
| `NUMERA_RUN` | `dev` | names the run spend is counted against; a new name starts a fresh budget |
| `NUMERA_CHECKPOINTS` | `checkpoints/ask.sqlite` | where sessions persist |
| `NUMERA_TRACE` | `logs/trace.jsonl` | the structured trail; `-` for stderr, empty to discard |
| `NUMERA_MAX_SESSIONS` | `20` | how many browser sessions the deployment holds open at once; the next is told to try later |
| `NUMERA_SESSION_IDLE_S` | `600` | how long a quiet session keeps its place before it is freed |
| `NUMERA_TRACING` | off | `langfuse` turns hosted tracing on, and nothing else does; see the [deployment guide](deployment.md#hosted-tracing-optional) |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | — | all three required when tracing is on; the base URL names the region |

Every variable above is read from the process environment. A hosted deployment has
no shell to export one from, so **put it in the app's Secrets box as a top-level
key** — Streamlit promotes every top-level string, int or float in secrets to an
environment variable at server start, before the script runs (verified against the
installed Streamlit 1.61.1: `runtime/secrets.py`, `_maybe_set_environment_variable`,
called from `web/bootstrap.py`). The `[auth]` and `[connections.usage]` *sections*
are the exception: a table is not promoted, and is read as `st.secrets` (see the
[deployment guide](deployment.md)).

```toml
OPENROUTER_API_KEY = "sk-or-..."
NUMERA_MODEL = "anthropic/claude-opus-4.7"
NUMERA_RUN_BUDGET_USD = "1.20"
```

For the database, sign-in and tracing sections of the secrets file, see the [deployment guide](deployment.md).

## Tests

```bash
uv run pytest -n 3 --dist worksteal            # ~3,000 tests on a six-entry fixture; no API key needed
uv run pre-commit install                      # once per clone: lint and tests at commit, push and merge
```

**The test loop has two tiers** ([ADR-1300](decisions/1300-two-tier-test-loop.md)). At *commit*, only the
tests the change reaches run (pytest-testmon: a few seconds to about a minute, against 100–180s for the whole
suite on the default three workers). Testmon follows Python only, so a staged change to anything a test merely
reads — `README.md`, `sql/`, `openspec/`, `.github/`, a data file, `pyproject.toml` — runs the **full suite**
instead; `CHANGELOG.md`, `CLAUDE.md` and `docs/` run nothing, and a test fails if any code starts naming
one of them ([ADR-2110](decisions/2110-the-inert-list-is-checked-by-what-code-names.md)). At *push*,
*merge* and in CI the full suite runs in parallel, once
([ADR-2100](decisions/2100-commit-tier-runs-at-commit-only.md)). The first commit in a clone builds testmon's database, which is one serial full run (~5 minutes);
the database is per-checkout and git-ignored. `NUMERA_TEST_WORKERS` overrides the three workers. Three is a memory limit, not a speed one:
on a 12-core, 8 GB machine six is faster (about 80s against 100–180s) when memory is free, but ran out of
memory once under ordinary load, and twelve were slower than serial. A checkout with no
`.venv` prints `NOT RUN` rather than failing, and the push and CI tiers still run everything.

The suite drives the real agent with scripted models rather than mocking the framework, so the
middleware, the checkpointer and the tool loop are exercised. Two suites are excluded by default
because they need something the repository does not carry:

```bash
NUMERA_CORPUS=... uv run pytest -m corpus    # markers checked against a real corpus
OPENROUTER_API_KEY=...    uv run pytest -m network   # real model calls; costs about $0.01
```

## Evaluating the answers

The harness is a third adapter over the same agent — it asks a question set and records what came
back, with no mode flag and nothing the interactive drivers do not also get.

```bash
uv sync --extra ask --extra eval
numera-eval check question-sets/first-set.jsonl      # is the set usable against this corpus?
numera-eval run   question-sets/first-set.jsonl --repeats 3 \
    --results evaluations/baseline.results.jsonl         # asks, and appends one line per answer
numera-eval report question-sets/first-set.jsonl \
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

## Harvesting and review

The pipeline that fills the paper database, and the page where its numbers are reviewed. The
[README](../README.md#where-the-numbers-come-from) says why it works this way. It is a prototype:
it ran in October 2026 to fill the current database and is not running continuously.

Its package and command are still called `numera_validator` / `numera-validator`, after its first
version, which went from a question to the literature (`discover`). That path is kept in the code
but is no longer used (ADR-0950): papers are now harvested ahead of any question.

```bash
uv sync --extra ask --extra validator          # the review page imports the ask app's sign-in
export NUMERA_OPENROUTER_API_KEY=...           # its own OpenRouter key, so its spend is readable apart from the ask app's
export NUMERA_REVIEW_DB_URL=...                # the store: a SQLite URL locally, Postgres when hosted

numera-validator harvest <run-id> --pmcids PMC1,PMC2 --scope biology --topic "..."
numera-validator extract <run-id>                                  # $2 per paper, $40 per run by default
numera-validator status  <run-id>
numera-validator load    <run-id>                                  # into the store; apply sql/review.sql once first
numera-validator curate  --corpus ~/bionumbers/bionumbers.jsonl    # the curated BioNumbers tier
numera-validator simulate-review --reviewer student=<model>@0.6 --reviewer scientist=<model>@0.35
streamlit run review_app.py --server.port 8502
```

The ask app reads the same store when `NUMERA_STORE` points at it (a SQLite file; see
[Configuration](#configuration)).

- **Harvest** starts a run from papers chosen by hand (`--pmcids`, or `--pmcid-file` with one per
  line), fetching each paper's JATS XML from Europe PMC into `data/europepmc/` and recording its
  licence. `--scope` names the domain whose classes of value are wanted: `biology` (the default,
  cells and molecules), `organismal` (bodies, physiology, life history, genomes), `biophysics`,
  `chemistry` or `physics` (ADR-1500). `--topic` is what the papers are about, for a reviewer to
  choose by.
- **Extract** reads each paper into passages (table cells carry their headers; citation markers stay
  visible as `[ref N]`) and makes **one** structured call per paper, asking for the numbers worth
  reusing, at most twenty: the paper in a cached prefix, no tools, no agent loop. Every quote is
  checked mechanically against the paper; a failure goes back to the model once, a second failure
  drops the claim. A second call picks the other text a reviewer will see. Each paper ends in one of
  six named states; the call that would cross the spend ceiling is not made.
- **Load** writes a run's results into the store. **Upgrade-store** adds columns a store loaded by an
  older version lacks (for example each paper's bibliographic record, ADR-1750).
- **Curate** loads BioNumbers' own entries as the top trust tier, beside the harvested ones. It keeps
  the yeast and cytoskeleton entries that are measured and referenced and that nothing in the record
  marks doubtful: no fused or one-sided range, a readable unit, no "rule of thumb" (ADR-1510).
- **The review page** shows one claim at a time, in two steps. First the question, the citation
  and **two texts** from the paper side by side, each as the paper wrote it with nothing in it
  emphasised; when a text is a table cell, the whole table is drawn beneath the two texts with its
  caption, both texts' cells marked alike. The reviewer chooses the text that states a value for
  the quantity by clicking it and writes the value they read. Only then is the stored entry
  revealed (the value as the paper states it, the paper's own term, the conditions and method each
  quoted with where it came from) and the reviewer approves or disapproves. An issue can be raised
  at either step. The second text is a distractor or a second legitimate occurrence; which it was is
  stored and never shown. Each step is written the moment it is given and the write fails closed: a
  reviewer whose step could not be saved is told so and keeps the item. A reviewer can narrow the
  pool to one domain or topic and can set a paper aside; the simulated reviewers never get those
  choices. The page is a separate Streamlit script, not part of the ask app, and has not been
  deployed. It finds its store in `[connections.review]` in `.streamlit/secrets.toml`, or else in
  `NUMERA_REVIEW_DB_URL`, never in the trail's `[connections.usage]` (ADR-2000). Where the secrets
  have `[auth]`, it signs readers in as the ask app does, so run it on the port `redirect_uri` names.
- **A simulated review** lets models stand in for reviewers until there are people: each role
  reviews its own fixed share of the items, is shown exactly what the page shows a person step by
  step, and may raise an issue instead of deciding. Every row it writes records the role, the model
  asked for and the model that answered, and anything built on those rows must be labelled as
  simulated. It is bounded at $0.10 per decision and $2 per run by default, and running it again
  continues where it stopped. Every decision in the current store is simulated.
- **Discover** (dormant) searches Europe PMC for open-access research articles for a property and an
  organism, then hands them to `extract`. It found the right paper 4 times in 32, which is why
  harvesting replaced it.

What it does not read: supplementary files, figure images, PDFs. What it does not do: verify an
existing BioNumbers entry, score agreement between reviewers, or route to cheaper models. Sequence
diagrams: [`architecture.md` §7](diagrams/architecture.md#7-the-validator-prototype-from-a-question-to-review-items).
