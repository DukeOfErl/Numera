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


def unavailable_but_buildable(export: Path) -> str:
    """What to say when an export is there and the ingester is not installed.

    Better than the message it replaces even though the feature is unavailable,
    which is the property worth having from a degradation: it names the file it
    found and the two ways to use it.
    """
    return (
        f"No corpus at the configured path, but {export} is beside it. "
        "Install the ingestion extra to have it built automatically "
        "(`uv sync --extra ask --extra ingest`), or run `bionumbers-ingest "
        f"{export}` yourself and point BIONUMBERS_ASK_CORPUS at the result."
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
        if Path(configured).is_file():
            return configured
        export = _export_beside(configured)
        if export is not None:
            raise CorpusUnavailable(unavailable_but_buildable(export)) from None
        return configured

    found = plan(configured)
    if found.is_ready:
        return str(found.corpus_path)
    if not found.needs_build:
        # Nothing to build from. The caller's own "no corpus there" stands, which
        # says more about the actual mistake than anything this module could add.
        return configured

    announce(building_text(found.export_path, found.corpus_path))
    try:
        return str(build(found))
    except OutputWouldBeCommitted as exc:
        # Translated here rather than in each driver. Both already render
        # `CorpusUnavailable` as a message, and this is the same kind of thing: a
        # condition a person can fix, whose whole value is the sentence. Making
        # both drivers import the ingester's exception type to say so would put
        # that dependency in two more places to no purpose.
        raise CorpusUnavailable(
            f"Refusing to build the corpus at {exc.path}: git would track it in "
            f"{exc.repo}, and the BioNumbers data must not enter a repository. "
            "Point BIONUMBERS_ASK_CORPUS somewhere outside the checkout."
        ) from exc
