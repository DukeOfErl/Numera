"""Identity is stamped at the sink; the agent is handed a credential and nothing else.

`add-user-identity` puts two things per person into the system: a credential,
which the agent needs to reach the provider, and an account with a role, which
the trail needs and the agent must never see. These tests hold the two apart:

- The credential travels as a constructor parameter, so two agents send two keys
  (asserted on the model's construction, not on the environment).
- The account and role travel through `web.IdentityStamp`, a filter on the
  trail's logger keyed by `session_id`, so records reach the durable store
  stamped while `agent.py`, `trace.py` and `feedback.py` are untouched.
- What the model is handed for the same question is identical under two roles,
  with the positive control that the question itself reached it.

`tests/test_driver_independence.py` asserts the same thing over the source; this
file asserts it over behaviour.
"""

from __future__ import annotations

import logging

import pytest
from conftest import agent_with

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import feedback, trace, web
from scinumbers_ask.agent import AskAgent
from scinumbers_ask.feedback import Verdict
from scinumbers_ask.permissions import Identity, Role
from scinumbers_ask.trail_store import TrailHandler, TrailStore

# --- a destination that keeps what was written ----------------------------------


class _Conn:
    def __init__(self, sink: list[dict]):
        self.sink = sink

    def execute(self, statement, params=None):
        if params is not None and "insert" in str(statement).lower():
            self.sink.append(dict(params))


class _Engine:
    def __init__(self):
        self.written: list[dict] = []

    def begin(self):
        conn = _Conn(self.written)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


@pytest.fixture
def destination():
    """The trail's logger with a fresh file sink, the stamp, and a capturing store.

    Attached in the order `web.resources` attaches them, and torn down entirely:
    the registry and the logger are process-wide, and a stamp left behind would
    make an unrelated test's records carry an identity.
    """
    logger = logging.getLogger(trace.LOGGER_NAME)
    trace.configure()
    web.install_identity_stamp()
    engine = _Engine()
    store = TrailStore(engine=engine)
    store.ready = True
    handler = TrailHandler(store)
    logger.addHandler(handler)
    yield engine
    logger.removeHandler(handler)
    for f in [f for f in logger.filters if isinstance(f, web.IdentityStamp)]:
        logger.removeFilter(f)
    web.IDENTITIES.clear()


def _rows(engine: _Engine, session_id: str) -> list[dict]:
    return [r for r in engine.written if r["session_id"] == session_id]


# --- the credential --------------------------------------------------------------


class _Constructed:
    """Stands in for `ChatOpenAI`; records how it was built, answers as scripted."""

    keys: list[str] = []

    def __new__(cls, **kwargs):
        cls.keys.append(kwargs.get("api_key"))
        return scripted(says("built"))


@pytest.fixture
def constructed(monkeypatch):
    import langchain_openai

    _Constructed.keys = []
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _Constructed)
    return _Constructed


def test_two_agents_with_two_keys_send_two_keys(repo, config, tmp_path, constructed, monkeypatch):
    """On the model's construction, not on the environment: the environment is
    one value per process, which is exactly what a per-person key cannot be."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key-must-not-be-used")
    one = AskAgent(repo, config, str(tmp_path / "one.sqlite"), api_key="key-for-one")
    two = AskAgent(repo, config, str(tmp_path / "two.sqlite"), api_key="key-for-two")
    list(one.ask("s1", "how many?"))
    list(two.ask("s2", "how many?"))
    assert constructed.keys == ["key-for-one", "key-for-two"]


def test_no_key_reads_the_environment_exactly_as_before(
    repo, config, tmp_path, constructed, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-the-environment")
    agent = AskAgent(repo, config, str(tmp_path / "env.sqlite"))
    list(agent.ask("s1", "how many?"))
    assert constructed.keys == ["from-the-environment"]


def test_no_key_anywhere_is_still_the_not_configured_ending(repo, config, tmp_path, monkeypatch):
    """The parameter must not have turned "unset" into a crash."""
    from scinumbers_ask.events import EndReason, QuestionEnded

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = AskAgent(repo, config, str(tmp_path / "none.sqlite"))
    events = list(agent.ask("s1", "how many?"))
    (ended,) = [e for e in events if isinstance(e, QuestionEnded)]
    assert ended.reason is EndReason.NOT_CONFIGURED


def test_the_agent_holds_the_key_and_nothing_else_about_the_person(repo, config, tmp_path):
    """No attribute of the agent names the account or the role, however spelled."""
    agent = AskAgent(repo, config, str(tmp_path / "a.sqlite"), api_key="k")
    held = {name.lower().lstrip("_") for name in vars(agent)}
    assert not held & {"identity", "role", "email", "account", "user", "user_role", "user_email"}


# --- the stamp, through the trail -------------------------------------------------


def test_two_sessions_under_two_identities_each_carry_their_own(
    repo, config, tmp_path, destination
):
    """Through the durable handler, not the events: the column is what the
    weighting queries read. Two identities, so a constant stamp or a shared one
    cannot pass -- and the question text differs too, so the rows cannot be
    told apart by anything but the session."""
    web.remember_identity("s-student", Identity("student@example.org", Role.STUDENT))
    web.remember_identity("s-dev", Identity("dev@example.org", Role.DEV))
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")))
    list(agent.ask("s-student", "first?"))
    list(agent.ask("s-dev", "second?"))

    student_rows, dev_rows = _rows(destination, "s-student"), _rows(destination, "s-dev")
    assert student_rows and dev_rows, "the run recorded nothing"
    assert {(r["user_email"], r["user_role"]) for r in student_rows} == {
        ("student@example.org", "student")
    }
    assert {(r["user_email"], r["user_role"]) for r in dev_rows} == {("dev@example.org", "dev")}


def test_a_session_nobody_is_signed_in_to_writes_null_for_both(repo, config, tmp_path, destination):
    """The CLI, the harness and an unconfigured deployment: no registry entry, so
    the stamp adds nothing and the handler writes NULL -- not `''`."""
    agent = agent_with(repo, config, tmp_path, scripted(says("a")))
    list(agent.ask("s-nobody", "anyone?"))
    rows = _rows(destination, "s-nobody")
    assert rows
    assert {(r["user_email"], r["user_role"]) for r in rows} == {(None, None)}


def test_the_role_is_written_as_it_was_at_record_time(repo, config, tmp_path, destination):
    """ADR-0810. A later change of role does not rewrite the rows already there."""
    web.remember_identity("s1", Identity("p@example.org", Role.SCIENTIST))
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")))
    list(agent.ask("s1", "before?"))
    web.remember_identity("s1", Identity("p@example.org", Role.SENIOR_SCIENTIST))
    list(agent.ask("s1", "after?"))
    roles = [r["user_role"] for r in _rows(destination, "s1")]
    assert "scientist" in roles and "senior scientist" in roles
    before = [r for r in _rows(destination, "s1") if r["event"] == "question.asked"]
    assert [r["user_role"] for r in before] == ["scientist", "senior scientist"]


def test_the_stamp_survives_the_file_sink_being_configured_afterwards(destination):
    """`trace.configure` clears the logger's *handlers*; the stamp is a filter on
    the logger and stays. So the ordering hazard `install_trail` has does not
    apply here -- asserted, rather than left to a comment."""
    web.remember_identity("s1", Identity("p@example.org", Role.DEV))
    trace.configure()  # what `to_file` calls; handlers gone, filters kept
    logger = logging.getLogger(trace.LOGGER_NAME)
    caught: list[logging.LogRecord] = []

    class _Catch(logging.Handler):
        def emit(self, record):
            caught.append(record)

    logger.addHandler(_Catch())
    trace.QuestionTrace(question_id="q", session_id="s1").record("search")
    (record,) = caught
    assert (record.user_email, record.user_role) == ("p@example.org", "dev")


def test_installing_the_stamp_twice_leaves_one():
    logger = logging.getLogger(trace.LOGGER_NAME)
    try:
        web.install_identity_stamp()
        web.install_identity_stamp()
        assert sum(isinstance(f, web.IdentityStamp) for f in logger.filters) == 1
    finally:
        for f in [f for f in logger.filters if isinstance(f, web.IdentityStamp)]:
            logger.removeFilter(f)


# --- feedback, stamped without changing --------------------------------------------


def test_a_verdict_in_a_signed_in_session_carries_the_identity(destination):
    """`feedback.py` did not change. It writes through the same logger, and the
    stamp reaches its records as it reaches the agent's."""
    web.remember_identity("s1", Identity("rater@example.org", Role.SENIOR_SCIENTIST))
    assert feedback.record_verdict({}, question_id="q1", session_id="s1", verdict=Verdict.DOWN)
    (row,) = [r for r in destination.written if r["event"] == "feedback.verdict"]
    assert (row["user_email"], row["user_role"]) == ("rater@example.org", "senior scientist")


def test_a_verdict_with_no_registry_entry_carries_null_for_both(destination):
    assert feedback.record_verdict({}, question_id="q1", session_id="s-none", verdict=Verdict.UP)
    (row,) = [r for r in destination.written if r["event"] == "feedback.verdict"]
    assert (row["user_email"], row["user_role"]) == (None, None)


# --- the spec's scenario: the agent is handed the same question whoever asks ------------


def test_the_same_question_under_two_roles_hands_the_model_identical_inputs(
    repo, config, tmp_path, destination
):
    """Positive control first: the question reached the model at all. Then the
    property: what two models saw for the same question under a student and a
    dev is identical, and neither the account nor the role is anywhere in it."""
    web.remember_identity("s-student", Identity("student@example.org", Role.STUDENT))
    web.remember_identity("s-dev", Identity("dev@example.org", Role.DEV))
    # A tool call in each script, so the comparison covers the tool's inputs and
    # its result as the model saw them, not only the question and the prompt.
    as_student = scripted(tool_call("search_entries", property="Cell"), says("x"))
    as_dev = scripted(tool_call("search_entries", property="Cell"), says("x"))
    question = "how many ribosomes in a cell?"
    list(agent_with(repo, config, tmp_path, as_student, "st.sqlite").ask("s-student", question))
    list(agent_with(repo, config, tmp_path, as_dev, "dv.sqlite").ask("s-dev", question))

    def _seen(model):
        return [
            (type(m).__name__, m.content, getattr(m, "tool_calls", None) or None)
            for m in model.seen
        ]

    seen_by_student, seen_by_dev = _seen(as_student), _seen(as_dev)
    assert any(question in str(content) for _, content, _ in seen_by_student), (
        "control: question absent"
    )
    assert any(name == "ToolMessage" for name, _, _ in seen_by_student), (
        "control: no tool result reached the model"
    )
    assert seen_by_student == seen_by_dev
    everything = " ".join(str(c) for _, c, _ in seen_by_student)
    for token in ("student@example.org", "dev@example.org", "student", "dev@"):
        assert token not in everything
