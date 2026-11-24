#!/usr/bin/env python3
"""The test loop at commit time and at the boundaries: what runs, and when.

    bin/testloop.py commit FILE...   pre-commit: only the tests the change reaches
    bin/testloop.py full             pre-push and pre-merge-commit: all of them, in parallel

**Two tiers, and the cheap one is not the gate.** `commit` runs pytest-testmon, which
re-runs only the tests that execute code that changed -- seconds instead of the
suite's ~160. That speed is bought with a blind spot: testmon follows *Python*, so a
change to a file a test merely reads (a README the wording tests quote, a SQL script,
a JSON fixture) selects nothing and passes. So for a staged file that is not Python
under `src/` or `tests/`, `commit` asks which code *names* it (ADR-2110): if only test
files do, it runs those; if the app, a script or a test helper does, or nothing does,
or a tool reads it without naming it, it runs the **full suite**. Every case the rule
cannot decide falls to the full suite, because a false all-clear at commit is the
expensive error and an over-long run the cheap one. `full` is what a push, a merge and
CI run, and the "green suite at a section boundary" is still this one, never testmon.

Stdlib only, so the hook starts in a checkout with no environment. **Where there is no
project environment it says so and exits 0**: this repository is worked in three
checkouts, one with no venv, and a hook that failed there would be turned off by the
first person who met it. That is a skipped check, announced, not a passed one -- the
push and CI tiers are the backstop.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

#: Selectable by testmon: Python it can trace to the tests that run it.
SELECTABLE_PREFIXES = ("src/", "tests/")

#: **No code reads these**, so a change to them runs nothing. `tests/test_testloop.py`
#: asks the same question `plan` asks -- which tracked code names the path -- and fails
#: when something new does, so the list cannot go stale unseen. `.github/` was here
#: until 2026-11-24: the old tripwire grepped for ".github/", and the test that loads
#: every workflow spells it `ROOT / ".github" / "workflows"` (ADR-2110).
INERT_PREFIXES = ("docs/",)
#: `CLAUDE.md` joined 2026-11-24: guidance for agents, which no code reads, and committed
#: often enough that a full run for each edit was most of the hook's cost.
INERT_FILES = frozenset({"CHANGELOG.md", "CLAUDE.md"})

#: **Read by a tool, not by a name in the code**: pytest reads `pyproject.toml`, git
#: reads `.gitignore`, Streamlit reads `.streamlit/` in every page test. Nothing names
#: them where it matters, so a change to one runs the full suite whatever names it.
IMPLICIT_PREFIXES = (".streamlit/",)
IMPLICIT_FILES = frozenset({"pyproject.toml", "uv.lock", ".gitignore", ".python-version"})

#: This file names paths as configuration, not as reads; counted as a reader, it would
#: send every path on the lists above to the full suite.
HOOK = "bin/testloop.py"

#: **Three, because the limit on this machine is memory, not cores.** Measured on a 12-core,
#: 7.8 GB machine: with the memory free, six workers took the suite from 158s to 81s, and
#: twelve (`-n auto`) were *slower* than serial at 145s -- each worker imports Streamlit and
#: LangChain. But with ordinary other work running (about 5.7 GB already in use) six workers
#: were killed once by the out-of-memory killer (exit 137) in the middle of a commit, and the
#: same suite ran to completion every time at three, in roughly 100-180s. A hook that can be
#: killed is worse than a slow one: it reads as a failed commit. So a cap well under the
#: fast setting, with an override for a machine that has the room.
DEFAULT_WORKERS = 3
WORKERS_ENV = "NUMERA_TEST_WORKERS"

#: Used only if git cannot be asked: `git rev-parse --local-env-vars` as git 2.43 gives it.
LOCAL_GIT_VARIABLES = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
)  # fmt: skip

#: pytest's exit status when nothing was collected or everything was deselected --
#: exactly what testmon produces when the change reaches no test. Success here;
#: for `full` it would mean the suite vanished, and stays a failure.
NO_TESTS_COLLECTED = 5


def selectable(path: str) -> bool:
    return path.endswith(".py") and path.startswith(SELECTABLE_PREFIXES)


def inert(path: str) -> bool:
    return path in INERT_FILES or path.startswith(INERT_PREFIXES)


def implicit(path: str) -> bool:
    return path in IMPLICIT_FILES or path.startswith(IMPLICIT_PREFIXES)


# -- which code names a file ---------------------------------------------------------
#
# A mention is a string in the code, read two ways. A **whole** string literal may be a
# single path segment -- `ROOT / "openspec"`, `HERE / "fixtures"` -- and names every file
# under a directory of that name. A **word** inside any string names a file only when it
# is shaped like the file's path, the file's name, or a directory above it: "see
# openspec/specs" does, "the specs changed" does not. Docstrings and comments are prose
# and are skipped. The over-matches this leaves (a path in an error message) only make a
# run longer; the misses (a path computed from parts no string holds) are what the full
# suite at push is for.

Mentions = frozenset[tuple[str, str]]


def string_mentions(source: str) -> Mentions:
    """The strings a source holds, as ("whole", literal) and ("word", word) pairs.

    Source that is not Python -- a shell script under `bin/` -- is read as words.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset(("word", w) for w in source.split())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            found.add(("whole", node.value.strip("/")))
            found.update(("word", w.strip(".,;:()[]'\"`")) for w in node.value.split())
    return frozenset(found)


def names(mentions: Mentions, path: str) -> bool:
    parts = path.split("/")
    pathlike = {path, parts[-1]} | {"/".join(parts[:i]) for i in range(1, len(parts))}
    directories = set(parts[:-1])
    for kind, text in mentions:
        if kind == "whole" and text in directories:
            return True
        for p in pathlike:
            if text == p or text.startswith(p + "/") or text.endswith("/" + p) or f"/{p}/" in text:
                return True
    return False


def is_test_file(path: str) -> bool:
    return path.startswith("tests/") and Path(path).name.startswith("test_")


def tracked_sources() -> dict[str, Mentions]:
    """Every tracked file that can read another: Python anywhere, and the scripts in `bin/`."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    readers = [p for p in listed if p and (p.endswith(".py") or p.startswith("bin/"))]
    out = {}
    for path in readers:
        if path == HOOK or not (ROOT / path).is_file():
            continue
        out[path] = string_mentions((ROOT / path).read_text(encoding="utf-8", errors="replace"))
    return out


# -- what a commit runs --------------------------------------------------------------


class Plan(NamedTuple):
    full: list[str]  # why the full suite runs, one line per staged file that needs it
    named_tests: list[str]  # test files to run because they name a staged file
    testmon: bool  # staged Python under src/ or tests/: let testmon select


def _needs_full_suite(path: str, sources: dict[str, Mentions]) -> str | None:
    if implicit(path):
        return f"{path}: read by a tool, not by name"
    if path.endswith(".py"):
        return f"{path}: Python outside src/ and tests/, which a test may import by name"
    readers = [p for p, m in sources.items() if p != path and names(m, path)]
    other = [p for p in readers if not is_test_file(p)]
    if other:
        return f"{path}: named by {', '.join(other[:2])}{' ...' if len(other) > 2 else ''}"
    if not readers:
        return f"{path}: named by no test, so whatever reads it is out of sight"
    return None


def plan(paths: list[str], sources: dict[str, Mentions]) -> Plan:
    """What a commit of `paths` runs. `sources` is `tracked_sources()`, or a made-up one."""
    full: list[str] = []
    named: set[str] = set()
    testmon = False
    for path in paths:
        if selectable(path):
            testmon = True
        elif inert(path):
            continue
        elif reason := _needs_full_suite(path, sources):
            full.append(reason)
        else:
            named.update(p for p, m in sources.items() if is_test_file(p) and names(m, path))
    if full:
        return Plan(full=full, named_tests=[], testmon=False)
    return Plan(full=[], named_tests=sorted(named), testmon=testmon)


def workers() -> int:
    try:
        return max(1, int(os.environ[WORKERS_ENV]))
    except (KeyError, ValueError):
        return max(1, min(DEFAULT_WORKERS, os.cpu_count() or 1))


def project_python() -> Path | None:
    candidate = ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def environment_for_tests(environ: dict[str, str]) -> dict[str, str]:
    """This environment without the variables git sets to point a hook at its repository.

    Git exports them so that git commands *in the hook* act on the repository being
    committed to. Handed on to pytest, they do the same to every git command a test
    runs: committing from a worktree sets GIT_DIR, and each test asking git about a
    temporary directory got an answer about this repository instead -- 61 failures,
    none of them real. Which variables those are is git's to say, so git is asked
    (`--local-env-vars`, documented for exactly this: cleaning the environment before
    running git somewhere else); the list above is only the fallback.
    """
    try:
        listed = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        listed = []
    local = set(listed or LOCAL_GIT_VARIABLES)
    return {name: value for name, value in environ.items() if name not in local}


def _run(python: Path, args: list[str]) -> int:
    return subprocess.run(
        [str(python), "-m", "pytest", *args], cwd=ROOT, env=environment_for_tests(dict(os.environ))
    ).returncode


def full(python: Path) -> int:
    return _run(python, ["-n", str(workers()), "--dist", "worksteal", "-q"])


def commit(python: Path, paths: list[str]) -> int:
    if not paths or all(inert(p) for p in paths):
        return 0
    needs_sources = any(not selectable(p) and not inert(p) for p in paths)
    decided = plan(paths, tracked_sources() if needs_sources else {})
    if decided.full:
        print("testloop: full suite, because", flush=True)
        for reason in decided.full[:3]:
            print(f"  {reason}", flush=True)
        if len(decided.full) > 3:
            print(f"  ... and {len(decided.full) - 3} more", flush=True)
        return full(python)
    status = _testmon(python) if decided.testmon else 0
    if status == 0 and decided.named_tests:
        shown = ", ".join(Path(p).name for p in decided.named_tests)
        print(f"testloop: the test files that name the changed files: {shown}", flush=True)
        status = _run(python, ["-q", *decided.named_tests])
        status = 0 if status == NO_TESTS_COLLECTED else status
    return status


def _testmon(python: Path) -> int:
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
