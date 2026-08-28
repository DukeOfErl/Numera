# ADR-0120: Spend is enforced in middleware, not asked for in the prompt

- **Status:** accepted
- **Date:** 2026-08-26
- **Pull request:** _pending — `feat/ask-agent`_

## Context

The agent runs against a metered API during development, where a loop that
retries a failing search is not a bug that costs nothing. Something has to stop a
question that is spending without converging.

Asking the model to stop is the cheap option and does not work: an instruction is
not a control. This project has direct evidence — the prompt names conversions and
ratios as things that must be declared computed, and a live answer converted three
values without declaring any of them. A model that ignores an explicit formatting
rule will ignore a budget.

LangChain v1 agents accept middleware with hooks around each step of the loop, and
the wrapping hooks may invoke the handler **zero** times, which short-circuits the
call.

## Decision

The spend ceiling is a **`wrap_model_call` middleware** that reads accumulated
spend and declines to call the handler once the ceiling is reached — the Decorator
pattern applied exactly where dispatch happens. Reaching the ceiling ends the
question and presents what was established, with its citations, marked incomplete.

Cost comes from the provider rather than a local table (OpenRouter reports it at
`response_metadata["token_usage"]["cost"]`, verified 2026-08-18 as needing no
per-request opt-in). A configured price table is the fallback for a provider that
reports only tokens, and the system refuses to start when it has neither.

The run budget is the same mechanism at a coarser scope — a **circuit breaker**
that stops the run rather than spending through a systematic fault.

## Trade-off accepted

This is an **interim mechanism, not a billing control**. It bounds what this
process spends; it knows nothing about what was spent by another process, another
machine, or a request that failed after the provider had already charged for it.
It is a development-stage guard, and anything user-facing needs a real quota
enforced at the account.

It also puts a hard stop where a person might have wanted one more call. That is
the intended failure direction: an incomplete answer that says it is incomplete is
recoverable, and an unbounded bill is not.
