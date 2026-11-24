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


def sources(testloop, files: dict[str, str]) -> dict:
    """A made-up repository: path -> source text, as `plan` receives it."""
    return {path: testloop.string_mentions(text) for path, text in files.items()}


NOBODY = {"tests/test_other.py": "def test_x():\n    assert True\n"}


@pytest.mark.parametrize(
    "path",
    ["src/numera_ask/units.py", "tests/test_units.py", "src/bionumbers_ingest/cleaning.py"],
)
def test_python_under_src_and_tests_is_left_to_testmon(testloop, path):
    plan = testloop.plan([path], sources(testloop, NOBODY))
    assert plan == testloop.Plan(full=[], named_tests=[], testmon=True)


def test_a_file_named_by_one_test_runs_that_test_and_no_other(testloop):
    repo = {
        "tests/test_readme.py": 'TEXT = (ROOT / "README.md").read_text()\n',
        **NOBODY,
    }
    plan = testloop.plan(["README.md"], sources(testloop, repo))
    assert plan == testloop.Plan(full=[], named_tests=["tests/test_readme.py"], testmon=False)


def test_a_file_no_test_names_runs_the_full_suite(testloop):
    # Named nowhere may mean read where the hook cannot see -- a glob, a computed path.
    plan = testloop.plan(["README.md"], sources(testloop, NOBODY))
    assert plan.full and "README.md" in plan.full[0]
    assert plan.named_tests == []


@pytest.mark.parametrize(
    "reader",
    [
        "src/numera_ask/web.py",  # the app reads it, and testmon cannot follow a read
        "bin/door-demo-chart",  # a script, not Python by extension
        "tests/conftest.py",  # a helper: every test that uses it reads the file
        "tests/store_double.py",
    ],
)
def test_a_file_named_by_code_or_a_test_helper_runs_the_full_suite(testloop, reader):
    repo = {
        reader: 'PATH = HERE / "door_demo.json"\n',
        "tests/test_door.py": 'PATH = HERE / "door_demo.json"\n',
    }
    plan = testloop.plan(["src/numera_ask/door_demo.json"], sources(testloop, repo))
    assert plan.full and reader in plan.full[0]
    assert plan.named_tests == []


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",  # pytest's options, the dependencies
        "uv.lock",
        ".gitignore",  # git reads it when a test asks what is tracked
        ".python-version",
        ".streamlit/config.toml",  # Streamlit reads it in every page test
        "bin/keepalive.py",  # Python outside src/ and tests/: imported, not named
        "streamlit_app.py",
    ],
)
def test_a_file_a_tool_reads_runs_the_full_suite_even_when_a_test_names_it(testloop, path):
    repo = {"tests/test_names_it.py": f'P = ROOT / "{path}"\n'}
    plan = testloop.plan([path], sources(testloop, repo))
    assert plan.full and path in plan.full[0]


@pytest.mark.parametrize("path", ["CHANGELOG.md", "CLAUDE.md", "docs/decisions/0010-x.md"])
def test_files_no_test_reads_need_no_tests(testloop, path):
    assert testloop.inert(path)
    assert testloop.plan([path], sources(testloop, NOBODY)) == testloop.Plan([], [], False)


def test_a_prefix_is_not_a_substring(testloop):
    # `docs_notes/` is not `docs/`.
    assert not testloop.inert("docs_notes/x.md")
    assert not testloop.inert("src/numera_validator/CLAUDE.md")  # a path, not a name
    assert testloop.plan(["docs_notes/x.md"], sources(testloop, NOBODY)).full
    assert not testloop.selectable("src/x.pyc")
    assert not testloop.selectable("mysrc/x.py")


def test_python_and_a_named_file_together_run_testmon_and_the_named_tests(testloop):
    repo = {"tests/test_readme.py": 'TEXT = (ROOT / "README.md").read_text()\n', **NOBODY}
    staged = ["src/numera_ask/units.py", "README.md", "CHANGELOG.md"]
    plan = testloop.plan(staged, sources(testloop, repo))
    assert plan == testloop.Plan(full=[], named_tests=["tests/test_readme.py"], testmon=True)


def test_one_file_that_needs_the_full_suite_outweighs_the_rest(testloop):
    repo = {"tests/test_readme.py": 'TEXT = (ROOT / "README.md").read_text()\n', **NOBODY}
    plan = testloop.plan(["README.md", "pyproject.toml"], sources(testloop, repo))
    assert len(plan.full) == 1 and "pyproject.toml" in plan.full[0]


def test_nothing_staged_needs_nothing(testloop):
    assert testloop.plan([], sources(testloop, NOBODY)) == testloop.Plan([], [], False)


# -- what counts as naming a file ---------------------------------------------------
#
# The dimension these read is *how* a string holds the name, so each negative case holds
# the same name in a form that is not a path.

FILE = "openspec/specs/user-identity/spec.md"


@pytest.mark.parametrize(
    "source",
    [
        'P = ROOT / "openspec/specs/user-identity/spec.md"',  # the whole path
        'P = HERE / "spec.md"',  # the name alone
        'SPECS = ROOT.joinpath("openspec", "specs").rglob("*.md")',  # a directory above it
        'P = ROOT / "openspec"',
        'P = f"{ROOT}/openspec/specs/{name}/spec.md"',  # inside an f-string
        'assert ok, "see openspec/specs for the wording"',  # a path-shaped word in prose
        'CMD = "cat $ROOT/openspec/specs/*.md"',  # the path in the middle of a word
    ],
)
def test_a_string_that_holds_the_path_or_a_directory_above_it_names_the_file(testloop, source):
    assert testloop.names(testloop.string_mentions(source), FILE)


@pytest.mark.parametrize(
    "source",
    [
        'assert ok, "the specs changed"',  # a directory's bare name as a word, not a path
        '"""Reads openspec/specs/user-identity/spec.md."""',  # a docstring is prose
        "# ROOT / 'openspec'",  # a comment is not a string
        'P = ROOT / "openspec-old"',  # a prefix is not a segment
        'P = ROOT / "my_spec.md"',
    ],
)
def test_the_same_words_not_as_a_path_do_not_name_the_file(testloop, source):
    assert not testloop.names(testloop.string_mentions(source), FILE)


def test_a_bare_directory_name_counts_only_as_a_whole_string(testloop):
    assert testloop.names(testloop.string_mentions('P = HERE / "specs"'), FILE)
    assert not testloop.names(testloop.string_mentions('m = "specs are fine"'), FILE)


def test_a_file_that_is_not_python_is_read_as_words(testloop):
    script = "#!/bin/sh\ncat openspec/specs/user-identity/spec.md\n"
    assert testloop.names(testloop.string_mentions(script), FILE)


# -- against this repository -----------------------------------------------------------


@pytest.fixture(scope="module")
def tracked(testloop):
    return testloop.tracked_sources()


def test_a_workflow_change_runs_the_test_that_reads_the_workflows(testloop, tracked):
    """The blind spot this replaced: `.github/` was called inert, the tripwire grepped for
    the string ".github/", and `test_scheduled_workflows.py` reads every workflow through
    `ROOT / ".github" / "workflows"` -- so a commit editing a workflow ran no test at all."""
    plan = testloop.plan([".github/workflows/checks.yml"], tracked)
    assert "tests/test_scheduled_workflows.py" in plan.named_tests or plan.full


def test_a_readme_change_runs_the_test_that_quotes_the_readme(testloop, tracked):
    plan = testloop.plan(["README.md"], tracked)
    assert "tests/test_web_driver.py" in plan.named_tests or plan.full


def test_the_hook_does_not_count_itself_as_a_reader(testloop, tracked):
    # Its lists of paths are configuration; were they reads, every path on them would
    # run the full suite.
    assert "bin/testloop.py" not in tracked


def test_scripts_without_an_extension_count_as_readers(tracked):
    # A test runs `bin/door-demo-chart`; what it reads, the test reads.
    assert {"bin/door-demo-chart", "bin/last-question"} <= set(tracked)


# -- what the commit hook actually starts ---------------------------------------------


@pytest.fixture
def started(testloop, monkeypatch):
    """Every pytest the hook starts, as its argument list; `exits` sets their statuses."""
    calls: list[list[str]] = []
    exits: list[int] = []

    def run(args, **kwargs):
        if "pytest" in args:
            calls.append(args[args.index("pytest") + 1 :])
            return subprocess.CompletedProcess(args, exits.pop(0) if exits else 0)
        return subprocess.CompletedProcess(args, 0, stdout="")

    repo = {"tests/test_readme.py": 'TEXT = (ROOT / "README.md").read_text()\n', **NOBODY}
    monkeypatch.setattr(testloop.subprocess, "run", run)
    monkeypatch.setattr(testloop, "tracked_sources", lambda: sources(testloop, repo))
    monkeypatch.setattr(testloop, "ROOT", Path("/nowhere"))  # no .testmondata: no stat surprises
    return calls, exits


PYTHON = Path("/venv/bin/python")


def test_a_named_file_starts_only_the_tests_that_name_it(testloop, started):
    calls, _ = started
    assert testloop.commit(PYTHON, ["README.md"]) == 0
    assert calls == [["-q", "tests/test_readme.py"]]


def test_a_file_that_needs_the_full_suite_starts_the_full_suite(testloop, started):
    calls, _ = started
    testloop.commit(PYTHON, ["pyproject.toml"])
    assert len(calls) == 1 and "-n" in calls[0] and "tests/test_readme.py" not in calls[0]


def test_python_and_a_named_file_start_testmon_then_the_named_tests(testloop, started):
    calls, _ = started
    testloop.commit(PYTHON, ["src/numera_ask/units.py", "README.md"])
    assert calls == [["--testmon-forceselect", "-q"], ["-q", "tests/test_readme.py"]]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (1, 1),  # a named test failed: the commit is refused
        (5, 0),  # nothing collected -- every test in the file deselected by a marker
    ],
)
def test_the_named_run_s_status_is_the_commit_s(testloop, started, status, expected):
    calls, exits = started
    exits.append(status)
    assert testloop.commit(PYTHON, ["README.md"]) == expected


# -- the tripwire: the inert list is a claim about the code, so check the code ---------

#: code that names an "inert" path, and why that does not make it a dependency. A new
#: mention is a new reason to look, which is the point.
KNOWN_MENTIONS = {
    "docs/": {
        # asks git whether `docs/` is *tracked*; no edit inside it changes that answer.
        "tests/test_answer_sheet.py",
        # messages pointing the reader at docs/roadmap.md, not reads of it.
        "src/numera_ask/corpus.py",
        "src/numera_ask/eval_cli.py",
    },
}


def test_no_code_reads_a_path_the_hook_calls_inert(testloop, tracked):
    for token in sorted(testloop.INERT_FILES | set(testloop.INERT_PREFIXES)):
        mentioning = {
            path
            for path, mentions in tracked.items()
            if path != "tests/test_testloop.py" and testloop.names(mentions, token.rstrip("/"))
        }
        assert mentioning == KNOWN_MENTIONS.get(token, set()), (
            f"{token!r} is called inert but this code names it: {sorted(mentioning)}. "
            "Either it reads it (remove it from the inert list) or the mention is "
            "harmless (add it to KNOWN_MENTIONS with the reason)."
        )


# -- which tier runs at which git hook ------------------------------------------------
#
# Read from `.pre-commit-config.yaml` with pre-commit's own rule: a hook with no `stages:`
# (and no `default_stages:`) runs at every installed hook type. That rule is how the
# commit tier came to run at push and merge too, and the full suite ran twice each time.


def _testloop_hooks_by_hook_type() -> dict[str, list[str]]:
    import yaml

    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    installed = config["default_install_hook_types"]
    default = config.get("default_stages", installed)
    hooks = [
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook.get("entry", "").startswith("bin/testloop.py")  # mirrored hooks have none
    ]
    return {
        hook_type: [h["id"] for h in hooks if hook_type in h.get("stages", default)]
        for hook_type in installed
    }


def test_each_git_hook_runs_exactly_one_tier_of_the_suite():
    assert _testloop_hooks_by_hook_type() == {
        "pre-commit": ["testloop-commit"],
        # The full suite at push and merge is kept (Yoav, 2026-11-24): once, not twice.
        "pre-push": ["testloop-full"],
        "pre-merge-commit": ["testloop-full"],
    }


def test_workers_default_is_capped_not_all_cores(testloop, monkeypatch):
    monkeypatch.delenv(testloop.WORKERS_ENV, raising=False)
    monkeypatch.setattr(testloop.os, "cpu_count", lambda: 64)
    assert testloop.workers() == testloop.DEFAULT_WORKERS
    # Six ran an 8 GB machine out of memory once, mid-commit (exit 137); the default must
    # stay at or under the count that did not.
    assert testloop.DEFAULT_WORKERS <= 3
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
