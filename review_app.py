"""The review page: `streamlit run review_app.py`.

A second script beside `streamlit_app.py` rather than a page inside it (design D9). The two apps
share a door and a database and nothing else: a reviewer has no use for the ask app's corpus,
agent or spend, and the ask app's reader has no business being handed items to judge.

The door is imported, not copied -- `web.admit` with `credential_required=False`, because a
reviewer needs no model credential and this page makes no model call at all: an enrolled account
without a key is refused asking and admitted here. With no `[auth]` configured the door is open and
decisions record no account, which `user-identity` already requires.

An item is decided in two steps (ADR-0970). First the reviewer sees the quantity, the paper and
the two texts, chooses the text that states a value for the quantity and writes the value they
read -- and nothing else: not the stored value, not the paper's own name for it, not the
conditions, each of which would point at the answer. That choice is written. Only then is the
entry as stored revealed, and the reviewer approves or disapproves. An issue can be raised at
either step. A reviewer who leaves after the first step comes back to the second.

A person may narrow what they are shown to one domain or one topic, and may set a paper aside
("not my field"); the simulated reviewers get none of this (ADR-0980). Those are page arguments
to the serving query, and the runner never passes them.

Everything that is not a screen element is in `bionumbers.review` -- and in `bionumbers.deployment`
for the two things taken from the deployment, its database and a person's rung -- so what the page
decides is tested without a browser and only the order and lifetime of the elements needs `AppTest`
(`.claude/rules/streamlit-driver.md`).
"""

import time

import streamlit as st

from bionumbers import deployment, review, store
from scinumbers_ask import web

#: The one sentence for a deployment with no database behind it. It names the secrets section
#: rather than describing the symptom, because the operator's next move is to write that section --
#: and this is the likeliest first-deploy mistake, the same one `web.admit` reports for the
#: accounts table.
NO_STORE = (
    "This deployment has no review database: add a [connections.usage] section to Streamlit's "
    "secrets and create the tables from sql/review.sql. There is nothing to review until then."
)

#: The chosen box says so in its heading; the other says nothing.
CHOSEN = "chosen"

#: Each text is one box, and at the first step the whole box is the control (Yoav, 2026-10-09):
#: a click anywhere on it is the choice. Streamlit has no clickable container, so this is a small
#: custom component -- one `<button>` carrying the label, the location line and the text, drawn
#: in the theme's colours -- that reports a click as a trigger. Only the click crosses back;
#: the content is handed down on every run and set as text, never as markup.
_CARD_HTML = """
<button class="card" type="button">
  <span class="head"><span class="label"></span><span class="mark"></span></span>
  <span class="where"></span>
  <span class="text"></span>
</button>
"""
_CARD_CSS = """
.card {
  display: flex; flex-direction: column; gap: 0.5rem; width: 100%; box-sizing: border-box;
  text-align: left; padding: 1rem 1.1rem; border-radius: 0.5rem; cursor: pointer;
  border: 1px solid var(--st-border-color, #d6d6d9);
  background: var(--st-background-color, #fff); color: var(--st-text-color, #262730);
  font-family: var(--st-font, inherit); font-size: 1rem; line-height: 1.5;
}
.card:hover { border-color: var(--st-primary-color, #ff4b4b); }
.card:focus-visible { outline: 2px solid var(--st-primary-color, #ff4b4b); outline-offset: 2px; }
.card.chosen {
  border: 2px solid var(--st-primary-color, #ff4b4b);
  padding: calc(1rem - 1px) calc(1.1rem - 1px);
}
.card.still { cursor: default; }
.head { display: flex; justify-content: space-between; font-weight: 700; }
.mark { color: var(--st-primary-color, #ff4b4b); font-weight: 600; }
.where { font-size: 0.85rem; opacity: 0.7; }
.text { white-space: pre-wrap; }
"""
_CARD_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const card = parentElement.querySelector(".card")
  if (!card) return
  parentElement.querySelector(".label").textContent = data.label
  parentElement.querySelector(".mark").textContent = data.chosen ? data.mark : ""
  parentElement.querySelector(".where").textContent = data.where
  parentElement.querySelector(".text").textContent = data.text
  card.classList.toggle("chosen", Boolean(data.chosen))
  card.classList.toggle("still", !data.choosable)
  card.disabled = !data.choosable
  card.onclick = () => { if (data.choosable) setTriggerValue("clicked", data.label) }
}
"""
_CARD = st.components.v2.component(
    "scinumbers_text_card", html=_CARD_HTML, css=_CARD_CSS, js=_CARD_JS
)


def _text_card(shown, *, chosen: bool, choosable: bool, key: str) -> bool:
    """One text as a box, the whole of it a button while `choosable`. Returns whether it was
    clicked on this run."""
    result = _CARD(
        key=key,
        data={
            "item": item.item_id,
            "label": shown.label,
            "where": shown.location_line,
            "text": shown.text,
            "chosen": chosen,
            "choosable": choosable,
            "mark": CHOSEN,
        },
        on_clicked_change=lambda: None,
    )
    return result.clicked == shown.label


#: The widget key prefixes. Each widget's key is the prefix, the item id and the step, so a new
#: item -- or the same item's next step -- is a new set of widgets and starts blank -- a choice or
#: a comment carried over from the last screen is a decision nobody made. Popping the keys from
#: `session_state` after a save, the first version of this, left the buttons clicked and the
#: comment typed in the browser (seen by Yoav on 2026-09-22): the widget's own state outlived the
#: key. A fresh key is the mechanism Streamlit documents for a fresh widget.
CHOICE_KEY = "bionumbers.review.choice"
VALUE_KEY = "bionumbers.review.value"
VERDICT_KEY = "bionumbers.review.verdict"
COMMENT_KEY = "bionumbers.review.comment"
ISSUE_KEY = "bionumbers.review.issue"
#: `(item id, step, monotonic seconds)` for the screen now showing. Keyed by the item and the step
#: because the script reruns on every click: a clock restarted per run would measure the last
#: interaction rather than the decision, and one never restarted would charge this screen with the
#: time spent on the last.
STARTED_KEY = "bionumbers.review.started"

#: The buttons' labels. Raising an issue is two clicks -- the button opens a box, and a second
#: button confirms it -- so an issue is never one stray click away from a verdict, and the
#: reviewer can take it back; the skip button names the paper, not the item, because that is
#: what it sets aside.
CONTINUE = "Continue"
SAVE_AND_NEXT = "Save and next"
RAISE_AN_ISSUE = "Raise an issue"
CONFIRM_ISSUE = "Confirm the issue"
CANCEL_ISSUE = "Cancel issue"
SKIP_PAPER = "Skip this paper"
#: The screen whose issue box is open, if any: `<item id>:<step>`.
RAISING_KEY = "bionumbers.review.raising"

#: The filters' keys and their "no filter" option. One selectbox each, in the sidebar, so the
#: choice survives from item to item; `ANY` is a label, never a stored value.
DOMAIN_KEY = "bionumbers.review.domain"
TOPIC_KEY = "bionumbers.review.topic"
ANY = "All"

# Wide, because the two texts sit side by side (Yoav, 2026-10-09): a reviewer compares them, and
# comparison across a gap is easier than down a column.
st.set_page_config(page_title=review.TITLE, page_icon=":material/fact_check:", layout="wide")

# The token in the URL, and this browser session's own identity. Same two as the ask app, because
# `admit` and `draw_identity` are the ask app's and expect them (ADR-0830).
url_session = web.session_id(st.session_state, st.query_params)
tab = web.tab_id(st.session_state)

# Before anything is drawn. A visitor who is not signed in or not enrolled sees the door and no
# item: an item is the paper's text, and the reviewer's judgement of it is the record.
admission = web.admit(
    st.session_state, web.trail_destination, url_session, credential_required=False
)
if admission.door is not web.Door.OPEN:
    web.draw_closed_door(admission, url_session, tab)
    st.stop()

session = web.effective_session(admission, url_session)
# None where no identity is configured, which the spec allows explicitly: the decision is recorded
# with no account and nothing else about it differs. It is also what `next_item` serves on, so an
# unconfigured deployment has exactly one reviewer.
reviewer = admission.account.email if admission.account else None
# The rung their decisions count on (ADR-0990): from the account's role, so a person's approval
# can set a tier as a model's does.
reviewer_role = deployment.reviewer_role_of(admission.account)

engine = deployment.store_engine()

preference = store.Preference()
with st.sidebar:
    web.draw_identity(admission, session, tab)
    if engine is not None:
        # A person's choices (ADR-0980): the domain and topic they want, read off the papers
        # loaded, so an option is never offered that nothing matches.
        domain = st.selectbox("Domain", [ANY, *store.domains(engine)], key=DOMAIN_KEY)
        chosen_domain = None if domain == ANY else domain
        # The topics of the chosen domain only, and a fresh widget per domain: a topic kept
        # from another domain would name papers the filter can no longer reach.
        topics = store.topics(engine, chosen_domain)
        topic = (
            st.selectbox("Topic", [ANY, *topics], key=f"{TOPIC_KEY}:{domain}") if topics else ANY
        )
        preference = store.Preference(domain=chosen_domain, topic=None if topic == ANY else topic)
        # Read before the decision below is written, so the figure is what is left *including*
        # this item -- the count a reviewer watches go down as they save.
        st.caption(web.as_text(f"{store.remaining(engine, reviewer, preference)} left to review"))

web.draw_title(review.TITLE)

if engine is None:
    st.error(web.as_text(NO_STORE))
    st.stop()

item = store.next_item(engine, reviewer, preference)
if item is None:
    st.info(web.as_text(review.NOTHING_LEFT))
    st.stop()

# The reviewer's first step on this item, if taken: it decides which screen this is.
choice = store.open_choice(engine, item.item_id, reviewer)
step = 2 if choice else 1
key = f"{item.item_id}:{step}"

started = st.session_state.get(STARTED_KEY)
if started is None or started[:2] != (item.item_id, step):
    started = (item.item_id, step, time.monotonic())
    st.session_state[STARTED_KEY] = started

st.subheader(web.as_text(item.question))
paper_line, aside = st.columns([5, 1])
paper_line.caption(web.as_text(review.citation_line(item.paper)))
# Beside the paper, because it is the paper that is set aside: every item of it, for this
# reviewer, recorded (ADR-0980). Keyed per item so the click belongs to this screen. Not at the
# second step: a choice is written by then, and a paper set aside with an open row on it would
# leave that row open for ever -- the reveal is the point to finish or raise an issue.
if step == 1 and aside.button(SKIP_PAPER, key=f"skip:{item.item_id}"):
    try:
        store.skip_paper(
            engine, reviewer, run_id=item.claim.fingerprint.run_id, pmcid=item.paper.pmcid
        )
    except store.DecisionNotSaved:
        st.error(web.as_text(review.NOT_SAVED))
    else:
        st.session_state.pop(STARTED_KEY, None)
        st.rerun()

# Both texts side by side, in the order `texts_in_order` gives and never sorted, filtered or
# labelled further here: which is which is the question being asked. Each text as the paper wrote
# it, nothing in it emphasised (ADR-0940). Shown at both steps: the verdict is a judgement of the
# text against the stored entry, and a reviewer should not have to hold the text in memory across
# a click. At the first step each box carries its own choose button; the chosen box says so.
picked_key = f"{CHOICE_KEY}:{item.item_id}:1"
picked = (
    st.session_state.get(picked_key)
    if choice is None
    else review.chosen_label(item, choice.chosen_supporting)
)
for shown, column in zip(review.texts_in_order(item), st.columns(2), strict=True):
    with column:
        clicked = _text_card(
            shown,
            chosen=picked == shown.label,
            choosable=choice is None,
            key=f"card:{item.item_id}:{shown.label}",
        )
        if clicked and choice is None:
            st.session_state[picked_key] = shown.label
            st.rerun()

# The table a cell came from, whole and with its caption, both cells marked alike. Our own HTML,
# because `st.table` cannot draw a spanning header and the paper's layout is the point.
for table in review.tables_html(item):
    st.markdown(table, unsafe_allow_html=True)


def _save(write, *, on_saved) -> None:
    """One write, failing closed (ADR-0930): nothing advances and nothing is cleared on a
    refusal, so the next click retries this step rather than starting another."""
    try:
        write()
    except store.DecisionNotSaved:
        st.error(web.as_text(review.NOT_SAVED))
    else:
        on_saved()


def _next_screen() -> None:
    # The next screen brings its own widgets (see the key prefixes above); only the clock, the
    # open issue box and the remembered choice are ours to reset.
    st.session_state.pop(STARTED_KEY, None)
    st.session_state.pop(RAISING_KEY, None)
    st.session_state.pop(picked_key, None)
    st.rerun()


def _elapsed() -> float:
    return time.monotonic() - started[2]


def _issue_controls() -> bool:
    """The issue control for this screen. Returns True while the issue box is open, so the
    caller leaves its own save button out: with the box open the only question is whether to
    confirm the issue or take it back."""
    if st.session_state.get(RAISING_KEY) != key:
        if st.button(RAISE_AN_ISSUE, key=f"issue-button:{key}"):
            st.session_state[RAISING_KEY] = key
            st.rerun()
        return False
    issue = st.text_area(
        "What is wrong with this entry? It is recorded in place of a decision.",
        key=f"{ISSUE_KEY}:{key}",
    )
    confirm, cancel = st.columns(2)
    if confirm.button(CONFIRM_ISSUE, type="primary", key=f"confirm-issue:{key}"):
        try:
            text = review.issue_from(issue)
        except review.Incomplete as incomplete:
            st.warning(web.as_text(incomplete.message))
        else:
            _save(
                lambda: store.record_issue(
                    engine,
                    item.item_id,
                    reviewer=reviewer,
                    issue=text,
                    time_to_decide_s=_elapsed(),
                    reviewer_role=reviewer_role,
                ),
                on_saved=_next_screen,
            )
    if cancel.button(CANCEL_ISSUE, key=f"cancel-issue:{key}"):
        st.session_state.pop(RAISING_KEY, None)
        st.rerun()
    return True


if step == 1:
    # No default: `picked` is None until a box's button was clicked. A default would be recorded
    # verbatim by anyone who clicked straight past it, and it would be the same default every
    # time -- a bias in the dataset with no trace of itself.
    st.markdown(web.as_text(review.CHOICE_QUESTION))
    value_read = st.text_input(
        review.VALUE_QUESTION, key=f"{VALUE_KEY}:{key}", help=review.VALUE_HINT
    )
    raising = _issue_controls()
    if not raising and st.button(CONTINUE, type="primary"):
        try:
            first = review.first_step_from(item, picked, value_read)
        except review.Incomplete as incomplete:
            # The screen stays as it is, widgets and all: a reviewer who has given half an answer
            # is being asked for the other half, not asked again from the start.
            st.warning(web.as_text(incomplete.message))
        else:
            _save(
                lambda: store.record_choice(
                    engine,
                    item.item_id,
                    reviewer=reviewer,
                    chosen_supporting=first.chosen_supporting,
                    value_read=first.value_read,
                    time_to_decide_s=_elapsed(),
                    reviewer_role=reviewer_role,
                ),
                on_saved=_next_screen,
            )
else:
    # The reveal: what the reviewer answered, then the entry as stored. The value is shown only
    # now, after the reading it will be compared with is on record.
    st.markdown(
        web.as_text(
            f"You chose **{review.chosen_label(item, choice.chosen_supporting)}** and read the "
            f"value as **{choice.value_read}**."
        )
    )
    st.markdown(web.as_text(f"### Stored: {item.claim.value} {item.claim.unit}".rstrip()))
    # One line on how the reading stands to the stored value, and no more: it is a hint, and the
    # verdict below is the reviewer's.
    st.caption(web.as_text(review.agreement_line(choice.value_agreement)))
    # The paper's own term beside the question's: the reviewer is judging whether this paper's
    # "generation time" is the question's "doubling time", and they cannot if only one is on
    # screen.
    st.caption(web.as_text(f"the paper calls it: {item.claim.property_in_paper}"))
    st.table(
        [
            {"Condition": name, "Stated": provenance, "Quote": quote}
            for name, provenance, quote in review.condition_rows(
                item.claim, item.claim.fingerprint.scope
            )
        ]
    )
    verdict = st.radio(
        review.VERDICT_QUESTION,
        [review.APPROVE, review.DISAPPROVE],
        index=None,
        key=f"{VERDICT_KEY}:{key}",
    )
    comment = st.text_area("Comment (optional)", key=f"{COMMENT_KEY}:{key}")
    raising = _issue_controls()
    if not raising and st.button(SAVE_AND_NEXT, type="primary"):
        try:
            approved = review.verdict_from(verdict)
        except review.Incomplete as incomplete:
            st.warning(web.as_text(incomplete.message))
        else:
            _save(
                lambda: store.record_verdict(
                    engine,
                    item.item_id,
                    reviewer=reviewer,
                    approved=approved,
                    comment=comment,
                    time_to_decide_s=_elapsed(),
                ),
                on_saved=_next_screen,
            )
