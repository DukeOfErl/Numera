"""Finding a corpus, or the export that would produce one.

Every requirement here is in `add-corpus-autobuild`'s `corpus-ingestion` delta.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from bionumbers_ingest.guard import OutputWouldBeCommitted
from bionumbers_ingest.resolve import build, plan


@pytest.fixture
def export(tmp_path, sample_html):
    """The sample export under the published filename, in its own directory."""
    directory = tmp_path / "downloads"
    directory.mkdir()
    target = directory / "BioNumbers.xls"
    shutil.copy(sample_html, target)
    return target


def test_a_corpus_that_is_there_needs_no_build(tmp_path):
    corpus = tmp_path / "bionumbers.jsonl"
    corpus.write_text("{}\n", encoding="utf-8")
    result = plan(corpus)
    assert result.is_ready and not result.needs_build
    assert result.corpus_path == corpus


def test_an_export_beside_a_missing_corpus_is_found(export):
    result = plan(export.parent / "bionumbers.jsonl")
    assert result.needs_build
    assert result.export_path == export
    assert result.corpus_path == export.parent / "bionumbers.jsonl"


def test_the_export_is_matched_however_it_is_cased(tmp_path, sample_html):
    """A browser on a case-preserving filesystem is not consistent about it."""
    directory = tmp_path / "d"
    directory.mkdir()
    shutil.copy(sample_html, directory / "bionumbers.XLS")
    assert plan(directory / "corpus.jsonl").needs_build


def test_the_configured_path_may_be_the_export_itself(export):
    result = plan(export)
    assert result.needs_build
    assert result.export_path == export
    # Beside the export, named for it -- not in whatever directory the caller
    # happened to be started from, which is how a relative default puts a corpus
    # in a checkout.
    assert result.corpus_path == export.with_suffix(".jsonl")


def test_an_export_whose_corpus_already_exists_is_not_rebuilt(export):
    beside = export.with_suffix(".jsonl")
    beside.write_text("{}\n", encoding="utf-8")
    result = plan(export)
    assert not result.needs_build
    assert result.corpus_path == beside


def test_nothing_to_build_from_is_reported_as_nothing(tmp_path):
    result = plan(tmp_path / "absent" / "bionumbers.jsonl")
    assert not result.needs_build and not result.is_ready


def test_a_directory_with_no_export_offers_no_build(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing here", encoding="utf-8")
    assert not plan(tmp_path / "bionumbers.jsonl").needs_build


def test_a_corpus_is_never_rebuilt_however_stale(export):
    """Absolute, not heuristic.

    A corpus produced deliberately -- from another export, with a row limit, or
    edited -- being replaced without being asked is worse than a stale one being
    read, and staleness is invisible from the answer side.
    """
    corpus = export.parent / "bionumbers.jsonl"
    corpus.write_text('{"deliberate": true}\n', encoding="utf-8")
    import os

    os.utime(corpus, (0, 0))  # older than the export by decades
    result = plan(corpus)
    assert not result.needs_build
    assert corpus.read_text(encoding="utf-8") == '{"deliberate": true}\n'


def test_building_produces_a_corpus_the_loader_can_read(export):
    corpus = build(plan(export.parent / "bionumbers.jsonl"))
    assert corpus.is_file()
    lines = corpus.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6  # the fixture's data rows, padding excluded

    load = pytest.importorskip("bionumbers_ask.corpus").load
    assert len(load(str(corpus))) == 6


def test_a_build_is_refused_where_git_would_track_the_corpus(tmp_path, sample_html):
    """The convenience path inherits the refusal rather than routing around it."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    shutil.copy(sample_html, repo / "BioNumbers.xls")

    with pytest.raises(OutputWouldBeCommitted):
        build(plan(repo / "bionumbers.jsonl"))
    assert not (repo / "bionumbers.jsonl").exists()


def test_building_without_an_export_is_a_programming_error(tmp_path):
    with pytest.raises(ValueError, match="no export"):
        build(plan(tmp_path / "bionumbers.jsonl"))


def test_two_exports_differing_only_in_case_are_ambiguous(tmp_path, sample_html):
    """Nothing, rather than whichever the filesystem lists first.

    They can coexist on a case-sensitive filesystem, and picking one by directory
    order picks differently on another machine.
    """
    shutil.copy(sample_html, tmp_path / "BioNumbers.xls")
    shutil.copy(sample_html, tmp_path / "bionumbers.xls")
    assert not plan(tmp_path / "corpus.jsonl").needs_build


def test_the_export_name_agrees_with_the_consumers_copy():
    """The consumer restates this constant, and cannot import it.

    `bionumbers_ask.autobuild` names the export in the branch where importing this
    package failed, so the duplication is unavoidable. Asserting the two agree
    whenever both are installed is what keeps it from drifting.
    """
    from bionumbers_ingest.resolve import EXPORT_NAME

    autobuild = pytest.importorskip("bionumbers_ask.autobuild")
    assert autobuild.EXPORT_NAME == EXPORT_NAME


def test_an_empty_path_is_a_misconfiguration_not_the_working_directory():
    """`Path("")` is `Path(".")`.

    An unset environment variable would otherwise make the working directory the
    corpus path: an export in the cwd reads as buildable, and the run announces
    "building into ." before the writer refuses. Reported by the consumer, whose
    drivers pass "" when the variable is unset.
    """
    with pytest.raises(ValueError, match="no corpus path"):
        plan("")


def test_a_directory_is_not_a_corpus_path(tmp_path):
    """Treating one as a corpus searches its *parent* for the export."""
    with pytest.raises(ValueError, match="directory"):
        plan(tmp_path)
