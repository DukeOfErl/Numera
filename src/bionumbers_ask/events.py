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
    question_id: str
    spent: int
    threshold: int


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
    model: str
    tool_calls: int
    incomplete: bool = False


Event = (
    QuestionStarted | Retrieval | ConversationWarning | SpendWarning | Answer | QuestionEnded
)
