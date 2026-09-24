## Why

The trail says what the deterministic layer did — what was searched, what an alias resolved to, what
was spent — and deliberately says nothing about the model calls (`trace.py`: "Tracing tools cover
those"). No tracing tool is connected, so when a tester rates an answer down, nobody can see the
sequence of model turns and tool calls that produced it. That is roadmap WP4's second half, and both
of its dependencies (the durable trail, WP1; identity, WP3) have merged.

There is also a standing hazard this change closes. `langsmith` is installed as a transitive
dependency of `langchain-core`, and setting `LANGSMITH_TRACING` — by anyone, in any shell or secrets
box — ships full prompts, tool results and corpus text to a third party today. The roadmap's
condition was that hosted tracing be a decision, not an environment variable nobody chose.

## What Changes

- **Hosted tracing to Langfuse Cloud (EU region, Hobby tier)**, chosen over LangSmith on 2026-09-24:
  30-day access rather than 14, two seats rather than one, EU as the default host, and a tracer that
  only runs when a handler is passed to the call. The comparison and what was verified are in
  `design.md` and the ADR.
- **Off unless a project setting turns it on.** One setting named by this project enables it; the
  vendor's own credentials being present does not. Absent, unknown, or enabled without credentials,
  the application runs exactly as it does now and ships nothing.
- **LangSmith tracing is refused inside the operation.** `LANGSMITH_TRACING` (and its legacy name)
  no longer causes anything to be sent, whichever driver asks the question.
- **Each question is one trace, found by the question's own identifier.** The trace's id is derived
  from `question_id`, so the trail row, the rating and the trace name one another without a lookup
  table. The session and the run label travel with it.
- **Per-user attribution without handing the agent an identity.** The web driver attaches an opaque
  per-account value around the call, the same way identity is stamped at the trail's sink (ADR-0820);
  `agent.py` and `trace.py` stay free of identity.
- **A rating is copied to the trace as a score.** The trail table remains the record (ADR-0750); the
  copy exists so that whoever debugs a run sees the thumbs-down beside it.
- **An evaluation run reports the tracer's monthly allowance before it starts**, and warns above
  50%. The figure is counted by this project, because Langfuse has no billing API. An unreadable
  figure is reported as unknown, never as zero, and the run is warned, not stopped.
- **The tracer cannot affect an answer.** A tracer that is unreachable, rejecting (including the
  Hobby tier's monthly cap), or raising must leave the answer, the trail and the rating exactly as they
  would have been — the same fail-open line the trail draws (ADR-0710).

Out of scope, deliberately: the usage-events table and its queries (WP4's first half, its own work
package); per-entry ratings; masking of corpus text (exposing corpus entries to the tracer was
accepted in the roadmap); any use of the tracer's own feedback UI.

## Capabilities

### New Capabilities
- `hosted-tracing`: when question-level traces are sent to a hosted tracer, what they carry, how
  they are found from a question or a rating, what is refused, and that a tracer fault never reaches
  a reader.

### Modified Capabilities
<!-- None. The rating's copy to the tracer is specified in `hosted-tracing` rather than by amending
     `answer-feedback`: the feedback requirements are unchanged in what a reader sees and in what is
     recorded, and a MODIFIED block would restate them in full to add one sentence. -->

## Impact

- **Code:** a new core module for the tracer (setting, handler, score, the LangSmith refusal);
  `agent.py` at the one `agent.stream` call; `feedback.py` at `_record`; `web.py` where the event
  stream is consumed (attribution); `config.py` for the setting.
- **Dependencies:** `langfuse` (4.x) added to the `ask` extra, bringing `opentelemetry-api`,
  `opentelemetry-sdk` and the OTLP HTTP exporter. `langsmith` remains, transitively.
- **Configuration:** a new project setting and the Langfuse keys in `.streamlit/secrets.toml.example`
  and README's configuration table.
- **Data leaving the host:** with tracing on, prompts, tool results, corpus text, answers and rating
  comments go to Langfuse's EU region. Accounts appear only as an opaque digest.
- **Docs:** README (the "no tracing instrumentation yet" paragraph is replaced), architecture diagram,
  CLAUDE.md module table, roadmap WP4, CHANGELOG, ADRs `1000`–`1040`.
