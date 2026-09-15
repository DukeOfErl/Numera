# Tasks — add-answer-feedback

**ADR block: `0740`–`0770`**, reserved in `CLAUDE.md`'s table, which is the
authority. Allocate by copying the template to the number and committing the stub
early — a number is spent when the file exists, not when the ADR is written.
`0780`–`0830` belongs to `add-user-identity` and must not be taken here.

**Testing policy for this change, decided with the user: no fault seeding and no
mutation testing.** This is a Streamlit widget, and the project's rule is to
scope those instruments by consequence — a broken thumbs-up announces itself to
the first person who clicks it. A read-only `verifier` subagent still reviews each
group before it is believed. `AppTest` against the real script is required for
anything about *when* a widget is drawn relative to a script run; nothing below
the driver can see that.

Already true and not to be redone: `question_id` is on `web.Item`,
`trail_store` is append-only with a nullable `user_email`, and recording already
fails open (ADR-0710).

## 1. What gets recorded

- [x] 1.1 Claim ADR-0740 with a stub: `st.feedback` over the trubrics component,
      with that component's staleness as the reason, and the three behaviours of
      the installed widget the design has to accommodate.
- [x] 1.2 Claim ADR-0750 with a stub: the tracer receives a copy and is not the
      record — free-tier trace expiry, feedback being a child of the run, and the
      retention cut of 2026-09-14.
- [x] 1.3 A `feedback` event written through `trail_store`, carrying the verdict
      and the `question_id`. A new `event` value, not a schema change.
- [x] 1.4 A comment is a **second** event naming the same question, never an
      update to the first row. Append-only means the sequence is the evidence.
- [x] 1.5 Rating state per question in session state, outside widget state, so
      "already recorded" is answerable on a redraw.

## 2. Verification of group 1

- [x] 2.1 Tests: a verdict is recorded with the right `question_id`; a comment is
      a separate record naming the same question; a second rating of the same
      answer does not write twice.
- [x] 2.2 A test that **neither a verdict nor a comment reaches the model**:
      assert over the stored conversation and the messages a later question is
      answered from, not over the answer's text. The property is what the model
      was shown; "the next answer is unchanged" is a counterfactual about a
      non-deterministic run and cannot be asserted at all.
- [x] 2.3 A test with a comment written as an instruction to the model -- stored
      as given, and absent from every prompt. Free text is the one input here
      authored by a stranger, and this is the route it must not take.
- [x] 2.4 A test that a failed write is invisible to the reader — inherited from
      `trail_store`, asserted here because this is the first caller where a
      failure would reach someone mid-conversation. **Was ticked once with no
      test behind it**; a verifier found that, and it now installs a failing
      handler and asserts the failure count moved.
- [x] 2.6 A test that a feedback record reaches `TrailStore` at all. Every other
      test here uses a fixture calling `trace.configure`, which *clears every
      handler* — so they all ran with the durable sink detached, and nothing
      established that the thing this change collects is collected.
- [x] 2.7 A test that the identifier a rating carries is one `start_question`
      actually minted. Every other test passes a literal `"q1"`, so a widget
      reading the wrong field off an item would write rows that are well formed
      and join to nothing.
- [x] 2.5 Hand group 1 to a `verifier` subagent before believing it. Give it the
      spec scenarios and ask specifically which are asserted and which merely
      execute. **Done, and it found five things a green 1200-test suite did
      not**: the guard named in `feedback.py`'s docstring did not exist (it
      cited a test checking `ADAPTERS`, and `feedback` is in `PRESENTATION`, a
      superset); task 2.4 was ticked with no test behind it; nothing asserted a
      feedback record reaches `TrailStore` at all, because the fixture every
      test uses calls `trace.configure`, which clears every handler; a spec
      scenario was unreachable and so could never fail; and `logging` catches
      nothing on its own, so the fail-open guarantee rested on one handler
      happening to swallow. All five closed in `2a58215` and `b6b388f`.

## 3. The widget

- [x] 3.1 `st.feedback` with thumbs, keyed on `question_id`, **outside** any
      `st.form` — inside one it returns `None` until submit and the conditional
      text area can never appear.
- [x] 3.2 The verdict commits on the click via the change callback, not on
      comment submit. Most readers who rate will do nothing else.
- [x] 3.3 The text area appears only once a verdict exists, and carries the hint
      asking for a problematic entry's ID by name. Keep it short — a hint that
      wraps into a paragraph is one nobody reads.
- [x] 3.4 Disable the control once a verdict is held, and keep the comment out of
      widget state: clicking the selected thumb clears it, and Streamlit discards
      the state of a widget it did not render, taking a half-typed comment along.
- [x] 3.5 Acknowledge a received rating on screen.

## 4. Through the real script

- [x] 4.1 `AppTest`: rate the **second** of two answers and assert the first is
      untouched. Rating the first would pass under a shared-key bug, which is the
      failure that produces no error at all.
- [x] 4.2 `AppTest`: interacting again after rating does not record a second time.
- [x] 4.3 `AppTest`: the widget is drawn once per answer per run — the transcript
      loop and the live turn must not both draw the newest one. That is currently
      true by ordering rather than by design, which is why it needs pinning.
- [x] 4.4 `AppTest`: an unrated answer records nothing and leaves the conversation
      able to take another question.
- [ ] 4.5 Hand group 3 and 4 to a `verifier`. Ask it in particular whether any
      `AppTest` assertion would still pass with the widget removed entirely.

## 5. The record

- [x] 5.1 Spec-conformance mapping entries for all five requirements, in this
      change. A requirement whose scenarios only execute is a gap, not a pass —
      say which is which. **Now genuinely five of five**: the three that sat in
      `AWAITING_THE_WIDGET` are mapped to the driver tests groups 3 and 4 built,
      and `AWAITING_THE_WIDGET` is gone rather than left empty. Closing the third
      needed a test that did not exist — that a broken sink does not stop the
      *page* — since the operation-level fail-open tests establish that
      `record_verdict` does not raise and say nothing about the conversation
      carrying on.
- [x] 5.2 `openspec validate add-answer-feedback --strict`. Passing, re-run after
      the group 7 spec edits.
- [ ] 5.3 CLAUDE.md: the new capability in the module table if a module is added.
- [ ] 5.4 `README.md` and `CHANGELOG.md`: that answers can be rated, that rating
      is optional, and that comments are read by the operators and never sent to
      the model.
- [ ] 5.5 Archive the change on this branch, before the merge, and diff the
      promoted requirement text mechanically — `openspec archive` refuses a
      dropped scenario and says nothing about dropped prose.

## 6. What the collected feedback is for

- [ ] 6.1 Write the handful of SQL queries that read it back: ratings per day,
      ratings per question, and every comment mentioning an entry identifier.
      Without these the data is collected and never looked at, which is the
      failure the previous change was about one level up.
- [x] 6.2 Record in ADR-0740 that a thumbs-down rate is **not** an error rate:
      people who rate are not a sample of people who read. The first person to
      quote a percentage should meet that sentence first. (Written with the ADR
      itself; this task was a check that it had been, and it had.)

## 7. What the first real use found

Three defects, all reported by the first person to use the deployed page and none
visible to a green suite — the expected division of labour for a driver, and the
reason this change carries `AppTest` coverage rather than a seeding budget.

- [x] 7.1 The comment box opened after approval as well as disapproval, under a
      hint reading "What was wrong?". Now disapproval alone opens it; approval is
      recorded and acknowledged and asks for nothing further. Spec requirement
      renamed accordingly, and its scenarios split in two.
- [x] 7.2 The rating was drawn after everything, so it sat below a table that one
      answer can fill the screen with. Now between the prose and the entries, by
      one predicate (`_ends_the_prose`) shared by the live path and the replay
      path — a seam computed twice is a seam that moves. Canary: making the
      predicate return `False` fails both placement tests.
- [x] 7.3 Sending a comment took two actions — the first committed the text, the
      second sent it — and `disabled=not text.strip()` made it worse, the first
      click landing on a disabled control. The text and its button are now a
      form; the thumb stays outside one, for the reason ADR-0740 gives. `AppTest`
      cannot see the two-action problem, so the test asserts the structure that
      prevents it: text area and Send sharing a form id.
- [x] 7.4 ADR-0740 records all three, including why softening the hint was
      rejected and why the form does not contradict the "no form" trap.
- [x] 7.5 Canary on the new fail-open driver test: narrowing `feedback._record`'s
      `except Exception` to `ZeroDivisionError` fails it. The first draft of that
      test installed the raising handler *before* the question and failed for the
      wrong reason — every trace record raised, which is the question's path and
      not the rating's.
