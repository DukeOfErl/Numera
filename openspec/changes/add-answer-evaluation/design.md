## Context

See `proposal.md` — Why. The requirements are in `specs/answer-evaluation/`; the harness drives
the agent through the port in `specs/agent-session/` (promoted when `add-ask-agent` archives) and
changes nothing in `grounded-answering` or `spend-control`.

What is already there and shapes the approach:

- **The port is complete for a driver's needs.** `ask()` yields `Retrieval` events carrying the entry
  identifiers each search returned, `AnswerEntries` carrying cited and retrieved identifiers,
  `UngroundedRefusal`, `CitationWarning`, and a `QuestionEnded` naming the reason, the spend, the
  model, and the counts against every bound (ADR-0180). The harness records; it does not judge what
  the agent should have emitted.
- **The citation parser is shared.** `citations.py` is the one parser of `[[nnnnnn]]`, used by both
  drivers (ADR-0410), so the harness's notion of "what was cited" is the same as the page's.
- **Spend is already a run-level figure.** `run_ledger` keys spend on the configured run label, so a
  driver opening a session per question is bounded by one budget, and `QuestionEnded.reason ==
  RUN_BUDGET` is how the harness learns the run must stop.
- **The dependency direction is enforced by a test.** `tests/test_driver_independence.py` asserts
  the core never imports a driver. The harness is a driver and must be added to that assertion.
- **`add-ask-agent`'s proposal already ruled on LLM judges**: weaker than identifier comparison,
  validated against it rather than assumed, deterministic harness first. This design implements
  that ordering rather than reopening it.
- **Frameworks checked on 2026-09-03.** `deepeval` 4.2.1 (released that day) exposes, after
  `FaithfulnessMetric.measure()`, `.score`, `.reason`, `.claims`, `.truths` and `.verdicts`, each
  verdict carrying `verdict` and `reason`; it has no LangChain dependency and resolves against the
  current lock. `ragas` 0.4.3 was rejected: no commit since 2026-02-24, an import-time failure
  against `langchain-community` 0.4 with the fixes unmerged, per-statement verdicts computed and
  then discarded, and a pin of `openai<3` that would downgrade ours. Both resolutions were run
  against a copy of `uv.lock`; each adds about thirty-six packages. **Re-verify the DeepEval surface
  against the installed version as the first task** — the API was read from source on `main` and
  the docs, not exercised.

## Goals / Non-Goals

**Goals:**

- A third adapter over the unchanged agent, runnable unattended, that leaves a readable record
  after any interruption and can be reported on at any point.
- Two scoring layers kept visibly apart: exact identifier and refusal scoring that needs no model,
  and a judged faithfulness layer whose per-claim reasons are the product and whose figures are
  labelled unvalidated until they have earned otherwise.
- Re-judging without re-asking: a second judge model, or a fixed judge prompt, must cost judge spend
  only.

**Non-Goals:**

- Changing the agent in response to findings. The baseline this produces is the input to those
  changes; they are their own work packages.
- A general evaluation platform, dashboards, or comparison between runs beyond what the report
  states. Cost-drift alerting stays deferred where the earlier proposal left it.
- Judging anything but faithfulness. Answer relevancy, context precision and the like are available
  in the same framework and can be added once the faithfulness judge has passed its gate; adding
  them first would multiply judge spend before any judge is trusted.

## Decisions

### The harness is a driver, in the package, under its own extra

Modules beside `cli.py` and `web.py`, named for what they hold: the question set and its loader;
the driver that asks, records and resumes; the deterministic scoring as pure functions; the judge
wrapper; the report; and the command. The judge wrapper is the **only** module that imports
`deepeval`, and imports it inside the function that needs it, so the deterministic layer runs on an
`ask` install with nothing added. `deepeval` goes in a new `eval` extra rather than into `ask`: it
brings OpenTelemetry, gRPC, PostHog and four pytest plugins, none of which a person running the
agent needs.

*Alternative rejected:* a separate `evals/` tree outside the package. It would need its own import
path to the port and its own place in the independence test, and it would tempt the harness into
reading the corpus and the checkpoint directly instead of through the agent — the very coupling the
port exists to prevent.

### The context recorded is the session transcript, not a re-rendering

Each question runs in a fresh session (follow-ups excepted, below), so that session's checkpoint
holds exactly the messages this question produced. The harness records the content of every tool
result message in that transcript, through **one public read on `AskAgent`** beside
`conversation_length` and `conversation_tokens`, returning the tool results a session was shown
without exposing the checkpointer.

*Alternative rejected:* rebuild the context from the entry identifiers in `Retrieval` events. It
would need the tools' private rendering, would drift from it silently the first time the rendering
changed, and cannot reproduce what a `list_values` call or a "No entries matched" reply showed the
model. The spec requires what the agent was shown, and the transcript is the only source that is
that by construction.

### One session per question; follow-ups share their parent's session

A question set entry may name the question it follows. The driver asks a follow-up in the session
its parent used, which is how the existing task 9.5b (answers cite in full rather than referring
back) becomes measurable. Resumption treats a follow-up whose parent's result is missing as
missing itself, since its session would not exist.

### Records are append-only JSONL, and judgements are a second file

One record per question and repeat, appended as it completes (ADR-0220's format, and the design
`add-ask-agent` already recorded). Judgements are **not** written into the record: they go to a
sibling JSONL keyed by question, repeat and judge model, appended by a separate `judge` pass that
reads the records. The report joins the two.

This is what lets a judge be re-run or replaced for judge spend only, keeps the deterministic run
free of the judge's dependencies and failures, and makes "never combined into a single figure"
structural rather than a reporting convention.

### Stating a quantity is detected from two cheap signals, flagged on either

Refusal scoring needs to know whether an answer stated a quantity. Two signals: a citation parsed
by `citations.py`, and a numeral in the prose. An answer is "declined" only when neither is
present; either one marks a quantity stated. The rule over-flags — a refusal that says "I searched
for 2 wordings" would be marked — and that is the cheap direction: a wrongly flagged decline is a
line in a list someone reads; a wrongly passed fabrication is the failure the whole project exists
to prevent. The report lists every flagged unsupported question with its answer so the over-flagging
is visible and measurable, per the conventions on rules that classify.

### The judge is DeepEval's faithfulness metric behind a thin wrapper

`FaithfulnessMetric` is used as shipped: claims extracted from the answer, truths from the context,
one verdict and reason per claim. The wrapper subclasses DeepEval's model base to hand it the
project's `ChatOpenAI` through OpenRouter — the same provider path as the agent — honouring the
metric's structured-output schema argument via `with_structured_output`, and reads the provider's
cost figure from the response the way `spend.py` does, so judge spend is real and separate.
Telemetry is switched off in the wrapper before the import, because a guard in a README protects
only the reader who saw it.

The judge model is configuration, recorded on every judgement, defaulting to a model other than the
one under test.

*Alternatives considered:* openevals with autoevals' `Faithfulness` (two small packages, a LangChain
model as judge directly, per-statement verdicts) — a real option, rejected for wanting a hand-written
harness where DeepEval has one, and for lacking the context metrics the non-goals defer; RAGAS,
rejected on maintenance and compatibility as recorded in Context. An ADR records the choice.

### The judge is gated on agreement with the deterministic layer

The report computes agreement over results where both layers can speak: every fabrication (an
unsupported question answered with a quantity) should be judged unfaithful; every answer whose cited
entries are all expected and whose claims are all supported is an agreement. A judged-faithful
fabrication is a judge miss. Disagreements where the identifier layer is satisfied and the judge
finds an unsupported claim are the judge adding information, and are listed with the claim and
reason rather than counted against it. Below a configured floor the judged figures carry an
"unvalidated" mark on every line that shows them.

### Scoring functions are pure and mutation-tested

Identifier comparison, quantity detection, spread across repeats, and the agreement computation are
functions from records to figures, with no I/O. They are where a wrong answer looks right, so they
get fault seeding and a mutation-testing pass before the baseline is recorded, per the project's
testing conventions.

## Risks / Trade-offs

- **DeepEval's API moves.** The surface above was read from source and docs on 2026-09-03, not
  run. → First task verifies it against the installed version, and the wrapper is tested with a
  scripted judge so the harness's tests do not depend on the framework's prompts.
- **DeepEval registers pytest plugins.** Its install adds plugins that may alter collection or
  output of this project's suite. → Check the default `pytest` run is unchanged after `uv sync
  --extra eval`; disable the plugin with `-p no:...` in `addopts` if it is not.
- **Claim extraction sees citation markers.** `[[100002]]` inside a claim may be dropped, kept, or
  read as a number by the extractor. → Test on fixture answers; if markers distort claims, strip
  them for the judge only and record that the judged text differs from the answer.
- **Judge spend on a large set.** Each judged answer is several judge calls. → The `judge` pass is
  separate, resumable, and bounded by its own budget; the first baseline is judged on a sample.
- **The transcript read exposes checkpoint internals.** A public method returning tool results
  couples the harness to the message shape. → It returns plain text per tool result and nothing
  else; the shape is the agent's to keep, tested in the agent's suite.
- **`openai<3` pin avoided, but the `eval` extra still moves the lock.** → Lock with the extra and
  run the full default suite before and after; the diff of `uv.lock` is reviewed like code.
- **Over-flagged declines.** The two-signal quantity rule marks some genuine refusals as
  fabrications. → Listed for reading, counted, and the rule tightened only with both directions
  measured.

## Open Questions

- The default agreement floor. Start at 0.9 and revise once the first judged baseline shows what a
  competent judge actually achieves; a floor set before any measurement is a guess either way.
- The default judge model. Any capable model reachable through OpenRouter other than the one under
  test; chosen when the first judged run is configured, recorded on every judgement regardless.
