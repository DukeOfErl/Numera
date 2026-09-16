# ADR-0840: What a question's trail keeps, and why

- **Status:** accepted
- **Date:** 2026-09-16
- **Pull request:** _pending — `feat/question-and-answer-records`_

## Context

The trail recorded a question's identifier, its searches, its retrievals and its
spend — and neither the question as asked nor the answer as given. So the first
ratings collected by `add-answer-feedback` said *"answer `c23c83c16324` was
wrong"*, and there was no way to find out what it was answering.

This was a gap rather than a decision: nothing in the source argued for omitting
the text, and both events already carry it (`QuestionStarted.question`,
`AnswerEntries.question`) because the drivers need it. It simply never reached
`trace.record`.

It had to be fixed now rather than later, because a trail cannot be backfilled.
Every rating written before this change names a question whose words were never
kept anywhere, and those stay unreadable.

## Decision

**Three records, on the existing table, all under the question's own identifier:
`question.asked`, `answer.given`, `answer.evidence`.**

### Three records rather than one

The question is known at the start, the evidence in the middle, the answer at the
end. A single `question.completed` record would have to be held and written last,
which loses the question whenever a run dies between — and a question that ended
without an answer is exactly the case worth having. It also matches the trail's
existing shape, which is one record per thing that happened rather than one row
per question.

### The question is recorded when the question starts

Not at the end. A question that hits a spend ceiling, a missing key or a crash
still leaves a record of what was asked. The failing runs are the ones worth
investigating, and they are precisely the ones a write-at-the-end design drops.

### Recorded in `ask`, not at the eight places that yield an `Answer`

`ask` now wraps the work as `_ask` and writes each record as the corresponding
event passes through. The alternative — a `trace.record` beside each `yield
Answer` — was rejected because seven of those eight branches are endings: a spend
limit, a conversation bound, a run budget, a missing key, an unpriceable
response. An ending *is* an answer, shown to a reader and rated by them, and a
per-branch record is one the next branch forgets. Writing it at the seam every
branch passes through makes the ninth branch record itself.

*This is the "guards belong to the operation" corollary applied to records.* The
same argument puts the records in the agent rather than in a driver: a record
written by `web.py` exists only for the web, and the evaluation harness — the
third adapter — would be missing from the data.

**Each record is written before its event is handed on.** Code after a `yield`
runs only if somebody asks for the next item, and Streamlit abandons the
generator mid-iteration on every rerun. A record written after the `Answer` would
be lost exactly when a reader clicked something, which is the moment a rating is
about to arrive.

### Cited and retrieved stay separable

Not one merged list. "The answer stood on this" and "this was in front of it" are
different statements, and merging them cannot be undone by a query. `retrieved`
is the whole retrieved set, not the head of it that the page displays.

### The answer is recorded verbatim

No truncation. A shortened answer cannot be compared against the rating it
received, which is the only thing this record is for.

## What is deliberately *not* recorded

- **The subset the reader actually saw.** `web.CITED_ROWS` and `UNCITED_ROWS` cut
  the table down, and "they rated it down because the entry they wanted was cut"
  is a real hypothesis. It is also a driver-side record and a different decision;
  the record here is what the *agent* knows.
- **Who asked.** Nothing about identity, until `add-user-identity` exists and a
  requirement says so. The session identifier was already recorded and still is.
- **Anything reaching the model.** These are records of a question already
  answered, not context for the next one, and `test_driver_independence.py` plus
  a positive-controlled test over what the model was shown both hold that line.

## Trade-off accepted

**The trail is no longer free of the corpus's text.** Before this change every
record carried search terms, identifiers and counts, and `trace.py` said so — a
trail could be committed or shared without a licensing thought. `answer.given`
carries the model's prose verbatim, which restates corpus values and may quote a
reference string. The default destination stays under gitignored `logs/`, and
nothing refuses a tracked `--trace` path the way `evaluation.py` refuses a
tracked results path: an answer is a reader's own output and reaches stdout
regardless, so the trail is not the surface that decides whether it leaks.
Accepted, and the comment that said otherwise is corrected — found by the code
review, which is what a false comment left behind looks like from outside.

**Rows grow from roughly a hundred bytes to roughly a kilobyte.** Accepted
unmitigated. At alpha scale — tens of questions a day — that is single-digit
megabytes a year, well inside Neon's free tier. A size guard added now would be
speculation with a real cost, because a truncated answer is a useless one.
Revisit if the corpus of questions ever outgrows it, not before.

**Keeping what somebody typed is an obligation, not a side effect of plumbing.**
Both interfaces now say so — a sidebar caption on the page, a line on stderr in
the terminal, the sentence shared through `messages.py` so two drivers cannot
make two different claims. It is not folded into the pinned prototype banner,
which is one line by design; a banner that wraps becomes a block a reader learns
to skip. Retention, redaction and deletion are not answered here: they only
become meaningful once there is an answer to "whose words are these", which
arrives with identity.

**`trace.record` itself still does not catch.** Fail-open (ADR-0710) is a
property of `TrailHandler.emit`, which swallows, and not of `logging`, which does
not wrap `emit` at all. That is unchanged by this change and is asserted at the
real sink rather than assumed; `feedback.py` guards independently for the same
reason.

**A dead destination loses the answer's records before the question ends, and
that is by design.** `FAILURES_BEFORE_GIVING_UP` is 3, and those three are spent
on `question.asked` and the retrieval records that follow it — so when the
database is down, `answer.given` and `answer.evidence` are not written *and are
not even attempted*: the store has already paused for `SCHEMA_RETRY_AFTER_S`.
The reader is unaffected, which is the guarantee. But an operator reading a
half-written question's rows should know the tail is missing because the store
stopped trying, not because these two records are broken. Worth knowing before
somebody debugs the wrong thing; pinned by
`test_a_dead_destination_stops_trying_before_the_answer_is_reached`.

## Where this leaves the data

`sql/feedback.sql` can now show a rating beside the question it judged and the
answer it judged, joined on `question_id` — one query rather than a
reconstruction. That join is the whole point of the change.
