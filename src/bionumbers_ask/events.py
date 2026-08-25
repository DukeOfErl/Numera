"""The port: what the agent emits, and what it accepts.

This is the boundary in ports and adapters. The agent never reads input or writes
output; it yields these events and takes an Ask. A terminal renders them, a web
interface renders them, and the evaluation harness records them -- three adapters
over one agent, with no mode flag inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EndReason(StrEnum):
    """Why a question stopped. Every ending has one; none is a bare failure."""

    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    NOT_CONFIGURED = "not_configured"
    SPEND_CEILING = "spend_ceiling"
    RUN_BUDGET = "run_budget"
    RETRIEVAL_BOUND = "retrieval_bound"
    PROVIDER_FAILURE = "provider_failure"
    CONVERSATION_BOUND = "conversation_bound"


@dataclass(frozen=True)
class Ask:
    """The only command in this build. Approval is deferred; see the proposal."""

    session_id: str
    question: str


@dataclass(frozen=True)
class QuestionStarted:
    question_id: str
    session_id: str
    question: str


@dataclass(frozen=True)
class Retrieval:
    """Emitted as it happens, so a driver can show progress before the answer.

    A driver that only received the answer would have nothing to render during a
    long question but a spinner.
    """

    question_id: str
    tool: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationWarning:
    """The session is nearing its length bound.

    A session that went from working to refusing with no notice would give the
    user no chance to finish what they were doing.
    """

    question_id: str
    messages: int
    bound: int


@dataclass(frozen=True)
class SpendWarning:
    """Spend has passed the warning threshold. Work continues.

    The threshold is notice and the ceiling is the stop; a run that only ever
    announced the stop would give no chance to intervene first.
    """

    question_id: str
    spent: int
    threshold: int


@dataclass(frozen=True)
class CostProjection:
    """An upper-bound estimate emitted before work begins, never enforcement.

    Emitted only when the projection exceeds the warning threshold, so it is a
    flag rather than a running commentary.
    """

    question_id: str
    projected: int
    threshold: int


@dataclass(frozen=True)
class CitationWarning:
    """An answer cited something it should not have been able to.

    `unknown` is not in the corpus at all; `unretrieved` exists but was never
    returned by a tool call during this question, which means it came from the
    model's own memory rather than from the corpus.
    """

    question_id: str
    unknown: tuple[int, ...] = ()
    unretrieved: tuple[int, ...] = ()


@dataclass(frozen=True)
class AnswerEntries:
    """The entries a question retrieved, so an answer can be checked against them.

    Identifiers rather than whole entries: a driver has the corpus and can look up
    what it displays, and the reference column is long enough that carrying it
    through the agent would tempt someone into sending it to the model.
    """

    question_id: str
    cited: tuple[int, ...] = ()
    retrieved: tuple[int, ...] = ()


@dataclass(frozen=True)
class Answer:
    question_id: str
    text: str


@dataclass(frozen=True)
class QuestionEnded:
    """Carries why it ended and what it consumed, so a limit is explicable."""

    question_id: str
    reason: EndReason
    spend: int
    run_spend: int
    model: str
    tool_calls: int
    incomplete: bool = False


Event = (
    QuestionStarted
    | Retrieval
    | ConversationWarning
    | SpendWarning
    | CostProjection
    | Answer
    | CitationWarning
    | AnswerEntries
    | QuestionEnded
)
