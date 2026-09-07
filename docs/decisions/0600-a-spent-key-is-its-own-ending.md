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

**The answer stays the model's.** Whatever text the model had produced is
presented and the ending marks it incomplete, exactly as the spend-ceiling branch
beside it does — and this is the branch where that matters most, because a balance
usually runs out part-way through a question whose earlier hops were already paid
for, which makes the discarded-answer case the common one rather than the corner.
Only where there is no text does the agent substitute a sentence of its own, and
that sentence states the fact — the provider refused the request because the key or
account funding it has no credit left — without saying whose key it is.

**What to do about it is the drivers' sentence, not the agent's.** Which key, whose
money, and who can top it up are facts about a *deployment*: the agent has no
standing to assert them, and a developer running this locally would be told to
contact themselves. `messages.run_over_advice(reason)` carries the wording, shared
for the reason the rest of that module is — the terminal and the page are answering
one question, "may I ask again, and if not what would help", and two drivers
phrasing that differently are two claims about one fact. It is keyed per reason and
returns `None` for every ending whose existing wording is already right.

That also repairs a banner this change would otherwise have broken. The page's line
for a closed run is "start a new session to continue", which is true of a spent
budget and false of a spent key — the next session's first question meets the same
refusal — and the banner is the last thing on screen, so it outranks the answer
that has just said otherwise. `NOT_CONFIGURED` joins the table for the same reason,
where the line was already wrong before this change: a missing credential, or a
spend that cannot be accounted for, meets the reader again on the first question of
any new session.

**The wording addresses nobody.** "Ask whoever deployed the app to raise it" was the
first attempt and reproduced, in the drivers, the absurdity that moving the sentence
out of the agent was meant to end: the terminal is the driver a developer runs on
their own key, so that sentence told the funder to contact themselves. Naming the
remedy without a second person — "the limit has to be raised by whoever funds it" —
reads correctly to a visitor and to the funder alike, and the spec now requires that
rather than leaving it to whoever next edits the string.

**Judgements about prose apply only to prose the reader saw.** `evidence()` takes
`judge_the_prose=False` where the answer shown is the agent's substitute. Run over
a substitute it reported on writing that was never on screen: a citation warning
naming an entry the discarded text had cited, or "this answer is not grounded in
the corpus — it says only what the model expected to find" about a system notice,
with `answer.ungrounded` in the trail for a question the model never answered. The
entries table is not a judgement about prose and is still emitted, because what
retrieval found before the stop was paid for too.

Detection reads `status_code == 402` and nothing else, deliberately not the
message text: the wording belongs to the provider and a rule matching on prose
goes quietly false the day it changes.

## Trade-off accepted

**The rule is a classifier, so it moves things in both directions**, and the
directions do not cost the same. A transient failure misread as a spent key closes
the run for everyone on a reason that was not true; a spent key misread as a
transient failure costs one pointless retry and then says the same thing again. So
the rule is deliberately narrow — an unambiguous 402, nothing inferred — and the
cheap direction absorbs the uncertainty.

**Both directions are asserted, and the first version of this ADR claimed that
before it was true.** The negative cases were `RuntimeError` and `TimeoutError`,
neither of which carries a status at all, so nothing distinguished "status is 402"
from "has a status": a review seeded `status_code is not None` and the whole suite
passed, under which an ordinary 429 rate limit or a 502 would close the run for
every reader — the exact failure this section says is covered. The negatives are now
real `openai.APIStatusError`s at 429, 502 and 401, and three mutations of the rule
each die against the test that should catch them (`return False` the out-of-credit
tests, `return True` the exhausted-retries one, `status_code is not None` the
attribute test). The lesson is narrower than "test both directions": a negative case
has to differ from the positive one *in the dimension the rule reads*.

What is given up: a 402 that a provider ever returns for something other than credit
would be reported as a spent key, and the run would close on it. Nothing in
OpenRouter's documented codes does that today.

**The door is shut per session, not per deployment.** `run_is_over` reads the
transcript in Streamlit's session state, so a reader who opens a new tab may ask
once more — and immediately gets the same refusal and the same advice. Closing it
process-wide means shared state between sessions, which this build does not have;
the spec is written to the behaviour rather than the intention.

`status_code` is an attribute of the provider's own error type, which this project
does not own. `test_the_attribute_this_rule_reads_is_on_the_provider_s_own_error`
builds a real `openai.APIStatusError` rather than a stand-in carrying the
attribute, so a rename fails a test here instead of silently sending every spent
key back to being an ordinary outage.
