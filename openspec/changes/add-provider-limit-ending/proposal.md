## Why

The app is about to run on a shared host, on one API key with a spending cap, in front of reviewers
and alpha testers. That makes one already-possible ending load-bearing in a way it was not while the
only reader was the developer running the app on their own key: the key runs out of credit.

OpenRouter answers **402** for that — its documentation covers "your account or API key has
insufficient credits" in one sentence, so the same code arrives whether the account is empty or the
key is over its own limit. The agent already catches it: a failure around the loop ends the question
as `provider_failure`, with the evidence it had. Nothing crashes.

But that ending is wrong in two ways for this case, and both are worse in front of a stranger:

- **It says nothing.** `provider_failure` emits no answer, only the ending line —
  `provider_failure (incomplete) · $0.00 · anthropic/claude-haiku-4.5 · 0 tool calls`. A reader
  concludes their question broke something, or that the corpus failed them. Neither is true, and the
  one thing they need to know — somebody has to top up a key — is not on the page.
- **It leaves the door open.** `PROVIDER_FAILURE` is deliberately outside `messages.STOP_THE_RUN`,
  because a gateway that failed once may answer the next call. A spent key will not, so every
  subsequent question fails identically. That is precisely the "reads as a broken app rather than a
  limit reached" failure `run_is_over` exists to prevent, reaching the page through a reason the set
  does not cover.

## What changes

**A reason of its own**, `provider_limit`, joining `messages.STOP_THE_RUN`. Not a flag on the
existing ending and not a different wording for it: whether asking again can come out differently is
a property of the reason, and `STOP_THE_RUN` is already keyed on exactly that.

**A sentence, as an answer**, saying what stopped, what would restart it, and that the reader's
question was not at fault — the shape the run-budget refusal already uses, for the same reason.

**No retries.** A 402 stops being retryable, alongside the spend-ceiling refusal already there: the
key does not acquire a balance during the backoff, so retrying makes the reader wait seconds for a
sentence that was available immediately.

Detection reads the status code and nothing else — not the message text, which belongs to the
provider and would take the rule quietly false the day it was reworded. ADR-0600 records the
decision and the direction the uncertainty is pushed in.

## Deferred

**Per-visitor budgets.** A hosted instance shares one run label, so its budget is one pot and one
visitor can spend another's share. Splitting it means a run label per session, which changes what a
"run" means to the spend ledger and to any evaluation reading it. Out of scope here.

**A friendlier ending for the other provider failures.** `provider_failure` still emits no sentence.
It is the right silence for a transient error a retry may clear, but a reader watching two questions
fail in a row deserves better than a status line. Left alone deliberately: this change is about the
one ending whose remedy is known.
