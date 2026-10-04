"""The scheduled workflows: what runs, what it may hold, and what it says.

Two kinds of check. The shell steps are **executed**, against a stub `gh` and real
`jq`, because a workflow is only a program and an unexecuted one is the kind that
fails on the first real run -- the digest was merged once with its logic checked only
against fixtures of its own making. And the structure is read from the YAML for the
properties no step can show: that nothing here holds a credential it should not.

Requirement text these map to: "A new reader's arrival reaches the operator on a
schedule, with no mail account of their own" (`user-identity`, add-first-use-notice).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta
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


def triggers(doc: dict) -> dict:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    return doc.get("on") or doc[True]


def step_script(doc: dict, job: str, step_name: str) -> str:
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise AssertionError(f"no step named {step_name!r} in {job}")


def all_run_lines(doc: dict) -> list[str]:
    lines = []
    for job in doc["jobs"].values():
        for step in job["steps"]:
            lines += step.get("run", "").splitlines()
    return lines


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
    wf="${wf:-$4}"
    var="GH_STUB_RUNS_$(echo "$wf" | tr '.-' '__' | tr a-z A-Z)"
    out="${!var:-[]}"
    expr=""; for i in "$@"; do [ "$p2" = "--jq" ] && expr="$i"; p2="$i"; done
    if [ -n "$expr" ]; then echo "$out" | jq -r "$expr"; else echo "$out"; fi
    ;;
esac
"""


STUB_UV = """#!/usr/bin/env bash
echo "$@" >> "$UV_CALLS"
echo "${UV_STUB_OUT:-}"
exit "${UV_STUB_EXIT:-0}"
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
    uv_stub = bin_dir / "uv"
    uv_stub.write_text(STUB_UV)
    uv_stub.chmod(uv_stub.stat().st_mode | stat.S_IEXEC)
    uv_calls = tmp_path / "uv_calls.log"
    uv_calls.write_text("")

    def run(script: str, **env) -> subprocess.CompletedProcess:
        full = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GH_CALLS": str(calls),
            "UV_CALLS": str(uv_calls),
            "TITLE": "the title",
            **env,
        }
        return subprocess.run(
            ["bash", "-e", "-c", script], cwd=tmp_path, env=full, capture_output=True, text=True
        )

    run.dir = tmp_path
    run.calls = lambda: calls.read_text().splitlines()
    run.uv_calls = lambda: uv_calls.read_text().splitlines()
    return run


def issue(number: int, title: str) -> str:
    return f'[{{"number":{number},"title":"{title}"}}]'


def runs(*conclusions: str) -> str:
    items = ",".join(
        f'{{"conclusion":"{c}","url":"https://example/run/{i}"}}' for i, c in enumerate(conclusions)
    )
    return f"[{items}]"


# -- the digest: one standing issue, both workflows, and the silence of a good day -----


@needs_tools
def test_the_digest_says_nothing_when_both_workflows_ran_and_passed(sandbox):
    script = step_script(load("keepalive-digest.yml"), "digest", "Summarise the last 24 hours")
    sandbox(
        script,
        GH_STUB_RUNS_KEEPALIVE_YML=runs("success", "success"),
        GH_STUB_RUNS_FIRST_USE_YML=runs("success"),
    )
    assert (sandbox.dir / "report.md").read_text() == ""


@needs_tools
def test_the_digest_does_not_count_a_cancelled_or_unfinished_run_as_a_failure(sandbox):
    script = step_script(load("keepalive-digest.yml"), "digest", "Summarise the last 24 hours")
    sandbox(
        script,
        GH_STUB_RUNS_KEEPALIVE_YML=runs("cancelled", ""),
        GH_STUB_RUNS_FIRST_USE_YML=runs("success"),
    )
    assert (sandbox.dir / "report.md").read_text() == ""


@needs_tools
def test_a_failing_first_use_run_is_reported_by_name_and_keepalive_is_not(sandbox):
    # The reason the digest was widened: GitHub's failure mail is off, so without
    # this a first-use job that cannot reach the database would be silent.
    script = step_script(load("keepalive-digest.yml"), "digest", "Summarise the last 24 hours")
    sandbox(
        script,
        GH_STUB_RUNS_KEEPALIVE_YML=runs("success"),
        GH_STUB_RUNS_FIRST_USE_YML=runs("success", "failure", "timed_out"),
    )
    report = (sandbox.dir / "report.md").read_text()
    assert "first-use.yml" in report and "2 of 3" in report
    assert "keepalive.yml" not in report
    assert report.count("https://example/run/") == 2


@needs_tools
def test_a_workflow_that_did_not_run_at_all_is_reported(sandbox):
    # A paused schedule looks exactly like a passing one; only "no runs" shows it.
    script = step_script(load("keepalive-digest.yml"), "digest", "Summarise the last 24 hours")
    sandbox(
        script,
        GH_STUB_RUNS_KEEPALIVE_YML=runs("success"),
        GH_STUB_RUNS_FIRST_USE_YML="[]",
    )
    report = (sandbox.dir / "report.md").read_text()
    assert "first-use.yml" in report and "no run" in report
    assert "keepalive.yml" not in report


@needs_tools
def test_both_workflows_failing_are_two_entries_in_one_report(sandbox):
    script = step_script(load("keepalive-digest.yml"), "digest", "Summarise the last 24 hours")
    sandbox(
        script,
        GH_STUB_RUNS_KEEPALIVE_YML=runs("failure"),
        GH_STUB_RUNS_FIRST_USE_YML="[]",
    )
    report = (sandbox.dir / "report.md").read_text()
    assert "keepalive.yml" in report and "first-use.yml" in report


# -- first-use: delivery ---------------------------------------------------------------

TELL = "Tell the operator"


@needs_tools
def test_a_run_with_nobody_new_delivers_nothing(sandbox):
    (sandbox.dir / "report.md").write_text("")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    result = sandbox(script, TEST="false")
    assert result.returncode == 0, result.stderr
    assert sandbox.calls() == [], "a quiet hour must not touch GitHub at all"


@needs_tools
def test_a_report_becomes_a_comment_on_the_one_standing_issue(sandbox):
    (sandbox.dir / "report.md").write_text("  new@example.org  signed in\n")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    sandbox(
        script,
        TEST="false",
        GH_STUB_ISSUES=issue(42, "first use"),
        TITLE="first use",
        OWNER="octocat",
    )
    calls = sandbox.calls()
    assert any(c.startswith("issue comment 42") and "--body-file body.md" in c for c in calls)
    assert not any(c.startswith("issue create") for c in calls), "one issue, not one per reader"


@needs_tools
def test_every_comment_mentions_the_owner_and_still_carries_the_report(sandbox):
    # The issue is opened by the Actions bot, so the owner is not "participating" in
    # it and "Participating and @mentions" mail would never arrive -- except for a
    # mention, which is exactly what that setting does notify on.
    (sandbox.dir / "report.md").write_text("  new@example.org  signed in\n")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    sandbox(
        script,
        TEST="false",
        GH_STUB_ISSUES=issue(42, "first use"),
        TITLE="first use",
        OWNER="octocat",
    )
    body = (sandbox.dir / "body.md").read_text()
    assert body.startswith("@octocat\n")
    assert "new@example.org  signed in" in body


@needs_tools
def test_the_first_report_also_mentions_the_owner(sandbox):
    (sandbox.dir / "report.md").write_text("  new@example.org  signed in\n")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    sandbox(script, TEST="false", GH_STUB_ISSUES="[]", TITLE="first use", OWNER="octocat")
    assert (sandbox.dir / "body.md").read_text().startswith("@octocat\n")
    assert any(c.startswith("issue create") and "--body-file body.md" in c for c in sandbox.calls())


@needs_tools
def test_the_digest_mentions_the_owner_when_it_has_something_to_say(sandbox):
    (sandbox.dir / "report.md").write_text("- `first-use.yml`: 1 of 2 runs failed\n")
    script = step_script(load("keepalive-digest.yml"), "digest", "Write to the standing issue")
    sandbox(
        script,
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
    script = step_script(load("keepalive-digest.yml"), "digest", "Write to the standing issue")
    sandbox(
        script,
        GH_STUB_ISSUES=issue(7, "scheduled workflow problems"),
        TITLE="scheduled workflow problems",
        OWNER="octocat",
    )
    assert sandbox.calls() == []


@needs_tools
def test_the_first_report_opens_the_standing_issue(sandbox):
    (sandbox.dir / "report.md").write_text("  new@example.org  signed in\n")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    sandbox(script, TEST="false", GH_STUB_ISSUES="[]", TITLE="first use")
    assert any(c.startswith("issue create") for c in sandbox.calls())


@needs_tools
def test_a_near_miss_title_is_not_the_standing_issue(sandbox):
    # `"first use" in:title` is a phrase search: it also finds "Improve first use
    # experience". Posting readers' addresses into an unrelated issue is the cost of
    # trusting the search, so the title is matched exactly after it.
    (sandbox.dir / "report.md").write_text("  new@example.org  signed in\n")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    sandbox(
        script,
        TEST="false",
        GH_STUB_ISSUES=issue(9, "Improve first use experience"),
        TITLE="first use",
        OWNER="octocat",
    )
    calls = sandbox.calls()
    assert not any(c.startswith("issue comment 9") for c in calls)
    assert any(c.startswith("issue create") for c in calls)


@needs_tools
def test_the_digest_does_not_post_into_a_near_miss_title_either(sandbox):
    (sandbox.dir / "report.md").write_text("- `first-use.yml`: 1 of 2 runs failed\n")
    script = step_script(load("keepalive-digest.yml"), "digest", "Write to the standing issue")
    sandbox(
        script,
        GH_STUB_ISSUES=issue(9, "Notes on scheduled workflow problems in March"),
        TITLE="scheduled workflow problems",
        OWNER="octocat",
    )
    calls = sandbox.calls()
    assert not any(c.startswith("issue comment 9") for c in calls)
    assert any(c.startswith("issue create") for c in calls)


@needs_tools
def test_the_test_input_posts_a_marked_line_even_when_nobody_is_new(sandbox):
    (sandbox.dir / "report.md").write_text("")
    script = step_script(load("first-use.yml"), "first-use", TELL)
    sandbox(script, TEST="true", GH_STUB_ISSUES=issue(42, "first use"), TITLE="first use")
    assert any(c.startswith("issue comment 42") for c in sandbox.calls())
    assert "TEST" in (sandbox.dir / "report.md").read_text()


# -- first-use: what it may hold and where it runs -------------------------------------


def test_it_runs_every_hour_and_not_on_keepalives_minute():
    crons = [entry["cron"] for entry in triggers(load("first-use.yml"))["schedule"]]
    assert len(crons) == 1
    minute, hour, day, month, weekday = crons[0].split()
    assert (hour, day, month, weekday) == ("*", "*", "*", "*"), "hourly"
    keepalive_minute = triggers(load("keepalive.yml"))["schedule"][0]["cron"].split()[0]
    assert minute != keepalive_minute


def test_it_can_be_run_by_hand_with_a_test_input_that_defaults_off():
    inputs = triggers(load("first-use.yml"))["workflow_dispatch"]["inputs"]
    assert inputs["test"]["default"] is False


def test_the_only_secret_is_the_read_only_url_and_no_mail_credential_exists():
    text = (WORKFLOWS / "first-use.yml").read_text()
    used = set(re.findall(r"secrets\.([A-Z0-9_]+)", text))
    assert used == {"SCINUMBERS_TRAIL_READ_URL"}, (
        f"first-use holds {sorted(used)}: it must hold the read-only URL and nothing else "
        "(not the Neon API key, which can delete the project, and not a mail credential)"
    )


def test_it_may_write_issues_and_nothing_else():
    permissions = load("first-use.yml")["permissions"]
    writes = {name for name, level in permissions.items() if level == "write"}
    assert writes == {"issues"}
    # `actions: read` is there for the run history the window is computed from.
    assert set(permissions) <= {"contents", "actions", "issues"}


def test_the_runner_is_pinned_not_the_floating_label():
    runner = load("first-use.yml")["jobs"]["first-use"]["runs-on"]
    assert runner != "ubuntu-latest"


def test_two_ticks_cannot_overlap():
    assert load("first-use.yml")["concurrency"]["cancel-in-progress"] is False
    assert load("first-use.yml")["concurrency"]["group"]


def test_no_address_is_written_into_the_file_and_exclusions_come_from_a_variable():
    text = (WORKFLOWS / "first-use.yml").read_text()
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text), "an address is in a committed file"
    assert "vars.FIRST_USE_EXCLUDE" in text


def test_the_report_is_never_printed_to_the_log():
    # Reader addresses are in the report. The issue is where they belong; the log of
    # a run is a second, wider place. Any line that prints the file without
    # redirecting it would put them there.
    for line in all_run_lines(load("first-use.yml")):
        if "report.md" in line and re.match(r"\s*(cat|echo|printf|tee)\b", line):
            assert ">" in line, f"prints the report to the log: {line.strip()}"


def test_the_dependencies_of_the_job_that_holds_the_credential_are_exact():
    # It runs with the database URL in its environment, 24 times a day, outside
    # `uv.lock`. A floating release would run with that URL.
    text = (WORKFLOWS / "first-use.yml").read_text()
    pins = re.findall(r'--with "([^"]+)"', text)
    assert pins, "the job installs nothing explicitly: check what it runs"
    assert all("==" in pin for pin in pins), f"unpinned: {pins}"


# -- first-use: the window follows the schedule, not the clock ------------------------

ASK = "Ask who is new"


def iso_ago(minutes: int) -> str:
    moment = datetime.now(UTC) - timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def success(*minutes_ago: int) -> str:
    """Newest first, as `gh run list` returns them."""
    return "[" + ",".join(f'{{"createdAt":"{iso_ago(m)}"}}' for m in minutes_ago) + "]"


def ask(sandbox, runs: str, **env):
    script = step_script(load("first-use.yml"), "first-use", ASK)
    return sandbox(script, GH_STUB_RUNS_FIRST_USE_YML=runs, **env)


def window_passed(sandbox) -> int | None:
    calls = sandbox.uv_calls()
    assert len(calls) == 1, f"expected one command invocation, got {calls}"
    match = re.search(r"--minutes (\d+)", calls[0])
    return int(match.group(1)) if match else None


#: How much later than the test's own clock the step's `date` may run. The lower
#: bounds below are exact (the overlap is part of the requirement); the upper bounds
#: allow for a loaded machine, because one full-suite run failed an earlier, tighter
#: +2 band once and could not be reproduced in 12 runs under CPU load. What each test
#: must distinguish is far wider than this (a 3-hour window from a 10-hour one).
SLACK = 10


@needs_tools
def test_the_window_reaches_back_to_the_previous_successful_run(sandbox):
    # GitHub fires this "hourly" schedule every 4-7 hours. A fixed look-back saw
    # about a quarter of arrivals; looking back to the last success misses none.
    ask(sandbox, success(180))
    got = window_passed(sandbox)
    assert 186 <= got <= 186 + SLACK, f"3 hours since the last run plus the overlap; got {got}"


@needs_tools
def test_the_window_keeps_an_overlap_so_a_slow_start_cannot_open_a_gap(sandbox):
    ask(sandbox, success(2))
    got = window_passed(sandbox)
    assert got >= 2 + 6, f"two minutes since the last run needs at least the overlap; got {got}"


@needs_tools
def test_the_newest_success_decides_not_an_older_one(sandbox):
    ask(sandbox, success(120, 600))
    got = window_passed(sandbox)
    assert 126 <= got <= 126 + SLACK, (
        f"the 2-hour-old success decides, not the 10-hour-old; got {got}"
    )


@needs_tools
def test_with_no_earlier_success_the_commands_own_default_applies(sandbox):
    ask(sandbox, "[]")
    got = window_passed(sandbox)
    assert got is None, f"no --minutes expected so the command uses its default; got {got}"


@needs_tools
def test_a_long_outage_is_capped_at_a_week(sandbox):
    ask(sandbox, success(60 * 24 * 30))
    got = window_passed(sandbox)
    assert got == 10080, f"a month's outage is capped at a week; got {got}"


@needs_tools
def test_only_successful_runs_of_this_workflow_set_the_window(sandbox):
    # A failed or cancelled run is not a success, so the next run covers its gap.
    ask(sandbox, success(60))
    asked = [c for c in sandbox.calls() if c.startswith("run list")]
    assert len(asked) == 1
    assert "--workflow first-use.yml" in asked[0] and "--status success" in asked[0]


@needs_tools
def test_exclusions_are_passed_one_per_address_with_spaces_and_blanks_dropped(sandbox):
    ask(sandbox, "[]", EXCLUDE="a@example.org, B@example.org,")
    (call,) = sandbox.uv_calls()
    assert call.count("--exclude") == 2
    assert "--exclude a@example.org" in call and "--exclude B@example.org" in call


@needs_tools
def test_the_report_is_written_to_a_file_for_the_next_step(sandbox):
    ask(sandbox, "[]", UV_STUB_OUT="  new@example.org  signed in")
    assert "new@example.org" in (sandbox.dir / "report.md").read_text()


@needs_tools
def test_a_failing_command_fails_the_step_rather_than_looking_like_a_quiet_hour(sandbox):
    result = ask(sandbox, "[]", UV_STUB_EXIT="1")
    assert result.returncode != 0
