"""Web driver entry point: `streamlit run streamlit_app.py`.

A direct script, which is what Streamlit runs and what its own test harness
drives. Everything that is not a screen element lives in `bionumbers_ask.web`,
so the decisions this page makes can be tested without a browser.

The corpus, the checkpoint store and the trail are read from the environment --
BIONUMBERS_ASK_CORPUS, BIONUMBERS_ASK_CHECKPOINTS, BIONUMBERS_ASK_TRACE -- since
a Streamlit script is given no arguments of its own.
"""

import streamlit as st

from bionumbers_ask import web
from bionumbers_ask.corpus import CorpusUnavailable

st.set_page_config(page_title="BioNumbers ask", page_icon=":material/biotech:")

try:
    repo, agent = web.resources()
except CorpusUnavailable as exc:
    # An external input, so its absence is a condition to explain rather than a
    # traceback to show.
    st.error(str(exc))
    st.stop()

session = web.session_id(st.session_state, st.query_params)

st.title("BioNumbers ask")
st.caption(f"{len(repo)} entries · session {session}")
# The identifier is in the URL, so this page can be reloaded, bookmarked or
# reopened after a restart and still be the same conversation.

for asked, drawn in web.transcript(st.session_state):
    with st.chat_message("user"):
        st.markdown(web.as_text(asked))
    with st.chat_message("assistant"):
        web.show(drawn)

# `submit_mode="disable"` because a question runs for as long as the agent takes:
# leaving the input live invites a second question into the middle of the first.
if question := st.chat_input("Ask a question", submit_mode="disable"):
    with st.chat_message("user"):
        st.markdown(web.as_text(question))
    with st.chat_message("assistant"):
        items = web.answer(agent.ask(session, question), repo)
    web.transcript(st.session_state).append((question, items))

# The side panel carries the newest answer's entries, whole and openable -- the
# main column's table is the first few rows of the same set. Written after the
# conversation so it reflects the question just asked.
web.draw_full_entries(web.latest_table(web.transcript(st.session_state)))
