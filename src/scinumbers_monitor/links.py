"""A question's link to its hosted trace, built from its id alone.

Nothing here calls Langfuse: no client, no HTTP. Hobby's Metrics API allows 100
requests a day, and the trail is the record while the tracer is a debugger
(ADR-1320), so the link is arithmetic on the question id and nothing more.
"""

from __future__ import annotations

from datetime import datetime, timedelta

#: Langfuse Hobby's data access window (langfuse.com/pricing, read 2026-10-02).
#: Past it the link leads nowhere, so no link is offered.
TRACER_WINDOW = timedelta(days=30)

# To be checked against a real trace (task 4.2). One constant, so a wrong guess
# is a one-line fix rather than a hunt.
_TRACE_PATH = "/project/{project_id}/traces/{trace_id}"


def trace_url(
    question_id: str,
    asked_at: datetime,
    *,
    now: datetime,
    base_url: str,
    project_id: str,
) -> str | None:
    """The hosted trace's URL, or None where a link would be dead or broken.

    A missing link is the cheap direction: a broken one sends a reader to an
    error page and looks like a fault in the dashboard.
    """
    if not project_id or now - asked_at >= TRACER_WINDOW:
        return None
    # Imported here because `trace_id_for` itself imports langfuse lazily; the
    # derivation is Langfuse's own and is never reimplemented.
    from scinumbers_ask.hosted_trace import trace_id_for

    return base_url.rstrip("/") + _TRACE_PATH.format(
        project_id=project_id, trace_id=trace_id_for(question_id)
    )
