# BioNumbers ask

An agent that answers natural-language questions about biological quantities using only a supplied
corpus, citing an entry for every number it reports. Where the corpus does not cover a question, it
says so rather than answering from the model's own knowledge.

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

Two parts of the plan are not built yet and are visible as unticked tasks in
`openspec/changes/add-ask-agent/tasks.md`: the web interface is partial (a session and its answers,
but not yet retrieval progress or the entries table), and the evaluation harness — scoring citations
against expected entries, scoring refusals on unanswerable questions — has not been started.

## Where to read next

- `openspec/changes/add-ask-agent/proposal.md` — why an agent rather than a search box, what was
  deferred and why
- `openspec/changes/add-ask-agent/design.md` — the middleware stack and the shape of the tools
- `src/bionumbers_ask/events.py` — the port: everything the agent emits and the one command it takes
