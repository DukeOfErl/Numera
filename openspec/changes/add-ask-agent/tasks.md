## 1. Scaffolding and framework verification

- [x] 1.1 Create the `bionumbers_ask` package under `src/` with `uv` entry points, and add dependencies: `langchain` (>=1.1), `langgraph`, an OpenAI-compatible client for OpenRouter, a web application framework, and `pytest`
- [x] 1.2 Read the framework's built-in middleware list before writing any custom hook, and record which built-ins cover which requirements here
- [x] 1.3 Verify against the installed versions which agent constructor is current and what the middleware hook signatures are — do not rely on documentation or tutorials for this
- [x] 1.4 Write a spike that compiles an agent with a file-backed checkpointer, completes a turn, exits the process, and continues the same session by its thread identifier in a new process
- [x] 1.5 Turn that spike into a test, since conversation across turns in the web interface depends on the behaviour it proves
- [x] 1.6 Add configuration for the model, the per-question warning threshold, the run budget, and a fallback price table, selectable per run
- [x] 1.7 Confirm that OpenRouter reports per-request cost for the configured models, and whether it must be enabled per request
- [x] 1.8 Add `.gitignore` entries for the corpus directory, the checkpoint store, logs, and evaluation results

## 2. Logging

- [x] 2.1 Add structured logging with a correlation identifier assigned per question and carried through every record for that question
- [x] 2.2 Name graph nodes and runs meaningfully, so traces are readable if tracing is switched on later
- [x] 2.3 Verify a question produces a coherent, readable trail from first tool call to answer, that a truncated search records both figures, and that two questions in one session carry different identifiers

## 3. Corpus and query tools

- [x] 3.1 Define the corpus record shape and a loader that reads JSONL from a supplied path, failing with an explanatory message when none is supplied
- [x] 3.2 Build the search index over property, organism, and keywords, matching case-insensitively on substrings
- [x] 3.3 Build the alias index from the corpus at load time, mapping common naming variants to stored values, and make it inspectable
- [x] 3.4 Implement search returning capped compact rows plus the total match count, logging what matched and what was truncated
- [x] 3.5 Implement vocabulary discovery: list stored organism and property values matching a partial term, with entry counts
- [x] 3.6 Implement single-entry retrieval, parsing cited entry identifiers out of the entry's text into a list
- [x] 3.7 Test that no tool can create, modify, or delete a corpus entry
- [x] 3.8 Test the case that motivated the two-tier design: a search matching over a thousand entries returns a bounded payload and an honest total

## 4. Agent — static prompt, fixed tools

- [x] 4.1 Define the event types the agent emits and the commands it accepts
- [x] 4.2 Wrap the corpus tools for the agent, with descriptions stating when each should be used
- [x] 4.3 Build the agent with the verified constructor, a static system prompt carrying the answering rules, and a fixed tool list
- [x] 4.4 Attach the file-backed checkpointer and map a session identifier to a thread identifier
- [x] 4.5 Emit retrieval events as they happen, so a driver can show progress before the answer exists, and an ending event naming why a question ended and what it consumed
- [x] 4.6 Test that two concurrent sessions share no conversation, no retrieved entries, and no spend
- [x] 4.7 Test that a follow-up question inherits context within a session and does not across sessions
- [x] 4.8 Configure reliability middleware: retried model calls with backoff, retried tool calls, and tool errors returned to the agent rather than ending the run
- [x] 4.9 Test that a transient provider failure is retried and the question continues, and that exhausted retries end the question as a provider failure rather than an answer
- [x] 4.10 Test that the same question through an attended and an unattended driver emits the same events, and that the agent takes no parameter naming its caller
- [x] 4.11 Assert the prompt requires follow-up answers to cite in full; the behavioural check moves to 9.x, since whether the model complies is only measurable by scoring answers
- [x] 4.12 Bound conversation growth: warn as the bound is approached, refuse further questions once reached, and never discard context silently

## 5. Spend control

- [ ] 5.1 Implement the spend ledger, reading provider-reported cost where present and falling back to configured prices, in integer minor units
- [ ] 5.2 Refuse to start when a model reports no cost and has no configured prices
- [ ] 5.3 Implement the spend gate as a `wrap_model_call` middleware that declines to call the handler once the ceiling is reached
- [ ] 5.4 End the question at the ceiling, presenting what was established with citations and marked incomplete
- [ ] 5.5 Persist accumulated spend and the ceiling in session state, and test that spend continues rather than resetting when a session is continued
- [ ] 5.6 Emit the warning when spend passes the threshold, without ending the question
- [ ] 5.10 Test that a second question in a session starts with a fresh per-question ceiling while run spend keeps accumulating
- [ ] 5.7 Implement the run budget across questions, stopping the run when it is reached
- [ ] 5.8 Implement the pre-flight projection that flags an expensive question before work begins, and test that it never affects where work stops
- [ ] 5.9 Report spend and the model with every answer

## 6. Answering behaviour

- [ ] 6.1 Implement the answer format carrying a citation for every quantity
- [ ] 6.2 Establish dimensional compatibility before presenting two entries as differing estimates, and test it against a mass-versus-count pair
- [ ] 6.3 Report disagreement with the conditions that distinguish the values
- [ ] 6.4 Mark computed values as computed and cite every input
- [ ] 6.5 Bound retrieval effort per question using the built-in call-limit middleware, and report when an answer was produced against that bound
- [ ] 6.6 Test that a question the corpus does not cover produces a statement to that effect and no quantity

## 7. Terminal driver

- [ ] 7.1 Implement the terminal driver: render events, accept questions as commands
- [ ] 7.2 Verify end to end against the corpus that a question is answered with citations
- [ ] 7.3 Verify that the driver holds no agent state of its own beyond the session identifier

## 8. Web interface

- [ ] 8.1 Implement the web driver, holding the session identifier in framework session state across re-runs
- [ ] 8.2 Hold the corpus index and alias index in a resource cache that survives re-runs, and verify they are built once rather than per interaction
- [ ] 8.3 Render retrieval progress from events while a question is being answered
- [ ] 8.4 Verify that a follow-up question is answered correctly after the application has been restarted mid-session
- [ ] 8.5 Verify that the agent code is unchanged from the terminal driver's version

## 9. Evaluation

- [ ] 9.1 Read up before building: LangGraph persistence and store semantics, and the LangSmith evaluation documentation — both post-date the design and may replace parts of what follows
- [ ] 9.2 Define the question set format, including questions the corpus cannot answer, and require one to be supplied
- [ ] 9.3 Implement the evaluation driver, recording outcomes from emitted events
- [ ] 9.4 Score by comparing cited entries against expected entries, reporting unexpected citations separately
- [ ] 9.5 Score refusals on unsupported questions, and report a quantity given for one as a fabrication
- [ ] 9.5b Include follow-up questions in the set, and score whether their answers cite in full rather than referring back to an earlier answer
- [ ] 9.6 Append each result as its question completes, carrying the question, answer, cited entries, expected entries, and model, in a shape external evaluation tooling can read
- [ ] 9.7 Implement resumption against an existing results file, attempting only what is missing
- [ ] 9.8 Support repeated runs of each question and report the variation across them
- [ ] 9.9 Produce the report from the results file, stating coverage when partial, breaking figures down per model, and distinguishing a run stopped on budget from a completed one
- [ ] 9.10 Report cost and tool calls per question and in aggregate, and separate spend in this session from total spend across a resumed run
- [ ] 9.11 Assemble a first question set from the corpus and record a baseline on the development model

## 10. Documentation

ADR numbers for this change are allocated `0100`–`0150`; `add-grounding-validator` holds `0040`–`0090`.

- [ ] 10.1 Write `README.md`: what the agent does, how to supply a corpus, how to run each driver, how to configure the model and limits, and how to run an evaluation
- [ ] 10.2 Add a diagram of the agent, its middleware, and the drivers to `docs/diagrams/`, following the principles already in `docs/diagrams/DIAGRAMS.md`
- [ ] 10.3 Record an ADR for separating the agent from its drivers (ports and adapters), and what it buys
- [ ] 10.4 Record an ADR for enforcing spend in middleware rather than in the prompt, and why it is an interim mechanism
- [ ] 10.5 Record an ADR for the deterministic alias index in place of long-term agent memory
- [ ] 10.6 Record an ADR for bounding conversation by refusal rather than condensing it, and what would change that
- [ ] 10.7 Add the agent's entries under `## [Unreleased]` in the existing `CHANGELOG.md`
- [ ] 10.8 Update the Architecture section of `CLAUDE.md` to describe the module layout and name the patterns used
