# ADR-1020: Attribution is an opaque digest, attached by the driver

- **Status:** accepted
- **Date:** 2026-09-24
- **Pull request:** _pending — `feat/hosted-tracing`_

## Context

A trace is most useful when it can be filtered to one reader. The tracer is a third party.
ADR-0820 settles that the agent is handed a credential and nothing else about the person.
`test_driver_independence.py` enforces this over `agent.py`, `trace.py` and `feedback.py`, and now
over `hosted_trace.py` as well.

Three ways to put a reader on a trace were considered:

- **The address.** This sends personal data to a third party for a purpose a stable key serves
  just as well.
- **A parameter on `AskAgent`.** ADR-0820 refuses exactly this. `budget_scope` carries the same
  digest, but it is a funding scope, and reading it as "who asked" is the conflation that ADR
  warns about.
- **The trail's own pattern.** Identity is stamped at the sink by the driver, and the agent never
  sees it.

## Decision

**The web page wraps its consumption of `agent.ask` in `web.attributed(admission)`.** That call is
`hosted_trace.attributed(account_scope(admission))`, and underneath it is Langfuse's
`propagate_attributes(user_id=...)`.

The value is `account_scope`: the first 16 hex characters of the SHA-256 of the account's address.
It is stable per account, already computed for the ledger, and `None` without sign-in. `None`
attaches nothing, rather than a placeholder that would read as an account. The terminal and the
harness do not call it.

The evaluation harness uses the same mechanism for a different fact. `eval_cli` wraps its run in
`hosted_trace.tagged("eval")`, so an evaluation's traces can be told apart whatever the run label
says. This keeps ADR-0110 intact: the agent is not told who is calling.

Checked on a real trace (2026-09-25): the digest is on every span, the generations included, and no
`@` appears anywhere in the trace's metadata, user or session fields.

## Trade-off accepted

**The digest is an unsalted hash of an address.** Anyone who already knows a tester's address can
compute it and recognise their traces. A keyed HMAC would close that. It is deferred because the
tracer is not an adversary, the testers are a handful, and the point is not publishing addresses,
not anonymity. If the tracer's audience widens, this is the next step.

**Attribution depends on context propagation** reaching spans that LangGraph creates on worker
threads, across a generator the page advances lazily. Tests assert it on every span, through the
real propagation path with an in-memory exporter. Isolating the stream's context (ADR-1010) is what
stops one reader's attribution from outliving their question.
