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
    reports_cost: bool = True
    #: Every message this model was handed, across every call.
    #:
    #: `answer-feedback` requires that a reader's rating and comment never reach
    #: the model, and that is a statement about what it was *shown* -- which
    #: nothing could assert without this. The alternative phrasing, "the next
    #: answer is unchanged", is a counterfactual about a non-deterministic run
    #: and is not checkable at all.
    seen: list[BaseMessage] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.attempts += 1
        # Before the failure check, so a retried call still records what it was
        # handed: the question is what reached the model, not what it answered.
        self.seen.extend(messages)
        if self.attempts <= self.failures:
            raise RuntimeError(f"upstream unavailable (attempt {self.attempts})")
        message = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        # Real responses carry cost metadata, and the spend ledger refuses to run
        # against one that carries none. A double that omitted it would leave every
        # test running down a path no real call takes -- and would have left the
        # gate, which reads exactly this, unexercised.
        if self.reports_cost and not message.response_metadata:
            message = message.model_copy(update={"response_metadata": OPENROUTER_RESPONSE_METADATA})
        return ChatResult(generations=[ChatGeneration(message=message)])


def scripted(
    *responses: BaseMessage, failures: int = 0, reports_cost: bool = True
) -> ScriptedModel:
    return ScriptedModel(responses=list(responses), failures=failures, reports_cost=reports_cost)


def provider_error(status: int, message: str) -> Exception:
    """The exception a real HTTP failure from the provider arrives as.

    Built through `openai.APIStatusError` rather than imitated. A hand-rolled
    object carrying a `status_code` would pass whether or not the provider's own
    error type still has one -- and that attribute is the whole of what
    `_is_out_of_credit` reads. Any status, so the tests can pin what must *not*
    count as a spent key as precisely as what must.
    """
    import httpx
    import openai

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(
        status,
        request=request,
        json={"error": {"message": message, "code": status}},
    )
    return openai.APIStatusError(message, response=response, body=None)


def out_of_credit_error() -> Exception:
    """What OpenRouter answers when the key or the account has no credit left."""
    return provider_error(402, "Insufficient credits")


class OutOfCreditModel(ScriptedModel):
    """Answers the way OpenRouter answers a key over its limit.

    `refuse_after` is how many calls succeed first, because where the refusal lands
    changes what the reader should see: on the first call there is no answer to
    keep, and part-way through a question the earlier hops have already been paid
    for. The default refuses immediately.

    Counts attempts like its parent, because "was this retried?" is half of the
    behaviour: a 402 sent through the backoff makes the reader wait seconds for a
    sentence that was available at once.
    """

    refuse_after: int = 0

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        if self.attempts >= self.refuse_after:
            self.attempts += 1
            raise out_of_credit_error()
        return super()._generate(messages, stop, run_manager, **kwargs)


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


def costing(message: AIMessage, cost_usd: float) -> AIMessage:
    """The same message, with a provider-reported cost attached.

    The ledger reads cost from the provider, so a test that needs a particular
    spend has to say what the provider reported. Choosing the cost is also the only
    way to separate the warning threshold from the ceiling, which are 20 per cent
    apart by construction and cannot both be crossed by tuning configuration alone.
    """
    return message.model_copy(update={"response_metadata": {"token_usage": {"cost": cost_usd}}})


def reports_usage_only(text: str, input_tokens: int, output_tokens: int) -> AIMessage:
    """A response shaped like a provider that reports tokens but not cost."""
    return AIMessage(
        content=text,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )
