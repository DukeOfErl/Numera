# ADR-1000: Langfuse Cloud EU over LangSmith, and what the tracer's copy of a rating can no longer do

- **Status:** accepted
- **Date:** 2026-09-24
- **Pull request:** _pending — `feat/hosted-tracing`_

## Context

The trail records the deterministic layer and deliberately not the model calls (`trace.py`). The
roadmap's WP4 agreed that a hosted tracer would cover them, "LangSmith (or Langfuse)". The
constraints were: cloud only, since nobody wants to run a server; the free tier only; and a
handful of alpha testers.

Both vendors' current pages were read on 2026-09-23:

| | LangSmith Developer | Langfuse Hobby |
|---|---|---|
| Allowance | 5k traces a month | 50k units a month (a unit is a trace, an observation or a score) |
| Access | 14 days; 180 if feedback is sent with `extend_trace_retention=true` | 30 days, flat |
| Seats | 1 | 2 |
| EU on the free tier | yes, on its own host | yes, and it is the default host |
| Switched on by | an environment variable, globally, or `tracing_context` | passing a handler to a call |
| New dependencies | none: it arrives with `langchain-core` | `langfuse` plus the OpenTelemetry SDK |

What Hobby does past 50k units is not stated anywhere first-party. Third-party write-ups (2026)
say it is a hard stop with no overage.

## Decision

**Langfuse Cloud, EU region, Hobby tier.** The reasons: a flat 30-day window, a second seat, EU by
default, and above all a tracer that runs only when a handler is passed to it. That last one is the
property the roadmap's condition asked for: tracing is a decision, not an environment variable
nobody chose (ADR-1010).

**ADR-0750 is amended in one detail.** It says the tracer's copy of a rating is written "with the
retention-extension flag set". That is a LangSmith mechanism, and Langfuse has no equivalent, so a
score does not extend a trace. The decision itself is unchanged: the trail is the record and the
tracer gets a copy.

## Trade-off accepted

A new dependency stack: `langfuse`, `opentelemetry-sdk` and the OTLP exporter. It is imported only
when tracing is on, and handed a private tracer provider, so an untraced deployment carries the
packages and never runs them.

LangSmith's native LangGraph view is given up, and so is its zero-dependency path.

**An unreachable Langfuse stops an evaluation run until someone approves it.** Usage that cannot
be counted is shown as unknown and pauses the run, and with no terminal to answer on, the run ends
before its first question. A code review flagged this as a telemetry outage becoming a harness
outage. It is deliberate, the user's decision of 2026-09-25: evaluation runs are attended, and an
unknown figure is not a figure to spend against. The pause is in `run_evaluation`, so every caller
meets it; the command only words the question.

The allowance is counted in units rather than traces. A question cost 37 units when measured
(2026-09-25), which is about 1,300 questions a month. The evaluation harness can spend that
quickly, which is why a run shows its estimate and pauses for approval when the allowance is at
risk (`hosted-tracing` spec).

Langfuse is retiring its legacy Cloud APIs (from 2026-11-16 for some endpoints). Organisations
created after 2026-09-16 already cannot use them. The code uses only the paths Langfuse names as
current: OTel ingestion, the v2 Metrics API, and the SDK's score ingestion.
