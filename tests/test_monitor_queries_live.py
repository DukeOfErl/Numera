"""Every read the view makes, run as the monitor's role against a real branch.

The page test replaces these reads with rows, so it cannot see a column the query
does not return, a grant the role lacks, or a `join` that only fails in Postgres --
`pending`'s two defects were of exactly that kind and were found only live. Same
setup and skips as `test_monitor_role_live.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from test_monitor_role_live import monitor, owner  # noqa: F401  (fixtures)

from scinumbers_ask import pending
from scinumbers_monitor import figures, queries

pytestmark = pytest.mark.network


def test_a_period_reads_as_rows_the_figures_accept(monitor):  # noqa: F811
    now = datetime.now(UTC)
    rows = queries.period_rows(monitor, now - timedelta(days=30), now)
    assert all(isinstance(r, figures.Row) for r in rows)
    assert all(isinstance(r.detail, dict) for r in rows)
    # Every figure computes over real rows without raising.
    figures.health(rows), figures.quality(rows), figures.recording(rows), figures.questions(rows)


def test_one_question_reads_back(monitor):  # noqa: F811
    now = datetime.now(UTC)
    rows = queries.period_rows(monitor, now - timedelta(days=30), now)
    asked = [r.question_id for r in rows if r.event == "question.asked"]
    if not asked:
        pytest.skip("no question in the last 30 days on this branch")
    trail = queries.question_rows(monitor, asked[0])
    assert trail and {r.question_id for r in trail} == {asked[0]}


def test_the_last_row_is_a_time(monitor):  # noqa: F811
    assert isinstance(queries.last_row_at(monitor), datetime | None)


def test_the_door_rule_runs_under_the_monitor_s_role(monitor):  # noqa: F811
    """`pending.waiting` reads `accounts.email` and `accounts.disabled`; this is
    what proves the column grant covers what it reads."""
    no_email, not_enrolled = pending.waiting(monitor)
    assert isinstance(no_email, list) and isinstance(not_enrolled, list)


def test_using_every_read_changes_no_row(monitor, owner):  # noqa: F811
    """The operator uses the view; the trail holds exactly what it held. Counted by
    the owner, before and after every read the page makes."""
    from sqlalchemy import text

    def count():
        with owner.connect() as conn:
            return conn.execute(text("select count(*), max(id) from trail")).one()

    before = count()
    now = datetime.now(UTC)
    rows = queries.period_rows(monitor, now - timedelta(days=30), now)
    queries.last_row_at(monitor)
    pending.waiting(monitor)
    for q in {r.question_id for r in rows if r.question_id}:
        queries.question_rows(monitor, q)
    after = count()
    # Only rows the deployment itself wrote meanwhile could differ; on `dev` that is
    # nothing, and a difference here is worth a look rather than a retry.
    assert after == before
