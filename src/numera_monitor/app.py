"""The operator's view of the alpha. Started by `numera-monitor --branch <name>`.

The only module here that imports Streamlit, and it only draws: every figure comes
from `figures`, every read from `queries` or `pending`. It reads through the
monitor's own role (ADR-1960), links to Langfuse without calling it (ADR-1970),
and never queries on a timer -- results are cached for ten minutes and fetched
again only when the operator presses refresh, so a tab left open lets Neon's
compute suspend as it would without it.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

import streamlit as st

from numera_ask import pending

# Absolute, not relative: `streamlit run` executes this file as a script, where a
# relative import has no package to be relative to.
from numera_monitor import connection, figures, queries
from numera_monitor.links import trace_url

#: The periods offered. The cache is keyed on the label, not on timestamps, so a
#: rerun inside the cache window does not become a new query.
PERIODS = {
    "24 hours": timedelta(hours=24),
    "7 days": timedelta(days=7),
    "30 days": timedelta(days=30),
}
CACHE_TTL = "10m"


def _branch() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default="")
    branch = parser.parse_known_args(sys.argv[1:])[0].branch.strip()
    if not branch:
        # `cli.main` refuses first; this is for someone running `streamlit run`
        # directly, who would otherwise get a page with no branch on it.
        st.error("No branch named. Start the view with `numera-monitor --branch alpha`.")
        st.stop()
    return branch


@st.cache_resource
def _engine(branch: str):
    return connection.engine(connection.resolve(branch))


@st.cache_data(ttl=CACHE_TTL, show_spinner="Reading the trail…")
def _period(branch: str, period: str) -> tuple[list[figures.Row], datetime | None, datetime]:
    now = datetime.now(UTC)
    engine = _engine(branch)
    rows = queries.period_rows(engine, now - PERIODS[period], now)
    return rows, queries.last_row_at(engine), now


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _waiting(branch: str):
    return pending.waiting(_engine(branch))


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _question(branch: str, question_id: str) -> list[figures.Row]:
    return queries.question_rows(_engine(branch), question_id)


def _share(share: figures.Share) -> str:
    """A rate is never shown without the count it is a share of."""
    if share.ratio is None:
        return f"{share.count} of {share.of}"
    return f"{share.count} of {share.of} ({share.ratio:.0%})"


def _usd(micro: int | None) -> str:
    return "—" if micro is None else f"${micro / 1_000_000:,.4f}"


st.set_page_config(page_title="Numera monitor", page_icon=":material/monitoring:", layout="wide")
branch = _branch()

with st.container(horizontal=True, vertical_alignment="bottom"):
    st.title(f"Numera monitor · `{branch}`")
    period = st.segmented_control("Period", list(PERIODS), default="7 days", required=True)
    if st.button("Refresh", icon=":material/refresh:"):
        st.cache_data.clear()

try:
    rows, last_row_at, now = _period(branch, period)
except connection.Missing as missing:
    st.error(str(missing))
    st.stop()

h = figures.health(rows)
q = figures.quality(rows)
rec = figures.recording(rows)
st.caption(f"Read from branch `{branch}` at {now:%Y-%m-%d %H:%M} UTC; cached for ten minutes.")

# --- Health ---------------------------------------------------------------------
with st.container(border=True):
    st.subheader(f"Use, cost and endings · `{branch}`")
    if h.quiet:
        st.info(f"No questions were asked in the last {period}.")
    else:
        with st.container(horizontal=True):
            st.metric("Questions", h.questions, border=True)
            st.metric("Testers", h.testers, border=True)
            st.metric("Unattributed questions", h.unattributed_questions, border=True)
            st.metric("Spend", _usd(h.spend_micro), border=True)
            st.metric("Spend per question", _usd(h.spend_per_question_micro), border=True)
            st.metric("Ended at a limit", _share(h.limit_endings), border=True)
        st.dataframe(
            [{"ending": kind, "questions": _share(s)} for kind, s in sorted(h.endings.items())],
            hide_index=True,
        )

# --- Quality --------------------------------------------------------------------
with st.container(border=True):
    st.subheader(f"What readers thought · `{branch}`")
    with st.container(horizontal=True):
        st.metric("Ungrounded answers", _share(q.ungrounded), border=True)
        st.metric(
            "Answers citing unretrieved entries", _share(q.unsupported_citations), border=True
        )
        st.metric("Retrieved entries cited", _share(q.cited), border=True)
        st.metric("Unattributed ratings", q.unattributed_verdicts, border=True)
    if q.verdicts:
        st.dataframe(
            [
                {
                    "run label": label or "(none)",
                    "approved": _share(figures.Share(v.up, v.rated)),
                    "disapproved": _share(figures.Share(v.down, v.rated)),
                }
                for label, v in sorted(q.verdicts.items(), key=lambda kv: kv[0] or "")
            ],
            hide_index=True,
        )
    else:
        st.caption("No ratings in this period.")
    if q.comments:
        st.markdown("**Comments**")
        st.dataframe(
            [
                {"at": c.at, "comment": c.comment, "question": c.question, "answer": c.answer}
                for c in q.comments
            ],
            hide_index=True,
        )

# --- The door -------------------------------------------------------------------
with st.container(border=True):
    st.subheader(f"Waiting at the door · `{branch}`")
    no_email, not_enrolled = _waiting(branch)
    st.caption("The same rule as `numera-pending`, over its 30-day window.")
    cols = st.columns(2)
    for col, title, people in (
        (cols[0], "Asked for the confirmation email again", no_email),
        (cols[1], "Verified, waiting to be enrolled", not_enrolled),
    ):
        with col:
            st.markdown(f"**{title}**")
            if people:
                st.dataframe(
                    [
                        {"address": w.address, "last seen": w.last_seen, "times": w.times}
                        for w in people
                    ],
                    hide_index=True,
                )
            else:
                st.caption("Nobody.")

# --- Recording health -----------------------------------------------------------
with st.container(border=True):
    st.subheader(f"Is the recording working · `{branch}`")
    with st.container(horizontal=True):
        st.metric(
            "Last row in the trail",
            "never" if last_row_at is None else f"{last_row_at:%Y-%m-%d %H:%M} UTC",
            border=True,
        )
        for name in sorted(figures.TRACER_TROUBLE):
            st.metric(name, rec.tracer_trouble.get(name, 0), border=True)
    if rec.cold_writes:
        st.markdown("**First writes after a quiet gap**")
        st.caption(
            "Opening this view wakes the database too, so a write soon after a visit "
            "here looks warm. That is this view's own effect, not the app's."
        )
        st.dataframe(
            [
                {"at": c.at, "after a gap of": str(c.gap), "write took (ms)": c.write_ms}
                for c in rec.cold_writes
            ],
            hide_index=True,
        )

# --- Recent questions -----------------------------------------------------------
base_url = os.environ.get("LANGFUSE_BASE_URL", "")
project_id = os.environ.get("LANGFUSE_PROJECT_ID", "")
with st.container(border=True):
    st.subheader(f"Questions · `{branch}`")
    lines = figures.questions(rows)
    if not project_id:
        st.caption(
            "Set LANGFUSE_PROJECT_ID (and LANGFUSE_BASE_URL) to link each question to its trace."
        )
    table = [
        {
            "asked": line.asked_at,
            "asker": line.asker or "(unattributed)",
            "run label": line.run_label,
            "question": line.question,
            "ending": line.ending.kind
            + (
                f" (last: {line.ending.last_event})"
                if line.ending.kind == figures.UNIDENTIFIED
                else ""
            ),
            "spend": _usd(line.spend_micro),
            "verdict": line.verdict,
            "trace": trace_url(
                line.question_id, line.asked_at, now=now, base_url=base_url, project_id=project_id
            ),
        }
        for line in lines
    ]
    event = st.dataframe(
        table,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="questions",
        column_config={"trace": st.column_config.LinkColumn("trace", display_text="open")},
    )
    if event.selection.rows:
        chosen = lines[event.selection.rows[0]]
        st.markdown(f"**The trail of `{chosen.question_id}`**")
        st.dataframe(
            [
                {"at": r.at, "event": r.event, "detail": dict(r.detail)}
                for r in _question(branch, chosen.question_id)
            ],
            hide_index=True,
        )
