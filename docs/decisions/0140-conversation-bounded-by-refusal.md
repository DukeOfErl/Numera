# ADR-0140: Conversation is bounded by refusal, not by condensing

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

A session's conversation lives in the checkpoint and grows with every question.
Unbounded, it eventually exceeds the context window; the question is what to do as
it approaches that.

The framework ships `SummarizationMiddleware`, which condenses older turns and is
the better long-term answer — the session continues indefinitely and the user
notices nothing.

That is the problem. This agent's contract is that every quantity carries a
citation to an entry that was actually retrieved. A summariser that drops the
entry a later answer depended on does not produce a visible failure; it produces a
**confident answer with a missing or wrong citation**, which is precisely the
failure mode the whole design exists to prevent, arriving through the mechanism
meant to be invisible.

## Decision

Growth is bounded by **warning as the bound approaches and refusing further
questions once it is reached**. Nothing is discarded silently. A session that has
filled up is ended, and a new one started.

Cross-session memory does not exist: there is no personalisation that changes a
correct answer, so it has no work to do until user accounts do.

## Trade-off accepted

A long session stops working, and the user has to start another and lose the
thread. That is a worse experience than summarisation would give, and it is
accepted because the alternative trades a visible limit for an invisible
correctness risk.

Condensing is not rejected permanently — it is deferred until the evaluation
harness can measure whether a summarised session still cites correctly. Until
there is a number for that, refusing is the honest option.
