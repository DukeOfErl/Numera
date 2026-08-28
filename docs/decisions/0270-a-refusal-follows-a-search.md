# ADR-0270: An answer with no retrieval behind it is a defect, not a wording choice

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _pending — `feat/ask-agent`_

## Context

Asked something the corpus does not cover, the agent ended `answered · 0 tool
calls` and said:

> I cannot find information about the airspeed velocity of an unladen swallow in
> this corpus… **based on my searches through the available data**, this topic does
> not appear to be covered.

No search ran. Two separate faults sit in that.

**A refusal with no retrieval is not about the corpus.** It reports what the model
expected to find. This project exists precisely so that answers rest on retrieved
entries rather than on the model's priors, and a refusal is an answer. Its error
is also invisible in a way a wrong number is not: an entry that was never sought
looks exactly like one that is absent, so a reader cannot distinguish *not in the
corpus* from *not looked for*, and neither can an evaluation set scoring refusals.

**The prose asserted a process that did not occur.** The ending carried
`tool_calls: 0` at the same moment the answer described searches. The harness had
the truth and the text the reader sees did not, which is the same shape as an
unsupported citation: a claim the system can check against its own record and was
not checking.

## Decision

**Search before refusing, asked for in the prompt.** The rule now precedes the
existing "say you could not find it" rule, because the order matters: *I did not
find it* is only true if you looked.

**An answer with nothing retrieved emits `UngroundedRefusal`**, carrying
`claimed_searching` where the prose also described searching. Both drivers render
it through the shared wording, as a warning beside the answer.

**Detected from the count, not from the content.** `tool_calls` is already on the
ending, so this needs no judge and no second model. The phrase list that sets
`claimed_searching` is only consulted where the count is already zero, so a phrase
it misses understates the report and can never manufacture one.

**Reported, not suppressed.** The answer is still shown. Hiding it would leave the
reader with nothing and tell them less than a flagged answer does.

## Trade-off accepted

**A literal phrase list will miss paraphrases.** "Having looked through the
entries" is not in it. Accepted because the consequence is asymmetric: a miss
downgrades an `UngroundedRefusal` from *claimed searching* to *retrieved nothing*,
and the second is still reported. The alternative — asking a model whether an
answer claims to have searched — spends money to make a checkable fact
probabilistic.

**A legitimate no-retrieval answer is flagged too.** A follow-up answerable
entirely from the conversation retrieves nothing and now carries a warning. This
is the accepted cost: the requirement that every answer cite entries in full
already means such an answer should be re-citing, and the flag is a warning rather
than a refusal.

**The prompt is asked to do work the code does not enforce.** Nothing prevents the
model answering without searching; the code reports it afterwards. Enforcement —
rejecting the answer and re-prompting — would cost a model call on every false
positive, and the reporting path makes the failure visible to the evaluation set
that group 9 will build, which is where the frequency should be measured before
anything more expensive is chosen.
