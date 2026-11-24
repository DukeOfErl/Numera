# ADR-2100: The commit tier runs at commit only

- **Status:** accepted
- **Date:** 2026-11-24
- **Pull request:** none yet (`chore/cheaper-test-loop`)
- **Amends:** [ADR-1300](1300-two-tier-test-loop.md) (the two-tier test loop)

## Context

ADR-1300 put two hooks in `.pre-commit-config.yaml`: `testloop-commit` (testmon, falling back
to the full suite when a staged file is not Python it can trace) and `testloop-full` (the full
suite, `stages: [pre-push, pre-merge-commit]`). Only the second was given stages.

pre-commit runs a hook with no `stages:` at **every** installed hook type, and this project
installs three (`default_install_hook_types: [pre-commit, pre-push, pre-merge-commit]`). So at a
push or a merge, `testloop-commit` ran too. It was handed the files of the pushed or merged
range, which nearly always held a Markdown or YAML file, so it fell back to the full suite, and
then `testloop-full` ran the same suite again. Every push and every merge paid for two identical
full runs. On 2026-11-23, two merges into `dev` plus pushing `dev` and `main` took about 16
minutes in hooks (twelve full runs at 1.5–2 minutes each).

Dropping the push-time suite in favour of CI was considered and declined (2026-11-24): CI was red
from 2026-10-15 to 2026-11-24 without anyone noticing, because GitHub's failure mail is off, so
the local push run is the check that is actually read.

## Decision

`testloop-commit` gets `stages: [pre-commit]`. Push and merge run `testloop-full` alone: the
full suite, once. Nothing else about either tier changes.

`tests/test_testloop.py::test_each_git_hook_runs_exactly_one_tier_of_the_suite` reads the config
with pre-commit's own rule (no `stages:` means every installed hook type) and asserts exactly one
test-loop hook per hook type. Against `dev`'s config before this change it fails, naming both
hooks at `pre-push` and at `pre-merge-commit`.

## Trade-off accepted

None in coverage: the run removed was a duplicate of the one kept. One thing is given up in
principle: at a merge, the commit tier would have checked the merge's own files with testmon
first, and that never did anything the full run after it did not also do.

**Also found while doing this:** the installed hooks in `.git/hooks` still named the interpreter
from before the rename (`…/BioNumbers/.venv/bin/python3`), which no longer exists, so they ran
only when `pre-commit` happened to be on `PATH`. A clone renamed after installing needs
`uv run pre-commit install` again; that is local state, not something this repository can fix.
