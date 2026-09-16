"""The door: sign-in, enrolment, a credential per session, and a deployment that
has none of it and notices nothing.

Driven through `AppTest` because *when* things are drawn is a whole-script
question (`.claude/rules/streamlit-driver.md`): "offered sign-in and nothing
else" is a claim about what the page did not draw, and no unit below the script
can see that. The unconfigured test runs first and is the regression guard for
every other web test in this suite -- they all run with no `[auth]` in secrets.

What is stubbed, and why it is honest to: `web.signed_in_email` stands in for
`st.user`, which `AppTest` fixes to a test address with no `is_logged_in`;
`web.accounts.lookup` stands in for the database; `web.AskAgent` is wrapped to
record the credential each agent was built with. `web.admit` and `web.agent_for`
themselves run for real, which is the point.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with, ask_question
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted
from scinumbers_ask import messages, trace, web
from scinumbers_ask.accounts import Account, EnrolmentUnavailable
from scinumbers_ask.permissions import Identity, Role

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
TIMEOUT = 30

TESTER = Account(email="tester@example.org", role=Role.SCIENTIST, openrouter_key="sk-tester")
KEYLESS = Account(email="keyless@example.org", role=Role.STUDENT, openrouter_key=None)
DEV = Account(email="dev@example.org", role=Role.DEV, openrouter_key="sk-dev")


class _Caught(logging.Handler):
    """Every trail record, after the stamp -- what the durable sink would see."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def events(self) -> list[str]:
        return [r.getMessage() for r in self.records]

    def identities(self) -> set[tuple]:
        return {
            (getattr(r, "user_email", None), getattr(r, "user_role", None)) for r in self.records
        }


@pytest.fixture
def caught():
    logger = logging.getLogger(trace.LOGGER_NAME)
    trace.configure()
    web.install_identity_stamp()  # what `resources` does, which the tests replace
    handler = _Caught()
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    for f in [f for f in logger.filters if isinstance(f, web.IdentityStamp)]:
        logger.removeFilter(f)
    web.IDENTITIES.clear()


@pytest.fixture
def page(monkeypatch, repo, config, tmp_path):
    """Build the real script with the door set as a test chooses."""
    built: list[str | None] = []
    monkeypatch.setattr(web, "resources", lambda corpus=None: repo)
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    # Something, so `admit` reaches `lookup` rather than concluding "no database".
    monkeypatch.setattr(web, "trail_destination", lambda: object())

    def make(
        *,
        auth: bool,
        email: str | None = None,
        enrolled: dict[str, Account] | None = None,
        unavailable: bool = False,
        answers=("an answer",),
    ) -> AppTest:
        agent = agent_with(repo, config, tmp_path, scripted(*(says(a) for a in answers)))

        def building(repo_, config_, path, model=None, api_key=None):
            built.append(api_key)
            return agent

        monkeypatch.setattr(web, "AskAgent", building)
        monkeypatch.setattr(web, "signed_in_email", lambda: email)

        def lookup(engine, who, **kwargs):
            if unavailable:
                raise EnrolmentUnavailable("relation does not exist")
            return (enrolled or {}).get(who)

        monkeypatch.setattr(web.accounts, "lookup", lookup)
        at = AppTest.from_file(APP, default_timeout=TIMEOUT)
        if auth:
            at.secrets["auth"] = {"client_id": "test-client"}
        return at

    make.built = built  # type: ignore[attr-defined]
    return make


_ask = ask_question


def _sidebar_text(at: AppTest) -> str:
    return " ".join(c.value for c in at.sidebar.caption)


# --- 4.6: no `[auth]` -- everything as before -----------------------------------


def test_with_no_identity_configured_a_question_is_answered_without_signing_in(page, caught):
    """The regression guard for every existing web test, which all run this way."""
    at = page(auth=False).run()
    assert at.chat_input, "the input must be there with no sign-in"
    assert not at.button, "no sign-in button, no sign-out button"
    at = _ask(at, "how many?")
    assert not at.exception
    assert any("an answer" in m.value for m in at.markdown)
    assert "question.asked" in caught.events()
    # Records carry no account -- absent, not empty.
    assert caught.identities() == {(None, None)}
    assert page.built == [None], "the environment's key, exactly as before"


def test_with_no_identity_configured_the_page_says_so(page):
    at = page(auth=False).run()
    assert messages.NO_SIGN_IN_CONFIGURED in _sidebar_text(at)
    assert web.RECORDS_NOTE in _sidebar_text(at)


# --- 4.7: `[auth]` configured -------------------------------------------------------


def test_a_visitor_who_is_not_signed_in_is_offered_sign_in_and_nothing_else(page, caught):
    at = page(auth=True, email=None).run()
    assert not at.exception
    assert not at.chat_input, "a question could be asked"
    assert not at.markdown and not at.chat_message, "something was drawn"
    assert [b.label for b in at.button] == ["Sign in with Google"]
    assert caught.events() == [], "a record was written for a visitor who asked nothing"


def test_a_signed_in_account_that_is_not_enrolled_is_refused_and_recorded(page, caught):
    at = page(auth=True, email="stranger@example.org", enrolled={}).run()
    assert not at.chat_input
    assert messages.NOT_ENROLLED in [e.value for e in at.error]
    (refused,) = [r for r in caught.records if r.getMessage() == "signin.refused"]
    assert refused.fields["email"] == "stranger@example.org"
    assert not getattr(refused, "user_email", None), "refused, so no identity to stamp"
    assert web.IDENTITIES == {}, "a refused account must not enter the registry"


def test_a_refusal_is_recorded_once_per_session_not_once_per_rerun(page, caught):
    at = page(auth=True, email="stranger@example.org", enrolled={}).run()
    at.run()
    at.run()
    assert caught.events().count("signin.refused") == 1


def test_an_enrolled_account_is_admitted_and_its_records_carry_who_and_as_what(page, caught):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    assert at.chat_input
    at = _ask(at, "how many?")
    assert any("an answer" in m.value for m in at.markdown)
    assert caught.identities() == {(TESTER.email, "scientist")}
    assert page.built == ["sk-tester"], "funded by the account's own credential"


def test_the_sidebar_says_who_is_signed_in_and_offers_sign_out(page):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    assert messages.SIGNED_IN_AS.format(email=TESTER.email, role="scientist") in _sidebar_text(at)
    assert "Sign out" in [b.label for b in at.sidebar.button]
    assert web.RECORDS_NOTE in _sidebar_text(at)


def test_an_enrolled_account_with_no_credential_meets_a_door_of_its_own(page, caught):
    """The dangerous direction: an agent built with no key falls back to the
    environment's. So the assertion is on what was *built*, not on the page --
    and the account never reaches the page at all, because no credential is now
    a closed door rather than a page with its input removed."""
    at = page(auth=True, email=KEYLESS.email, enrolled={KEYLESS.email: KEYLESS}).run()
    assert not at.chat_input
    assert messages.NO_CREDENTIAL in [e.value for e in at.error]
    assert page.built == [], "an agent was built, and would spend the environment's key"
    assert "Sign out" in [b.label for b in at.button], "no way out of the closed door"


def test_the_no_credential_door_is_its_own_state_not_an_open_one(monkeypatch):
    _configured(monkeypatch, KEYLESS.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: KEYLESS)
    admission = web.admit({}, object(), "s1")
    assert admission.door is web.Door.NO_CREDENTIAL
    assert admission.account == KEYLESS, "enrolled, and the page can say so"


def test_agent_for_refuses_rather_than_falling_back_to_the_environment(repo):
    """Defence behind the door: if a configured account without a credential ever
    reached here, building with `api_key=None` would quietly spend the
    deployment's own key."""
    admission = web.Admission(web.Door.OPEN, configured=True, account=KEYLESS)
    with pytest.raises(ValueError):
        web.agent_for({}, repo, admission)


def test_an_unreadable_accounts_table_admits_nobody_and_says_a_different_sentence(page, caught):
    at = page(
        auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}, unavailable=True
    ).run()
    assert not at.chat_input
    errors = [e.value for e in at.error]
    assert messages.ENROLMENT_CHECK_UNAVAILABLE in errors
    assert messages.NOT_ENROLLED not in errors, "an outage must not read as 'not enrolled'"
    assert "signin.refused" not in caught.events()
    assert page.built == []


def test_the_credential_is_never_on_the_page(page):
    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER}).run()
    at = _ask(at, "how many?")
    everything = " ".join(
        [c.value for c in at.caption]
        + [m.value for m in at.markdown]
        + [e.value for e in at.error]
        + [i.value for i in at.info]
    )
    assert "sk-tester" not in everything


# --- 4.3: one repository, one agent per session ----------------------------------------


def test_two_sessions_get_two_agents_and_one_repository(monkeypatch, tmp_path):
    """Through the real cached `resources` and the real `agent_for`. The index is
    the expensive thing and stays shared; the agent holds a credential and
    cannot be."""
    from scinumbers_ask.corpus import load
    from scinumbers_ask.repository import CorpusRepository

    web.resources.clear()
    counts = {"indexed": 0, "agents": 0}
    rows = load(FIXTURE)
    monkeypatch.setattr(web, "load", lambda path: rows)

    def counting_repository(entries):
        counts["indexed"] += 1
        return CorpusRepository(entries)

    real_agent = web.AskAgent

    def counting_agent(*args, **kwargs):
        counts["agents"] += 1
        return real_agent(*args, **kwargs)

    monkeypatch.setattr(web, "CorpusRepository", counting_repository)
    monkeypatch.setattr(web, "AskAgent", counting_agent)
    monkeypatch.setattr(web.trace, "to_file", lambda spec: None)
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    try:
        one = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        one.run()  # a rerun of the same session builds nothing new
        AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    finally:
        web.resources.clear()
    assert counts == {"indexed": 1, "agents": 2}


# --- `admit` and `agent_for` below the page ----------------------------------------------


def _configured(monkeypatch, email):
    monkeypatch.setattr(web, "identity_configured", lambda: True)
    monkeypatch.setattr(web, "signed_in_email", lambda: email)


def test_enrolment_is_read_once_per_account_per_session(monkeypatch):
    calls: list[str] = []
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: calls.append(who) or TESTER)
    state: dict = {}
    try:
        for _ in range(3):
            assert web.admit(state, object(), "s1").door is web.Door.OPEN
        assert calls == [TESTER.email]
        # A different account on the same tab is looked up afresh.
        monkeypatch.setattr(web, "signed_in_email", lambda: DEV.email)
        monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: calls.append(who) or DEV)
        admission = web.admit(state, object(), "s1")
        assert admission.account == DEV
        assert calls == [TESTER.email, DEV.email]
        session = web.effective_session(admission, "s1")
        web.establish_identity(admission, session)
        assert web.IDENTITIES[session] == Identity(DEV.email, Role.DEV)
    finally:
        web.IDENTITIES.clear()


def test_an_unavailable_check_is_retried_on_the_next_rerun(monkeypatch):
    """ "Try again shortly" has to mean the next rerun tries again."""
    _configured(monkeypatch, TESTER.email)
    attempts = {"n": 0}

    def flaky(engine, who, **k):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise EnrolmentUnavailable("asleep")
        return TESTER

    monkeypatch.setattr(web.accounts, "lookup", flaky)
    state: dict = {}
    try:
        assert web.admit(state, object(), "s1").door is web.Door.UNAVAILABLE
        assert web.admit(state, object(), "s1").door is web.Door.OPEN
    finally:
        web.IDENTITIES.clear()


def test_no_database_at_all_says_so_rather_than_asking_the_reader_to_wait(monkeypatch):
    """`[auth]` set and `[connections.usage]` not is the likeliest first-deploy
    mistake, and it never comes right on its own -- so "try again shortly" would
    leave every visitor waiting on a retry that cannot succeed."""
    _configured(monkeypatch, TESTER.email)
    door = web.admit({}, None, "s1").door
    assert door is web.Door.NO_ACCOUNTS_DATABASE
    assert door is not web.Door.OPEN, "fails closed either way"
    assert messages.NO_ACCOUNTS_DATABASE != messages.ENROLMENT_CHECK_UNAVAILABLE


def test_signing_out_forgets_the_session_s_identity(monkeypatch):
    """The page establishes identity every rerun, so the rerun after sign-out --
    which has no account -- is what clears it."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    state: dict = {}
    try:
        admission = web.admit(state, object(), "s1")
        session = web.effective_session(admission, "s1")
        web.establish_identity(admission, session)
        assert session in web.IDENTITIES
        monkeypatch.setattr(web, "signed_in_email", lambda: None)
        after = web.admit(state, object(), "s1")
        assert after.door is web.Door.SIGN_IN
        web.establish_identity(after, web.effective_session(after, "s1"))
        assert web.ADMISSION_KEY not in state
        web.end_session(session)
        assert session not in web.IDENTITIES
    finally:
        web.IDENTITIES.clear()


def test_a_refusal_after_another_account_was_admitted_carries_no_stamp(monkeypatch, caught):
    """A verifier produced this row: admit as one account, then a stranger on the
    same session id with no signed-out rerun between, and the refusal came out
    stamped with the *first* account's email. The registry entry has to go
    before the lookup, not only on sign-out."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    state: dict = {}
    admitted = web.admit(state, object(), "s1")
    web.establish_identity(admitted, web.effective_session(admitted, "s1"))
    monkeypatch.setattr(web, "signed_in_email", lambda: "stranger@example.org")
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: None)
    assert web.admit(state, object(), "s1").door is web.Door.NOT_ENROLLED
    (refused,) = [r for r in caught.records if r.getMessage() == "signin.refused"]
    assert refused.fields["email"] == "stranger@example.org"
    assert getattr(refused, "user_email", None) is None, (
        "the refusal is recorded against the URL token, which no account owns"
    )
    assert getattr(refused, "user_role", None) is None
    assert "s1" not in web.IDENTITIES


def test_sign_out_forgets_the_identity_and_then_logs_out(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(web.st, "logout", lambda: calls.append("logout"))
    web.remember_identity("s1", Identity(TESTER.email, Role.SCIENTIST))
    try:
        web._sign_out("s1")
        assert "s1" not in web.IDENTITIES
        assert calls == ["logout"]
    finally:
        web.IDENTITIES.clear()


def test_identity_is_not_configured_when_there_is_no_secrets_file_at_all(monkeypatch):
    """This checkout has a real secrets file, so the branch for a machine with
    none never runs here unless made to. Streamlit raises its own error for
    the missing file; that is "not configured", and anything else is not."""
    from streamlit.errors import StreamlitSecretNotFoundError

    class _NoFile:
        def __contains__(self, key):
            raise StreamlitSecretNotFoundError("no secrets.toml")

    class _Broken:
        def __contains__(self, key):
            raise RuntimeError("malformed")

    monkeypatch.setattr(web.st, "secrets", _NoFile())
    assert web.identity_configured() is False
    monkeypatch.setattr(web.st, "secrets", _Broken())
    with pytest.raises(RuntimeError):
        web.identity_configured()


def test_agent_for_holds_one_agent_per_state_and_rebuilds_on_a_new_credential(
    monkeypatch, repo, tmp_path
):
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    built: list = []
    monkeypatch.setattr(
        web, "AskAgent", lambda *a, api_key=None, **k: built.append(api_key) or object()
    )
    state: dict = {}
    open_as = web.Admission(web.Door.OPEN, configured=True, account=TESTER)
    first = web.agent_for(state, repo, open_as)
    assert web.agent_for(state, repo, open_as) is first
    assert built == ["sk-tester"]
    web.agent_for(state, repo, web.Admission(web.Door.OPEN, configured=True, account=DEV))
    assert built == ["sk-tester", "sk-dev"]
    assert web.agent_for({}, repo, web.Admission(web.Door.OPEN, configured=False)) is not first
    assert built[-1] is None, "unconfigured: the environment's key"


def test_signed_in_email_is_none_without_is_logged_in(monkeypatch):
    """`AppTest` fixes `st.user` to an address with no `is_logged_in`; a real
    unconfigured deployment has no such key either. Neither is signed in."""
    monkeypatch.setattr(web.st, "user", type("U", (), {"to_dict": lambda self: {"email": "x@y"}})())
    assert web.signed_in_email() is None
    monkeypatch.setattr(
        web.st,
        "user",
        type("U", (), {"to_dict": lambda self: {"email": "x@y", "is_logged_in": True}})(),
    )
    assert web.signed_in_email() == "x@y"


# --- 4.5: the note, both variants -----------------------------------------------------------


def test_the_note_is_one_short_sentence_whatever_is_configured():
    """Deliberately not an enumeration, and deliberately not two sentences: the
    fuller statement of what is kept about a person is deferred to a disclaimer
    shown once before use, when there are users to show it to."""
    assert messages.RECORDS_NOTE == "All exchange in this app is logged for product development."
    assert messages.RECORDS_NOTE.count(".") == 1
    assert "account" not in messages.RECORDS_NOTE and "role" not in messages.RECORDS_NOTE


def test_a_signed_in_tester_is_told_whom_to_ask_when_the_allowance_is_spent():
    """The funder-neutral sentence was written so a developer on their own key is
    not told to contact themselves. A signed-in tester is not the funder, so
    the page may -- must -- say whom to ask, and that the allowance renews."""
    from scinumbers_ask.events import EndReason

    plain = messages.run_over_advice(EndReason.PROVIDER_LIMIT)
    tester = messages.run_over_advice(EndReason.PROVIDER_LIMIT, signed_in=True)
    assert "ask" not in plain.lower()
    assert "ask whoever runs this deployment" in tester
    assert "renews" in tester and "monthly" in tester
    assert "new session will not help" in tester
    # Endings with no advice of their own stay that way for both readers.
    assert messages.run_over_advice(EndReason.RUN_BUDGET, signed_in=True) is None


def test_the_no_credential_sentence_says_whom_to_ask():
    assert "Ask whoever runs this deployment" in messages.NO_CREDENTIAL


def test_the_page_shows_a_tester_the_tester_s_wording_and_a_developer_the_neutral_one(
    page, caught, repo, config, tmp_path
):
    from conftest import agent_with

    from agent_doubles import OutOfCreditModel, says

    def _spent_agent():
        return agent_with(repo, config, tmp_path, OutOfCreditModel(responses=[says("x")]))

    at = page(auth=True, email=TESTER.email, enrolled={TESTER.email: TESTER})
    monkeypatch_agent = _spent_agent()
    import scinumbers_ask.web as w

    original = w.agent_for
    w.agent_for = lambda state, repo_, admission: monkeypatch_agent
    try:
        at = _ask(at.run(), "how many?")
        banner = " ".join(e.value for e in at.error)
        assert "ask whoever runs this deployment" in banner
        assert "whoever funds it" not in banner

        w.agent_for = lambda state, repo_, admission: _spent_agent()
        dev = _ask(page(auth=False).run(), "how many?")
        banner = " ".join(e.value for e in dev.error)
        assert "whoever funds it" in banner
        assert "ask whoever runs this deployment" not in banner
    finally:
        w.agent_for = original


# --- the session is keyed on the account, not on the shared link ------------------------


def _admitted(account: Account) -> web.Admission:
    return web.Admission(web.Door.OPEN, configured=True, account=account)


def test_two_accounts_on_one_shared_link_get_two_sessions():
    """The defect this model exists to remove: `?session=` is shared by anyone
    given the link, so keying identity on it let the second reader's sign-in
    overwrite the first's stamp, and every later record of the first reader was
    attributed to the second."""
    link = "abc123"
    one = web.effective_session(_admitted(TESTER), link)
    two = web.effective_session(_admitted(DEV), link)
    assert one != two
    try:
        web.establish_identity(_admitted(TESTER), one)
        web.establish_identity(_admitted(DEV), two)
        assert web.IDENTITIES[one] == Identity(TESTER.email, Role.SCIENTIST)
        assert web.IDENTITIES[two] == Identity(DEV.email, Role.DEV)
    finally:
        web.IDENTITIES.clear()


def test_the_account_s_session_survives_a_url_token_that_changed_or_vanished():
    """Streamlit's OAuth callback and logout redirect to the bare base URL, so
    the token is gone on the rerun after sign-in. A key derived from the account
    does not care."""
    account = _admitted(TESTER)
    assert web.effective_session(account, "abc") == web.effective_session(account, "zzz")
    assert web.effective_session(account, "") == web.effective_session(account, "abc")


def test_with_no_identity_configured_the_url_token_is_still_the_session():
    """A developer's machine keeps today's bookmarkable behaviour."""
    unconfigured = web.Admission(web.Door.OPEN, configured=False)
    assert web.effective_session(unconfigured, "abc123") == "abc123"


def test_the_session_key_does_not_carry_the_address_in_the_clear():
    """It is shown in the page's caption and lands in the trail; an email there
    would put the account in places the stamp already covers properly."""
    assert TESTER.email not in web.effective_session(_admitted(TESTER), "abc")


def test_a_session_pruned_for_idleness_is_stamped_again_when_its_reader_returns(monkeypatch):
    """The silent one: prune evicts the identity, the held admission short-cuts
    the lookup, and every later record of a still-signed-in tab was written with
    no account while the sidebar still named one."""
    _configured(monkeypatch, TESTER.email)
    monkeypatch.setattr(web.accounts, "lookup", lambda e, who, **k: TESTER)
    state: dict = {}
    try:
        first = web.admit(state, object(), "url")
        session = web.effective_session(first, "url")
        web.establish_identity(first, session)
        web.forget_identity(session)  # what prune does after the idle window
        held = web.admit(state, object(), "url")
        assert held.account == TESTER, "the held admission is still the fast path"
        web.establish_identity(held, session)
        assert web.IDENTITIES[session] == Identity(TESTER.email, Role.SCIENTIST)
    finally:
        web.IDENTITIES.clear()


def test_ending_a_session_clears_the_identity_the_panel_and_the_place():
    """Sign-out cleared the identity and left the panel rows, so the next account
    on that tab could be shown the last one's questions."""
    import logging

    handler = web.install_recent_trail()
    web.session_registry.clear()
    try:
        web.remember_identity("s1", Identity(TESTER.email, Role.SCIENTIST))
        record = logging.LogRecord("x", logging.INFO, "f", 1, "question.asked", None, None)
        record.session_id, record.question_id, record.fields = "s1", "q1", {"question": "secret?"}
        handler.emit(record)
        assert web.session_registry().admit("s1")
        assert handler.rows("s1") and "s1" in web.IDENTITIES
        web.end_session("s1", "s1")
        assert handler.rows("s1") == []
        assert "s1" not in web.IDENTITIES
        assert web.session_registry().live() == 0
    finally:
        logging.getLogger(web.trace.LOGGER_NAME).removeHandler(handler)
        web.RECENT = None
        web.IDENTITIES.clear()
        web.session_registry.clear()


def test_the_cap_counts_tabs_and_not_accounts(monkeypatch):
    """One account is one conversation across its tabs (ADR-0830), so a cap keyed
    on the conversation would count *accounts*: eight testers with five tabs each
    is forty Streamlit sessions and forty agents, reported as eight. What costs
    the host is a tab, so that is what the registry holds."""
    web.session_registry.clear()
    try:
        registry = web.session_registry()
        conversation = web.effective_session(_admitted(TESTER), "ignored")
        for tab in ("tab-1", "tab-2", "tab-3"):
            assert registry.admit(tab, conversation)
        assert registry.live() == 3, "three tabs of one account are three sessions"
    finally:
        web.session_registry.clear()


def test_the_stamp_survives_the_prune_that_admitting_performs(monkeypatch):
    """The ordering the page depends on. `admit` prunes, and pruning clears the
    stamp of a conversation whose last tab has gone; establishing identity before
    that call had the stamp wiped in the same run, so a reader returning after
    the idle window asked their question against no account at all."""
    now = {"t": 1000.0}
    registry = web.SessionRegistry(max_sessions=20, idle_s=600, clock=lambda: now["t"])
    admission = _admitted(TESTER)
    conversation = web.effective_session(admission, "url")
    try:
        registry.admit("url", conversation)
        web.establish_identity(admission, conversation)
        assert web.IDENTITIES[conversation] == Identity(TESTER.email, Role.SCIENTIST)

        now["t"] += 601  # the reader steps away, then comes back and asks
        registry.admit("url", conversation)
        web.establish_identity(admission, conversation)
        assert web.IDENTITIES[conversation] == Identity(TESTER.email, Role.SCIENTIST), (
            "the stamp was pruned away in the same run that set it"
        )
    finally:
        web.IDENTITIES.clear()


def test_pruning_one_tab_leaves_a_conversation_another_tab_is_still_in():
    """The stamp belongs to the conversation, so it may only go when the last tab
    holding it does."""
    now = {"t": 1000.0}
    registry = web.SessionRegistry(max_sessions=20, idle_s=600, clock=lambda: now["t"])
    admission = _admitted(TESTER)
    conversation = web.effective_session(admission, "url")
    try:
        registry.admit("tab-1", conversation)
        registry.admit("tab-2", conversation)
        web.establish_identity(admission, conversation)
        now["t"] += 400
        registry.admit("tab-2", conversation)  # one tab keeps rerunning
        now["t"] += 400  # tab-1 is now past its window, tab-2 is not
        registry.prune()
        assert conversation in web.IDENTITIES, "the live tab's conversation was cleared"
        now["t"] += 601
        registry.prune()
        assert conversation not in web.IDENTITIES, "the last tab went and nothing was cleared"
    finally:
        web.IDENTITIES.clear()


def test_a_malformed_cap_setting_falls_back_rather_than_taking_the_page_down(monkeypatch, capsys):
    monkeypatch.setenv(web.MAX_SESSIONS_ENV, "twenty")
    web.session_registry.clear()
    try:
        assert web.session_registry().max_sessions == web.DEFAULT_MAX_SESSIONS
        assert "not a number" in capsys.readouterr().err
    finally:
        web.session_registry.clear()


def test_the_url_token_is_neither_advertised_nor_adopted_under_sign_in():
    """Not advertised, because it would name a conversation that opening it does
    not reach. Not adopted either, because under sign-in it is the tab's identity
    for the session cap -- and ten testers on one shared bookmark would register
    as a single tab, bounding nothing, with any one of them able to free the
    place the other nine sit in."""
    state, params = {}, {"session": "abc123"}
    minted = web.session_id(state, params, advertise=False)
    assert minted != "abc123", "the link decided which tab this is"
    assert "session" not in params
    assert web.session_id(state, params, advertise=False) == minted, "stable for this tab"

    state, params = {}, {"session": "abc123"}
    assert web.session_id(state, params, advertise=True) == "abc123"
    assert params["session"] == "abc123", "a developer's machine keeps its bookmark"


def test_the_suite_runs_as_though_no_sign_in_were_configured():
    """The insulation `conftest` provides, pinned where it will be read.

    Without it the suite's result depends on whether the developer running it
    happens to have Google sign-in in their own `.streamlit/secrets.toml` --
    which they will, the day they set up the deployment. Sixty-four tests failed
    exactly that way, on a tree that had not changed.
    """
    assert web.identity_configured() is False
