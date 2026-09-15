"""Web driver entry point: `streamlit run streamlit_app.py`.

A direct script, which is what Streamlit runs and what its own test harness
drives. Everything that is not a screen element lives in `scinumbers_ask.web`,
so the decisions this page makes can be tested without a browser.

The corpus, the checkpoint store and the trail are read from the environment --
SCINUMBERS_CORPUS, SCINUMBERS_CHECKPOINTS, SCINUMBERS_TRACE -- since
a Streamlit script is given no arguments of its own.
"""

import streamlit as st

from scinumbers_ask import autobuild, web
from scinumbers_ask.config import (
    NotConfigured,
    env_setting,
    format_usd,
    refuse_retired_env,
)
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
        env_setting("SCINUMBERS_CORPUS"),
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
        # Inside the message, so a rating sits with the answer it is about rather
        # than floating between turns -- and `after_prose` places it between the
        # prose and the table of entries, which is long enough to push it off the
        # screen. Every past turn gets one, not just the newest: a reader who
        # reads three answers and then decides the second was wrong is the case
        # this exists for.
        # `drawn=drawn` binds this turn's items rather than the loop variable. The
        # callback is in fact called before the next iteration, but a lambda that
        # reads the loop variable is one refactor away from being called after it.
        web.show(drawn, after_prose=lambda drawn=drawn: web.draw_feedback(drawn, session))

# Some endings close the run: the budget is spent, the conversation is past its
# token bound, nothing is configured, or the key funding the calls is out of credit.
# Asking again cannot come out differently, so the input goes away rather than
# replaying the same refusal -- the terminal returns from its read loop at exactly
# these endings.
if web.run_is_over(web.transcript(st.session_state)):
    # An ending with advice of its own replaces the line below rather than sitting
    # under it: "start a new session" is wrong for a spent key -- the next session's
    # first question meets the same refusal -- and this banner is the last thing on
    # screen, so wrong advice here outranks the answer that said otherwise.
    st.error(
        web.as_text(
            web.run_over_advice(web.transcript(st.session_state))
            or "This run has stopped taking questions. Start a new session to continue —"
            " reload with a fresh `?session=` or clear this one."
        ),
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
        # Rated here as well as in the loop above, and for the reason the "run is
        # over" banner had to be: this turn joined the transcript after that loop
        # had already run, so without this the rating appears one interaction late
        # -- never, for the reader who reads the answer and stops. It is not drawn
        # twice in one run, because the append is below the loop and not above it.
        #
        # `items` is the same list being filled as the answer arrives, so by the
        # time the seam is reached it already holds the prose the rating is about.
        web.answer(
            agent.ask(session, question),
            repo,
            items,
            after_prose=lambda: web.draw_feedback(items, session),
        )

    # The ending only exists now, and the branch above decided whether the run was
    # over *before* this question ran. Streamlit reruns on the next interaction and
    # not when a script finishes, so without this the reader is left looking at a
    # live input on a run that is over, with no line saying why -- which is the state
    # `run_is_over` exists to prevent, arriving one interaction late. It showed up on
    # the deployed app's very first question: a spent key, and nothing on the page to
    # say a new one was needed.
    #
    # A rerun rather than drawing the banner here: the input has already been created
    # by the time the ending arrives and cannot be taken back within one run, and a
    # closed run that still offers an input is the other half of the same confusion.
    # It costs one redraw from the transcript -- no question, no model call.
    if web.run_is_over(web.transcript(st.session_state)):
        st.rerun()

# The side panel carries the newest answer's entries, whole and openable -- the
# main column's table is the first few rows of the same set. Written after the
# conversation so it reflects the question just asked.
web.draw_full_entries(web.latest_table(web.transcript(st.session_state)))
