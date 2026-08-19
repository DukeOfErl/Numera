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

from .config import Config, NotConfigured, format_usd
from .events import (
    Answer,
    ConversationWarning,
    CostProjection,
    EndReason,
    Event,
    QuestionEnded,
    QuestionStarted,
    Retrieval,
)
from .repository import CorpusRepository
from .spend import (
    SpendGate,
    SpendLedger,
    SpendLimitReached,
    Unpriceable,
    project_question_cost,
)
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


def _retry_on(exc: Exception) -> bool:
    """Retry transient failures, but never a spend limit or an unpriceable response.

    The default is `(Exception,)`, which would retry the gate's own refusal: the
    question would sleep through the full backoff and then fail anyway, so a
    question stopped on its ceiling would take seconds longer to say so. Retrying
    an unpriceable response is equally futile -- a provider that reports no cost
    will not start reporting one on the second attempt.
    """
    return not isinstance(exc, (SpendLimitReached, Unpriceable))


def _middleware(gate: SpendGate) -> list:
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
            retry_on=_retry_on,
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
        # A retrieval bound, not a cost guard -- the spend gate below is what
        # bounds the bill. This limits how much searching one question may do.
        #
        # exit_behavior="error" rather than "end": ending injects an AIMessage
        # reading "Model call limits exceeded", which this loop would adopt as the
        # answer and report as a complete one. Raising lets the limit be named.
        ModelCallLimitMiddleware(run_limit=RUN_CALL_LIMIT, exit_behavior="error"),
        # Innermost, so it is the last thing between the loop and a dispatched
        # request, and so each attempt the retry middleware makes passes through it.
        gate,
    ]


def _persisted(saver: SqliteSaver, session_id: str) -> dict:
    """The session's persisted state, or an empty mapping if it has none.

    Read straight from the checkpoint rather than through the agent, because the
    gate has to be constructed from these values before there is an agent to ask.
    """
    record = saver.get_tuple({"configurable": {"thread_id": session_id}})
    if record is None:
        return {}
    return record.checkpoint.get("channel_values") or {}


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
            return len(_persisted(saver, session_id).get("messages") or [])

    def run_spend(self, session_id: str) -> int:
        """What this session has spent so far, across all its questions.

        Same reasoning as conversation_length: a driver deciding whether to offer
        another question needs this without building a model.
        """
        with self._saver() as saver:
            return _persisted(saver, session_id).get("run_spend") or 0

    def ask(self, session_id: str, question: str) -> Iterator[Event]:
        """Answer a question, emitting events as the work happens.

        A generator rather than a callback or a blocking call: the driver decides
        when to consume, so nothing here waits on an interface.
        """
        trace = start_question()
        yield QuestionStarted(question_id=trace.question_id, session_id=session_id, question=question)

        # Retrievals and spend warnings both arrive from inside the agent loop, so
        # they queue here and are drained at each step of the stream.
        pending: deque[Event] = deque()
        tools = build_tools(self._repo, trace, pending.append)
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
                run_spend=0,
                model=self._config.model,
                tool_calls=0,
                incomplete=True,
            )
            return

        with self._saver() as saver:
            # One read of the checkpoint, before the agent exists: the conversation
            # bound, the run budget, and the ceiling in force all come from it, and
            # the gate must be constructed with them.
            persisted = _persisted(saver, session_id)
            messages = persisted.get("messages") or []
            run_spend = persisted.get("run_spend") or 0
            # The ceiling a session was created with is the one it keeps. A session
            # resumed by a process with a different environment must not be handed a
            # larger budget part-way through; reconfiguring bounds new sessions.
            ceiling = persisted.get("spend_ceiling") or self._config.question_ceiling

            if run_spend >= self._config.run_budget:
                trace.record("run.budget_reached", run_spend=run_spend)
                yield Answer(
                    question_id=trace.question_id,
                    text=(
                        f"This run has spent {format_usd(run_spend)} of its "
                        f"{format_usd(self._config.run_budget)} budget, so no further "
                        "question can be started. Raise the budget or start a new run."
                    ),
                )
                yield QuestionEnded(
                    question_id=trace.question_id,
                    reason=EndReason.RUN_BUDGET,
                    spend=0,
                    run_spend=run_spend,
                    model=self._config.model,
                    tool_calls=0,
                    incomplete=True,
                )
                return

            if len(messages) >= CONVERSATION_BOUND:
                trace.record("conversation.bound_reached", messages=len(messages))
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
                    run_spend=run_spend,
                    model=self._config.model,
                    tool_calls=0,
                    incomplete=True,
                )
                return

            if len(messages) >= CONVERSATION_BOUND * CONVERSATION_WARN_AT:
                yield ConversationWarning(
                    question_id=trace.question_id,
                    messages=len(messages),
                    bound=CONVERSATION_BOUND,
                )

            # Before any work: an upper bound on what this question could cost,
            # flagged only if it exceeds the warning threshold. An estimate, never
            # enforcement -- the gate below acts on measured spend alone.
            projected = project_question_cost(self._config, question, RUN_CALL_LIMIT)
            if projected is not None and projected > self._config.warning_threshold:
                trace.record("spend.projected", projected=projected)
                yield CostProjection(
                    question_id=trace.question_id,
                    projected=projected,
                    threshold=self._config.warning_threshold,
                )

            ledger = SpendLedger(
                model=self._config.model,
                prices=self._config.prices_for(self._config.model),
                run_spend=run_spend,
            )
            gate = SpendGate(
                ledger=ledger,
                ceiling=ceiling,
                run_budget=self._config.run_budget,
                warning_threshold=self._config.warning_threshold,
                question_id=trace.question_id,
                emit=pending.append,
                trace=trace,
            )

            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
                middleware=_middleware(gate),
                checkpointer=saver,
            )
            config = {"configurable": {"thread_id": session_id}, **trace.run_config("ask")}

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
                    except SpendLimitReached as limit:
                        trace.record(
                            "spend.limit_reached",
                            reason=limit.reason.value,
                            spent=limit.spent,
                            limit=limit.limit,
                        )
                        # The question is not discarded. Whatever the model had
                        # established is presented, and the ending marks it
                        # incomplete -- an empty answer here would throw away work
                        # that was already paid for.
                        yield Answer(
                            question_id=trace.question_id,
                            text=answer_text.strip()
                            or (
                                "I stopped on a spend limit before establishing anything I "
                                "could cite, so there is no partial answer to give."
                            ),
                        )
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=limit.reason,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            incomplete=True,
                        )
                        return
                    except Unpriceable as exc:
                        # Spend cannot be accounted for, so there is no working
                        # control: stop rather than continue blind.
                        trace.record("spend.unpriceable", detail=str(exc))
                        yield Answer(question_id=trace.question_id, text=str(exc))
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.NOT_CONFIGURED,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            incomplete=True,
                        )
                        return
                    except ModelCallLimitExceededError:
                        trace.record("retrieval.bound_reached", tool_calls=tool_calls)
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.RETRIEVAL_BOUND,
                            spend=ledger.question,
                            run_spend=ledger.run,
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
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            incomplete=True,
                        )
                        return

                    # Only retrievals are tool calls. Counting every queued event
                    # would inflate the figure by one for each spend warning.
                    while pending:
                        event = pending.popleft()
                        if isinstance(event, Retrieval):
                            tool_calls += 1
                        yield event
                    for update in chunk.values():
                        for message in (update or {}).get("messages", []) or []:
                            if getattr(message, "type", "") == "ai":
                                text = _text_of(message)
                                if text.strip():
                                    answer_text = text

            while pending:
                event = pending.popleft()
                if isinstance(event, Retrieval):
                    tool_calls += 1
                yield event

        if not answer_text.strip():
            # The loop finished without producing text. Reporting that as an
            # answered question would hand the driver a blank answer marked
            # complete, which is the silent failure this project cannot afford.
            trace.record("question.no_answer", tool_calls=tool_calls)
            yield QuestionEnded(
                question_id=trace.question_id,
                reason=EndReason.NO_ANSWER,
                spend=ledger.question,
                run_spend=ledger.run,
                model=self._config.model,
                tool_calls=tool_calls,
                incomplete=True,
            )
            return

        trace.record(
            "question.answered",
            spend_micro=ledger.question,
            run_spend_micro=ledger.run,
            tool_calls=tool_calls,
        )
        yield Answer(question_id=trace.question_id, text=answer_text)
        yield QuestionEnded(
            question_id=trace.question_id,
            reason=EndReason.ANSWERED,
            spend=ledger.question,
            run_spend=ledger.run,
            model=self._config.model,
            tool_calls=tool_calls,
        )
