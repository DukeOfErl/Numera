# ADR-0600: A provider out of credit is its own ending, not a provider failure

- **Status:** accepted
- **Date:** 2026-09-07
- **Pull request:** — (branch `feat/provider-limit-ending`)

## Context

Every ending already carries a reason, and a failure around the agent loop was
told apart two ways: ours (`internal_error`) or the provider's
(`provider_failure`). That split is about *whose fault it is*, and it was the only
question worth asking while the only reader was the developer running the app on
their own key.

Deploying the app to a shared host makes a third case load-bearing. The key
funding a hosted instance has a spending cap, and OpenRouter answers **402** when
it is reached — documented in one sentence covering both an account with no
credits and a key over its own limit. Reported as `provider_failure`, that arrives
as a terse ending line: `provider_failure (incomplete) · $0.00 · …`. A reader sees
no sentence at all, and the two things they would conclude are both wrong — that
their question broke something, or that retrying might work. Worse, the door stays
open: `PROVIDER_FAILURE` is deliberately absent from `messages.STOP_THE_RUN`
because a gateway that failed once may answer the next call, so every subsequent
question fails identically. That is the "reads as a broken app rather than a limit
reached" failure `run_is_over` was written to prevent, arriving through a reason
the set does not cover.

Three options were on the table. Reuse `PROVIDER_FAILURE` and vary the wording:
rejected, because the wording is not the part that matters — whether the run is
over is, and that is a property of the reason. Add a flag to the ending
(`permanent=True`): rejected, because every driver would have to learn to read a
second field alongside a reason that already exists to answer exactly this. Or a
reason of its own, which is what `STOP_THE_RUN` is keyed on.

## Decision

`EndReason.PROVIDER_LIMIT`, and it joins `messages.STOP_THE_RUN`.

A 402 also stops being retried (`_retry_on`), for the reason a spend-ceiling
refusal already is not: the key does not acquire a balance during the backoff, so
retrying buys the reader seconds of waiting for a sentence that was available
immediately.

The ending is accompanied by an `Answer` carrying the sentence — what stopped,
what would restart it, and that it was not the reader's question — rather than
leaving the ending line to imply it. This follows the run-budget refusal, which
does the same thing for the same reason.

Detection reads `status_code == 402` and nothing else, deliberately not the
message text: the wording belongs to the provider and a rule matching on prose
goes quietly false the day it changes.

## Trade-off accepted

**The rule is a classifier, so it moves things in both directions**, and the
directions do not cost the same. A transient failure misread as a spent key closes
the run for everyone on a reason that was not true; a spent key misread as a
transient failure costs one pointless retry and then says the same thing again. So
the rule is deliberately narrow — an unambiguous 402, nothing inferred — and the
cheap direction absorbs the uncertainty. Both directions are asserted:
`test_a_key_out_of_credit_says_what_happened_and_stops_the_run` covers the
under-flagging side, and `test_exhausted_retries_end_the_question_as_a_provider_failure`
now asserts that an outage does *not* end up in `STOP_THE_RUN`. Seeding each
mutation of the rule into a copy fails exactly one of those two.

What is given up: a 402 that a provider ever returns for something *other* than
credit would be reported as a spent key, and the run would close on it. Nothing in
OpenRouter's documented codes does that today.

`status_code` is an attribute of the provider's own error type, which this project
does not own. `test_the_attribute_this_rule_reads_is_on_the_provider_s_own_error`
builds a real `openai.APIStatusError` rather than a stand-in carrying the
attribute, so a rename fails a test here instead of silently sending every spent
key back to being an ordinary outage.
