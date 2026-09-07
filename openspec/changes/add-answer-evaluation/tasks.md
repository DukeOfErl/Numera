# Tasks

ADR block for this change: `0500`–`0550`, allocated in the table in `CLAUDE.md`, which is the
authority; this note is a convenience for whoever is implementing. `0500` (DeepEval over RAGAS) and
`0510` (a judge is validated against the identifiers) are written and are both in force for this
change. Widen in `CLAUDE.md` first if the change owes more.

**Read this before picking up a task.** The sequence is scoped by what each check costs to build, not
by whether it uses a model. Groups 1–3 are the recording layer that every measure needs. Group 4 is
every check that reads only events, the citation set, the corpus and the question set — exact and
cheap. Group 5 records the baseline **and reads its answers by hand**, which is the calibration
reference the judge in group 6 is gated against. The value-and-unit check is **not** in this change:
it is a parser over free prose, it is deferred in the proposal, and the correction it must carry is
recorded there rather than here.

## 1. Ground

- [x] 1.1 Add the `scinumbers-eval` console script and the `eval` extra (`deepeval`, for group 6 only)
      to `pyproject.toml`; review the `uv.lock` diff for what moved, `openai` in particular
- [x] 1.2 Add the harness's modules to the driver-independence test so the core is asserted never to
      import them
- [x] 1.3 Read `openspec/specs/agent-session/` as promoted, not the archived delta: it is the port the
      harness drives
- [x] 1.4 Confirm the default `pytest` run is unchanged after `uv sync --extra eval` — DeepEval registers
      pytest plugins — and disable its plugin in `addopts` if collection or output moves
  - **What the lock review found.** 93 → 129 packages, nothing removed, and exactly one version
    moved: `click` 8.4.2 → 8.3.3, pinned down by `typer` (which `deepeval` brings). `openai` stayed
    at 3.2.0 and so did every LangChain package, `pydantic` and `httpx` — the agent's stack is
    untouched, which is what task 1.1 was asking.
  - **Five pytest plugins arrive with DeepEval**: its own, plus `xdist`, `asyncio`, `repeat` and
    `rerunfailures`. Only its own changed anything — a "Running teardown with pytest
    sessionfinish..." line after every run, including runs that touch none of its code — and
    `-p no:deepeval` in `addopts` restores the output exactly. Collection was never affected: 919
    selected and 35 deselected before and after.
  - **`uv sync` pruned `mutmut`, `textual` and `setproctitle` from the venv**, because they were
    installed ad hoc and are in no extra or group. Nothing here needs them, but a mutation run does:
    reinstall before reaching for the `mutation-test-module` skill.

- [x] 1.5 Run an adversarial code review of the branch before merging it, and act on what it
      finds in the same branch. **Not optional and not a formality**: the review of groups 1-2
      found a reproducible crash, a shape that called a hedged value complete, a format that
      could not express a question kind the spec requires, and a conformance mapping that
      over-claimed — all in code that had already passed fault seeding and mutation testing

## 2. The question set

- [x] 2.1 Define the question set format (JSONL, ADR-0220): identifier, question, the property and
      organism asked in the corpus's vocabulary, expected entry identifiers, unsupported flag, the
      identifier of the question it follows, tags, and free notes. Require one to be supplied and fail
      with an explanatory message without one
  - Include questions that separate an object from its measure — a volume asked of two different objects,
    a size asked where only a diameter exists, E. coli's nucleus. `add-ask-agent`'s Deferred section,
    *Faceting the property field into object and measure*, turns on the failure rate these measure.
- [x] 2.2 Validate unsupported and follow-up questions in the format, and reject a follow-up naming a
      parent the set does not contain
- [x] 2.3 Derive each expected entry's shape from the corpus at load time — complete, or lacking a scalar,
      a classified unit, an unfused range, a method, or carrying a hedged range — and have validation
      require every shape to be present in the set, reporting which are missing
  - **The six-entry fixture corpus can never satisfy this check**: it holds two of the six shapes
    (`no scalar value`, `no measurement method`) and no complete entry at all. So the passing path is
    tested against constructed `Entry` objects, and `check_against_corpus` is exercised through the
    command only in its refusing direction. The first real question set (5.1) needs a real corpus.
  - Fault-seeded over `question_set.py` in an isolated copy: five realistic defects — a boolean read
    as entry 1, an unknown key ignored, an entry with a range counted as having a scalar, shape
    coverage read from the corpus instead of the set, a follow-up with no parent accepted — and each
    was caught by the test written for it. No survivors.
  - **Mutation-tested too, and it found what seeding could not.** 272 mutants, 35 survivors on the
    first pass. Every *location* argument could be replaced with `None` — so every refusal could have
    read "None: question must be a string" with all 38 tests still green — and the duplicate-id
    message counted questions rather than lines, which diverge the moment the file holds a blank
    line. Both are fixed and tested; 264 mutants now, 11 survivors, all message prose or the
    `encoding="utf-8"` pair, recorded as accepted in the test module's docstring. Seeding could not
    have found either: both were things nobody had a belief about. Re-run after the branch review
    reworked the module: 327 mutants, 10 survivors, all message prose or a codec alias. The rework's
    own new paths arrived with unasserted messages, so a second run after a substantial change earns
    its four minutes.

**What the branch review of groups 1-2 left open** (2026-09-04). Everything else it found was
fixed on that branch; these were deferred deliberately, each to where the material for it exists:

- ~~**Nothing validates `unsupported: true` against the corpus.**~~ Done in 4.11, refusing on the
  conjunction of a resolved property and a resolved organism. The corpus check refuses a stale
  *supported* identifier and says nothing about a question wrongly marked unsupported. That is the
  expensive direction: the corpus answers it, the agent answers it correctly and cites, and the spec's
  own scenario scores that as a **fabrication** -- the evaluation's headline figure, wrong for the one
  reason no reader would suspect. Deferred to **4.11** rather than done in group 2, because deciding
  "the corpus cannot answer this" needs the repository's organism and property resolution, which 4.2
  wires up anyway; doing it earlier would mean a second, hand-rolled resolution.
- **`NO_METHOD` reads a field that also holds quotations.** `measurement_method` is half of
  `Entry.quotation_text` ("where curator quotations live"), and fixture entry 100001's method field
  holds a page reference, so `COMPLETE` includes entries whose method field carries a quotation and no
  method. This over-passes in the expensive direction. The fix wants a discriminator taken from real
  data, which is a measurement over a real corpus rather than a rule reasoned out here -- fold it into
  5.4, which already measures the clean fraction.
- **`spans_implausibly` is not a shape.** `Entry` already judges an entry unusable and
  `entries_table` marks it, yet an entry with a scalar value and an implausible span is `COMPLETE`.
  The spec lists five deficiencies and this is not one of them; raise it if 5.4 or the baseline shows
  such entries among the expected ones.
- **Shapes are derived per run and not recorded per result.** `units.dimension`'s table grows
  (`kDalton` was added on 2026-09-04), so the same entry can be `NO_CLASSIFIED_UNIT` one week and
  `COMPLETE` the next, and 4.8's per-shape breakdown would mix the two. 3.4's code version covers it
  in a checkout but not in an installed wheel.
- ~~**Nothing requires a parent to precede its child in the file.**~~ Answered in 3.2: `in_order`
  sorts parents before children, and the format still permits any order.
- **`-p no:deepeval` in `addopts` is global**, so group 6's DeepEval pytest integration
  (`assert_test`, its marker) is off for the whole suite. If 6.3 wants it, override `addopts` in that
  run and write the *whole* expression -- the same trap as `-m`.

- [x] 2.4 Review the branch before merging (see 1.5)

## 3. The driver and its records

- [x] 3.1 Add one public read on `AskAgent` returning the tool results a session was shown, as plain text
      per result, tested in the agent's suite against a scripted model
- [x] 3.2 Implement the evaluation driver: one session per question, a follow-up in its parent's session,
      outcomes recorded from emitted events, the run stopped when a question ends on the run budget
- [x] 3.3 Append each result as its question completes, carrying the question, answer, cited and
      retrieved entries, expected entries, the context shown, the agent's warnings (`CitationWarning`,
      `UngroundedRefusal`), the end reason, spend, and every count `QuestionEnded` carries. Record a failed
      question as a failure and continue
- [x] 3.4 Record provenance on every result: model and every `Config` setting that shapes an answer, a
      digest of the system prompt, a digest and entry count of the corpus file, the code version (git
      commit, else package version, saying which), and the UTC time
- [x] 3.5 Implement resumption against an existing results file, attempting only the questions and
      repeats not present; a follow-up whose parent is missing counts as missing
- [x] 3.6 Support repeating each question and record the repeat index on every result
  - Repeated runs are also the baseline a cost-drift alert would need. That alert is out of scope — see
    `add-ask-agent`'s Deferred section, *Alerting on cost drift* — and this task's output is what makes
    it possible.
  - **Two things came out of building this that were not in the plan.** Each `Retrieval`'s tool and
    arguments are recorded, because 4.2 scores the asked organism and property from exactly those and a
    record without them would mean re-asking the whole set to score it. And the recorded context
    distinguishes `null` from `[]`: the spec requires an empty context to be told apart from one that
    was not recorded, and collapsing them would make a harness fault look like proof the agent searched
    for nothing.
  - Fault-seeded over `evaluation.py` in an isolated copy: eight defects, seven caught. The survivor
    was resumption keyed on the question alone, ignoring the repeat — every resumption test ran at the
    default of one repeat, where the mistake cannot show. A run interrupted during the first repeat and
    resumed asking for three would have recorded one and reported it as three, against the requirement
    that variation is measured rather than averaged away. Note also that the *first* seed written for
    it was equivalent (it forced recorded repeats to 1, which is what they were) and passed for the
    right reason — a seed that survives is a claim about the seed until it is read.
  - The `run` subcommand landed with the driver rather than waiting for group 4: a driver with no
    caller cannot be run end to end, and the console script existed already.

- [x] 3.7 Review the branch before merging (see 1.5)

## 4. Scoring that needs no parser, and the report

Everything in this group reads events, the citation set, the corpus and the question set. Nothing here
reads a number out of the answer's prose, except 4.3, which only asks whether a digit is present.

- [x] 4.1 Score by comparing cited entries against expected entries, reporting unexpected citations
      separately rather than as errors, and splitting the expected entries not cited into retrieved and
      passed over versus never retrieved
- [x] 4.2 Score whether the agent searched for the asked organism and property — a public resolution
      method on the repository, the same one `search` uses, applied to each `Retrieval`'s arguments — and
      what fraction of cited entries carry the asked organism and property in their fields; the two
      reported apart
- [x] 4.3 Detect a stated quantity from two signals — a parsed citation, and any digit in the prose — and
      score an unsupported question as declined only when neither is present; a quantity given is a
      fabrication, reported apart from citation failures, with every flagged answer listed for reading.
      Deliberately a digit test and not a number parser: the cheap direction is to over-flag
- [x] 4.4 Score the agent's own warnings: unretrieved and unknown citations as grounding failures; a
      refusal with no retrieval as an ungrounded refusal apart from correctly declined; `claimed_searching`
      counted separately
- [x] 4.5 Flag a cited entry that is a distant outlier among the entries for the same property and
      organism, naming its value and the interval its peers occupy, reported for reading and not scored.
      Say in the code which comparison is used and why, and report nothing where a property has too few
      peers to judge
  - This is the check that catches an answer whose every number is correct and correctly attributed and
    whose headline is still the one figure in the corpus that contradicts all its neighbours. It needs
    only the citation set and the corpus. The threshold is an open question in the design.
- [x] 4.6 Score follow-up answers on whether they cite in full rather than referring back to an earlier
      answer
- [x] 4.7 Report the spread across repeats beside the aggregate, and report a question whose cited
      entries differ across repeats as unstable
- [x] 4.8 Produce the report from the results file: coverage stated when partial; figures per model, per
      prompt digest and per corpus digest, never combined across any of them, saying when the corpus
      differed; per tag and per entry shape on request; a run stopped on budget distinguished from a
      completed one; cost and tool calls per question and in aggregate; spend in this session apart from
      total spend across a resumed run; how often each ending carried `at_tool_bound`,
      `at_retrieval_bound` or `at_spend_ceiling`
- [x] 4.9 Fault-seed and mutation-test the scoring module before the baseline is recorded; it is where a
      wrong figure looks right
  - Fault-seeded: ten defects, eight caught by the test written for each, two survivors and both
    worth the trip. One showed that `correctly_declined`'s ungrounded-refusal clause is **redundant**
    against anything the agent can emit — `UngroundedRefusal` means no retrieval happened, so the
    retrieval count alone carries it. The clause stays, annotated, because scoring reads *files* that
    another tool or a hand edit can make inconsistent, and a test now covers that record.
  - The other survivor was the outlier comparison: a median-based rule passed every test, because
    the yeast population happens to give the same verdict either way. The distinguishing case is peers
    at 1, 1, 1, 1 and 10, where the median is 1 and a value of 5 sits inside the recorded range — now
    a test, and the reasoning is ADR-0520.
  - **A seed that fails to apply reads as a pass.** One seed's text did not match after the formatter
    reflowed it; the harness printed "56 passed" for a run against pristine source. The assertion in
    the seeding script is what caught it, and any such harness needs one.
  - **Mutation testing, done 2026-09-07: 338 mutants, 57 survivors on the first pass and most of them
    real** — which is the strongest evidence yet that the two instruments find different things.
    Fault seeding had passed over every one. `bounds_reached` had no direct test at all; each part of
    the provenance carried "never combine two runs" alone, so nulling any one merged runs that differ
    in it; the `property` key was read from a retrieval by a literal no test exercised; a one-sided
    range was never given to `representative_value`, which would have raised on it; `MIN_PEERS` was
    never tested at exactly the floor; and every `continue` in the peer functions could be a `break`,
    silencing the outlier check for everything cited after the first unjudgeable entry. It also found
    `Outlier.peer_median` — a field with no reader, left from the median form ADR-0520 rejected — now
    removed. 25 survivors left, all sentinel permutations or constructor fields the properties do not
    read; zero control-flow flips.
- [x] 4.11 Validate `unsupported: true` against the corpus, with the same resolution 4.2 uses: a
      question claiming the corpus cannot answer it, which the corpus can, scores a correct cited answer
      as a fabrication and becomes the evaluation's most-read number. Refuse rather than warn — a
      wrongly refused unsupported question costs one line of the set, a wrongly accepted one costs the
      headline figure — and count both directions. See the review note above group 3
- [ ] 4.10 On the first run, count both directions of every classifying rule (flagged declines, outlier
      flags, organism misses) and read them against the answers before trusting any figure
  - **Still open by design: it needs a real run.** Each rule now says in its own docstring which
    direction it errs and why, and each direction has a test, but a test proves the rule behaves as
    intended rather than that the intent was right. The three to count: the digit rule for a stated
    quantity (over-flags — a refusal mentioning any number is marked, and the same rule also drops it
    from the refusals-that-searched-first count, so two figures move together); the asked-property
    match (over-credits — a search for "Cell" agrees with an asked "Cell volume"); and the outlier
    factor of two over a tight interval (over-flags, ADR-0520).

**What the branch review of groups 3-4 found** (2026-09-07). Ten findings, all reproduced, all
fixed on that branch. Four are worth carrying forward as lessons rather than as history:

- **A results file holds corpus text**, because the recorded context is verbatim by requirement. The
  default path was not gitignored and nothing in the write path asked, so a `git add -A` after a run
  would have committed corpus excerpts — the one irreversible mistake this project can make. Fixed by
  importing the ingester's own guard (ADR-0250) rather than writing a second copy. **Any later
  artefact of a run — a judgements file, a hand-label file, an exported report — carries the same
  risk and needs the same guard.**
- **The append-per-result shape did not survive the interruption it was designed for.** A torn final
  line was tolerated on read and then concatenated with the next record, silently dropping a
  paid-for result and eventually making the whole file unreadable. Tolerating a partial read is only
  half the job; the write has to repair before appending.
- **A crashed question scored as a correct refusal**, and one refused on the run budget scored as a
  fabrication — its answer is the budget message, whose dollar figures contain digits. Scoring read
  `answer` and never `failure` or `end_reason`, so infrastructure failures moved the headline figure
  in the unfalsifiable direction. `reached_the_model` is now the scored population.
- **`--by-shape` crashed on every real results file** and no test caught it, because `Result` is
  unhashable once it carries a retrieval and every synthetic test record had none. A double that is
  simpler than the real thing in a load-bearing way hides the path it stands in for.

- [x] 4.12 Review the branch before merging (see 1.5). The review of groups 3-4 found ten
      defects, including a results file that would have committed corpus text

## 5. The baseline, and reading it

- [ ] 5.1 Assemble a first question set from the corpus, committed to the repository — it carries
      identifiers and wording, never entry text (ADR-0170). Happy-path questions on complete entries, and
      questions on each incomplete shape (2.3), chosen by querying the corpus for entries of that shape;
      the set's validation refuses a set missing one
  - The specimen questions on the reviewer page of 2026-09-04 are the seed: *E. coli* ribosome count and
    cell volume, ribosome size, the nuclear-volume question whose premise is wrong, budding yeast nuclear
    volume through the cell cycle, and a planarian question the corpus cannot answer at all.
- [ ] 5.2 Measure the two retrieval bounds rather than defending them. `TOOL_CALL_LIMIT` (20) and
      `RUN_CALL_LIMIT` (12) were both chosen from a handful of observations — answers that satisfied their
      question used about five retrievals, one runaway used twenty-nine — and neither has been reached in
      live use since. What the run should settle: whether either bound ever binds; whether the questions
      that reach one are the hard questions or the badly worded ones; and whether an answer produced at a
      bound scores worse than one produced with room to spare. A bound that never fires costs nothing and
      proves nothing, and a bound that fires on good questions is cutting answers short — the distribution
      tells them apart and no amount of argument does. See ADR-0260, which records both numbers as chosen
      rather than derived
- [ ] 5.3 Record a baseline on the development model, with repeats, and keep the report beside the ADRs
      that the figures bear on
- [ ] 5.4 **Read every answer in the baseline by hand and label it.** This is a task, not a review step:
      the labels are the reference the judge in group 6 is measured against, and they are also the only
      instrument that finds a fault nobody specified. Record, per answer, whether it is sound and what is
      wrong with it, in a file beside the results
  - It is also the cheapest way to size the deferred value check: count how often a stated number is
    actually wrong. If that is rare, the parser stays deferred.
- [ ] 5.5 Record what fraction of the corpus is clean, beside the answer baseline, so a citation rate is
      read against the base rate rather than as a failure: measurement method recorded, scalar value
      recorded, unit classified, range not fused. Report the four separately and the conjunction, and
      report it twice — once counting an unclassified unit as dirty and once as unknown — because that
      condition measures our dimension table's coverage, not the corpus's quality. Extend the
      `corpus`-marked reporting test rather than writing a script
  - **Do not carry the old figures forward.** 19.4%/34.6% of 14,294 entries was measured against a
    fused-range population of 1,222; the ingester's number lexer has since been corrected and the
    population is 1,445 records — 10.1% of the corpus, 23.5% of the 6,146 entries with a parsed range.
    This population has been measured three times, 1,716 → 1,222 → 1,445, and a flag is only ever as
    good as the tokenizer under it; keep that lesson in the report.

- [ ] 5.6 Review the branch before merging (see 1.5). Give the reviewer the *question set and the
      baseline* as well as the code: a set that measures the wrong thing is not a defect any test
      can see

## 6. The judged layer

Gated on group 5, and on 5.4 in particular: the judge is validated against the hand labels, not against
a checker (ADR-0510).

- [ ] 6.1 Implement the judge wrapper: DeepEval's model base subclassed over the project's `ChatOpenAI`
      through OpenRouter, honouring the schema argument via structured output, reading the provider's cost
      figure per call, telemetry switched off before the import. The only module that imports `deepeval`,
      and it imports it lazily so the deterministic layer runs without the extra
- [ ] 6.2 Verify the DeepEval surface against the installed version rather than the design: confirm
      `FaithfulnessMetric` exposes `.score`, `.reason`, `.claims`, `.truths` and `.verdicts[i].verdict/.reason`
      after `measure()`. Record what was verified and against which version in the module's docstring
- [ ] 6.3 Implement the `judge` pass: read the results file, judge each answer that states a quantity,
      record a refusal as not judged, and append one judgement per question, repeat and judge model —
      claims, verdicts, reasons, score, judge model, judge spend — to a second JSONL. Resumable against it
- [ ] 6.4 Test the wrapper and the pass against a scripted judge, so the harness's tests assert this code
      and not the framework's prompts; one `network`-marked check runs the real judge on a fixture answer
- [ ] 6.5 Check how claim extraction treats `[[nnnnnn]]` markers on the baseline's answers; if it distorts
      claims, strip them for the judge only and record that the judged text differs from the answer
- [ ] 6.6 Extend the report: judged figures beside the deterministic ones, never combined; per judge
      model; judge spend apart from the agent's; the report unchanged when no judgements file exists
- [ ] 6.7 Measure agreement against the hand labels from 5.4 and against the deterministic scoring where
      both speak; list every disagreement with its claim and reason; report a judged-faithful fabrication
      as a judge miss; mark every judged figure unvalidated while agreement is below the configured floor
- [ ] 6.8 Set the floor from what 6.7 shows, not from the design's placeholder, and write an ADR only if
      the reading changes a decision

- [ ] 6.8 Review the branch before merging (see 1.5). The judge is the component whose output a
      reader is least able to check, so brief the reviewer on the agreement gate specifically

## 7. Documentation and conformance

- [ ] 7.1 `README.md`: how to run an evaluation, resume one, judge one, and read the report — the task
      `add-ask-agent` deferred as 10.1
- [ ] 7.2 `docs/diagrams/architecture.md`: the third adapter in the modules diagram, following
      `docs/diagrams/DIAGRAMS.md`; the agent's graph is unchanged and needs no regeneration
- [ ] 7.3 `CLAUDE.md`: the new modules in the Architecture table, and the note that one module only
      imports `deepeval`
- [ ] 7.4 `CHANGELOG.md`: the harness, the judged layer, and the `eval` extra under Unreleased
- [ ] 7.5 `tests/test_spec_conformance.py`: map every requirement in `answer-evaluation` to the test that
      asserts it, retiring the gap entries this change added, in the same commits as the tests
- [ ] 7.6 Reconcile the ADR block against `CLAUDE.md` before archiving

- [ ] 7.7 Review the whole change before archiving: the specs against the code that claims to
      satisfy them, not only the last group's diff (see 1.5)
