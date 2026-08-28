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
from dataclasses import dataclass, field
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.sqlite import SqliteSaver

from . import run_ledger
from .citations import citations
from .config import Config, NotConfigured, format_usd
from .events import (
    Answer,
    AnswerEntries,
    CitationWarning,
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

1. Cite every quantity you state, by its bnid, written as "BNID 100002" -- the \
word BNID, a space, then the number, every time. A quantity you cannot attribute \
to an entry you retrieved does not go in the answer.
2. When you find nothing, say you could not find it -- not that the corpus does \
not contain it. You searched some wordings, not every one, so name briefly what \
you looked for and leave the difference visible. Do not answer from your own \
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

# How large a session's conversation may grow, in tokens, before it stops taking
# questions. Tokens rather than messages because context length is the hazard and
# a message is a poor proxy for it: a retrieved entry's payload runs from 16
# characters to 8,023 across the corpus, so sixty messages is anywhere from a few
# thousand tokens to well over a hundred thousand. ADR-0180.
#
# 120,000 against the development model's 200,000-token window, leaving room for
# a question's own retrievals -- a capped search is about 2,100 tokens and a full
# entry about 180 -- and for the answer. A number to tune against real sessions;
# the design records condensing instead as deferred.
CONVERSATION_BOUND = 120_000
# How close to the bound before the user is told. A session that went from
# working to refusing with no notice gives no chance to finish a line of enquiry.
CONVERSATION_WARN_AT = 0.75


def _conversation_size(persisted: dict, messages: list) -> int:
    """How large this conversation is, in tokens.

    The provider's own figure where there is one: `prompt_tokens` is exactly the
    size of what was sent, needs no tokeniser here, and cannot drift from what the
    model actually received. It is retrospective -- it describes the last request
    rather than the next -- so the bound arrives one call late, which is the same
    one-call overshoot the spend ceiling has and is accepted for the same reason.

    Counted locally when there is none. A session's first question has made no
    request yet, and a provider that reports no usage would otherwise leave this
    at zero for ever: a bound that can never be reached, which is the failure
    mode this project has already met once from the other side.
    """
    reported = persisted.get("prompt_tokens") or 0
    if reported:
        return int(reported)
    return count_tokens_approximately(messages) if messages else 0


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
# Exceptions that mean this code is wrong, not that a request failed. A network
# error, a rate limit or a malformed provider response are conditions to retry;
# these are defects, and no number of retries fixes one. Deliberately the
# unambiguous ones only: a KeyError can come from a provider payload shaped
# differently than expected, which is a bad response as much as a bad assumption.
OUR_DEFECT = (
    AttributeError,
    NameError,
    TypeError,
    IndexError,
    ZeroDivisionError,
    AssertionError,
)


def _origin(exc: BaseException) -> str:
    """Where in this package the exception was raised, for the trail.

    The innermost of our own frames, so a defect surfacing deep inside a library
    still points at the line of ours that led there.
    """
    frame = exc.__traceback__
    where = ""
    while frame is not None:
        name = frame.tb_frame.f_code.co_filename
        if "bionumbers_ask" in name:
            where = f"{Path(name).name}:{frame.tb_lineno}"
        frame = frame.tb_next
    return where


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


@dataclass
class _Retrieved:
    """What a question put in front of the model, and how much it passed over."""

    bnids: dict[int, None] = field(default_factory=dict)
    matched: int = 0
    searches: int = 0


def _collect(retrieved: _Retrieved, event: Retrieval) -> None:
    """Record which entries a retrieval put in front of the model.

    A search reports every identifier it returned; a fetch reports the one it
    found. Both count: an entry shown in a search row carries enough to be cited
    from, so requiring a fetch would flag legitimate citations.
    """
    if "matched" in event.detail:
        retrieved.matched += int(event.detail["matched"])
        retrieved.searches += 1
    for bnid in event.detail.get("bnids") or ():
        retrieved.bnids.setdefault(int(bnid), None)
    # Both keys are required. `found` alone is not a fetch marker: list_values
    # reports how many vocabulary values it found under the same key, and reading
    # a bnid off that raises.
    bnid = event.detail.get("bnid")
    if bnid is not None and event.detail.get("found"):
        retrieved.bnids.setdefault(int(bnid), None)


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

    def run_spend(self) -> int:
        """What this run has spent so far, across every session in it.

        No session identifier: the run budget bounds a run, and a run is not a
        session. Keyed on the configured run label, so an evaluation driver opening
        a session per question is still bounded by one figure.

        Same reasoning as conversation_length for reading it directly: a driver
        deciding whether to offer another question needs this without building a
        model.
        """
        return run_ledger.read(self._checkpoint_path, self._config.run_label)

    def ask(self, session_id: str, question: str) -> Iterator[Event]:
        """Answer a question, emitting events as the work happens.

        A generator rather than a callback or a blocking call: the driver decides
        when to consume, so nothing here waits on an interface.
        """
        trace = start_question(self._config.run_label)
        yield QuestionStarted(
            question_id=trace.question_id, session_id=session_id, question=question
        )

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
            # From the run's ledger, not this session's checkpoint: the budget
            # bounds the run, and a driver opening a session per question would
            # otherwise start every question at zero.
            run_spend = run_ledger.read(self._checkpoint_path, self._config.run_label)
            # The ceiling a session was created with is the one it keeps. A session
            # resumed by a process with a different environment must not be handed a
            # larger budget part-way through; reconfiguring bounds new sessions.
            ceiling = persisted.get("spend_ceiling") or self._config.question_ceiling

            if run_spend >= self._config.run_budget:
                trace.record("run.budget_reached", run_spend=run_spend)
                yield Answer(
                    question_id=trace.question_id,
                    text=(
                        f"This run has spent {format_usd(run_spend)} against a "
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

            conversation_tokens = _conversation_size(persisted, messages)
            if conversation_tokens >= CONVERSATION_BOUND:
                trace.record("conversation.bound_reached", tokens=conversation_tokens)
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

            if conversation_tokens >= CONVERSATION_BOUND * CONVERSATION_WARN_AT:
                yield ConversationWarning(
                    question_id=trace.question_id,
                    tokens=conversation_tokens,
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

            def record_spend(micro: int) -> None:
                run_ledger.add(self._checkpoint_path, self._config.run_label, micro)

            gate = SpendGate(
                ledger=ledger,
                persist=record_spend,
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
            # Read from the call-limit middleware's own state updates rather than
            # counted here, so the number reported is the one that trips the bound.
            # Its run counter is untracked, so it never reaches the checkpoint and
            # has to be caught in flight.
            model_calls = 0
            # Insertion-ordered: the order entries were retrieved is the order a
            # reader met them in, and the order the table falls back to.
            retrieved = _Retrieved()

            def evidence() -> Iterator[Event]:
                """What the answer rests on, and anything it should not rest on.

                Emitted before every ending that got as far as retrieving, a limit
                included: a question stopped part-way still found entries, and
                throwing them away would discard work already paid for.

                The citation check runs whether or not anything was retrieved. It
                used to return early when nothing was, which skipped it exactly
                where it matters most: a search that matched nothing, followed by an
                answer citing an entry no tool call returned, is the model answering
                from its own memory -- and it was reported as a clean answer.
                """
                cited = citations(answer_text)
                unknown = tuple(b for b in cited if self._repo.get(b) is None)
                unretrieved = tuple(
                    b for b in cited if b not in unknown and b not in retrieved.bnids
                )
                if unknown or unretrieved:
                    # A cited entry no tool call returned came from the model's own
                    # memory. Reported rather than accepted: it is the failure this
                    # project exists to catch, and it is silent otherwise.
                    trace.record("citations.unsupported", unknown=unknown, unretrieved=unretrieved)
                    yield CitationWarning(
                        question_id=trace.question_id,
                        unknown=unknown,
                        unretrieved=unretrieved,
                    )
                if not (retrieved.bnids or retrieved.searches or cited):
                    # Nothing retrieved, nothing searched, nothing cited: there is no
                    # evidence to present, and an empty table with no counts beside it
                    # would describe a question that never looked.
                    return
                yield AnswerEntries(
                    question_id=trace.question_id,
                    cited=cited,
                    retrieved=tuple(retrieved.bnids),
                    matched=retrieved.matched,
                    searches=retrieved.searches,
                    question=question,
                )

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
                        yield from evidence()
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=limit.reason,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            incomplete=True,
                        )
                        return
                    except Unpriceable as exc:
                        # Spend cannot be accounted for, so there is no working
                        # control: stop rather than continue blind.
                        trace.record("spend.unpriceable", detail=str(exc))
                        yield Answer(question_id=trace.question_id, text=str(exc))
                        yield from evidence()
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.NOT_CONFIGURED,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            incomplete=True,
                        )
                        return
                    except ModelCallLimitExceededError:
                        trace.record(
                            "retrieval.bound_reached",
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            spend_ceiling=ceiling,
                        )
                        # Same reasoning as the spend limit above, and it was missing
                        # here: a question stopped at the bound may already have
                        # established something citable, and discarding it threw away
                        # work already paid for. The middleware's own message never
                        # reaches this -- with exit_behavior="error" it lives in the
                        # exception, not in a message the model appears to have said.
                        yield Answer(
                            question_id=trace.question_id,
                            text=answer_text.strip()
                            or (
                                "I reached the limit on how much retrieval one question "
                                "may do before establishing anything I could cite, so "
                                "there is no partial answer to give."
                            ),
                        )
                        yield from evidence()
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.RETRIEVAL_BOUND,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            incomplete=True,
                        )
                        return
                    except Exception as exc:  # the provider, or us
                        # Told apart, because they ask different things of the
                        # reader. "provider_failure" means try again; a defect in
                        # this code will do exactly the same thing on every retry,
                        # and reporting it as the provider's fault sends whoever
                        # sees it to look in the wrong place -- or to blame a
                        # service that did nothing wrong.
                        ours = isinstance(exc, OUR_DEFECT)
                        trace.record(
                            "internal.failed" if ours else "provider.failed",
                            error=type(exc).__name__,
                            message=str(exc)[:200],
                            where=_origin(exc),
                        )
                        yield from evidence()
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=(
                                EndReason.INTERNAL_ERROR if ours else EndReason.PROVIDER_FAILURE
                            ),
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            incomplete=True,
                        )
                        return

                    # Only retrievals are tool calls. Counting every queued event
                    # would inflate the figure by one for each spend warning.
                    while pending:
                        event = pending.popleft()
                        if isinstance(event, Retrieval):
                            tool_calls += 1
                            _collect(retrieved, event)
                        yield event
                    for update in chunk.values():
                        model_calls = max(
                            model_calls, (update or {}).get("run_model_call_count") or 0
                        )
                        for message in (update or {}).get("messages", []) or []:
                            if getattr(message, "type", "") == "ai":
                                text = _text_of(message)
                                if text.strip():
                                    answer_text = text

            while pending:
                event = pending.popleft()
                if isinstance(event, Retrieval):
                    tool_calls += 1
                    _collect(retrieved, event)
                yield event

        if not answer_text.strip():
            # The loop finished without producing text. Reporting that as an
            # answered question would hand the driver a blank answer marked
            # complete, which is the silent failure this project cannot afford.
            trace.record("question.no_answer", tool_calls=tool_calls)
            yield from evidence()
            yield QuestionEnded(
                question_id=trace.question_id,
                reason=EndReason.NO_ANSWER,
                spend=ledger.question,
                run_spend=ledger.run,
                model=self._config.model,
                tool_calls=tool_calls,
                model_calls=model_calls,
                call_limit=RUN_CALL_LIMIT,
                spend_ceiling=ceiling,
                incomplete=True,
            )
            return

        trace.record(
            "question.answered",
            spend_micro=ledger.question,
            run_spend_micro=ledger.run,
            tool_calls=tool_calls,
            model_calls=model_calls,
            call_limit=RUN_CALL_LIMIT,
            spend_ceiling=ceiling,
        )
        yield Answer(question_id=trace.question_id, text=answer_text)
        yield from evidence()
        yield QuestionEnded(
            question_id=trace.question_id,
            reason=EndReason.ANSWERED,
            spend=ledger.question,
            run_spend=ledger.run,
            model=self._config.model,
            tool_calls=tool_calls,
            model_calls=model_calls,
            call_limit=RUN_CALL_LIMIT,
            spend_ceiling=ceiling,
        )
