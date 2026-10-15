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
`hosted_trace.attributed(web.trace_user(admission))`, and underneath it is Langfuse's
`propagate_attributes(user_id=...)`.

The value is **`trace_user`: an HMAC-SHA256 of the lower-cased address, keyed with `[auth]`'s
`cookie_secret`**, truncated to 16 hex characters and prefixed `u-`. The host already holds that key
and never sends it anywhere. The value is stable per account and `None` without sign-in. With no
key to read it is also `None`: there is no fallback to an unkeyed digest. `None` attaches nothing,
rather than a placeholder that would read as an account. The terminal and the harness do not call
it.

**Revised after review, 2026-09-25.** The first version sent `account_scope`, the unsalted SHA-256
the ledger is keyed by. Anyone who guessed a tester's address could compute it and confirm it,
and a handful of named testers is an easy list to guess. The ledger keeps `account_scope`, because
changing it would reset every tester's spend, and nobody outside reads it.

**The session goes to the tracer as a digest too** (`hosted_trace.session_ref`). Without sign-in,
the session is the `?session=` token from the link, and that token opens the reader's
conversation. It was reaching the trace three ways: the propagated session, `run_config`'s
`session_id` metadata, and the `thread_id` LangGraph copies into metadata by itself. The
propagated session is set to the digest. Two Langfuse masks replace the other two, one on the
SDK's calls and one on every exported span attribute. A test searches everything exported for
the raw token.

The evaluation harness uses the same mechanism for a different fact. `run_evaluation` wraps its
questions in `hosted_trace.tagged("eval")`, so an evaluation's traces can be told apart whatever the
run label says, and every caller of it gets the tag. This keeps ADR-0110 intact: the agent is not
told who is calling.

Checked on a real trace (2026-09-25): the digest is on every span, the generations included, and no
`@` appears anywhere in the trace's metadata, user or session fields.

## Trade-off accepted

**The key is `cookie_secret`, which already signs the identity cookie.** Rotating it re-keys every
tester's trace value, so traces before and after a rotation no longer group by reader. That is
accepted: rotation is rare, and the trail is where a reader's history is read from.

**Attribution depends on context propagation** reaching spans that LangGraph creates on worker
threads, across a generator the page advances lazily. Tests assert it on every span, through the
real propagation path with an in-memory exporter. Isolating the stream's context (ADR-1010) is what
stops one reader's attribution from outliving their question.
