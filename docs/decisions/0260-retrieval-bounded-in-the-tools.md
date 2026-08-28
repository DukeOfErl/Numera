# ADR-0260: Retrieval is bounded in the tools, and exhaustion is a tool result

- **Status:** accepted
- **Date:** 2026-08-28
- **Pull request:** _pending — `feat/ask-agent`_

## Context

`grounded-answering` has required from the start that the system bound "the number
of tool calls made in answering a single question". What the code bounded was
model calls — `ModelCallLimitMiddleware(run_limit=12)` — and `at_retrieval_bound`
reported those. The spec and the implementation had been describing different
quantities, and nothing noticed because on most questions the two move together.

They came apart in live use. A model may request several tools in one assistant
message, so twelve model calls bought **twenty-nine retrievals across seventeen
searches** on a single question. It spent $0.27 and took the run from $0.91 to
$1.18 of its $1.20 budget: one question consuming a fifth of a run.

The only thing that stopped it was the spend ceiling. That is the wrong instrument
for this. Cost is a consequence of searching too much, not the thing being
limited, so the report named the symptom; and a cheaper model would have run the
same loop further before anything intervened.

## Decision

**A retrieval budget, held by the tools, spent by each call.** `ToolBudget` is
constructed per question and passed to `build_tools`. Every tool takes one call
from it before doing any work. The limit is 20 — answers that satisfied their
question used about five, the runaway used twenty-nine.

**Exhaustion is returned to the model, not raised.** The tool returns a sentence
telling it to answer now from what it already retrieved, cite it, and say the
answer may be incomplete. Raising would end the question, discarding retrieval
that was already paid for; the spec asks for the opposite — "what had been
established so far is still presented with citations".

**A declined call is still an event.** It emits a `Retrieval` carrying `declined`,
so it appears in the progress a reader sees and in the tool count. A call the
model made and was refused is part of what happened to the question, and a
progress trail that omits it describes a question that behaved differently.

**Reported like the bound beside it.** `QuestionEnded` carries `tool_call_limit`,
`at_tool_bound` is exact rather than within a margin, and the ending line names
the figure only where the bound was reached — the same rule the model-call bound
already follows, for the same reason.

**The model-call limit stays.** It bounds a different failure: a loop that calls
the model repeatedly without ever calling a tool.

## Trade-off accepted

**Twenty is chosen, not derived.** It is a number to tune against real questions,
and a genuinely hard question that needed twenty-five will now be cut short. That
is visible rather than silent — the ending says so and the answer says so — which
is the property that makes a wrong limit findable.

**The bound is not verified live.** The question that produced twenty-nine calls
came back in seven on the next run, so the cap has only been exercised offline,
against a scripted model batching five calls into a limit of three. What live use
showed is that the old bound did not bind, not that this one does.

**Two limits to understand instead of one.** A reader now has model calls,
retrievals, a per-question spend ceiling and a run budget. Accepted because they
fail differently and a single number would have to be the minimum of all of them,
which is the arrangement that made this defect invisible in the first place.
