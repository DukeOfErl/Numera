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


def batched_tool_calls(*specs: tuple[str, dict[str, Any]]) -> AIMessage:
    """One assistant message requesting several tools at once.

    Real models batch tool calls into a single hop, and the framework may run them
    on worker threads. A double that only ever emits one call per hop leaves both
    of those paths -- concurrent appends to the event queue among them -- entirely
    unexercised.
    """
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call-{i}"}
            for i, (name, args) in enumerate(specs, start=1)
        ],
    )


# The response metadata OpenRouter actually returned, recorded from a live call on
# 2026-08-18 (14 prompt tokens, 4 completion tokens, anthropic/claude-haiku-4.5).
# Kept verbatim: the spend ledger reads this shape, and a mock is what preserves a
# live discovery once the live call is no longer being made.
OPENROUTER_RESPONSE_METADATA = {
    "finish_reason": "stop",
    "id": "gen-recorded",
    "logprobs": None,
    "model_name": "anthropic/claude-haiku-4.5",
    "model_provider": "openai",
    "system_fingerprint": None,
    "token_usage": {
        "completion_tokens": 4,
        "completion_tokens_details": None,
        "cost": 3.4e-05,
        "cost_details": {
            "upstream_inference_cost": 3.4e-05,
            "upstream_inference_prompt_cost": 1.4e-05,
            "upstream_inference_completions_cost": 2e-05,
        },
        "is_byok": False,
        "prompt_tokens": 14,
        "prompt_tokens_details": None,
        "total_tokens": 18,
    },
}


def says(text: str) -> AIMessage:
    return AIMessage(content=text)
