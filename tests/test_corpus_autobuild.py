"""A missing corpus is built from an export beside it, and said so before it is.

The wiring, not the resolver: `bionumbers_ingest` owns finding the export and
performing the build, and these check what this project does with the answer --
which path it loads, what it says first, and whether the two ways a build can be
refused reach the reader as a message rather than a traceback.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import FIXTURE

from bionumbers_ask import autobuild
from bionumbers_ask.corpus import CorpusUnavailable


@pytest.fixture
def outside_any_repo(tmp_path) -> Path:
    """A directory git does not track, since the guard refuses everything else."""
    return tmp_path


def test_an_existing_corpus_is_used_and_never_rebuilt(outside_any_repo):
    """Absolute, not a heuristic on age. Silently replacing a corpus somebody
    produced deliberately is a worse surprise than a stale one, and "the file
    changed under me" is the hardest kind of bug to see from the answer side."""
    corpus = outside_any_repo / "bionumbers.jsonl"
    shutil.copy(FIXTURE, corpus)
    stamped = corpus.stat().st_mtime

    said = []
    assert autobuild.corpus_path(str(corpus), said.append) == str(corpus)
    assert not said, "a build was announced for a corpus that was already there"
    assert corpus.stat().st_mtime == stamped, "the corpus was rewritten"


def test_nothing_to_build_from_leaves_the_ordinary_error(outside_any_repo):
    """The caller's own "no corpus there" says more about the actual mistake than
    anything this module could add, so it is left to stand."""
    missing = outside_any_repo / "absent.jsonl"
    said = []
    assert autobuild.corpus_path(str(missing), said.append) == str(missing)
    assert not said


def test_the_build_is_announced_before_it_happens(outside_any_repo, monkeypatch):
    """A minute of silence on first launch reads as a hang, and the page shows
    nothing at all while it happens. Ordering is the whole point, so it is asserted
    rather than assumed: the announcement is recorded by the double that performs
    the build, and must already be there when it runs."""
    export = outside_any_repo / "BioNumbers.xls"
    export.write_text("not really an export")
    corpus = outside_any_repo / "bionumbers.jsonl"
    said = []
    order = []

    def fake_build(plan):
        order.append(("built", tuple(said)))
        shutil.copy(FIXTURE, corpus)
        return corpus

    monkeypatch.setattr("bionumbers_ingest.resolve.build", fake_build)
    result = autobuild.corpus_path(
        str(corpus), lambda text: (said.append(text), order.append("said"))
    )

    assert result == str(corpus)
    assert order[0] == "said", f"the build ran before it was announced: {order}"
    assert order[1][1], "the build saw no announcement, so nothing was shown first"
    assert str(export) in said[0] and str(corpus) in said[0], (
        "the notice must name both paths -- the build can be refused, and a reader "
        f"needs to know which path was being written: {said[0]}"
    )


def test_a_refused_destination_reaches_the_reader_as_a_message(outside_any_repo, monkeypatch):
    """The guard refuses a corpus git would track. Translated once here rather than
    in each driver, so neither has to import the ingester's exception to say so."""
    from bionumbers_ingest.guard import OutputWouldBeCommitted

    export = outside_any_repo / "BioNumbers.xls"
    export.write_text("not really an export")
    corpus = outside_any_repo / "bionumbers.jsonl"

    def refuse(plan):
        raise OutputWouldBeCommitted(corpus, "/some/checkout")

    monkeypatch.setattr("bionumbers_ingest.resolve.build", refuse)
    with pytest.raises(CorpusUnavailable) as raised:
        autobuild.corpus_path(str(corpus), lambda _text: None)

    said = str(raised.value)
    assert str(corpus) in said and "/some/checkout" in said
    assert "must not enter a repository" in said


def test_without_the_ingester_the_error_still_names_the_export(outside_any_repo, monkeypatch):
    """The degradation worth having: a better message than the one it replaces,
    even though the feature is unavailable."""
    export = outside_any_repo / "BioNumbers.xls"
    export.write_text("not really an export")
    corpus = outside_any_repo / "bionumbers.jsonl"

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def no_ingester(name, *args, **kwargs):
        if name.startswith("bionumbers_ingest"):
            raise ImportError("no ingestion extra installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_ingester)
    with pytest.raises(CorpusUnavailable) as raised:
        autobuild.corpus_path(str(corpus), lambda _text: None)

    said = str(raised.value)
    assert str(export) in said, "the reader is not told which file they already have"
    assert "bionumbers-ingest" in said, "nor how to use it without the extra"


def test_without_the_ingester_and_without_an_export_nothing_is_claimed(
    outside_any_repo, monkeypatch
):
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def no_ingester(name, *args, **kwargs):
        if name.startswith("bionumbers_ingest"):
            raise ImportError("no ingestion extra installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_ingester)
    missing = outside_any_repo / "absent.jsonl"
    assert autobuild.corpus_path(str(missing), lambda _t: None) == str(missing)


# -- both drivers, since a message that never reaches the reader is not a message


def test_the_terminal_shows_the_refusal_rather_than_a_traceback(outside_any_repo, monkeypatch):
    from bionumbers_ask.cli import main
    from bionumbers_ingest.guard import OutputWouldBeCommitted

    (outside_any_repo / "BioNumbers.xls").write_text("not really an export")
    corpus = outside_any_repo / "bionumbers.jsonl"

    def refuse(plan):
        raise OutputWouldBeCommitted(corpus, "/some/checkout")

    monkeypatch.setattr("bionumbers_ingest.resolve.build", refuse)
    with pytest.raises(SystemExit) as exited:
        main(["--corpus", str(corpus), "--ask", "q"])
    assert "must not enter a repository" in str(exited.value)
    assert "bionumbers-ask:" in str(exited.value)


def test_the_page_shows_the_refusal_rather_than_a_traceback(outside_any_repo, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from bionumbers_ask import web
    from bionumbers_ingest.guard import OutputWouldBeCommitted

    (outside_any_repo / "BioNumbers.xls").write_text("not really an export")
    corpus = outside_any_repo / "bionumbers.jsonl"
    monkeypatch.setenv("BIONUMBERS_ASK_CORPUS", str(corpus))
    monkeypatch.setenv("BIONUMBERS_ASK_CHECKPOINTS", str(outside_any_repo / "c.sqlite"))

    def refuse(plan):
        raise OutputWouldBeCommitted(corpus, "/some/checkout")

    monkeypatch.setattr("bionumbers_ingest.resolve.build", refuse)
    # The real `resources`, uncached, so the failure happens where the page meets it.
    monkeypatch.setattr(web, "resources", web.resources.__wrapped__)

    at = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=30
    ).run()
    assert any("must not enter a repository" in e.value for e in at.error), [
        e.value for e in at.error
    ]
    assert not at.exception, "the page raised instead of explaining"


def test_the_duplicated_export_rule_still_agrees_with_the_resolver():
    """`autobuild` restates the export's name and matching rule because the
    guarded-out branch runs when the ingester cannot be imported, so its constant
    is not reachable there. Duplication that cannot be removed can at least be
    stopped from drifting: if the resolver changes what it looks for, the message
    shown to someone without the extra would name a file that is no longer the one
    a build would use."""
    from bionumbers_ingest import resolve

    assert autobuild.EXPORT_NAME.lower() == resolve.EXPORT_NAME.lower()


def test_several_exports_are_reported_by_neither(tmp_path):
    """Both sides decline to choose. A directory holding two exports is ambiguous,
    and picking one silently is how the wrong corpus gets built."""
    from bionumbers_ingest import resolve

    for name in ("BioNumbers.xls", "bionumbers.xls"):
        try:
            (tmp_path / name).write_text("export")
        except OSError:  # pragma: no cover - case-insensitive filesystem
            pytest.skip("filesystem cannot hold both spellings")
    if len(list(tmp_path.iterdir())) < 2:  # pragma: no cover
        pytest.skip("filesystem folded the two names together")

    corpus = tmp_path / "bionumbers.jsonl"
    assert resolve.plan(corpus).export_path is None
    assert autobuild._export_beside(str(corpus)) is None
