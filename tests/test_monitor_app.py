"""The page, run whole with `streamlit.testing`, its reads replaced by rows.

What only a whole script run can show: that every row renders from real `figures`
output, that the branch is named on each, that a quiet period says so, and that
nothing on the page opens a network connection -- the trace links are built, never
fetched. Sockets are refused outright, which is stricter than refusing Langfuse's
host and catches any client that tries.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from scinumbers_ask import pending
from scinumbers_monitor import connection, queries
from scinumbers_monitor.figures import Row

APP = Path(__file__).resolve().parents[1] / "src" / "scinumbers_monitor" / "app.py"
NOW = datetime.now(UTC)


def _rows():
    def r(i, event, q=None, **detail):
        return Row(
            id=i,
            at=NOW - timedelta(hours=2) + timedelta(seconds=i),
            event=event,
            question_id=q,
            run_label="run-a",
            user_email="a@x.org" if q else None,
            detail=detail,
        )

    return [
        r(1, "question.asked", "q1", question="How big is E. coli?"),
        r(2, "spend.increment", "q1", increment=1200),
        r(3, "question.answered", "q1"),
        r(4, "answer.given", "q1", answer="About 1 µm³."),
        r(5, "answer.evidence", "q1", cited=["1"], retrieved=["1", "2"]),
        r(6, "feedback.verdict", "q1", verdict="down"),
        r(7, "feedback.comment", "q1", comment="wrong volume"),
        r(8, "question.asked", "q2", question="?"),
        r(9, "tracing.failed"),
    ]


@pytest.fixture
def offline(monkeypatch):
    """No database and no network: reads return rows, and any socket is refused."""
    state = {"rows": _rows(), "asked_for": []}
    monkeypatch.setattr(connection, "resolve", lambda branch: "postgresql+psycopg://x@h/db")
    monkeypatch.setattr(connection, "engine", lambda url: object())
    monkeypatch.setattr(queries, "period_rows", lambda engine, since, until: state["rows"])
    monkeypatch.setattr(queries, "last_row_at", lambda engine: NOW)
    monkeypatch.setattr(
        queries,
        "question_rows",
        lambda engine, q: (
            state["asked_for"].append(q) or [x for x in state["rows"] if x.question_id == q]
        ),
    )
    monkeypatch.setattr(pending, "waiting", lambda engine, **kw: ([], []))

    def refuse(*args, **kwargs):
        raise AssertionError(f"the page opened a network connection: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", "p1")
    # The page caches its reads for ten minutes, and `AppTest` runs in this process,
    # so one test's rows would otherwise be the next test's.
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    return state


def _run(monkeypatch, branch="alpha"):
    monkeypatch.setattr("sys.argv", ["app.py", "--branch", branch])
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    return at


def test_every_row_renders_and_names_the_branch(offline, monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    subheaders = [s.value for s in at.subheader]
    assert len(subheaders) == 5
    assert all("`alpha`" in s for s in subheaders), subheaders
    assert "`alpha`" in at.title[0].value


def test_a_rate_is_shown_with_its_count(offline, monkeypatch):
    at = _run(monkeypatch)
    values = {m.label: m.value for m in at.metric}
    assert values["Ended at a limit"] == "0 of 2 (0%)"
    assert values["Retrieved entries cited"] == "1 of 2 (50%)"


def test_a_quiet_period_says_so(offline, monkeypatch):
    offline["rows"] = []
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    assert any("No questions were asked" in i.value for i in at.info)


def test_the_page_makes_no_network_request_through_every_part(offline, monkeypatch):
    """Including the drill-down, which is where a trace lookup would be tempting.
    `AppTest` cannot click a dataframe row, so the selection is put in session state."""
    monkeypatch.setattr("sys.argv", ["app.py", "--branch", "alpha"])
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["questions"] = {"selection": {"rows": [1], "columns": [], "cells": []}}
    at.run()
    assert not at.exception, at.exception
    assert offline["asked_for"] == ["q1"], "the drill-down did not run"


def test_without_a_branch_the_page_refuses(offline, monkeypatch):
    monkeypatch.setattr("sys.argv", ["app.py"])
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert any("No branch named" in e.value for e in at.error)
    assert not at.subheader


def test_missing_settings_are_named_on_the_page(offline, monkeypatch):
    def missing(branch):
        raise connection.Missing("set SCINUMBERS_MONITOR_DB_PASSWORD before starting the view.")

    monkeypatch.setattr(connection, "resolve", missing)
    at = _run(monkeypatch, branch="beta")
    assert any("SCINUMBERS_MONITOR_DB_PASSWORD" in e.value for e in at.error)


def test_reruns_reuse_the_read_and_only_refresh_reads_again(offline, monkeypatch):
    """Leaving the view open does not keep the database awake: an interaction
    reruns the script, and that rerun must not query. Refresh must."""
    calls = []
    rows = offline["rows"]

    def counted(engine, since, until):
        calls.append(since)
        return rows

    monkeypatch.setattr(queries, "period_rows", counted)
    at = _run(monkeypatch)
    at.run()
    at.run()
    assert len(calls) == 1
    next(b for b in at.button if b.label == "Refresh").click().run()
    assert len(calls) == 2


def test_nothing_on_the_page_runs_on_a_timer():
    """A fragment with `run_every`, or an auto-refresh component, would poll."""
    source = APP.read_text()
    assert "run_every" not in source
    assert "autorefresh" not in source
