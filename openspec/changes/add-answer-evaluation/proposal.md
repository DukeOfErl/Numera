## Why

The agent is non-deterministic and nothing measures it. Every tuning decision so far — the two
retrieval bounds, the prompt's wording, the choice of development model — was made from a handful
of hand-driven observations, and ADR-0260 records both bounds as chosen rather than derived. The
evaluation was specified in `add-ask-agent` as its `answer-evaluation` capability and task group 9,
and never built. Now is the moment because the thing to be measured has stopped moving: the agent,
both drivers and the corpus pipeline are complete, and `add-ask-agent` could not archive while group
9 sat unimplemented inside it (it has since archived, once this change took the group over).

This change builds the layer that needs no model to score: exact comparisons between what an answer
cited and stated and what the corpus and the question set record. A right entry identifier beside
no quantity, or beside the wrong one, is a useless answer, so the identifier check is extended to
the value and the unit beside each citation; and the agent's own grounding warnings — a cited entry
it never retrieved, a refusal reached without searching — become scores rather than notes. The
judged layer (faithfulness with per-claim reasons, and the softer qualities below) is drafted in
the Deferred section and follows once this baseline exists, because a judge is validated against
this layer and cannot be trusted before it (ADR-0510).

## What Changes

- **Take over, unchanged in intent**, the `answer-evaluation` spec and task group 9 from
  `add-ask-agent`. No behaviour of the agent changes; this is a new adapter over the existing event
  port.
- **Build the deterministic harness the spec already described**: an explicit, versioned question
  set including unsupported and follow-up questions; an evaluation driver as the third adapter over
  the agent; scoring by cited entry identifiers against expected ones; refusal scoring; repeats with
  the spread reported; results appended as each question completes, resumable, reported per model,
  with cost and effort.
- **Extend the identifier check to the value and unit beside each citation**, against the corpus's
  own figures, reporting per citation whether the value matched as written, only under a rescaling,
  not at all, or was absent, and whether the unit was compatible, incompatible or unclassifiable.
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

Not in scope: the judged layer and every metric that needs a model (deferred below, drafted);
alerting on cost drift between runs (this change produces the baseline it needs); faceting the
property field; and any change to the agent's prompt or tools in response to what the evaluation
finds.

## Capabilities

### New Capabilities

- `answer-evaluation`: Score answers against a held-out question set with known answering entries.
  Covers the question set and its tags, citation-set scoring with passed-over entries separated from
  unretrieved ones, the value and unit beside each citation, unsupported questions, the agent's own
  grounding warnings, run-to-run variation, incremental recording and resumption, per-model
  reporting, cost and effort, the recorded context as shown to the agent, and the provenance of
  every result. Moved from `add-ask-agent`, where it was `ADDED` and never promoted, and extended
  here.

### Modified Capabilities

<!-- None. The agent's behaviour, its port and its limits are unchanged; the harness is a driver. -->

## Impact

- **`src/scinumbers_ask/`**: new modules for the question set, the evaluation driver and its
  records, the deterministic scoring (pure functions, including the quantity-beside-a-citation
  parser), and the report and command. One public read on `AskAgent` for a session's transcript,
  beside the existing `conversation_length` and `conversation_tokens`, so the driver can record what
  the model was shown without reaching into the checkpointer.
- **`pyproject.toml`**: a `scinumbers-eval` console script. No new dependency: the deterministic
  layer needs nothing beyond the `ask` extra. (The judged layer, when it comes, adds `deepeval`
  under its own extra; ADR-0500 records that choice and why RAGAS was rejected.)
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

### The judged layer: faithfulness with per-claim reasons

Drafted as six requirements, ready to become a follow-up change's delta on `answer-evaluation`
(their full text is in this repository's history at the commit that carved this change out,
`d768db2`, in this spec file). In summary:

- **Faithfulness is judged per claim, with a reason.** An answer stating a quantity is separated into
  claims, each judged against the recorded context, with verdict and reason recorded; a refusal is
  recorded as not judged. The reason is the product: it names the claim a user can be warned about
  and a developer can fix.
- **The judged layer is secondary and optional.** The report is produced in full with no judge;
  judged figures sit beside the deterministic ones and are never combined into one number.
- **A judge is trusted only after measured agreement** with the deterministic layer where both
  speak; a judged-faithful fabrication is a judge miss; disagreements are listed for reading, and
  judged figures carry an unvalidated mark below a stated floor (ADR-0510).
- **Every judgement records the judge model and its cost**, apart from the agent's.
- Built on DeepEval's `FaithfulnessMetric` behind a thin wrapper over the project's `ChatOpenAI`
  through OpenRouter, in its own `eval` extra, with telemetry switched off before the import
  (ADR-0500). Judgements go to a second JSONL keyed by question, repeat and judge model, so a judge
  can be re-run or swapped for judge spend only.

**Raise this again once the deterministic baseline is recorded (task 5.3)** — the floor the judge is
validated against does not exist before then.

### Further metrics, and which need a judge

Asked for during review, sorted by what can score them. The deterministic ones could join this change
cheaply if the first baseline shows a need; the judged ones wait for the layer above.

Scorable without a model:

- **Declared computation.** A number in the answer matching no cited entry's value or range (and not
  a rescaling of one) must sit beside wording that says it was computed or converted, and its inputs
  must be cited — rule 5 of the system prompt. A lexical check that over-flags; listed for reading.
- **Unit uniformity.** Whether every quantity of one kind in an answer is stated in one unit. Parsed
  from the same quantity-beside-a-citation reader this change builds.
- **Conciseness, as a distribution.** Words per answer and words per cited entry, reported as a
  spread rather than thresholded; a change that doubles answer length shows up without anyone
  having decided what "too long" is.
- **Length of the search.** Retrievals and model calls per question, already recorded; the
  measurement task 5.2 reads them.

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
