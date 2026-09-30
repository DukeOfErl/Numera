## Why

A visitor who has not signed in meets a sentence and a button, and nothing that shows
what the app does. The people it is meant for, biologists invited to try it, decide
whether it is worth signing in from exactly that page.

## What Changes

- **The sign-in door plays recorded examples on a loop.** Each one types a question
  into a mock input, sends it, and streams the answer back. The first types "What
  is the number of ribosomes in an e.coli cell?", takes back its last three words,
  and completes it as a comparison with budding yeast.
- **Every example is real.** It is a question actually put to the agent and its
  answer, verbatim, labelled as recorded with the model and the date (ADR-1210). A
  test holds the typed text to the question that was answered.
- **Two examples, not three.** A third, a distribution drawn as a text chart, was
  tried live twice and rejected on evidence: the model miscounted, then misplaced
  every bar on its own axis. It waits for application-drawn charts (roadmap).
- **The examples are committed**, a bounded exception to ADR-0170 (ADR-1200).
- Only on the sign-in door: not on a door that refuses an account, and not after
  sign-in. Reduced motion shows each example whole. Pointing at the frame pauses
  the loop, and the frame scrolls.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-identity`: *"A reader signs in before anything is shown, and identity comes
  from the provider"*: the recorded examples become the one exception to "sign-in
  and nothing else", and the exception is narrow: nothing is produced for the
  visitor.
- `user-identity`: a new requirement, *"The sign-in door may play recorded
  examples, and they are real and say so"*.

## Impact

**Code.** New `door_demo.py` (presentation) and `door_demo.json` (the examples).
`web.py`: `draw_examples`, called from the sign-in branch of `draw_closed_door`.
Drawn with `st.iframe`, which Streamlit 1.61.1 names as the replacement for the
deprecated `st.components.v1.html`.

**Tests.** `test_door_demo.py`; three driver tests in `test_web_driver_identity.py`;
`door_demo` joins `PRESENTATION` in `test_driver_independence.py`.

**Not tested by the suite.** The animation itself: typing, erasing, streaming, the
pause while pointed at, reduced motion, dark mode and phone width. All of it was
driven in headless Chromium, with a no-hover baseline for the pause, and looked at.
