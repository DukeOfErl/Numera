# Tasks

ADR block for this change: `0500`–`0550`, allocated in the table in `CLAUDE.md`, which is the
authority; this note is a convenience for whoever is implementing. `0500` and `0510` were written
with the proposal, since the decisions they record were made there; they concern the judged layer,
which is deferred to a follow-up but decided. Widen in `CLAUDE.md` first if the change owes more.

Groups 2–5 are the deterministic harness `add-ask-agent`'s group 9 specified, carrying those tasks'
text and notes forward, renumbered, plus the extensions from the review of 2026-09-03: the value and
unit beside each citation, passed-over entries, the agent's own warnings as scores, provenance and
tags. The judged layer is **not** in this change; see the proposal's Deferred section.

## 1. Ground

- [ ] 1.1 Add the `scinumbers-eval` console script to `pyproject.toml`. No new dependency
- [ ] 1.2 Add the harness's modules to the driver-independence test so the core is asserted never to
      import them
- [ ] 1.3 Read `openspec/specs/agent-session/` as promoted, not the archived delta: it is the port the
      harness drives

## 2. The question set

- [ ] 2.1 Define the question set format (JSONL, ADR-0220): identifier, question, the property and
      organism asked in the corpus's vocabulary, expected entry identifiers, unsupported flag, the
      identifier of the question it follows, tags, and free notes.
      Require one to be supplied and fail with an explanatory message without one
  - Include questions that separate an object from its measure — a volume asked of two different objects,
    a size asked where only a diameter exists, E. coli's nucleus. `add-ask-agent`'s Deferred section,
    *Faceting the property field into object and measure*, turns on the failure rate these measure.
- [ ] 2.2 Validate unsupported and follow-up questions in the format, and reject a follow-up naming a
      parent the set does not contain
- [ ] 2.3 Derive each expected entry's shape from the corpus at load time — complete, or lacking a scalar,
      a classified unit, an unfused range, a method, or carrying a hedged range — and have validation
      require every shape to be present in the set, reporting which are missing

## 3. The driver and its records

- [ ] 3.1 Add one public read on `AskAgent` returning the tool results a session was shown, as plain text
      per result, tested in the agent's suite against a scripted model
- [ ] 3.2 Implement the evaluation driver: one session per question, a follow-up in its parent's session,
      outcomes recorded from emitted events, the run stopped when a question ends on the run budget
- [ ] 3.3 Append each result as its question completes, carrying the question, answer, cited and
      retrieved entries, expected entries, the context shown, the agent's warnings (`CitationWarning`,
      `UngroundedRefusal`), the end reason, spend, and every count `QuestionEnded` carries. Record a failed
      question as a failure and continue
- [ ] 3.4 Record provenance on every result: model and every `Config` setting that shapes an answer, a
      digest of the system prompt, a digest and entry count of the corpus file, the code version (git
      commit, else package version, saying which), and the UTC time
- [ ] 3.5 Implement resumption against an existing results file, attempting only the questions and
      repeats not present; a follow-up whose parent is missing counts as missing
- [ ] 3.6 Support repeating each question and record the repeat index on every result
  - Repeated runs are also the baseline a cost-drift alert would need. That alert is out of scope — see
    `add-ask-agent`'s Deferred section, *Alerting on cost drift* — and this task's output is what makes
    it possible.

## 4. Deterministic scoring and the report

- [ ] 4.1 Score by comparing cited entries against expected entries, reporting unexpected citations
      separately rather than as errors, and splitting the expected entries not cited into retrieved and
      passed over versus never retrieved
- [ ] 4.2 Implement the quantity reader: every number, optional exponent, optional range, qualification
      token and unit token in the window before each citation marker, with consecutive markers sharing a
      window. A parser; test it on answer shapes taken from the live traces, and on the shapes the design
      lists (a value and its conversion, a range and a typical value, two dimensions before one marker)
- [ ] 4.3 Compare each quantity in the window with its entry according to the entry's shape: scalar within
      tolerance; range endpoints or a value inside; bare correct where the entry gives no number and a
      quantity there reported; a qualification required where the range is hedged; the unit string
      verbatim where it is unclassified. Retry under power-of-ten rescaling and report a hit there as
      matching under rescaling, listed and not counted; compare the unit token with the entry's unit
      through `units.py`'s three-valued check. Report per citation: all match, mixed, rescaled, mismatch,
      bare; compatible, incompatible, unknown
- [ ] 4.3a Score whether the agent searched for the asked organism and property — a public resolution
      method on the repository, the same one `search` uses, applied to each `Retrieval`'s arguments — and
      what fraction of cited entries carry the asked organism and property in their fields; the two
      reported apart
- [ ] 4.4 Detect a stated quantity from two signals — a parsed citation, a numeral in the prose — and
      score an unsupported question as declined only when neither is present; a quantity given is a
      fabrication, reported apart from citation failures, with every flagged answer listed for reading
- [ ] 4.5 Score the agent's own warnings: unretrieved and unknown citations as grounding failures; a
      refusal with no retrieval as an ungrounded refusal apart from correctly declined; `claimed_searching`
      counted separately
- [ ] 4.6 Score follow-up answers on whether they cite in full rather than referring back to an earlier
      answer
- [ ] 4.7 Report the spread across repeats beside the aggregate, and report a question whose cited
      entries differ across repeats as unstable
- [ ] 4.8 Produce the report from the results file: coverage stated when partial; figures per model, per
      prompt digest and per corpus digest, never combined across any of them, saying when the corpus
      differed; per tag on request; every value figure per entry shape; a run stopped on budget distinguished from a completed one; cost and
      tool calls per question and in aggregate; spend in this session apart from total spend across a
      resumed run; how often each ending carried `at_tool_bound`, `at_retrieval_bound` or
      `at_spend_ceiling`
- [ ] 4.9 Fault-seed and mutation-test the scoring module — the quantity reader above all — before the
      baseline is recorded; it is where a wrong figure looks right
- [ ] 4.10 On the first run, count both directions of every classifying rule (bare citations, rescaled
      matches, mismatches, flagged declines) and read them against the answers before trusting any figure

## 5. The baseline

- [ ] 5.1 Assemble a first question set from the corpus, committed to the repository — it carries
      identifiers and wording, never entry text (ADR-0170). Happy-path questions on complete entries, and
      questions on each incomplete shape (2.3), chosen by querying the corpus for entries of that shape;
      the set's validation refuses a set missing one
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
      that the figures bear on. **This is the trigger for the deferred judged layer**
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

## 6. Documentation and conformance

- [ ] 6.1 `README.md`: how to run an evaluation, resume one, and read the report — the task
      `add-ask-agent` deferred as 10.1
- [ ] 6.2 `docs/diagrams/architecture.md`: the third adapter in the modules diagram, following
      `docs/diagrams/DIAGRAMS.md`; the agent's graph is unchanged and needs no regeneration
- [ ] 6.3 `CLAUDE.md`: the new modules in the Architecture table
- [ ] 6.4 `CHANGELOG.md`: the harness under Unreleased
- [ ] 6.5 `tests/test_spec_conformance.py`: map every requirement in `answer-evaluation` to the test that
      asserts it, retiring the gap entries this proposal added, in the same commits as the tests
- [ ] 6.6 Reconcile the ADR block against `CLAUDE.md` before archiving
