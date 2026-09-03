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
  The value-and-unit check inherits that shape rather than inventing a binary one.
- **The corpus holds the figures.** `Entry` carries `value`, `range_low`, `range_high` and `units`,
  so a cited value can be checked against the corpus without the question set recording it.
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
- Every score in this change exact and model-free, with the cheap error direction chosen and
  stated wherever a rule classifies.
- A record that already carries what the judged layer will need — the verbatim context, the full
  answer, the provenance — so that layer costs judge spend only.

**Non-Goals:**

- Anything a model scores. Drafted in the proposal's Deferred section; follows this baseline.
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

### The quantity beside a citation is read from a window before the marker

The value check needs "the quantity stated beside this citation". The reader takes the text between
the previous citation marker (or sentence start) and this one, and extracts numerals with an
optional unit token: a number, an optional `×10^n` or `e` exponent, an optional range written with
a dash or "to", and the word or symbol that follows. The **last** quantity in the window is the one
attributed to the citation, since the prompt asks for the identifier after the quantity it
supports.

Comparison against the entry: a scalar within a relative tolerance of `value` (rounding to two or
three significant figures is normal), or within `[range_low, range_high]`; a stated range matching
the entry's endpoints within the same tolerance. If no match, retry at each power-of-ten rescaling
from 10⁻¹² to 10¹²; a hit there is "matches under rescaling", listed and not counted — the design's
statement of which error direction is cheap. Units compared with `units.py`'s three-valued check
between the token read and the entry's unit string.

*Alternatives rejected:* asking the question set to record the expected value (the corpus already
has it, and a second copy drifts); a windowless "any number in the answer" match (attributes a
neighbour's figure to the wrong citation and passes an answer that states the right number beside
the wrong entry); converting units with `pint` (in the validator's extra, not `ask`'s, and a
correct conversion is exactly what the rescaling tier reports without needing to be right about it).

This reader is a parser whose wrong output looks right, so it gets fault seeding and a mutation pass
before the baseline is recorded, and its two directions are both measured on the first run: how
many bare citations and mismatches it reports, read against the answers.

### Stating a quantity is detected from two cheap signals, flagged on either

Refusal scoring needs to know whether an answer stated a quantity. Two signals: a citation parsed
by `citations.py`, and a numeral in the prose, read by the same reader as above. An answer is
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

### Scoring functions are pure and mutation-tested

Identifier comparison, the quantity reader and value comparison, quantity detection, spread across
repeats, and the per-group breakdowns are functions from records to figures, with no I/O. They are
where a wrong answer looks right, so they get fault seeding and a mutation-testing pass before the
baseline is recorded, per the project's testing conventions.

## Risks / Trade-offs

- **The quantity reader is a heuristic over free prose.** It will attribute the wrong number to a
  citation in some sentence shapes. → Listed per citation with the window text, both directions
  counted on the first run, and the rule changed only with both measured.
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

- The relative tolerance for a value match. Start at 5 per cent and read the mismatches on the
  first run; a tolerance set before any answer has been read is a guess either way.
- Whether the question set should also record, per question, the property and organism asked, so
  the deferred relevancy metric has a reference. Cheap to add to the format now; decided when the
  first set is assembled (task 5.1).
