# Tasks

**ADR block: `1300`–`1340`**, added to CLAUDE.md's allocation table as task 0.1.
The table is the authority; `tasks.md` is the copy an implementer reads.
`add-first-use-notice` holds `1250`–`1290` on its own branch, and this block sits
clear of it. Planned: `1300` its own package, a reader of the trail and not an
adapter; `1310` a role that can read the trail and nothing else; `1320` Langfuse
is linked, never queried. Each ADR is written with its decision, never batched.

**Testing policy.** Two places in this change produce output that looks right
when it is wrong, and they get the instrument:

- **The ending classification** (`figures.py`) is a classifying rule. Its tests
  cover both populations: questions it calls answered, and questions it must
  *not* call answered (no ending, an unknown last event, an ending followed by a
  later non-ending event). Its negative cases vary the event names it reads, not
  merely the outcome. Seed it at the end of task group 3.
- **The read-only role** is a guard. Its live test proves it can fail before it
  is believed: the same assertions run under the owner role must fail (the
  canary), and under `scinumbers_monitor` must pass.

Rendering (`app.py`) is not seeded. A bug there shows itself the moment someone
looks.

**Operator tasks are marked (operator).** They happen in a console, not the
repository. The implementer's job is to leave the instructions right.

## 0. Allocation

- [ ] 0.1 CLAUDE.md: add `add-monitor-dashboard` | `1300`–`1340` to the ADR
      table. Write ADR stubs `1300`, `1310`, `1320` from the template and commit
      them first.

## 1. The read-only role

- [ ] 1.1 Probe: does Neon's API (`GET /projects/{id}/connection_uri` with
      `role_name`) return a URI for a role made in SQL? Answer it on `dev` with a
      throwaway role, then drop the role. Record the answer, with the date, in
      ADR-1310, and pick the password path from design §2 accordingly.
- [ ] 1.2 `sql/monitor_role.sql`: idempotent create of `scinumbers_monitor`
      (`LOGIN`, password from `psql -v`), `CONNECT`, `USAGE ON SCHEMA public`,
      `SELECT ON trail` only, `default_transaction_read_only = on`, and a
      role-level `statement_timeout`. No default privileges, no
      `ALL TABLES`. A header comment says why, and how to run it per branch.
- [ ] 1.3 (operator) Run it on `dev`.
- [ ] 1.4 `tests/test_monitor_role_live.py` (live marker, against `dev`):
      under `scinumbers_monitor`, `select` from `trail` succeeds; `insert` into
      `trail` is refused; `select` from `accounts` is refused; `create table` is
      refused. **Canary first:** the same test parametrised over the owner role
      must fail on the three refusals, and the test says so. A test that passes
      for both roles proves nothing.
- [ ] 1.5 Write ADR-1310.

## 2. Package and entry point

- [ ] 2.1 `src/scinumbers_monitor/__init__.py` and `connection.py`: build the
      read-only engine from a branch name, per the outcome of 1.1. Apply
      `trail_store.CONNECT_TIMEOUT_S` and `POOL_RECYCLE_S` rather than new
      numbers.
- [ ] 2.2 `cli.py` and the `scinumbers-monitor` console script in
      `pyproject.toml`: refuse without `--branch`, with no default, using a
      sentence in `pending.NO_BRANCH`'s pattern. Exec `streamlit run app.py
      --server.address 127.0.0.1 --server.headless true`, passing the branch.
      Test: no branch → non-zero exit and the sentence; with a branch → the argv
      handed to the exec names the branch and binds to localhost (exec stubbed).
- [ ] 2.3 `tests/test_monitor_boundaries.py`: `scinumbers_monitor` imports from
      `scinumbers_ask` only `neon` and `hosted_trace`; no `scinumbers_ask` module
      imports `scinumbers_monitor`; within the package, only `app` imports
      Streamlit. Reuse `test_driver_independence`'s import reader, don't copy it.
- [ ] 2.4 Write ADR-1300.

## 3. Queries and figures

- [ ] 3.1 `figures.py`: `ENDINGS: dict[EndReason, str]` and `classify(rows)`
      → answered / each other ending / unidentified, with the last event named.
      Tests come from the spec scenarios. Expected values are written from the
      requirement, not taken from a run.
- [ ] 3.2 Tests guarding the map: every `EndReason` has an entry; every mapped
      event name appears as `record("<name>"` somewhere in
      `src/scinumbers_ask/`.
- [ ] 3.3 `figures.py`: health figures for a period (questions, distinct
      testers, endings, spend total and per question, limit endings), each rate
      paired with its count; an empty period gives a value that says so, not
      zeros that look like data.
- [ ] 3.4 `figures.py`: quality figures (verdicts by `run_label` with counts;
      unattributed judgements counted, not dropped; ungrounded and unsupported
      citation counts; retrieved against cited).
- [ ] 3.5 `figures.py`: recording health (time of last row; `tracing.failed`,
      `tracing.unavailable` and `tracing.usage_unknown` counts; `prev_write_ms`
      for the first write after a gap of more than 10 minutes).
- [ ] 3.6 `queries.py`: one `select` per row of the view, parameterised by
      period, reading `trail` only.
- [ ] 3.7 `tests/test_monitor_queries_live.py` (live, `dev`, read-only role):
      every statement in `queries.py` runs and returns the columns `figures.py`
      reads; `pending.waiting` runs under the read-only role.
- [ ] 3.8 Seed the ending classification in a copy (fault-seeding skill): an
      off-by-one on "latest", an unmapped event counted as answered, the
      unidentified bucket merged into no-answer. Each must be caught by a named
      test. Record the result in the commit message.

## 4. The page

- [ ] 4.1 `app.py`: header with the branch name and a period selector; rows for
      health, quality, door (via `pending.waiting`) and recording health; a
      recent-questions table. Every query goes through `st.cache_data(ttl=600)`
      keyed on branch and period. A **Refresh** button clears the cache. Nothing
      runs on a timer.
- [ ] 4.2 Trace link: `{LANGFUSE_BASE_URL}/project/{LANGFUSE_PROJECT_ID}/traces/{trace_id_for(question_id)}`,
      omitted past `TRACER_WINDOW_DAYS = 30`. Check the pattern by opening the
      link for a real traced question. Unit test: a question at 29 days gets a
      link and one at 31 days does not; the URL contains `trace_id_for`'s output.
- [ ] 4.3 Question drill-down: selecting a row shows that question's whole
      trail in `at` order.
- [ ] 4.4 Test that the page makes no request to Langfuse: run the app with
      `streamlit.testing` and a network-refusing opener for the Langfuse host,
      and exercise every row and the drill-down.
- [ ] 4.5 Run it against `dev` and look at it (run skill). Check the quiet-period
      wording, rates with counts, and the branch name on every row.
- [ ] 4.6 Write ADR-1320.

## 5. Spec conformance

- [ ] 5.1 `tests/test_spec_conformance.py`: map each `operator-monitoring`
      requirement to the tests above. Record any gap explicitly (for example,
      "another machine connects" is asserted by the argv test, not by a
      connection attempt — say so).

## 6. Langfuse side (operator)

- [ ] 6.1 (operator) In Langfuse: keep the curated Latency, Cost and Usage
      dashboards; add widgets from the observations and scores views (not the
      legacy traces view) for p50/p95 latency of `ask` traces, tokens by model,
      and `reader_verdict` over time.
- [ ] 6.2 (operator) Configure the two Hobby alerts (design, Open Questions)
      with an email or webhook automation.
- [ ] 6.3 Document 6.1–6.2 in the README's operator section, with the reason
      they live in Langfuse and not in the view.

## 7. Documentation and wrap-up

- [ ] 7.1 README: what the view is, `scinumbers-monitor --branch alpha`, the
      role script, the settings (`LANGFUSE_PROJECT_ID`, and the password
      variable if 1.1 needs it).
- [ ] 7.2 `docs/diagrams/architecture.md`: the view as a reader of the trail
      beside the app, the Langfuse link, and the role's reach (following
      `DIAGRAMS.md`).
- [ ] 7.3 CLAUDE.md: a `scinumbers_monitor` paragraph and module table in the
      Architecture section.
- [ ] 7.4 CHANGELOG: an Added entry.
- [ ] 7.5 `docs/roadmap.md`: reconcile WP4. "The usage-events table and its
      queries" is met by reading the trail, unless that is decided otherwise;
      note the deferred `question.ended` record (design §4).
- [ ] 7.6 (operator) Run `sql/monitor_role.sql` on `alpha`; open the view
      against `alpha`.
- [ ] 7.7 Full suite green, `openspec validate --strict` passes, and the work is
      committed and handed over for the operator to try before merge.
