# Tasks

**ADR block: `1000`–`1040`.** Numbers up to `0940` are already spent across branches
(`add-open-enrolment` holds `0880`–`0920`, and `0930`/`0940` exist on another branch), so this block
starts clear of all of them. Add the row to CLAUDE.md's table first; that table is the authority.
Planned: `1000` Langfuse Cloud EU over LangSmith (and the amendment to ADR-0750's copy detail);
`1010` tracing is a project setting, and vendor switches are refused in the operation; `1020`
attribution is an opaque digest attached by the driver.

**Where silent failure lives in this change.** A wrong setting reads like "tracing is off", which is
also the correct state. A LangSmith refusal that stopped working looks exactly like one that works,
until data has already left. An attribution that failed to propagate looks like an unattributed
reader. These three are where testing effort goes. Rendering, and the wording of the operator
message, get ordinary tests.

**Every test of the gate asserts both directions** (the negative-case rule in
`.claude/rules/testing.md`). For each "nothing is sent" test there is a paired test with the one
dimension changed that shows something *is* sent. Without the pair, a double that never records
anything passes every refusal test.

**No test talks to Langfuse or LangSmith over the network.** The doubles are the SDKs' own seams: a
recording handler or exporter, and a stubbed client. Task 5.2 is the one live check, done by hand and
recorded.

## 1. Decisions, and the installed APIs they rest on

- [x] 1.1 CLAUDE.md: add `add-hosted-tracing` → `1000`–`1040` to the ADR table. Create stubs for
      `1000`, `1010` and `1020`, and commit them before anything else.
- [x] 1.2 `uv add --optional ask "langfuse>=4.15,<5"`, then read the **installed** 4.x source and docs
      for each of the following. For the docs, use the Langfuse skill's method: any page as `….md`,
      `langfuse.com/llms.txt` as the index, and `langfuse.com/api/search-docs?query=` for search. All
      three are free and need no key. Record the version and the answer in the design's D-sections (not in
      a chat), and correct the design wherever it guessed:
      (a) the host variable's name (`LANGFUSE_BASE_URL` or `LANGFUSE_HOST`);
      (b) how a `CallbackHandler`'s run is bound to a given trace id;
      (c) the `propagate_attributes` signature, and whether it is contextvar-based;
      (d) `create_score`'s id, upsert and comment-length behaviour;
      (e) whether the handler sets `raise_error`;
      (f) whether the SDK registers its own `atexit` flush;
      (g) whether constructing the client touches OpenTelemetry's global provider;
      (h) for D9: how the installed SDK or API counts traces, observations and scores over a time
      window, and whether anything first-party says how Hobby's billing month is anchored. The skill's
      `cli.md` says the `traces` endpoints are outdated on the v4 platform ("always query via
      observations"), so count traces through observations or metrics (for example, distinct trace
      ids), not through the traces list;
      (i) for D5: whether `session_id` should also go through `propagate_attributes`, set before the
      first observation, so every child observation carries it (the skill's v4 migration note says so).
- [x] 1.3 A throwaway probe, not a test and not committed: with `LANGSMITH_TRACING=true` and the
      installed `langsmith` 0.11.0 / `langchain-core` 1.5.6, does `tracing_context(enabled=False)`
      around a lazily consumed `agent.stream` stop LangChain attaching its LangSmith tracer, including
      on LangGraph's worker threads? Record the result in D3. If it does not, the fallback in D3
      becomes the design before group 2 starts.
- [x] 1.4 The Langfuse agent skill (`github.com/langfuse/skills`, read at `b8cc05c` on 2026-09-24):
      the user installs it at user level. `~/.claude/skills` is read-only to the agent's sandbox, and
      the skill is untracked there until the claude-config `.gitignore` whitelists it. Until then,
      follow its documented method directly (1.2, 5.2).

## 2. The setting and the refusal — `hosted_trace.py`

- [x] 2.1 Tests first, from the spec's first requirement. Setting absent / empty / `off` → off; `langfuse`
      with all credentials → on; `langfuse` with each credential missing in turn → off, and the report
      names that credential; an unrecognised value → off, and the report names the value; Langfuse keys
      present with the setting absent → off. Pair each off case with the on case that differs in one
      dimension.
- [x] 2.2 Implement reading the setting through `config.env_setting`. `langfuse` must not be imported
      unless the setting is on. Assert that by checking `sys.modules` in a subprocess, not by reading
      the source.
- [x] 2.3 Tests: with `LANGSMITH_TRACING=true` (and, separately, `LANGCHAIN_TRACING_V2=true`), a
      question asked through `AskAgent` with a model double sends no run to any LangSmith tracer. Once
      with the project setting off, once with it on. Paired with a control showing that the same
      harness *does* see a LangSmith run when the refusal is removed (in a copy, per the fault-seeding
      skill), or the test proves nothing.
- [x] 2.4 Implement the refusal inside `hosted_trace` and use it at the `agent.stream` call in
      `agent.py`. Report to the operator once per process when the vendor switch is set.
- [x] 2.5 Add `hosted_trace` to the identity-free set in `tests/test_driver_independence.py`, and to
      the core side.

## 3. One question, one trace — and who asked

- [x] 3.1 Tests: with tracing on and a recording double in place of the export, one question produces
      one trace whose id equals `create_trace_id(seed=question_id)`, carrying `question_id`, the session
      and the run label. Two questions in one session produce two ids and share a session.
- [x] 3.2 Implement the handler per question in `hosted_trace`, and the Langfuse metadata keys added
      to the config. `trace.py`'s `run_config` is unchanged; assert that its existing tests pass
      untouched.
- [x] 3.3 Tests, **against the real propagation path, not a double of it**: a user id set by
      `hosted_trace.attributed(...)` around consumption of `agent.ask` reaches every span of the trace,
      including spans created on LangGraph's worker threads. It must still hold when the driver
      consumes the generator one item at a time with other work in between. `None` attaches nothing.
      If propagation fails, stop and bring it back to design. Do not patch around it.
- [x] 3.4 Implement `attributed()`, and use it in `web.py` where the event stream is consumed, with
      `account_scope(admission)`. The CLI and the harness do not call it.
- [x] 3.5 Test (in `tests/test_hosted_tracing.py`, beside the tracer it needs, rather than extending
      `tests/test_identity_never_reaches_the_agent.py`): two readers, tracing on
      and off. The model doubles' `seen` lists are identical across all four runs.

## 4. The rating's copy, and failing open

- [x] 4.1 Tests: `record_verdict` with tracing on writes the trail row, then a `reader_verdict` score
      on `create_trace_id(seed=question_id)` with value 1 or 0. `record_comment` adds `reader_comment`
      with the text. With tracing off, no client is touched at all.
- [x] 4.2 Tests: the score client raises, and separately hangs past its timeout. The trail row is
      identical to the tracing-off run, `_record` returns, nothing reaches the page, and a
      `tracing.failed` record is written.
- [x] 4.3 Implement the copy in `feedback._record`, after the trail record, with deterministic score
      ids. `feedback.py` stays free of identity; the score carries none.
- [x] 4.4 Tests: the handler raises in `on_llm_start`, and separately its export fails. The answer,
      the entries and the trail records are equal to a tracing-off run of the same question with the
      same doubles. Compare them whole, not by one field.
- [x] 4.5 Tests for the conditions (D9), pure, in `hosted_trace`, over stubbed counts:
      49% used with the estimate within what remains → proceed; 51% → pause; exactly 50% → proceed
      (the spec says "more than half"); 10% used but the estimate exceeds what remains → pause; one of
      the three counts failing → usage unknown → pause, never a partial sum and never 0%; zero traces
      this month → per-question unknown → pause. Pair each pause with the proceed case that differs in
      one dimension. Control: the stub that yields unknown yields a number once all three counts answer.
- [x] 4.6 Implement `monthly_usage()`, the per-question average and `needs_approval()` in
      `hosted_trace`. Expose from `evaluation` the count of pairs a run will actually ask after
      resuming, using the same rule `run_evaluation` uses to skip. Do not write a second copy of it.
- [x] 4.7 Tests for the pause in `eval_cli run`, with stdin stubbed: when a condition holds,
      `yes` proceeds; `no`, an empty line, EOF and a non-terminal stdin each end the run with a
      non-zero code, before `run_evaluation` is called, with no results file created or appended and
      the agent's model double never called. When no condition holds, the run proceeds without reading
      stdin. With tracing off, the tracer client is never constructed and stdin is never read. A
      resumed file's estimate counts only the remaining pairs.
- [x] 4.8 Implement the prompt and its wording in `eval_cli`. `evaluation.py` gains no input.
- [x] 4.9 Add the new requirements to `tests/test_spec_conformance.py`'s map, each pointing at the
      tests above.

## 5. Seeding, the live check, and the record

- [x] 5.1 Fault-seed `hosted_trace.py` in a copy, following the `fault-seeding` skill. At minimum:
      the setting read as on for an unknown value; the LangSmith refusal removed; the trace id seeded
      from `session_id` instead of `question_id`; the user id attached when it is `None`; the score
      written before the trail row. Each must be killed by the test named for it. Write down any
      survivor and act on it. Then run `mutation-test-module` over `hosted_trace.py`.
- [x] 5.2 Live, by hand, with a Langfuse Cloud EU project: ask one question signed in, and rate it down
      with a comment. Then run the skill's self-audit loop (`references/instrumentation.md` step 3):
      fetch the trace with `langfuse-cli`, audit it against the best-practices page fetched fresh, fix
      the gaps and re-run. Its checklist is the audit list: generations typed as generations, model
      and tokens present, a readable trace name, input and output on the root observation, session
      and user on the cost-bearing generations. Check in the UI that the trace id matches, that session, run label and user id
      are present, that no address appears anywhere in the trace, and that both scores are on it.
      Record what was seen and on which date. Do not paste corpus text into the record.
- [x] 5.3 From that trace, count the units one question costs, and write the figure and the implied
      monthly headroom into README.
- [x] 5.4 Docs, in this change:
      README (replace "There is no tracing instrumentation yet", add the setting and keys to the
      configuration table, and state what leaves the host, including readers' comments);
      `.streamlit/secrets.toml.example` (the setting, the keys and the EU host, with placeholder values
      only); `docs/diagrams/architecture.md` (the tracer as a sink beside the trail; check that the
      generated agent graph is unchanged); CLAUDE.md (the module table row for `hosted_trace.py`);
      `docs/roadmap.md` (WP4 split: tracing done, usage events still open; WP3 moved to Done; the
      LangSmith hazard marked closed); CHANGELOG `[Unreleased]`; ADRs `1000`–`1020` completed.
- [x] 5.5 Full suite, lint and `openspec validate add-hosted-tracing --strict`. Then commit, and
      suggest `/code-review` before the merge.
