## Context

See `proposal.md` — Why. The requirements are in `specs/corpus-query/`, `specs/grounded-answering/`,
`specs/agent-session/`, `specs/spend-control/`, and `specs/answer-evaluation/`.

Constraints that shape everything below:

- **LangChain and LangGraph are required**, so the question is how to use them well rather than
  whether to.
- **The interface is a web application**, with a terminal driver first. A framework that re-runs its
  script on each interaction cannot host an agent that blocks waiting for input.
- **Models are reached through OpenRouter**, where the capable models are expensive and the available
  set does not include the newest.
- **Spend must be bounded by code**, as a development-stage guard.
- **The corpus is an external file** that must not be committed, as in `add-grounding-validator`.

Corpus figures quoted below were measured during exploration: 14,294 entries, 841 distinct organism
strings, an average full entry of ~1,400 characters, and single-word property searches matching
300–1,600 entries.

## Goals / Non-Goals

**Goals:**

- One agent, several drivers, no driver privileged and no mode flag inside the agent.
- Conversation that survives a process boundary, because a web interface requires it.
- Retrieval that fits in a context window and makes the agent's selection decisions explicit.
- A first build that is small enough to prove, with capability added in named stages.

**Non-Goals:**

- Deployment, scaling, and multi-user serving. Isolation is specified so concurrency is possible
  later, not so it is supported now.
- Optimising spend. The controls bound and reveal cost; tuning follows measurement.
- Any persistence beyond session checkpoints, the evaluation results file, and logs.

## Design patterns used

Named because naming is only useful when it changes what gets built, and each of these does.

| Pattern | Where it applies | Ours or the framework's |
|---|---|---|
| **Ports and Adapters** (hexagonal) | The agent exposes an event/command port; terminal, web, and evaluation are adapters. The spine of the design. | Ours |
| **Repository** | `corpus-query` is a read-only repository over the corpus; nothing else reaches the data. | Ours |
| **List/Detail** (coarse-to-fine) | Search returns summaries with a total; retrieval returns bodies. | Ours |
| **Circuit Breaker** | The run budget trips to stop a systematic fault early rather than spending through it. | Ours |
| **Decorator / Interceptor** | Middleware wrapping the model call; LangChain's middleware chain is a chain of responsibility. | Framework's mechanism, our use |
| **Memento** | The checkpointer captures and restores session state. | Framework's |

## Decisions

### Middleware is the extension point, not a graph built by hand

LangChain v1 agents accept **middleware** with hooks at each step of the loop — `before_agent`,
`before_model`, `after_model`, `after_agent`, and the wrapping `wrap_model_call` and
`wrap_tool_call`. The wrapping hooks may invoke the handler zero times, which short-circuits the call.

The spend gate is therefore **a `wrap_model_call` middleware** that checks accumulated spend and
declines to call the handler once the ceiling is reached. That is the Decorator pattern applied
exactly where the dispatch happens, and it satisfies `spend-control` literally rather than
approximately.

*Alternative considered and rejected.* An earlier draft put the gate in a `StateGraph` node wrapping
the agent. That works but sits one layer out from the actual dispatch, so the check would be "before
the agent's next step" rather than "before this model request" — and it means composing a graph by
hand where the framework offers a hook.

*Corollary:* prefer built-in middleware over writing our own. The framework's own guidance is to
configure rather than reimplement, and most of what this change needs already exists. Verified against the installed
packages on 2026-08-18 — `langchain` 1.3.15, `langgraph` 1.2.11, `langchain-core` 1.5.6 — rather than
from documentation alone:

| Requirement | Built-in | Status here |
|---|---|---|
| Retried model calls | `ModelRetryMiddleware` | Configure — MVP |
| Retried tool calls | `ToolRetryMiddleware` | Configure — MVP |
| Tool errors returned to the agent, not fatal | `ToolErrorMiddleware` | Configure — MVP |
| Bounded retrieval effort per question and per run | `ModelCallLimitMiddleware` (`thread_limit`, `run_limit`) | Configure — MVP; the two limits map onto per-question and per-run bounds |
| Routing to another model when one is unavailable | `ModelFallbackMiddleware` | Available, not configured yet |
| Condensing a long conversation | `SummarizationMiddleware` (`trigger`, `keep`) | **Deferred** — see the conversation-bound decision below |
| Capping tool calls specifically | `ToolCallLimitMiddleware` | **Deferred** — had unexpected consequences in `interv_preper` |
| Redacting sensitive text | `PIIMiddleware` | **Deferred** with the guardrails work |
| Selecting tools dynamically from a larger set | `LLMToolSelectorMiddleware` | **Deferred** — a later phase; the MVP has a fixed tool list |

Only one hook here is genuinely custom: the spend gate, because no built-in bounds cost in currency
rather than in call count. Everything else above is configuration.

Hook signatures, read off `AgentMiddleware` in the installed package. Node-style hooks
(`before_agent`, `before_model`, `after_model`, `after_agent`) take `(state, runtime)` and return
`dict | None`. Wrapping hooks take `(request, handler)`: `wrap_model_call` receives a `ModelRequest`
and a handler returning a `ModelResponse`, and `wrap_tool_call` the tool equivalent. An async
`awrap_model_call` exists alongside. The handler is an ordinary callable, so calling it zero times is
what makes the spend gate possible.

`create_agent` lives in `langchain.agents` and takes `checkpointer` directly — so no `StateGraph` needs
composing by hand, as an earlier draft assumed. Its parameters include `model`, `tools`,
`system_prompt`, `middleware`, `state_schema`, `checkpointer`, `store`, and `interrupt_before` /
`interrupt_after`, which is where the deferred approval flow would eventually attach.

*Found by verifying rather than reading.* **`SqliteSaver` ships separately** from `langgraph`, in
`langgraph-checkpoint-sqlite`. Only `InMemorySaver` is reachable from a plain `langgraph` install, and
in-memory is exactly what the process-boundary requirement rules out — so the extra package is a direct
dependency, not an option.

*Consequence to respect.* The check runs between model calls, so the request that crosses the ceiling
completes. Final spend can exceed the ceiling by at most one call, which `spend-control` states
rather than implying exactness.

### The checkpointer stays; suspending for approval does not

These are separate mechanisms and only one is deferred. A **checkpointer** persists state and is what
makes a follow-up question in a web interface possible at all, since the script re-runs on every
interaction and holds nothing between them. `interrupt()` suspends mid-run and resumes on a command,
and is only needed to ask permission part-way through a question.

So: file-backed checkpointer from the start, `interrupt()` left for later. Reaching a ceiling ends the
question, which bounds cost just as effectively as pausing to ask.

State management is widely reported as a leading source of production trouble in agent systems,
though the figures circulating for it trace back to a report this design has not read. The decision
does not rest on the statistic: hand-rolled session state in the web framework would be more code
than the checkpointer and would lose durability across restarts, which is reason enough.

*Alternative considered.* Holding the conversation in web-framework session state and passing it in
each turn. Rejected: more code, lost on refresh and redeploy, and it cannot satisfy
`agent-session`'s process-boundary requirement.

### Reliability middleware is configured, not written

A transient provider failure — a rate limit, a gateway error — should not end a question, and inside
an evaluation it would burn a question slot and its spend for no information. Three built-ins cover
this and are configured rather than implemented: **`ModelRetryMiddleware`** for retried model calls
with backoff, **`ToolRetryMiddleware`** for retried tool calls, and **`ToolErrorMiddleware`** so a
tool raising an exception returns something the agent can react to instead of collapsing the run.
`ModelFallbackMiddleware` routes to another model when the first is unavailable.

A shared gateway makes transient failure likely enough that this belongs in the first build rather
than in Deferred.

*Consequence to respect.* Every attempt is billed, so retries accumulate against the spend ledger and
the ceiling. This is correct — the money was spent — but it means a retry storm consumes budget, which
is precisely what the ceiling is for.

### Models: cheap while building, capable once proved

Development runs on **Claude Haiku 4.5**; the later target is **Claude Opus 4.7**, the most capable
model available on the account. The choice is driven by instruction-following rather than raw
capability, because every requirement in `grounded-answering` is an instruction the model must obey —
cite every quantity, refuse beyond the corpus, do not compare across unit dimensions. A model that
reasons well but follows loosely is worse here than one that reasons adequately and complies.

The model is configuration, selectable per run, so the same question set can be put to both.

*Consequence to respect.* A weak model failing the citation or refusal requirements is
indistinguishable from a broken harness if the model is not recorded. `answer-evaluation` therefore
requires the model on every result and per-model breakdown in reports.

### Spend comes from the provider, not from a price table

OpenRouter reports the cost of each request alongside token usage, including cache reads and writes;
for streamed responses it arrives with the final chunk. Reading that figure is strictly better than
tokens times a local table: nothing to keep current, no drift when the provider reprices, and it is
actual spend rather than an estimate.

A configured price table remains a fallback for a provider that reports only token counts, and the
system refuses to run when it has neither.

*Verified against OpenRouter on 2026-08-18.* Cost arrives at
`response_metadata["token_usage"]["cost"]`, with a `cost_details` breakdown, and — answering the
question the task raised — **it needs no per-request opt-in**: the figure was present without passing
`usage: {"include": true}`, and identical with it. On a 14-in / 4-out call it reported `3.4e-05` USD,
matching the price table computed from the published per-token rates exactly, which is the strongest
available evidence that the fallback table and the reported figure agree.

Two consequences for the ledger. The provider reports cost as a **float**, so conversion to integer
micro-dollars is the one place a float is allowed in: round once at that boundary and stay integral
afterwards. And money is held in **micro-dollars rather than cents**, because a thousand-token call on
a cheap model costs a fraction of a cent — a ledger rounding each increment to whole cents would round
most of them to zero and never move. The same reasoning applies to display: fixed two-decimal
formatting renders development-scale spend as "$0", so precision follows magnitude.

Model slugs confirmed from the models endpoint: `anthropic/claude-haiku-4.5` for development and
`anthropic/claude-opus-4.7` as the capable target.

### Two-tier retrieval

Search returns capped compact rows plus the total match count; full entries are fetched individually.
A full entry averages roughly eight times a compact row, and a single-word search can match over
1,600 entries — returning those in full would be a six-figure token result for one tool call, and
would bury the few relevant entries.

The secondary effect matters as much: the agent's selection becomes an explicit tool call that can be
logged and scored, rather than an invisible step inside one forward pass. Returning the total is what
makes truncation honest — without it the agent cannot distinguish "50 results, that is all" from
"50 of 1,656".

### A deterministic alias index rather than agent memory

Resolving "E. coli" to `Bacteria Escherichia coli` is knowledge worth keeping, and long-term agent
memory is the obvious-looking home for it. It is the wrong home: the mapping is identical for every
user, derivable from the corpus, and something a human should be able to inspect and correct. As
memory it would be per-user, non-deterministic, and invisible when wrong.

Built from the corpus at load time and shared. Determinism underneath, agent on top — the same
principle the project applies elsewhere.

### Conversation memory is thread-scoped, and bounded by refusal

Within a session the checkpointed state carries the conversation. Nothing persists across sessions:
there is no personalisation that changes a correct answer, so cross-session memory has no work to do
until user accounts exist.

Growth is bounded by warning as the bound approaches and refusing further questions once reached.
`SummarizationMiddleware` would condense instead, and is the better long-term answer, but a
summariser that silently drops the entry a later answer depended on produces a confident answer with
a missing citation. Refusing is honest; condensing needs evaluating first.

### The web interface must cache the index, not rebuild it

The web framework re-runs the script on every interaction. The corpus index and alias index are built
over 14,294 entries, so they must be held in a resource cache that survives re-runs rather than
constructed per interaction — the difference between a usable application and an unusable one.

Per-session data — the session identifier above all — lives in the framework's session state. The
driver holds no agent state of its own beyond that identifier.

The framework is **Streamlit**, chosen because it is a course requirement and suits a
single-developer demo. It is named here as the current choice rather than a commitment: the
specifications say nothing about it, the caching and session-state requirements above are stated as
properties rather than as Streamlit APIs, and swapping it means writing another adapter. Expect it to
change when this is shown to testers.

### Logging the deterministic layer

Structured records, one correlation identifier per question, at the tool, spend, and session
boundaries: what was searched, how many matched, what was truncated, what an alias resolved to, each
spend increment and its source.

This is complementary to tracing rather than redundant with it. Tracing tools show model calls; the
failures that will cost time here are in the deterministic layer, and several are silent — an alias
resolving to the wrong stored value, a truncated result treated as complete, spend accumulating from a
response that reported no cost. A non-deterministic agent reproduces those intermittently, which is
exactly when logs earn their place. The correlation identifier is the part that is annoying to
retrofit.

### Built in stages

Following the framework's own guidance: a static system prompt and a fixed tool list first, then one
dynamic feature at a time, monitoring calls, tokens, and latency throughout. Dynamic tool selection,
dynamic prompts, and conversation condensation are each a later step rather than part of the first
build. `tasks.md` is ordered accordingly.

### Evaluation results are an append-only JSONL file

One record per question and repeat, written as each completes. Resumption reads the file and skips
what is present; the reporter computes from whatever is there, so reporting on a partial run falls out
rather than being a separate feature.

Each record carries the question, the answer, the cited entries, the expected entries, and the model —
the shape external evaluation tooling expects. Adopting such a tool later then costs a reading
exercise rather than a re-run paid in model spend.

## Risks / Trade-offs

- **Framework API drift.** LangChain v1 moved the recommended entry point and deprecated the
  constructor most material still shows; middleware parameter names come from documentation read
  during design. → Verify the API surface against the installed version as the first task, not as an
  assumption.
- **A cheap development model may not follow the answering rules.** Citation and refusal are
  instructions, and a small model may comply unevenly. → The model is recorded on every result, so
  the harness and the model can be diagnosed separately; the capable model is a configuration change.
- **Provider-reported cost may need enabling, or may be absent for some models.** → The price-table
  fallback exists, and the system refuses to run rather than guessing.
- **A web framework that re-runs its script fights long-running work.** Progress needs the agent to
  emit retrieval events as they happen. → The event contract requires this, so the constraint is
  discharged by specification rather than discovered during interface work.
- **Refusing rather than condensing will annoy users in long sessions.** → Deliberate: a missing
  citation is worse than a refused question, and condensation is deferred rather than rejected.
- **Corpus text reaches the model.** Entry comments are free text and could carry instructions. →
  Recorded under Deferred; the read-only tool surface bounds what any such instruction could achieve.
- **The run budget doubles as a circuit breaker.** Two questions at the per-question ceiling exhaust
  it. → Intended, but the report must say a run stopped on budget or a tripped breaker reads as a poor
  score.

## Open Questions

- The checkpointer backend if this is ever deployed rather than run locally. A file-backed store is
  right for one user on one machine; a hosted deployment would want a server-backed one. Configuration,
  not design.
- Whether the alias index is derived from the corpus alone or seeded with a hand-written list of
  common abbreviations. Derivation is cheaper; seeding is likely more accurate for what people
  actually type. Measurable once the evaluation set exists.
- Where to set the conversation bound. A number to tune once real sessions exist; it changes no
  interface.
