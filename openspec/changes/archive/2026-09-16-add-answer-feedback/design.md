# Design — add-answer-feedback

## Context

See `proposal.md` — Why. What shapes the approach:

- **The page redraws entirely on every interaction.** Streamlit re-runs the
  script, replaying the whole transcript, then draws the live turn. Any widget in
  that loop is re-created on every click, which decides both its keying and where
  the record must be kept.
- **`question_id` already reaches the page.** It is on `web.Item` and in every
  trail record; that was the previous change, done first precisely because it
  cannot be retrofitted.
- **A durable append-only store already exists.** `trail_store` writes one table
  where a new kind of record is a new `event` value.
- **The fail-open policy is already decided and specified** (ADR-0710). Feedback
  inherits it rather than restating it.

## Goals / Non-Goals

**Goals.** A rating survives the deploy. It names its question. It costs a reader
nothing to ignore. It cannot be double-counted by a redraw.

**Non-Goals.** Not per-entry rating — deferred deliberately, and the comment
field is the instrument for deciding whether to build it. Not identity. Not any
aggregation UI. Not acting on a rating.

## Decisions

### D1. Native `st.feedback`, not the third-party component

`streamlit-feedback` (trubrics) has exactly the feature wanted — thumbs plus an
optional text box that appears only after a thumb, with `review_on_positive`
control. It is also last released **2025-01-13**, 26 open issues, declares
`streamlit>=0.63` with no claim about the installed 1.61.x, and carries an open
issue reporting that the released wheel ships JavaScript built from an older
version. It is a custom component: its frontend is prebuilt JS against a 2023-era
component API.

The only thing it buys is the conditional text box, which natively is an
`if verdict is not None:` guard. Not worth a deployment risk on a hosted app for
~25 lines.

### D2. Three behaviours of the installed widget that the design must accommodate

Read out of the installed Streamlit 1.61.1 source rather than its documentation:

- **Clicking the selected thumb clears it** — `if ui_value == "": return None`. A
  conditional text area therefore disappears, and Streamlit discards the state of
  a widget it did not render, taking a half-typed comment with it. Handled by
  disabling the control once a verdict is held, and by keeping the comment
  outside widget state.
- **The control must sit outside any `st.form`.** Inside one it returns `None`
  until the form submits, so a text area conditional on its value can never
  appear.
- **The verdict is committed on the click**, through the widget's change
  callback, not when a comment is submitted. Otherwise the reader who rates and
  walks away — most of them — leaves nothing behind.

### D3. Keyed on `question_id`, never on transcript position

Widget keys must be unique per answer or Streamlit raises `DuplicateWidgetID`.
The louder failure is not the risk; the quiet one is that a **shared** key gives
every answer one value, so rating the third answer writes the verdict onto the
first, with no error at all.

Position is unsafe for the durable record for a different reason: `web.transcript`
lives in session state alone, so reopening a conversation from its identifier
restarts positions at 0 while the conversation continues — and `(session, 0)`
then names two different questions.

### D4. The record goes in `trail_store`; the tracer gets a copy that is not the record

A new `event` value in the existing append-only table. No migration, no second
store to operate, and the rating lands in the same place as the trail of what the
question retrieved — which is the join anyone analysing this will want.

A hosted tracer also receives the verdict, because that is where someone
debugging a single run is already looking. **It is explicitly not the record**:
on the free tier a trace expires after 14 days and feedback is a child object of
the run, so it dies with it; the bulk export needed to read it back became
enterprise-only for new customers on 2026-08-03; and the vendor cut maximum
retention from 400 days to 180 on 2026-09-14. A system of record should not be
one whose retention the supplier re-cuts mid-alpha.

### D5. The comment is a second write, not part of the first

The verdict is one row; a comment that follows is another, naming the same
question. Append-only means never updating a row, and it means a reader who rates
and then comments is two events in time order — which is what happened.

### D6. Rating state lives in session state, keyed by question, outside widget state

Streamlit garbage-collects the state of a widget it did not render, and clearing
a thumb un-renders the conditional text area. So the durable-intent record — what
this reader has rated and whether a comment has been sent — is held in an
ordinary dictionary keyed by `question_id`, never read back out of the widget's
own key. This is also what makes "do not record the same judgement twice on a
redraw" checkable.

## Risks / Trade-offs

- **A redraw double-records** → the per-question dictionary is consulted before
  writing; a test drives the real script and interacts twice.
- **A shared widget key silently mis-attributes a rating** → keys derive from
  `question_id`, and a test rates the *second* of two answers and asserts the
  first is untouched. Rating the first would pass under the bug.
- **The transcript loop and the live turn both draw the same answer in one run**
  → currently avoided because the loop finishes before the live turn is appended.
  That is ordering, not design, so `AppTest` pins it.
- **Selection bias, unmitigated** → people who rate are not a sample of people who
  read, and a thumbs-down rate is not an error rate. Recorded here so the first
  person to quote a percentage sees it.
- **Free text may contain anything a reader types** → it is stored as given and
  shown to no one but the operators; it is never fed back to the model, which is
  also what keeps D4's "a rating changes nothing" true.

## Migration Plan

Additive. No schema change (a new `event` value in an existing table), no change
to answering, and nothing to roll back beyond removing the widget. With no
durable destination configured, ratings behave like every other record: collected
in the process, reported as dropped, and the reader unaffected.

## Open Questions

- Whether per-entry rating is worth building. That is what this change exists to
  answer, and answering it needs collected comments rather than a decision now.
