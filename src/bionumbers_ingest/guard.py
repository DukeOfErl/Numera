"""Refuse to write the corpus where git would track it.

**In the library, not the command.** The refusal used to live in `cli.py`, which
meant it protected exactly one caller: `ingest()` invoked programmatically wrote
20 MB of unlicensed export data onto a committable path without a word. Nothing
called it that way, so the hole was invisible — until the ask agent was proposed
as a second caller, which would have routed the convenience path around the one
irreversible mistake this project can make (ADR-0200).

A guard in a driver is a guard for one driver. This one belongs to the operation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from bionumbers_ingest.io import PARTIAL_SUFFIX
from bionumbers_ingest.provenance import manifest_path_for


class OutputWouldBeCommitted(Exception):
    """The requested output path is one git would track.

    Its own type rather than `ValueError`, so a caller can tell "this file cannot
    be written here" from "this source cannot be read" and say something useful.
    """

    def __init__(self, path: Path, repo: str) -> None:
        self.path = path
        self.repo = repo
        super().__init__(f"git would track {path} in {repo}")


def _nearest_existing(path: Path) -> Path:
    for candidate in [path, *path.parents]:
        if candidate.exists():
            return candidate
    return Path.cwd()


def committable_repo_for(output: Path) -> str | None:
    """The repository this output would be committable in, if any.

    The default output path is relative, so a run started from the wrong checkout
    writes the corpus into whichever repository the caller happens to be standing
    in. Three checkouts here share one origin and one of them tracks `main`, so
    that is how 19.5 MB of unlicensed data reaches a public history.

    A `.gitignore` entry only protects the repositories someone remembered to
    edit. Asking git whether it would track the file protects all of them, and
    asks the authority rather than guessing at ignore semantics.

    Returns the repository root as a string when the file would be tracked, or
    ``None`` when it is ignored, outside any repository, or git is unavailable.
    """
    target = output if output.is_absolute() else Path.cwd() / output
    anchor = _nearest_existing(target.parent)
    try:
        top = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if top.returncode != 0:
            return None  # not a repository
        ignored = subprocess.run(
            ["git", "-C", str(anchor), "check-ignore", "-q", str(target)],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # no git to ask; the .gitignore is the only guard left
    return None if ignored.returncode == 0 else top.stdout.strip()


def paths_a_run_can_create(output: Path) -> list[Path]:
    """Every file an ingest of ``output`` may leave on disk, partials included.

    The manifest is written beside the corpus under a different name, so a rule
    like `bionumbers*.jsonl` ignores one and not the other. And each is written
    through a `.partial` first, which a suffix-matching ignore rule does not cover
    either: the partial is unlinked on the way out of an exception, but a SIGKILL,
    an OOM or a power cut leaves it behind on a committable path.
    """
    final = [output, manifest_path_for(output)]
    return final + [p.with_name(p.name + PARTIAL_SUFFIX) for p in final]


def refuse_if_committable(output: Path) -> None:
    """Raise if any file the run may create is one git would track."""
    for candidate in paths_a_run_can_create(output):
        repo = committable_repo_for(candidate)
        if repo is not None:
            raise OutputWouldBeCommitted(candidate, repo)
