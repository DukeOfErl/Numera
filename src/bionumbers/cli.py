"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from bionumbers.corpus import CorpusError, load_corpus


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bionumbers",
        description="Grounding validator for claimed biological quantities.",
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help="Path to the JSONL evaluation corpus. Required; there is no bundled corpus.",
    )
    args = parser.parse_args(argv)

    try:
        entries = load_corpus(args.corpus)
    except CorpusError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"Loaded {len(entries)} entries from {args.corpus}")
    return 0
