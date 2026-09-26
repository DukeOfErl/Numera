"""The session cap: a guard for the host, by heartbeat, never by address.

Through the real script, because "the (N+1)th visitor sees one sentence and
nothing else" is a whole-script claim; and directly against `SessionRegistry`
for the clock, because AppTest cannot wait ten minutes. The registry is a
cached resource, so it is cleared on both sides of every test here -- otherwise
one test's sessions are the next test's crowd.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURE, agent_with, ask_question
from streamlit.testing.v1 import AppTest

from agent_doubles import says, scripted
from scinumbers_ask import messages, web

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "streamlit_app.py")
TIMEOUT = 30


@pytest.fixture
def capped(monkeypatch, repo, config, tmp_path):
    """The real script with a cap of two, over a scripted agent."""
    monkeypatch.setenv(web.MAX_SESSIONS_ENV, "2")
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setattr(web, "resources", lambda corpus=None: repo)
    agent = agent_with(repo, config, tmp_path, scripted(says("an answer")))
    monkeypatch.setattr(web, "agent_for", lambda state, repo, admission: agent)
    web.session_registry.clear()
    yield lambda: AppTest.from_file(APP, default_timeout=TIMEOUT)
    web.session_registry.clear()


def _turned_away(at: AppTest) -> bool:
    return messages.TRY_LATER in [w.value for w in at.warning]


# --- through the page --------------------------------------------------------------------


def test_the_session_past_the_cap_is_told_to_try_later(capped):
    first, second, third = capped().run(), capped().run(), capped().run()
    assert first.chat_input and second.chat_input, "the first two were admitted"
    assert _turned_away(third)
    assert not third.chat_input and not third.button and not third.chat_message, (
        "the turned-away visitor was offered something"
    )


def test_an_admitted_session_is_never_ended_to_make_room(capped):
    first, second = capped().run(), capped().run()
    capped().run()  # the third, refused
    first.run()
    second.run()
    assert first.chat_input and second.chat_input
    assert not _turned_away(first) and not _turned_away(second)


def test_a_refused_visitor_holds_no_place(capped):
    """Refused and not recorded: otherwise the crowd at the door would fill the
    room from outside it, and nobody would ever get in."""
    capped().run(), capped().run()
    for _ in range(5):
        assert _turned_away(capped().run())
    assert web.session_registry().live() == 2


def test_a_visitor_who_has_not_passed_the_door_holds_no_place(capped, monkeypatch):
    """Counting before the door meant every abandoned sign-in page held a slot
    for the idle window -- and Streamlit's OAuth callback drops the query string,
    so each sign-in stranded exactly one. What costs the host is a session with
    an agent behind it, which is what the cap now counts."""
    monkeypatch.setattr(web, "identity_configured", lambda: True)
    monkeypatch.setattr(web, "signed_in_claims", lambda: None)
    for _ in range(5):
        at = capped().run()
        assert not at.chat_input, "control: the door was closed"
        assert not _turned_away(at)
    assert web.session_registry().live() == 0


def test_a_session_mid_conversation_is_not_turned_away_when_the_cap_fills(capped):
    """ "No open session is ended" has to survive pruning: a reader who steps away
    past the idle window loses their heartbeat, and without this comes back to a
    try-later page with their transcript gone."""
    reader = capped().run()
    reader = ask_question(reader, "how many?")
    registry = web.session_registry()
    session = reader.session_state[web.SESSION_KEY]
    registry.drop(session)  # what prune does after the idle window
    for _ in range(registry.max_sessions):
        capped().run()
    assert registry.live() == registry.max_sessions

    returned = reader.run()
    assert not _turned_away(returned), "a reader mid-conversation was turned away"
    assert returned.chat_input


def test_a_genuinely_new_session_is_still_refused_at_the_cap(capped):
    """The other direction: `continuing` must not become a way in for everyone."""
    capped().run(), capped().run()
    assert _turned_away(capped().run())


def test_the_cap_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(web.MAX_SESSIONS_ENV, "7")
    monkeypatch.setenv(web.SESSION_IDLE_ENV, "42")
    web.session_registry.clear()
    try:
        registry = web.session_registry()
        assert (registry.max_sessions, registry.idle_s) == (7, 42.0)
    finally:
        web.session_registry.clear()


# --- the clock, against the registry directly -----------------------------------------------


def _registry(max_sessions=2, idle_s=600.0):
    now = {"t": 1000.0}
    registry = web.SessionRegistry(max_sessions=max_sessions, idle_s=idle_s, clock=lambda: now["t"])
    return registry, now


def test_a_continuing_session_is_admitted_over_the_cap_but_a_new_one_is_not():
    registry, _ = _registry(max_sessions=1)
    assert registry.admit("a")
    assert not registry.admit("b"), "a new session at the cap"
    assert registry.admit("b", continuing=True), "a tab already holding a conversation"
    assert registry.live() == 2


def test_dropping_a_session_frees_its_place_at_once():
    registry, _ = _registry(max_sessions=1)
    assert registry.admit("a")
    assert not registry.admit("b")
    registry.drop("a")
    assert registry.admit("b")


def test_a_session_that_goes_idle_frees_a_place():
    registry, now = _registry()
    assert registry.admit("a") and registry.admit("b")
    assert not registry.admit("c")
    now["t"] += 601  # both quiet past the window
    assert registry.admit("c")
    assert registry.live() == 1


def test_a_session_that_keeps_rerunning_keeps_its_place():
    """Varies the dimension the rule reads -- the last heartbeat -- and not only
    the clock: `a` reruns, `b` does not, and only `b` is freed."""
    registry, now = _registry()
    registry.admit("a"), registry.admit("b")
    now["t"] += 400
    registry.admit("a")
    now["t"] += 400
    assert registry.live() == 1
    assert registry.admit("a"), "the live one was evicted"
    assert registry.admit("c"), "the idle one's place was not freed"


def test_pruning_a_session_forgets_its_identity_and_its_panel_rows():
    from scinumbers_ask.permissions import Identity, Role

    registry, now = _registry()
    handler = web.install_recent_trail()
    try:
        registry.admit("s1")
        web.remember_identity("s1", Identity("p@example.org", Role.DEV))
        import logging

        rec = logging.LogRecord("x", logging.INFO, "f", 1, "question.asked", None, None)
        rec.session_id, rec.question_id, rec.fields = "s1", "q1", {"question": "?"}
        handler.emit(rec)
        assert "s1" in web.IDENTITIES and handler.rows("s1")
        now["t"] += 601
        registry.prune()
        assert "s1" not in web.IDENTITIES
        assert handler.rows("s1") == []
    finally:
        import logging

        logging.getLogger(web.trace.LOGGER_NAME).removeHandler(handler)
        web.RECENT = None
        web.IDENTITIES.clear()


# --- what it is not ----------------------------------------------------------------------------


def test_nothing_reads_the_client_s_address():
    """`st.context.ip_address` is supplied by the client. Asserted over the
    *identifiers* of the two files that could reach for it -- attributes, names
    and string keys -- not over their text, which is allowed to say why not."""
    import ast

    forbidden = {"ip_address", "remote_ip", "X-Forwarded-For", "x-forwarded-for"}
    for path in (ROOT / "src" / "scinumbers_ask" / "web.py", ROOT / "streamlit_app.py"):
        reached = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute):
                reached.add(node.attr)
            elif isinstance(node, ast.Name):
                reached.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                reached.add(node.value)
        assert not reached & forbidden, (path.name, sorted(reached & forbidden))
