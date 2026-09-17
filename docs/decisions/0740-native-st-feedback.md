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

## A fourth correction: a rating must not be clickable while the agent works

Reported by a reader, who pressed thumbs-down while an answer was still arriving
and watched the turn stop — the tool call it was in the middle of cancelled, no
further progress, the turn left half-finished.

The mechanism is Streamlit's, and it is not specific to feedback. **A widget is
live in the browser the moment it renders, and a click re-runs the script.** A
re-run abandons the generator `web.answer` is consuming, at whatever `yield` it
had reached — and `agent.py` persists each turn as it goes, so the conversation
the model remembers advances past what the page shows. `answer`'s own docstring
had noted that the generator "can be abandoned at any yield" as a property of
callers; it is also a property of the page, and nothing had drawn the conclusion.

Two windows existed, and only the first was new:

- **The live turn's own control**, drawn at the seam inside the streaming loop.
  Closed by reserving an `st.container()` at the seam and filling it once the
  generator is exhausted. A Streamlit container is bound to where it was made, so
  the control lands exactly where calling at the seam put it, without existing
  while there is still work to interrupt — the same trick the retrieval box
  already used, for the same reason.
- **Every past turn's control**, redrawn by the transcript loop before the new
  question runs. This one predates the columns and shipped with the feature: those
  thumbs were clickable throughout every answer. Closed by asking
  `question_pending` before anything is drawn and passing `answering` down, so the
  whole rating block — thumb, comment box and Send — is drawn inert for the
  duration of the run.

`st.chat_input` is given a key for that question. Streamlit restores widget state
at the top of a run, so the submitted question is readable *before* the
`st.chat_input` call that returns it, which is what lets the page know a question
is coming before it redraws the transcript.

**Disabled, not hidden.** Streamlit discards the state of a widget it did not
render, so skipping the comment box for the duration of a run would take a
half-typed comment with it — the same loss the rating is disabled rather than
re-clickable to avoid.

### What no test here can see

`AppTest` runs a script to completion and cannot click during one, so the defect
itself is unreachable from the suite. Three checkable halves stand in for it: that
the live control is drawn only after the last item is consumed, that
`question_pending` reads a submitted question, and that `answering=True` disables
every control in the block. The wiring between the second and third is verified by
reading, and is named here so the next person knows which link is unpinned.

A chat input is a trigger widget — its value is cleared after each run, and a
value written into session state by hand does not survive to the next one — which
is why the mid-run page state cannot be staged even artificially.

### A fifth: inert *while* a question runs, not inert until something else happens

The disabling above worked, and then stopped working in the other direction.
Reported by the same reader: after asking a second question, the first answer's
rating stayed dead, and came back only when they clicked something — pressing a
thumb on the *new* answer was what woke it.

`answering` is decided at the top of a run and is true for all of it. Nothing
re-drew the page once the agent stopped, so the last frame of the answering run
was the one left on screen, with every older rating in it disabled. Streamlit
re-runs on the next interaction, not when a script finishes.

This is the "run is over" banner's fault exactly — a state decided before the
thing that changes it, left standing until the reader happens to interact. That
branch already ended in `st.rerun()` for its own version of the problem, so the
fix is to stop making it conditional: after a question is answered, the page
re-runs unconditionally. A programmatic re-run clears the submitted question
(verified — a chat input is a trigger widget), so the redraw has `answering`
false and the ratings come back.

**It costs one extra script run per question**, and the redraw is from the
transcript: no question, no model call. That is the same cost this page already
pays for every thumb, expander and text entry, so it is in line with how the app
already behaves rather than a new kind of expense.

**A cost was claimed here that did not exist, and the claim nearly bought a rule.**
The suite appeared to go from about two minutes to 9m12s, and the re-run was made
conditional on there being an older turn to revive. Both timings had been taken
with other test runs competing for the machine. Measured alone, one file: 38.4s
with the redraw, 41.0s without it. The re-run costs nothing, and the condition was
removed again.

Recorded rather than quietly deleted, because the failure is the interesting part.
A timing is a measurement, and a measurement taken on a loaded machine is not one
— the number looked authoritative enough to justify a second rule about when the
page is fresh, which is exactly the kind of rule that outlives its reason. Time a
suite alone, or do not quote the figure.

### What the re-run exposed

The replay path drew a *finished* search under the running label: `show` created
the box with the present-tense "Searching the corpus…" and never relabelled it,
where the live path updates it to "Retrieval" when the answer completes. Every
redrawn turn therefore claimed to still be searching.

It had always been that way and was invisible, because the live render was what a
reader saw after asking and the replay render only appeared on turns they had
scrolled back to. Making the page re-run put the replay render on screen
immediately, and a test that had only ever exercised the live path failed.

Both paths now take the label from one of two constants, so they cannot drift
again — which is what two literals for one string had already done.


### A sixth: the colour rule was aimed at the wrong widget, and then at the wrong state

Found by a read-only verifier, not by the suite, and in two stages.

**Stage one: the selector named a widget that is not on the page.** It read
`[data-testid="stButtonGroup"]`, which is `st.pills` and `st.segmented_control`.
`st.feedback` has its own module, enqueues as `"feedback"`, and the frontend's
`case 'feedback'` loads a separate `Feedback` component rendering `stFeedback` and
`stFeedbackButton`. The rule matched nothing and the thumbs stayed grey — the
state a reader reported and this ADR recorded as deferred cosmetics.

**The test written to prevent exactly that passed.** It asserted the id appeared
in Streamlit's frontend bundle, and it does — in `ButtonGroup.*.js`, for a
different widget. A commit message and a comment both claimed the ids were
"verified against 1.61.1's bundle", and in the only sense the check performed,
they were. A string present somewhere under `static/` says nothing about which
component renders it. The test now reads the wrapper id out of `Feedback.*.js`
specifically and asserts the rule targets something *that* component renders.

**Stage two: fixing the selector broke a requirement.** `answer-feedback` says a
rating once given is shown as settled, and Streamlit provides that — `Feedback`'s
`&:disabled` rule replaces the button's colour with `fadedText40` selected,
`fadedText10` unselected. But it sets that on the *button*, and the icon is a
separate span whose own class declares `color: inherit` at specificity 0,1,0. A
rule painting the icon directly is 0,2,0, so it wins, `inherit` never resolves,
and the disabled colour has nothing to propagate to. There is no `!important` in
that bundle. A corrected selector would therefore have left rated thumbs as bright
as unrated ones, with `cursor: not-allowed` the only surviving signal — a spec
requirement unmet by a stylesheet, which no test of behaviour would ever see.

The rule now declines to apply to a disabled control (`button:not(:disabled)`)
rather than overriding it. Letting Streamlit keep its own state styling also
avoids naming which half of the pair is selected, and `stFeedbackButtonActive` is
the markup most likely to move.

**What this cost, stated plainly.** Three consecutive comments in the source made
three different claims about the disabled state — that the hue survives, that it
does not, and finally why our own rule decides which. Each was written
confidently. The first two were wrong in opposite directions, and nothing in a
green suite distinguished them, because none of it is behaviour a test can run.
Both properties are now pinned structurally, with canaries: dropping
`:not(:disabled)` fails one test, restoring the old wrapper fails the other.
