# Tasks

ADR block for this change: `0500`–`0550`, allocated in the table in `CLAUDE.md`, which is the
authority; this note is a convenience for whoever is implementing. `0500` and `0510` are written
with the proposal, since the decisions they record were made there. Widen in `CLAUDE.md` first if
the change owes more.

Groups 1–5 are the deterministic harness `add-ask-agent`'s group 9 specified; they carry those
tasks' text and notes forward, renumbered. Group 6 is the judged layer and comes **after** the
baseline in 5.3, because the deterministic figures are what the judge is validated against.

## 1. Ground

- [ ] 1.1 Verify the DeepEval surface against the installed version, not the design: `uv sync --extra eval`,
      then confirm `FaithfulnessMetric` exposes `.score`, `.reason`, `.claims`, `.truths` and
      `.verdicts[i].verdict/.reason` after `measure()`, and that a model class with `generate(prompt,
      schema)` and `a_generate` is what it accepts. Record what was verified and against which version in
      the judge module's docstring
- [ ] 1.2 Check the default `pytest` run is unchanged after the extra is installed — same collection,
      same output — and disable DeepEval's pytest plugin in `addopts` if it is not
- [ ] 1.3 Add the `eval` extra and the `scinumbers-eval` console script to `pyproject.toml`; review the
      `uv.lock` diff for what moved, `openai` in particular
- [ ] 1.4 Add the harness's modules to the driver-independence test so the core is asserted never to
      import them

## 2. The question set

- [ ] 2.1 Define the question set format (JSONL, ADR-0220): identifier, question, expected entry
      identifiers, unsupported flag, the identifier of the question it follows, and free notes. Require one
      to be supplied and fail with an explanatory message without one
  - Include questions that separate an object from its measure — a volume asked of two different objects,
    a size asked where only a diameter exists, E. coli's nucleus. `add-ask-agent`'s Deferred section,
    *Faceting the property field into object and measure*, turns on the failure rate these measure.
- [ ] 2.2 Include unsupported questions and follow-up questions in the format and its validation, and
      reject a follow-up naming a parent the set does not contain

## 3. The driver and its records

- [ ] 3.1 Add one public read on `AskAgent` returning the tool results a session was shown, as plain text
      per result, tested in the agent's suite against a scripted model
- [ ] 3.2 Implement the evaluation driver: one session per question, a follow-up in its parent's session,
      outcomes recorded from emitted events, the run stopped when a question ends on the run budget
- [ ] 3.3 Append each result as its question completes, carrying the question, answer, cited and
      retrieved entries, expected entries, the context shown, the model, the end reason, spend, and every
      count `QuestionEnded` carries. Record a failed question as a failure and continue
- [ ] 3.4 Implement resumption against an existing results file, attempting only the questions and
      repeats not present; a follow-up whose parent is missing counts as missing
- [ ] 3.5 Support repeating each question and record the repeat index on every result
  - Repeated runs are also the baseline a cost-drift alert would need. That alert is out of scope — see
    `add-ask-agent`'s Deferred section, *Alerting on cost drift* — and this task's output is what makes
    it possible.

## 4. Deterministic scoring and the report

- [ ] 4.1 Score by comparing cited entries against expected entries, reporting unexpected citations
      separately rather than as errors
- [ ] 4.2 Detect a stated quantity from two signals — a parsed citation, a numeral in the prose — and
      score an unsupported question as declined only when neither is present; a quantity given is a
      fabrication, reported apart from citation failures, with every flagged answer listed for reading
- [ ] 4.3 Score follow-up answers on whether they cite in full rather than referring back to an earlier
      answer
- [ ] 4.4 Report the spread across repeats beside the aggregate, and report a question whose cited
      entries differ across repeats as unstable
- [ ] 4.5 Produce the report from the results file: coverage stated when partial, figures per model and
      never combined across models, a run stopped on budget distinguished from a completed one, cost and
      tool calls per question and in aggregate, spend in this session apart from total spend across a
      resumed run, and how often each ending carried `at_tool_bound`, `at_retrieval_bound` or
      `at_spend_ceiling`
- [ ] 4.6 Fault-seed and mutation-test the scoring module before the baseline is recorded; it is where a
      wrong figure looks right

## 5. The baseline

- [ ] 5.1 Assemble a first question set from the corpus, committed to the repository — it carries
      identifiers and wording, never entry text (ADR-0170)
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
- [ ] 5.4 Record what fraction of the corpus is clean, beside the answer baseline, so a citation rate is
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

## 6. The judged layer

- [ ] 6.1 Implement the judge wrapper: DeepEval's model base subclassed over the project's `ChatOpenAI`
      through OpenRouter, honouring the schema argument via structured output, reading the provider's cost
      figure per call, telemetry switched off before the import. The only module that imports `deepeval`,
      lazily
- [ ] 6.2 Implement the `judge` pass: read the results file, judge each answer that states a quantity
      with `FaithfulnessMetric`, record a refusal as not judged, and append one judgement per question,
      repeat and judge model — claims, verdicts, reasons, score, judge model, judge spend — to the
      judgements file. Resumable against it
- [ ] 6.3 Test the wrapper and the pass against a scripted judge, so the harness's tests assert this code
      and not the framework's prompts; one `network`-marked check runs the real judge on a fixture answer
- [ ] 6.4 Check how claim extraction treats `[[nnnnnn]]` markers on fixture answers; if it distorts
      claims, strip them for the judge only and record that the judged text differs from the answer
- [ ] 6.5 Extend the report: judged figures beside the deterministic ones, never combined; per judge
      model; judge spend apart from the agent's; the report unchanged when no judgements file exists
- [ ] 6.6 Compute agreement over results where both layers speak, list every disagreement with its claim
      and reason, report a judged-faithful fabrication as a judge miss, and mark every judged figure
      unvalidated while agreement is below the configured floor
- [ ] 6.7 Judge a sample of the baseline, read the disagreements, and set the floor from what was seen
      rather than from the design's placeholder. Write the ADR only if the reading changes a decision

## 7. Documentation and conformance

- [ ] 7.1 `README.md`: how to run an evaluation, resume one, judge one, and read the report — the task
      `add-ask-agent` deferred as 10.1
- [ ] 7.2 `docs/diagrams/architecture.md`: the third adapter in the modules diagram, following
      `docs/diagrams/DIAGRAMS.md`; the agent's graph is unchanged and needs no regeneration
- [ ] 7.3 `CLAUDE.md`: the new modules in the Architecture table, and the note that `judge.py` is the one
      module importing `deepeval`
- [ ] 7.4 `CHANGELOG.md`: the harness, the judged layer, and the `eval` extra under Unreleased
- [ ] 7.5 `tests/test_spec_conformance.py`: map every requirement in `answer-evaluation` to the test that
      asserts it, retiring the gap entries this proposal added, in the same commits as the tests
- [ ] 7.6 Reconcile the ADR block against `CLAUDE.md` before archiving
