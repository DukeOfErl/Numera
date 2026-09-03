## Why

The agent is non-deterministic and nothing measures it. Every tuning decision so far — the two
retrieval bounds, the prompt's wording, the choice of development model — was made from a handful
of hand-driven observations, and ADR-0260 records both bounds as chosen rather than derived. The
evaluation was specified in `add-ask-agent` as its `answer-evaluation` capability and task group 9,
and never built. Now is the moment because the thing to be measured has stopped moving: the agent,
both drivers and the corpus pipeline are complete, and two open changes (`add-ask-agent` and
`rename-to-scinumbers`, which modifies its specs) cannot archive while group 9 sits unimplemented
inside the first of them.

This change carves the evaluation out into its own work package and adds one thing the original
spec anticipated but did not require: a second scoring layer that judges an answer's *claims*
against the context the agent was shown, and says which claim failed and why. Identifier scoring
catches an entry cited that should not have been; it cannot see a right citation beside a wrong
number, a computed figure presented as retrieved, or a range read as a point. A faithfulness critic
can, and its per-claim reasons are what a user could be warned with and what a developer would fix
from.

## What Changes

- **Move, unchanged in intent**, the `answer-evaluation` spec and task group 9 from `add-ask-agent`
  into this change. `add-ask-agent`'s own artifacts are edited only to point here. No behaviour of
  the agent changes; this is a new adapter over the existing event port.
- **Build the deterministic harness the spec already describes**: an explicit, versioned question
  set including questions the corpus cannot answer and follow-up questions; an evaluation driver as
  the third adapter over the agent; scoring by cited entry identifiers against expected ones;
  refusal scoring; repeats with the spread reported; results appended as each question completes,
  resumable, reported per model, with cost and effort.
- **Record, on every result, the context the agent was actually shown** — the tool results it read
  during that question, verbatim from the session checkpoint — not the corpus entries re-rendered.
  A judge fed entries the model never saw would score groundedness against material the agent did
  not have.
- **Add the judged layer**: faithfulness scored by an LLM judge through DeepEval, returning a score
  and, per claim, a verdict and a reason. Recorded beside the deterministic score, never in place of
  it; a report is producible with no judge configured.
- **Gate the judge on agreement** with the deterministic scoring before its figures are read as
  results, as `add-ask-agent`'s Deferred section already requires: a measured agreement floor
  against the golden set, with the disagreements listed for reading rather than averaged.
- **Record the judge model on every judgement**, for the same reason the answering model is
  recorded on every result: a change of judge must not read as a change in quality.
- Add `deepeval` as a separate optional extra so the `ask` install does not carry its dependency
  tail; the harness's deterministic layer needs nothing beyond what `ask` already has.
- Measure, not defend, the two retrieval bounds and the corpus's clean fraction — the two
  measurement tasks group 9 carried, unchanged.

Not in scope, and still deferred where `add-ask-agent`'s proposal left them: alerting on cost
drift between runs (this change produces the baseline it needs), faceting the property field, and
any change to the agent's prompt or tools in response to what the evaluation finds.

## Capabilities

### New Capabilities

- `answer-evaluation`: Score answers against a held-out question set with known answering entries.
  Covers the question set, citation-based scoring, unsupported questions, run-to-run variation,
  incremental recording and resumption, per-model reporting, cost and effort, the recorded context
  as shown to the agent, and a judged faithfulness layer with per-claim reasons that is gated on
  agreement with the identifier scoring. Moved from `add-ask-agent`, where it was `ADDED` and never
  promoted, and extended here.

### Modified Capabilities

<!-- None. The agent's behaviour, its port and its limits are unchanged; the harness is a driver. -->

## Impact

- **`src/scinumbers_ask/`**: new modules for the question set, the evaluation driver and its
  report, and the judge wrapper (the only module that imports `deepeval`, imported lazily so the
  deterministic layer runs without it). One public read on `AskAgent` for a session's transcript,
  beside the existing `conversation_length` and `conversation_tokens`, so the driver can record what
  the model was shown without reaching into the checkpointer.
- **`pyproject.toml`**: a new `eval` extra carrying `deepeval`; a `scinumbers-eval` console script.
  Verified 2026-09-03: `deepeval` 4.2.1 and `ragas` 0.4.3 both resolve against the current lock;
  RAGAS is not adopted (unmaintained since February 2026, import failure against
  `langchain-community` 0.4, per-statement verdicts computed and discarded) — recorded in an ADR.
- **`tests/`**: the harness's own tests on doubles; the judge wrapper tested against a scripted
  judge; a `network`-marked check of the real judge; the requirement-to-test mapping in
  `tests/test_spec_conformance.py`, which already lists this capability's requirements as gaps.
- **`openspec/changes/add-ask-agent/`**: `specs/answer-evaluation/` moves here; group 9 in its
  `tasks.md` is replaced by a pointer; its `proposal.md` and `design.md` note the move. Task 10.1
  (README: how to run an evaluation) and the group-9 part of 10.9 come with it.
- **Docs**: `README.md` (how to run an evaluation and read its report), `docs/diagrams/architecture.md`
  (the third adapter), `CLAUDE.md` (module table, and the ADR block `0500`–`0550` allocated to this
  change), `CHANGELOG.md`.
- **Runtime state**: results under `eval-results/`, already ignored. The judge spends money on a
  second model; its spend is reported separately from the agent's.
