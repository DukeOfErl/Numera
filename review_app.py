"""The review page: `streamlit run review_app.py`.

A second script beside `streamlit_app.py` rather than a page inside it (design D9). The two apps
share a door and a database and nothing else: a reviewer has no use for the ask app's corpus,
agent or spend, and the ask app's reader has no business being handed items to judge.

The door is imported, not copied -- `web.admit` with `check_key=None`, because a reviewer needs no
model credential and this page makes no model call at all. With no `[auth]` configured the door is
open and decisions record no account, which `user-identity` already requires.

Everything that is not a screen element is in `bionumbers.review`, so what the page decides is
tested without a browser and only the order and lifetime of the elements needs `AppTest`
(`.claude/rules/streamlit-driver.md`).
"""

import time

import streamlit as st

from bionumbers import review, store
from scinumbers_ask import web

#: The one sentence for a deployment with no database behind it. It names the secrets section
#: rather than describing the symptom, because the operator's next move is to write that section --
#: and this is the likeliest first-deploy mistake, the same one `web.admit` reports for the
#: accounts table.
NO_STORE = (
    "This deployment has no review database: add a [connections.usage] section to Streamlit's "
    "secrets and create the tables from sql/review.sql. There is nothing to review until then."
)

#: The widget key prefixes. Each widget's key is the prefix and the item id, so a new item is a
#: new set of widgets and starts blank -- a choice or a comment carried over from the last item
#: is a decision nobody made. Popping the keys from `session_state` after a save, the first
#: version of this, left the buttons clicked and the comment typed in the browser (seen by Yoav
#: on 2026-09-22): the widget's own state outlived the key. A fresh key is the mechanism
#: Streamlit documents for a fresh widget.
CHOICE_KEY = "bionumbers.review.choice"
VERDICT_KEY = "bionumbers.review.verdict"
COMMENT_KEY = "bionumbers.review.comment"
#: `(item id, monotonic seconds)` for the item now on screen. Keyed by the item because the script
#: reruns on every click: a clock restarted per run would measure the last interaction rather than
#: the decision, and one never restarted would charge this item with the time spent on the last.
STARTED_KEY = "bionumbers.review.started"

st.set_page_config(page_title=review.TITLE, page_icon=":material/fact_check:")

# The token in the URL, and this browser session's own identity. Same two as the ask app, because
# `admit` and `draw_identity` are the ask app's and expect them (ADR-0830).
url_session = web.session_id(st.session_state, st.query_params)
tab = web.tab_id(st.session_state)

# Before anything is drawn. A visitor who is not signed in or not enrolled sees the door and no
# item: an item is the paper's text, and the reviewer's judgement of it is the record.
admission = web.admit(st.session_state, web.trail_destination, url_session, check_key=None)
if admission.door is not web.Door.OPEN:
    web.draw_closed_door(admission, url_session, tab)
    st.stop()

session = web.effective_session(admission, url_session)
# None where no identity is configured, which the spec allows explicitly: the decision is recorded
# with no account and nothing else about it differs. It is also what `next_item` serves on, so an
# unconfigured deployment has exactly one reviewer.
reviewer = admission.account.email if admission.account else None

engine = review.store_engine()

with st.sidebar:
    web.draw_identity(admission, session, tab)
    if engine is not None:
        # Read before the decision below is written, so the figure is what is left *including*
        # this item -- the count a reviewer watches go down as they save.
        st.caption(web.as_text(f"{store.remaining(engine, reviewer)} left to review"))

web.draw_title(review.TITLE)

if engine is None:
    st.error(web.as_text(NO_STORE))
    st.stop()

item = store.next_item(engine, reviewer)
if item is None:
    st.info(web.as_text(review.NOTHING_LEFT))
    st.stop()

started = st.session_state.get(STARTED_KEY)
if started is None or started[0] != item.item_id:
    started = (item.item_id, time.monotonic())
    st.session_state[STARTED_KEY] = started

st.subheader(web.as_text(item.question))
st.markdown(web.as_text(f"### {item.claim.value} {item.claim.unit}".rstrip()))
# The paper's own term beside the question's: the reviewer is judging whether this paper's
# "generation time" is the question's "doubling time", and they cannot if only one is on screen.
st.caption(web.as_text(f"the paper calls it: {item.claim.property_in_paper}"))
st.caption(web.as_text(review.citation_line(item.paper)))

st.table(
    [
        {"Condition": name, "Stated": provenance, "Quote": quote}
        for name, provenance, quote in review.condition_rows(item.claim)
    ]
)

# Both texts, in the order `texts_in_order` gives and never sorted, filtered or labelled further
# here: which is which is the question being asked. Each text as the paper wrote it, nothing in
# it emphasised (ADR-0940).
for shown in review.texts_in_order(item):
    with st.container(border=True):
        st.markdown(f"**{shown.label}**")
        st.caption(web.as_text(shown.location_line))
        st.markdown(review.as_markdown(shown.text))

# The table a cell came from, whole and with its caption, both cells marked alike. Our own HTML,
# because `st.table` cannot draw a spanning header and the paper's layout is the point.
for table in review.tables_html(item):
    st.markdown(table, unsafe_allow_html=True)

# `index=None`, so neither radio carries an answer the reviewer did not give. A default would be
# recorded verbatim by anyone who clicked straight past it, and it would be the same default every
# time -- a bias in the dataset with no trace of itself.
choice = st.radio(
    "Which text better fits the value?", ["A", "B"], index=None, key=f"{CHOICE_KEY}:{item.item_id}"
)
verdict = st.radio(
    "Did this value come from this paper under these conditions?",
    [review.APPROVE, review.DISAPPROVE],
    index=None,
    key=f"{VERDICT_KEY}:{item.item_id}",
)
comment = st.text_area("Comment (optional)", key=f"{COMMENT_KEY}:{item.item_id}")

if st.button("Save and next", type="primary"):
    try:
        decision = review.decision_from(item, choice, verdict, comment)
    except review.Incomplete as incomplete:
        # The item stays as it is, widgets and all: a reviewer who has given half an answer is
        # being asked for the other half, not asked again from the start.
        st.warning(web.as_text(incomplete.message))
    else:
        try:
            store.record_decision(
                engine,
                item.item_id,
                reviewer=reviewer,
                chosen_supporting=decision.chosen_supporting,
                approved=decision.approved,
                comment=decision.comment,
                time_to_decide_s=time.monotonic() - started[1],
            )
        except store.DecisionNotSaved:
            # The reviewer's half of failing closed (ADR-0930): nothing advances and nothing is
            # cleared, so the next click retries this decision rather than starting another.
            st.error(web.as_text(review.NOT_SAVED))
        else:
            # The next item brings its own widgets (see the key prefixes above); only the clock
            # is ours to reset.
            st.session_state.pop(STARTED_KEY, None)
            st.rerun()
