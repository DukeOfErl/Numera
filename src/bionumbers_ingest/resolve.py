"""Find a corpus, or the export that would produce one.

The reader who has downloaded the export has already done the only step that
cannot be automated. Asking them to invoke the ingester before the agent will
start is a third step whose only cause is that nothing told the agent the file
was there — while the error they get says no corpus exists, with the material to
build one sitting in the same directory.

**Reporting is separate from building.** A caller has to be able to say what is
about to happen before a 27 MB read begins: a minute of silence on first launch
reads as a hang, and a web driver shows a blank page for it. So :func:`plan` looks
and :func:`build` acts, and nothing here prints — the caller owns the wording.

**A corpus that exists is never rebuilt**, whatever its age or its manifest's
digest. A corpus someone produced deliberately being replaced without being asked
is a worse surprise than a stale one being read, and "the file changed under me"
is the hardest class of defect to see from the answer side.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bionumbers_ingest.ingest import ingest

#: The export's published filename, in the form the site serves it. Matched
#: case-insensitively, because a browser on a case-preserving filesystem is not
#: consistent about it.
#:
#: Restated in `bionumbers_ask.autobuild`, unavoidably: that module has to name the
#: export in the branch where this package failed to import, so it cannot import
#: this. `tests/test_resolve.py` asserts the two agree whenever both are present,
#: which is the only thing that makes the duplication safe.
EXPORT_NAME = "BioNumbers.xls"


@dataclass(frozen=True)
class CorpusPlan:
    """What a caller would have to do to have a corpus at the configured path."""

    corpus_path: Path
    """Where the corpus is, or would be written."""

    export_path: Path | None
    """The export a build would read, or ``None`` when there is nothing to build from."""

    @property
    def needs_build(self) -> bool:
        """Is there a corpus to build, and no corpus already there?"""
        return self.export_path is not None

    @property
    def is_ready(self) -> bool:
        """Is a corpus already at the configured path?"""
        return self.export_path is None and self.corpus_path.is_file()


def _export_in(directory: Path) -> Path | None:
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    matches = [p for p in entries if p.name.lower() == EXPORT_NAME.lower() and p.is_file()]
    # Exactly one, or nothing. Two files differing only in case can coexist on a
    # case-sensitive filesystem, and taking the first would pick between them by
    # directory order -- silently, and differently on another machine.
    return matches[0] if len(matches) == 1 else None


def plan(configured: str | Path) -> CorpusPlan:
    """Report what stands between ``configured`` and a readable corpus.

    Looks only; writes nothing. Raises ``ValueError`` for an empty path or a
    directory — both are misconfigurations that would otherwise resolve to
    somewhere surprising rather than fail.

    Four outcomes, in the order they are checked:

    - the configured path holds a corpus — use it, and **never rebuild it**
    - the configured path is the export itself — the corpus belongs beside it,
      named for it, rather than in whatever directory the caller was started from
    - the configured path holds nothing and the export is in the same directory —
      a build would produce the corpus at the configured path
    - neither — nothing to do here, and the caller's own error stands
    """
    if not str(configured).strip():
        # `Path("")` is `Path(".")`, so an unset environment variable would make
        # the working directory the corpus path: an export in the cwd then reads
        # as buildable, and the run announces "building into ." before the writer
        # refuses. A caller's empty value is a misconfiguration, and saying so is
        # more use than resolving it to somewhere surprising.
        raise ValueError("no corpus path was given")
    configured = Path(configured)
    if configured.is_dir():
        # Same class: a directory is not a corpus, and treating it as one searches
        # its *parent* for the export, which is not what anyone meant by it.
        raise ValueError(f"{configured} is a directory, not a corpus path")

    if configured.is_file() and configured.suffix.lower() != ".xls":
        return CorpusPlan(configured, None)

    if configured.suffix.lower() == ".xls":
        beside = configured.with_suffix(".jsonl")
        if beside.is_file():
            return CorpusPlan(beside, None)
        return CorpusPlan(beside, configured if configured.is_file() else None)

    return CorpusPlan(configured, _export_in(configured.parent))


def build(plan: CorpusPlan) -> Path:
    """Build the corpus this plan describes, and return where it landed.

    Goes through :func:`~bionumbers_ingest.ingest.ingest`, so a destination git
    would track is refused before anything is read — the guard moved out of the
    command into the operation so that callers like this one inherit it.
    """
    if plan.export_path is None:
        raise ValueError("this plan has no export to build from")
    return ingest(plan.export_path, plan.corpus_path).corpus_path
