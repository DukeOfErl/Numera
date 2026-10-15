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
from langchain_core.messages import ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.sqlite import SqliteSaver

from . import run_ledger
from .citations import FORM, citations
from .config import Config, NotConfigured, format_usd, warning_for
from .corpus import EntryId, entry_key
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
    UngroundedRefusal,
)
from .repository import CorpusRepository
from .spend import (
    LedgerUnavailable,
    SpendGate,
    SpendLedger,
    SpendLimitReached,
    Unpriceable,
    project_question_cost,
)
from .tools import ToolBudget, build_tools
from .trace import QuestionTrace, start_question

# An f-string so the citation form is the one `citations.py` parses, not a copy of
# it. It was a copy, and nothing tied the two together: the prompt could have asked
# for a form the scorer did not read, and the only symptom would have been answers
# reported as uncited.
SYSTEM_PROMPT = f"""\
You answer questions about scientific quantities using only a corpus of entries, \
reached through your tools. You have no other source.

Rules, in order of importance:

1. Cite every quantity you state, by its entry identifier, written as "{FORM}" -- \
the identifier exactly as the entry gives it, inside double square brackets, every \
time. A quantity you cannot attribute to an entry you retrieved does not go in the answer.
2. Search before you answer, always, even when you are confident the corpus does \
not cover the question. An answer given without retrieving anything reports what \
you expected to find, not what is there, and "I did not find it" is only true if \
you looked. When you find nothing, say you could not find it -- not that the \
corpus does not contain it. You searched some wordings, not every one, so name briefly what \
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
6. Some entries carry a trust rating, from 5 of 5 for a curated entry down to 0 of 5 \
when no reviewer approved it. Decide first which entries bear on the question; a \
trust rating never makes an entry relevant, and a highly rated entry about another \
quantity is still about another quantity. Then, among relevant entries for the same \
quantity, prefer the better-rated one, and say so when your answer rests on an \
entry that is disputed or has not been approved. Do not write ratings or stars \
yourself; the application shows them beside your citations.

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


def _is_tool_result(message: object) -> bool:
    """Whether a persisted message is a tool result.

    By type rather than by class alone: a checkpoint read back carries whatever the
    framework serialised, and a version that reconstructs tool results as some
    other class would silently empty the record of what the agent was shown.
    """
    return isinstance(message, ToolMessage) or getattr(message, "type", "") == "tool"


def _tool_text(message: object) -> str:
    """A tool result as text, never silently blank.

    `_text_of` returns "" for content it does not recognise, which is right for an
    answer -- a blank answer is visible -- and wrong here: this is the record of
    the evidence, so an unrecognised shape is written out rather than dropped.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return _text_of(message) or str(content)


def default_model(config: Config, api_key: str | None = None) -> BaseChatModel:
    """The provider's model, funded by `api_key` -- or by the environment when None.

    The key is a parameter so that a driver holding one credential per person can
    hand each agent its own (ADR-0820). `None` reads `OPENROUTER_API_KEY` exactly
    as before, which is what the terminal, the evaluation harness and a
    deployment with no identity configured pass. The credential is the one
    per-person fact the agent needs; who the person is never arrives here.
    """
    from langchain_openai import ChatOpenAI

    key = api_key or os.environ.get("OPENROUTER_API_KEY")
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

#: The provider's answer when there is no money left. OpenRouter returns 402 both
#: for an account out of credits and for a key over its own spending limit, and
#: documents them in one sentence -- so one code covers both, which is what we
#: want: the remedy is the same, and the reader cannot tell the two apart anyway.
OUT_OF_CREDIT_STATUS = 402


def _is_out_of_credit(exc: BaseException) -> bool:
    """Whether this failure means the money ran out rather than the call went wrong.

    Reads the status code and nothing else. Not the message text: the wording is
    the provider's to change, and a rule matching on prose would go quietly false
    the day it did.

    **Conservative on purpose, because the two directions do not cost the same.**
    A transient failure misread as "out of credit" tells the reader the run is over
    when it is not, and closes the door for everyone on a reason that was not true.
    A limit misread as a transient failure costs one pointless retry and then says
    the same thing again. So only an unambiguous 402 counts, and everything else
    stays an ordinary provider failure.
    """
    return getattr(exc, "status_code", None) == OUT_OF_CREDIT_STATUS


def _origin(exc: BaseException) -> str:
    """Where in this package the exception was raised, for the trail.

    The innermost of our own frames, so a defect surfacing deep inside a library
    still points at the line of ours that led there.

    Our frames are recognised by the module name each one was compiled in, not by
    its filename. Two earlier versions of this got it wrong in the same silent
    direction -- returning no origin at all, so an internal error says the fault is
    ours without saying where, and nothing raises. First a hardcoded package name,
    which a rename falsified; then the package directory from `__file__`, which
    compares a resolved path against an *unresolved* `co_filename` and so fails
    for every exception whenever the checkout or the editable install is reached
    through a symlink. `__package__` is computed, involves no filesystem, and
    survives both.
    """
    frame = exc.__traceback__
    where = ""
    while frame is not None:
        # The dot matters: without it a sibling `scinumbers_ask_helpers` would read
        # as ours.
        module = frame.tb_frame.f_globals.get("__name__", "")
        if module == __package__ or module.startswith(f"{__package__}."):
            where = f"{Path(frame.tb_frame.f_code.co_filename).name}:{frame.tb_lineno}"
        frame = frame.tb_next
    return where


# Phrases that assert retrieval happened. Matched literally and kept short, because
# this is checked only where the tool count is already zero: the count is the
# evidence and this only distinguishes an answer that overclaimed from one that
# merely guessed. A missed phrase understates; it cannot produce a false report.
_SEARCH_CLAIMS = (
    "my search",
    "my searches",
    "i searched",
    "i have searched",
    "searching the corpus",
    "searches through",
    "based on my search",
    "after searching",
)


def _claims_searching(text: str) -> bool:
    """Whether an answer says it searched. Only meaningful where nothing was."""
    lowered = text.lower()
    return any(claim in lowered for claim in _SEARCH_CLAIMS)


RUN_CALL_LIMIT = 12
# Retrievals one question may make. Separate from RUN_CALL_LIMIT and not implied by
# it: a model batches tool calls into a single hop, so twelve model calls bought
# twenty-nine retrievals across seventeen searches in one observed question, which
# spent $0.27 and a fifth of the run budget with the spend ceiling as its only
# brake. `grounded-answering` has required this bound all along; the code was
# bounding model calls and reporting those, so spec and implementation had been
# describing different quantities.
#
# Twenty. Answers that satisfied their question used about five; the runaway used
# twenty-nine. A number to tune against real questions rather than a derived one.
TOOL_CALL_LIMIT = 20
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

    A provider out of credit is the same futility from the other side of the wire:
    the key does not acquire a balance during the backoff, so retrying only makes
    the reader wait longer for the same sentence.
    """
    return not isinstance(exc, (SpendLimitReached, Unpriceable)) and not _is_out_of_credit(exc)


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

    entry_ids: dict[EntryId, None] = field(default_factory=dict)
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
    for entry_id in event.detail.get("entry_ids") or ():
        retrieved.entry_ids.setdefault(entry_key(entry_id), None)
    # Both keys are required. `found` alone is not a fetch marker: list_values
    # reports how many vocabulary values it found under the same key, and reading
    # a entry_id off that raises.
    entry_id = event.detail.get("entry_id")
    if entry_id is not None and event.detail.get("found"):
        retrieved.entry_ids.setdefault(entry_key(entry_id), None)


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
        api_key: str | None = None,
        budget_scope: str | None = None,
    ) -> None:
        self._repo = repo
        self._config = config
        self._checkpoint_path = checkpoint_path
        self._model = model
        # The credential, and nothing else about the person it was issued to. An
        # agent is built per browser session so that each holds its own; the
        # account and the role stay in the driver and are stamped onto the trail
        # at the sink, where this class cannot see them (ADR-0820).
        self._api_key = api_key
        # An opaque string the run ledger is keyed under, beside the run label.
        # `None` keeps one pot for the whole deployment, which is what the
        # terminal, the harness and an unconfigured page want. A driver that
        # funds each reader separately passes something per reader, so one
        # reader's spend cannot close the door on another (ADR-0820). Opaque
        # deliberately: this is a funding scope, not who anybody is, and nothing
        # here can turn it back into a person.
        self._budget_scope = budget_scope

    @contextmanager
    def _saver(self):
        with SqliteSaver.from_conn_string(self._checkpoint_path) as saver:
            yield saver

    def conversation_length(self, session_id: str) -> int:
        """How many messages a session holds.

        A count of messages, and **not** comparable to `CONVERSATION_BOUND`, which
        is a number of tokens: one retrieved entry runs from 16 characters to
        8,023, so the two differ by orders of magnitude and a caller comparing
        them would find every session empty. Use `conversation_tokens` for how
        full a session is; this answers whether a turn was recorded at all.

        Read straight from the checkpoint. Constructing an agent for this would
        build a chat model, which reads the API key from the environment -- so a
        driver asking about a session would fail wherever that key is absent, to
        answer a question needing no model at all.
        """
        with self._saver() as saver:
            return len(_persisted(saver, session_id).get("messages") or [])

    def conversation_tokens(self, session_id: str) -> int:
        """How full a session is, in the units `CONVERSATION_BOUND` is expressed in."""
        with self._saver() as saver:
            persisted = _persisted(saver, session_id)
            return _conversation_size(persisted, persisted.get("messages") or [])

    def tool_results(self, session_id: str) -> tuple[str, ...]:
        """Every tool result this session was shown, in order, as plain text.

        The evaluation has to record the context the agent actually had, and the
        session's own transcript is the only thing that is that by construction.
        Rebuilding it from the entry identifiers in `Retrieval` events would need
        the tools' private rendering, would drift from it silently the first time
        that rendering changed, and could not reproduce what a `list_values` call
        or a "No entries matched" reply put in front of the model.

        Plain text and nothing else, so the message shape stays the agent's own.
        A caller wanting to know which tool produced which result reads the
        `Retrieval` events, which carry the tool and its arguments.

        Read straight from the checkpoint, for the reason `conversation_length`
        gives: constructing an agent to answer this would build a chat model and
        so demand an API key to answer a question needing no model.
        """
        with self._saver() as saver:
            messages = _persisted(saver, session_id).get("messages") or []
        return tuple(_tool_text(message) for message in messages if _is_tool_result(message))

    @property
    def run_budget(self) -> int:
        """What this run may spend, so a driver can show the limit before the first
        question rather than only once spending has started."""
        return self._config.run_budget

    def _ledger_key(self) -> str:
        """What the run ledger counts under: the run, narrowed by who funds it."""
        if not self._budget_scope:
            return self._config.run_label
        return f"{self._config.run_label}:{self._budget_scope}"

    def run_spend(self) -> int:
        """What this run has spent so far, across every session in it.

        No session identifier: the run budget bounds a run, and a run is not a
        session. Keyed on the configured run label, so an evaluation driver opening
        a session per question is still bounded by one figure.

        Same reasoning as conversation_length for reading it directly: a driver
        deciding whether to offer another question needs this without building a
        model.
        """
        return run_ledger.read(self._checkpoint_path, self._ledger_key())

    def ask(self, session_id: str, question: str) -> Iterator[Event]:
        """Answer a question, emitting events as the work happens.

        A generator rather than a callback or a blocking call: the driver decides
        when to consume, so nothing here waits on an interface.

        The question, the answer and the evidence behind it are recorded here
        rather than at the eight places inside `_ask` that can yield an `Answer`.
        A record written per branch would be a record the next branch forgets:
        seven of those eight are endings -- a spend limit, a length bound, a
        missing key -- and an ending is exactly the answer worth reading later.
        Recording off the event stream makes the ninth branch record itself.

        Each record is written *before* its event is handed on, because a driver
        can abandon this generator mid-iteration -- Streamlit does, on every
        rerun -- and code after a `yield` runs only if somebody asks for the next
        item.
        """
        trace = start_question(self._config.run_label, session_id=session_id)
        # At the start, not at the end. A question that hits a spend ceiling, a
        # missing key or a crash still leaves a record of what was asked, and
        # those are the runs worth investigating.
        trace.record("question.asked", question=question)
        for event in self._ask(session_id, question, trace):
            if isinstance(event, Answer):
                # Verbatim. A shortened answer cannot be compared against the
                # rating a reader gave it, which is what this record is for.
                trace.record("answer.given", answer=event.text)
            elif isinstance(event, AnswerEntries):
                # Cited and retrieved stay separable: "the answer stood on this"
                # and "this was in front of it" are different statements, and
                # merging them cannot be undone by a query.
                #
                # A harvested entry's label is valid for one load only, so the store's
                # id goes beside it: a saved answer is resolved by that, never by the
                # label (ADR-1610). Absent for a corpus file, whose BNIDs are both.
                saved = self._repo.saved_ids((*event.cited, *event.retrieved))
                trace.record(
                    "answer.evidence",
                    cited=list(event.cited),
                    retrieved=list(event.retrieved),
                    **({"saved_ids": saved} if saved else {}),
                )
            yield event

    def _ask(self, session_id: str, question: str, trace: QuestionTrace) -> Iterator[Event]:
        """The work itself. See `ask`, which is the only caller."""
        yield QuestionStarted(
            question_id=trace.question_id, session_id=session_id, question=question
        )

        # Retrievals and spend warnings both arrive from inside the agent loop, so
        # they queue here and are drained at each step of the stream.
        pending: deque[Event] = deque()
        budget = ToolBudget(TOOL_CALL_LIMIT)
        tools = build_tools(self._repo, trace, pending.append, budget)
        try:
            model = self._model or default_model(self._config, self._api_key)
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
            run_spend = run_ledger.read(self._checkpoint_path, self._ledger_key())
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
                        "question in it without dropping earlier context. "
                        "Please start a new session."
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
            # Against the ceiling this session actually stops at, not the one this
            # process is configured with -- a resumed session keeps its own.
            warning_threshold = warning_for(ceiling)
            if projected is not None and projected > warning_threshold:
                trace.record("spend.projected", projected=projected)
                yield CostProjection(
                    question_id=trace.question_id,
                    projected=projected,
                    threshold=warning_threshold,
                )

            ledger = SpendLedger(
                model=self._config.model,
                prices=self._config.prices_for(self._config.model),
                run_spend=run_spend,
            )

            def record_spend(micro: int) -> None:
                try:
                    run_ledger.add(self._checkpoint_path, self._ledger_key(), micro)
                except Exception as exc:
                    # A locked or unwritable store is ours to fix, and unrecorded
                    # spend is worse than a failed question: the run budget would
                    # go on enforcing a limit against a total that stopped moving.
                    raise LedgerUnavailable(
                        f"could not record spend in {self._checkpoint_path}: {exc}"
                    ) from exc

            gate = SpendGate(
                ledger=ledger,
                persist=record_spend,
                ceiling=ceiling,
                run_budget=self._config.run_budget,
                warning_threshold=warning_threshold,
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

            def evidence(judge_the_prose: bool = True) -> Iterator[Event]:
                """What the answer rests on, and anything it should not rest on.

                Emitted before every ending that got as far as retrieving, a limit
                included: a question stopped part-way still found entries, and
                throwing them away would discard work already paid for.

                The citation check runs whether or not anything was retrieved. It
                used to return early when nothing was, which skipped it exactly
                where it matters most: a search that matched nothing, followed by an
                answer citing an entry no tool call returned, is the model answering
                from its own memory -- and it was reported as a clean answer.

                `judge_the_prose=False` for an ending whose answer is this module's
                own sentence rather than the model's text. What it suppresses is the
                ungrounded report, which describes the answer the reader was shown:
                run over a substitute it says "this answer is not grounded in the
                corpus -- it says only what the model expected to find" about a
                notice that was never an answer, and writes `answer.ungrounded` to
                the trail for a question the model never answered.

                The citation check needs no such guard and does not get a misleading
                one: it reads the model's text, which is empty wherever a substitute
                was used, so it reports nothing there by construction.

                The entries are not a judgement about prose and are still emitted:
                what retrieval found before the stop was paid for too.
                """
                cited = citations(answer_text, trace=trace)
                unknown = tuple(b for b in cited if self._repo.get(b) is None)
                unretrieved = tuple(
                    b for b in cited if b not in unknown and b not in retrieved.entry_ids
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
                if not (retrieved.entry_ids or retrieved.searches or cited):
                    if not judge_the_prose:
                        # Nothing retrieved and no answer of the model's to judge.
                        # An empty entries table says nothing a reader needs.
                        return
                    # Nothing retrieved, nothing searched, nothing cited. The table
                    # is right to stay empty -- there is no evidence to show -- but
                    # the answer is not therefore fine: it describes the corpus
                    # without having read it. Reported for the same reason an
                    # unsupported citation is, and detectable the same way, from the
                    # harness's own count rather than by judging the prose.
                    trace.record(
                        "answer.ungrounded", claimed_searching=_claims_searching(answer_text)
                    )
                    yield UngroundedRefusal(
                        question_id=trace.question_id,
                        claimed_searching=_claims_searching(answer_text),
                    )
                    return
                yield AnswerEntries(
                    question_id=trace.question_id,
                    cited=cited,
                    retrieved=tuple(retrieved.entry_ids),
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
                        yield from evidence(judge_the_prose=bool(answer_text.strip()))
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=limit.reason,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            tool_call_limit=TOOL_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            run_budget=self._config.run_budget,
                            incomplete=True,
                        )
                        return
                    except Unpriceable as exc:
                        # Spend cannot be accounted for, so there is no working
                        # control: stop rather than continue blind.
                        trace.record("spend.unpriceable", detail=str(exc))
                        yield Answer(question_id=trace.question_id, text=str(exc))
                        # Never the model's text on this branch: the answer shown is
                        # always this exception's sentence, whatever the model had
                        # said. So the prose judgements never apply here.
                        yield from evidence(judge_the_prose=False)
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.NOT_CONFIGURED,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            tool_call_limit=TOOL_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            run_budget=self._config.run_budget,
                            incomplete=True,
                        )
                        return
                    except ModelCallLimitExceededError:
                        trace.record(
                            "retrieval.bound_reached",
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            tool_call_limit=TOOL_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            run_budget=self._config.run_budget,
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
                        yield from evidence(judge_the_prose=bool(answer_text.strip()))
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=EndReason.RETRIEVAL_BOUND,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            tool_call_limit=TOOL_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            run_budget=self._config.run_budget,
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
                        ours = isinstance(exc, (*OUR_DEFECT, LedgerUnavailable))
                        if ours:
                            reason = EndReason.INTERNAL_ERROR
                        elif _is_out_of_credit(exc):
                            reason = EndReason.PROVIDER_LIMIT
                        else:
                            reason = EndReason.PROVIDER_FAILURE
                        trace.record(
                            "internal.failed" if ours else "provider.failed",
                            error=type(exc).__name__,
                            message=str(exc)[:200],
                            where=_origin(exc),
                            reason=reason.value,
                        )
                        if reason is EndReason.PROVIDER_LIMIT:
                            # Whatever the model had established is presented, and
                            # the ending marks it incomplete -- the reasoning the
                            # spend limit above states, and this is the branch it
                            # matters most in: the balance usually runs out part-way
                            # through a question whose earlier hops were paid for,
                            # so discarding the text is the common case rather than
                            # the corner one.
                            #
                            # What to *do* about a spent key is not the agent's to
                            # say: which key, whose money, and who can raise it are
                            # facts about a deployment. `messages.run_over_advice`
                            # carries that sentence and both drivers render it.
                            partial = answer_text.strip()
                            yield Answer(
                                question_id=trace.question_id,
                                text=partial
                                or (
                                    "I could not answer this: the provider refused the "
                                    "request because the key or account funding it has no "
                                    "credit left."
                                ),
                            )
                            yield from evidence(judge_the_prose=bool(partial))
                        else:
                            yield from evidence()
                        yield QuestionEnded(
                            question_id=trace.question_id,
                            reason=reason,
                            spend=ledger.question,
                            run_spend=ledger.run,
                            model=self._config.model,
                            tool_calls=tool_calls,
                            model_calls=model_calls,
                            call_limit=RUN_CALL_LIMIT,
                            tool_call_limit=TOOL_CALL_LIMIT,
                            spend_ceiling=ceiling,
                            run_budget=self._config.run_budget,
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
            # No answer at all, so there is no answer to call ungrounded. Saying
            # "this answer is not grounded in the corpus" where the reader was shown
            # nothing describes something that does not exist, and `NO_ANSWER`
            # already reports what happened. Found while fixing the branches above:
            # same defect, one line further down.
            yield from evidence(judge_the_prose=False)
            yield QuestionEnded(
                question_id=trace.question_id,
                reason=EndReason.NO_ANSWER,
                spend=ledger.question,
                run_spend=ledger.run,
                model=self._config.model,
                tool_calls=tool_calls,
                model_calls=model_calls,
                call_limit=RUN_CALL_LIMIT,
                tool_call_limit=TOOL_CALL_LIMIT,
                spend_ceiling=ceiling,
                run_budget=self._config.run_budget,
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
            tool_call_limit=TOOL_CALL_LIMIT,
            spend_ceiling=ceiling,
            run_budget=self._config.run_budget,
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
            tool_call_limit=TOOL_CALL_LIMIT,
            spend_ceiling=ceiling,
            run_budget=self._config.run_budget,
        )
