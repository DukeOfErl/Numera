# ADR-1010: Tracing is a project setting, and a vendor's own switch is refused in the operation

- **Status:** accepted
- **Date:** 2026-09-24
- **Pull request:** _pending — `feat/hosted-tracing`_

## Context

`langsmith` is installed as a dependency of `langchain-core`. LangChain attaches a LangSmith tracer
to every run whenever `LANGSMITH_TRACING` (or the legacy `LANGCHAIN_TRACING_V2`) is true. So one
variable, set by anyone in any shell or secrets box, sends prompts, tool results and corpus text to
a US-hosted service. The roadmap recorded this as a hazard to close, not a feature to use.

Langfuse, the tracer chosen (ADR-1000), reads its own keys from the environment too. Keys being
present is not the same as someone having decided to send data.

## Decision

**Tracing is on only when `SCINUMBERS_TRACING=langfuse` and all three of `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` are set** (`hosted_trace.read_setting`).

- Anything else is **off**: unset, `off`, an unrecognised value, a missing key. When the setting
  was clearly meant to do something, the operator is told once per process which value or which
  key was the problem.
- **It never refuses to start.** Telemetry must not become an outage (ADR-0710).
- **The host is required rather than defaulted,** so the region a deployment sends to is written
  in its own configuration.

**The vendor's switch is refused where the question is answered, not in a driver.** `AskAgent`
advances its stream inside `hosted_trace.Isolated`, a private copy of the context with
`langsmith.tracing_context(enabled=False)` entered inside it. So the web page, the terminal, the
harness and a test that builds the agent directly all get the same refusal. The probe before it
was built: with the switch set, 13 LangSmith runs started, one of them on a LangGraph worker
thread. With the refusal: none. The variable is left in the environment and the operator is told,
rather than unset: silently fixing a misconfiguration hides it.

**The private context is also a fix.** An earlier version entered the refusal in the caller's
context. That leaked in two ways:

- A generator abandoned without being closed left the refusal set on the caller.
- Worse, the Langfuse handler's own attribute propagation was finalised by the garbage collector
  onto whatever the thread did next, after Streamlit abandoned a question mid-stream on a rerun.
  The next question was then attributed to the previous reader.

Both were found by order-dependent test failures. Each has a test that reproduces it on its own.

## Trade-off accepted

Someone who genuinely wanted LangSmith would have to change code, not configuration. That is
intended.

Unknown values fail towards "off". A mistyped setting gives a deployment with no traces, and the
operator hears about it once. It is not an error that stops the app.

The refusal depends on how `langsmith` and `langchain-core` treat `tracing_context` against the
environment switch. A version bump could change that. A test asserts the outcome with the switch
set, next to a control that proves the same harness sees LangSmith runs when the refusal is
removed. A tracer that stopped being refused therefore fails the suite rather than going quiet.
`langsmith` caches its environment reads (`get_env_var` is `lru_cache`d), which is why that
control exists: without it, the refusal tests passed because LangSmith never read the switch.
