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

## Three corrections after the first real use

The design above was right about the widget and wrong about three things around
it. All three were found by a person using the deployed page, not by the suite —
which is the expected division of labour for a driver, and the reason this change
carries `AppTest` coverage rather than a seeding budget.

**The comment box now opens on disapproval alone.** It opened on either thumb,
and the hint reads *"What was wrong?"* — a question nobody can answer about an
answer they have just approved, and which reads as the click not having
registered. The alternative was to soften the hint to cover both, which was
rejected: the hint's job is to ask for an entry identifier from the one reader
who has a specific complaint, and a wording vague enough to suit approval asks
that reader for nothing in particular. Approval stays the cheap signal, and the
point of a cheap signal is that it asks for nothing further.

The cost is that free text praising an answer can no longer be given. Nobody had
offered any, and the evidence this is collected for — which entries readers say
are wrong — does not come from there.

**The rating sits at the foot of the prose, not after everything.** The table was
unbounded — one answer could fill the screen with it — so a control below it was
one the reader had to go looking for at exactly the moment they had formed the
view it asks about. Both drawing paths use one predicate (`_ends_the_prose`),
because the live path and the replay path draw the same turn in two places and a
seam computed twice is a seam that moves.

That reasoning is now partly spent: [ADR-0760](0760-an-answer-is-two-columns.md)
moved the table into its own column, so it no longer pushes anything downwards.
The placement is kept for the plainer reason — a reader forms a view at the end of
the prose — and the ADR records the demotion rather than leaving an argument
standing that the layout has retired.

**The comment box is a form, which is the only way one action sends it.** A plain
text area beside a plain button takes two: typing leaves the value uncommitted,
the first Ctrl+Enter or click commits it and re-runs, and only a second press
sends. `disabled=not text.strip()` on the button made it worse rather than better
— the first click then landed on a disabled control and did nothing at all, so the
reader saw no response whatsoever.

This does not contradict trap 2 above. The *thumb* must stay outside a form, or
it reads `None` until submit and the box can never appear conditionally. The text
and its button are a different matter: submitting several widgets as one act is
what a form is for, and it is the framework's own answer rather than a hand-rolled
one. The button is left enabled on empty text, because disabling it is what costs
the extra action; pressing Send with nothing typed records nothing.

`AppTest` cannot see the two-action problem — it sets widget values directly and
never blurs anything — so what the test asserts is the structure that prevents it:
that the text area and the Send button share a form id.
