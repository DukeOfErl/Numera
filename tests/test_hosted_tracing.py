"""Hosted tracing: off unless the project says so, one trace per question, and never in the way.

Spec: `hosted-tracing`. Every "nothing is sent" test here is paired with the case
that differs in the one dimension the rule reads and shows that something *is*
sent -- without the pair, a double that never records anything passes every
refusal (`.claude/rules/testing.md`, the negative-case rule).

No test talks to Langfuse or LangSmith. The tracer is the real one with an
in-memory exporter (`tracing_doubles.recording_tracer`), so what these tests
see is what would have left the host.
"""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import agent_with
from tracing_doubles import (
    SESSION_ID,
    TRACE_NAME,
    UNREACHABLE,
    USER_ID,
    finished_spans,
    langsmith_runs,
    on_setting,
    recording_tracer,
    trace_ids,
)

from agent_doubles import says, scripted, tool_call
from scinumbers_ask import feedback, hosted_trace, trace
from scinumbers_ask.feedback import Verdict
from scinumbers_ask.hosted_trace import HostedTracer, Setting, Usage, estimate, read_setting

CREDENTIALS = {
    "LANGFUSE_PUBLIC_KEY": "pk-lf-x",
    "LANGFUSE_SECRET_KEY": "sk-lf-x",
    "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
}


def a_question():
    """A question that searches once and answers, so the trace has children."""
    return scripted(tool_call("search_entries", property="Cell"), says("About 1 [[100001]]."))


def ask(agent, session="s1", question="What is the volume of a cell?"):
    return list(agent.ask(session, question))


def question_id_of(events) -> str:
    return events[0].question_id


# --- the setting: off unless this project's own setting turns it on --------------


@pytest.mark.parametrize("value", [None, "", "off", "OFF", "  off "])
def test_absent_or_off_is_off_and_says_nothing(monkeypatch, value):
    for name, v in CREDENTIALS.items():
        monkeypatch.setenv(name, v)
    if value is not None:
        monkeypatch.setenv(hosted_trace.SETTING, value)
    setting = read_setting()
    assert not setting.on
    assert setting.problem == ""


def test_langfuse_with_every_credential_is_on(monkeypatch):
    """The positive case every off case below differs from in one dimension."""
    monkeypatch.setenv(hosted_trace.SETTING, "langfuse")
    for name, v in CREDENTIALS.items():
        monkeypatch.setenv(name, v)
    setting = read_setting()
    assert setting.on
    assert (setting.public_key, setting.secret_key, setting.base_url) == tuple(CREDENTIALS.values())


@pytest.mark.parametrize("missing", sorted(CREDENTIALS))
def test_a_missing_credential_is_off_and_is_named(monkeypatch, missing):
    monkeypatch.setenv(hosted_trace.SETTING, "langfuse")
    for name, v in CREDENTIALS.items():
        if name != missing:
            monkeypatch.setenv(name, v)
    setting = read_setting()
    assert not setting.on
    assert missing in setting.problem
    assert all(name not in setting.problem for name in CREDENTIALS if name != missing)


def test_the_deprecated_host_name_does_not_stand_in_for_the_base_url(monkeypatch):
    """The region must be written under the name this project reads."""
    monkeypatch.setenv(hosted_trace.SETTING, "langfuse")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    setting = read_setting()
    assert not setting.on
    assert "LANGFUSE_BASE_URL" in setting.problem


@pytest.mark.parametrize("value", ["langsmith", "true", "1", "on", "langfuse-eu"])
def test_an_unrecognised_value_is_off_and_is_named(monkeypatch, value):
    monkeypatch.setenv(hosted_trace.SETTING, value)
    for name, v in CREDENTIALS.items():
        monkeypatch.setenv(name, v)
    setting = read_setting()
    assert not setting.on
    assert repr(value) in setting.problem


def test_credentials_without_the_setting_do_not_turn_it_on(monkeypatch):
    for name, v in CREDENTIALS.items():
        monkeypatch.setenv(name, v)
    assert not read_setting().on


def test_the_operator_is_told_once_not_on_every_question(repo, config, tmp_path, monkeypatch):
    monkeypatch.setenv(hosted_trace.SETTING, "langsmith")
    buf = io.StringIO()
    trace.configure(buf)
    agent = agent_with(repo, config, tmp_path, scripted(says("a"), says("b")))
    ask(agent, question="one?")
    ask(agent, question="two?")
    reports = [r for r in _records(buf) if r["event"] == "tracing.off"]
    assert len(reports) == 1
    assert "'langsmith'" in reports[0]["detail"]


def test_a_misconfigured_setting_still_answers(repo, config, tmp_path, monkeypatch):
    monkeypatch.setenv(hosted_trace.SETTING, "langfuse")  # and no credentials
    agent = agent_with(repo, config, tmp_path, a_question())
    events = ask(agent)
    assert any(type(e).__name__ == "Answer" and "[[100001]]" in e.text for e in events)


_IMPORT_PROBE = """
import os, sys, tempfile, pathlib
sys.path[:0] = [{tests!r}, {src!r}]
from agent_doubles import says, scripted
from scinumbers_ask.agent import AskAgent
from scinumbers_ask.config import Config, usd
from scinumbers_ask.corpus import load
from scinumbers_ask.repository import CorpusRepository
from conftest import FIXTURE
agent = AskAgent(CorpusRepository(load(FIXTURE)),
                 Config(model="fake/model", question_ceiling=usd("0.60"), run_budget=usd("1.20")),
                 str(pathlib.Path(tempfile.mkdtemp()) / "c.sqlite"), model=scripted(says("a")))
list(agent.ask("s", "q?"))
print("langfuse" in sys.modules)
"""


@pytest.mark.parametrize("setting, imported", [(None, "False"), ("langfuse", "True")])
def test_langfuse_is_not_imported_unless_tracing_is_on(tmp_path, setting, imported):
    """In a fresh interpreter, so nothing another test imported can answer for it.

    The pair is the point: the same probe with the setting on shows the probe
    can see an import at all.
    """
    tests = str(Path(__file__).parent)
    src = str(Path(__file__).parents[1] / "src")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    if setting:
        env |= {hosted_trace.SETTING: setting, **CREDENTIALS, "LANGFUSE_BASE_URL": UNREACHABLE}
    out = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE.format(tests=tests, src=src)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == imported


# --- a vendor's own switch sends nothing -----------------------------------------


@pytest.fixture
def vendor_switch(monkeypatch):
    """LangSmith switched on in the environment, pointed where nothing listens.

    `langsmith.utils.get_env_var` is `lru_cache`d, so a switch set after any
    runnable has run in this process is not seen at all -- and every "nothing was
    sent" test below would pass because LangSmith never read the switch, not
    because anything refused it. Found by the control test failing whenever an
    unrelated test had invoked a tool first. Cleared on the way in and out.
    """
    from langsmith.utils import get_env_var

    def set_(name):
        monkeypatch.setenv(name, "true")
        monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test")
        monkeypatch.setenv("LANGSMITH_ENDPOINT", UNREACHABLE)
        monkeypatch.setenv("LANGCHAIN_ENDPOINT", UNREACHABLE)
        get_env_var.cache_clear()

    yield set_
    monkeypatch.undo()
    get_env_var.cache_clear()


@pytest.mark.parametrize("switch", hosted_trace.VENDOR_SWITCHES)
def test_the_vendor_switch_sends_nothing_with_tracing_off(
    repo, config, tmp_path, vendor_switch, switch
):
    vendor_switch(switch)
    agent = agent_with(repo, config, tmp_path, a_question())
    with langsmith_runs() as started:
        ask(agent)
    assert started == []


@pytest.mark.parametrize("switch", hosted_trace.VENDOR_SWITCHES)
def test_the_vendor_switch_sends_nothing_beside_the_chosen_tracer(
    repo, config, tmp_path, vendor_switch, switch
):
    """And the chosen tracer still traces: refusing one must not silence the other."""
    vendor_switch(switch)
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter), langsmith_runs() as started:
        ask(agent)
        spans = finished_spans(tracer, exporter)
    assert started == []
    assert spans


@pytest.mark.parametrize("switch", hosted_trace.VENDOR_SWITCHES)
def test_control_without_the_refusal_the_same_harness_sees_langsmith(
    repo, config, tmp_path, vendor_switch, switch, monkeypatch
):
    """The control that makes the two tests above mean something.

    With the refusal replaced by a no-op, the same switch and the same question
    start LangSmith runs -- including on LangGraph's worker threads, which is
    where a refusal set only on the calling thread would leak.
    """
    from contextlib import nullcontext

    vendor_switch(switch)
    monkeypatch.setattr(hosted_trace, "vendor_tracing_refused", nullcontext)
    agent = agent_with(repo, config, tmp_path, a_question())
    with langsmith_runs() as started:
        ask(agent)
    assert started
    assert any(thread != "MainThread" for _, thread in started)


def test_the_vendor_switch_is_reported_to_the_operator(repo, config, tmp_path, vendor_switch):
    vendor_switch("LANGSMITH_TRACING")
    buf = io.StringIO()
    trace.configure(buf)
    ask(agent_with(repo, config, tmp_path, a_question()))
    reports = [r for r in _records(buf) if r["event"] == "tracing.vendor_switch_refused"]
    assert [r["variable"] for r in reports] == ["LANGSMITH_TRACING"]


def test_the_refusal_holds_while_the_generator_is_consumed_one_event_at_a_time(
    repo, config, tmp_path, vendor_switch
):
    """The way a driver consumes it: an event, other work, the next event."""
    vendor_switch("LANGSMITH_TRACING")
    agent = agent_with(repo, config, tmp_path, a_question())
    with langsmith_runs() as started:
        for _ in agent.ask("s1", "What is the volume of a cell?"):
            sum(i * i for i in range(5000))
    assert started == []


# --- one question, one trace, found by its identifier -----------------------------


def test_a_question_is_one_trace_whose_id_is_derived_from_the_question(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        events = ask(agent, session="session-7")
        spans = finished_spans(tracer, exporter)
    qid = question_id_of(events)
    assert trace_ids(spans) == {hosted_trace.trace_id_for(qid)}
    assert len(spans) > 1  # the model call and the tool call are in it, not only a root
    metadata = " ".join(str(dict(s.attributes)) for s in spans)
    assert qid in metadata
    assert all(s.attributes.get(SESSION_ID) == "session-7" for s in spans)
    assert "run:dev" in metadata


def test_the_trace_is_named_for_the_operation_not_the_question(repo, config, tmp_path):
    """A name unique per question cannot be filtered on; the id is in the metadata."""
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        ask(agent)
        spans = finished_spans(tracer, exporter)
    assert {s.attributes.get(TRACE_NAME) for s in spans} == {hosted_trace.TRACE_NAME}


def test_two_questions_are_two_traces_in_one_session(repo, config, tmp_path):
    model = scripted(says("a [[100001]]."), says("b [[100001]]."))
    agent = agent_with(repo, config, tmp_path, model)
    with recording_tracer() as (tracer, exporter):
        first = ask(agent, session="s-shared", question="one?")
        second = ask(agent, session="s-shared", question="two?")
        spans = finished_spans(tracer, exporter)
    expected = {hosted_trace.trace_id_for(question_id_of(e)) for e in (first, second)}
    assert len(expected) == 2
    assert trace_ids(spans) == expected
    assert {s.attributes.get(SESSION_ID) for s in spans} == {"s-shared"}


def test_the_trace_id_depends_on_the_question_not_the_session():
    assert hosted_trace.trace_id_for("q1") == hosted_trace.trace_id_for("q1")
    assert hosted_trace.trace_id_for("q1") != hosted_trace.trace_id_for("q2")


def test_tracing_off_sends_nothing_and_leaves_the_config_alone(repo, config, tmp_path):
    tracer = HostedTracer(Setting(on=False))
    base = {"metadata": {"a": 1}, "tags": ["t"]}
    assert tracer.traced(base, trace.start_question()) is base
    assert tracer._client is None


# --- who asked: an opaque value from the driver, and the agent is not told -------


def test_an_attributed_question_carries_the_value_on_every_span(repo, config, tmp_path):
    """Through the real propagation path, consumed the way a driver consumes it.

    Every span, not the root: LangGraph runs the model and the tool on worker
    threads, and an attribute that stayed on the calling thread would reach the
    root and nothing the cost is attached to.
    """
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        with tracer.attributed("acct-digest-1"):
            for _ in agent.ask("s1", "What is the volume of a cell?"):
                sum(i * i for i in range(5000))
        spans = finished_spans(tracer, exporter)
    assert spans
    assert {s.attributes.get(USER_ID) for s in spans} == {"acct-digest-1"}


def test_two_readers_carry_two_values(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, scripted(says("a [[100001]]."), says("b.")))
    with recording_tracer() as (tracer, exporter):
        with tracer.attributed("acct-a"):
            first = ask(agent, session="s-a")
        with tracer.attributed("acct-b"):
            second = ask(agent, session="s-b")
        spans = finished_spans(tracer, exporter)
    by_trace = {}
    for s in spans:
        by_trace.setdefault(format(s.context.trace_id, "032x"), set()).add(
            s.attributes.get(USER_ID)
        )
    assert by_trace[hosted_trace.trace_id_for(question_id_of(first))] == {"acct-a"}
    assert by_trace[hosted_trace.trace_id_for(question_id_of(second))] == {"acct-b"}


def test_nobody_signed_in_attaches_nothing(repo, config, tmp_path):
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        with tracer.attributed(None):
            ask(agent)
        spans = finished_spans(tracer, exporter)
    assert spans
    assert all(USER_ID not in s.attributes for s in spans)


def test_abandoning_an_attributed_question_mid_stream_is_harmless(repo, config, tmp_path):
    """What a Streamlit rerun does: stop consuming, and let the generator go."""
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        with tracer.attributed("acct-x"):
            events = agent.ask("s1", "What is the volume of a cell?")
            next(events)
            next(events)
            events.close()
        with tracer.attributed("acct-y"):
            later = ask(agent_with(repo, config, tmp_path, a_question(), name="b.sqlite"))
        spans = finished_spans(tracer, exporter)
    later_trace = hosted_trace.trace_id_for(question_id_of(later))
    assert {
        s.attributes.get(USER_ID)
        for s in spans
        if format(s.context.trace_id, "032x") == later_trace
    } == {"acct-y"}


def test_what_the_agent_is_given_does_not_depend_on_tracing_or_the_reader(repo, config, tmp_path):
    """Four runs: two readers, tracing on and off. The model is shown the same thing."""
    seen = []
    for traced in (False, True):
        for reader in ("acct-a", "acct-b"):
            model = a_question()
            model.seen = []
            agent = agent_with(repo, config, tmp_path, model, name=f"{traced}-{reader}.sqlite")
            if traced:
                with recording_tracer() as (tracer, _), tracer.attributed(reader):
                    ask(agent, session=f"s-{reader}")
            else:
                ask(agent, session=f"s-{reader}")
            seen.append([(type(m).__name__, m.content) for m in model.seen])
    assert seen[0]  # the question reached it at all
    assert all(s == seen[0] for s in seen)


# --- a rating is copied to its trace; the trail stays the record ------------------


class ScoreClient:
    """Stands in for the Langfuse client's score call; can be made to fail."""

    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.scores: list[dict] = []

    def create_score(self, **kwargs):
        if self.fail:
            raise self.fail
        self.scores.append(kwargs)


def tracer_with(client: ScoreClient) -> HostedTracer:
    tracer = HostedTracer(on_setting())
    tracer._client = client
    hosted_trace.use(tracer)
    return tracer


def _records(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


@pytest.mark.parametrize("verdict, value", [(Verdict.UP, 1), (Verdict.DOWN, 0)])
def test_a_verdict_reaches_its_question_trace_after_the_trail(verdict, value):
    buf = io.StringIO()
    trace.configure(buf)
    client = ScoreClient()
    tracer_with(client)
    feedback.record_verdict({}, question_id="q-1", session_id="s", verdict=verdict)
    assert [r["event"] for r in _records(buf)] == [feedback.VERDICT_EVENT]
    (score,) = client.scores
    assert score["trace_id"] == hosted_trace.trace_id_for("q-1")
    assert (score["name"], score["value"], score["data_type"]) == (
        hosted_trace.VERDICT_SCORE,
        value,
        "BOOLEAN",
    )


def test_a_changed_verdict_overwrites_rather_than_adds():
    client = ScoreClient()
    tracer_with(client)
    feedback.record_verdict({}, question_id="q-1", session_id="s", verdict=Verdict.UP)
    feedback.record_verdict({}, question_id="q-1", session_id="s", verdict=Verdict.DOWN)
    assert len({s["score_id"] for s in client.scores}) == 1


def test_a_comment_reaches_the_same_trace():
    client = ScoreClient()
    tracer_with(client)
    state = {}
    feedback.record_verdict(state, question_id="q-2", session_id="s", verdict=Verdict.DOWN)
    feedback.record_comment(state, question_id="q-2", session_id="s", text=" entry 100001 is off ")
    verdict, comment = client.scores
    assert comment["trace_id"] == verdict["trace_id"] == hosted_trace.trace_id_for("q-2")
    assert comment["name"] == hosted_trace.COMMENT_SCORE
    assert comment["comment"] == "entry 100001 is off"
    assert comment["score_id"] != verdict["score_id"]


def test_tracing_off_touches_no_client():
    """The pair of the tests above: the same calls, with tracing off, construct nothing."""
    tracer = HostedTracer(Setting(on=False))
    hosted_trace.use(tracer)
    feedback.record_verdict({}, question_id="q-3", session_id="s", verdict=Verdict.UP)
    assert tracer._client is None


def test_a_failed_copy_leaves_the_trail_exactly_as_it_would_be():
    def trail_for(client):
        buf = io.StringIO()
        trace.configure(buf)
        tracer_with(client)
        state = {}
        feedback.record_verdict(state, question_id="q-4", session_id="s", verdict=Verdict.DOWN)
        feedback.record_comment(state, question_id="q-4", session_id="s", text="wrong")
        return [r for r in _records(buf) if not r["event"].startswith("tracing.")], _records(buf)

    working, _ = trail_for(ScoreClient())
    failing, everything = trail_for(ScoreClient(fail=RuntimeError("429 usage limit")))
    assert failing == working
    assert [r["stage"] for r in everything if r["event"] == "tracing.failed"] == [
        "score",
        "score",
    ]


# --- a tracer fault never reaches a reader ----------------------------------------


def _shape(events) -> list[str]:
    """Events with the per-run question id taken out, so two runs compare whole."""
    qid = question_id_of(events)
    return [repr(e).replace(qid, "Q") for e in events]


def _trail_shape(buf: io.StringIO) -> list[dict]:
    rows = []
    for r in _records(buf):
        r.pop("question_id", None)
        rows.append(r)
    return rows


def _run(repo, config, tmp_path, name):
    buf = io.StringIO()
    trace.configure(buf)
    events = ask(agent_with(repo, config, tmp_path, a_question(), name=name))
    return _shape(events), _trail_shape(buf)


def test_a_raising_handler_changes_nothing_a_reader_sees(
    repo, config, tmp_path, monkeypatch, caplog
):
    from langfuse.langchain import CallbackHandler

    untraced = _run(repo, config, tmp_path, "off.sqlite")

    def explode(self, *args, **kwargs):
        raise RuntimeError("tracer exploded")

    for hook in ("on_chat_model_start", "on_llm_start", "on_chain_start", "on_tool_start"):
        monkeypatch.setattr(CallbackHandler, hook, explode)
    with recording_tracer(), caplog.at_level(logging.WARNING):
        traced = _run(repo, config, tmp_path, "on.sqlite")
    assert traced == untraced
    assert "tracer exploded" in caplog.text  # the operator can see it failed


def test_an_export_that_fails_changes_nothing_a_reader_sees(repo, config, tmp_path):
    from opentelemetry.sdk.trace.export import SpanExportResult

    class FailingExporter:
        def export(self, spans):
            return SpanExportResult.FAILURE

        def shutdown(self):
            pass

        def force_flush(self, timeout_millis=None):
            return True

    untraced = _run(repo, config, tmp_path, "off.sqlite")
    tracer = HostedTracer(on_setting(), span_exporter=FailingExporter())
    hosted_trace.use(tracer)
    try:
        traced = _run(repo, config, tmp_path, "on.sqlite")
        tracer._langfuse().flush()
    finally:
        from langfuse._client.resource_manager import LangfuseResourceManager

        LangfuseResourceManager.reset()
    assert traced == untraced


def test_a_client_that_cannot_be_built_is_tracing_off_and_the_question_is_answered(
    repo, config, tmp_path, monkeypatch
):
    import langfuse

    def refuse(*args, **kwargs):
        raise RuntimeError("cannot build")

    monkeypatch.setattr(langfuse, "Langfuse", refuse)
    buf = io.StringIO()
    trace.configure(buf)
    hosted_trace.use(HostedTracer(on_setting()))
    events = ask(agent_with(repo, config, tmp_path, a_question()))
    assert any(type(e).__name__ == "Answer" and "[[100001]]" in e.text for e in events)
    assert [r["event"] for r in _records(buf) if r["event"].startswith("tracing.")] == [
        "tracing.unavailable"
    ]


# --- the allowance: counted, and unknown is never zero ------------------------------
#
# Mutation testing (2026-09-25, 405 mutants over hosted_trace.py) left these alive on
# purpose. An empty metrics response counting 1 rather than 0 over-counts, which is
# the safe direction. The wording and fields of the operator's `tracing.*` reports
# are unasserted, like the rest of the trail's content. A client that failed to
# build being retried per question rather than once is still reported once, and no
# requirement says how often to retry.


class MetricsClient:
    """Answers the v2 metrics queries from a table; a view can be made to fail.

    Shaped like the SDK's own nesting, `client.api.metrics.metrics(query=...)`.
    """

    def __init__(self, counts: dict[str, int], fail: set[str] = frozenset()):
        self.counts, self.fail, self.queries = counts, fail, []
        endpoint = SimpleNamespace(metrics=self._answer)
        self.api = SimpleNamespace(metrics=endpoint)

    def _answer(self, *, query):
        q = json.loads(query)
        key = q["view"] + (":root" if q["filters"] else "")
        self.queries.append(q)
        if key in self.fail:
            raise RuntimeError(f"{key} failed")
        return SimpleNamespace(data=[{"count_count": self.counts.get(key, 0)}])


def usage_from(counts, fail=frozenset()):
    tracer = HostedTracer(on_setting())
    tracer._client = MetricsClient(counts, set(fail))
    return tracer.monthly_usage(now=datetime(2026, 9, 24, tzinfo=UTC)), tracer._client


COUNTS = {
    "observations:root": 100,
    "observations": 2_000,
    "scores-numeric": 40,
    "scores-categorical": 10,
    "scores-boolean": 40,
}


def test_usage_is_traces_plus_observations_plus_scores_over_31_days():
    usage, client = usage_from(COUNTS)
    assert usage.units == 100 + 2_000 + 40 + 10 + 40
    assert usage.traces == 100
    assert (usage.until - usage.since).days == 31
    assert {q["fromTimestamp"] for q in client.queries} == {"2026-08-24T00:00:00Z"}


@pytest.mark.parametrize("view", sorted(COUNTS))
def test_one_view_failing_makes_usage_unknown_never_a_partial_sum(view):
    usage, _ = usage_from(COUNTS, fail={view})
    assert usage.units is None
    assert usage.share is None
    assert usage.per_question is None


def test_usage_is_not_counted_when_tracing_is_off():
    tracer = HostedTracer(Setting(on=False))
    assert tracer.monthly_usage() is None
    assert tracer._client is None


def _usage(units, traces=100):
    now = datetime(2026, 9, 24, tzinfo=UTC)
    return Usage(units=units, traces=traces, since=now, until=now)


def test_under_half_and_fitting_proceeds():
    e = estimate(_usage(24_500), questions=10)  # 49%, 245 units a question
    assert not e.needs_approval
    assert e.units == pytest.approx(2_450)


def test_more_than_half_pauses():
    assert estimate(_usage(25_500), questions=1).needs_approval


def test_exactly_half_does_not_pause():
    """The spec says "more than half"; the boundary is where a `>=` would hide."""
    assert not estimate(_usage(25_000, traces=25_000), questions=1).needs_approval


def test_a_run_that_would_not_fit_pauses_even_under_half():
    e = estimate(_usage(5_000, traces=10), questions=10_000)  # 500 a question
    assert e.needs_approval
    assert "exceed" in " ".join(e.reasons)


def test_a_run_that_fits_exactly_does_not_pause():
    e = estimate(_usage(5_000, traces=10), questions=90)  # 45,000 of 45,000 remaining
    assert not e.needs_approval


def test_unknown_usage_pauses():
    assert estimate(_usage(None, traces=None), questions=1).needs_approval


def test_no_traces_yet_makes_the_cost_unknown_and_pauses():
    """The first run of a month asks once; the control is the same usage with traces."""
    assert estimate(_usage(0, traces=0), questions=5).needs_approval
    assert not estimate(_usage(100, traces=1), questions=5).needs_approval


# --- the page attaches who asked, and only the digest -------------------------------


def test_the_page_attaches_the_account_digest_and_never_the_address(repo, config, tmp_path):
    from scinumbers_ask import web
    from scinumbers_ask.accounts import Account
    from scinumbers_ask.permissions import Role

    account = Account(email="tester@example.org", role=Role.SCIENTIST, openrouter_key="sk-t")
    admission = web.Admission(web.Door.OPEN, configured=True, account=account)
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        with web.attributed(admission):
            ask(agent)
        spans = finished_spans(tracer, exporter)
    assert {s.attributes.get(USER_ID) for s in spans} == {web.account_scope(admission)}
    everything = " ".join(str(dict(s.attributes)) for s in spans)
    assert "tester@example.org" not in everything
    assert str(account.role) not in everything


def test_an_unconfigured_page_attaches_nothing(repo, config, tmp_path):
    from scinumbers_ask import web

    admission = web.Admission(web.Door.OPEN, configured=False)
    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        with web.attributed(admission):
            ask(agent)
        spans = finished_spans(tracer, exporter)
    assert spans
    assert [s.attributes.get(USER_ID) for s in spans if USER_ID in s.attributes] == []


def test_the_page_consumes_the_answer_inside_the_attribution():
    """Structural, because the page runs only under Streamlit: the one call that
    consumes `agent.ask` must sit inside `with web.attributed(...)`. Moved outside
    it, every trace from the deployed app arrives unattributed and nothing fails."""
    import ast

    source = (Path(__file__).parents[1] / "streamlit_app.py").read_text()
    tree = ast.parse(source)
    consuming = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "answer"
        and any(isinstance(a, ast.Call) and getattr(a.func, "attr", "") == "ask" for a in node.args)
    ]
    assert len(consuming) == 1
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    node, inside = consuming[0], False
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.With) and any(
            isinstance(i.context_expr, ast.Call)
            and getattr(i.context_expr.func, "attr", "") == "attributed"
            for i in node.items
        ):
            inside = True
            break
    assert inside


def test_an_abandoned_question_cannot_attribute_a_later_one_to_its_reader(repo, config, tmp_path):
    """Found by an order-dependent failure, and reproduced here on its own.

    The Langfuse handler enters its own attribute propagation at the root run and
    leaves it only when the run ends. A question abandoned mid-stream -- every
    Streamlit rerun -- never ends its run, and when the garbage collector later
    finalises that propagation it restores the context it saw, *including the
    abandoned question's reader*, onto whatever the thread does next. The next
    question on that thread was then attributed to the previous reader: a wrong
    trace that looks like an ordinary one.
    """
    import gc

    from opentelemetry import context as otel

    with recording_tracer() as (tracer, exporter):
        with tracer.attributed("acct-abandoned"):
            events = agent_with(repo, config, tmp_path, a_question()).ask("s1", "q?")
            next(events)
            next(events)
            events.close()
        del events
        gc.collect()
        leaked = {k: v for k, v in otel.get_current().items() if "user_id" in k}
        later = ask(agent_with(repo, config, tmp_path, a_question(), name="later.sqlite"))
        spans = finished_spans(tracer, exporter)
    assert leaked == {}
    later_trace = hosted_trace.trace_id_for(question_id_of(later))
    assert {
        s.attributes.get(USER_ID)
        for s in spans
        if format(s.context.trace_id, "032x") == later_trace
    } == {None}


# --- an evaluation run is marked, whatever the run label says -----------------------


def test_a_tagged_question_carries_the_tag_beside_its_own(repo, config, tmp_path):
    """Merged, not replacing: the run label and the application tag are still there."""
    from tracing_doubles import TRACE_TAGS

    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        with tracer.tagged("eval"):
            ask(agent)
        spans = finished_spans(tracer, exporter)
    tag_sets = {tuple(sorted(s.attributes.get(TRACE_TAGS, ()))) for s in spans}
    assert tag_sets == {tuple(sorted(("eval", "ask", "scinumbers-ask", "run:dev")))}


def test_an_untagged_question_is_not_marked(repo, config, tmp_path):
    """The pair: the same question outside the block carries no `eval`."""
    from tracing_doubles import TRACE_TAGS

    agent = agent_with(repo, config, tmp_path, a_question())
    with recording_tracer() as (tracer, exporter):
        ask(agent)
        spans = finished_spans(tracer, exporter)
    assert spans
    assert all("eval" not in s.attributes.get(TRACE_TAGS, ()) for s in spans)


def test_tagging_with_tracing_off_builds_nothing():
    tracer = HostedTracer(Setting(on=False))
    with tracer.tagged("eval"):
        pass
    assert tracer._client is None


def test_each_count_asks_the_metrics_api_in_its_documented_shape():
    """The request, not the arithmetic: a misspelt key is invisible to every stub
    that answers regardless, and would only show against the live API.

    The expected shape is Langfuse's own v2 example (metrics-api.md, read
    2026-09-24): a `view`, `metrics` as `[{"measure": ..., "aggregation": ...}]`,
    `dimensions`, `filters`, and both timestamps as ISO 8601 in UTC. Traces are the
    `observations` view filtered to root observations, because v2 has no traces
    view. Confirmed live on 2026-09-25, when this query counted 37 units.
    """
    _, client = usage_from(COUNTS)
    assert {q["view"] for q in client.queries} == {
        "observations",
        "scores-numeric",
        "scores-categorical",
        "scores-boolean",
    }
    for q in client.queries:
        assert set(q) == {
            "view",
            "metrics",
            "dimensions",
            "filters",
            "fromTimestamp",
            "toTimestamp",
        }
        assert q["metrics"] == [{"measure": "count", "aggregation": "count"}]
        assert q["dimensions"] == []
        assert (q["fromTimestamp"], q["toTimestamp"]) == (
            "2026-08-24T00:00:00Z",
            "2026-09-24T00:00:00Z",
        )
    roots = [q for q in client.queries if q["filters"]]
    assert [q["filters"] for q in roots] == [
        [{"column": "isRootObservation", "operator": "=", "value": True, "type": "boolean"}]
    ]


def test_usage_is_counted_up_to_now_in_utc_when_no_time_is_given():
    """The Metrics API takes ISO 8601 in UTC. Every test above passes `now`; this is
    the call the command makes, and a naive local time would be read as UTC and
    shift the window by the host's offset."""
    tracer = HostedTracer(on_setting())
    tracer._client = MetricsClient(COUNTS)
    before = datetime.now(UTC)
    usage = tracer.monthly_usage()
    assert usage.until.tzinfo is not None
    assert before <= usage.until <= datetime.now(UTC)
    assert all(q["toTimestamp"].endswith("Z") for q in tracer._client.queries)


def test_the_client_is_built_from_the_setting_and_never_touches_the_global_provider(
    monkeypatch,
):
    """ADR-1010: the region is the one written in the configuration, never an SDK
    default; and the client gets a provider of its own, so the process's global
    OpenTelemetry provider is not replaced."""
    import langfuse
    from opentelemetry import trace as otel_trace

    built = []
    monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: built.append(kwargs) or object())
    setting = Setting(
        on=True, public_key="pk-a", secret_key="sk-b", base_url="https://region.example"
    )
    HostedTracer(setting)._langfuse()
    (kwargs,) = built
    assert (kwargs["public_key"], kwargs["secret_key"], kwargs["base_url"]) == (
        "pk-a",
        "sk-b",
        "https://region.example",
    )
    assert kwargs["tracer_provider"] is not None
    assert kwargs["tracer_provider"] is not otel_trace.get_tracer_provider()
