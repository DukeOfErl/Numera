"""``bionumbers-ingest`` — build a corpus from the published BioNumbers export.

Two defaults are inverted from the first-pass ingester this ports, and both
inversions exist because the original's default produced a corpus that looked
complete and was not:

- **The whole file is processed.** A row limit is an explicit request, not a
  default, and a limited run says so in its report and its manifest.
- **The output appears only on success.** A failed or interrupted run leaves the
  previous corpus or nothing, never a truncated one.

The corpus is written under ``data/`` by default, which is git-ignored: the
published data's licensing is unresolved, so nothing derived from it may enter
the repository (ADR-0200).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from bionumbers_ingest.ingest import VERSION, ingest
from bionumbers_ingest.io import PARTIAL_SUFFIX
from bionumbers_ingest.provenance import manifest_path_for

DEFAULT_OUTPUT = Path("data/processed/bionumbers.jsonl")


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
    that is how 19.5 MB of unlicensed data reaches a public history — the single
    irreversible mistake this change can make.

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


def _paths_a_run_can_create(output: Path) -> list[Path]:
    """Every file an ingest of ``output`` may leave on disk, partials included."""
    final = [output, manifest_path_for(output)]
    return final + [p.with_name(p.name + PARTIAL_SUFFIX) for p in final]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bionumbers-ingest",
        description=(
            "Turn the published BioNumbers export (an HTML table saved as .xls) "
            "into a JSONL corpus, with a manifest recording what was read."
        ),
    )
    parser.add_argument("source", help="path to the export, as published")
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"where to write the corpus (default: {DEFAULT_OUTPUT}, which is git-ignored)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help=(
            "process only the first N rows. NOT the default: a sampled corpus "
            "looks complete and is not, so the limit must be asked for and is "
            "recorded in the manifest."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.limit is not None and args.limit < 1:
        # `--limit -100` is truthy and compares as "already past the limit", so it
        # used to write a one-row corpus and exit 0. Given that a sampled corpus
        # looks complete and is not, a typo here is the worst thing to accept.
        print(
            f"bionumbers-ingest: --limit must be at least 1, got {args.limit}",
            file=sys.stderr,
        )
        return 2

    output = Path(args.output)
    # Every file the run can create, not just the corpus. The manifest is written
    # beside it under a different name, so a rule like `bionumbers*.jsonl` ignores
    # one and not the other. And each is written through a `.partial` first, which
    # a suffix-matching ignore rule does not cover either: the partial is unlinked
    # on the way out of an exception, but a SIGKILL, an OOM or a power cut leaves
    # ~19.5 MB of unlicensed export data on a committable path, which `git add .`
    # would then take.
    for candidate in _paths_a_run_can_create(output):
        repo = committable_repo_for(candidate)
        if repo is not None:
            break
    if repo is not None:
        print(
            f"bionumbers-ingest: refusing to write {candidate} — git would track it "
            f"in {repo}.\n"
            f"  The published BioNumbers data has unresolved licensing, so nothing "
            f"derived from it may enter a repository (ADR-0200), and git history is "
            f"permanent.\n"
            f"  Either write it outside the repository, or add the path to that "
            f"repository's .gitignore.",
            file=sys.stderr,
        )
        return 3

    source = Path(args.source)
    try:
        result = ingest(source, output, limit=args.limit)
    except OSError as exc:
        # Covers a missing source as well as an unwritable destination, so it
        # names the file the operating system actually complained about — saying
        # "cannot read <source>" when the output directory is read-only sends the
        # reader to the wrong file.
        blamed = exc.filename or source
        print(f"bionumbers-ingest: {exc.strerror or exc}: {blamed}", file=sys.stderr)
        return 2
    except ValueError as exc:
        # A malformed or truncated source, or columns that are not the ones this
        # ingester reads. Failing is the point: each of those otherwise produces a
        # corpus that is short or shifted and reports success.
        print(f"bionumbers-ingest: {source} cannot be ingested: {exc}", file=sys.stderr)
        return 1

    print(result.report.format())
    print(f"\n  corpus:   {result.corpus_path}")
    print(f"  manifest: {result.manifest_path}")
    print(f"  source stamped on every record: {result.source_digest}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
