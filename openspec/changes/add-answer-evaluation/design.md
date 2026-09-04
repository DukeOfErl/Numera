## Context

See `proposal.md` — Why. The requirements are in `specs/answer-evaluation/`; the harness drives
the agent through the port in `openspec/specs/agent-session/` and changes nothing in
`grounded-answering` or `spend-control`.

What is already there and shapes the approach:

- **The port is complete for a driver's needs.** `ask()` yields `Retrieval` events carrying the entry
  identifiers each search returned, `AnswerEntries` carrying cited and retrieved identifiers,
  `UngroundedRefusal` (with `claimed_searching`), `CitationWarning` (with `unknown` and
  `unretrieved`), and a `QuestionEnded` naming the reason, the spend, the model, and the counts
  against every bound (ADR-0180). The harness records; it does not judge what the agent should have
  emitted — and several of the scores this change adds are those events read as scores.
- **The citation parser is shared.** `citations.py` is the one parser of `[[nnnnnn]]`, used by both
  drivers (ADR-0410), so the harness's notion of "what was cited" is the same as the page's.
- **Unit compatibility is three-valued** (`units.py`, ADR-0160): compatible, incompatible, unknown.
  Review on 2026-09-04 found real gaps in its table — `kDalton` and `ribosomes/cell` are unclassified,
  so a mass compared against a length returns unknown rather than incompatible. Those are a defect in
  `units.py` and are being fixed on their own branch, not here; this change does not depend on them,
  since it no longer compares units beside quantities.
- **The corpus holds the figures, and most entries are incomplete.** `Entry` carries `value`,
  `range_low`, `range_high` and `units`, plus the flags that describe its shape (`range_fused`,
  `range_approximate`, `range_one_sided`) and a `hedge` reading, so a cited value can be checked
  against the corpus without the question set recording it — and what "correct" means for a citation
  depends on that shape. Roughly two thirds of the corpus lacks at least one of a scalar value, a
  classified unit, an unfused range or a measurement method (the clean-fraction figures in task 5.4),
  so the incomplete shapes are the common case, not the edge.
- **The repository resolves organisms.** `CorpusRepository` turns an organism term into the stored
  organism values it refers to — abbreviated binomials via an alias index (ADR-0130), then substrings
  — and matches a property by substring. Whether the agent searched for the asked organism has to be
  judged with the same resolution, or "E. coli" would be scored as not "Escherichia coli".
- **Spend is already a run-level figure.** `run_ledger` keys spend on the configured run label, so a
  driver opening a session per question is bounded by one budget, and `QuestionEnded.reason ==
  RUN_BUDGET` is how the harness learns the run must stop.
- **The dependency direction is enforced by a test.** `tests/test_driver_independence.py` asserts
  the core never imports a driver. The harness is a driver and must be added to that assertion.
- **Reasoning effort is not yet a setting.** Nothing in `config.py` configures it, so the record
  carries the model settings that exist and gains reasoning effort when it becomes one; the record
  shape must not need changing for that.
- **The ask side never reads the corpus manifest.** The ingester writes one beside the corpus, but
  `corpus.py` loads the JSONL alone. The harness fingerprints the corpus file itself.

## Goals / Non-Goals

**Goals:**

- A third adapter over the unchanged agent, runnable unattended, that leaves a readable record
  after any interruption and can be reported on at any point.
- Every deterministic score exact and free of prose parsing, with the cheap error direction chosen
  and stated wherever a rule classifies.
- A judged faithfulness layer whose per-claim reasons are the product, kept structurally apart from
  the deterministic figures, and validated against hand labels before its numbers are read.
- A record shaped so the judge, and any later judged metric, costs judge spend only.

**Non-Goals:**

- **Reading numbers out of the answer's prose.** The value-and-unit check is deferred with its text
  drafted and a correction attached; see the proposal.
- Judged metrics beyond faithfulness. Available in the same framework and listed in the proposal;
  each multiplies judge spend, so they wait for the agreement gate.
- Changing the agent in response to findings. The baseline this produces is the input to those
  changes; they are their own work packages.
- A general evaluation platform, dashboards, or comparison between runs beyond what the report
  states.

## Decisions

### The harness is a driver, in the package

Modules beside `cli.py` and `web.py`, named for what they hold: the question set and its loader;
the driver that asks, records and resumes; the deterministic scoring as pure functions; the report;
and the command. No new dependency.

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
its parent used, which is how "answers cite in full rather than referring back" becomes measurable.
Resumption treats a follow-up whose parent's result is missing as missing itself, since its session
would not exist.

### Records are append-only JSONL, shaped for a second file of judgements

One record per question and repeat, appended as it completes (ADR-0220's format, and the design
`add-ask-agent` already recorded). The record carries the raw material — answer, cited, retrieved
and expected identifiers, verbatim context, the agent's warnings, the ending's counts, provenance —
and the scores derived from it, so a reporter can recompute a score from the raw fields when a
scoring rule changes without re-asking. Judgements, when they come, go to a sibling file keyed by
question, repeat and judge model; the record does not reserve a field for them.

### The value-and-unit check is deferred, and why the reasoning is kept

The design for it was worked out in full and is in this repository's history at commit `75d8767`:
read every quantity in the window before a citation marker rather than only the last one, because
real answers put a value and its conversion, or a range and a typical value, before one marker; let a
run of consecutive markers share a window; and let what counts as a match depend on the cited entry's
shape, since bare is correct where the entry records no number at all.

It is out of this change because it is a parser over free prose. `cleaning.py` is the standing lesson:
seven review passes plus fault seeding plus mutation testing each found more defects, and every one
produced a plausible number rather than an error. Designing a second such parser before any real
answer has been read means designing for failures nobody has observed.

**What replaces it here is not a weaker version of it but a different question.** The outlier check
below asks whether a *cited entry* disagrees with its peers, which needs no prose at all, and it
catches the specimen that every value check would have passed. The hand-labelling task in group 5
covers the rest, and produces the count that says whether the parser is worth building.

The correction that must travel with the deferred design — that containment inside a recorded range
is too generous, because a range in this corpus is sometimes real variation, sometimes a standard
deviation, and sometimes measurement uncertainty, with nothing distinguishing them — is recorded in
the proposal beside the deferred item rather than here, so whoever picks it up reads it before
copying the draft.

### The asked organism and property are checked against the search and against what was cited

The question set records the property and organism asked, in the corpus's vocabulary. Two scores
per question, kept apart because they fail differently. *What the agent asked for:* whether any
`Retrieval`'s `organism` argument resolves — through a public resolution method on the repository,
the same one `search` uses — to the asked organism, and whether any `property` or `keyword`
argument matches the asked property the way `search` matches one. *What it settled on:* the
fraction of cited entries whose `organism` and `property` fields carry the asked ones. An agent can
search correctly and cite a neighbour, or never search for the organism and still cite the right
entry through a keyword; the two scores tell those apart.

*Alternative rejected:* a judge for relevancy. It is in the deferred list for the prose; but whether
the search named the organism and whether the cited entries carry it are facts on record, and a
judge would be a weaker instrument for a question that has an exact answer.

### The outlier check compares entries, never prose

For each cited entry, gather the other entries sharing its property and organism, and ask whether the
cited one's value sits far outside them. Inputs are the citation set and the corpus; the answer's text
is never read. That is what makes it cheap, and it is why it survives in a change that has no parser.

Comparison over a spread rather than a mean, and reported rather than scored. These populations are
small — nine entries for yeast nuclear volume — and skewed, so a standard-deviation test would be
driven by the outlier it is meant to find. A ratio against the median of the peers is the starting
form, with the threshold an open question below. Where a property has fewer than a stated number of
peers, nothing is reported and the report says the comparison could not be made, rather than staying
silent in a way that reads as a pass.

Not scored against the answer, because an outlier is a fact about the corpus: the entry may be
measuring something its neighbours are not, which is exactly the yeast case where one entry gives
10.3 μm³ against eight others between 1.76 and 3.3. What the check buys is that the figure appears
in a list a person reads, next to the interval its peers occupy.

### The question set is composed by entry shape

Each expected entry's shape is derived from the corpus at evaluation time, never hand-recorded:
complete, or lacking a scalar, a classified unit, an unfused range, a method, or carrying a hedged
range. The set's validation requires every shape to be present, and the report gives every value
figure per shape. Happy-path questions target complete entries; the others score the behaviour the
prompt's rules ask for on incomplete ones — a bare citation where the entry gives no number, a
qualified figure where the range is hedged, the unit carried verbatim where it is unclassified.

### Stating a quantity is detected from two cheap signals, flagged on either

Refusal scoring needs to know whether an answer stated a quantity. Two signals: a citation parsed
by `citations.py`, and **any digit** in the prose — a character test, not a number parser, which is
what keeps this group free of the deferred reader. An answer is
"declined" only when neither is present; either one marks a quantity stated. The rule over-flags —
a refusal that says "I searched for 2 wordings" would be marked — and that is the cheap direction: a
wrongly flagged decline is a line in a list someone reads; a wrongly passed fabrication is the
failure the whole project exists to prevent. The report lists every flagged unsupported question
with its answer so the over-flagging is visible and measurable.

### The agent's warnings are scores, read from events

`CitationWarning.unretrieved` and `.unknown`, and `UngroundedRefusal` with `claimed_searching`, are
recorded from the event stream and scored as the spec's grounding failures. The harness computes
nothing here; it counts what the agent already established about itself. "Passed over" is
`expected ∩ retrieved − cited`, from `AnswerEntries`.

### Provenance is recorded from what the run can see, not declared

Per result: the model name from `QuestionEnded.model`; every model setting `Config` carries (and
reasoning effort as soon as `Config` does); a digest of the system prompt text, since a reworded
prompt moves every figure and the prompt has no version of its own; a digest of the corpus file plus
its entry count, computed once per run; the code version as the git commit when the working tree is
a repository, else the installed package version; and the time in UTC. A report groups by model,
prompt digest and corpus digest and refuses to combine across any of them.

*Alternative rejected:* a run-level header record carrying provenance once. A resumed run may cross
a corpus rebuild or a prompt edit, and per-result provenance is what makes that visible rather than
silently mixed.

### The judge is DeepEval's faithfulness metric behind a thin wrapper

`FaithfulnessMetric` is used as shipped: claims extracted from the answer, truths from the recorded
context, one verdict and reason per claim. The wrapper subclasses DeepEval's model base to hand it the
project's `ChatOpenAI` through OpenRouter — the same provider path as the agent — honouring the
metric's structured-output schema argument, and reads the provider's cost figure the way `spend.py`
does so judge spend is real and separate. Telemetry is switched off in that module before the import,
because a guard in a README protects only the reader who saw it. The judge model is configuration and
is recorded on every judgement, defaulting to a model other than the one under test.

Judgements go to a second JSONL keyed by question, repeat and judge model, written by a pass that
reads the results file. That is what makes replacing or re-running a judge cost judge spend only, and
it makes "never combined into one figure" structural rather than a reporting convention.

*Alternatives considered:* openevals with autoevals' `Faithfulness` (two small packages, a LangChain
model as judge directly, per-statement verdicts) — a real option, rejected for wanting a hand-written
harness where DeepEval has one; RAGAS, rejected on maintenance and compatibility. ADR-0500 records it.

### The judge is calibrated against hand labels, not against the deferred parser

ADR-0510 requires the judge be validated against something before its figures are read. The reference
was going to be the deterministic value check. With that deferred, the reference is the hand labels
from group 5.4: every answer in the first baseline read and marked by a person.

This is better rather than merely available. Twenty answers can be read in an hour, which is cheaper
than the parser; a person catches faults nobody specified, which is the whole reason for the reviewer
exercise; and it removes the circularity of validating one automated instrument against another whose
own error rate is unmeasured. What the deterministic layer still supplies is the hard cases where it
cannot be wrong: a fabrication on an unsupported question must be judged unfaithful, and a
judged-faithful fabrication is a judge miss.

### Scoring functions are pure and mutation-tested

Identifier comparison, the quantity reader and value comparison, quantity detection, spread across
repeats, and the per-group breakdowns are functions from records to figures, with no I/O. They are
where a wrong answer looks right, so they get fault seeding and a mutation-testing pass before the
baseline is recorded, per the project's testing conventions.

## Risks / Trade-offs

- **No check reads the numbers in the answer.** A wrong value beside a right citation passes every
  deterministic measure in this change. → The judge sees it, the hand labels in 5.4 count it, and that
  count decides whether the deferred parser gets built.
- **DeepEval's API moves, and its prompts are its own.** The surface was read from source and docs on
  2026-09-03, not exercised, and a release can shift judged figures with no change here. → Task 6.2
  verifies it against the installed version; the wrapper is tested against a scripted judge; every
  judgement records the judge model.
- **The outlier threshold is a tuning knob.** Set too tight it flags every legitimate
  method-dependent difference. → Reported and never scored, so a false flag costs a line someone
  reads; both directions counted in 4.10.
- **Organism resolution is the repository's, not the biologist's.** A question asking about "yeast"
  resolves to whatever organism strings contain it. → The set records the organism in the corpus's
  own vocabulary, and the listed misses show where the resolution, not the agent, is at fault.
- **The organism check flags a deliberate contrast as a mistake.** An answer that cites a
  different-organism entry precisely to rule it out is indistinguishable, to this check, from one that
  substituted it. Seen twice in the reviewer specimens. → Reported with the entry named so a reader
  can tell; a candidate for the judge rather than for a tighter rule.
- **Rescaling hides a real error.** A ×1000 mistake looks like a µm→nm conversion. → Rescaled
  matches are never counted as matches; they are a list to read.
- **Over-flagged declines.** The two-signal quantity rule marks some genuine refusals as
  fabrications. → Listed for reading, counted, and tightened only with both directions measured.
- **The transcript read exposes checkpoint internals.** A public method returning tool results
  couples the harness to the message shape. → It returns plain text per tool result and nothing
  else; the shape is the agent's to keep, tested in the agent's suite.
- **Provenance from git.** The code version is unavailable in an installed wheel. → Fall back to
  the package version and say which was used.
- **A first question set is small.** Spread across repeats on twenty questions is a coarse
  instrument. → The report states coverage and repeat count beside every figure; no threshold is
  set on the first run.

## Open Questions

- The outlier threshold and its comparison form. A ratio against the peer median is the starting
  point; the value comes from running 4.5 over the first question set and reading both directions, not
  from a figure chosen now.
- How few peers is too few to judge an outlier at all.
- The agreement floor for the judge. Start at 0.9 against the hand labels and revise once 6.7 shows
  what a competent judge actually achieves; a floor set before any measurement is a guess either way.
- The default judge model. Any capable model reachable through OpenRouter other than the one under
  test; chosen when the first judged run is configured, recorded on every judgement regardless.
