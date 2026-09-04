"""The evaluation command. A third adapter over the agent, alongside `cli` and `web`.

Only `check` so far: it reads a question set and says whether it can be evaluated
against. The subcommand exists from the start rather than a bare path argument
because `run`, `report` and `judge` follow, and a positional that means one thing
today and another next week is the kind of interface change that breaks a script
nobody remembers writing.
"""

from __future__ import annotations

import argparse
import sys

from . import autobuild
from .config import NotConfigured, env_setting, refuse_retired_env
from .corpus import CorpusUnavailable, load
from .question_set import QuestionSetError, load_question_set

PROG = "scinumbers-eval"


def main(argv: list[str] | None = None) -> None:
    # Before the parser, as in `cli.main`: `--corpus` reads the environment as its
    # default, and argparse evaluates that when the argument is declared, so a
    # retired variable name would escape as a traceback instead of its instructions.
    try:
        refuse_retired_env()
    except NotConfigured as exc:
        raise SystemExit(f"{PROG}: {exc}") from exc

    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Evaluate the ask agent against a question set.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="validate a question set")
    check.add_argument("question_set", help="path to the question set (JSONL)")
    check.add_argument(
        "--corpus",
        default=env_setting("SCINUMBERS_CORPUS"),
        help="path to the JSONL corpus (or set SCINUMBERS_CORPUS); without it the "
        "expected entries and their shapes are not checked",
    )
    args = parser.parse_args(argv)

    try:
        # Through `autobuild`, as `cli.main` does, so a configured export resolves
        # to the corpus beside it. Calling `load` on the configured path directly
        # reported the export as a corrupt corpus -- "line 1 is not a usable entry"
        # over HTML -- in the same environment where `scinumbers-ask` works.
        # Announced on stderr because stdout carries what a person reads.
        corpus = (
            autobuild.corpus_path(args.corpus, lambda text: print(text, file=sys.stderr))
            if args.corpus
            else ""
        )
        # `None` says "structure only" out loud. The parameter has no default, so a
        # later driver cannot skip the corpus checks by leaving it off.
        questions = load_question_set(args.question_set, load(corpus) if corpus else None)
    except (QuestionSetError, CorpusUnavailable, NotConfigured) as exc:
        raise SystemExit(f"{PROG}: {exc}") from exc

    followups = sum(1 for question in questions if question.follows is not None)
    unsupported = sum(1 for question in questions if question.unsupported)
    print(
        f"{len(questions)} questions, {unsupported} unsupported, "
        f"{followups} follow-up{'' if followups == 1 else 's'}."
    )
    if args.corpus:
        print("Every expected entry is in the corpus, and every entry shape is exercised.")
    else:
        # Said rather than left out. A structural pass that reads as a full pass is
        # how a set with a stale identifier reaches a run.
        print(
            "Structure only: no corpus given, so the expected entries and the shapes "
            "they carry were not checked."
        )
