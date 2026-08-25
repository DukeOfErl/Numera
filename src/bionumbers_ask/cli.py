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
from typing import Any, TextIO

from . import entries_table
from .agent import AskAgent
from .citations import format_citation
from .config import Config, format_usd
from .corpus import CorpusUnavailable, load
from .events import (
    Answer,
    AnswerEntries,
    CitationWarning,
    ConversationWarning,
    CostProjection,
    EndReason,
    Event,
    QuestionEnded,
    Retrieval,
    SpendWarning,
)
from .repository import CorpusRepository

# Endings that finish the run rather than the question. Continuing past a spent
# budget or a full conversation would put the same refusal on every subsequent
# question, which reads as a broken prompt rather than a limit.
STOP_THE_RUN = {
    EndReason.RUN_BUDGET,
    EndReason.CONVERSATION_BOUND,
    EndReason.NOT_CONFIGURED,
}


# Carried for the entries table and the citation check, not for a person to read:
# fifty identifiers on a progress line would bury what the search was for.
_UNRENDERED_DETAIL = {"bnids"}


def _detail(detail: dict[str, Any]) -> str:
    return " ".join(
        f"{k}={v!r}"
        for k, v in detail.items()
        if v is not None and k not in _UNRENDERED_DETAIL
    )


def render(event: Event, repo: CorpusRepository | None = None) -> str | None:
    """One line for an event, or None for one a terminal need not show.

    A pure function so the rendering can be tested without a terminal, and so the
    driver's only other job -- deciding when to stop -- is the only thing the loop
    below actually does.
    """
    if isinstance(event, Retrieval):
        return f"  · {event.tool} {_detail(event.detail)}".rstrip()
    if isinstance(event, ConversationWarning):
        return (
            f"  ! this session holds {event.messages} of {event.bound} messages; "
            "it will stop taking questions at the bound"
        )
    if isinstance(event, SpendWarning):
        return (
            f"  ! spent {format_usd(event.spent)}, past the "
            f"{format_usd(event.threshold)} warning threshold"
        )
    if isinstance(event, CostProjection):
        return (
            f"  ! this question could cost up to {format_usd(event.projected)}, "
            f"above the {format_usd(event.threshold)} threshold (an estimate)"
        )
    if isinstance(event, CitationWarning):
        parts = []
        if event.unknown:
            parts.append(f"not in the corpus: {', '.join(map(format_citation, event.unknown))}")
        if event.unretrieved:
            parts.append(
                "cited without being retrieved: "
                + ", ".join(map(format_citation, event.unretrieved))
            )
        return f"  ! {'; '.join(parts)}"
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
        return f"\n{event.text}\n"
    if isinstance(event, QuestionEnded):
        mark = " (incomplete)" if event.incomplete else ""
        return (
            f"  — {event.reason.value}{mark} · {format_usd(event.spend)} "
            f"(run {format_usd(event.run_spend)}) · {event.model} · "
            f"{event.tool_calls} tool calls"
        )
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
            if isinstance(event, QuestionEnded) and event.reason in STOP_THE_RUN:
                if event.reason is EndReason.NOT_CONFIGURED:
                    code = 1
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
    parser = argparse.ArgumentParser(
        prog="bionumbers-ask",
        description="Ask questions about biological quantities, answered only from a corpus.",
    )
    parser.add_argument(
        "--corpus",
        default=os.environ.get("BIONUMBERS_ASK_CORPUS", ""),
        help="path to the JSONL corpus (or set BIONUMBERS_ASK_CORPUS)",
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
        "--ask",
        default="",
        help="ask a single question and exit, instead of reading from the terminal",
    )
    args = parser.parse_args(argv)

    try:
        repo = CorpusRepository(load(args.corpus))
    except CorpusUnavailable as exc:
        raise SystemExit(f"bionumbers-ask: {exc}") from exc

    config = Config.from_env()
    # The store is created on demand by the checkpointer, but its directory is not.
    directory = os.path.dirname(args.checkpoints)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # A fresh session per launch unless one is named. The run budget is persisted
    # per session, so reusing one silently would carry a spent budget into what
    # looks like a new run.
    session_id = args.session or uuid.uuid4().hex[:8]
    agent = AskAgent(repo, config, args.checkpoints)

    if args.ask:
        raise SystemExit(run(agent, session_id, [args.ask], repo=repo))

    print(f"{len(repo)} entries · session {session_id} · {config.model}")
    print("Ask a question, or 'exit'. Continue this session later with --session.")
    raise SystemExit(
        run(agent, session_id, _questions_from_terminal(sys.stdout), repo=repo)
    )
