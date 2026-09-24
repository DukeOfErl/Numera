## Context

See `proposal.md` for why. The code this lands on:

- **One call reaches the framework.** `AskAgent._ask` builds its graph and calls `agent.stream(...)`
  once per question, with `config = {"configurable": {"thread_id": ...}, **trace.run_config("ask")}`.
  `QuestionTrace.run_config` already supplies `run_name` (`ask:<question_id>`), `tags` and
  `metadata` (`question_id`, `run`, `session_id` when there is one). It was written so that traces
  would be readable on the day a tracer arrived (`add-ask-agent` task 2.2).
- **The stream is a generator consumed lazily by a driver.** Streamlit abandons it mid-iteration on
  every rerun (ADR-0840), and LangGraph runs nodes on worker threads.
- **Identity stops at the driver** (ADR-0820, `.claude/rules/identity.md`). `agent.py`, `trace.py`
  and `feedback.py` may not name any of `Identity`, `role`, `email`, `account`, `user_role`,
  `user_email`, and `test_driver_independence.py` parses them to enforce it. Identity reaches the
  trail through a `logging.Filter` at the sink.
- **Ratings go through `feedback._record`**, the one function both `record_verdict` and
  `record_comment` call. `feedback.py` is presentation, not core.
- **`langsmith` 0.11.0 is installed** through `langchain-core` 1.5.6. LangChain attaches a LangSmith
  tracer on its own whenever `LANGSMITH_TRACING` (or the legacy `LANGCHAIN_TRACING_V2`) is true.
- **Langfuse's Python SDK is 4.15.4** (PyPI, 2026-09-16) and is built on OpenTelemetry: it depends
  on `opentelemetry-api`, `-sdk` and `-exporter-otlp-proto-http`. It integrates with LangChain through
  `langfuse.langchain.CallbackHandler`, passed in `config["callbacks"]`. Nothing is traced unless
  that handler is passed.

## Verified against the installed versions (tasks 1.2, 1.3 — 2026-09-24)

`langfuse` 4.15.6, `langsmith` 0.11.0, `langchain-core` 1.5.6, `langgraph` 1.2.11. Read from the
installed source unless a docs page is named. Each answer corrects or confirms a guess made below.

| | Question | Answer, and where it came from |
|---|---|---|
| a | Host variable | `LANGFUSE_BASE_URL`; `LANGFUSE_HOST` is deprecated (`_client/environment_variables.py`). The client also takes `base_url=` directly, which is what we pass. |
| b | Binding a handler to a trace id | `CallbackHandler(trace_context={"trace_id": ...})` sets the root LangChain run's trace id (`langchain/CallbackHandler.py`). The handler finds its client with `get_client(public_key=...)`, so we construct `Langfuse(...)` once and the handler reuses it. |
| c | `propagate_attributes` | Contextvar-based OpenTelemetry context. Keyword-only `user_id`, `session_id`, `metadata`, `tags`, `trace_name`, `environment`. Values must be ≤200 US-ASCII characters. Only spans created *after* entering it carry the attributes. |
| d | Score ids | `create_score(score_id=...)`. The docs (search-docs, scores page) say a re-sent score overwrites only when **id, name and calendar date of the timestamp** all match. A verdict changed on a later day is therefore a second score. Accepted: it is a copy, and the trail holds the answer. `TEXT` scores need 1–500 characters, so the comment goes in `comment` on a `CATEGORICAL` score. |
| e | Handler errors | `create_score` catches and logs its own exceptions. LangChain's callback manager logs handler exceptions unless the handler sets `raise_error`, and Langfuse's does not. Group 4 still tests the outcome, not these claims. |
| f | Exit flush | `resource_manager.py` registers `atexit.register(self.shutdown)`. **We write no flush of our own.** |
| g | Global OTel provider | Without `tracer_provider=`, the client installs a new `TracerProvider` as the **global** one whenever the global is still the default proxy. **We pass our own `tracer_provider=`**, so the global is never touched. `span_exporter=` exists too, and it is the tests' seam: an in-memory exporter on the real code path. |
| h | Counting units | v2 Metrics API (`api.metrics.metrics(query=...)`): views `observations`, `scores-numeric`, `scores-categorical`, `scores-boolean`, each with a `count` measure. There is **no traces view**; traces are counted as observations with `isRootObservation = true` (docs, metrics-api.md). Hobby has v2 metrics. **Billing period:** Langfuse's own source (via search-docs) stores a per-organisation *billing cycle anchor*, reset to "start of today" on a downgrade to Hobby, so it is not the calendar month and the project API cannot read it. Decision: count the **last 31 days**. That window always contains the current billing period, so it can only over-count, which is the safe direction (it pauses more, never less). |
| i | Session and user on child spans | The handler reads `langfuse_session_id` / `langfuse_user_id` / `langfuse_tags` from the root run's metadata and enters `propagate_attributes` itself at the root chain start (`CallbackHandler.py` ~l.588). So session goes in the metadata, and every child carries it. User id comes from the driver's outer `propagate_attributes` (D5), and task 3.3 must show the two nest. |
| 1.3 | LangSmith refusal | Probe: `LANGSMITH_TRACING=true` with a model double and the generator consumed one event at a time. No context: **13** LangSmith runs started, one on `ThreadPoolExecutor-2_0`. Inside `langsmith.tracing_context(enabled=False)`: **0**. D3's mechanism holds and the fallback is not needed. |

## Goals / Non-Goals

**Goals:**
- The gate on sending anything, and the refusal of the vendor's own switch, live in the operation
  that answers a question. They do not live in a driver.
- The trace id can be computed from `question_id`, so no join table is needed.
- Attribution without giving the agent any fact about the person.
- The tracer cannot fail, slow or alter a question, and it cannot alter a rating.

**Non-Goals:**
- Masking corpus text or prompts before export. The roadmap accepted that corpus entries are exposed.
- Choosing what the evaluation harness does differently. It traces when the setting is on, like
  every other caller (ADR-0110). The operator leaves the setting off for a run that shouldn't spend the
  Hobby allowance.
- Reading anything back from Langfuse. Analysis reads the trail.
- Changing the agent's graph. Callbacks are not nodes, so the diagram generated from the compiled
  graph does not change.

## Decisions

### D1 — Langfuse Cloud, EU region, Hobby tier (ADR-1000)

| | LangSmith Developer | Langfuse Hobby |
|---|---|---|
| Allowance | 5k traces/month | 50k units/month. A unit is a trace, an observation or a score |
| Access | 14 days. 180 if feedback is sent with `extend_trace_retention=true` | 30 days, not extendable |
| Seats | 1 | 2 |
| EU on the free tier | Yes, `eu.smith.langchain.com` | Yes, and it is the default host |
| Enabled by | Env var, globally, or `tracing_context` | Passing a handler; never by env alone |
| Trace id from our id | Set `run_id` in config | `create_trace_id(seed=...)` |
| New dependencies | None | `langfuse` + OpenTelemetry SDK |

Langfuse was chosen for the longer flat window, the second seat, EU by default, and because its opt-in
design fits "a decision, not an env var". LangSmith would have cost no new dependency and gives the
native LangGraph view. Retention matters less than it looks, because the trail is the record
(ADR-0750).

**What was not verified.** Langfuse's first-party docs do not say what Hobby does past 50k units.
Third-party write-ups (2026) say it is a hard stop with no overage, and that is assumed here. It is
the reason D7 matters.

**ADR-0750's copy detail changes.** That ADR says the copy is written "with the retention-extension
flag set", which is a LangSmith mechanism. Langfuse has no equivalent, so a score does not extend a
trace. ADR-1000 records the amendment. ADR-0750's decision (the trail is the record, the tracer gets
a copy) is unchanged.

### D2 — The project setting, and credentials that do not enable anything (ADR-1010)

`SCINUMBERS_TRACING`, read through `config.env_setting` (so `.streamlit/secrets.toml` top-level keys
reach it too):

| Value | Result |
|---|---|
| unset, empty, `off` | Off. Nothing imported from `langfuse`, nothing sent |
| `langfuse` | On, if the credentials below are all present. Otherwise off, and the operator is told which is missing |
| anything else | Off, and the operator is told the value was not recognised |

The credentials are `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and the host variable. **The host is
required rather than defaulted**, so the region is written down in the deployment's configuration and
not inherited from an SDK default. The host variable is `LANGFUSE_BASE_URL` (verified, row a).

**Why not let the Langfuse keys enable it.** A key present is not a decision; the whole point of the
setting is that someone wrote it on purpose. **Why off rather than refusing to start on an unknown
value.** Refusing to start would make telemetry an outage (ADR-0710). A missing trace is the cheap
direction, and the operator hears about it.

The setting is read once per agent, at construction, and held by the operator-facing value that
`agent.py` consults per question.

### D3 — Where the gate and the refusal live: a core module used at the one stream call

A new core module, **`hosted_trace.py`**, holds everything vendor-specific: reading the setting, the
lazy `langfuse` import, building the handler for a question, the score copy, the attribution context,
and the LangSmith refusal. `agent.py` calls it at the single `agent.stream` site. The call site that
answers a question is the one every caller goes through. The terminal, the web page, the harness and a
test constructing `AskAgent` all get the same behaviour, with no driver asked to remember
(the "guards belong to the operation" rule).

`trace.py` stays vendor-neutral: `run_config` is unchanged, and `hosted_trace` adds the
Langfuse-named metadata keys (`langfuse_session_id`, `langfuse_tags`) to the config it is given.
`hosted_trace.py` joins the identity-free set in `test_driver_independence.py`. It holds no identity;
the per-account value reaches it only as an opaque string from the driver (D5).

**Refusing LangSmith.** The stream runs inside `langsmith.tracing_context(enabled=False)`, whatever
the project setting. Langfuse's handler is an ordinary callback and is not affected. Task 1.3 has to
show, against the installed `langsmith` and `langchain-core`, that this context beats
`LANGSMITH_TRACING=true`, and that it holds across LangGraph's worker threads and a lazily consumed
generator. If it doesn't, the fallback is to strip LangChain's tracer from the resolved callback
manager. The test is written against the behaviour (no LangSmith tracer receives a run), not against
the mechanism, so it survives a change of mechanism.

**Alternatives rejected.**
- Building the handler in each driver: that protects three callers and forgets the fourth.
- Unsetting `LANGSMITH_TRACING` from `os.environ` at import: this mutates process state that other
  code can read, and it silently fixes a misconfiguration the operator should hear about. The operator
  *is* told when the variable is set.

### D4 — The trace id is derived from `question_id`

`Langfuse.create_trace_id(seed=question_id)` gives 32 hex characters, the same for the same seed. The
handler is bound to that trace id, so the question's LangChain run becomes that trace. Task 1.2
confirms the 4.x way to bind it (`trace_context={"trace_id": ...}` on the handler, or an enclosing
`start_as_current_observation`).

`feedback._record` derives the same id from the same `question_id` to attach a score. Langfuse
accepts a score for a trace id before the trace arrives (verified on the scores page, 2026-09-23),
which covers a reader rating an answer the exporter has not yet flushed.

**Alternative rejected:** Langfuse's own random ids, with a `question_id → trace_id` column in the
trail. That is one more thing to lose, and the spec says no mapping table.

### D5 — Attribution from the driver, as an opaque per-account digest (ADR-1020)

The web driver wraps its consumption of `agent.ask(...)` in `hosted_trace.attributed(user_id)`, a
context manager over Langfuse's `propagate_attributes(user_id=...)`. It is a no-op when tracing is
off or `user_id` is `None`. The value is `web.account_scope(admission)`: the first 16 hex characters
of the SHA-256 of the account's address. That value is already computed, already opaque, stable per
account, and `None` without sign-in.

This is the trail's own pattern, where identity is stamped at the sink by the driver. The agent is
handed nothing new, so `user-identity`'s "same inputs whoever asks" holds by construction.

**Alternatives rejected.**
- The address itself: personal data sent to a third party for a purpose a stable key already serves.
- A parameter on `AskAgent`: ADR-0820 refuses exactly this. `budget_scope` carries the same digest,
  but it is a funding scope, and reading it as "who" is the conflation that ADR warns against.
- A keyed HMAC (secret salt): a real improvement against someone who knows a tester's address and
  wants to find their traces. Deferred: the tracer is not an adversary and the testers are a handful.
  Recorded as a risk.

**Must be proven, not assumed** (task 3.3): that a `contextvars`-based attribute set in the driver
reaches spans created on LangGraph's worker threads, across a generator the driver advances, and
across a Streamlit rerun that abandons it.

### D6 — The rating's copy is a score, written after the trail row

In `feedback._record`, after the trail record:
- a verdict becomes a `BOOLEAN` score named `reader_verdict` (1 up, 0 down);
- a comment becomes a score named `reader_comment`, with the text in the score's `comment` field.

Each score has a deterministic id derived from `question_id` and the event. A reader who changes
their verdict then overwrites it in the tracer rather than adding a second one, matching what the
reader sees. Task 1.2 confirms that Langfuse treats a repeated score id as an upsert.

After the trail, not before and not instead. The copy is wrapped so that nothing it raises leaves
`_record` (D7).

### D7 — Fail open, and tell the operator

- **During the question:** Langfuse exports on a background thread. LangChain's callback manager logs
  and swallows handler exceptions unless the handler sets `raise_error`, and task 1.2 confirms Langfuse's
  handler does not. `hosted_trace` builds the handler inside a `try`, and a failure to build it means
  "trace nothing for this question", never an ending.
- **For the score:** the SDK call is queued rather than sent inline. It is wrapped anyway, because
  "the SDK doesn't raise" is a claim about someone else's code.
- **For the operator:** failures are written to the trail logger as a `tracing.failed` record, which
  already reaches the operator's sinks (ADR-0710's route). A disabled-but-misconfigured setting is
  reported once per process, not once per question.
- **Exit:** the terminal and the harness are short-lived processes. `hosted_trace` flushes at exit.
  Task 1.2 checks whether Langfuse registers its own `atexit` flush, so we don't write a second one.

### D8 — The dependency

`langfuse>=4.15,<5` in the `ask` extra, with a comment in the same style as its neighbours. It is
imported only inside `hosted_trace`, and only once the setting is on. A deployment with tracing off
never starts OpenTelemetry's exporter, and never installs anything into its global provider.

### D9 — The allowance check before an evaluation run: estimate, then pause for approval

Added at the user's request, 2026-09-24, and revised the same day. The harness is the one caller
that can use up a month's allowance in an afternoon, and on Hobby that also switches tracing off for
the readers. **The harness is not run unattended**: the operator starts it and watches it. So it asks
before spending. It does not just warn.

**Langfuse has no billing API.** The feature request (GitHub discussion #12612) is open with no
maintainer reply, and the pricing and billable-units pages point only to the Usage Management
dashboard. So every figure is **counted, not read**.

- **Used.** `hosted_trace.monthly_usage()` gives units = traces + observations + scores (the
  billable-units definition) ingested since the start of the period, over the Hobby allowance of
  50,000. The v2 Metrics API has `observations` and `scores-*` views but no `traces` view, so traces
  come from v1 metrics or the traces list, whichever the installed SDK exposes (task 1.2 (h)). The
  Hobby Metrics API allows 100 requests a day, and one check costs a handful.
- **Per question.** Units ÷ traces over the same period. It calibrates itself: it is the average of
  what questions actually cost this month, readers' and earlier runs' alike, with no constant to go
  stale. With no traces yet this month it is *unknown*, and unknown pauses the run. That is
  deliberate: the first run of a month asks once, and every later run has a figure.
- **This run.** Questions still to be asked × per-question. "Still to be asked" is the pairs the
  resume logic will not skip. It comes from the same place `run_evaluation` decides that, not from
  `len(questions) × repeats`, which over-counts every resumed run. Task 4.6 exposes it without
  duplicating the resume rule.
- **Period.** The last 31 days (row h): the billing month is anchored per organisation and cannot
  be read, and 31 days always contains it. The window is printed beside the figures.
- **Scope.** API keys are per project and units are per organisation. The count covers this project
  only, which is exact while the organisation holds one project. README says so.
- **Unknown is not zero.** Any failure to count, including a partial count where one of the views
  failed, gives *unknown*. A sum over the views that did answer would under-report, which is the
  dangerous direction.

**The pause.** In `eval_cli run`, after the corpus is loaded and before `run_evaluation`. The run
pauses when more than 50% is used, when the estimate exceeds what remains, or when any figure is
unknown. Only an explicit `yes` proceeds. Anything else ends the run with its own exit code before
any question: an empty line, another word, EOF, or stdin that is not a terminal. Declining is the
cheap direction. A non-interactive invocation therefore cannot pass this gate when a condition holds.
That is accepted, because the user runs the harness attended. If that changes, an explicit flag
(an approval given in advance, named on the command line) is the way to add it. Removing the pause
is not.

**Where each part lives.** The counting and the conditions (`needs_approval(usage, estimate)`) are
in `hosted_trace`, as pure functions over the counts, so they are testable without a terminal. The
prompt and its wording are in `eval_cli`, the command. `evaluation.py`, the harness core, gains no
input and stays runnable without a terminal. That is what `test_driver_independence`'s `HARNESS`
rule protects, and it only forbids importing a driver, so a prompt in the command does not break it.

**Alternative rejected:** a local tally of what this process sent. It misses the readers' questions
on the deployed app, which spend the same allowance.

## Risks / Trade-offs

- [Hobby's cap is assumed to be a hard stop] → Traces stop for the rest of the month, silently from
  the reader's side. That is acceptable by D7. The operator watches the usage dashboard, and task 5.3
  measures units per question on the first real traces and writes the figure into README so the
  headroom is known rather than guessed.
- [Context propagation across LangGraph threads or a lazily consumed generator loses the user id]
  → Traces arrive unattributed. That fails in the cheap direction, but it has to be tested (task 3.3),
  not assumed.
- [A future `langsmith` or `langchain-core` changes how `tracing_context` interacts with the env
  switch] → The refusal test asserts the outcome (no LangSmith run) with the env var set, so a
  version bump that breaks it fails the suite.
- [The digest is an unsalted hash of an address] → Anyone who already knows a tester's address can
  recognise their traces. Accepted for now (D5), and it is the next step if the tracer's audience widens.
- [Readers' comments are free text, now copied to a third party] → A comment could hold something
  personal. README says so, beside where it already says prompts and corpus text leave the host.
- [OpenTelemetry arrives as a dependency] → Langfuse 4.x exports only Langfuse and GenAI spans by
  default. When DeepEval returns with `add-judged-faithfulness`, both will want OTel. Worth checking then.
- [The evaluation harness can burn the allowance] → D9: the run shows its estimate and pauses for
  approval when it is at risk. The run label is on every trace.
- [The per-question average is skewed by the mix of this month's questions] → It is an estimate and is
  labelled as one. An evaluation set's compound questions may cost more than readers' average. Task 5.3's
  measured figure is the check on it.

## Migration Plan

1. Merge with the setting absent everywhere. Behaviour is unchanged, and the LangSmith refusal is the
   only thing that is live.
2. Create a Langfuse Cloud EU project. Put the keys, the host and `SCINUMBERS_TRACING = "langfuse"`
   in a local `secrets.toml`, ask a question and rate it, then check one trace by hand (task 5.2).
3. Add the same to the Community Cloud secrets box for the alpha.

Rollback is removing `SCINUMBERS_TRACING`. Nothing else depends on the tracer.
