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

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from bionumbers_ingest.io import PARTIAL_SUFFIX
from bionumbers_ingest.provenance import manifest_path_for

#: How long git has to answer. A slow answer is a refusal, not a pass.
GIT_TIMEOUT_S = 10


class OutputWouldBeCommitted(Exception):
    """The requested output path is one git would track.

    Its own type rather than `ValueError`, so a caller can tell "this file cannot
    be written here" from "this source cannot be read" and say something useful.
    """

    def __init__(self, path: Path, repo: str) -> None:
        self.path = path
        self.repo = repo
        super().__init__(f"git would track {path} in {repo}")


class GitDidNotAnswer(Exception):
    """Git is there and gave no answer about this path, so whether it is tracked is unknown.

    A refusal like `OutputWouldBeCommitted`, and its own type because the remedy differs: not
    "write it elsewhere" but "run it again". An unknown is refused rather than allowed, because
    the mistake this guards against cannot be undone (fix-guard-fails-closed).
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"could not ask git whether it would track {path}: {reason}")


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
    ``None`` when it is ignored, outside any repository, or git is not installed.

    **An unknown is a refusal** (fix-guard-fails-closed). Raises `GitDidNotAnswer`
    when git is installed and gives no answer -- it times out, cannot be started,
    or fails for any reason but "not a git repository". Under memory pressure a
    results file was once written inside this repository by the test asserting it
    would be refused, because a git that did not answer read as "no git".
    "Not a git repository" is matched in git's own words, so git is run in the C
    locale, where those are the words it uses.
    """
    target = output if output.is_absolute() else Path.cwd() / output
    anchor = _nearest_existing(target.parent)
    try:
        top = _git(anchor, "rev-parse", "--show-toplevel")
        if top.returncode != 0:
            if "not a git repository" in top.stderr:
                return None
            raise GitDidNotAnswer(target, _said(top))
        ignored = _git(anchor, "check-ignore", "-q", str(target))
    except FileNotFoundError:
        return None  # git is not installed, so nothing here can commit the file
    except subprocess.TimeoutExpired as exc:
        raise GitDidNotAnswer(target, f"git did not answer within {exc.timeout:g} s") from exc
    except OSError as exc:
        raise GitDidNotAnswer(target, f"git could not be started: {exc}") from exc
    if ignored.returncode == 0:
        return None
    if ignored.returncode == 1:
        return top.stdout.strip()
    raise GitDidNotAnswer(target, _said(ignored))


def _git(anchor: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(anchor), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        env={**os.environ, "LC_ALL": "C"},
    )


def _said(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or f"git exited with status {result.returncode}"


def paths_a_run_can_create(output: Path, scratch: Sequence[Path] = ()) -> list[Path]:
    """Every file an ingest of ``output`` may leave on disk, scratch files included.

    The manifest is written beside the corpus under a different name, so a rule
    like `bionumbers*.jsonl` ignores one and not the other. And each is written
    through a scratch file first: it is unlinked on the way out of an exception,
    but a SIGKILL, an OOM or a power cut leaves it behind on a committable path.

    ``scratch`` is the actual paths the writers will use, which the caller knows
    because it generates them — they carry a unique component so two concurrent
    builds cannot share one file, and asking git about a *representative* name
    instead would be asking about a file that never exists. The generic
    `<name>.partial` forms stay in the list as well, for a caller that passes
    nothing and for the ignore rules that are written against them.
    """
    final = [output, manifest_path_for(output)]
    return final + [p.with_name(p.name + PARTIAL_SUFFIX) for p in final] + list(scratch)


def refuse_if_committable(output: Path, scratch: Sequence[Path] = ()) -> None:
    """Raise if any file the run may create is one git would track."""
    for candidate in paths_a_run_can_create(output, scratch):
        repo = committable_repo_for(candidate)
        if repo is not None:
            raise OutputWouldBeCommitted(candidate, repo)
