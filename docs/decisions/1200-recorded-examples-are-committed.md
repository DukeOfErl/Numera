# ADR-1200: The door's recorded examples are committed, a bounded exception to ADR-0170

- **Status:** accepted
- **Date:** 2026-09-30
- **Pull request:** _pending — `feat/door-demo`_

## Context

The sign-in door plays recorded questions and their answers (ADR-1210). An answer
quotes corpus values and cites entries by number, so the examples are corpus-derived
text. ADR-0170 keeps the corpus outside every repository, because its licence for
redistribution is unresolved and a file committed in any of the three checkouts
publishes from all of them. That is also why `evaluations/` is git-ignored.

Two options:

- **Keep the examples outside the repository**, supplied at run time like the
  corpus, with the door showing no examples when the file is absent. ADR-0170 would
  stay intact, but every deployment would need one more file placed beside it, and
  the Streamlit Cloud deployment would need a way to receive it.
- **Commit them**, as ADR-0170 already does for the six-entry test sample.

## Decision

The examples are committed, in `src/scinumbers_ask/door_demo.json`. Yoav chose this
on 2026-09-30.

The exception is bounded, and these limits are the decision:

- **Answers, not entries.** What gets committed is an answer the agent gave, verbatim.
  No entry's reference, method or comments get committed beyond what that answer
  itself quotes.
- **A handful.** Two examples today and a third planned. ADR-0170's sample note
  applies here too: this is not a licence to commit a larger slice.
- **Shown before sign-in.** The door is public, so these answers are readable by
  anyone with the link. Signed-in readers already see the same kind of text; the
  difference is the audience, and the decision is made knowing that.

## Trade-off accepted

ADR-0170's rule is weaker by one file. Anyone later adding an example must weigh the
same question, and nothing checks that they do: no test bounds the count. In return the door works on every deployment with nothing extra placed beside
it. If the licensing question is ever settled against redistribution, this file is
the first thing to remove, and the door then plays nothing.
