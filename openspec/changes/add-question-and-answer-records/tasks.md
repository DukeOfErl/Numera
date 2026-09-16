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

- [x] 1.1 Record the question as asked, at the start of `ask` — not at the end.
      A question that hits a spend ceiling, a missing key or a crash must still
      leave a record of what was asked, and those are the runs worth
      investigating.
- [x] 1.2 Test: two different questions produce two records whose recorded text
      differs. Not "the field is non-empty" — that passes against a mutant
      recording a constant.
- [x] 1.3 Test: a question that ends without an answer still recorded what was
      asked. Drive it through an ending that produces no `Answer`, and assert
      through the trail, not through the events.

## 2. The answer

- [x] 2.1 Record the answer as given, verbatim, at the existing
      `question.answered` seam. No truncation: a shortened answer cannot be
      compared against the rating it received.
- [x] 2.2 Test: two different answers produce two records whose recorded text
      differs, and each sits under the question id that produced it.
- [x] 2.3 Check the ending paths that yield an `Answer` other than the ordinary
      one — a refusal, a partial answer at a limit. Decide deliberately whether
      each records an answer, and write down which and why. `messages.STOP_THE_RUN`
      names the endings; `agent.py` yields `Answer` from several branches.
      **Decided: all of them, and structurally rather than branch by branch.** An
      ending is an answer a reader is shown and rates, so every one records. The
      record is written in `ask`, which wraps the work as `_ask`, so the property
      holds for a branch nobody has written yet. `test_every_ending_that_gives_an_answer_records_it`
      drives all nine builds in `tests/agent_endings.py` — shared with
      `test_agent.py` so the two enumerations cannot drift apart.

## 3. The evidence

- [x] 3.1 Record the cited set and the retrieved set together, on the existing
      `AnswerEntries` seam, keeping them distinguishable. Not one merged list —
      merging cannot be undone by a query, and the distinction is "the answer
      stood on this" versus "this was in front of it".
- [x] 3.2 `retrieved` is the whole retrieved set, not the displayed head of it.
      Assert that with a retrieval larger than `web.CITED_ROWS`, so a test would
      fail if the driver's presentation cap ever leaked into the record.
- [x] 3.3 Test: a cited set that differs from the retrieved set stays
      distinguishable in the record. A test where they are equal proves nothing.
- [x] 3.4 Test: a question that retrieved nothing records no evidence row, or
      records an empty one — decide which, and say why in the test's name.
      **Decided: no row.** A row of empty lists reads as "the answer rested on
      nothing we could find", when what happened is that it never looked;
      `answer.ungrounded` already says that and is asserted alongside.

## 4. The obligations the spec creates

- [x] 4.1 The reader can learn from the interface that their question is kept.
      ~~The prototype banner~~ — **not** the banner, which is one line by design
      and becomes a block a reader skips if it wraps. `messages.RECORDS_NOTE`,
      shown as a sidebar caption on the page and on stderr in the terminal, above
      the `--ask` branch so a single question says it too.
- [x] 4.2 Test: nothing recorded here reaches the model. Follow
      `test_feedback.py::test_neither_a_verdict_nor_a_comment_reaches_the_model`,
      including its positive control — every assertion in that test is a `not in`,
      which an empty haystack satisfies.
- [x] 4.3 Test: a sink that raises does not fail a question. The existing
      fail-open guarantee must still hold with the larger rows; `logging` catches
      nothing on its own, which cost this project a defect already.
      Asserted at the real sink — a `TrailHandler` over an engine that refuses to
      begin — because that is where the swallowing happens. `trace.record` itself
      still does not catch, which is unchanged by this change and said so in
      ADR-0840 rather than left to be discovered.
- [x] 4.4 Confirm no driver records the question as well. Two records of one
      question under one identifier make a naive query double-count, and the
      agent-side record is the one the spec requires.

## 5. Verification

- [ ] 5.1 Hand groups 1–3 to a `verifier`. Ask it specifically whether any test
      would still pass if the recorded value were replaced by a constant, and
      whether any asserts only that a field exists.
- [x] 5.2 Run the full suite once, at the end. Not per group. 1273 passed,
      3 skipped, 39 deselected. (One fewer than before the mapping: removing the
      requirement from `TESTED_BUT_UNNAMED` drops one parametrised gap test.)

**Eight canaries, eight deaths**, seeded into a copy: a constant question, a
truncated answer, `cited` set from `event.retrieved`, the retrieved set sliced at
the driver's cap, the answer recorded after the `yield`, only short answers
recording, and each interface notice removed. Recorded because the first run of
the last two **passed vacuously** — `test_web_driver.py` resolves the app by
absolute path, so a mutation applied to a copied `streamlit_app.py` was never
read. They died once re-run from a self-contained copy of `src`, `tests` and the
app. A canary that cannot be shown to have applied proves nothing.

## 6. The record

- [x] 6.1 ADR in block `0840`–`0870`: what is kept about a person and why, three
      records rather than one, and why the displayed subset is deliberately not
      recorded. Write it with the change, not as a batch at the end.
- [x] 6.2 Spec-conformance mapping for the modified requirement's new scenarios.
      A scenario that merely executes is a gap, not a pass — say which is which.
- [x] 6.3 `sql/feedback.sql`: extend the per-question query to show the question
      and answer beside the rating. Query 2 now joins `question.asked` and
      `answer.given`; query 2b is new and shows cited against retrieved. Both run
      against `dev` on 2026-09-16: 25 rows, left joins keeping the pre-change
      ratings rather than dropping them, and the new columns null on every one —
      so the *populated* case is exercised by the suite and not yet by real rows.
      The header says exactly that.
- [x] 6.4 `README.md` and `CHANGELOG.md`: that questions and answers are recorded,
      and who reads them.
- [x] 6.5 `docs/roadmap.md`: WP2.5 points at this change rather than describing it.
- [x] 6.6 `openspec validate add-question-and-answer-records --strict`, then
      archive, then diff the promoted requirement text mechanically — `openspec
      archive` refuses a dropped scenario and says nothing about dropped prose.
