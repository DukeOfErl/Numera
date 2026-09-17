## Why

The trail is written to `logs/trace.jsonl` inside a Streamlit Community Cloud
container, whose filesystem does not survive a reboot or a redeploy. Every
search, alias resolution, truncation decision and spend increment from every real
user session has been discarded, and there is no usage or debugging record from
production at all.

This does not merely leave a feature unbuilt — it defeats a requirement already
in force. `agent-session` requires the deterministic layer to be logged under a
per-question identifier, on the stated grounds that "the identifier is what makes
an intermittent failure investigable after the fact." The code satisfies that
in-process and the environment throws the result away, so the requirement is met
and its purpose is not. A record that does not outlive the container cannot make
anything investigable afterwards.

It is also the prerequisite for capturing what users think of an answer. A rating
has to name the question it is about, and the identifier that names it cannot be
added to records already written.

## What Changes

- The trail gains a **durable sink** that survives a redeploy, alongside the
  existing file sink. Where records go becomes configuration, not a constant.
- A failed write to that sink **cannot break the app**. This is the deliberate
  opposite of the spend gate: that fails closed because proceeding costs
  unbounded real money, and this fails open because proceeding costs one row of a
  dataset read by eye. The refusal to fail closed is a requirement, not an
  implementation detail, which is why it appears in the spec.
- Records gain the **session** they belong to, not only the question. Today a
  question can be located but the sequence of questions one person asked cannot
  be reassembled, so nothing can distinguish one person asking ten questions from
  ten people asking one.
- `question_id` is **carried through to the web driver's rendered items**, so a
  thing on screen can be traced back to the question that produced it. Today
  `web.Item` does not carry it and `web.item_for` drops it.
- **No behavioural change to answering.** The agent, the tools, the spend gate
  and the limits are untouched.

## Capabilities

### New Capabilities

None. Everything here is a change to how an existing obligation is discharged.

### Modified Capabilities

- `agent-session`: the per-question logging requirement gains durability (a
  record must outlive the process that wrote it) and a session identifier on
  every record. A new requirement states that recording is best-effort and must
  never fail a question — the one place in this system where a failed write is
  deliberately ignored, stated so that nobody later "fixes" it into a fail-closed
  path by analogy with the spend gate.

## Impact

- `scinumbers_ask/trace.py` — gains a sink it does not choose for itself, a
  `session_id` on records and in `run_config()` metadata, and the best-effort
  contract.
- `scinumbers_ask/web.py` — passes the session identifier it already mints into
  the trail; `Item` carries `question_id`.
- A new module owning the durable sink and its schema. It is reached by the
  drivers, never by the agent core, so the dependency direction asserted in
  `tests/test_driver_independence.py` is unchanged.
- **Dependencies**: `sqlalchemy` and `psycopg[binary]`, already added to the
  `ask` extra. The deploy branch promotes `ask` into `[project].dependencies`,
  so they must reach that arrangement before the next deploy.
- **Configuration**: a connection URL in `.streamlit/secrets.toml` and in the
  Community Cloud secrets box. Absent, the app must run exactly as it does today.
- **Not affected**: the agent's event stream, the corpus, the evaluation harness.

## Out of scope

Named because each is a natural next thought and none belongs here:

- The feedback widget and where ratings are stored — the following change.
- Authentication, identity and roles — a later change. Records carry a session,
  not a person, and the column for a person is added when there is one.
- Wiring a hosted tracer (LangSmith). It answers a different question — why one
  run behaved as it did — and needs none of this.
- Anything on Cloud Run, and any move of the checkpoints or the spend ledger off
  SQLite.
