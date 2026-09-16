"""The dev panel: present for the roles granted it, absent for the rest, and
this session's only.

Both directions through the real script, because "absent -- not disabled" is a
claim about what the page did not draw. The deny case varies the dimension the
rule reads: a *student* -- an enrolled account with a real role -- and not only a
visitor with no identity. The panel is the only thing that puts a `dataframe` in
the sidebar, so its presence is asserted on that element and on the "Dev" header.
"""

from __future__ import annotations

# ruff: noqa: F811 -- `page` and `caught` are fixtures imported from the identity
# tests; pytest registers them by name, and every use below is that registration.
import logging

import pytest
from test_web_driver_identity import DEV, TESTER, _ask, caught, page  # noqa: F401 - fixtures

from scinumbers_ask import trace, web
from scinumbers_ask.accounts import Account
from scinumbers_ask.authorization import Refused
from scinumbers_ask.permissions import Role

STUDENT = Account(email="student@example.org", role=Role.STUDENT, openrouter_key="sk-student")
ADMIN = Account(email="admin@example.org", role=Role.ADMIN, openrouter_key="sk-admin")


@pytest.fixture
def recent(caught):
    """The panel's sink, installed as `resources` would install it."""
    handler = web.install_recent_trail()
    yield handler
    logging.getLogger(trace.LOGGER_NAME).removeHandler(handler)
    web.RECENT = None


def _panel(at):
    return at.sidebar.dataframe


def _dev_header(at) -> bool:
    return any(h.value == "Dev" for h in at.sidebar.header)


# --- both directions, through the page -------------------------------------------------


@pytest.mark.parametrize("account", [DEV, ADMIN], ids=["dev", "admin"])
def test_an_operator_s_page_has_the_section(page, recent, account):
    at = page(auth=True, email=account.email, enrolled={account.email: account}).run()
    assert _dev_header(at)
    assert len(_panel(at)) == 1


@pytest.mark.parametrize(
    "account",
    [
        STUDENT,
        Account(email="sci@example.org", role=Role.SCIENTIST, openrouter_key="k"),
        Account(email="sen@example.org", role=Role.SENIOR_SCIENTIST, openrouter_key="k"),
    ],
    ids=["student", "scientist", "senior scientist"],
)
def test_a_tester_s_page_has_no_such_section(page, recent, account):
    """Absent, not disabled: no header, no table, of any kind, anywhere in the sidebar."""
    at = page(auth=True, email=account.email, enrolled={account.email: account}).run()
    assert not at.exception
    assert at.chat_input, "control: the tester was admitted and can ask"
    assert not _dev_header(at)
    assert not _panel(at)


def test_the_section_is_below_the_run_status(page, recent):
    """The spec says where, and a verifier moved it above with every test green."""
    at = page(auth=True, email=DEV.email, enrolled={DEV.email: DEV}).run()
    headers = [h.value for h in at.sidebar.header]
    assert "Run budget" in headers, "control: the run status was drawn"
    assert headers.index("Run budget") < headers.index("Dev")


def test_installing_the_panel_s_sink_twice_leaves_one():
    logger = logging.getLogger(trace.LOGGER_NAME)
    before = list(logger.handlers)
    try:
        web.install_recent_trail()
        web.install_recent_trail()
        assert sum(isinstance(h, web.RecentTrail) for h in logger.handlers) == 1
    finally:
        logger.handlers[:] = before
        web.RECENT = None


def test_a_fresh_operator_session_shows_the_section_empty(page, recent):
    """ "Nothing yet" must look different from "not permitted"."""
    at = page(auth=True, email=DEV.email, enrolled={DEV.email: DEV}).run()
    (table,) = _panel(at)
    assert len(table.value) == 0
    assert list(table.value.columns) == list(web.PANEL_COLUMNS)


def test_the_table_names_the_question_just_asked(page, recent):
    at = page(auth=True, email=DEV.email, enrolled={DEV.email: DEV}).run()
    at = _ask(at, "how many ribosomes?")
    (table,) = _panel(at)
    assert "how many ribosomes?" in set(table.value["question"])
    assert "question.asked" in set(table.value["event"])
    assert "answer.given" in set(table.value["event"])


def test_the_developer_s_machine_sees_the_panel(page, recent):
    """No identity configured: the deferred decision, as the spec states it."""
    at = page(auth=False).run()
    assert _dev_header(at)
    assert len(_panel(at)) == 1


# --- this session's only ---------------------------------------------------------------------


def test_two_sessions_panels_show_only_their_own_records(page, recent):
    """The question text differs between the two, so a shared buffer cannot pass."""
    one = page(auth=True, email=DEV.email, enrolled={DEV.email: DEV}).run()
    one = _ask(one, "first session's question")
    two = page(auth=True, email=ADMIN.email, enrolled={ADMIN.email: ADMIN}).run()
    two = _ask(two, "second session's question")
    one.run()  # redraw, so the first panel would show the second's rows if it leaked

    (first,), (second,) = _panel(one), _panel(two)
    assert set(first.value["question"]) == {"first session's question"}
    assert set(second.value["question"]) == {"second session's question"}


def test_the_panel_holds_the_last_five_questions_and_drops_the_sixth_s_predecessor():
    handler = web.RecentTrail(questions=5)
    for n in range(7):
        q = trace.QuestionTrace(question_id=f"q{n}", session_id="s")
        q.record("question.asked", question=f"question {n}")
        q.record("search")
    rows = handler.rows("s")
    assert rows == []  # not attached to the logger; drive `emit` directly
    for n in range(7):
        rec = logging.LogRecord("x", logging.INFO, "f", 1, "question.asked", None, None)
        rec.session_id, rec.question_id, rec.fields = "s", f"q{n}", {"question": f"question {n}"}
        handler.emit(rec)
    kept = {r["question"] for r in handler.rows("s")}
    assert kept == {f"question {n}" for n in range(2, 7)}


def test_rows_without_a_question_are_not_a_question_s_records():
    """A refused sign-in has a session and no question; it is not the panel's."""
    handler = web.RecentTrail()
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "signin.refused", None, None)
    rec.session_id, rec.question_id, rec.fields = "s", "", {"email": "x@example.org"}
    handler.emit(rec)
    assert handler.rows("s") == []


# --- the refusal is in the accessor -------------------------------------------------------------


def test_the_accessor_refuses_a_tester_and_no_identity_but_gives_a_dev_the_rows(recent):
    configured = lambda account: web.Admission(web.Door.OPEN, configured=True, account=account)  # noqa: E731
    with pytest.raises(Refused):
        web.dev_panel_rows(configured(STUDENT), "s")
    with pytest.raises(Refused):
        web.dev_panel_rows(configured(None), "s")
    assert web.dev_panel_rows(configured(DEV), "s") == []
    assert web.dev_panel_rows(web.Admission(web.Door.OPEN, configured=False), "s") == []


def test_the_refusal_does_not_depend_on_the_caller(recent):
    """Spec: "by any caller". The page and a direct call meet the same refusal."""
    admission = web.Admission(web.Door.OPEN, configured=True, account=TESTER)
    with pytest.raises(Refused) as direct:
        web.dev_panel_rows(admission, "s")
    assert direct.value.permission.value == "dev panel"


# --- nothing here reaches the model -----------------------------------------------------------


def test_the_panel_s_contents_do_not_reach_the_model(page, recent, repo, config, tmp_path):
    """Positive control first: the question reached the model. Then: the event
    names and detail the panel shows are nowhere in what the model was handed."""
    from conftest import agent_with

    from agent_doubles import says, scripted

    model = scripted(says("first"), says("second"))
    agent = agent_with(repo, config, tmp_path, model)
    at = page(auth=True, email=DEV.email, enrolled={DEV.email: DEV})
    import scinumbers_ask.web as w

    w_agent_for = w.agent_for
    w.agent_for = lambda state, repo_, admission: agent
    try:
        at = _ask(at.run(), "how many ribosomes?")
        at = _ask(at, "and how big?")
    finally:
        w.agent_for = w_agent_for
    (table,) = _panel(at)
    shown = set(table.value["event"]) | set(table.value["detail"])
    assert shown, "control: the panel showed something"
    seen = " ".join(str(m.content) for m in model.seen)
    assert "how many ribosomes?" in seen, "control: the question reached the model"
    for fragment in ("question.asked", "answer.given", "spend.increment"):
        assert fragment not in seen
