## Why

Nothing in this system records what a reader thinks of an answer. The corpus is
retrieved, the prose is generated, the entries are shown — and whether any of it
was useful is known only to the person who read it, and only for as long as they
remember.

That gap makes the alpha a demonstration rather than an experiment. Every other
judgement available is mechanical: whether an answer cited something, whether it
retrieved before answering, whether a value is dimensionally plausible. None of
them can say the answer was wrong in a way that mattered, and a scientist reading
a number they know to be off is the only instrument that can.

Now, because the identifiers a rating has to name landed in the previous change
and cannot be retrofitted onto answers already given.

## What Changes

- A reader can **rate an answer up or down**, and add **an optional comment**
  that appears only once they have rated.
- Ratings are **durable**, keyed to the question they are about, so a rating can
  be read back beside the trail of what that question actually retrieved.
- The comment prompt **asks for a problematic entry's identifier by name**. This
  is how a per-row rating gets decided later — by mining what people actually
  complain about, rather than by guessing at a UI first.
- **Rating is not required.** An unrated answer is the normal case and must cost
  the reader nothing.
- **No behavioural change to answering.** The agent, its tools, its limits and
  its spend accounting are untouched.

## Capabilities

### New Capabilities

- `answer-feedback`: what a reader may record about an answer, when they may
  record it, what must be kept with it, and what the system must not do with it.

### Modified Capabilities

None. Answering is unchanged; this only adds a way to record a judgement of it.

## Impact

- `scinumbers_ask/web.py` — the widget, its keying, and the decision of what to
  record. `Item` already carries `question_id`.
- `streamlit_app.py` — where the widget is drawn relative to the rest of a script
  run, which is the part no test below the driver can see.
- `scinumbers_ask/trail_store.py` — feedback is a new `event` value in the
  existing append-only table. No migration: a new kind of record is a new value,
  which is what that shape is for.
- A hosted tracer receives the verdict as well, as a convenience for whoever is
  debugging a run. **It is not the record** — see design.md.
- **Not affected**: the agent, the corpus, the evaluation harness, the spend
  gate.

## Out of scope

Each is a natural next thought, and naming them is how they stay out:

- **Per-row ratings.** Deliberately deferred rather than forgotten: the comment
  field is the instrument for finding out whether they are worth building. The
  design must not foreclose them.
- **Authentication and identity.** Ratings carry no person yet. The column for
  one exists and stays null; the next change fills it.
- **Comparing two answers to the same question.** A different instrument with a
  different UI, and it needs answers to compare.
- **Any aggregation, dashboard or report** over what is collected. The data is
  read with SQL by the people who built it, until there is enough of it to be
  worth more.
- **Acting on a rating** — no retry, no re-ask, no adjustment to retrieval. A
  rating is evidence, and this change only gathers it.
