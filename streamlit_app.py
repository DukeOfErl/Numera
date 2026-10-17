"""Web driver entry point: `streamlit run streamlit_app.py`.

A direct script, which is what Streamlit runs and what its own test harness
drives. Everything that is not a screen element lives in `scinumbers_ask.web`,
so the decisions this page makes can be tested without a browser.

The corpus, the checkpoint store and the trail are read from the environment --
SCINUMBERS_CORPUS (or SCINUMBERS_STORE for the harvest store), SCINUMBERS_CHECKPOINTS,
SCINUMBERS_TRACE -- since
a Streamlit script is given no arguments of its own.
"""

import streamlit as st

from scinumbers_ask import autobuild, web
from scinumbers_ask.config import (
    NotConfigured,
    env_setting,
    refuse_retired_env,
)
from scinumbers_ask.corpus import CorpusUnavailable

# Wide, because each answer is now two columns: the prose and the entries it
# rests on, side by side. The entries table is fixed-width and needs about
# 640px before it grows a horizontal scrollbar that hides the ID column, which
# the centred layout's ~700px main area cannot give half of. See READING_SPLIT.
# The sidebar is collapsed by default (ADR-1850): it holds the account, the budget and the trail,
# none of which a reader needs in front of every answer.
st.set_page_config(
    page_title=web.TITLE,
    page_icon=":material/biotech:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
    # The harvest store is read as it is and never built, so autobuild is for a corpus file
    # only. Both named is refused inside `resources` (design D7), not here.
    store = env_setting("SCINUMBERS_STORE")
    corpus = env_setting("SCINUMBERS_CORPUS")
    if not store:
        corpus = autobuild.corpus_path(
            corpus,
            lambda text: st.info(web.as_text(text), icon=":material/build:"),
        )
    repo = web.resources(corpus, store)
except (CorpusUnavailable, NotConfigured) as exc:
    # Both are misconfiguration a person can fix, so the message is the point:
    # Streamlit's exception panel would bury it under a stack the reader did not
    # cause, and NotConfigured's message is a set of instructions.
    st.error(web.as_text(str(exc)))
    st.stop()

# The token in the URL. It continues a conversation on a developer's machine and
# is what a bookmark carries -- but it is supplied by whoever holds the link, so
# under sign-in it is not what the conversation is keyed on (see below).
# The token in the URL. It names the conversation -- under sign-in together with
# the account, so a link cannot carry one reader into another's (ADR-0830) -- and
# it is what a reader changes to start a fresh one when the current conversation
# has filled up. Kept in the address bar so that is possible.
url_session = web.session_id(st.session_state, st.query_params)
# This browser session's own identity, which the cap counts and the link cannot
# supply.
tab = web.tab_id(st.session_state)

# The door, before anything is drawn. Where identity is configured a visitor who
# is not signed in, not enrolled, or holding no credential is offered sign-in or
# the one sentence that says why not -- no question, no answer, no record. Where
# it is not configured the door is open and the page runs exactly as it did
# before identity existed.
admission = web.admit(
    st.session_state, web.trail_destination, url_session, check_key=web.allowance.probe
)
if admission.door is not web.Door.OPEN:
    web.draw_closed_door(admission, url_session, tab)
    st.stop()

# What the conversation, the identity stamp, the dev panel and the cap are all
# keyed on. Derived from the account where one is signed in, so two readers on
# one shared link cannot overwrite each other's attribution and the OAuth
# redirect -- which drops the query string -- cannot strand a session (ADR-0830).
session = web.effective_session(admission, url_session)

# The cap, at the door rather than before it. Counting a visitor who has not yet
# passed the door left a place held by every abandoned pre-sign-in visit; what
# costs the host is a session with an agent behind it. Counted per *tab*, not per
# conversation, because one account's five tabs are five Streamlit sessions and
# five agents. A tab already holding a conversation is admitted whatever the
# count, because no open session is ended to make room (ADR-0790).
#
# **Before the stamp below, and that order is load-bearing**: admitting prunes,
# and pruning clears the stamp of any conversation whose last tab has gone. Set
# the stamp first and a reader returning after the idle window had it wiped in
# the same run, so the question they came back to ask was recorded against
# nobody while the sidebar still named them.
if not web.session_registry().admit(
    tab, session, continuing=bool(web.transcript(st.session_state))
):
    web.draw_try_later()
    st.stop()

# Every rerun, not only at sign-in: a session pruned for idleness and returned to
# would otherwise keep drawing "signed in as" while recording nobody.
web.establish_identity(admission, session)

# One agent per session, holding this account's credential and nothing else about
# the person. Never None: an enrolled account with no credential met its own door
# above, so nothing here can fall back on the environment's key.
agent = web.agent_for(st.session_state, repo, admission)

# Asked before anything is drawn, because every control drawn below is live in the
# browser for as long as this run takes. A click on any of them re-runs the script,
# and a re-run abandons the agent's generator mid-tool-call -- so while a question
# is being answered, the ratings on past answers are drawn inert.
answering = web.question_pending(st.session_state)

# Page-level, drawn once, above everything that uses them, rather than once per turn.
web.draw_page_style()
web.draw_feedback_style()

# The title, what the data is, and the prototype caveat in amber (ADR-1850).
web.draw_header(harvested=bool(store))

# Both pinned to the top of the panel, before anything whose length depends on an
# answer. The entries below are unbounded -- one question can fill the panel -- and
# a run budget pushed past the scroll is not a standing figure.
with st.sidebar:
    # Who this page thinks you are, or that it is nobody's. A person reading
    # under an account they did not expect is a person whose questions are being
    # recorded against the wrong name.
    web.draw_identity(admission, session, tab)
    # Always drawn, including before the first question, when it reads zero. The
    # panel must not gain a section the moment a question completes: a layout that
    # grows under the reader is a worse surprise than a bar showing nothing spent.
    spent_and_cap = web.run_status(
        web.transcript(st.session_state), (agent.run_spend(), agent.run_budget)
    )
    if spent_and_cap:
        spent, cap = spent_and_cap
        st.header("Session budget", anchor=False)
        st.progress(min(1.0, spent / cap) if cap else 0.0)
        # Escaped: two dollar signs in one caption are read as opening and closing
        # inline mathematics, so "$1.20 of $1.20" typeset the middle as an equation
        # and ate both currency signs. Same fault as the ending line's, same fix.
        # One line: the run budget, and in the parenthesis what the provider still
        # honours on this reader's own key. Escaped, because two dollar signs in
        # one caption are read as opening and closing inline mathematics -- "$1.20
        # of $1.20" typeset the middle as an equation and ate both currency signs.
        st.caption(web.as_text(web.spend_line(spent, cap, admission)))
    # Whose numbers these are. One click rather than one line: it must be present
    # on every page view and need not be read on every page view.
    web.draw_data_credit()
    if web.may_see_dev_panel(admission):
        # The corpus size and the conversation's identifier: diagnostics, behind the same grant
        # as the dev panel (ADR-0800). The identifier is in the URL regardless.
        st.caption(web.as_text(f"{len(repo)} entries · session {session}"))
    st.divider()
    # This session's trail, for the roles the grant table allows, filled at the foot of the
    # script where the newest question's records exist. The refusal is inside `dev_panel_rows`.
    dev_seat = web.dev_seat(admission)

# Before the first question: what the page is for, and questions to start from (ADR-1850).
if not web.transcript(st.session_state):
    web.draw_first_view(answering=answering)

for asked, drawn in web.transcript(st.session_state):
    with st.chat_message("user"):
        st.markdown(web.as_text(asked))
    with st.chat_message("assistant"):
        # Inside the message, so a rating sits with the answer it is about rather
        # than floating between turns -- and `after_prose` places it at the foot
        # of the prose column, beside the entries rather than under them. Every
        # past turn gets one, not just the newest: a reader who reads three
        # answers and then decides the second was wrong is the case this exists
        # for.
        # `drawn=drawn` binds this turn's items rather than the loop variable. The
        # callback is in fact called before the next iteration, but a lambda that
        # reads the loop variable is one refactor away from being called after it.
        web.show(
            drawn,
            after_prose=lambda drawn=drawn: web.draw_feedback(drawn, session, answering=answering),
            answering=answering,
        )

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
            web.run_over_advice(web.transcript(st.session_state), signed_in=admission.configured)
            or "This run has stopped taking questions. Start a new session to continue —"
            " reload with a fresh `?session=` or clear this one."
        ),
        icon=":material/block:",
    )
# `submit_mode="disable"` because a question runs for as long as the agent takes:
# leaving the input live invites a second question into the middle of the first.
elif question := (
    st.chat_input("Ask a question", submit_mode="disable", key=web.ASK_KEY) or web.take_example()
):
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
        # Around the consumption rather than the call: the generator runs as it is
        # read, so this is where the question's trace is actually begun.
        with web.attributed(admission):
            web.answer(
                agent.ask(session, question),
                repo,
                items,
                after_prose=lambda: web.draw_feedback(items, session),
            )

    # Unconditional, and it settles two things this run decided too early.
    #
    # The ending only exists now, and the branch above decided whether the run was
    # over *before* this question ran. Streamlit reruns on the next interaction and
    # not when a script finishes, so without this the reader is left looking at a
    # live input on a run that is over, with no line saying why -- which is the state
    # `run_is_over` exists to prevent, arriving one interaction late. It showed up on
    # the deployed app's very first question: a spent key, and nothing on the page to
    # say a new one was needed.
    #
    # `answering` was likewise decided at the top of this run and was true for all
    # of it, so every older answer's rating was drawn inert -- correctly, while the
    # agent was working. Nothing re-drew them once it stopped, so the last frame of
    # the answering run stayed on screen and those ratings were dead until the
    # reader clicked something else. A reader reported exactly that. `st.rerun()`
    # clears the submitted question, so the redraw has `answering` false and the
    # ratings come back.
    #
    # A rerun rather than drawing the banner here: the input has already been created
    # by the time the ending arrives and cannot be taken back within one run, and a
    # closed run that still offers an input is the other half of the same confusion.
    # It costs one redraw from the transcript -- no question, no model call, and the
    # same cost this page already pays on every thumb, expander and text entry.
    #
    # Unconditional. A condition was tried -- only redraw when an older turn exists
    # to revive -- on the strength of a timing that turned out to be measured with
    # other test runs competing for the machine. Measured alone: 38.4s with the
    # redraw against 41.0s without it, so it costs nothing and the condition bought
    # nothing. What it did buy was a second rule about when the page is fresh.
    st.rerun()

# Under the question box: what is kept, and whose account it is kept against (ADR-1850).
web.draw_footer(admission)
# Written after the conversation, so the trail reflects the question just asked.
web.draw_dev_panel(admission, session, dev_seat)
