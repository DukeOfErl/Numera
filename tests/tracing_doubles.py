"""A hosted tracer whose spans stay in memory, and the LangSmith runs a test can count.

The tracer is the real one -- the real Langfuse client, the real LangChain
handler, the real OpenTelemetry context -- with only the last step replaced: an
in-memory span exporter instead of the OTLP one. So what reaches the exporter is
what would have left the host. Nothing here talks to a network: the base URL is
a port nothing listens on, which the score queue fails against quietly.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from langfuse._client.attributes import LangfuseOtelSpanAttributes as A
from langfuse._client.resource_manager import LangfuseResourceManager
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from scinumbers_ask import hosted_trace
from scinumbers_ask.hosted_trace import HostedTracer, Setting

UNREACHABLE = "http://127.0.0.1:9"

USER_ID = A.TRACE_USER_ID
SESSION_ID = A.TRACE_SESSION_ID
TRACE_NAME = A.TRACE_NAME


def on_setting() -> Setting:
    return Setting(on=True, public_key="pk-lf-test", secret_key="sk-lf-test", base_url=UNREACHABLE)


@contextmanager
def recording_tracer() -> Iterator[tuple[HostedTracer, InMemorySpanExporter]]:
    """Install a tracer that is on and keeps its spans; tear the client down after.

    Langfuse keeps one resource manager per public key for the life of the
    process, and a second test would otherwise inherit the first one's exporter.
    """
    exporter = InMemorySpanExporter()
    tracer = HostedTracer(on_setting(), span_exporter=exporter)
    hosted_trace.use(tracer)
    try:
        yield tracer, exporter
    finally:
        hosted_trace.use(None)
        LangfuseResourceManager.reset()


def finished_spans(tracer: HostedTracer, exporter: InMemorySpanExporter) -> list:
    client = tracer._langfuse()
    if client is not None:
        client.flush()
    return list(exporter.get_finished_spans())


def trace_ids(spans: list) -> set[str]:
    return {format(span.context.trace_id, "032x") for span in spans}


@contextmanager
def langsmith_runs() -> Iterator[list[tuple[str, str]]]:
    """Every run a LangSmith tracer starts, with the thread it started on.

    Counted at `_start_trace`, which every LangSmith-traced run goes through
    before anything is queued for upload. The endpoint is set unreachable by the
    caller, so even a run that is counted cannot leave the host.
    """
    from langchain_core.tracers.langchain import LangChainTracer

    started: list[tuple[str, str]] = []
    original = LangChainTracer._start_trace

    def spy(self, run):
        started.append((run.name, threading.current_thread().name))
        return original(self, run)

    LangChainTracer._start_trace = spy
    try:
        yield started
    finally:
        LangChainTracer._start_trace = original
