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
- [x] 2.4 Carry a run label from configuration on every record and every framework run, so an evaluation run's spend is separable from hand-driven use — it is a label for the run, not a name for the caller, which the agent is required not to have
- [x] 2.5 Record the model on every spend increment, so a trail spanning a model change can be split by model without joining each record back to its ending event

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

- [x] 5.1 Implement the spend ledger, reading provider-reported cost where present and falling back to configured prices, in integer minor units
- [x] 5.2 Refuse to start when a model reports no cost and has no configured prices
- [x] 5.3 Implement the spend gate as a `wrap_model_call` middleware that declines to call the handler once the ceiling is reached
- [x] 5.4 End the question at the ceiling, presenting what was established with citations and marked incomplete
- [x] 5.5 Persist accumulated spend and the ceiling in session state, and test that spend continues rather than resetting when a session is continued
- [x] 5.6 Emit the warning when spend passes the threshold, without ending the question
- [x] 5.10 Test that a second question in a session starts with a fresh per-question ceiling while run spend keeps accumulating
- [x] 5.7 Implement the run budget across questions, stopping the run when it is reached
- [x] 5.8 Implement the pre-flight projection that flags an expensive question before work begins, and test that it never affects where work stops
- [x] 5.9 Report spend and the model with every answer
- [x] 5.11 Stress the limits against the real provider, at the smallest limits that mean anything: count requests at the provider boundary so a refusal is proven to be a request that never left rather than an ending reason; hold the overshoot past a ceiling to one request, measured from the recorded charges; and price one response with no fallback table configured, since the provider's reported cost and the table's figure are numerically identical and every other test would survive the field being renamed. About $0.01 a run, bounded twice -- by each configuration's own run budget and by a module cap read from the run ledger

## 6. Answering behaviour

- [x] 6.1 Implement the answer format carrying a citation for every quantity, in one stated form, and a single parser that requires the marker rather than inferring a citation from a bare number — used by every driver and by the evaluation harness, so they agree on what was cited
- [x] 6.1a Record the identifiers a search returned, so a citation can be checked against what the agent was shown and a driver can present the entries without re-running the search
- [x] 6.1b Check that every cited identifier exists and was returned by a tool call during that question, and report one that was not rather than accepting it
- [x] 6.1c Build the entries table an answer is presented with — property, organism, value, units, identifier, reference — cited entries first, stating how many were retrieved when more were retrieved than are shown. Shared by the drivers; the reference is looked up for display and never sent to the model, since carrying it into search results would more than double what a search costs
- [x] 6.1d Present a stored single measurement as one number where the corpus holds it as a range with equal bounds, and drop the matched figure from the count line when every match was retrieved
- [x] 6.1e Order the entries an answer did not cite by wording overlap with the question and the cited properties, discounting words the property repeats from its organism; separate them from the cited entries visibly, and mark an entry whose measurement method the corpus does not record
- [x] 6.2 Establish dimensional compatibility before presenting two entries as differing estimates, and test it against a mass-versus-count pair. Three-valued, so a unit nobody classified is never claimed compatible and never mistaken for dimensionless — 2,305 distinct unit strings make complete classification permanently unavailable, and the table covers 45% of the corpus's entries
- [x] 6.2a Say it where the decision is made: a search result spanning more than one dimension names the kinds it carries, and the entries table footnotes the same over every cited entry
- [x] 6.2b Never break a number across two lines — the value column split "6800.0-72000.0" into a figure the corpus does not hold, shown with no sign it had been altered
- [x] 6.3 Report disagreement with the conditions that distinguish the values -- show each cited entry's recorded measurement method, so a reader can check the prose's account of what separates two numbers instead of taking it on trust; marking only a method's absence left a textbook page and a count over a thousand cells looking identical. Live-tested against the fixture's two `Cell diameter` entries, 1.0-1.1 um and 5.0 um, which differ by organism alone
- [x] 6.4 Mark computed values as computed and cite every input -- live-tested on the case that prompted the rule, a unit conversion, whose arithmetic is trivially correct and which therefore reads as a stored measurement unless it says otherwise; and on a computation whose input the corpus does not hold, which must not be presented at all. Programmatic marking of numbers matching no entry is deferred to the post-MVP middleware, so this rests on the prompt and is verified rather than enforced
- [x] 6.5 Bound retrieval effort per question using the built-in call-limit middleware, and report when an answer was produced against that bound — the count read from the middleware's own state so a retried call counts once, reported only where the bound was reached
- [x] 6.5a Present what a question established before the bound stopped it, as the spend ceiling already did — the bound was discarding a partial answer and its citations
- [x] 6.6 Test that a question the corpus does not cover produces a statement to that effect and no quantity, offline for the harness and live for the model
- [x] 6.6a Run the citation check whether or not anything was retrieved, and mark an entry cited without being retrieved where it is shown — an answer that cited an entry after an empty search was reported as clean
- [x] 6.6b Parse the plural citation marker, so "BNIDs 100002" is not read as an uncited answer
- [x] 6.6c Read a run of identifiers introduced by one marker, with one parser shared by the corpus text and the answers — two existed and had already drifted, and the corpus-side one hardcoded identifiers as six digits beginning with 1
- [x] 2.1a Point the structured trail at a file from the driver, since nothing outside the tests configured it and every record a real run produced was discarded
- [x] 2.1b Read a provider-reported cost of zero as a cost, not as an absent one
- [x] 5.6a Exit non-zero from the terminal driver when a question did not finish, not only on a configuration error
- [x] 5.6b Key accumulated run spend to the run rather than to the session, recorded as each charge is made, so a driver opening a session per question is still bounded by the run budget

## 7. Terminal driver

- [x] 7.1 Implement the terminal driver: render events, accept questions as commands
- [x] 7.2 Verify end to end against the corpus that a question is answered with citations
- [x] 7.3 Verify that the driver holds no agent state of its own beyond the session identifier
- [x] 7.4 Render the entries table after each answer, the first five entries only, in the column order and relative widths of the reference database's results page — two text lines per row, cells wrapped then truncated — so output can be compared against it by eye

## 8. Web interface

- [x] 8.1 Implement the web driver, holding the session identifier in framework session state across re-runs
- [x] 8.2 Hold the corpus index and alias index in a resource cache that survives re-runs, and verify they are built once rather than per interaction
- [x] 8.3 Render retrieval progress from events while a question is being answered -- and every warning with it, which the page had been dropping silently
- [x] 8.4 Verify that a follow-up question is answered correctly after the application has been restarted mid-session (needed the identifier published to the URL: session state dies with the server, the checkpoint it points at does not)
- [x] 8.5 Verify that the agent code is unchanged from the terminal driver's version -- asserted over the source as an import direction, so it stays answered rather than being answered once
- [x] 8.6 Render the entries table after each answer, the first ten to twenty entries with a way to reach the rest, and make a row open the full entry. Separate the cited entries from the uncited ones as the terminal already does -- the separation is the requirement, its visual form (colour, a divider, a heading) is decided when the table is built -- and carry the no-recorded-method marking through
- [x] 8.7 Mark the two range flags the ingester reports, beside the existing no-recorded-method
      marking, and send both booleans to the model on a retrieved entry -- the prose is what people
      read, and a model that does not know will state a hedged or fused range as a measurement while
      only the table contradicts it. Shown, never hidden and never repaired, and still citable: a
      citation claims provenance, which stays true of a marked entry.
      **Unblocked as of 2026-08-28**: a corpus emitting both fields exists, 14,294 records, and this
      project's whole offline suite passes against it.
  - `range_qualified` (2,233 records) -- the source never claimed an interval. `<0.001` was stored as
    the closed interval [0.001, 0.001], `>100` as [100, 100], `~5` as [5, 5]. This is the more urgent
    of the two and the larger population: nothing about the rendering looks wrong, and *less than*
    reaching a reader as *equal to* is a misreading the table itself creates.
  - `range_fused` (1,461 records) -- the bounds may come from two different quantities.
  - **Two marks and two footnote sentences, not one of each.** A record can carry either without the
    other, and "the source states a bound, not a range" is not "these bounds may belong to two
    different quantities". The ingester kept them as separate booleans for exactly this reason rather
    than widening a term this project already reads.
  - Check both marks can fire against a real corpus, per `tests/test_markers_against_corpus.py`.
- [x] 8.8 Mark a range whose bounds span implausibly far apart, and say in the legend what the mark
      means. Not blocked and not the ingester's to fix: `range_fused` claims only that two bounds may
      come from different quantities, so a range parsed exactly as written stays unmarked however wide
      it is. 47 entries span more than a millionfold; `range_fused` marks 42, and the remaining five
      are genuine two-number cells -- `0.25-2.5e30`, `1-2×10^9`, `10^-5 to 10^-12` -- one of which
      renders as `0.25–2.5e+30 cells` with nothing beside it. Plausibility is a presentation
      judgement and the ingester deliberately does not judge ranges (its ADR-0230), so the span ratio
      and the threshold belong here.
      Own the threshold explicitly: it is a number this project chose, so record why in the ADR and
      test both sides of it. And check the mark can fire -- `tests/test_markers_against_corpus.py`
      exists because a marker whose condition never holds passes every test and draws nothing.

- [x] 8.9 Bound tool calls per question, as model calls are already bounded. Observed live: one
      question made **29 tool calls across 17 searches**, spent **$0.27**, and took the run from
      $0.91 to $1.18 of its $1.20 budget -- a single question consuming a fifth of a run. The model
      call limit did not bind it: a model may batch several tool calls into one hop, so 12 model
      calls bought 29 retrievals. The spend ceiling is the only thing that stopped it, which makes
      cost the sole brake on a search loop and reports the symptom rather than the cause.
      **This is a conformance gap, not a new requirement.** `grounded-answering`, *Retrieval effort is
      bounded and reported*, already says the system SHALL bound "the number of tool calls made in
      answering a single question". The code bounds model calls and `at_retrieval_bound` reports
      those, so the spec and the implementation have been describing different quantities. Bound and
      report the one the spec names, keeping the model-call limit as well.
- [x] 8.10 Refuse only after searching, and never claim searches that did not happen. Observed live:
      an unanswerable question ended `answered · 0 tool calls` with prose reading "based on my
      searches through the available data" and "I would need to search the corpus". No search ran.
      Two separate defects, and the second is the serious one:
  - A refusal with no retrieval is not grounded in the corpus. It is the model's prior about what
    the corpus contains, which is exactly what this project exists not to rely on -- and a false
    negative is invisible, because the reader cannot tell "not in the corpus" from "not looked for".
  - The prose asserted a process that did not occur. `tool_calls` on the ending contradicted it, so
    the harness had the truth and the answer the reader sees did not.
      Fix the first (require at least one search before a no-answer ending) and detect the second:
      the ending already carries `tool_calls`, so an answer claiming to have searched when the count
      is zero is checkable without a judge. Consider whether this is a `CitationWarning` sibling.

## 9. Evaluation

Moved, with its spec, to the change `add-answer-evaluation` on 2026-09-03: this change had
everything else complete and could not archive while group 9 sat unbuilt inside it, and
`rename-to-scinumbers` modifies this change's specs and could not archive until it did. The tasks
carry over with their notes, renumbered as that change's groups 2–5; the ADR numbering note in
group 10 below no longer applies to them, since that change has its own block.

## 10. Documentation

ADR numbers for this change are allocated `0100`–`0190` by the table in `CLAUDE.md`, which is the
authority; this note is a convenience for whoever is implementing and must be reconciled against it.
`0100`–`0190` are written, and the block was extended in `CLAUDE.md` with `0260`–`0290` when it
ran out mid-change; `0260` and `0270` are spent on tasks 8.9 and 8.10, so group 9 starts at `0280`. Widen in
`CLAUDE.md` first if group 9 owes more than one -- widening here and nowhere else is what let this
block drift past `0150` unnoticed. **ADRs are written with the decision, not collected here at
the end** -- the four below were already retroactive when they were written, which is the
practice this note exists to stop repeating.

- [x] 10.1a Write a reviewer-facing `README.md` covering the ask agent only: what it does, the corpus and
      why it is not committed, how to run each driver, configuration, and what is not built yet
- [x] 10.1 Extend `README.md` with how to run an evaluation. **Moved with group 9** to
      `add-answer-evaluation` (its task 7.1); everything else this task asked for is covered by 10.1a,
      and documenting a way to run something that does not exist is the one part that cannot be
      written honestly yet
- [x] 10.2 Add a diagram of the agent, its middleware, and the drivers to `docs/diagrams/`, following the principles already in `docs/diagrams/DIAGRAMS.md`
- [x] 10.2a ADR-0100: the web driver decides in items and draws from them, since Streamlit
      composes successive writes to one screen location into the last of them (written with 8.1)
- [x] 10.3 ADR-0110: the agent is separated from its drivers by an event port
- [x] 10.4 ADR-0120: spend is enforced in middleware, not asked for in the prompt -- an interim guard, not a billing control
- [x] 10.5 ADR-0130: a deterministic alias index, not long-term agent memory
- [x] 10.6 ADR-0140: conversation is bounded by refusal, not by condensing
- [x] 10.6a ADR-0150: retrieval is two-tier -- capped summaries with an honest total, then bodies (owed by group 3)
- [x] 10.6b ADR-0160: unit compatibility is three-valued, because 2,305 distinct unit strings make complete
      classification permanently unavailable (owed by 6.2)
- [x] 10.6c ADR-0170: the corpus stays outside every repository, and the three consequences that follow
      -- the six-entry fixture, the entry-text-free trail, the defects file kept beside the corpus (owed by group 1)
- [x] 10.7 Add the agent's entries under `## [Unreleased]` in the existing `CHANGELOG.md`
- [ ] 10.9 Finish the requirement-to-test mapping in `tests/test_spec_conformance.py`. 10 of 49
      requirements name the tests that assert them; 39 are recorded as gaps -- 10 of those are
      group 9's and moved with it to `add-answer-evaluation`, and 29 are tested by something whose
      name nobody has written down. The check already refuses a requirement that is neither mapped
      nor listed, so the list can only shrink deliberately. Work through it a capability at a time;
      the reward is not the number but the reading: putting a requirement's words beside the test
      that claims them is where a mismatch like 8.9's becomes visible.
- [x] 10.8 Update the Architecture section of `CLAUDE.md` to describe the module layout and name the patterns used


## 11. Limits, said where they bind

Taken **after group 8 and before group 9**, because the evaluation harness records what a question
consumed and against which limit, and would otherwise record the shape being replaced here. All
three follow from [ADR-0180](../../../docs/decisions/0180-limits-named-where-they-bind.md), written
with the decision rather than after it.

- [x] 11.1 Configure the per-question spend **ceiling** and derive the warning from it at 80 per cent,
      instead of configuring the warning and deriving the ceiling at 120 per cent -- the configured
      number should be the one that stops work, and this is what `CONVERSATION_BOUND` /
      `CONVERSATION_WARN_AT` already do
- [x] 11.2 Reject `BIONUMBERS_ASK_WARN_USD` with a message naming its replacement, rather than
      accepting it under the new meaning: carried over unchanged it would silently tighten the hard
      limit to 80 per cent of what it used to permit
- [x] 11.3 Bound the conversation by its token count rather than its message count, read from the
      provider's reported `prompt_tokens`, which is the size of what was actually sent. Sixty messages
      is between a few thousand tokens and over a hundred thousand: measured over the corpus, one
      retrieved entry's payload spans 16 to 8,023 characters, p50 557 and p99 2,353
- [x] 11.4 Report an answered question that reached its spend ceiling as distinct from one that
      finished with room to spare, the way `at_retrieval_bound` already does for model calls -- the
      gate checks before each call and cannot check after, so an overshoot of up to one call is
      inherent and currently invisible
- [x] 11.5a Check every marker can fire against a real corpus, as a `corpus`-marked test rather
      than a remembered practice -- a flag whose condition cannot hold passes every test, draws
      nothing, and reports a zero that reads as a fact about the world
- [x] 11.5 Update `README.md`'s configuration table, and the `openspec/specs/spend-control` deltas,
      for the renamed key and the three reporting states
