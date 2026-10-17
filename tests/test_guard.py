"""The refusal belongs to the operation, not to the command that usually runs it.

A guard in a driver is a guard for one driver. This one lived in `cli.py`, so
`ingest()` called as a library wrote 20 MB of unlicensed export data onto a
committable path without a word -- invisible while the command was the only
caller, and the exact bypass a second caller would have taken. ADR-0200.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from bionumbers_ingest.guard import (
    GitDidNotAnswer,
    OutputWouldBeCommitted,
    committable_repo_for,
    paths_a_run_can_create,
    refuse_if_committable,
)
from bionumbers_ingest.ingest import ingest


def _repo(tmp_path, name, ignore=None):
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    if ignore is not None:
        (repo / ".gitignore").write_text(ignore, encoding="utf-8")
    return repo


def test_the_library_call_refuses_where_git_would_track_the_output(tmp_path, sample_html):
    repo = _repo(tmp_path, "tracked")
    out = repo / "corpus.jsonl"

    with pytest.raises(OutputWouldBeCommitted) as refusal:
        ingest(sample_html, out)

    assert refusal.value.repo == str(repo.resolve())
    assert not out.exists()


def test_it_refuses_before_reading_the_source(tmp_path):
    """A 27 MB read is not spent to discover the destination was never allowed.

    Asserted through a source that does not exist: reaching the read would raise
    `OSError` instead, so the exception type says which check ran first.
    """
    repo = _repo(tmp_path, "tracked")
    with pytest.raises(OutputWouldBeCommitted):
        ingest(tmp_path / "no-such-export.xls", repo / "corpus.jsonl")


def test_the_library_call_writes_where_git_ignores_the_path(tmp_path, sample_html):
    repo = _repo(tmp_path, "ignoring", ignore="data/\n")
    out = repo / "data" / "corpus.jsonl"
    result = ingest(sample_html, out)
    assert result.corpus_path.exists()


def test_the_library_call_writes_outside_any_repository(tmp_path, sample_html):
    out = tmp_path / "plain" / "corpus.jsonl"
    assert ingest(sample_html, out).corpus_path.exists()


def test_every_file_a_run_can_create_is_checked(tmp_path):
    names = {p.name for p in paths_a_run_can_create(tmp_path / "bionumbers.jsonl")}
    assert names == {
        "bionumbers.jsonl",
        "bionumbers.jsonl.manifest.json",
        "bionumbers.jsonl.partial",
        "bionumbers.jsonl.manifest.json.partial",
    }


def test_the_actual_scratch_paths_are_checked_not_only_representative_ones(tmp_path):
    """The scratch names carry a unique component, so they are passed in.

    Asking git about `<name>.partial` while the writer creates
    `<name>.1234-ab12cd34.partial` is asking about a file that never exists — and
    an ignore rule naming the representative exactly would not cover the real one.
    """
    real = tmp_path / "bionumbers.jsonl.99-deadbeef.partial"
    assert real in paths_a_run_can_create(tmp_path / "bionumbers.jsonl", (real,))


def test_a_run_is_refused_when_only_its_real_scratch_path_would_be_tracked(tmp_path, sample_html):
    """Everything but the unique scratch names is ignored, so only they can refuse.

    Ignoring just the corpus and the manifest would leave the *representative*
    `<name>.partial` trackable too, and the refusal would prove nothing about
    whether the path the writer actually creates was ever checked. Both generic
    forms are ignored here, so a refusal can only have come from a real one.
    """
    ignore = (
        "bionumbers.jsonl\n"
        "bionumbers.jsonl.manifest.json\n"
        "bionumbers.jsonl.partial\n"
        "bionumbers.jsonl.manifest.json.partial\n"
    )
    repo = _repo(tmp_path, "scratch-only", ignore=ignore)
    shutil.copy(sample_html, repo / "export.html")

    with pytest.raises(OutputWouldBeCommitted) as refusal:
        ingest(repo / "export.html", repo / "bionumbers.jsonl")

    assert ".partial" in refusal.value.path.name
    assert not (repo / "bionumbers.jsonl").exists()


def test_a_path_outside_any_repository_names_no_repository(tmp_path):
    assert committable_repo_for(tmp_path / "corpus.jsonl") is None
    refuse_if_committable(tmp_path / "corpus.jsonl")  # does not raise


# -- a git that does not answer is a refusal, not a pass (fix-guard-fails-closed) ------------
#
# Seen 2026-10-16: under memory pressure from a parallel test run, a results file was written
# inside the repository by the test asserting it would be refused. The guard read a git that did
# not answer -- a timeout, or a fork that failed -- as "git unavailable" and let the write
# through: for the one irreversible mistake, the expensive direction.


def _git_does(monkeypatch, *outcomes):
    """Replace the guard's git calls with `outcomes`, in order: a result, or an exception."""
    queue = list(outcomes)

    def run(args, **kwargs):
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return subprocess.CompletedProcess(args, *outcome)

    monkeypatch.setattr("bionumbers_ingest.guard.subprocess.run", run)


TOP = (0, "/some/checkout\n", "")
NOT_A_REPOSITORY = (
    128,
    "",
    "fatal: not a git repository (or any of the parent directories): .git\n",
)


@pytest.mark.parametrize(
    "outcomes",
    [
        pytest.param((subprocess.TimeoutExpired(["git"], 10),), id="rev-parse times out"),
        pytest.param((TOP, subprocess.TimeoutExpired(["git"], 10)), id="check-ignore times out"),
        pytest.param((OSError(12, "Cannot allocate memory"),), id="git cannot be started"),
        pytest.param(
            ((128, "", "fatal: detected dubious ownership in repository at '/x'\n"),),
            id="a repository git will not read",
        ),
        pytest.param((TOP, (128, "", "fatal: something broke\n")), id="check-ignore fails"),
    ],
)
def test_a_git_that_does_not_answer_is_a_refusal(tmp_path, monkeypatch, outcomes):
    _git_does(monkeypatch, *outcomes)
    with pytest.raises(GitDidNotAnswer) as raised:
        committable_repo_for(tmp_path / "corpus.jsonl")
    assert str(tmp_path / "corpus.jsonl") in str(raised.value)


def test_a_library_ingest_writes_nothing_when_git_does_not_answer(
    tmp_path, monkeypatch, sample_html
):
    _git_does(monkeypatch, subprocess.TimeoutExpired(["git"], 10))
    out = tmp_path / "corpus.jsonl"
    with pytest.raises(GitDidNotAnswer):
        ingest(sample_html, out)
    assert not out.exists()


def test_a_path_git_says_is_in_no_repository_is_still_allowed(tmp_path, monkeypatch):
    """The other direction: "not a git repository" is an answer, and the write may go ahead."""
    _git_does(monkeypatch, NOT_A_REPOSITORY)
    assert committable_repo_for(tmp_path / "corpus.jsonl") is None


def test_a_machine_without_git_is_still_allowed(tmp_path, monkeypatch):
    """No git installed is not git failing to answer: nothing here can commit the file."""
    _git_does(monkeypatch, FileNotFoundError(2, "No such file or directory: 'git'"))
    assert committable_repo_for(tmp_path / "corpus.jsonl") is None


def test_the_command_says_why_when_git_does_not_answer(tmp_path, monkeypatch, sample_html, capsys):
    from bionumbers_ingest.cli import main

    _git_does(monkeypatch, subprocess.TimeoutExpired(["git"], 10))
    out = tmp_path / "corpus.jsonl"
    assert main([str(sample_html), "-o", str(out)]) == 3
    err = capsys.readouterr().err
    assert "could not ask git" in err
    assert not out.exists()
