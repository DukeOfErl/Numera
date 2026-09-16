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
  - **Reworked by ADR-0530; see 4.13.** The four figures this task produced disagree about what
    `expected_entries` means — three read it as a required set, `unexpected` reads it as a floor —
    and the smoke run's remedy for the too-narrow lists would have broken the sound three to fix
    the one that was not hurting. What ships is the identifier comparison; what changes is which
    figure is the headline.
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
- [x] 4.10 On the first run, count both directions of every classifying rule (flagged declines, outlier
      flags, organism misses) and read them against the answers before trusting any figure
  - **Still open by design: it needs a real run.** Each rule now says in its own docstring which
    direction it errs and why, and each direction has a test, but a test proves the rule behaves as
    intended rather than that the intent was right. The three to count: the digit rule for a stated
    quantity (over-flags — a refusal mentioning any number is marked, and the same rule also drops it
    from the refusals-that-searched-first count, so two figures move together); the asked-property
    match (over-credits — a search for "Cell" agrees with an asked "Cell volume"); and the outlier
    factor of two over a tight interval (over-flags, ADR-0520).

  - **Counted 2026-09-16 over the 30-result baseline. Two predictions were wrong and the third was
    far worse than predicted.**
  - **The digit rule never fired alone.** 24 answers carried both a citation and a digit, 6 carried
    neither, **0 were digit-only**. The feared over-flag -- a refusal mentioning a number marked as
    stating one -- did not occur once; the six refusals contain no digits at all. Leave the rule
    alone: the risk is real in principle and absent here, and is worth re-counting on a set with
    numeric refusals rather than acting on now.
  - **The asked-property match over-credits almost always: 20 of 23 credits came from an argument
    that is not the asked property.** The worst case is exact -- `yeast-vs-ecoli-volume` repeat 1
    asked `Cell volume`, searched only `size` twice, reached **0 of 24** expected entries, and is
    credited with having searched for the asked property. It earns that on **one** shared stored
    property out of 492: *"Carbon:cell volume ratios ... in size-fractionated natural bacterial
    assemblages"* -- one entry in 14,294 whose wording contains both terms.
  - The overlap distribution is sharply bimodal -- 0.8%, 2.2%, 2.2%, 14.8% x3, then 100% x17, with
    **nothing between 15% and 100%** -- so any threshold from ~20% to ~99% gives the same answer. The
    strict form costs six credits: one plainly right to drop, five arguable, because
    `ribosome-diameter` searching `size` really does find 102320 *"Size of 70s (intact) of
    ribosome"*, an expected entry. **Two of the five are a fault in the set, not the rule**:
    `asked_properties` of `Nuclear` and `diameter` are single words where the question asks a
    compound property. Fix the set before tightening the rule.
  - **The outlier check judged nothing at all: 0 of 91 citations judged, 91 unjudgeable.** Not
    mostly -- all. Superseded by **ADR-0540**: peers become the question's own expected entries,
    restricted to the cited entry's organism and an identical unit string. That judges 56 of 91 and
    raises two flags, both surviving inspection, including 106356 -- the entry that motivated the
    check and that the old rule could never reach.
  - **A definition matched on unit *dimension* was measured and rejected**, and that is the finding
    worth carrying: it put `1.8e-15 Liter` beside `2.95 um^3`, both volumes, spanning fifteen orders
    of magnitude and destroying the lower bound. The project has dimensional compatibility (ADR-0160)
    and no unit conversion, so sameness of unit has to mean the same string.

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

- [x] 4.13 Rework the citation scoring to ADR-0530, over the raw material already recorded — no
      re-run is needed for any of it. The headline pass becomes *every expected entry reached the
      entries table* (expected ⊆ retrieved), renamed from `all_expected_cited` to say so; prose
      citation stays as a secondary figure. Add the rank of each expected entry within `rows_for`
      order as a continuous figure beside it, because "reached the table" passes an entry ranked
      fortieth and a ranking failure needs a different fix from a search failure. Read
      `admissible_entries` from the question set, not from the result record, so a borderline case
      found while hand-labelling costs nothing to add. Report a cited entry outside both lists as
      unexpected, as now
  - **Do not score a driver's truncation.** `TERMINAL_ROWS` is 5 in the CLI and the web's cut
    differs; scoring it would make one answer score differently depending on who asked (ADR-0110).
  - **Both directions, as 4.10 requires of any classifying rule.** Widening the expected set moves
    `passed_over` up by construction — a good answer cites four of nine — so count it before and
    after and check the increase is the benign kind rather than evidence the widening went too far.
  - **Done 2026-09-11, and the baseline was re-scored from the same file without re-asking** —
    which is the property the whole records-hold-no-scores shape was for. On the 30-result baseline:
    140 of 219 expected entries reached the table (64%), every one of them in 9 of 21 results,
    79 never retrieved, deepest expected entry at median rank 17 and worst 29. The old prose figure
    survives beside it at 74 of 219 (34%) — the same run, and the two numbers say different things.
  - **The admissible list immediately moved three citations out of "unexpected"** (17 → 14) on the
    baseline, which is the whole reason it exists: a citation outside both lists now means something.
  - **A question tier was added with it** (`basic` / `compound` / `declining`), because the aggregate
    hides the trade that matters: basic questions reached 90% and compound 24%, and a prompt change
    that searched harder for two-organism comparisons could move the 64% up while the simple
    questions — most of what anyone asks — got worse. A closed vocabulary, unlike tags: a tier is
    compared against the same tier in an earlier run, so a typo would open a bucket of its own.
  - **One regression caught by an existing test.** Filtering to results whose question the set still
    holds made every citation figure vanish for a results file that outlived its set, rather than
    saying so. The report now names the count and, where nothing is scorable, says that plainly.

- [ ] 4.14 **Moved to `add-judged-faithfulness`** (2026-09-16). A scoped claim of absence — an answer
      declining part of a question by saying the corpus holds nothing for it, while the corpus holds
      entries for exactly that part — is a defect in what the prose *asserts*, and reading prose for
      meaning is what the judged layer is for. A phrase list here would be brittle in both directions
      and superseded the moment that layer lands. The evidence is in
      `docs/evaluations/2026-09-11-baseline.md`; nothing catches it until then, which is accepted.

- [ ] 4.15 Implement ADR-0540's peer definition in `scoring.py`, replacing the property-string pool.
      The measurement is done (4.10); this is the code. Keep the factor of two and the floor of four
      peers -- only what counts as a peer changes -- and keep reporting the citations that could not
      be judged, because an absence reading as a pass is the failure this check exists to avoid
  - Both directions again once it lands: it can only flag an entry *in* the expected list, so one
    cited from outside it is never judged -- and an entry the set did not anticipate is exactly the
    kind most likely to be wrong. Count how many citations fall in that blind spot.

- [x] 4.12 Review the branch before merging (see 1.5). The review of groups 3-4 found ten
      defects, including a results file that would have committed corpus text

## 5. The baseline, and reading it

- [x] 5.1 Assemble a first question set from the corpus, committed to the repository — it carries
      identifiers and wording, never entry text (ADR-0170). Happy-path questions on complete entries, and
      questions on each incomplete shape (2.3), chosen by querying the corpus for entries of that shape;
      the set's validation refuses a set missing one
  - The specimen questions written for the review page of 2026-09-04 are the seed: *E. coli* ribosome count and
    cell volume, ribosome size, the nuclear-volume question whose premise is wrong, budding yeast nuclear
    volume through the cell cycle, and a planarian question the corpus cannot answer at all.
  - **Done: `question-sets/first-set.jsonl`, ten questions.** Committed inputs live in
    `question-sets/`; outputs live in `evaluations/`, which is gitignored — two directories rather than
    one, because a results file carries corpus text and a question set does not.
  - **Two things the corpus settled that the plan had wrong.** There is no flatworm anywhere in it, so
    *both* planarian questions are genuinely unsupported — one where neither term resolves, one where
    the property is common and only the organism is absent, which is the harder case. And *E. coli*
    **does** carry a nuclear-volume entry (100013, for the nucleoid), so the false-premise question is
    supported-with-a-caveat rather than unanswerable: the desired answer cites the entry and says a
    prokaryote has no membrane-bound nucleus. No deterministic check here can score that sentence,
    which is precisely why the question is in the set and tagged for the judged layer.
  - Guarded by `tests/test_first_question_set.py` (`corpus`-marked): a set can go stale three ways —
    a retired identifier, a shape it no longer exercises, an unsupported question the corpus has since
    learned to answer — and all three are silent, because the run still completes and the figures are
    simply about something else.
- [x] 5.1b Widen every question's expected entries to every spelling of the asked property, and add
      `admissible_entries` where a *different* property still answers (ADR-0530). **This is the one
      item that must land before 5.3**: expected entries are copied into each result at run time, so
      a list fixed afterwards does not repair the records it was scored into, and the only remedy is
      re-asking at cost. Everything else ADR-0530 asks for is recomputable at report time
  - Build the lists from the corpus vocabulary — `resolve_property` returns 14 spellings of
    "Nuclear volume" alone — and **never from what the agent cited in the smoke run**. Widening a
    set to what the system found makes it a set the system passes by construction.
  - Worked example, already measured: `yeast-nuclear-volume` lists 3 entries where 9 of the 52
    nucleus-mentioning yeast entries record a nuclear volume in volume units. Fractions, radii,
    diameters and surface areas are deliberately excluded — those are a different property, and the
    ones that still answer the question belong in `admissible_entries`.
  - The two lists behave differently on purpose and the reader needs telling: `expected_entries`
    freezes into each record, `admissible_entries` is read from the question set at report time so a
    borderline case found during 5.4 costs nothing. Extend `check_against_corpus` to validate the
    new list, and `tests/test_first_question_set.py` to keep it from going stale.
  - Each widened list is a hand judgement with no controlled vocabulary behind it, so a wrong one is
    invisible until someone reads an answer against it. That is what 5.6 asks a reviewer to do.
  - **Done 2026-09-11. The eight supported questions went from 24 expected entries to 91**, and the
    two unsupported ones are unchanged. Per question: ribosome count 7 → 10, the stationary-phase
    follow-up 1 → 2, *E. coli* cell volume 4 → 8, ribosome diameter 2 → 3, yeast nuclear volume
    3 → 9, yeast cell volume 3 → 17, the yeast-vs-*E. coli* comparison 3 → 24, the *E. coli* nucleus
    1 → 2. Three questions carry `admissible_entries`, five carry none.
  - **The spellings the old lists missed are the whole story.** "Volume of nucleus" and "Volume of
    nuclei during S phase" record the same property as "Nuclear volume"; "Size of 70s (intact) of
    ribosome" the same as "Diameter of 70S (intact) ribosome"; "No. of ribosomes per E. coli TG1"
    the same as "Number of ribosomes/cell". Not one of them contains the asked property as a
    substring, so `resolve_property` finds none of them and neither did the search that built the
    original lists.
  - **`ecoli-nucleus` rests on admissible entries alone, and that is a third state the format did
    not have.** Both nucleoid entries were first made expected, on the reasoning that 100013
    ("Nuclear (DNA+protein) volume", 0.16 um^3) and 107009 ("Volume of nucleoid", 0.2) are one
    property under two spellings. That was wrong about which list they belong in: nothing records
    the volume of an *E. coli* nucleus, because there is no such thing, so the question has no
    expected entry — and it is not unsupported either, since the corpus holds the nucleoid.
    Marking it unsupported would score the desired answer, which cites them and says the premise
    does not hold, as a failure to decline. So a question may now name admissible entries and no
    expected ones; the refusal that used to demand expected-or-unsupported now demands
    expected-or-admissible-or-unsupported, which keeps the "0 of 0 reads as a pass" protection.
  - **`admissible_entries` is kept deliberately narrow**, and the direction was chosen rather than
    fallen into: too generous and a genuinely off-topic citation goes unflagged, too narrow and a
    reasonable one is listed as unexpected — which is reported and never counted as an error. The
    cheap direction is narrow. So a radius, a diameter and a fraction-of-cell-volume are admissible
    for a volume question (one step, same object) and a surface area, a nucleus/cytoplasm ratio and
    a subunit's dimension are not.
  - **Two corpus oddities recorded rather than corrected.** 104441 and 104442 read as nitrifying
    bacteria from their wording ("with nitrite as oxidizer") but the corpus files them under
    *E. coli*; the set follows the corpus. And 103074 (the percentage increase in yeast cell volume
    on a shift to aerobic growth) is expected for the conditions question and deliberately excluded
    from the comparison question — the same entry, two questions, because it bears on how volume
    varies and not on which cell is bigger.
  - **Five seeded defects, five caught, after the harness was fixed.** The first run reported 0 of 5
    with identical timings, which is the signature of a harness testing the installed package rather
    than the copy; it now asserts the module's `__file__` is inside the copy and kills a canary
    before believing a pass. The one real survivor: `Question.__post_init__`'s refusal of
    `unsupported` with admissible entries is shadowed by the reader's, so nothing asserted the guard
    that holds for a caller building a set programmatically. Tested directly now.

- [~] 5.2 Measure the two retrieval bounds rather than defending them. `TOOL_CALL_LIMIT` (20) and
      `RUN_CALL_LIMIT` (12) were both chosen from a handful of observations — answers that satisfied their
      question used about five retrievals, one runaway used twenty-nine — and neither has been reached in
      live use since. What the run should settle: whether either bound ever binds; whether the questions
      that reach one are the hard questions or the badly worded ones; and whether an answer produced at a
      bound scores worse than one produced with room to spare. A bound that never fires costs nothing and
      proves nothing, and a bound that fires on good questions is cutting answers short — the distribution
      tells them apart and no amount of argument does. See ADR-0260, which records both numbers as chosen
      rather than derived
  - **First reading, from the smoke run: neither bound is close to binding.** 5.7 retrievals per
    question against a limit of 20; the most model calls any question used was 3 against 12. The
    second half of the question — whether an answer produced *at* a bound scores worse — cannot be
    answered yet, because no answer was produced at one. Repeats may change that; a harder set would.
- [x] 5.3 Record a baseline on the development model, with repeats, and keep the report beside the ADRs
      that the figures bear on
  - **A smoke run came first: ten questions, one repeat, $0.13, all answered, no failures.** Findings
    in `docs/evaluations/2026-09-07-smoke.md`. It proved the harness end to end and found four things,
    two of which must be settled before a baseline is worth recording:
  - **The outlier check cannot fire on this corpus, and never could.** Peers were the corpus's other
    entries with an *identical* property string for the same organism. Measured: 10,846 (property,
    organism) pairs carry a usable value, **zero** hold five or more entries, and 10,753 hold exactly
    one. `property` is free text, not a controlled vocabulary — `resolve_property("Nuclear volume")`
    alone returns 14 spellings. So the comparison form is wrong, not the factor, and **ADR-0520 needs
    superseding**. The measured alternative is the entries the question's property terms select,
    restricted to the cited entry's organism (pools of 4 to 44 here); the organism restriction is not
    optional, since one question's pool spans two organisms differing by an order of magnitude.
  - **The set's expected lists are too narrow, for the same vocabulary reason**, and this must be
    fixed *before* a baseline: expected entries are frozen into each record at run time, unlike a
    scoring rule, which the raw material lets us recompute. Fix it from the corpus vocabulary and
    **not from what the agent cited** — widening a set to what the system found is how a set becomes
    one the system passes by construction.
  - **Corrected 2026-09-11, ADR-0530: widening alone would have made the scoring worse.** The
    remedy above is right about the lists and wrong about what they then have to prove. Under the
    scoring as written, a widened list makes `all_expected_cited` unreachable — no good answer to
    the yeast nuclear-volume question cites nine entries — and fills `passed_over` with entries the
    answer sensibly declined. Widening is only sound together with the change of target: an
    expected entry discharges its obligation by reaching the **entries table**, not the prose. See
    4.13 for the scoring and 5.1b for the lists; do not do one without the other.
  - Two smaller findings, both real: `ecoli-nucleus` refused a question entry 100013 answers, having
    searched the organism and never a matching property; and a correct follow-up is reported as a
    grounding failure, because the agent's `unretrieved` warning means "not retrieved in *this*
    question" and a follow-up legitimately retrieves nothing.
  - **Recorded 2026-09-11: `docs/evaluations/2026-09-11-baseline.md`.** 10 x 3, $0.38, 30 of 30
    answered, no bound reached. 140 of 219 expected entries reached the table (64%) — but `basic`
    stands at 90% and `compound` at 24%, and the aggregate hides that entirely. Three findings to
    act on: compound questions fail on *search* (the two-organism comparison reached 0 of 24 on one
    repeat and 8 on the others); run-to-run variation is large enough that a single-repeat
    comparison of two prompts is noise (`yeast-nuclear-volume` went 2, 9, 9); and expected entries
    are landing at ranks 17 to 29 where the CLI shows five rows, which is a ranking failure and not
    a search one.
  - **The property search is the largest single lever, and it belongs to `add-ask-agent`.**
    `search` matches a property by substring on the whole argument, so a multi-word argument needs
    the stored value to contain that phrase verbatim: `"nucleus volume"` over yeast matches **1**
    entry and finds 0 of 9 expected, while `"volume"` matches 63 and finds all 9. The agent
    searching one word is the recall-preserving adaptation, not the defect. Matching on all terms
    present gives `"cell volume"` over *E. coli* 48 entries and 8 of 8 expected — full recall at
    half the noise. Stemming ("nucleus" against a stored "Nuclear") is a second step.

- [x] 5.4 **Read every answer in the baseline by hand and label it.** This is a task, not a review step:
      the labels are the reference the judge in group 6 is measured against, and they are also the only
      instrument that finds a fault nobody specified. Record, per answer, whether it is sound and what is
      wrong with it, in a file beside the results
  - It is also the cheapest way to size the deferred value check: count how often a stated number is
    actually wrong. If that is rare, the parser stays deferred.
  - **Three states, not two, and this was measured before the file was designed.** DeepEval's
    faithfulness verdict is `yes` / `no` / `idk`, so a binary label file could not be compared against
    it in 6.7 without collapsing a state arbitrarily — and the collapse would not show up in the
    agreement figure. Label on the same three states. Design: *What DeepEval's faithfulness metric
    actually returns*.
  - **Done 2026-09-16, and the result is that faithfulness is the wrong axis to gate the judge on.**
    30 of 30 labelled by hand: **29 sound, 1 unsound, 0 unclear.** A judge answering "faithful" to
    everything agrees 97% of the time, so plain agreement in 6.7 would be a high number meaning
    nothing, and 6.8 cannot set a floor from it. **Do not treat the saturation as a pass** — it says
    the instrument does not discriminate here, not that the answers are good.
  - **The one `unsound` is a citation swap, and it is the case that discriminates.** Repeat 2 of
    `yeast-nuclear-volume` cites 101627 ("Restriction enzyme EcoRI catalytic rate", 3.8 1/min,
    organism Unspecified) for "2.83 μm³ during late anaphase", which is 105627. A digit
    transposition. The *number is right and is in the context* — from 105627, which was retrieved —
    so only the attribution is wrong, and a faithfulness judge that reads claims against context will
    very likely pass it. `unretrieved_citations` already flags it; 101627 was never retrieved.
    **Check the judge against this case specifically in 6.7**: it is the one answer in thirty where
    the deterministic layer and a faithfulness judge should disagree, and if the judge passes it the
    agreement figure will hide that it saw nothing.
  - **All three hand-written notes describe the same defect, and none of it is faithfulness**: the
    answer understates or misstates what the corpus holds. Two are the coverage claim of 4.14 — whose
    detector fires on exactly those two answers and on no other, with the six honest planarian
    refusals correctly left alone. The third is the citation swap above. The notes carried more
    signal than the labels, which is worth knowing before designing the next label file.
  - **What 6.7 should measure instead of agreement.** Agreement against a saturated reference is
    uninformative; what the labels can still support is (a) whether the judge passes the one citation
    swap, which is a yes/no about a known blind spot, and (b) whether the judge's disagreements fall
    on the answers the notes flag, which tests whether it sees the defect class that actually occurs
    here. Both are weaker than a correlation floor and both are honest; ADR-0510 required the floor,
    so **record the substitution as a decision rather than quietly weakening the gate**.
  - The deferred value-and-unit check stays deferred on this evidence: no answer stated a number that
    was wrong on its face. The one bad citation carried a *correct* number, which is the opposite
    failure and is not what a value parser would catch.
- [x] 5.5 Record what fraction of the corpus is clean, beside the answer baseline, so a citation rate is
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
  - **Measured 2026-09-07 over 14,294 entries**, and the warning above was right — none of the old
    figures survived. A method recorded: 49.9%. A scalar value: 42.5%. A classified unit: 46.1%. An
    unfused range: 90.1%. **All four: 13.9%** (1,983 entries). The other three with the unit set
    aside: 24.5% (3,497). The gap between those two is 10.6% — 1,514 entries that fail only on a unit
    spelling `units.py` does not know, which measures our dimension table and not the corpus. A
    citation rate has to be read against 13.9%, not against 100%.
  - The figures are printed by the `corpus`-marked test rather than pinned in an assertion: what they
    *should* be is a fact about the corpus, and a test that fixed them would fail every time the
    ingester improved. They go into a document beside the baseline when 5.3 records one.

- [ ] 5.6 Review the branch before merging (see 1.5). Give the reviewer the *question set and the
      baseline* as well as the code: a set that measures the wrong thing is not a defect any test
      can see

## 6. The judged layer — moved to `add-judged-faithfulness`

Deferred out of this change on 2026-09-16, and the reason is measured rather than preferred.
ADR-0510 requires a judge to be gated on agreement with the deterministic scoring against a golden
set. Task 5.4 built that set — 30 answers read by hand — and it came back **29 sound, 1 unsound, 0
unclear**. A judge answering "faithful" to everything agrees 97% of the time, so no floor can be set
from it, and building the judge against it would produce exactly what ADR-0510 exists to prevent: a
validated-looking figure resting on a validation that could not fail.

The second reason is where the defects were. Everything this change found came from the deterministic
layer or from reading answers: a citation swap, two answers understating what the corpus holds, and
expected lists twice built by a method that missed a third of what it should have. None of those is
what a faithfulness judge catches, and the citation swap is one it will probably pass.

The four judged-layer requirements moved with it, into `specs/judged-faithfulness/`. `deepeval`
leaves the `eval` extra and returns with the change that uses it. **ADR-0500 and ADR-0510 stay where
they are** — written under this change's block and referenced from commits — and remain in force
there.

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
