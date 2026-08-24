## Why

A database of biological numbers is only worth as much as people's ability to get answers out of
it. Structured queries require knowing the schema; researchers ask questions in prose, and the
useful ones are rarely a single lookup — "how does cell volume scale with growth rate across
bacteria" needs several searches, a comparison, and a judgment about which measurements are
comparable at all.

That shape is why this warrants an agent rather than a fixed query interface: **the question
determines the plan**, and the plan cannot be specified in advance. A one-shot lookup and an
open-ended comparison arrive through the same prompt.

Two properties of the corpus make the agentic approach pay off rather than merely sound modern:

- **Entries cross-reference each other.** Many carry pointers such as "See BNID 102065, 104333" in
  their comments, so answering well means deciding which neighbours are worth following and when to
  stop.
- **The corpus disagrees with itself.** Several entries report the same quantity with different
  values under different conditions. A useful answer reports that spread with its conditions rather
  than silently selecting one — which is also a preview of the contradiction detection the project
  wants later.

This capability sits at a different layer from the grounding validator (see
`add-grounding-validator`). That change produces trustworthy facts deterministically, because a
verdict must be auditable. This one consumes them conversationally, where open-ended behaviour is
the point. Agents belong at the interface; determinism belongs under the evidence.

Working against the existing curated corpus also exercises the data before anything depends on it,
and requires nothing from the validator — the two proceed in parallel.

## What Changes

- Introduce an agent that answers natural-language questions about quantities in a corpus, built on
  LangChain and LangGraph.
- **Separate the agent from the interface that drives it.** The agent emits events and accepts
  commands; it never reads input or writes output directly. A terminal driver comes first for
  testing and a web interface follows, and neither is privileged — the evaluation harness is simply
  a third driver.
- Introduce a bounded tool surface over the corpus: search by property, organism, and keyword;
  retrieve a full entry; discover the corpus's own vocabulary. The agent selects and sequences
  these; no fixed pipeline is imposed.
- **Every claim in an answer SHALL cite the entries it came from.** An answer that cannot be
  attributed to retrieved entries is a failure, not a fallback — the same evidence discipline the
  validator applies to papers, applied here to the corpus.
- **The agent answers only from the corpus.** Where the corpus does not cover a question, it says so
  rather than answering from the model's own knowledge. For a project whose premise is verifiable
  provenance, a plausible unsourced number is the worst possible output.
- Report disagreement rather than resolving it silently: when retrieved entries give different
  values for the same quantity, the answer presents the range with the conditions that distinguish
  them.
- **Support conversation within a session.** Follow-up questions inherit what came before, sessions
  are isolated from one another, and a session continues in a different process than the one that
  started it. Conversation growth is bounded, with the bound announced before it is reached rather
  than context being discarded silently.
- Introduce an evaluation harness: a held-out set of questions whose answering entries are known,
  scored on whether the agent cited them, recorded incrementally so an interrupted run resumes
  without repeating work. Evaluating a non-deterministic system is a first-class deliverable here,
  not an afterthought.
- **Enforce spend ceilings in code, not in the prompt.** An agent chooses its own number of steps, so
  cost is unbounded by construction unless something outside the model stops it. A per-question
  ceiling ends the question before it is crossed, and a run-level budget bounds a set of questions as
  a whole. Both are development-stage guards rather than the eventual mechanism.
- **Configure reliability middleware rather than writing it.** Retried model and tool calls, and
  tool errors surfaced to the agent instead of collapsing the run, come from built-in components. A
  transient gateway failure should not end a question, and in an evaluation it would waste a question
  slot and its spend.
- **Log the deterministic layer.** Tool calls, spend arithmetic, alias resolution, and truncation
  decisions are logged with a correlation identifier per question. Several failure modes here are
  silent rather than loud — an alias resolving to the wrong stored value, a truncated search treated
  as complete — and a non-deterministic agent reproduces them intermittently.
- **Build in stages, not at once.** A fixed prompt and a fixed tool list first; dynamic tool
  selection, dynamic prompts, and conversation condensation each arrive later as separate steps, with
  model calls, tokens, and latency monitored throughout.

Not in scope: writing to the corpus, retrieving literature or fetching papers (that belongs to the
validator's retrieval layer and to a future discovery capability), and web access of any kind.

## Capabilities

### New Capabilities
- `corpus-query`: A bounded, read-only tool surface over a corpus of quantities. Covers search by
  property, organism, and keyword; the deterministic index that resolves common naming variants to
  the corpus's own wording; vocabulary discovery; retrieval of a complete entry; and the
  cross-references an entry exposes.
- `grounded-answering`: Answer a natural-language question using only retrieved corpus entries,
  with citations. Covers the citation requirement, the refusal to answer beyond the corpus,
  dimensional compatibility before values are compared, how disagreement is reported, and how
  retrieval effort is bounded.
- `agent-session`: The boundary between the agent and whatever drives it. Covers the event and
  command contract, resumption of a suspended session in another process, isolation between
  sessions, conversational context within a session, and the bound on conversation growth.
- `spend-control`: Bound what questions may cost. Covers taking spend from what the provider reports,
  the pre-request gate, the per-question ceiling and the run budget, what a question ended on a
  ceiling still reports, persistence of spend state, and price configuration as a fallback.
- `answer-evaluation`: Score answers against a held-out question set with known answering entries.
  Covers the question set, citation-based scoring, unsupported questions, run-to-run variation,
  incremental recording and resumption, and a record shape external evaluation tooling can read.

### Modified Capabilities
<!-- None. -->

## Deferred

Recorded so the reasoning survives, and so these are not rediscovered from scratch. None is built
here.

- **User accounts and tiers.** Nothing in the MVP distinguishes users. The design keeps spend
  accounting keyed rather than global, so adding a user dimension later is a change of key rather
  than a redesign. Long-term, cross-session memory becomes worth revisiting at the same time —
  preferences and query history only mean something once there is a user to attach them to.
- **Guardrails against misuse and prompt injection.** `grounded-answering` already supplies part of
  this structurally: an agent restricted to a read-only corpus, required to cite, and required to
  refuse beyond its sources has refusal as its failure mode rather than compliance. The residual
  risk is injection through corpus text, since entry comments are free text that reaches the model,
  and that deserves its own change.
- **Observability tooling.** Adopting LangSmith or Langfuse is configuration rather than a rewrite,
  given LangChain. What is not free later is meaningful naming: nodes and runs are named and tagged
  now so that traces are worth reading when tracing is switched on.
- **Alerting on cost drift.** Total spend rising is growth; cost per question rising on flat traffic
  after a change is a regression that was shipped, and only the second is worth waking up for.
  Detecting it needs a baseline — per-question cost across repeated runs of the same question set —
  which `answer-evaluation` produces but nothing yet compares between runs. The comparison belongs
  with the observability tooling above rather than inside the agent. What is not free later is the
  tagging: an alert computed over a total that mixes evaluation runs with hand-driven use fires on the
  mix rather than on a regression, so the run label and the per-increment model are in place now.
  **Raise this again once the same question set has been run more than once and a baseline exists** —
  that is task 9.8's output, not a date.
- **External evaluation frameworks.** Ragas, DeepEval, and similar tools consume a question, an
  answer, retrieved context, and an expected result. `answer-evaluation` records exactly that shape,
  so adopting one later is a reading exercise rather than a re-run.

  These frameworks score with an LLM judge, which is a materially weaker instrument than the
  identifier comparison specified here. Reported measurements of frontier judges find verdicts
  flipping in roughly a quarter to two thirds of cases under simple pushback, and the great majority
  of the time against an adversarial persuader, with the flips tending to corrupt rather than
  correct. The strong figures concern conversational scorers, so they bound how far to trust a judge
  rather than condemning the approach. Adoption should therefore be gated on agreement with the
  deterministic scoring already in place — a correlation floor against a golden set — rather than
  assumed after it. Position rotation and decomposed rubrics are the cheap mitigations. Surfaced by
  the GenAI scouting scheme via AI News, issue 2026-08-14, reporting Meta's "Jagged Judges" /
  Wiggle Framework work with earlier independent corroboration.

  Note the ordering this implies: the deterministic harness is the reference against which any judge
  is validated, so it must exist and be trusted first.
- **Interfaces beyond the first two.** The event and command contract exists so that a further
  interface is a new driver. Nothing in the agent should need to change for one. Streamlit is the
  current web framework by course requirement, not a commitment.
- **Capping tool calls per question.** A built-in exists for this, and retrieval effort is bounded by
  the model-call limit in the MVP. Capping *tool* calls specifically had unexpected consequences in
  the `interv_preper` project — before adopting it here, read that project's experience of what went
  wrong, starting from its ADR on the agent loop. Read it for the failure modes rather than the
  remedies; how it was resolved there may be specific to that implementation.
- **What a property actually measures.** Two distinct problems, both real in this corpus and neither
  addressed here.

  *A property name can cover several quantities.* 193 entries mention "density" in their property,
  spanning mass density (`g/cm^3`), linear gene density (`genes/kb`), areal counts (`NPC/μm^2`,
  `stomata/mm^2`) and more. 136 property strings appear under more than one unit, and those divide
  further: `genome size` in `Base pairs` and `Gbp` is one quantity in two scales, whereas
  `mutation rate` as `1/genome/generation` and as `mutation/hour` are different quantities, and
  `generation time` appears as both `Hours` and `Hour^-1` — reciprocals of each other. The dimensional
  compatibility already required prevents these being averaged or presented as a range, which is the
  arithmetic error. It does **not** prevent answering the wrong sense of the question with a correct
  citation, which is the subtler failure and is not currently guarded against.

  *A measure may be uncommon, or defined by the paper itself.* Here the value is right and the reader
  still cannot use it, because the metric means nothing outside its source. The model must not explain
  such a measure from its own knowledge — that is exactly the unsourced answer this project exists to
  avoid — so the answer has to point at where the measure is defined rather than paraphrase it.

  Two things bear on how this gets built. The corpus already carries part of the material: 50% of
  entries have a `measurement_method`, often a verbatim quotation with a page pointer, which
  `get_entry` already returns but nothing instructs the agent to use for disambiguation. That is the
  cheapest first step and belongs here. The rest — locating where a measure is *defined* in the source
  paper — is the grounding validator's machinery pointed at a different target: it already locates a
  claimed value in a document and returns a citable span, and a definition is the same kind of span.
  That belongs to a follow-up on `add-grounding-validator` rather than to either change as scoped.
- **Latency monitoring.** The phased approach calls for watching calls, tokens, and latency. Calls and
  tokens are covered; latency is not measured in the MVP. When it is, the quantities worth recording
  are wall time per question, duration per tool call, and time from question to first emitted event —
  the last being what a user actually experiences as responsiveness. Deferred rather than dropped, so
  the gap is deliberate.
- **Suspending a question for approval.** Reaching a spend ceiling ends the question here. Suspending
  mid-question and resuming on the user's approval is the better behaviour and the framework supports
  it directly, but it is not needed to bound cost — ending the question bounds it just as well — so it
  is left out of the first build. Note the distinction that makes this safe to defer: the checkpointer
  is **not** deferred, because conversation across turns in a web interface depends on it. Only the
  suspend-and-approve flow is.
- **Condensing the conversation.** The MVP bounds conversation growth and refuses further questions
  once the bound is reached. Automatic summarisation is the better answer and is available as
  configuration, but a summariser that drops the entry a later answer depended on yields a confident
  answer with a missing citation — the exact failure this project exists to prevent. Several schemes
  should be compared on the evaluation set before one is trusted. **Raise this again once the MVP is
  merged.**
- **Moving spend enforcement out of the application.** The code-enforced ceilings are a stopgap
  suited to development, when a runaway agent spends the developer's own money. The durable answers
  are a provider-side cap on the key itself, or users supplying their own key with a cap of their
  own choosing. Both remove the application from the trust path for spending.

## Impact

- **New code**: this worktree contains only the `uv` scaffold. Everything is greenfield.
- **External dependencies**: LangChain and LangGraph, an OpenAI-compatible model client pointed at
  OpenRouter, and a web application framework for the second driver. LangGraph's checkpointing is
  load-bearing, since conversation across turns rests on it.
- **Models**: reached through OpenRouter rather than a provider directly. Development runs on an
  inexpensive, strong instruction-follower, because the design depends on the agent obeying the
  citation and refusal requirements rather than on raw capability; a more capable model is a
  configuration change once the harness is proved. The model in force is recorded on every answer and
  every evaluation result, so a change of model cannot be mistaken for a change in quality.
- **Cost reporting**: OpenRouter reports the cost of each request, so spend is read from the provider
  rather than computed from a local price table. A price table remains a fallback for providers that
  report only token counts.
- **Framework version sensitivity**: LangChain v1 changed the recommended agent entry point, and the
  prebuilt agent constructor most existing material shows is deprecated. The design pins what is
  used and the implementation verifies it against the installed version rather than against
  documentation.
- **Credentials**: the model API key is read from the environment, never committed. See
  `CLAUDE.md`, "Never commit secrets".
- **Shared concern with `add-grounding-validator`**: both changes consume a corpus of the same
  entries, and both treat it as a swappable external input that must not be committed. They are
  developed on separate branches and will each define their own loader; whether to unify them is a
  question for whichever merges second, and should not be pre-emptively coupled now.
- **Evaluation cost**: every run makes model calls. At the default settings a run is bounded at USD
  1.20, and two questions running to the per-question ceiling would exhaust it — a deliberate
  circuit breaker, which the report must distinguish from a completed run.
- **Cost model accuracy**: spend is priced from the token usage each response reports, so per-token
  prices become configuration that has to be kept current. A stale price table produces a ceiling
  that does not mean what it says.
- **Web framework**: Streamlit, as a course requirement. Treated as replaceable — no requirement
  names it, and changing it means writing another driver rather than touching the agent.
- **Documentation**: `README.md` is still empty. `docs/diagrams/DIAGRAMS.md` and `CHANGELOG.md` are
  provided on `dev`, so this change extends them rather than creating them.
