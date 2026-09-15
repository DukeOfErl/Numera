"""The durable trail through the real script, because the driver is where it breaks.

Two of the properties this change needs cannot be seen below `streamlit_app.py`:

- **Whether the sink survives being installed at all.** `trace.to_file` calls
  `trace.configure`, which *clears* the logger's handlers. Install the sink first
  and it is attached and then silently thrown away -- an app that looks configured
  and records nothing, which is precisely the failure this change exists to end,
  reintroduced two lines further up. No unit test of either function sees it;
  only their order in the script does.

- **Whether a record is written once per question or once per rerun.** Streamlit
  re-runs the whole script on every interaction, so anything installed at the top
  of the page is installed again on every click. The unit test for idempotence
  clears the handler list first and therefore cannot observe the accumulation.

Both are the shape CLAUDE.md records under the banner incident: correct at the
item level, wrong in a whole script run, found by the first real question.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import FIXTURE
from streamlit.testing.v1 import AppTest

from scinumbers_ask import trace, trail_store, web

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
TIMEOUT = 30


class _Conn:
    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        if self.fail is not None:
            raise self.fail
        if params is not None:
            self.params.append(dict(params))
        return None


class _Engine:
    """Enough of an engine to count what reached it."""

    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.conns: list[_Conn] = []

    def begin(self):
        conn = _Conn(self.fail)
        self.conns.append(conn)

        class _Ctx:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()

    @property
    def rows(self) -> list[dict]:
        return [p for c in self.conns for p in c.params if "event" in p]


@pytest.fixture
def clean_logger():
    """The trail's logger is process-global; these tests attach to it."""
    logger = logging.getLogger(trace.LOGGER_NAME)
    before = list(logger.handlers)
    yield logger
    logger.handlers[:] = before


@pytest.fixture
def script(monkeypatch, tmp_path):
    """The real script over the fixture corpus, with `resources` uncached.

    `resources` is `@st.cache_resource`, so without clearing it a second test in
    this process is served the first one's agent -- and, more to the point here,
    the first one's trail installation, which is the thing under test.
    """
    monkeypatch.setenv("SCINUMBERS_CORPUS", FIXTURE)
    monkeypatch.setenv("SCINUMBERS_CHECKPOINTS", str(tmp_path / "c.sqlite"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    web.resources.clear()
    yield AppTest.from_file(APP, default_timeout=TIMEOUT)
    web.resources.clear()


def test_the_sink_survives_the_file_sink_being_configured(monkeypatch, script, clean_logger):
    """The ordering hazard, pinned.

    `to_file` clears the handlers, so this fails if the install moves above it --
    which is a one-line edit that no unit test would notice.
    """
    engine = _Engine()
    monkeypatch.setattr(web, "trail_destination", lambda: engine)

    script.run()

    handlers = [h for h in clean_logger.handlers if isinstance(h, trail_store.TrailHandler)]
    assert handlers, "the durable sink was installed and then cleared"


def test_reruns_do_not_reinstall_because_resources_is_cached(monkeypatch, script, clean_logger):
    """Three script runs, one handler -- and the reason is the cache, not idempotence.

    Named for what it actually pins, after seeding proved the earlier name wrong.
    It was called `test_reruns_do_not_stack_a_handler_per_interaction`, and
    deleting the de-duplication from `install` left it green: `resources` is
    `@st.cache_resource`, so it runs once per container and reruns never reach
    `install` at all.

    So this is a test of the *wiring* -- that installation sits inside the cached
    function rather than at the top of the script. Move it out and this fails.
    Idempotence is a separate property, exercised below and pinned at the unit
    level in `test_trail_store.py`.
    """
    engine = _Engine()
    monkeypatch.setattr(web, "trail_destination", lambda: engine)

    at = script.run()
    at.run()
    at.run()

    handlers = [h for h in clean_logger.handlers if isinstance(h, trail_store.TrailHandler)]
    assert len(handlers) == 1, f"{len(handlers)} handlers after three runs"


def test_a_cache_clear_leaves_one_handler_because_configure_clears_them(
    monkeypatch, script, clean_logger
):
    """One handler after two installs -- and `install`'s de-duplication is not why.

    This began as a driver-level test of idempotence and was found, by seeding,
    to be incapable of failing: deleting the de-duplication from `install` left
    it green. The reason is upstream. `resources` calls `to_file`, which calls
    `configure`, which *clears every handler* -- so the second install starts
    from an empty list and there is nothing to stack, whatever `install` does.

    Kept, renamed, because the property is worth pinning even though the
    mechanism is not the obvious one: two passes through `resources` must leave
    one handler. If `configure` ever stopped clearing, `install`'s own
    de-duplication becomes the thing holding this up -- which is exactly why that
    de-duplication stays, and why it is pinned at the unit level in
    `test_trail_store.py` where a double can isolate it.
    """
    engine = _Engine()
    monkeypatch.setattr(web, "trail_destination", lambda: engine)

    script.run()
    web.resources.clear()
    script.run()

    handlers = [h for h in clean_logger.handlers if isinstance(h, trail_store.TrailHandler)]
    assert len(handlers) == 1, f"{len(handlers)} handlers after a cache clear"


def test_a_record_reaches_the_destination_once_not_once_per_rerun(
    monkeypatch, script, clean_logger
):
    """The property the two above exist to protect, asserted end to end.

    The question cannot be answered -- no key is configured -- and that is fine:
    what is counted is records, and an ending is a record. A question that
    *could* be answered would make this test depend on a model.
    """
    engine = _Engine()
    monkeypatch.setattr(web, "trail_destination", lambda: engine)

    at = script.run()
    at.chat_input[0].set_value("how many ribosomes?").run()
    after_question = len(engine.rows)
    assert after_question, "the question recorded nothing at all"

    at.run()
    at.run()
    assert len(engine.rows) == after_question, "reruns re-recorded the question"


# --- configuration is absence-tolerant, end to end -------------------------


def test_the_app_runs_with_no_destination_configured(monkeypatch, script, clean_logger):
    """The ordinary case on a developer's machine, and it must stay ordinary.

    Refusing to start without a telemetry database would make the absence of
    telemetry an outage -- a worse version of the problem being solved.
    """
    monkeypatch.setattr(web, "trail_destination", lambda: None)

    at = script.run()

    assert not at.exception
    assert not any(isinstance(h, trail_store.TrailHandler) for h in clean_logger.handlers)


def test_the_app_runs_when_the_destination_refuses_every_connection(
    monkeypatch, script, clean_logger
):
    """Configured and broken is an operator's problem, not a reader's.

    No handler is attached, so the per-question path never attempts a write it
    cannot make: the failure is reported once at install rather than once per
    question.
    """
    monkeypatch.setattr(web, "trail_destination", lambda: _Engine(fail=OSError("refused")))

    at = script.run()

    assert not at.exception
    assert not any(isinstance(h, trail_store.TrailHandler) for h in clean_logger.handlers)


def test_a_broken_connection_url_is_reported_rather_than_swallowed(monkeypatch, capsys):
    """Configured-but-wrong must not look like not-configured.

    The likeliest mistake is the first one `secrets.toml.example` warns about:
    pasting the provider's `postgresql://` instead of `postgresql+psycopg://`.
    That raises inside `create_engine` -- before any connection is attempted --
    so it never reaches the store's own reporting. Swallowed here, the operator
    sees nothing at all, and "looks configured, records nothing" is this change's
    own failure reinstated at the one place it is hardest to notice.
    """

    def explode(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'psycopg2'")

    monkeypatch.setattr(web.st, "connection", explode)
    assert web.trail_destination() is None
    err = capsys.readouterr().err
    assert "trail destination unusable" in err
    assert "psycopg2" in err, "the operator needs to know which mistake it was"


def test_no_configuration_at_all_is_silent(monkeypatch, capsys):
    """The ordinary case on a developer's machine says nothing.

    Distinguished by exception type, not by message text: the wording is
    Streamlit's to change, and a rule matching on prose goes quietly false the
    day it does.
    """
    from streamlit.errors import StreamlitSecretNotFoundError

    def missing(*args, **kwargs):
        raise StreamlitSecretNotFoundError("no secrets")

    monkeypatch.setattr(web.st, "connection", missing)
    assert web.trail_destination() is None
    assert capsys.readouterr().err == ""


def test_a_question_is_still_answered_when_every_write_fails(monkeypatch, script, clean_logger):
    """Fail-open, through the whole script rather than through one function.

    The store is forced ready with a failing engine, which is the state a
    destination that dies *after* install would be in -- the case `install`'s own
    guard cannot cover, and the one a reader would actually meet.
    """
    engine = _Engine(fail=OSError("gone"))
    store = trail_store.TrailStore(engine=engine)
    store.ready = True
    monkeypatch.setattr(web, "trail_destination", lambda: None)

    at = script.run()
    # Attached *after* the first run, not before. `resources` calls `to_file`,
    # which calls `configure`, which clears the handlers -- so a handler added
    # beforehand is wiped before the question is ever asked, and this test
    # silently exercised nothing. It failed that way when first written, which is
    # the same hazard `test_the_sink_survives_the_file_sink_being_configured`
    # pins from the other direction.
    clean_logger.addHandler(trail_store.TrailHandler(store))
    at.chat_input[0].set_value("how many ribosomes?").run()

    assert not at.exception, "a failed telemetry write reached the reader"
    assert store.failures, "the test did not exercise a failing write"
