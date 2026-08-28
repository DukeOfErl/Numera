# BioNumbers ask

**How long is an E. coli cell? How many ribosomes does it carry?** Quantitative biology runs on
numbers like these, and the usual way to get one out of a language model is to ask and hope. A
plausible number arrives with no way to tell whether it was recalled, interpolated, or invented.

This agent answers only from a corpus you supply, and cites the entry behind every number it
reports. Where the corpus does not cover a question, it says so rather than answering from the
model's own knowledge. It is for people who need a figure they can defend — students,
researchers, anyone writing an estimate they will later have to justify.

Three commitments shape the design:

- **Provenance.** Every figure carries the identifier of the entry it came from, and the entries
  themselves are shown beside the answer — cited ones first, then others the search found and the
  answer passed over. A number the answer used but the corpus never returned is flagged as
  unsupported rather than quietly printed.
- **Precision.** Units are compared by dimension, so a length is never silently reconciled with a
  volume, and an unrecognised unit is reported as *unknown* rather than assumed compatible. Entries
  with no measurement method recorded, or no scalar value, are marked — half the corpus has no
  method, and an answer should not hide that.
- **Reliability.** Spend is capped per question and per run, conversations are bounded by their
  token count, and every question ends with a stated reason and what it consumed. No tool can
  create, modify or delete an entry.

> **A prototype, not an instrument.** More careful than a general-purpose model, but unevaluated
> and not scientifically trustworthy: verify every number against the original source before
> relying on it.

The agent is separated from the interfaces that drive it (ports and adapters): it emits events and
accepts questions, and a terminal, a web page and — later — an evaluation harness are three adapters
over the one agent, with no mode flag inside it.

## The corpus

**The corpus is not bundled with the code and is not in version control.** Its licensing is
unresolved, so the data is deliberately kept out of the repository (see `.gitignore`).

The agent answers from a JSONL corpus supplied at run time. It was built and tested against
**BioNumbers** (<https://bionumbers.hms.harvard.edu>), a public database of quantitative biology,
whose record shape and `BNID` identifiers the loader and citation format follow. Any corpus in that
shape can be substituted.

To cite BioNumbers itself:

> Milo et al. *Nucl. Acids Res.* (2010) 38 (suppl 1): D750–D753.

### Obtaining a runnable corpus

Download the prepared file: **&lt;CORPUS-DOWNLOAD-LINK&gt;** (JSONL, ~20 MB, 14,294 entries).

> **The link above is a placeholder and must be filled in before this README is given to anyone.**
> Without it this section describes a file the reader has no way to obtain, and every instruction
> below it is unrunnable.

#### Getting the source export yourself

Go to <https://bionumbers.hms.harvard.edu/resources.aspx> and click **Download the BioNumbers
database**. That gives you `BioNumbers.xls`, the export this project was built against.

It is a button rather than a link, so there is no address to paste — the page has to be open for the
download to work.

Checked on 2026-08-28: 27,286,533 bytes, SHA-256
`b185032ac36bfa250435ef0980180e1b5bc4341ae9e06c5f83aa764a84fd36ef`. Worth confirming, since the
database is updated and the file you get may not be the one these figures describe:

```bash
sha256sum BioNumbers.xls
```

It is provided ready to use because what BioNumbers distributes is not directly readable here: the
export is a 27 MB HTML `<table>` carrying an `.xls` extension, and converting it into the record
shape this agent reads — normalising ranges written a dozen ways, reconciling two Unicode
micrometres, stripping injected markup — is done by a separate ingestion project that is not part of
this repository.

A six-entry sample lives at `tests/fixtures/corpus_sample.jsonl`. It is enough to run the whole test
suite, and too small to ask real questions of.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra ask
export OPENROUTER_API_KEY=...                  # the model is reached through OpenRouter
export BIONUMBERS_ASK_CORPUS=/path/to/bionumbers.jsonl
```

## Running it

### Terminal

```bash
uv run bionumbers-ask                          # a session; ask questions, 'exit' to leave
uv run bionumbers-ask --ask "how wide is an E. coli cell?"
```

Each answer is followed by the entries it drew on — property, organism, value, units, identifier,
reference — with the cited entries separated from the rest, and by a line reporting why the question
ended, what it cost and which model produced it.

A session continues across launches:

```bash
uv run bionumbers-ask --session <id>           # the id is printed when a session starts
```

The conversation, the accumulated spend and the ceiling in force live in the checkpoint store
(`checkpoints/`), not in the driver — which is what lets a second interface pick up the same session.

### Web

```bash
uv run streamlit run streamlit_app.py
```

Reads `BIONUMBERS_ASK_CORPUS`, `BIONUMBERS_ASK_CHECKPOINTS` and `BIONUMBERS_ASK_TRACE` from the
environment, since a Streamlit script takes no arguments of its own.

## Tests

```bash
uv run pytest                                  # runs against the six-entry fixture; no API key needed
uv run pytest -m network                       # calls a real model; needs OPENROUTER_API_KEY and costs money
```

The suite drives the real agent with scripted models rather than mocking the framework, so the
middleware, the checkpointer and the tool loop are exercised.

## Configuration

| Variable | Default | What it does |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | required; a question ends as `not_configured` without it |
| `BIONUMBERS_ASK_CORPUS` | — | required; path to the JSONL corpus |
| `BIONUMBERS_ASK_MODEL` | `anthropic/claude-haiku-4.5` | the model, as an OpenRouter slug |
| `BIONUMBERS_ASK_QUESTION_CEILING_USD` | `0.60` | hard per-question limit; the warning is derived at 80% of it |
| `BIONUMBERS_ASK_RUN_BUDGET_USD` | `1.20` | total across all questions in a run |
| `BIONUMBERS_ASK_CHECKPOINTS` | `checkpoints/ask.sqlite` | where sessions persist (web only; the terminal takes `--checkpoints`) |
| `BIONUMBERS_ASK_TRACE` | `logs/trace.jsonl` | the structured trail; `-` for stderr, empty to discard |
| `BIONUMBERS_ASK_RUN` | `dev` | a label carried on every record, so one run's spend is separable |

Two further limits are module constants rather than settings, in `agent.py`: **12 model calls**
per question, and a conversation bounded at **120,000 tokens** (warning at 75% of it). Both are
numbers to tune against measured sessions rather than knobs.

Spend is enforced, not merely reported: a question stops at its ceiling and presents what it had
established, marked incomplete, rather than being cut off mid-sentence. A limit is configured where
it binds — the number you set is the one that stops work, and the warning is derived from it — and an
answer that ran to a limit says so, which is a different thing from one that finished with room to
spare ([ADR-0180](docs/decisions/0180-limits-named-where-they-bind.md)).

Two test suites are excluded by default because they need something the repository does not carry:

```bash
BIONUMBERS_ASK_CORPUS=... uv run pytest -m corpus    # markers checked against a real corpus
OPENROUTER_API_KEY=...    uv run pytest -m network   # real model calls; costs about $0.01
```

## What it does not do

Nothing writes to the corpus, and no tool can create, modify or delete an entry. The agent does not
retrieve literature or fetch papers. It is not given the name of whichever driver is calling it, so
it cannot behave one way for a person and another for a harness.

One part of the plan is not built yet and is visible as unticked tasks in
`openspec/changes/add-ask-agent/tasks.md`: the evaluation harness — scoring citations against
expected entries, scoring refusals on unanswerable questions — has not been started. The web
interface is complete: a session, streamed retrieval progress, the cited and uncited tables, and the
full entries in the side panel.

## For the course review

Sprint 3 asks for an agent with a clear purpose, real tools, a usable interface, error handling and
documentation. Those are covered above. What follows is where the project went past the brief, and
where it deliberately has not gone yet.

| Beyond the brief | Where |
|---|---|
| Provenance as a hard requirement, not a prompt instruction — citations are checked against what was actually retrieved, and unsupported ones flagged | `citations.py`, `entries_table.py` |
| Agentic retrieval over a 14,294-entry corpus: capped summaries with an honest total, then full entries on demand | ADR-0150, `tools.py` |
| Spend enforced in middleware — a per-question ceiling and a run budget that stop the next call rather than reporting after the fact | ADR-0120, ADR-0180, `spend.py` |
| The agent separated from its drivers, so a terminal, a web page and an evaluation harness run the identical agent with no mode flag | ADR-0110, `test_driver_independence.py` |
| Fault injection at the seams that fail silently — a spend ledger that cannot write, a marker whose condition can never fire | `test_spend.py`, `test_markers_against_corpus.py` |
| Decisions recorded as ADRs, and behaviour specified in OpenSpec rather than prose | `docs/decisions/`, `openspec/` |

Of the optional tasks: token usage and cost are displayed per question and per run; short- and
long-term memory are LangGraph checkpoints resumable across processes; the model is configurable and
reached through OpenRouter; and retrieval is agentic rather than a single similarity lookup.

**Not done, and the honest gap:** there is no evaluation report. The question set and scoring are
specified (`tasks.md`, group 9) and unbuilt, which is exactly why the prototype warning above says
what it says — nothing here has been measured against expected answers.

## Where to read next

- `docs/diagrams/architecture.md` — the agent's graph (generated from the compiled
  object), one question as a sequence, and which modules may depend on which

- `openspec/changes/add-ask-agent/proposal.md` — why an agent rather than a search box, what was
  deferred and why
- `openspec/changes/add-ask-agent/design.md` — the middleware stack and the shape of the tools
- `src/bionumbers_ask/events.py` — the port: everything the agent emits and the one command it takes
