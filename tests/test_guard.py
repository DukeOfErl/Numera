"""The refusal belongs to the operation, not to the command that usually runs it.

A guard in a driver is a guard for one driver. This one lived in `cli.py`, so
`ingest()` called as a library wrote 20 MB of unlicensed export data onto a
committable path without a word -- invisible while the command was the only
caller, and the exact bypass a second caller would have taken. ADR-0200.
"""

from __future__ import annotations

import subprocess

import pytest

from bionumbers_ingest.guard import (
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


def test_a_path_outside_any_repository_names_no_repository(tmp_path):
    assert committable_repo_for(tmp_path / "corpus.jsonl") is None
    refuse_if_committable(tmp_path / "corpus.jsonl")  # does not raise
