# Tasks

**ADR block: `0840`–`0870`.** Reconciled against CLAUDE.md's table, which is the
authority. Allocate by creating the stub and committing it early — a ceiling only
holds if claiming the number and writing the file are the same step.

**Testing policy for this change**, same as `add-answer-feedback`: no fault
seeding and no mutation testing. This is plumbing whose failure is visible in the
first row anybody reads. A read-only `verifier` reviews each group.

**The negative-case rule bites here specifically.** A test asserting "the record
carries the question" passes against a mutant that records *any* string — the
project has been caught by exactly this shape three times. Every test below varies
the thing the assertion reads: two different questions, two different answers, a
cited set that differs from the retrieved set.

## 1. The question

- [ ] 1.1 Record the question as asked, at the start of `ask` — not at the end.
      A question that hits a spend ceiling, a missing key or a crash must still
      leave a record of what was asked, and those are the runs worth
      investigating.
- [ ] 1.2 Test: two different questions produce two records whose recorded text
      differs. Not "the field is non-empty" — that passes against a mutant
      recording a constant.
- [ ] 1.3 Test: a question that ends without an answer still recorded what was
      asked. Drive it through an ending that produces no `Answer`, and assert
      through the trail, not through the events.

## 2. The answer

- [ ] 2.1 Record the answer as given, verbatim, at the existing
      `question.answered` seam. No truncation: a shortened answer cannot be
      compared against the rating it received.
- [ ] 2.2 Test: two different answers produce two records whose recorded text
      differs, and each sits under the question id that produced it.
- [ ] 2.3 Check the ending paths that yield an `Answer` other than the ordinary
      one — a refusal, a partial answer at a limit. Decide deliberately whether
      each records an answer, and write down which and why. `messages.STOP_THE_RUN`
      names the endings; `agent.py` yields `Answer` from several branches.

## 3. The evidence

- [ ] 3.1 Record the cited set and the retrieved set together, on the existing
      `AnswerEntries` seam, keeping them distinguishable. Not one merged list —
      merging cannot be undone by a query, and the distinction is "the answer
      stood on this" versus "this was in front of it".
- [ ] 3.2 `retrieved` is the whole retrieved set, not the displayed head of it.
      Assert that with a retrieval larger than `web.CITED_ROWS`, so a test would
      fail if the driver's presentation cap ever leaked into the record.
- [ ] 3.3 Test: a cited set that differs from the retrieved set stays
      distinguishable in the record. A test where they are equal proves nothing.
- [ ] 3.4 Test: a question that retrieved nothing records no evidence row, or
      records an empty one — decide which, and say why in the test's name.

## 4. The obligations the spec creates

- [ ] 4.1 The reader can learn from the interface that their question is kept.
      The prototype banner is pinned to the viewport and is the obvious place.
      This is an obligation the spec states, not a nicety.
- [ ] 4.2 Test: nothing recorded here reaches the model. Follow
      `test_feedback.py::test_neither_a_verdict_nor_a_comment_reaches_the_model`,
      including its positive control — every assertion in that test is a `not in`,
      which an empty haystack satisfies.
- [ ] 4.3 Test: a sink that raises does not fail a question. The existing
      fail-open guarantee must still hold with the larger rows; `logging` catches
      nothing on its own, which cost this project a defect already.
- [ ] 4.4 Confirm no driver records the question as well. Two records of one
      question under one identifier make a naive query double-count, and the
      agent-side record is the one the spec requires.

## 5. Verification

- [ ] 5.1 Hand groups 1–3 to a `verifier`. Ask it specifically whether any test
      would still pass if the recorded value were replaced by a constant, and
      whether any asserts only that a field exists.
- [ ] 5.2 Run the full suite once, at the end. Not per group.

## 6. The record

- [ ] 6.1 ADR in block `0840`–`0870`: what is kept about a person and why, three
      records rather than one, and why the displayed subset is deliberately not
      recorded. Write it with the change, not as a batch at the end.
- [ ] 6.2 Spec-conformance mapping for the modified requirement's new scenarios.
      A scenario that merely executes is a gap, not a pass — say which is which.
- [ ] 6.3 `sql/feedback.sql`: extend the per-question query to show the question
      and answer beside the rating. That join is the whole point of this change,
      and the file currently returns a `question_id` nobody can read.
- [ ] 6.4 `README.md` and `CHANGELOG.md`: that questions and answers are recorded,
      and who reads them.
- [ ] 6.5 `docs/roadmap.md`: WP2.5 points at this change rather than describing it.
- [ ] 6.6 `openspec validate add-question-and-answer-records --strict`, then
      archive, then diff the promoted requirement text mechanically — `openspec
      archive` refuses a dropped scenario and says nothing about dropped prose.
