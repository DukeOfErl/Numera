# ADR-1320: Langfuse is linked from the monitor, never queried

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** _pending — `feat/monitor-dashboard`_

## Context

The trail is the record; the tracer is a debugger (ADR-0750, ADR-1000). Langfuse
holds the per-call detail that the trail does not: latency per model call, the
span tree, the prompt as sent. The question was whether the monitor should pull
any of it in.

Limits of Langfuse's Hobby plan, read from langfuse.com/pricing on 2026-10-02:

- The Metrics API v2 allows 100 requests a *day*, about fifteen loads of a page
  with half a dozen Langfuse widgets.
- The general API allows 30 requests a minute.
- Data is accessible for 30 days.
- Custom dashboards are included and do not count against the API limits.

Most of what a dashboard would want from Langfuse is already in the trail: spend
and token increments per call, model and tool call counts, the times of asking and
ending.

## Decision

The monitor links to each question's trace and makes no request to Langfuse. The
link is `{LANGFUSE_BASE_URL}/project/{LANGFUSE_PROJECT_ID}/traces/{trace_id}`, with
the id from `hosted_trace.trace_id_for(question_id)`, Langfuse's own derivation. It
is omitted for questions older than the 30-day window, where it would lead nowhere.
`tests/test_monitor_app.py` runs the whole page with sockets refused. A copy of the
page that called Langfuse failed that test, which was checked before the test was
believed.

Langfuse's own charts (latency, cost, units, `reader_verdict` over time) and its two
Hobby alerts are configured in Langfuse, as an operator step in the README.

## Trade-off accepted

Per-call latency is not on the same screen as the trail. If that is wanted, the
escape hatch is a nightly job that copies about five Metrics API aggregates into a
table of their own, well inside the daily limit. It is not built.

The trail does not record per question whether a trace was sent, so a link can lead
to "not found" for a question asked while tracing was off. The pattern
`/project/{id}/traces/{id}` must be checked against a real trace (task 4.2). It is
one constant in `links.py`.
