# ADR-0180: A limit is configured where it binds, measures what it protects, and is reported when it is reached

- **Status:** accepted
- **Date:** 2026-08-27
- **Pull request:** _pending — `feat/ask-agent`_

## Context

Four limits bound a question: model calls per question, messages per session,
spend per question, spend per run. They were added at different times and ended
up expressing themselves in three different shapes, which showed up as three
separate confusions in one session of using the app.

**The spend limits are configured from the wrong end.** `BIONUMBERS_ASK_WARN_USD`
sets the warning, and the hard stop is derived from it as `warning * 12 // 10`.
So the number a person configures is the one that does not stop anything, and the
number that does is 20 per cent above it and never named. Asked where the
per-question hard limit was, a reader of `config.py` concluded there wasn't one.
The conversation bound already does the opposite — `CONVERSATION_BOUND = 60` with
`CONVERSATION_WARN_AT = 0.75` — and that reads correctly.

**The conversation bound counts the wrong thing.** Its own comment says the
hazard is context length; the mechanism counts messages. Measured over the
corpus, one retrieved entry's payload runs from 16 characters to 8,023 — p50 557,
p99 2,353, a 14x spread between the median and the largest — before counting a
capped search result of 25 rows in a single message against a five-word question.
Sixty messages is therefore anywhere from a few thousand tokens to well over a
hundred thousand. The bound fires far too early in a cheap session and possibly
too late in an expensive one, which is the failure it exists to prevent. Its
comment calls 60 "a number to tune against real sessions", and no real sessions
have been measured.

**An answered question does not say whether it ran up against a limit.** A
question whose spend crossed the ceiling on its final model call ends `answered`
and looks identical to one that used a fraction of its budget. The gate checks
before each call and cannot check after — a call's cost is unknown until it
returns — so overshoot by up to one call is inherent, not a defect. But
`QuestionEnded` already solves exactly this for the retrieval bound with
`at_retrieval_bound`, on the stated reasoning that "an answer produced with no
room left to search is a different thing from one produced with room to spare,
and the two are otherwise indistinguishable". Spend has the same property and
does not report it.

## Decision

One rule, three consequences.

**A limit is configured where it binds.** The configured number is the one that
stops work; the warning is derived from it as a fraction. The per-question spend
ceiling becomes the configured value with the warning at 80 per cent of it,
matching `CONVERSATION_BOUND` / `CONVERSATION_WARN_AT`.

**A limit measures the resource it protects.** The conversation bound moves from
a message count to the conversation's token count, read from the provider's
reported `prompt_tokens` — which is exactly the size of what was sent — against a
configured budget.

**A limit is reported when it is reached, and only then.** `QuestionEnded` gains
a spend equivalent of `at_retrieval_bound`, so an answered question that ran to
its ceiling says so and is distinguishable from one that finished with room to
spare.

## Trade-off accepted

**The configuration key changes meaning.** `BIONUMBERS_ASK_WARN_USD` names the
warning; the replacement names the ceiling. Anyone carrying the old variable gets
a limit 20 per cent lower than before, silently, unless the old name is rejected
outright — which is what will be done, since a spend limit that quietly tightens
is worse than one that refuses to start.

**Token counting is model-specific and retrospective.** An approximate count
depends on the tokeniser, so a bound expressed against a context window becomes
another per-model figure to keep current, beside the fallback price table. And
`prompt_tokens` describes the call that already happened, so the warning and the
refusal both arrive one call late. That is accepted for the same reason the spend
ceiling's one-call overshoot is: measuring the real quantity late beats measuring
a proxy on time.

**Three reporting states cost more than two.** Every driver and eventually the
evaluation harness must distinguish answered, answered-at-the-ceiling, and
stopped-at-the-ceiling. The alternative is the present state, where the middle
case is invisible and a reader has to know the threshold and do the arithmetic.
