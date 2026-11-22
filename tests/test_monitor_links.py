"""A question is followed to its hosted trace by a link built from its id alone.

Nothing here may call Langfuse: the link is arithmetic on the question id, and the
access window is Hobby's 30 days (langfuse.com/pricing, read 2026-10-02).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from numera_ask.hosted_trace import trace_id_for
from numera_monitor.links import TRACER_WINDOW, trace_url

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
BASE = "https://cloud.langfuse.com"


def test_a_recent_question_links_to_its_derived_trace():
    url = trace_url("q-123", NOW - timedelta(days=29), now=NOW, base_url=BASE, project_id="p1")
    assert url == f"{BASE}/project/p1/traces/{trace_id_for('q-123')}"


def test_a_question_older_than_the_window_gets_no_link():
    url = trace_url("q-123", NOW - timedelta(days=31), now=NOW, base_url=BASE, project_id="p1")
    assert url is None


def test_the_window_is_thirty_days():
    assert TRACER_WINDOW == timedelta(days=30)


def test_a_trailing_slash_on_the_host_does_not_double():
    url = trace_url("q-1", NOW, now=NOW, base_url=BASE + "/", project_id="p1")
    assert url is not None and "//project" not in url


def test_no_project_id_means_no_link_rather_than_a_broken_one():
    assert trace_url("q-1", NOW, now=NOW, base_url=BASE, project_id="") is None
