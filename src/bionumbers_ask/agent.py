"""The agent. Static prompt, fixed tool list, checkpointed sessions.

Deliberately the first stage of a phased build: nothing dynamic. Dynamic tool
selection, a dynamic prompt, and conversation condensation are each a later step,
so that when behaviour changes it is clear which change caused it.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.sqlite import SqliteSaver

from .config import Config, micro_from_provider_cost
from .events import Answer, EndReason, Event, QuestionEnded, QuestionStarted, Retrieval
from .repository import CorpusRepository
from .tools import build_tools
from .trace import start_question

SYSTEM_PROMPT = """\
You answer questions about biological quantities using only a corpus of curated \
entries, reached through your tools. You have no other source.

Rules, in order of importance:

1. Cite every quantity you state, by its bnid. A quantity you cannot attribute to \
an entry you retrieved does not go in the answer.
2. If the corpus does not cover the question, say so. Do not answer from your own \
knowledge, and do not offer a number you did not retrieve. A plausible unsourced \
number is the worst thing you can produce here.
3. Before presenting two entries as differing estimates of the same quantity, \
check that their units measure the same kind of thing. A mass and a count are not \
a range.
4. When entries disagree, report the values and the conditions that distinguish \
them, rather than choosing one silently. If you do prefer one, say that the others \
differ and why.
5. If you state a number that appears in no entry -- a conversion, a ratio, an \
average -- say it is computed and cite the entries behind every input.

Cite entries in full each time, including in follow-up answers. Someone reading \
one answer on its own must still be able to trace every number.
"""

# How many messages a session may accumulate before it stops taking questions.
# Retrieved entries are large, so an unbounded session eventually fails on context
# length partway through a question. A number to tune against real sessions; the
# design records condensing instead as deferred.
CONVERSATION_BOUND = 60


@dataclass
class _Spend:
    """Minimal accumulation so an ending can report what it consumed.

    The ledger proper -- persistence, the gate, thresholds -- is spend-control's
    work. This is only enough to make QuestionEnded honest.
    """

    micro: int = 0

    def add_from(self, message: object) -> None:
        meta = getattr(message, "response_metadata", None) or {}
        cost = (meta.get("token_usage") or {}).get("cost")
        if cost:
            self.micro += micro_from_provider_cost(cost)


def default_model(config: Config) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.model,
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


def _tool_error_message(exc: Exception, request: object) -> str:
    """What the agent sees when a tool raises: the failure, and what to do next."""
    return (
        f"The tool failed: {type(exc).__name__}: {exc}. "
        "Do not treat this as evidence about the corpus. Either retry with different "
        "arguments, or report that the lookup could not be completed."
    )


# Retry settings, at module level so tests can shorten the delays without
# reaching into the middleware list.
MODEL_RETRIES = 2
TOOL_RETRIES = 2
RETRY_INITIAL_DELAY = 1.0


def _middleware() -> list:
    return [
        # A transient gateway failure should not end a question, and in an
        # evaluation it would waste a question slot and its spend.
        #
        # on_failure="error" rather than the default "continue": continuing turns an
        # exhausted provider failure into an ordinary assistant message, so an
        # outage would be reported to the user as an answer. A failure has to
        # surface as one.
        ModelRetryMiddleware(
            max_retries=MODEL_RETRIES,
            backoff_factor=2.0,
            initial_delay=RETRY_INITIAL_DELAY,
            on_failure="error",
        ),
        # Tool failures are left to continue, because ToolErrorMiddleware below
        # turns them into something the agent can act on -- which is more useful
        # than ending the question.
        ToolRetryMiddleware(
            max_retries=TOOL_RETRIES,
            backoff_factor=2.0,
            initial_delay=RETRY_INITIAL_DELAY,
        ),
        # A tool that raises returns something the agent can act on instead of
        # collapsing the run. The handler is required rather than defaulted, which
        # is the right call by the framework: silently swallowing every tool
        # exception is not a safe default.
        ToolErrorMiddleware(on_error=_tool_error_message),
        # Brought forward from the retrieval-effort task: until the spend gate
        # exists, this is the only thing standing between a loop and the bill.
        ModelCallLimitMiddleware(run_limit=12, exit_behavior="end"),
    ]


class AskAgent:
    def __init__(
        self,
        repo: CorpusRepository,
        config: Config,
        checkpoint_path: str,
        model: BaseChatModel | None = None,
    ) -> None:
        self._repo = repo
        self._config = config
        self._checkpoint_path = checkpoint_path
        self._model = model

    @contextmanager
    def _saver(self):
        with SqliteSaver.from_conn_string(self._checkpoint_path) as saver:
            yield saver

    def conversation_length(self, session_id: str) -> int:
        with self._saver() as saver:
            agent = create_agent(model=self._model or default_model(self._config), tools=[], checkpointer=saver)
            state = agent.get_state({"configurable": {"thread_id": session_id}})
            return len((state.values or {}).get("messages", []))

    def ask(self, session_id: str, question: str) -> Iterator[Event]:
        """Answer a question, emitting events as the work happens.

        A generator rather than a callback or a blocking call: the driver decides
        when to consume, so nothing here waits on an interface.
        """
        trace = start_question()
        yield QuestionStarted(question_id=trace.question_id, session_id=session_id, question=question)

        pending: deque[Retrieval] = deque()
        tools = build_tools(self._repo, trace, pending.append)
        spend = _Spend()
        model = self._model or default_model(self._config)

        with self._saver() as saver:
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
                middleware=_middleware(),
                checkpointer=saver,
            )
            config = {"configurable": {"thread_id": session_id}, **trace.run_config("ask")}

            existing = agent.get_state(config).values or {}
            if len(existing.get("messages", [])) >= CONVERSATION_BOUND:
                trace.record("conversation.bound_reached", messages=len(existing["messages"]))
                yield Answer(
                    question_id=trace.question_id,
                    text=(
                        "This conversation has reached its length limit, so I cannot take another "
                        "question in it without dropping earlier context. Please start a new session."
                    ),
                )
                yield QuestionEnded(
                    question_id=trace.question_id,
                    reason=EndReason.CONVERSATION_BOUND,
                    spend=0,
                    model=self._config.model,
                    tool_calls=0,
                    incomplete=True,
                )
                return

            answer_text = ""
            tool_calls = 0
            reason = EndReason.ANSWERED
            try:
                for chunk in agent.stream(
                    {"messages": [{"role": "user", "content": question}]},
                    config=config,
                    stream_mode="updates",
                ):
                    while pending:
                        event = pending.popleft()
                        tool_calls += 1
                        yield event
                    for update in chunk.values():
                        for message in (update or {}).get("messages", []) or []:
                            spend.add_from(message)
                            text = getattr(message, "content", "")
                            if getattr(message, "type", "") == "ai" and isinstance(text, str) and text.strip():
                                answer_text = text
            except Exception as exc:  # provider failure after retries are exhausted
                trace.record("provider.failed", error=str(exc))
                yield QuestionEnded(
                    question_id=trace.question_id,
                    reason=EndReason.PROVIDER_FAILURE,
                    spend=spend.micro,
                    model=self._config.model,
                    tool_calls=tool_calls,
                    incomplete=True,
                )
                return

            while pending:
                tool_calls += 1
                yield pending.popleft()

        trace.record("question.answered", spend_micro=spend.micro, tool_calls=tool_calls)
        yield Answer(question_id=trace.question_id, text=answer_text)
        yield QuestionEnded(
            question_id=trace.question_id,
            reason=reason,
            spend=spend.micro,
            model=self._config.model,
            tool_calls=tool_calls,
        )
