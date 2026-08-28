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


def test_without_the_ingester_a_corpus_that_is_there_is_simply_used(tmp_path, monkeypatch):
    """The case the guarded-out branch got wrong: a corpus present, an export beside
    it, and no ingestion extra. It refused to start, said there was no corpus when
    there was, and told the reader to install something they did not need.

    Not an edge case. Export and corpus in one directory is the arrangement the
    README describes, and the ask-only install is the one it offers -- so a reviewer
    handed a corpus by a colleague walks straight into it.

    The deeper fault was order, not a missing line: this branch is a hand copy of
    the resolver's decision procedure, and it had copied the matching rule while
    dropping the check that comes before it.
    """
    corpus = tmp_path / "bionumbers.jsonl"
    shutil.copy(FIXTURE, corpus)
    (tmp_path / "BioNumbers.xls").write_text("export")

    real_import = __import__

    def no_ingester(name, *args, **kwargs):
        if name.startswith("bionumbers_ingest"):
            raise ImportError("ask extra only")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_ingester)
    said = []
    assert autobuild.corpus_path(str(corpus), said.append) == str(corpus)
    assert not said


def test_the_guarded_branch_agrees_with_the_resolver_wherever_no_build_happens(
    tmp_path, monkeypatch
):
    """The copy and the original must choose the same path, not merely match on the
    export's name. The drift that mattered was in the decision order, so an
    agreement test comparing only constants passed while the branch was wrong.

    Checked wherever a build is not what happens, which is every arrangement the
    guarded branch can be in: it cannot build, so those are the only cases where
    the two are answering the same question.
    """
    from bionumbers_ingest import resolve

    real_import = __import__

    def no_ingester(name, *args, **kwargs):
        if name.startswith("bionumbers_ingest"):
            raise ImportError("ask extra only")
        return real_import(name, *args, **kwargs)

    arrangements = [(True, True), (True, False), (False, False)]
    for index, (has_corpus, has_export) in enumerate(arrangements):
        case = tmp_path / f"case{index}"
        case.mkdir()
        corpus = case / "bionumbers.jsonl"
        if has_corpus:
            shutil.copy(FIXTURE, corpus)
        if has_export:
            (case / "BioNumbers.xls").write_text("export")

        with_resolver = autobuild.corpus_path(str(corpus), lambda _t: None)

        monkeypatch.setattr("builtins.__import__", no_ingester)
        try:
            without = autobuild.corpus_path(str(corpus), lambda _t: None)
        except CorpusUnavailable:  # pragma: no cover - only where an export exists
            without = None
        finally:
            monkeypatch.undo()

        assert without == with_resolver, (
            f"corpus={has_corpus} export={has_export}: the guarded branch loads "
            f"{without!r} where the resolver loads {with_resolver!r}"
        )
        # And the resolver's own view agrees about whether anything was there.
        assert resolve.plan(corpus).is_ready is has_corpus


# -- what the review found, each pinned where the old tests could not see it


def test_a_configured_export_resolves_to_the_corpus_beside_it_either_way(tmp_path, monkeypatch):
    """`BIONUMBERS_ASK_CORPUS` pointing at the .xls means "here is the export", not
    "here is the corpus". The resolver knows that; the hand copy did not, and
    returned the export -- so `load` was handed 27 MB of HTML and died on line 1.

    Same class as the corpus-present bug, in the other spelling, and invisible to
    the agreement test because every arrangement it built used a .jsonl path.
    """
    export = tmp_path / "BioNumbers.xls"
    export.write_text("<table>not a corpus</table>")
    beside = tmp_path / "BioNumbers.jsonl"
    shutil.copy(FIXTURE, beside)

    with_resolver = autobuild.corpus_path(str(export), lambda _t: None)

    real_import = __import__

    def no_ingester(name, *args, **kwargs):
        if name.startswith("bionumbers_ingest"):
            raise ImportError("ask extra only")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_ingester)
    without = autobuild.corpus_path(str(export), lambda _t: None)

    assert with_resolver == str(beside)
    assert without == with_resolver, "the copy handed back the export itself"


def test_an_unset_corpus_path_is_left_to_say_so(tmp_path, monkeypatch):
    """Both drivers pass "" when the variable is unset, and `Path("")` is
    `Path(".")` -- so an export in the working directory made the current directory
    the corpus, announced a build into `.`, and raised out of the writer. The
    unset case has a good message already; it just has to be allowed to happen."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "BioNumbers.xls").write_text("<table></table>")
    said = []
    assert autobuild.corpus_path("", said.append) == ""
    assert not said, "a build was announced for a path nobody configured"


def test_a_build_that_fails_for_any_other_reason_is_still_a_sentence(tmp_path, monkeypatch):
    """A truncated download is the likeliest real failure, since fetching the
    export is the one manual step. Only the git refusal had its own type, so
    everything else reached the terminal as a stack and the page as Streamlit's
    exception panel."""
    (tmp_path / "BioNumbers.xls").write_text("<table>truncated")
    corpus = tmp_path / "bionumbers.jsonl"

    def truncated(plan):
        raise ValueError("the table is never closed and ends mid-row")

    monkeypatch.setattr("bionumbers_ingest.resolve.build", truncated)
    with pytest.raises(CorpusUnavailable) as raised:
        autobuild.corpus_path(str(corpus), lambda _t: None)
    said = str(raised.value)
    assert "ends mid-row" in said, "the actual cause is dropped"
    assert "download it again" in said, "and nothing tells the reader what to do"


def test_nothing_to_build_names_the_corpus_not_the_export(tmp_path):
    """With the export configured and neither file present, the error named the
    export as the missing corpus -- sending the reader to look at a file that is
    not the one missing."""
    export = tmp_path / "BioNumbers.xls"
    assert autobuild.corpus_path(str(export), lambda _t: None) == str(
        tmp_path / "BioNumbers.jsonl"
    )


def test_the_build_notice_is_not_drawn_from_inside_the_cache():
    """Streamlit records elements drawn inside a cached function and replays them
    on every hit, so an `st.info` written inside `resources` would redraw "building
    a corpus" at the top of the page for the life of the server -- true once, false
    every rerun after. The page resolves the path before calling the cached
    function, so the notice belongs to the script run that caused it."""
    import ast
    import inspect

    from bionumbers_ask import web

    # The code, not the prose. A plain substring search matched this function's own
    # comment explaining why `st.info` must not be here -- a source-scanning test
    # reads docstrings too, and one that passes on an explanation of the bug is
    # worse than none.
    tree = ast.parse(inspect.getsource(web.resources.__wrapped__).strip())
    drawn = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "info" not in drawn, "the build notice is drawn inside a cached function"
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "corpus_path" not in called, "the build was moved back inside the cache"

    app = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    body = app.read_text()
    assert "autobuild.corpus_path(" in body, "the page no longer resolves the path itself"
    assert body.index("autobuild.corpus_path(") < body.index("web.resources("), (
        "the corpus must be resolved before the cached function is called"
    )
