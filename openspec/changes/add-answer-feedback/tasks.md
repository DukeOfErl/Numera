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

- [ ] 1.1 Claim ADR-0740 with a stub: `st.feedback` over the trubrics component,
      with that component's staleness as the reason, and the three behaviours of
      the installed widget the design has to accommodate.
- [ ] 1.2 Claim ADR-0750 with a stub: the tracer receives a copy and is not the
      record — free-tier trace expiry, feedback being a child of the run, and the
      retention cut of 2026-09-14.
- [ ] 1.3 A `feedback` event written through `trail_store`, carrying the verdict
      and the `question_id`. A new `event` value, not a schema change.
- [ ] 1.4 A comment is a **second** event naming the same question, never an
      update to the first row. Append-only means the sequence is the evidence.
- [ ] 1.5 Rating state per question in session state, outside widget state, so
      "already recorded" is answerable on a redraw.

## 2. Verification of group 1

- [ ] 2.1 Tests: a verdict is recorded with the right `question_id`; a comment is
      a separate record naming the same question; a second rating of the same
      answer does not write twice.
- [ ] 2.2 A test that a failed write is invisible to the reader — inherited from
      `trail_store`, asserted here because this is the first caller where a
      failure would reach someone mid-conversation.
- [ ] 2.3 Hand group 1 to a `verifier` subagent before believing it. Give it the
      spec scenarios and ask specifically which are asserted and which merely
      execute.

## 3. The widget

- [ ] 3.1 `st.feedback` with thumbs, keyed on `question_id`, **outside** any
      `st.form` — inside one it returns `None` until submit and the conditional
      text area can never appear.
- [ ] 3.2 The verdict commits on the click via the change callback, not on
      comment submit. Most readers who rate will do nothing else.
- [ ] 3.3 The text area appears only once a verdict exists, and carries the hint
      asking for a problematic entry's ID by name. Keep it short — a hint that
      wraps into a paragraph is one nobody reads.
- [ ] 3.4 Disable the control once a verdict is held, and keep the comment out of
      widget state: clicking the selected thumb clears it, and Streamlit discards
      the state of a widget it did not render, taking a half-typed comment along.
- [ ] 3.5 Acknowledge a received rating on screen.

## 4. Through the real script

- [ ] 4.1 `AppTest`: rate the **second** of two answers and assert the first is
      untouched. Rating the first would pass under a shared-key bug, which is the
      failure that produces no error at all.
- [ ] 4.2 `AppTest`: interacting again after rating does not record a second time.
- [ ] 4.3 `AppTest`: the widget is drawn once per answer per run — the transcript
      loop and the live turn must not both draw the newest one. That is currently
      true by ordering rather than by design, which is why it needs pinning.
- [ ] 4.4 `AppTest`: an unrated answer records nothing and leaves the conversation
      able to take another question.
- [ ] 4.5 Hand group 3 and 4 to a `verifier`. Ask it in particular whether any
      `AppTest` assertion would still pass with the widget removed entirely.

## 5. The record

- [ ] 5.1 Spec-conformance mapping entries for all five requirements, in this
      change. A requirement whose scenarios only execute is a gap, not a pass —
      say which is which.
- [ ] 5.2 `openspec validate add-answer-feedback --strict`.
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
- [ ] 6.2 Record in ADR-0740 that a thumbs-down rate is **not** an error rate:
      people who rate are not a sample of people who read. The first person to
      quote a percentage should meet that sentence first.
