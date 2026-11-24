# ADR-2110: At commit, a changed file runs the tests that name it

- **Status:** accepted
- **Date:** 2026-11-24
- **Pull request:** none yet (`chore/cheaper-test-loop`)
- **Amends:** [ADR-1300](1300-two-tier-test-loop.md) (the two-tier test loop)

## Context

ADR-1300's commit tier left Python under `src/` and `tests/` to testmon, ran nothing for
a short inert list (`CHANGELOG.md`, `docs/`, `.github/`), and ran the **full suite** for
every other staged file, because testmon cannot see a test that merely reads a file. That
was the safe direction, and it made every edit to `README.md`, `CLAUDE.md` or an OpenSpec
spec cost a full run (about 160 s), which is most of what a commit here touches.

Building the replacement turned up a hole in the old rule. Its tripwire grepped test files
for the literal `".github/"`, but `test_scheduled_workflows.py` reads every workflow
through `ROOT / ".github" / "workflows"`, a string the grep could not match. So a commit
that changed only a workflow ran **no test**, while a test reads that workflow. The push tier
caught it later.

## Decision

For a staged file that is neither selectable Python nor inert, `bin/testloop.py` asks which
tracked code **names** it, and decides:

| The file | Commit runs |
|---|---|
| read by a tool rather than by name (`pyproject.toml`, `uv.lock`, `.gitignore`, `.python-version`, `.streamlit/`) | the full suite |
| Python outside `src/` and `tests/` (a test may import it by module name, which no string shows) | the full suite |
| named by the app, a script, or a test helper (`conftest.py`, `store_double.py`, …) | the full suite |
| named by no code at all, so its readers are out of sight | the full suite |
| named only by `tests/test_*.py` files | those test files |

"Names" is read from string literals, parsed with `ast` (docstrings and comments are prose
and are skipped). A whole literal may be one path segment (`ROOT / "openspec"`) and names
everything under a directory of that name. A word inside a longer string counts only when
it has the shape of the path, the file name, or a directory above it. The same detector
checks the inert list: `tests/test_testloop.py` fails if any tracked code starts naming an
inert path. `.github/` leaves that list, and `CLAUDE.md` joins it because nothing names it.

Measured on 2026-11-24 over all 532 tracked files: 173 go to testmon, 103 are inert, 172
run only their named tests (every OpenSpec file, `README.md`, the workflows), and 84 run
the full suite. A `README.md` commit ran 151 tests in 45 s, and an OpenSpec spec ran 93 in 11 s,
against about 160 s for the full suite.

## Trade-off accepted

The rule is now a judgement about code, not a list, so it can be wrong in two directions,
and they don't cost the same:

- **Too many tests** (a path quoted in an error message counts as a mention): a longer run.
  Cheap, and accepted.
- **Too few** (a test reads the file through a path no string spells out, e.g. a name
  computed from parts, or through code it imports from another test file): a commit that
  nothing checked. The full suite at push and merge is the backstop, which is why that tier
  stays (ADR-2100). Every case the detector can't decide goes to the full suite.

**What was verified.** Fourteen defects were seeded into a copy of `bin/testloop.py`, with a
green baseline, a caught canary (`plan` renamed), and a test inside the copy asserting the
copy was the code under test. All fourteen were caught by the test named for the behaviour.
The first run left five survivors: three in `commit()`'s orchestration (named tests skipped,
the full-suite verdict ignored, an empty named run failing the commit), `bin/` scripts not
read as readers, and a mid-word path match. Each got a test before the second run. The
`.github` regression is
`test_a_workflow_change_runs_the_test_that_reads_the_workflows`; putting `.github/` back
on the inert list fails it and the tripwire.

**Not verified:** that no test reads a file by a computed path today. The measurement shows
which files the detector calls narrow, but it can't see a read the detector misses, by
construction.
