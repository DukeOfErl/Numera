"""The scheduled workflows here: the keepalive's digest, and what no workflow here may do.

The shell steps are **executed**, against a stub `gh` and real `jq`, because a workflow is only
a program and an unexecuted one is the kind that fails on the first real run -- the digest was
merged once with its logic checked only against fixtures of its own making.

The first-use alert moved to the private DukeOfErl/numera-ops on 2026-11-23 (ADR-2050), with its
tests (`tests/test_workflows.py` there): this repository is public, and that job posts readers'
addresses. "A new reader's arrival reaches the operator on a schedule, with no mail account of
their own" (`user-identity`) is recorded in `test_spec_conformance.py` as tested there.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

needs_tools = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="jq and bash are needed to execute the workflow steps",
)


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def step_script(doc: dict, job: str, step_name: str) -> str:
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise AssertionError(f"no step named {step_name!r} in {job}")


STUB_GH = """#!/usr/bin/env bash
echo "$@" >> "$GH_CALLS"
case "$1 $2" in
  "issue list")
    # Applies the caller's own `--jq` to the fixture, as gh does, so what the
    # workflow's filter selects is what is tested -- not what the stub assumes.
    for i in "$@"; do [ "$prev" = "--jq" ] && expr="$i"; prev="$i"; done
    echo "${GH_STUB_ISSUES:-[]}" | jq -r "$expr"
    ;;
  "run list")
    # `--workflow NAME` selects which fixture to return.
    for i in "$@"; do last="$prev"; prev="$i"; [ "$last" = "--workflow" ] && wf="$i"; done
    var="GH_STUB_RUNS_$(echo "$wf" | tr '.-' '__' | tr a-z A-Z)"
    out="${!var:-[]}"
    expr=""; for i in "$@"; do [ "$p2" = "--jq" ] && expr="$i"; p2="$i"; done
    if [ -n "$expr" ]; then echo "$out" | jq -r "$expr"; else echo "$out"; fi
    ;;
esac
"""


@pytest.fixture
def sandbox(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(STUB_GH)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls.log"
    calls.write_text("")

    def run(script: str, **env) -> subprocess.CompletedProcess:
        full = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GH_CALLS": str(calls),
            "TITLE": "the title",
            **env,
        }
        return subprocess.run(
            ["bash", "-e", "-c", script], cwd=tmp_path, env=full, capture_output=True, text=True
        )

    run.dir = tmp_path
    run.calls = lambda: calls.read_text().splitlines()
    return run


def issue(number: int, title: str) -> str:
    return f'[{{"number":{number},"title":"{title}"}}]'


def runs(*conclusions: str) -> str:
    items = ",".join(
        f'{{"conclusion":"{c}","url":"https://example/run/{i}"}}' for i, c in enumerate(conclusions)
    )
    return f"[{items}]"


# -- the digest: one standing issue, the keepalive, and the silence of a good day -------

DIGEST = "keepalive-digest.yml"
SUMMARY = "Summarise the last 24 hours"
WRITE = "Write to the standing issue"


def test_the_digest_watches_the_keepalive_and_nothing_else():
    """first-use.yml left with its own digest; a stale entry here would report "no run" daily."""
    script = step_script(load(DIGEST), "digest", SUMMARY)
    assert re.search(r"for workflow in keepalive\.yml; do", script)


@needs_tools
def test_the_digest_says_nothing_when_the_keepalive_ran_and_passed(sandbox):
    sandbox(
        step_script(load(DIGEST), "digest", SUMMARY), GH_STUB_RUNS_KEEPALIVE_YML=runs("success")
    )
    assert (sandbox.dir / "report.md").read_text() == ""


@needs_tools
def test_the_digest_does_not_count_a_cancelled_or_unfinished_run_as_a_failure(sandbox):
    script = step_script(load(DIGEST), "digest", SUMMARY)
    sandbox(script, GH_STUB_RUNS_KEEPALIVE_YML=runs("cancelled", ""))
    assert (sandbox.dir / "report.md").read_text() == ""


@needs_tools
def test_a_failing_keepalive_run_is_reported_by_name_with_its_links(sandbox):
    script = step_script(load(DIGEST), "digest", SUMMARY)
    sandbox(script, GH_STUB_RUNS_KEEPALIVE_YML=runs("success", "failure", "timed_out"))
    report = (sandbox.dir / "report.md").read_text()
    assert "keepalive.yml" in report and "2 of 3" in report
    assert report.count("https://example/run/") == 2


@needs_tools
def test_a_keepalive_that_did_not_run_at_all_is_reported(sandbox):
    # A paused schedule looks exactly like a passing one; only "no runs" shows it.
    sandbox(step_script(load(DIGEST), "digest", SUMMARY), GH_STUB_RUNS_KEEPALIVE_YML="[]")
    report = (sandbox.dir / "report.md").read_text()
    assert "keepalive.yml" in report and "no run" in report


@needs_tools
def test_the_digest_mentions_the_owner_when_it_has_something_to_say(sandbox):
    (sandbox.dir / "report.md").write_text("- `keepalive.yml`: 1 of 2 runs failed\n")
    sandbox(
        step_script(load(DIGEST), "digest", WRITE),
        GH_STUB_ISSUES=issue(7, "scheduled workflow problems"),
        TITLE="scheduled workflow problems",
        OWNER="octocat",
    )
    assert (sandbox.dir / "body.md").read_text().startswith("@octocat\n")
    assert any(
        c.startswith("issue comment 7") and "--body-file body.md" in c for c in sandbox.calls()
    )


@needs_tools
def test_the_digest_says_nothing_when_it_has_nothing_to_say(sandbox):
    (sandbox.dir / "report.md").write_text("")
    sandbox(
        step_script(load(DIGEST), "digest", WRITE),
        GH_STUB_ISSUES=issue(7, "scheduled workflow problems"),
        TITLE="scheduled workflow problems",
        OWNER="octocat",
    )
    assert sandbox.calls() == []


@needs_tools
def test_the_digest_does_not_post_into_a_near_miss_title(sandbox):
    (sandbox.dir / "report.md").write_text("- `keepalive.yml`: 1 of 2 runs failed\n")
    sandbox(
        step_script(load(DIGEST), "digest", WRITE),
        GH_STUB_ISSUES=issue(9, "Notes on scheduled workflow problems in March"),
        TITLE="scheduled workflow problems",
        OWNER="octocat",
    )
    calls = sandbox.calls()
    assert not any(c.startswith("issue comment 9") for c in calls)
    assert any(c.startswith("issue create") for c in calls)


# -- what no workflow here may do -----------------------------------------------------------


#: What a job that names readers would mention: the alert's command, setting and exclusions,
#: `numera-pending` (which also lists readers' addresses, from the Neon control plane) and the
#: key it needs. A text match over what runs, so a name not on this list gets past it.
READER_MARKERS = (
    "TRAIL_READ_URL",
    "first_use",
    "first-use",
    "FIRST_USE_EXCLUDE",
    "numera-pending",
    "numera_ask.pending",
    "NEON_API_KEY",
)


def test_no_workflow_here_reads_the_trail_or_reports_readers():
    """The repository is public, and so are its issues and Actions logs (ADR-2050). The job
    that names readers lives in DukeOfErl/numera-ops; this fails if it, or a job like it --
    `numera-pending` included -- comes back, in a workflow or a composite action."""
    github = ROOT / ".github"
    files = sorted([*github.rglob("*.yml"), *github.rglob("*.yaml")])
    assert any(path.parent == WORKFLOWS for path in files), "found no workflows to check"
    for path in files:
        # What a workflow does, not what its comments say about where the job went.
        text = "\n".join(
            line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
        )
        for marker in READER_MARKERS:
            assert marker not in text, f"{path.relative_to(ROOT)} mentions {marker}"
