# ADR-1300: The test loop has two tiers, and the cheap one is not the gate

- **Status:** accepted
- **Date:** 2026-10-02
- **Pull request:** none yet (`chore/test-loop`)
- **Amended 2026-10-04:** the default is **three** workers, not six. Six is faster (81 s) with
  memory free, but was killed once by the out-of-memory killer (exit 137) under ordinary load
  on the 7.8 GB machine, mid-commit; three finished every full run in about 100-180 s. The
  rest of this decision stands.

## Context

The suite is ~1,870 tests and takes about 160 s serially, which is long enough that
it stopped being run at every commit. Two instruments were measured on this machine
(12 cores, 7.8 GB) before choosing:

- **pytest-xdist** (3.8.0): `-n 6 --dist worksteal` 81 s; `-n 4` 104 s; `-n 4
  --dist loadfile` 111 s; `-n 2` 140 s; **`-n auto` (12) 145 s** — a dozen workers
  each importing Streamlit and LangChain press on memory, not cores. Every run
  passed all 1,847 tests; the cause of the `-n auto` slowdown is inferred, not
  confirmed.
- **pytest-testmon** (2.2.0): a first run that builds its database costs about
  twice a plain run (302 s); a run with nothing changed took 1.6 s; a small edit
  took 4–66 s depending on how widely the changed code is used.

Testmon's own documentation says it does not track static files, and the trial
showed it: a whitespace edit to `door_demo.json`, which `test_door_demo.py` reads,
selected **zero** tests. Separately, testmon switches selection off whenever `-m`
is in play, and this project's `addopts` carries `-m 'not network and not corpus'`.
The first full "testmon" run here executed everything and looked fine.

## Decision

Two tiers, both in `bin/testloop.py` and wired through `.pre-commit-config.yaml`.

- **Commit:** `pytest --testmon-forceselect`. If any staged file is not Python
  under `src/` or `tests/` and is not on a short list that no test reads
  (`CHANGELOG.md`, `docs/`, `.github/`), run the **full suite** instead and say
  why. A list of what *is* inert, not of what is dangerous, so a new kind of file
  defaults to the safe direction.
- **Push, merge and CI:** the full suite, in parallel, three workers locally (six when this
  was written; see the amendment above) and
  `auto` on the CI runner. Not testmon, ever: the "green suite at a section
  boundary" is this tier.
- Where there is no `.venv` the hook prints `NOT RUN` and exits 0, because this
  repository is worked in a checkout that has none and a hook that failed there
  would be switched off by the first person who met it.

`tests/test_testloop.py` fails if a test file starts mentioning a path on the inert
list, so the list is a checked claim and not a convention.

## Trade-off accepted

A commit gets a result in seconds instead of minutes. The cost is a blind spot
that is closed by a rule, not by testmon: any gap in the inert list, or a test
that reads a file through a path the grep cannot see, is a commit that nothing
checked until the push. The push tier is the backstop, which is why it is not
optional. The testmon database is per checkout, git-ignored, and a clone's first
commit pays ~5 minutes to build it; copying a database between directories makes
testmon select nothing, so it must not be shared. Six workers is a measurement for
one machine, with an environment override for another.

**What was verified, and what was not.** Selection was observed on a real edit (a
no-op in `units.dimension` selected 217 tests and passed in 60 s). The fail path
was observed in a clean copy: green baseline (1,868 passed), then `dimension`
returning a constant failed 30 tests in `test_units.py` plus dependents and exited
non-zero. A relocated copy of the testmon database was *not* a valid harness — it
selected nothing. Not verified: that the push and pre-merge hooks fire from git
(the sandbox could not install them), that xdist is free of order-dependent
flakiness beyond five green runs, and testmon's behaviour across a branch switch.
