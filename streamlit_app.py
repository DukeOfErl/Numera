"""Web driver entry point: `streamlit run streamlit_app.py`.

A direct script, which is what Streamlit runs and what its own test harness
drives. Everything that is not a screen element lives in `scinumbers_ask.web`,
so the decisions this page makes can be tested without a browser.

The corpus, the checkpoint store and the trail are read from the environment --
SCINUMBERS_CORPUS, SCINUMBERS_CHECKPOINTS, SCINUMBERS_TRACE -- since
a Streamlit script is given no arguments of its own.

**Deployment branch.** Three things differ from `main` and none of them belong
there: secrets are copied into the environment, the corpus is fetched into the
container before anything looks for it, and the run budget is shown as a figure
rather than a bar because the cap here is set far above what anyone will spend.
"""

import os
from pathlib import Path

import streamlit as st

from scinumbers_ask import autobuild, hosted, web
from scinumbers_ask.config import (
    NotConfigured,
    env_setting,
    format_usd,
    refuse_retired_env,
)
from scinumbers_ask.corpus import CorpusUnavailable

st.set_page_config(page_title="SciNumbers ask", page_icon=":material/biotech:")

# Root-level secrets are exposed as environment variables by Streamlit, but on
# first access -- and everything below reads `os.environ`, some of it deep inside
# the agent. Copied explicitly so the configuration does not depend on when the
# secrets happen to be loaded. `setdefault`, so a real environment variable still
# wins: that is what lets this branch be run locally without a secrets file.
#
# Numbers are coerced rather than skipped, and that is the whole point of this
# branch of the condition. Every setting here is a *string* in TOML, and a value
# pasted without quotes -- `SCINUMBERS_QUESTION_CEILING_USD = 0.20` -- arrives as a
# float. Skipping it left the variable unset and the run silently on the 0.60
# default: three times the intended per-question ceiling, from one missing pair of
# quotes, with nothing on the page to say so. `str(0.2)` is "0.2", which the parser
# reads as the amount that was meant; anything genuinely unparseable now fails
# loudly in `usd()` instead of disappearing.
try:
    for _name, _value in st.secrets.items():
        if isinstance(_value, str | int | float):
            os.environ.setdefault(_name, str(_value))
except Exception:
    # No secrets file at all, which is the ordinary case when this branch is run on
    # a laptop. Not a condition to report: the environment is then the only source,
    # and anything genuinely missing is named by the errors below.
    pass


@st.cache_resource(show_spinner="Fetching the corpus…")
def _corpus_in_this_container() -> str:
    """Put the corpus on this container's disk, once per cold start.

    Cached rather than guarded by a file check, so that a second visitor arriving
    mid-download waits on the cache lock instead of starting a second one. The disk
    is ephemeral, so this runs again after every restart -- Community Cloud sleeps
    an idle app, so the first reader of the day pays for it.
    """
    return str(
        hosted.fetch_corpus(
            url=os.environ.get("CORPUS_URL", ""),
            token=os.environ.get("CORPUS_TOKEN", ""),
            dest=Path(env_setting("SCINUMBERS_CORPUS")),
            expected_sha256=os.environ.get("CORPUS_SHA256", ""),
        )
    )


try:
    # Only where a URL says this is a hosted run. Without one the page behaves
    # exactly as it does on `main` -- a corpus beside the configured path, or the
    # export to build one from -- which is what lets this branch be run on a laptop
    # and what keeps the driver tests driving the same script everyone else does.
    #
    # The division of labour: this line decides *whether* to fetch, and `hosted`
    # refuses a fetch that cannot be trusted -- no digest, a copy that does not
    # match. A deployment that sets no URL at all falls through to the ordinary "no
    # corpus at that path" message, which is the right sentence for it anyway.
    #
    # Before `autobuild`, which only looks for a corpus already beside the configured
    # path -- in a fresh container there is nothing there and nothing to build from.
    if os.environ.get("CORPUS_URL"):
        _corpus_in_this_container()
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

# Under the title rather than in the side panel, which Streamlit collapses on a
# phone: a reader who never opens it would otherwise never see this. Deployment
# wording, so it lives here and not in `web` -- someone running the app locally
# pays for their own calls and this sentence would be nonsense to them.
st.caption(
    web.as_text(
        "Model usage here is paid for by the developer, from a shared budget — "
        "please keep questions purposeful, and don't automate against it."
    )
)

# Both pinned to the top of the panel, before anything whose length depends on an
# answer. The entries below are unbounded -- one question can fill the panel -- and
# a run budget pushed past the scroll is not a standing figure.
with st.sidebar:
    st.caption(web.PROTOTYPE_SHORT)
    # The figure, without the bar. A progress bar is a claim about a fraction of a
    # limit, and this deployment sets its run budget far above anything a reader will
    # spend so that the app does not stop taking questions mid-session -- the real
    # ceiling is the API key's own cap. Against that budget the bar would read zero
    # for ever, and if it ever moved it would imply headroom nobody intends to
    # enforce. The spend is true and stays; the proportion is not and goes.
    #
    # Named for what it is, too: one run label serves every visitor here, so this is
    # everyone's spend and not the reader's own. Their own cost is on each answer's
    # ending line.
    spent_and_cap = web.run_status(
        web.transcript(st.session_state), (agent.run_spend(), agent.run_budget)
    )
    if spent_and_cap:
        # Escaped: a dollar sign opens inline mathematics, which ate the currency
        # signs and the text between them when this said "$0.01 of $1.20".
        st.caption(web.as_text(f"Spent across all questions here: {format_usd(spent_and_cap[0])}"))
    st.caption(web.as_text(web.DATA_CREDIT))
    st.divider()

for asked, drawn in web.transcript(st.session_state):
    with st.chat_message("user"):
        st.markdown(web.as_text(asked))
    with st.chat_message("assistant"):
        web.show(drawn)

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
        web.answer(agent.ask(session, question), repo, items)

# The side panel carries the newest answer's entries, whole and openable -- the
# main column's table is the first few rows of the same set. Written after the
# conversation so it reflects the question just asked.
web.draw_full_entries(web.latest_table(web.transcript(st.session_state)))
