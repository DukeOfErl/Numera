"""Build the corpus from an export beside it, when there is no corpus to load.

Policy, and therefore a driver's business rather than the agent's. `corpus.load`
stays a read: its contract is "parse this JSONL or explain why you cannot", and
tests, the repository and the corpus-marked suite all call it. A minute-long 20 MB
build behind it would mean any call anywhere can write a file.

Shared by both drivers for the reason `messages` is: whether to build, and what to
say about it, are the same decision in a terminal and on a page. Only the drawing
differs, so the sentence is passed out through `announce` and each driver renders
it its own way.

The import of `bionumbers_ingest` is guarded. Installing `--extra ask` is what a
reviewer does to run the agent, and making that carry the ingester's stack so a
convenience can fire on a machine that happens to hold a raw export is the wrong
trade for everyone who does not have one. Absent, the feature degrades to a better
error than the one it replaces: it still names the export it would have used.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .corpus import CorpusUnavailable

#: The export's published filename, restated here rather than imported: this
#: module has to name it in the guarded-out branch, where the ingester -- and
#: therefore its constant -- is not importable.
EXPORT_NAME = "BioNumbers.xls"


def _export_beside(configured: str) -> Path | None:
    """The export a build would read, found without the ingester.

    Only reached when the import failed, and only after establishing there is no
    corpus. It exists so the degraded message can name a file it has confirmed is
    there, which is what a reader in that position most needs to know -- they have
    the export already and only lack the component that converts it.

    Deliberately the same rule the resolver uses: one file of that name, matched
    case-insensitively, and nothing reported where several sit together. The
    agreement is asserted by a test rather than left to memory, because it is a
    hand copy of a rule this project does not own.
    """
    path = Path(configured)
    if path.suffix.lower() == ".xls":
        return path if path.is_file() else None
    try:
        matches = [
            entry
            for entry in path.parent.iterdir()
            if entry.name.lower() == EXPORT_NAME.lower() and entry.is_file()
        ]
    except OSError:
        return None
    return matches[0] if len(matches) == 1 else None


def _corpus_for(configured: str) -> Path:
    """Where the corpus is, for a configured path that may be the export itself.

    `plan` resolves a configured `.xls` to the `.jsonl` beside it, because the
    export is not a corpus and the corpus should not land in whatever directory
    the caller was started from. This branch has to make the same move, and the
    first version of it did not: it returned any existing file, so pointing at the
    export handed 27 MB of HTML to a JSONL parser.
    """
    path = Path(configured)
    return path.with_suffix(".jsonl") if path.suffix.lower() == ".xls" else path


def _without_the_ingester(configured: str) -> str:
    """The same decisions `plan` makes, for when `plan` cannot be imported.

    A hand copy, and therefore the thing most likely to drift. It has drifted twice
    -- once dropping the corpus-present check, once ignoring that a configured
    `.xls` names the export rather than the corpus -- and both times the copy had
    the matching rule right and the decision order wrong. The order is the part to
    read against `plan`, not the constants.
    """
    corpus = _corpus_for(configured)
    if corpus.is_file():
        return str(corpus)
    export = _export_beside(configured)
    if export is not None:
        raise CorpusUnavailable(unavailable_but_buildable(export))
    return configured


def unavailable_but_buildable(export: Path) -> str:
    """What to say when an export is there and the ingester is not installed.

    Better than the message it replaces even though the feature is unavailable,
    which is the property worth having from a degradation: it names the file it
    found and the two ways to use it.
    """
    return (
        f"No corpus at the configured path, but {export} is beside it. "
        "Install the ingestion extra -- `uv sync --extra ask --extra ingest` -- and "
        "it will be built on the next start, or run `bionumbers-ingest "
        f"{export}` yourself once that extra is installed and point "
        "SCINUMBERS_CORPUS at the result."
    )


def building_text(export: Path, corpus: Path) -> str:
    """Said before the build, never after.

    A minute of silence on first launch reads as a hang, and the page would show
    nothing at all while it happened. Names both paths because the build can be
    refused -- the destination may be somewhere git would track it -- and a reader
    needs to know which path was being written, not only which was read.
    """
    return f"No corpus yet. Building one from {export} into {corpus}; this takes a minute."


def corpus_path(configured: str, announce: Callable[[str], None]) -> str:
    """The corpus to load, built first if there is only an export.

    Returns the path to load. Raises `CorpusUnavailable` where a corpus cannot be
    had, so a caller that already handles that -- both drivers do -- needs no new
    branch for the case where the ingester is missing.

    Never rebuilds. A corpus already at the configured path is used however old it
    is: silently replacing one somebody produced deliberately is a worse surprise
    than a stale one, and "the file changed under me" is the hardest kind of bug to
    see from the answer side. Staleness, if it is ever detected, should be reported
    rather than acted on.
    """
    if not configured:
        # No path at all. `load` says so better than anything here could, and
        # `Path("")` is `Path(".")` -- which would make the current directory the
        # corpus and any export in it a thing to build.
        return configured

    try:
        from bionumbers_ingest.guard import OutputWouldBeCommitted
        from bionumbers_ingest.resolve import build, plan
    except ImportError:
        # A corpus already there is the answer, whatever else is beside it. Checked
        # first because that is the order `plan` checks in, and the whole of this
        # branch is a hand copy of `plan` for the case where `plan` cannot be
        # imported. Omitting this line refused to start with a perfectly good
        # corpus present -- and told the reader there was none, and to install an
        # extra they did not need. Worse than an edge case, because export and
        # corpus in one directory is the arrangement the README now describes.
        return _without_the_ingester(configured)

    try:
        found = plan(configured)
    except ValueError as exc:
        # The resolver rejects a path that cannot name a corpus -- a directory,
        # most likely, from someone who pointed the variable at the folder holding
        # their export. A `ValueError` out of here is a traceback in the terminal
        # and Streamlit's exception panel on the page, for what is a typo.
        raise CorpusUnavailable(
            f"{exc}. SCINUMBERS_CORPUS names the corpus file itself, not the directory holding it."
        ) from exc
    if found.is_ready:
        return str(found.corpus_path)
    if not found.needs_build:
        # Nothing to build from, so the caller's own "no corpus there" stands --
        # but about the corpus's path rather than the configured one, which for a
        # configured `.xls` are different files. Naming the export as the missing
        # corpus sends the reader to look at a file that is present.
        return str(found.corpus_path)

    announce(building_text(found.export_path, found.corpus_path))
    try:
        return str(build(found))
    except CorpusUnavailable:
        raise
    except OutputWouldBeCommitted as exc:
        # Translated here rather than in each driver. Both already render
        # `CorpusUnavailable` as a message, and this is the same kind of thing: a
        # condition a person can fix, whose whole value is the sentence. Making
        # both drivers import the ingester's exception type to say so would put
        # that dependency in two more places to no purpose.
        raise CorpusUnavailable(
            f"Refusing to build the corpus at {exc.path}: git would track it in "
            f"{exc.repo}, and the BioNumbers data must not enter a repository. "
            "Point SCINUMBERS_CORPUS somewhere outside the checkout."
        ) from exc
    except Exception as exc:
        # Every other way a build can fail, and there are many: a truncated
        # download, an unreadable file, a full disk. Broad on purpose -- whatever
        # went wrong, the outcome for the reader is that there is no corpus, and
        # that is a condition both drivers already render as a sentence. Letting
        # it through instead put a stack trace in the terminal and Streamlit's
        # exception panel on the page, for what is usually a bad download.
        raise CorpusUnavailable(
            f"Could not build a corpus from {found.export_path}: {exc}. "
            "If the export was interrupted, download it again."
        ) from exc
