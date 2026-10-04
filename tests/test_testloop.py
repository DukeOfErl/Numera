"""Which changes the commit-time hook trusts testmon with, and which it will not.

Written from the requirement: testmon follows Python, so any change to a file a test
merely *reads* must fall back to the full suite -- a hook that passes on a change
nothing checked is the failure this exists to prevent.
"""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def testloop():
    spec = importlib.util.spec_from_file_location("testloop", ROOT / "bin" / "testloop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "path",
    ["src/scinumbers_ask/units.py", "tests/test_units.py", "src/bionumbers_ingest/cleaning.py"],
)
def test_python_under_src_and_tests_is_left_to_testmon(testloop, path):
    assert testloop.reasons_for_full_suite([path]) == []


@pytest.mark.parametrize(
    "path",
    [
        "README.md",  # quoted by wording tests
        "CLAUDE.md",
        "sql/accounts.sql",
        "src/scinumbers_ask/door_demo.json",  # a data file inside src/: not Python
        "tests/fixtures/entries.json",  # likewise inside tests/
        "openspec/specs/user-identity/spec.md",
        ".claude/rules/testing.md",
        "bin/keepalive.py",  # Python, but outside src/ and tests/, and a test loads it
        "pyproject.toml",
        "uv.lock",
        ".gitignore",
        ".pre-commit-config.yaml",
    ],
)
def test_a_file_a_test_may_read_forces_the_full_suite(testloop, path):
    assert testloop.reasons_for_full_suite([path]) == [path]


@pytest.mark.parametrize(
    "path", ["CHANGELOG.md", "docs/decisions/0010-x.md", ".github/workflows/checks.yml"]
)
def test_files_no_test_reads_need_no_tests(testloop, path):
    assert testloop.inert(path)
    assert testloop.reasons_for_full_suite([path]) == []


def test_a_prefix_is_not_a_substring(testloop):
    # `docs_notes/` and `.github-old/` are not `docs/` and `.github/`.
    assert testloop.reasons_for_full_suite(["docs_notes/x.md", ".github-old/x.yml"]) != []
    assert not testloop.selectable("src/x.pyc")
    assert not testloop.selectable("mysrc/x.py")


def test_one_unvouched_file_among_selectable_ones_names_only_itself(testloop):
    staged = ["src/scinumbers_ask/units.py", "README.md", "CHANGELOG.md", "tests/test_units.py"]
    assert testloop.reasons_for_full_suite(staged) == ["README.md"]


def test_nothing_staged_needs_nothing(testloop):
    assert testloop.reasons_for_full_suite([]) == []


# -- the tripwire: the inert list is a claim about the tests, so check the tests -------

#: tests that mention an "inert" path, and why that does not make it a dependency.
#: A new mention is a new reason to look, which is the point.
KNOWN_MENTIONS = {
    # asks git whether `docs/` is *tracked*; no edit inside it changes that answer.
    "docs/": {"test_answer_sheet.py"},
}


def test_no_test_reads_a_path_the_hook_calls_inert(testloop):
    tokens = sorted(testloop.INERT_FILES | set(testloop.INERT_PREFIXES))
    for token in tokens:
        mentioning = {
            p.name
            for p in (ROOT / "tests").glob("*.py")
            if p.name != Path(__file__).name and token in p.read_text(encoding="utf-8")
        }
        assert mentioning == KNOWN_MENTIONS.get(token, set()), (
            f"{token!r} is called inert but tests mention it: {sorted(mentioning)}. "
            "Either a test now reads it (remove it from the inert list) or the mention "
            "is harmless (add it to KNOWN_MENTIONS with the reason)."
        )


def test_workers_default_is_capped_not_all_cores(testloop, monkeypatch):
    monkeypatch.delenv(testloop.WORKERS_ENV, raising=False)
    monkeypatch.setattr(testloop.os, "cpu_count", lambda: 64)
    assert testloop.workers() == testloop.DEFAULT_WORKERS
    monkeypatch.setattr(testloop.os, "cpu_count", lambda: 2)
    assert testloop.workers() == 2


def test_workers_can_be_overridden_and_a_bad_value_falls_back(testloop, monkeypatch):
    monkeypatch.setenv(testloop.WORKERS_ENV, "3")
    assert testloop.workers() == 3
    monkeypatch.setenv(testloop.WORKERS_ENV, "many")
    assert testloop.workers() >= 1


# --- the environment the tests run in -------------------------------------------
#
# Git exports variables to a hook that point every git command at this repository.
# Committing from a worktree sets GIT_DIR, and the hook handed it to pytest unchanged,
# so every test asking git about a temporary directory got an answer about this
# repository: 61 failures, none of them real (found 2026-10-04).


def test_the_tests_do_not_inherit_the_repository_git_pointed_the_hook_at(testloop):
    hook = {
        "GIT_DIR": "/repo/.git/worktrees/x",
        "GIT_INDEX_FILE": "/repo/.git/worktrees/x/index",
        "GIT_WORK_TREE": "/repo",
        "GIT_COMMON_DIR": "/repo/.git",
        "PATH": "/usr/bin",
        testloop.WORKERS_ENV: "3",
        # Not a pointer to a repository: who is committing. It must survive, or the
        # rule has become "drop everything named GIT_", which is not the rule.
        "GIT_AUTHOR_NAME": "Someone",
    }
    cleaned = testloop.environment_for_tests(hook)
    for name in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
        assert name not in cleaned, name
    assert cleaned["PATH"] == "/usr/bin"
    assert cleaned[testloop.WORKERS_ENV] == "3"
    assert cleaned["GIT_AUTHOR_NAME"] == "Someone"


def test_git_asked_about_a_temporary_directory_answers_about_that_directory(testloop, tmp_path):
    """The failure itself, end to end: with GIT_DIR pointing at this repository,
    git claims a fresh temporary directory is inside a work tree. The cleaned
    environment makes it answer about the directory it was asked about."""
    git_dir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    hook = {**os.environ, "GIT_DIR": git_dir}

    def inside_work_tree(env: dict) -> bool:
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "--is-inside-work-tree"],
            env=env,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "true"

    assert inside_work_tree(hook), "the canary: GIT_DIR should mislead git here"
    assert not inside_work_tree(testloop.environment_for_tests(hook))


def test_pytest_is_started_with_the_cleaned_environment(testloop, monkeypatch):
    seen = {}

    def run(args, **kwargs):
        if "pytest" in args:
            seen.update(kwargs)
        # Empty for git's own list, so the fallback list is exercised as well.
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setenv("GIT_DIR", "/repo/.git")
    monkeypatch.setattr(testloop.subprocess, "run", run)
    testloop.full(Path("/venv/bin/python"))
    assert "env" in seen and "GIT_DIR" not in seen["env"]
