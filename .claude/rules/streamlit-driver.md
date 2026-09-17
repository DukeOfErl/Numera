---
paths:
  - "streamlit_app.py"
  - "src/scinumbers_ask/web.py"
  - "tests/test_web_driver*.py"
  - "tests/test_streamlit*.py"
---

<!-- Moved out of CLAUDE.md. Applies only to the web driver and the tests that
     drive it. -->

# When something is drawn is a driver-level question

A change to *when* an element is created, relative to the rest of a script run, cannot be seen below
the driver. `web.items_for` decides what the page says and is tested directly (ADR-0100), but the
order and the lifetime of the elements themselves belong to `streamlit_app.py`, which Streamlit
re-runs from the top on every interaction. **Drive the real script through `AppTest` for those.**

There is a production incident to cite. The "this run is over" banner was decided before
`st.chat_input`, so on the run that ended the conversation the ending did not exist yet and the
banner appeared one interaction late — never, for a reader who stopped there. `run_is_over` and
`ends_the_run` were correct throughout and every item-level test passed; the first real question put
to the deployed app found it. The same blindness hides an element drawn unconditionally that should
not have been drawn at all, which is how the empty "Retrieval" box survived.

This does not contradict the scoping rule above. Driver bugs still announce themselves to the first
person who looks, so they do not earn a seeding budget — the point is only that the person looking
has to be looking at a whole script run, and `AppTest` is the cheapest thing that is.
