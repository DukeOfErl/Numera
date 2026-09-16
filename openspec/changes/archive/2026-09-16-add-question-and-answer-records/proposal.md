## Why

A rating now says *"answer `c23c83c16324` was wrong"* and there is no way to find
out what it was answering. The trail records the question's identifier, its
searches, its retrievals and its spend — but neither the question as asked nor the
answer as given — so the judgement the previous change was built to collect cannot
be read.

This is a gap rather than a decision. No comment in the source argues for omitting
the text, and the question is already carried on the events
(`QuestionStarted.question`, `AnswerEntries.question`) because the drivers need
it; it simply never reaches `trace.record`. The capability's own requirement lists
what must be recorded — "searches, retrievals, alias resolutions, truncation
decisions, and each spend increment" — and the question and the answer are not in
that list.

Now, because feedback has started arriving. Every rating collected before this
lands is a verdict on a question nobody can reconstruct, and a trail cannot be
backfilled: the rows already written name a question whose text was never kept
anywhere.

## What Changes

- A question's trail records **the question as asked**.
- A question's trail records **the answer as given**.
- A question's trail records **every entry the answer was built on** — the cited
  set and the retrieved set — as one record, so the evidence behind an answer can
  be read without reassembling it from individual search and retrieval rows.
- The requirement states plainly **what is stored and why**, because what a person
  typed is being kept. The change is a decision about a reader's words, not only a
  plumbing change.
- No storage migration. The trail table is append-only with a `detail` column, so
  new record kinds are new event values — the same way feedback was added.

Not breaking: nothing already recorded changes shape, and a deployment with no
durable destination configured behaves exactly as before.

## Capabilities

### New Capabilities

None. This extends what the existing trail records rather than introducing a new
kind of behaviour.

### Modified Capabilities

- `agent-session`: the requirement *"The deterministic layer is logged under a
  per-question identifier"* gains the question, the answer and the answer's
  evidence set to what must be recorded, and states what is being stored about a
  person and why.

## Impact

**Code.** `agent.py` at two existing seams — where `AnswerEntries` is emitted
(the evidence set) and where `question.answered` is recorded (the answer). The
question is available at the top of `ask`. `trace.py` is unchanged: `record`
already takes arbitrary fields.

**Storage.** None. New `event` values in the existing `trail` table; `detail` is
`jsonb`.

**Size.** Rows grow from tens of bytes to the length of a question plus an answer
— roughly a kilobyte per question rather than a hundred bytes. Worth stating, not
worth engineering around at alpha scale.

**Reading it back.** `sql/feedback.sql` becomes able to show a rating beside the
question it judged. The queries there join on `question_id` already.

**Deliberately unaffected.** The model is never shown any of this; these are
records, not context. The entry set recorded is what the *agent* knows — cited
plus retrieved. What the *driver* displayed is a smaller set chosen by
presentation limits, and recording that is a separate question left open here.
