"""Terminal driver: renders the agent's events, puts questions to it as commands.

The terminal adapter in ports and adapters. It renders what the agent emits and
holds nothing of its own beyond the session identifier -- the conversation, the
accumulated spend and the ceiling in force all live in the checkpoint. That is
what lets the web driver replace this one without the agent changing, and it is
why `run` takes its questions as an iterable: the loop is the same whether they
come from a person typing or from a list in a test.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Iterable
from typing import TextIO

from . import autobuild, entries_table, messages, trace, trust_marks
from .agent import AskAgent
from .config import Config, NotConfigured, env_setting, refuse_retired_env
from .corpus import CorpusUnavailable, load_configured
from .events import (
    Answer,
    AnswerEntries,
    Event,
    QuestionEnded,
    Retrieval,
)
from .repository import CorpusRepository


# Endings that finish the run rather than the question. Continuing past a spent
# budget or a full conversation would put the same refusal on every subsequent
# question, which reads as a broken prompt rather than a limit.
def render(event: Event, repo: CorpusRepository | None = None) -> str | None:
    """One line for an event, or None for one a terminal need not show.

    A pure function so the rendering can be tested without a terminal, and so the
    driver's only other job -- deciding when to stop -- is the only thing the loop
    below actually does.
    """
    if isinstance(event, Retrieval):
        return f"  · {messages.retrieval_text(event)}"
    warning = messages.warning_text(event)
    if warning is not None:
        return f"  ! {warning}"
    if isinstance(event, AnswerEntries):
        # Needs the corpus to show anything: the event carries identifiers, and the
        # reference deliberately never travels through the agent.
        if repo is None:
            return None
        rows = entries_table.rows_for(repo, event.cited, event.retrieved, event.question)
        table = entries_table.render(
            rows,
            total=len(event.retrieved),
            matched=event.matched,
            searches=event.searches,
        )
        return f"{table}\n" if table else None
    if isinstance(event, Answer):
        # The stars are drawn here, beside each citation, and never written into the answer
        # the agent recorded (ADR-1630). A corpus file has no tiers, so its answers draw as before.
        # What they mean is said once, under the entries table, as on the page.
        drawn = dict(trust_marks.cited_stars(event.text, trust_marks.trust_lookup(repo)))
        return f"\n{trust_marks.annotate(event.text, drawn)}\n"
    if isinstance(event, QuestionEnded):
        return f"  — {messages.ending_text(event)}"
    return None


def run(
    agent: AskAgent,
    session_id: str,
    questions: Iterable[str],
    out: TextIO | None = None,
    repo: CorpusRepository | None = None,
) -> int:
    """Put each question to the agent and render what comes back.

    Returns a process exit code. Nothing about the session is remembered here
    between questions, so this function may be called repeatedly with the same
    session identifier and the conversation still continues.

    `out` resolves at call time rather than defaulting to `sys.stdout` in the
    signature: a default binds the stream at import, so anything that replaces
    sys.stdout later -- a redirect, a wrapper, a test capturing output -- would be
    written straight past.
    """
    out = out if out is not None else sys.stdout
    code = 0
    for question in questions:
        question = question.strip()
        if not question:
            continue
        for event in agent.ask(session_id, question):
            line = render(event, repo)
            if line is not None:
                print(line, file=out, flush=True)
            if isinstance(event, QuestionEnded):
                if event.incomplete:
                    # Any ending that did not finish as intended, not only a
                    # configuration error: a provider outage, a blank answer and an
                    # exhausted budget all exited zero, so a script driving --ask
                    # read them as success. `incomplete` is already the flag that
                    # says the question did not finish as intended.
                    code = 1
                if event.reason in messages.STOP_THE_RUN:
                    # Where the ending has advice of its own, said before returning:
                    # the terminal otherwise exits on the ending line alone, which
                    # names a reason without saying that the remedy is somebody
                    # else's to apply. The page shows the same sentence.
                    advice = messages.run_over_advice(event.reason)
                    if advice:
                        print(advice, file=out, flush=True)
                    return code
    return code


def _questions_from_terminal(out: TextIO) -> Iterable[str]:
    while True:
        try:
            line = input("ask> ")
        except (EOFError, KeyboardInterrupt):
            print(file=out)
            return
        if line.strip() in {"exit", "quit"}:
            return
        yield line


def main(argv: list[str] | None = None) -> None:
    # First, and before the parser exists. Two of this parser's defaults read the
    # environment, and argparse evaluates a default when the argument is *declared*
    # -- above the try below, where a raised NotConfigured escapes as a traceback
    # rather than as the sentence it was written to be.
    try:
        refuse_retired_env()
    except NotConfigured as exc:
        raise SystemExit(f"scinumbers-ask: {exc}") from exc

    parser = argparse.ArgumentParser(
        prog="scinumbers-ask",
        description="Ask questions about biological quantities, answered only from a corpus.",
    )
    parser.add_argument(
        "--corpus",
        default=env_setting("SCINUMBERS_CORPUS"),
        help="path to the JSONL corpus (or set SCINUMBERS_CORPUS)",
    )
    parser.add_argument(
        "--store",
        default=env_setting("SCINUMBERS_STORE"),
        help="path to the harvest store, instead of a corpus (or set SCINUMBERS_STORE)",
    )
    parser.add_argument(
        "--checkpoints",
        default="checkpoints/ask.sqlite",
        help="where sessions are persisted",
    )
    parser.add_argument(
        "--session",
        default="",
        help="session to continue; a new one is created and printed if omitted",
    )
    parser.add_argument(
        "--trace",
        default=env_setting("SCINUMBERS_TRACE", trace.DEFAULT_FILE),
        help=f"where the structured trail is written (default {trace.DEFAULT_FILE}); "
        "'-' for stderr, empty to discard it",
    )
    parser.add_argument(
        "--ask",
        default="",
        help="ask a single question and exit, instead of reading from the terminal",
    )
    args = parser.parse_args(argv)
    trace.to_file(args.trace)

    # Both are misconfiguration a person can fix, not a fault: the message is the
    # whole point of raising them, and a traceback buries it in a stack the reader
    # did not cause. `NotConfigured` carries the instructions for a retired
    # variable name, which arriving as a crash would waste entirely.
    try:
        # Announced on stderr: in one-shot mode stdout carries the answer, and a
        # build notice mixed into it would corrupt whatever reads that.
        # The store is read as it is and never built; both named is refused by the loader.
        corpus = args.corpus
        if not args.store:
            corpus = autobuild.corpus_path(corpus, lambda text: print(text, file=sys.stderr))
        repo = CorpusRepository(load_configured(corpus, args.store))
        config = Config.from_env()
    except (CorpusUnavailable, NotConfigured) as exc:
        raise SystemExit(f"scinumbers-ask: {exc}") from exc
    # The store is created on demand by the checkpointer, but its directory is not.
    directory = os.path.dirname(args.checkpoints)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # A fresh session per launch unless one is named. The run budget is persisted
    # per session, so reusing one silently would carry a spent budget into what
    # looks like a new run.
    session_id = args.session or uuid.uuid4().hex[:8]
    agent = AskAgent(repo, config, args.checkpoints)

    # Above the `--ask` branch, not below it. A single question is recorded the
    # same way a session's tenth is, and a reader who only ever runs `--ask` would
    # otherwise never be told. To stderr, so it cannot land in a pipeline reading
    # the answer off stdout.
    #
    # Only when something is kept. `--trace ""` discards the trail, and this
    # driver installs no durable store, so the sentence would then be false -- and
    # the requirement it implements is that a reader can learn what is kept, which
    # is a claim about accuracy rather than a fixed banner.
    if args.trace:
        print(messages.RECORDS_NOTE, file=sys.stderr)

    if args.ask:
        raise SystemExit(run(agent, session_id, [args.ask], repo=repo))

    print(f"{len(repo)} entries · session {session_id} · {config.model}")
    print("Ask a question, or 'exit'. Continue this session later with --session.")
    raise SystemExit(run(agent, session_id, _questions_from_terminal(sys.stdout), repo=repo))


if __name__ == "__main__":  # pragma: no cover
    # `python -m scinumbers_ask.<module>` imported this and exited 0 without it --
    # a command that does nothing and reports success, which is how a baseline run
    # came to be "finished" in seconds having asked no questions. `main` raises
    # `SystemExit` itself on every failure, so there is no status to forward.
    main()
