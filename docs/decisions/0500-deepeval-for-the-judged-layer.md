# ADR-0500: DeepEval for the judged layer, and why not RAGAS

- **Status:** accepted
- **Date:** 2026-09-03
- **Pull request:** _pending — feat/answer-evaluation_

## Context

The evaluation specified in `answer-evaluation` scores by entry identifiers and needs no model.
A follow-up to `add-answer-evaluation` (deferred there, drafted, triggered by its baseline) adds a second layer that judges an answer's claims against the context the agent was
shown, and the product of that layer is not the score but the per-claim verdict and reason: which
claim was unsupported and why, so a user can be warned and a developer can fix the cause. That
needs an LLM judge, and the question was which framework to build it on rather than whether to
hand-roll one — the user-level conventions prefer a library's component to a parallel
implementation.

The candidates were surveyed on 2026-09-03 against PyPI, each repository's commit history, source
on `main`, and the official docs, and the two front-runners were resolved against a copy of this
project's `uv.lock`.

- **RAGAS 0.4.3** (released 2026-01-13). No commit since 2026-02-24 and no pull request merged since
  June, with about six hundred issues open. `import ragas` fails on a fresh install beside
  LangChain 1.x because it imports a module removed from `langchain-community` 0.4; five fixes are
  open and unmerged. Its 0.4 `Faithfulness` computes per-statement verdicts with reasons and then
  discards them, returning a bare score, so the critic would have needed a subclass. Its LangChain
  model wrapper is deprecated. It pins `openai<3`, which would downgrade this project's `openai`.
- **DeepEval 4.2.1** (released 2026-09-03, commits that day). `FaithfulnessMetric` exposes `.score`,
  `.reason`, `.claims`, `.truths` and `.verdicts`, each verdict carrying `verdict` and `reason`. It
  has no LangChain dependency, so nothing to break; a custom judge is a subclass of its model base
  with `generate(prompt, schema)`. pytest is first class. It sends anonymous telemetry unless
  `DEEPEVAL_TELEMETRY_OPT_OUT=1`.
- **openevals + Braintrust autoevals.** Two light packages; a LangChain model as judge directly;
  autoevals' `Faithfulness` returns per-statement verdicts with reasons. Rejected for wanting a
  hand-written harness where DeepEval has one, and for lacking the context metrics a later step may
  want.
- Also read and set aside: Arize Phoenix evals (binary verdict, one explanation), MLflow GenAI
  (needs retriever spans in a trace, heavy), Opik and TruLens (server or session machinery), Inspect
  and promptfoo (different runners).

## Decision

Build the judged layer on DeepEval's `FaithfulnessMetric`, used as shipped, behind one thin wrapper
that hands it the project's `ChatOpenAI` through OpenRouter and reads the provider's cost figure.
`deepeval` goes in its own `eval` extra, and exactly one module imports it, lazily, so the
deterministic harness runs on an `ask` install unchanged. Telemetry is switched off in that module,
before the import, not in a README.

RAGAS is not adopted, and the reasons are the ones above rather than a preference: an unmaintained
dependency with a known import failure against the framework this project is built on is a cost
paid at every upgrade.

## Trade-off accepted

DeepEval brings about thirty-six packages, among them OpenTelemetry, gRPC, PostHog and four pytest
plugins, into an environment that otherwise has none of them; the extra keeps them out of the
agent's install but not out of the developer's. Its judge prompts are the framework's, so a change
in a DeepEval release can move the judged figures with no change here — which is one reason every
judgement records the judge model and the report marks judged figures unvalidated until they agree
with the deterministic layer (ADR-0510). The API surface was read from source and docs on the date
above, not exercised; the first implementation task verifies it against the installed version.
