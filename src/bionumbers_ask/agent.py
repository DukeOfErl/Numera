"""The agent. Static prompt, fixed tool list, checkpointed sessions.

Deliberately the first stage of a phased build: nothing dynamic. Dynamic tool
selection, a dynamic prompt, and conversation condensation are each a later step,
so that when behaviour changes it is clear which change caused it.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.sqlite import SqliteSaver

from .config import Config, NotConfigured, micro_from_provider_cost
from .events import (
    Answer,
    ConversationWarning,
    EndReason,
    Event,
    QuestionEnded,
    QuestionStarted,
    Retrieval,
)
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
# How close to the bound before the user is told. A session that went from
# working to refusing with no notice gives no chance to finish a line of enquiry.
CONVERSATION_WARN_AT = 0.75


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


def _text_of(message: object) -> str:
    """Text from a message whose content may be a string or a list of blocks.

    Anthropic-shaped and reasoning-model responses use block lists; treating only
    strings as text silently yields a blank answer that still reports success.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def default_model(config: Config) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        # Raised as a named condition rather than a bare KeyError, so `ask` can
        # end the question properly instead of the driver seeing a question start
        # and then an exception where an ending belongs.
        raise NotConfigured(
            "OPENROUTER_API_KEY is not set, so no model can be reached. "
            "Set it in the environment; it must never be committed."
        )
    return ChatOpenAI(
        model=config.model,
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
    )


# Exceptions our own tools raise deliberately, for arguments the model got wrong.
# Anything else is a defect here and must not be dressed up as a lookup failure.
_EXPECTED_TOOL_ERRORS = (ValueError, KeyError, TypeError)


def _tool_error_message(exc: Exception, request: object) -> str | None:
    """What the agent sees when a tool raises -- or None to let it propagate.

    Returning a message for every exception would hand a genuine defect to the
    model as a retryable lookup failure: it would retry, fail again, and report
    that the corpus has nothing on the subject. A wrong grounded-sounding answer
    is far worse than a crash. Only argument errors are surfaced, and only by
    type, since an exception message may carry internal detail.
    """
    if not isinstance(exc, _EXPECTED_TOOL_ERRORS):
        return None
    return (
        f"The tool rejected those arguments ({type(exc).__name__}). "
        "This says nothing about what the corpus contains. Correct the arguments "
        "and try again, or report that the lookup could not be completed."
    )


# Retry settings, at module level so tests can shorten the delays without
# reaching into the middleware list.
RUN_CALL_LIMIT = 12
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
        # Order matters and is not cosmetic. First in the list is outermost, and
        # ToolRetryMiddleware only retries when the handler raises -- so with
        # ToolErrorMiddleware inside it, every exception would be converted to a
        # ToolMessage before retry ever saw one, and retries would silently never
        # happen. ToolErrorMiddleware's own docstring specifies this arrangement:
        # retry placed inner, with on_failure="error" so exhaustion propagates out
        # to be turned into something the agent can act on.
        ToolErrorMiddleware(on_error=_tool_error_message),
        ToolRetryMiddleware(
            max_retries=TOOL_RETRIES,
            backoff_factor=2.0,
            initial_delay=RETRY_INITIAL_DELAY,
            on_failure="error",
        ),
        # Brought forward from the retrieval-effort task: until the spend gate
        # exists, this is the only thing standing between a loop and the bill.
        #
        # exit_behavior="error" rather than "end": ending injects an AIMessage
        # reading "Model call limits exceeded", which this loop would adopt as the
        # answer and report as a complete one. Raising lets the limit be named.
        ModelCallLimitMiddleware(run_limit=RUN_CALL_LIMIT, exit_behavior="error"),
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
        """How many messages a session holds.

        Read straight from the checkpoint. Constructing an agent for this would
        build a chat model, which reads the API key from the environment -- so a
        driver asking how full a session is would fail wherever that key is
        absent, to answer a question needing no model at all.
        """
        with self._saver() as saver:
            record = saver.get_tuple({"configurable": {"thread_id": session_id}})
        if record is None:
            return 0
        return len((record.checkpoint.get("channel_values") or {}).get("messages", []))

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
        try:
            model = self._model or default_model(self._config)
        except NotConfigured as exc:
            # Every path out of this generator that does not raise must end with a
            # QuestionEnded: a driver pairing starts with endings, or rendering
            # progress until one arrives, otherwise waits for an event that never
            # comes. Only NotConfigured is caught here -- a genuine defect must
            # still surface as one rather than be dressed up as an ending.
            trace.record("not_configured", detail=str(exc))
            yield Answer(question_id=trace.question_id, text=str(exc))
            yield QuestionEnded(
                question_id=trace.question_id,
                reason=EndReason.NOT_CONFIGURED,
                spend=0,
                model=self._config.model,
                tool_calls=0,
                incomplete=True,
            )
            return

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

            if len(existing.get("messages", [])) >= CONVERSATION_BOUND * CONVERSATION_WARN_AT:
                yield ConversationWarning(
                    question_id=trace.question_id,
                    messages=len(existing.get("messages", [])),
                    bound=CONVERSATION_BOUND,
                )

            answer_text = ""
            tool_calls = 0
            stream = agent.stream(
                {"messages": [{"role": "user", "content": question}]},
                config=config,
                stream_mode="updates",
            )
            # closing() so the stream is shut down before the checkpointer is.
            # This generator can be abandoned at any yield -- a caller breaking
            # out of the loop, or an exception from the processing below -- and
            # unwinding would otherwise close the SQLite connection while
            # LangGraph's worker threads are still writing to it, which segfaults
            # the interpreter rather than raising.
            with closing(stream):
                while True:
                    # The guard covers advancing the stream and nothing else. Wrapping
                    # the processing below would report a defect in this file as a
                    # provider failure, sending whoever debugs it to the wrong place.
                    try:
                        chunk = next(stream)
                    except StopIteration:
                        break
                    except ModelCallLimitExceededError:
                        trace.record("retrieval.bound_reached", tool_calls=tool_calls)
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.RETRIEVAL_BOUND,
                            spend=spend.micro,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            incomplete=True,
                        )
                        return
                    except Exception as exc:  # provider failure after retries are exhausted
                        trace.record("provider.failed", error=type(exc).__name__)
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
                    for update in chunk.values():
                        for message in (update or {}).get("messages", []) or []:
                            spend.add_from(message)
                            if getattr(message, "type", "") == "ai":
                                text = _text_of(message)
                                if text.strip():
                                    answer_text = text

            while pending:
                    tool_calls += 1
                    yield pending.popleft()

        if not answer_text.strip():
            # The loop finished without producing text. Reporting that as an
            # answered question would hand the driver a blank answer marked
            # complete, which is the silent failure this project cannot afford.
            trace.record("question.no_answer", tool_calls=tool_calls)
            yield QuestionEnded(
                question_id=trace.question_id,
                reason=EndReason.NO_ANSWER,
                spend=spend.micro,
                model=self._config.model,
                tool_calls=tool_calls,
                incomplete=True,
            )
            return

        trace.record("question.answered", spend_micro=spend.micro, tool_calls=tool_calls)
        yield Answer(question_id=trace.question_id, text=answer_text)
        yield QuestionEnded(
            question_id=trace.question_id,
            reason=EndReason.ANSWERED,
            spend=spend.micro,
            model=self._config.model,
            tool_calls=tool_calls,
        )
