"""The evaluation command. A third adapter over the agent, alongside `cli` and `web`.

`check` reads a question set and says whether it can be evaluated against, `run`
asks it and records the results, and `report` reads those results back. `judge`
follows, which is why these are subcommands rather than a bare path argument -- a
positional that means one thing today and another next week breaks a script
nobody remembers writing.

The command builds the agent and hands it to the driver, rather than the driver
building one. That is what lets the driver be tested against a scripted model, and
it keeps the choice of model and corpus where the other drivers keep it.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import autobuild, messages
from .agent import AskAgent
from .config import Config, NotConfigured, env_setting, format_usd, refuse_retired_env
from .corpus import CorpusUnavailable, load
from .evaluation import ResultsFileError, provenance_for, read_results, run_evaluation
from .events import EndReason
from .question_set import QuestionSetError, load_question_set
from .report import render
from .repository import CorpusRepository

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

    ask = commands.add_parser("run", help="ask a question set and record the results")
    ask.add_argument("question_set", help="path to the question set (JSONL)")
    ask.add_argument(
        "--corpus",
        default=env_setting("SCINUMBERS_CORPUS"),
        help="path to the JSONL corpus (or set SCINUMBERS_CORPUS); required here",
    )
    ask.add_argument(
        "--results",
        default="evaluations/results.jsonl",
        help="where results are appended; an existing file is resumed, not replaced",
    )
    ask.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="how many times to ask each question; the spread across repeats is what "
        "distinguishes an improvement from a lucky trajectory",
    )
    ask.add_argument(
        "--checkpoints",
        default="checkpoints/eval.sqlite",
        help="where sessions and run spend are persisted; separate from the ask "
        "command's store, so an evaluation does not spend a person's run budget",
    )
    shown = commands.add_parser("report", help="read a results file and report on it")
    shown.add_argument("question_set", help="path to the question set (JSONL)")
    shown.add_argument(
        "--corpus",
        default=env_setting("SCINUMBERS_CORPUS"),
        help="path to the JSONL corpus (or set SCINUMBERS_CORPUS); required here",
    )
    shown.add_argument("--results", default="evaluations/results.jsonl")
    shown.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="how many repeats the run asked for, so a partial file can say so",
    )
    shown.add_argument("--by-tag", action="store_true", help="figures per question tag")
    shown.add_argument("--by-shape", action="store_true", help="figures per entry shape")

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
        if args.command in {"run", "report"} and not corpus:
            raise CorpusUnavailable(
                f"{args.command} needs a corpus: pass --corpus or set "
                f"SCINUMBERS_CORPUS. Checking a question set without one is "
                f"possible; asking it, or scoring what it returned, is not."
            )
        entries = load(corpus) if corpus else None
        questions = load_question_set(args.question_set, entries)
    except (QuestionSetError, CorpusUnavailable, NotConfigured) as exc:
        raise SystemExit(f"{PROG}: {exc}") from exc

    if args.command == "run":
        # `entries` rather than the path: `main` has already parsed the corpus for
        # `check_against_corpus`, and a 20-30 MB file was being read a second time
        # with both copies alive for the length of the run.
        _run(args, questions, corpus, entries or ())
        return

    if args.command == "report":
        try:
            results = read_results(args.results)
        except ResultsFileError as exc:
            raise SystemExit(f"{PROG}: {exc}") from exc
        print(
            render(
                results,
                questions,
                entries or (),
                repeats=args.repeats,
                by_tag=args.by_tag,
                by_shape=args.by_shape,
            ),
            end="",
        )
        return

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


def _run(args, questions, corpus: str, entries) -> None:
    """Ask the set and record it. Everything printed here goes to stdout as text."""
    try:
        config = Config.from_env()
    except NotConfigured as exc:
        raise SystemExit(f"{PROG}: {exc}") from exc
    directory = os.path.dirname(args.checkpoints)
    if directory:
        os.makedirs(directory, exist_ok=True)

    agent = AskAgent(CorpusRepository(entries), config, args.checkpoints)
    provenance = provenance_for(config, corpus, len(entries))
    print(
        f"{len(questions)} questions x {args.repeats}, model {config.model}, "
        f"run budget {format_usd(config.run_budget)}, code {provenance.code_version}."
    )
    try:
        outcome = run_evaluation(
            agent,
            questions,
            args.results,
            provenance,
            repeats=args.repeats,
            announce=lambda text: print(text, file=sys.stderr),
        )
    except (ResultsFileError, ValueError) as exc:
        raise SystemExit(f"{PROG}: {exc}") from exc

    print(f"Recorded {outcome.recorded} of {outcome.attempted} attempted in {args.results}.")
    if outcome.failed:
        print(f"{outcome.failed} question(s) failed and were recorded as failures.")
    if outcome.stopped_on is not None:
        # Said plainly, because a partial run that reads as a complete one is the
        # way a report comes to describe a set it never finished asking.
        #
        # The remedy is named per reason rather than assumed. Telling someone to
        # raise SCINUMBERS_RUN_BUDGET_USD when the API key has no credit left sends
        # them to change the one number that cannot help.
        print(
            f"The run stopped on {outcome.stopped_on.value}; "
            f"{outcome.questions_skipped} question(s) were not asked."
        )
        if outcome.stopped_on is EndReason.RUN_BUDGET:
            print(
                f"The budget was {format_usd(config.run_budget)}. Raise "
                "SCINUMBERS_RUN_BUDGET_USD and run again to resume where this stopped."
            )
        else:
            advice = messages.run_over_advice(outcome.stopped_on)
            if advice:
                print(advice)
            print("Run again once that is resolved; it resumes where this stopped.")
