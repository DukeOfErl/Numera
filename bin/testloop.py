#!/usr/bin/env python3
"""The test loop at commit time and at the boundaries: what runs, and when.

    bin/testloop.py commit FILE...   pre-commit: only the tests the change reaches
    bin/testloop.py full             pre-push and pre-merge-commit: all of them, in parallel

**Two tiers, and the cheap one is not the gate.** `commit` runs pytest-testmon, which
re-runs only the tests that execute code that changed -- seconds instead of the
suite's ~160. That speed is bought with a blind spot: testmon follows *Python*, so a
change to a file a test merely reads (a README the wording tests quote, a SQL script,
a JSON fixture) selects nothing and passes. A false all-clear at the gate that decides
a commit is the expensive error, so `commit` falls back to the **full suite** when any
staged file is not Python under `src/` or `tests/` and is not known to be read by no
test. `full` is what a push, a merge and CI run, and the "green suite at a section
boundary" is still this one, never testmon.

Stdlib only, so the hook starts in a checkout with no environment. **Where there is no
project environment it says so and exits 0**: this repository is worked in three
checkouts, one with no venv, and a hook that failed there would be turned off by the
first person who met it. That is a skipped check, announced, not a passed one -- the
push and CI tiers are the backstop.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Selectable by testmon: Python it can trace to the tests that run it.
SELECTABLE_PREFIXES = ("src/", "tests/")

#: **No test reads these.** Anything else non-Python is assumed to be read by some
#: test, because that was true often enough (README, CLAUDE.md, openspec/, sql/,
#: `.claude/`, `bin/keepalive.py`) that the safe default is the full suite, and
#: because the failure of guessing wrong is a commit that nothing checked.
#: `tests/test_testloop.py` greps the test files for each of these and fails when
#: one starts naming a path here, so the list cannot go stale unseen.
INERT_PREFIXES = ("docs/", ".github/")
INERT_FILES = frozenset({"CHANGELOG.md"})

#: Measured on a 12-core, 7.8 GB machine: six workers took the suite from 158s to
#: 81s, and twelve (`-n auto`) were *slower* than serial at 145s -- a dozen workers
#: each importing Streamlit and LangChain press on memory, not on cores. So a cap,
#: not "all cores", with an override for a machine that has the room.
DEFAULT_WORKERS = 6
WORKERS_ENV = "SCINUMBERS_TEST_WORKERS"

#: pytest's exit status when nothing was collected or everything was deselected --
#: exactly what testmon produces when the change reaches no test. Success here;
#: for `full` it would mean the suite vanished, and stays a failure.
NO_TESTS_COLLECTED = 5


def selectable(path: str) -> bool:
    return path.endswith(".py") and path.startswith(SELECTABLE_PREFIXES)


def inert(path: str) -> bool:
    return path in INERT_FILES or path.startswith(INERT_PREFIXES)


def reasons_for_full_suite(paths: list[str]) -> list[str]:
    """The staged files that testmon cannot vouch for. Empty means testmon suffices."""
    return [p for p in paths if not selectable(p) and not inert(p)]


def workers() -> int:
    try:
        return max(1, int(os.environ[WORKERS_ENV]))
    except (KeyError, ValueError):
        return max(1, min(DEFAULT_WORKERS, os.cpu_count() or 1))


def project_python() -> Path | None:
    candidate = ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def _run(python: Path, args: list[str]) -> int:
    return subprocess.run([str(python), "-m", "pytest", *args], cwd=ROOT).returncode


def full(python: Path) -> int:
    return _run(python, ["-n", str(workers()), "--dist", "worksteal", "-q"])


def commit(python: Path, paths: list[str]) -> int:
    if not paths or all(inert(p) for p in paths):
        return 0
    reasons = reasons_for_full_suite(paths)
    if reasons:
        shown = ", ".join(reasons[:3]) + (" ..." if len(reasons) > 3 else "")
        print(f"testloop: full suite, because testmon cannot see changes to: {shown}", flush=True)
        return full(python)
    if not (ROOT / ".testmondata").exists():
        print(
            "testloop: building the testmon database -- the first run is the whole suite",
            flush=True,
        )
    # `--testmon-forceselect`: the project's `addopts` carries `-m`, and testmon
    # switches selection off whenever `-m` is in play. Without this it records data
    # and runs everything, which looks like testmon working and saves nothing.
    status = _run(python, ["--testmon-forceselect", "-q"])
    return 0 if status == NO_TESTS_COLLECTED else status


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"commit", "full"}:
        print(__doc__, file=sys.stderr)
        return 2
    python = project_python()
    if python is None:
        print(
            "testloop: NOT RUN -- no .venv in this checkout, so no tests were run. "
            "The push and CI tiers still run the full suite."
        )
        return 0
    if argv[0] == "full":
        return full(python)
    return commit(python, argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
