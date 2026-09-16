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
- [x] 4.5 Hand group 3 and 4 to a `verifier`. Ask it in particular whether any
      `AppTest` assertion would still pass with the widget removed entirely.

      **Answer: 17 of 27 fail with the widget gone, so the file is load-bearing.**
      Of the 10 survivors, 8 legitimately bypass the page and 2 assert absence,
      one of which needed a positive control and now has one.

      Four items came back CONFIRMED. **Five mutants survived the whole
      1243-test suite**, every one of them in the same blind spot — what the
      *page* hands down, rather than what a function does with a literal:

      - `draw_feedback(items, "wrong-session")` — every rating row would carry a
        session that joins to no trail row. Well-formed, plausible, useless.
      - `text="x"` in `_draw_comment_box` — every comment reads the same. The
        expensive direction: comments cannot be reconstructed from anything else.
      - `answering = False` — past turns' thumbs clickable mid-answer again, so a
        click abandons the generator. The defect `994087c` fixed, silently back.
      - `is_ratable -> True` — a reader thumbs down a spend-ceiling refusal and
        that row is indistinguishable from "the science was wrong".
      - `_column_for` in `answer()` only — the live path's layout was untested,
        because `st.rerun()` means `AppTest` only ever inspects the replay render.

      All five now die to a test, each with a canary. The lesson worth keeping:
      every one passed because the tests exercised the functions with literals
      and nothing asserted the wire between the page and them.

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
- [x] 5.3 CLAUDE.md: the new capability in the module table if a module is added.
      `feedback.py` added, marked **presentation, not core**, with a paragraph
      saying the placement *is* the guarantee — the agent must not be able to
      reach a stranger's text even by accident — and naming the wider
      `PRESENTATION` set the test checks, since the older adapters test does not
      cover it.
- [x] 5.4 `README.md` and `CHANGELOG.md`: that answers can be rated, that rating
      is optional, and that comments are read by the operators and never sent to
      the model. README gained a "Rating an answer" section and **two entries
      under "What it does not do"** — that a rating never changes the answer it
      judges, and that the trail names the question without storing it, pointing
      at the change that fixes it. A README that described only what works would
      be the more comfortable and less true one.
- [ ] 5.5 Archive the change on this branch, before the merge, and diff the
      promoted requirement text mechanically — `openspec archive` refuses a
      dropped scenario and says nothing about dropped prose.

## 6. What the collected feedback is for

- [x] 6.1 Write the handful of SQL queries that read it back: ratings per day,
      ratings per question, and every comment mentioning an entry identifier.
      Without these the data is collected and never looked at, which is the
      failure the previous change was about one level up. `sql/feedback.sql`,
      five queries — the three asked for, plus the unfiltered comment population
      to compare the third against, plus a "is anything arriving at all" query.
      **Unverified against a real database**, which the file says in its own
      header: they were written from `trail_store._SCHEMA` and the two event
      names, and this machine cannot reach Neon.
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

## 8. The layout the placement fixes kept pointing at

Three fixes in group 7 were the same fix — move the useful thing above the table
— which is a symptom of the layout rather than three placement bugs. ADR-0760.

- [x] 8.1 Each answered turn draws into two columns: prose, warnings, rating and
      ending on the left; the entries table, its legend and the corpus summary on
      the right. One `_column_for`, called by both the live path and the replay
      path, because a split computed twice is a split that drifts.
- [x] 8.2 `layout="wide"`, and `READING_SPLIT = (5, 6)` giving the larger share to
      the evidence. Not taste: the table's widths are fixed pixels summing to 640,
      and below that it grows a horizontal scrollbar whose first casualty is the
      ID column. No split of the centred layout's ~700px leaves 640 on one side.
- [x] 8.3 Rewrite the two placement tests. They still passed after the split and
      had stopped testing anything: the prose column is drawn first, so "the
      rating comes before the table" is true however the turn is divided. They now
      assert which column each landed in. Canaries: drawing everything into one
      column fails the first, and drawing the rating into the evidence column
      fails the second.
- [x] 8.4 Correct the two arguments the split retired — the rating's placement and
      the uncited fold — in ADR-0740, in the code comments that made them, and in
      the spec requirement, rather than leaving them standing.
- [x] 8.5 ADR-0760, including the cost: Streamlit columns do not stack until the
      viewport is narrow, so a small laptop gets a cramped page rather than the
      single column it replaces. Named as the first thing to look at if a reader
      reports one.
