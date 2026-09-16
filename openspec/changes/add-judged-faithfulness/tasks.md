# Tasks

ADR block for this change: **`0650`–`0690`**, allocated in the table in `CLAUDE.md`, which is the
authority. ADR-0500 (DeepEval over RAGAS) and ADR-0510 (a judge is validated against the identifiers)
were written under `add-answer-evaluation` and **remain in force here**; they are not renumbered,
because they are referenced from code comments and commit messages.

**Read this before picking up a task.** Group 1 is the part that has to come first and is the reason
this change exists: a reference a judge can fail against. Building the judge before that reference
exists produces a validated-looking figure resting on a validation that could not fail, which is
exactly what ADR-0510 was written to prevent.

## 1. A reference that can fail

- [ ] 1.1 Decide how to build it — harder questions, seeded faults, a weaker model's answers, or a
      combination — and record the choice with its cost. Each measures something different; the
      design names the trade. **Do not skip to group 2**: the 2026-09-11 reference is 29 sound of 30
      and cannot gate anything
- [ ] 1.2 Include the known discriminating case: the citation swap in repeat 2 of
      `yeast-nuclear-volume` (101627 cited for 105627's value), where the number is right, is in the
      context, and only the attribution is wrong
- [ ] 1.3 Build and hand-label the reference, on the same three states DeepEval returns
      (`sound` / `unsound` / `unclear`), and report the distribution before anything is judged. A
      reference that comes back saturated again is a stop, not a detail
- [ ] 1.4 Review before merging, with the reference itself in front of the reviewer, not only the code

## 2. The judge

- [ ] 2.1 Add `deepeval` to the `eval` extra, which it left when this change was split out; confirm
      the default `pytest` run is still unchanged, as `add-answer-evaluation` task 1.4 did
- [ ] 2.2 Implement the judge wrapper: DeepEval's model base subclassed over the project's
      `ChatOpenAI`, so the judge is configured where every other model is
- [ ] 2.3 Set `penalize_ambiguous_claims=True`, and say in the code why the shipped default is wrong
      here: `idk` counting as faithful is lenient on exactly the claims the judge was least sure of,
      in the layer that exists to catch what the deterministic checks cannot
- [ ] 2.4 Restate the verified DeepEval surface in the judge module's docstring, naming the version
      it was verified against, so the next reader knows what was checked rather than assumed
- [ ] 2.5 Implement the `judge` pass: read a results file, judge each answer that states a quantity,
      write judgements to their own file keyed by question, repeat and judge model. **The judgement
      file carries corpus text** and takes the same git refusal every other artefact of a run takes
- [ ] 2.6 Gate on *claims extracted*, not on the score: `_calculate_score` returns 1.0 for an empty
      verdict list, so a refusal and an unparseable answer both read as perfectly faithful. Record a
      refusal as not judged
- [ ] 2.7 Test the wrapper and the pass against a scripted judge, so the harness's own tests assert
      this code without a network call
- [ ] 2.8 Check how claim extraction treats `[[nnnnnn]]` markers on real answers; if it distorts the
      claims, strip them before judging and say so
- [ ] 2.9 Review before merging (see 1.4)

## 3. Trust, measured

- [ ] 3.1 Measure agreement against the reference from group 1 and against the deterministic scoring
      where both speak; list every disagreement with its claim and reason
- [ ] 3.2 Report the citation-swap case by name: if the judge passes it, say so plainly rather than
      letting a high agreement figure hide that the judge saw nothing
- [ ] 3.3 Set the floor from what 3.1 shows, not from a placeholder, and mark every judged figure
      unvalidated while agreement is below it
- [ ] 3.4 Write the ADR for whatever gate is adopted. If it is weaker than ADR-0510's correlation
      floor, **record that as a decision with its reason**, rather than letting the gate quietly
      soften
- [ ] 3.5 Review before merging (see 1.4)

## 4. The report, and the deferred judged metrics

- [ ] 4.1 Extend the report: judged figures beside the deterministic ones, never combined; per judge
      model, and marked unvalidated until 3.3 says otherwise
- [ ] 4.2 Judge whether a passed-over entry's *omission* changed the answer — an unmentioned growth
      condition, a value an order of magnitude from everything cited — rather than whether it fits
      the question, which the expected set settles by construction. Gate it behind a deterministic
      check on the spread between cited and passed-over values, so a judge is paid only where the
      numbers differ
- [ ] 4.3 Review before merging (see 1.4)

## 5. Documentation and conformance

- [ ] 5.1 `README.md`: how to judge a recorded run and how to read a judged figure
- [ ] 5.2 `CLAUDE.md`: the judge module in the Architecture table, and `deepeval` back in the `eval`
      extra
- [ ] 5.3 `CHANGELOG.md`: the judged layer under Unreleased
- [ ] 5.4 `tests/test_spec_conformance.py`: map every requirement in `judged-faithfulness` to the
      test that asserts it, and move them out of the `AWAITING_THE_JUDGE` gap bucket as they land
- [ ] 5.5 Reconcile the ADR block against `CLAUDE.md` before archiving
- [ ] 5.6 Review the whole change before archiving
