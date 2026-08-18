"""Model doubles for the agent tests. Nothing here reaches a provider.

The stock fakes in langchain_core do not implement bind_tools, so an agent that
binds tools to them fails with NotImplementedError before any tool can run. This
double supports binding, which is the whole point of testing an agent.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedModel(BaseChatModel):
    """Returns the scripted messages in order; optionally fails first.

    `failures` exists because retry cannot be tested against a model that never
    fails, and a real provider cannot be made to fail on demand.
    """

    responses: list[BaseMessage] = []
    index: int = 0
    failures: int = 0
    attempts: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError(f"upstream unavailable (attempt {self.attempts})")
        message = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def scripted(*responses: BaseMessage, failures: int = 0) -> ScriptedModel:
    return ScriptedModel(responses=list(responses), failures=failures)


def tool_call(name: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call-1"}])


def says(text: str) -> AIMessage:
    return AIMessage(content=text)
