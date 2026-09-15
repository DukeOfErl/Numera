# Tasks — add-durable-trail

**ADR block for this change: `0700`–`0730`.** Reconcile against the table in
`CLAUDE.md`, which is the authority — this note is where an implementer reads it,
not where it is decided. Allocate by copying the template to the number and
committing the stub early; a number is spent when the file exists, not when the
ADR is written. `0740`–`0770` and `0780`–`0830` are reserved for the two changes
that follow and must not be taken here.

Two things that are already true and should not be redone: `sqlalchemy` and
`psycopg[binary]` are in the `ask` extra, and `.streamlit/secrets.toml` is
gitignored by path and by bare name.

## 1. The sink, and the refusal that belongs to it

- [x] 1.1 Claim ADR-0700 by copying the template and committing the stub. It
      records choosing Neon over Supabase, Turso, Firestore and Sheets, with the
      disqualifying property of each — write it now, while the rejected options
      are still in view, not at the end when only the choice survives.
- [x] 1.2 Claim ADR-0710 for the fail-open decision, and say in it that it
      inverts the spend gate deliberately. This is the ADR that stops someone
      later making the two consistent in the wrong direction.
- [x] 1.3 New module owning the durable sink: connection, schema
      (`CREATE TABLE IF NOT EXISTS`), and one `record(...)` entry point. The
      append-only shape is in design.md D5, `user_email` nullable from the start.
- [x] 1.4 The swallow goes **inside** `record(...)`, not at any call site — broad
      `except Exception`, one line naming the exception type and message to the
      trail and stderr, no traceback. A module-level failure counter, readable
      without grepping.
- [x] 1.5 An explicit short connect/statement timeout, and **no retry**. Both are
      requirements, not tuning: a hung rerun is worse for the reader than a
      missing row.
- [x] 1.6 Configuration is absence-tolerant: no destination configured means the
      app behaves exactly as today, and the absence is reported once rather than
      per question.

## 2. Verification of group 1, before anything depends on it

- [x] 2.1 Tests for the fail-open contract. **The negative case must differ in
      the dimension the code actually reads**: a store that raises on connect, a
      store that raises on execute, and a store that hangs are three different
      paths, and a single `Exception` double proves only one of them. Check
      CLAUDE.md's `_is_out_of_credit` note before writing these — that mutant
      passed 905 tests.
- [x] 2.2 A test asserting a **direct caller** of `record(...)` — not through a
      driver — needs no error handling to keep working. This is the spec scenario
      "Something other than a driver records", and it is what makes the guard
      belong to the operation.
- [x] 2.3 A test that the failure counter moves, so "nothing recorded for three
      weeks" is answerable.
- [x] 2.4 Fault-seed group 1 into a **copy** of the source, never the working
      tree: make `record()` swallow silently without counting, and confirm 2.3
      fails. Name the mutant that died in the commit message. Per CLAUDE.md, no
      coverage claim before that happens.

## 3. Session and question identity

- [x] 3.1 `session_id` into `QuestionTrace`'s records and into the metadata dict
      returned by `run_config()`, beside `question_id` and `run_label`.
- [x] 3.2 `question_id` onto `web.Item`, and stop `web.item_for` dropping it.
- [x] 3.3 Tests: two questions in one session share a session identifier and
      differ in question identifier, and the order they were asked is recoverable
      from records alone.
- [x] 3.4 A test that a rendered item names the question that produced it.

## 4. Wiring, and the driver-level check

- [x] 4.1 The web driver passes the session identifier it already mints into the
      trail. It is read from `web.session_id(...)`, never from anything the
      browser can set independently.
- [x] 4.2 `tests/test_driver_independence.py`: **this task was written on a false
      premise and the decision went the other way.** `trail_store` is on the
      *agent* side, deliberately: what the dependency rule protects against is the
      agent becoming unrunnable without an interface, and a logging handler over
      an engine it is handed does not do that. `trace` is already core for the
      same reason. Recorded in a named test rather than left to subtraction,
      which is silent and cannot distinguish a decision from an oversight. If the module needs a
      name in `HARNESS`, add it — the set decides by subtraction which modules
      count as core, and it refuses a name with no file behind it.
- [x] 4.3 Drive the **real script** through `AppTest` to confirm recording
      happens once per question and not once per rerun. Per CLAUDE.md, when
      something is drawn — or written — relative to a script run cannot be seen
      below the driver; the banner incident is the precedent.
- [x] 4.4 Confirm the app starts and answers with no destination configured, and
      with a destination configured that refuses every connection.

## 5. Spec conformance and the record

- [x] 5.1 Add the mapping entries in `tests/test_spec_conformance.py` for the
      modified requirement and the added one — in this change, not a later one.
- [x] 5.2 `openspec validate add-durable-trail --strict`.
- [x] 5.3 Update the `CLAUDE.md` Architecture table with the new module, and the
      ADR allocation table with `0700`–`0730` plus the two reserved blocks.
- [x] 5.4 `README.md` and `CHANGELOG.md`: what a deployer must now configure, and
      that conversations remain ephemeral while the trail does not.
- [x] 5.5 Note in the deploy branch's contract that the two new dependencies must
      reach `[project].dependencies` before the next deploy.

## 6. Measure what was assumed

- [ ] 6.1 **Blocked until the change is deployed.** Measure INSERT latency **from the deployed app**, not from a developer
      machine. design.md carries ~500 ms from Europe as an upper bound; record
      the real figure there and mark which one it is. An unmeasured reassurance
      in a design document is worse than an admitted gap.
- [x] 6.2 Record the **duration of every write** as a field on the row itself,
      rather than measuring idle-restore latency on a schedule. Neon free-plan
      branches archive when inactive and publish no restore latency, and that is
      the one number nobody has — but a scheduled probe cannot get it, because
      pinging the database on a timer keeps it warm and destroys the condition
      being measured. (The same self-defeating shape as the keep-alive cron that
      ruled out Supabase.) Instrumented instead, the figure falls out of data
      already being collected: the first write after a long gap carries it. It
      also keeps measuring, so Neon changing this under us is visible rather than
      assumed.
- [ ] 6.3 **Deferred by design, and gated on 6.2.** Only after 6.2 has captured one real cold figure, consider a weekly
      heartbeat that reports whether any row arrived in the last seven days —
      the alarm for the fail-open hazard, which is not the lost row but
      discovering weeks later that nothing was ever recorded. Deliberately second:
      a heartbeat is itself traffic, so adding it first forecloses 6.2 permanently.
      A counter that only an operator reads is the cheap half of this and is
      already task 1.4.
- [x] 6.4 Run mutation testing over the new sink module via the
      `mutation-test-module` skill. Orchestrator only — one run at the end, not
      per task, and not over the package.
