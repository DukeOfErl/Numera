## Why

The agent is non-deterministic and nothing measures it. Every tuning decision so far — the two
retrieval bounds, the prompt's wording, the choice of development model — was made from a handful
of hand-driven observations, and ADR-0260 records both bounds as chosen rather than derived. The
evaluation was specified in `add-ask-agent` as its `answer-evaluation` capability and task group 9,
and never built. Now is the moment because the thing to be measured has stopped moving: the agent,
both drivers and the corpus pipeline are complete, and `add-ask-agent` could not archive while group
9 sat unimplemented inside it (it has since archived, once this change took the group over).

This change is scoped by what each check costs to build rather than by whether it uses a model. The
recording layer — ask, record, resume, report — is needed by every measure and has no parser in it.
On top of it sit the checks that read only events, the citation set, the corpus and the question set:
which entries were cited against which were expected, whether the search named the organism and
property asked, the agent's own grounding warnings, refusals on questions the corpus cannot answer,
and whether a cited entry is a distant outlier among its peers. All of those are exact and cheap.

Two things are deliberately out. The **value and unit beside each citation** needs a parser over free
prose, and this project's record says that is where silent defects live; it is deferred with its text
drafted and a correction attached. The **judged faithfulness layer** is in, because reading the first
baseline's answers by hand is a cheaper and better calibration reference than a checker that does not
exist yet — which is the ordering ADR-0510 asks for, with the reference supplied by a person instead
of by the deferred parser.

## What Changes

- **Take over, unchanged in intent**, the `answer-evaluation` spec and task group 9 from
  `add-ask-agent`. No behaviour of the agent changes; this is a new adapter over the existing event
  port.
- **Build the deterministic harness the spec already described**: an explicit, versioned question
  set including unsupported and follow-up questions; an evaluation driver as the third adapter over
  the agent; scoring by cited entry identifiers against expected ones; refusal scoring; repeats with
  the spread reported; results appended as each question completes, resumable, reported per model,
  with cost and effort.
- **Flag a cited entry that disagrees with its peers** — a distant outlier among the entries for the
  same property and organism — reported for reading rather than scored. This needs no reading of the
  answer's prose, and it catches the one failure every citation-checking measure passes: an answer
  whose numbers are all correct and correctly attributed, leading with the one figure in the corpus
  that contradicts every other measurement of the same quantity.
- **Separate a selection failure from a search failure**: of the expected entries an answer did not
  cite, report those the agent retrieved and passed over apart from those it never retrieved.
- **Score the agent's own grounding warnings**: citations of unretrieved or unknown entries, and
  answers or refusals reached without any retrieval, including prose that claims a search that did
  not happen.
- **Record, on every result, the context the agent was actually shown** — the tool results it read,
  verbatim from the session checkpoint — so the judged layer can be added later for judge spend only.
- **Record what produced every result**: the model and its settings (reasoning effort, once it is a
  setting), the identity of the system prompt, the identity of the corpus asked, the code version
  and the time. A report breaks figures down by each of these rather than combining across them.
- **Tag questions** by what they exercise, so figures can be read per kind.
- Measure, not defend, the two retrieval bounds and the corpus's clean fraction — the two
  measurement tasks group 9 carried, unchanged.
- **Add the judged layer**: faithfulness scored per claim by an LLM judge through DeepEval, each
  claim carrying a verdict and a reason, recorded in a second file beside the deterministic results
  and never combined with them. Gated on measured agreement with the deterministic scoring, and with
  the first calibration coming from reading the baseline's answers by hand rather than from a
  checker that does not exist yet (ADR-0500, ADR-0510).

Not in scope, and deferred below with its text drafted: **the value and unit beside each citation**,
which needs a parser over free prose and is the most defect-prone thing this change could contain.
Also out of scope: alerting on cost drift between runs (this change produces the baseline it needs);
faceting the property field; the unit-table gaps found during review, which are a defect in
`units.py` and are being fixed on their own branch; and the shape of the answers themselves, which
belongs to the system prompt in `grounded-answering` and has its own change.

## Capabilities

### New Capabilities

- `answer-evaluation`: Score answers against a held-out question set with known answering entries.
  Covers the question set and its tags, citation-set scoring with passed-over entries separated from
  unretrieved ones, unsupported questions, the agent's own grounding warnings, a cited entry at odds with its peers, run-to-run variation, incremental
  recording and resumption, per-model reporting, cost and effort, the recorded context as shown to
  the agent, the provenance of every result, and a judged faithfulness layer with per-claim reasons
  that is gated on agreement with the deterministic scoring. Moved from `add-ask-agent`, where it was
  `ADDED` and never promoted, and extended here.

### Modified Capabilities

<!-- None. The agent's behaviour, its port and its limits are unchanged; the harness is a driver. -->

## Impact

- **`src/scinumbers_ask/`**: new modules for the question set, the evaluation driver and its
  records, the deterministic scoring (pure functions over events, citations and the corpus — no prose
  parser in this change), the judge wrapper, and the report and command. One public read on `AskAgent` for a session's transcript,
  beside the existing `conversation_length` and `conversation_tokens`, so the driver can record what
  the model was shown without reaching into the checkpointer.
- **`pyproject.toml`**: a `scinumbers-eval` console script, and a new `eval` extra carrying
  `deepeval` for the judged layer only — the deterministic layer needs nothing beyond `ask`.
  Verified 2026-09-03 against the current lock: `deepeval` 4.2.1 resolves, `ragas` 0.4.3 was rejected
  (unmaintained since February 2026, import failure against `langchain-community` 0.4, per-statement
  verdicts computed and discarded, and a pin of `openai<3`). ADR-0500 records the choice.
- **`tests/`**: the harness's own tests on doubles; fault seeding and mutation testing over the
  scoring module; the requirement-to-test mapping in `tests/test_spec_conformance.py`, which lists
  this capability's requirements as gaps until the harness exists.
- **Docs**: `README.md` (how to run an evaluation and read its report), `docs/diagrams/architecture.md`
  (the third adapter), `CLAUDE.md` (module table; the ADR block `0500`–`0550` is allocated to this
  change), `CHANGELOG.md`.
- **Runtime state**: results under `eval-results/`, already ignored.

## Deferred

Recorded here so the follow-up starts from a draft rather than a memory. Each item says what would
trigger raising it again.

### The value and unit beside each citation

Drafted in full, and the text is in this repository's history at commit `75d8767` in this change's
spec file. In summary: read every quantity in the window before each citation marker, compare it with
what the cited entry records, and report per citation whether all match, some match, one matches only
under a power-of-ten rescaling, none match, or none was found — with what counts as a match depending
on the entry's shape, and with the unit beside each quantity checked through the three-valued
dimensional comparison.

**Why it is deferred.** It is a parser over free prose, and `cleaning.py` is this project's standing
lesson about that class of code: seven review passes, fault seeding and mutation testing each found
more defects, and every one produced a plausible number rather than an error. Building it before a
single real answer has been read means designing for failures nobody has seen. The first baseline
will say how often a stated value is actually wrong, which is the evidence this check should be sized
against.

**A correction to carry into it, not into a later task.** The drafted text counts any quantity inside
an entry's recorded range as a match. Review on 2026-09-04 showed that is too generous, because a
range in this corpus means at least three different things and nothing in the record distinguishes
them: genuine variation with growth rate or cell-cycle phase (*E. coli* ribosome counts, 6,800 to
72,000); a standard deviation rather than a minimum and maximum (yeast nuclear volume, whose interval
of 2.0 to 3.8 is an SD, said so only in the entry's free text); and ordinary measurement uncertainty.
Containment also let a specimen answer pass by quoting a mean that appears in an entry's free-text
note and in none of its value fields. Settle what a range means before implementing this, and prefer
an endpoint match over containment wherever the kind of range is unknown.

**Raise this again once the first baseline has been read by hand** — that reading, not a date, is
what says whether wrong values are common enough to justify the parser.

### Further metrics, and which need a judge

Asked for during review, sorted by what can score them. The deterministic ones could join this change
cheaply if the first baseline shows a need. The judged ones are additional rubrics over the judge this
change does build, and each one multiplies judge spend, so they wait until the faithfulness judge has
passed its agreement gate.

Scorable without a model:

- **Declared computation.** A number in the answer matching no cited entry's value or range (and not
  a rescaling of one) must sit beside wording that says it was computed or converted, and its inputs
  must be cited — rule 5 of the system prompt. A lexical check that over-flags; listed for reading.
- **Unit uniformity.** Whether every quantity of one kind in an answer is stated in one unit. Needs
  the deferred quantity reader above.
- **Conciseness, as a distribution.** Words per answer and words per cited entry, reported as a
  spread rather than thresholded; a change that doubles answer length shows up without anyone
  having decided what "too long" is.
- **Length of the search.** Retrievals and model calls per question, already recorded; the
  bound-measurement task reads them.
- **Corpus coverage for the question asked.** Review turned up a field the corpus does not cover at
  all: no planarian appears among its 841 organisms, and "neoblast" appears in no entry. A question
  set cannot test what the corpus lacks, so reporting coverage per organism and property would say
  where a refusal is the only correct answer — and would stop a future set being read as
  representative when whole fields are missing.

Needing a judge, each a rubric over the answer with the cited entries' fields as context:

- **Scientific caution.** Caveats a limited search; says "could not find" rather than "does not
  exist"; does not present one entry as the value when several disagree.
- **Contrast of conditions.** When several entries are cited, whether the prose says what
  distinguishes them — organism, method, condition — and whether that accounts for the difference in
  values. Rule 4 of the system prompt.
- **Flaws surfaced.** Whether the prose notes what the drivers already mark deterministically: a
  range spanning orders of magnitude, no measurement method, a bound reported as a point. The mark is
  a corpus fact; whether the answer mentions it is a judgement.
- **Answer relevancy.** Whether the answer addresses the property and organism asked, rather than a
  neighbour the search happened to return.

**The price of many metrics, and how to choose.** Each judged metric costs judge spend on every
answer, adds a noisy instrument whose variance on a small question set can outweigh the effect being
measured, and adds a rubric that drifts with the judge model. A weighted overall score would hide a
regression in one metric behind improvements in others, which is why this project reports figures
apart and never combines them. Choose a metric by three questions: does it map to a requirement the
system is actually held to (the five prompt rules are the first list); has the failure it detects
been seen live, or is it hypothetical; and can it be validated against something deterministic or a
human label. A metric that fails all three is a number nobody will act on. **Raise this again when a
live failure is seen that nothing above measures**, and when the first judged baseline shows how
much variance one judged metric already carries.
