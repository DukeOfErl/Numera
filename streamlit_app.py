"""Web driver entry point: `streamlit run streamlit_app.py`.

A direct script, which is what Streamlit runs and what its own test harness
drives. Everything that is not a screen element lives in `scinumbers_ask.web`,
so the decisions this page makes can be tested without a browser.

The corpus, the checkpoint store and the trail are read from the environment --
SCINUMBERS_CORPUS, SCINUMBERS_CHECKPOINTS, SCINUMBERS_TRACE -- since
a Streamlit script is given no arguments of its own.
"""

import os

import streamlit as st

from scinumbers_ask import autobuild, web
from scinumbers_ask.config import NotConfigured, format_usd, refuse_retired_env
from scinumbers_ask.corpus import CorpusUnavailable

st.set_page_config(page_title="SciNumbers ask", page_icon=":material/biotech:")

try:
    # Before the corpus is resolved. A reader who still exports the old variable
    # names would otherwise be told the corpus is missing, which is true and about
    # the wrong thing.
    refuse_retired_env()
    # Resolved here rather than inside `resources`, which is cached: Streamlit
    # replays elements drawn inside a cached function on every hit, so a build
    # notice written in there would be redrawn for ever. Announced before the
    # build starts, because a minute of blank page is indistinguishable from a
    # hang.
    corpus = autobuild.corpus_path(
        os.environ.get("SCINUMBERS_CORPUS", ""),
        lambda text: st.info(web.as_text(text), icon=":material/build:"),
    )
    repo, agent = web.resources(corpus)
except (CorpusUnavailable, NotConfigured) as exc:
    # Both are misconfiguration a person can fix, so the message is the point:
    # Streamlit's exception panel would bury it under a stack the reader did not
    # cause, and NotConfigured's message is a set of instructions.
    st.error(web.as_text(str(exc)))
    st.stop()

session = web.session_id(st.session_state, st.query_params)

# Pinned to the viewport, before anything that could scroll it away.
web.draw_prototype_banner()

st.title("SciNumbers ask")
st.caption(web.as_text(f"{len(repo)} entries · session {session}"))
# The identifier is in the URL, so this page can be reloaded, bookmarked or
# reopened after a restart and still be the same conversation.

# Both pinned to the top of the panel, before anything whose length depends on an
# answer. The entries below are unbounded -- one question can fill the panel -- and
# a run budget pushed past the scroll is not a standing figure.
with st.sidebar:
    st.caption(web.PROTOTYPE_SHORT)
    # Always drawn, including before the first question, when it reads zero. The
    # panel must not gain a section the moment a question completes: a layout that
    # grows under the reader is a worse surprise than a bar showing nothing spent.
    spent_and_cap = web.run_status(
        web.transcript(st.session_state), (agent.run_spend(), agent.run_budget)
    )
    if spent_and_cap:
        spent, cap = spent_and_cap
        st.header("Run budget")
        st.progress(min(1.0, spent / cap) if cap else 0.0)
        # Escaped: two dollar signs in one caption are read as opening and closing
        # inline mathematics, so "$1.20 of $1.20" typeset the middle as an equation
        # and ate both currency signs. Same fault as the ending line's, same fix.
        st.caption(web.as_text(f"{format_usd(spent)} of {format_usd(cap)}"))
    st.divider()

for asked, drawn in web.transcript(st.session_state):
    with st.chat_message("user"):
        st.markdown(web.as_text(asked))
    with st.chat_message("assistant"):
        web.show(drawn)

# Some endings close the run: the budget is spent, or the conversation is past its
# token bound. Asking again cannot come out differently, so the input goes away
# rather than replaying the same refusal -- the terminal returns from its read loop
# at exactly these endings.
if web.run_is_over(web.transcript(st.session_state)):
    st.error(
        "This run has stopped taking questions. Start a new session to continue —"
        " reload with a fresh `?session=` or clear this one.",
        icon=":material/block:",
    )
# `submit_mode="disable"` because a question runs for as long as the agent takes:
# leaving the input live invites a second question into the middle of the first.
elif question := st.chat_input("Ask a question", submit_mode="disable"):
    with st.chat_message("user"):
        st.markdown(web.as_text(question))
    # Recorded before it is drawn, and filled in place. The agent persists the turn
    # as it goes, so a failure while drawing must not be able to lose the question
    # from the page -- that leaves the model remembering what the screen does not.
    items: list[web.Item] = []
    web.transcript(st.session_state).append((question, items))
    with st.chat_message("assistant"):
        web.answer(agent.ask(session, question), repo, items)

# The side panel carries the newest answer's entries, whole and openable -- the
# main column's table is the first few rows of the same set. Written after the
# conversation so it reflects the question just asked.
web.draw_full_entries(web.latest_table(web.transcript(st.session_state)))

