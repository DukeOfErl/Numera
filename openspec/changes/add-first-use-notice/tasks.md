<!-- ADR block for this change: 1250–1290, reserved in CLAUDE.md. Write each ADR in
     the same task as the decision, not at the end. Planned: 1250 sibling module +
     stateless window; 1260 read-only role and a URL, not the control plane; 1270
     delivery through a standing issue, and the digest widened to cover it; 1280 reader
     addresses in an issue and a log, private repository only. -->

## 1. Confirm what the trail actually carries (before any code)

- [x] 1.1 Against the real trail (read-only, the Neon SQL-over-HTTP recipe in the memory note), confirm that **`question.asked` rows carry `user_email`** and that **`signin.admitted` is written, with `user_email`, for a reader who asks nothing**. If either is false, stop and say so: the design's join rests on both (ADR-0810). Record what was queried and when, in the ADR it supports.
- [x] 1.2 Count rows and distinct addresses per event, and `explain analyze` the full-history `min(at)` aggregate for each event, so Decision 2's "a few thousand rows, well inside 30 s" is a measurement and not a guess.

## 2. The query and its read-only role (tests first)

- [x] 2.1 Write the failing offline tests from the spec's scenarios: nobody new → empty report; first sign-in only; first question only; both in one window → one block; seen before the window → not reported; signed in before / asks now → reported for asking only; one address in two spellings → one reader; excluded address → not reported; asking twice → identical and nothing written. **Assertions come from the spec text, not from running the code.**
- [x] 2.2 Write the live-Postgres test in the style of `tests/test_pending_live.py` (same marker and skip rule) covering the SQL join itself: the offline double cannot reach it, and `pending` had two defects that only the live run found. Include the combined case and the "earlier event of a different kind" case.
- [x] 2.3 Implement `src/scinumbers_ask/first_use.py`: the two first-ever queries joined on address, `--minutes` (default 70, with the comment saying why it exceeds the interval and which direction is the cheap error), repeatable `--exclude`, `SCINUMBERS_TRAIL_READ_URL`, `pending`'s timeouts imported not copied, and the stdout/stderr/exit contract of Decision 4 (0 silent, 1 unreadable, 2 bad arguments). Returns a value rather than printing, as `waiting` does.
- [x] 2.4 Register the console script `scinumbers-first-use` in `pyproject.toml`; add `first_use` to the `HARNESS` set in `tests/test_driver_independence.py` (the test that refuses a name with no file behind it will say if it is missing).
- [x] 2.5 Write `sql/first_use_reader.sql`: a login role with `select` on the trail table **only**, password a placeholder; plus the live test that the role **cannot** insert, update, delete, or read `accounts` — assertions against the database refusing, not against the file's text.
- [x] 2.6 ADR-1250 (sibling module, stateless window, the rejected marker-row option and why) and ADR-1260 (read-only role and a URL; the Neon API key rejected because it can delete the project; `accounts` deliberately not granted). Add the `tests/test_spec_conformance.py` mapping entries for the three new requirements in this task, with the tests that assert them.

## 3. The scheduled workflow and its failure path

- [ ] 3.1 `.github/workflows/first-use.yml`: `23 * * * *`, `workflow_dispatch` with a `test` input, a `concurrency` group, `issues: write`; runs `uv run scinumbers-first-use` with the secret as `SCINUMBERS_TRAIL_READ_URL` and `--exclude` from the `FIRST_USE_EXCLUDE` variable; a non-empty report becomes a comment on the open `first use` issue (created if absent); empty report writes nothing; `test: true` posts one clearly-marked test line. Pin the runner to `ubuntu-24.04` as `keepalive.yml` does, and say why.
- [ ] 3.2 Widen `keepalive-digest.yml` to a list of workflows (`keepalive.yml`, `first-use.yml`), name each in its report, retitle its standing issue `scheduled workflow problems`. Re-run the jq logic against fixtures for each case (healthy, failing, none ran) and show it can fail.
- [ ] 3.3 Comment beside the line that prints reader addresses saying that it is safe only while the repository is private. ADR-1270 (delivery through a standing issue; digest widened because GitHub's failure mail is off) and ADR-1280 (addresses in an issue and a log; what making the repository public would publish).

## 4. Prove the tests can fail (fault-seeding, over this module only)

- [ ] 4.1 Per the `fault-seeding` skill, seed into a **copy**, never the working tree: (a) drop the "no earlier event" predicate, (b) drop the lower-casing, (c) apply `--exclude` before instead of after combining so a combined reader splits, (d) report both firsts when only one is in the window. Establish a green baseline and a caught canary first; each mutant must fail exactly the test written for it. Record which survived and what that means.

## 5. Documentation, in this change

- [ ] 5.1 README: what the notice is, the role and secret setup steps, the workflow, and the privacy note; keep the existing cron note for `pending` consistent with it.
- [ ] 5.2 CHANGELOG `[Unreleased]` Added; `CLAUDE.md` module table row for `first_use.py` (a harness module; **silent when nobody is new**), and update the ADR block's "written" note.
- [ ] 5.3 `docs/diagrams/architecture.md`: if it carries the operator/scheduled-job story, add this as one sequence diagram following `docs/diagrams/DIAGRAMS.md`; if it does not, say so in the commit rather than inventing a place for it.
- [ ] 5.4 `openspec validate add-first-use-notice --strict`.

## 6. Roll out (operator steps, then verify)

- [ ] 6.1 Create the role on the deployment's Neon branch and set its password; add the repository secret `SCINUMBERS_TRAIL_READ_URL` and the variable `FIRST_USE_EXCLUDE`. These are the operator's, and none of it is committed.
- [ ] 6.2 Full suite once; commit; hand over. Merging to `dev` and `main` and pushing are the operator's call (scheduled workflows exist only on `main`).
- [ ] 6.3 After the merge: dispatch with `test: true` and **see the mail arrive** — until it does, neither this notice nor the digest has been shown to reach anyone. Then dispatch plain and confirm it is silent.
- [ ] 6.4 After a week: read keepalive's run history for the largest gap between ticks and set `--minutes` from it rather than from 70.
- [ ] 6.5 Archive the change once its requirements have landed (`openspec archive`), per `.claude/rules/specs.md`.
