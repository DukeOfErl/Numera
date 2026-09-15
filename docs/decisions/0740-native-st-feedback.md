# ADR-0740: The rating widget is Streamlit's own, not the component that does exactly this

- **Status:** accepted
- **Date:** 2026-09-15
- **Pull request:** _pending — `feat/answer-feedback`_

## Context

A reader needs to rate an answer and optionally say why, with the text box
appearing only once they have rated. Two options do this.

`streamlit-feedback` (trubrics) is purpose-built for it and has every feature
wanted, including `optional_text_label` and `review_on_positive=False` so text is
requested only on a negative. It is also a **custom component**: a prebuilt
JavaScript frontend talking to Streamlit over a component API. Checked on
2026-09-15 rather than recalled:

- Last commit and last release are both **2025-01-13**, twenty months old.
- **26 open issues**, oldest from September 2023, none triaged recently.
- Declares `streamlit>=0.63` with no upper bound and **no claim about 1.61.x**,
  the version installed here; Streamlit has moved twenty-four minor versions
  since that release.
- Open issues report the familiar custom-component failures — *"having trouble
  loading the streamlit_feedback component"*, *"Bad 'setIn' index"* in multi-turn
  chat, a missing submit button, invisible on iOS — and one reports that **the
  released wheel contains JavaScript built from previous versions**.

`st.feedback` has shipped natively since Streamlit 1.37.0. It gives thumbs and
nothing else: no text box, no submit, no callbacks beyond the ordinary widget
ones.

## Decision

Native `st.feedback`, with the conditional text area written here.

The only thing the third party buys is that conditional text area, which
natively is an `if verdict is not None:` guard — roughly twenty-five lines. That
is not worth a stale prebuilt frontend on a deployed app.

Three behaviours of the installed widget were established by reading
`streamlit/elements/widgets/feedback.py`, not its documentation, and the design
accommodates all three:

1. **Clicking the selected thumb clears it.** The source returns `None` for an
   empty value, with the comment *"User explicitly cleared"*. A text area
   conditional on the verdict therefore disappears — and Streamlit discards the
   state of a widget it did not render, taking a half-typed comment with it. So
   the control is disabled once a verdict is held, and the comment is kept
   outside widget state.
2. **It must sit outside any `st.form`.** Inside one, widgets do not re-run until
   the form submits, so the verdict reads `None` until then and a conditional
   text area can never appear at all.
3. **The verdict is committed on the click**, through the widget's change
   callback, rather than when a comment is submitted. Most readers who rate will
   do nothing further, and a design that waits for a second action to commit the
   first collects nothing from them.

## Trade-off accepted

Twenty-five lines of widget code to maintain, against a dependency that would
have written them. Worth it while that dependency ships a frontend built against
a component API two years older than the Streamlit running it.

The judgement is about *this* package's staleness, not about custom components.
A maintained equivalent would be worth reconsidering.

## What the collected ratings do not measure

**A thumbs-down rate is not an error rate.** People who rate are not a sample of
people who read: a reader who spots a wrong number is far likelier to say so than
one whose answer was fine, and both are rarer than the reader who says nothing.
The numbers here support "what do people complain about", and will not support
"how often is it wrong".

Recorded in the decision rather than beside the query, because the first person
to quote a percentage from this data will have found it somewhere else.
