"""The spend ledger, the gate that enforces it, and a pre-flight projection.

Two things are separated here on purpose. The **ledger** is accounting: what each
request actually cost, taken from what the provider reported. The **gate** is
control: a LangChain middleware (the Decorator pattern, applied by the framework)
sitting in the dispatch path, which declines to issue a request once a limit is
reached. An instruction to the model to stay within budget is a preference it may
or may not honour; only the gate is a limit.

Money is integer micro-dollars throughout -- see `config` for why not cents.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, NotRequired

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState, PrivateStateAttr

from .config import MICRO_PER_USD, Config, ModelPrices, micro_from_provider_cost
from .events import EndReason, SpendWarning
from .trace import QuestionTrace


class Unpriceable(Exception):
    """A model response carried no cost, and nothing could price it.

    Not a defect and not a limit: a run that cannot account for what it is
    spending has no working control, so it stops. Discovering this needs a
    response, so the request that reveals it has already been billed -- what the
    spec's "no request is dispatched" bounds is every request after it.
    """


class SpendLimitReached(Exception):
    """A limit was reached, checked before this request was dispatched.

    Carries which limit: a question ceiling and a run budget are different
    outcomes for whoever reads them -- one bounds a question, the other trips a
    circuit breaker over the whole run.
    """

    def __init__(self, reason: EndReason, spent: int, limit: int) -> None:
        self.reason = reason
        self.spent = spent
        self.limit = limit
        super().__init__(f"{reason.value}: {spent} of {limit} micro-dollars spent")


@dataclass(frozen=True)
class Charge:
    """What one model response cost, and the usage behind it.

    Cost on its own cannot tell a question that got dearer because the provider
    repriced from one that got dearer because it retrieved more. Tokens are what
    separate the two, and the provider already reports them.
    """

    micro: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _usage(message: Any) -> tuple[int | None, int | None]:
    """Prompt and completion tokens, from whichever shape carries them.

    `usage_metadata` is the framework's normalised form and `token_usage` is what
    the provider returned. Which one is populated depends on the client rather
    than on anything here, so both are read.
    """
    usage = getattr(message, "usage_metadata", None) or {}
    if usage:
        return usage.get("input_tokens"), usage.get("output_tokens")
    token_usage = (getattr(message, "response_metadata", None) or {}).get("token_usage") or {}
    return token_usage.get("prompt_tokens"), token_usage.get("completion_tokens")


def _total(left: int | None, right: int | None) -> int | None:
    """Sum, treating "not reported" as different from zero.

    A response that reported nothing must not be recorded as having used no
    tokens: the first is an unknown, the second is a measurement.
    """
    if left is None:
        return right
    if right is None:
        return left
    return left + right


class SpendLedger:
    """Accumulates what the provider reports, against two counters.

    Two counters because the limits are not the same kind of thing: the
    per-question ceiling resets with every question, while the run total persists
    with the session and is what bounds an evaluation.
    """

    def __init__(self, model: str, prices: ModelPrices | None, run_spend: int = 0) -> None:
        # Public: every spend record names the model, so a trail spanning a model
        # change can be split by model without joining back to the ending event.
        self.model = model
        self._prices = prices
        self.question = 0
        self.run = run_spend

    def add_response(self, messages: Sequence[Any]) -> Charge:
        """Price the model output in one response and accumulate it.

        Only assistant messages are priced. A response may also carry a tool
        message -- the framework returns one for structured output -- and pricing
        that would raise Unpriceable over something that never cost anything.
        """
        charge = Charge()
        for message in messages:
            if getattr(message, "type", "") == "ai":
                prompt, completion = _usage(message)
                charge = Charge(
                    micro=charge.micro + self._price(message),
                    prompt_tokens=_total(charge.prompt_tokens, prompt),
                    completion_tokens=_total(charge.completion_tokens, completion),
                )
        self.question += charge.micro
        self.run += charge.micro
        return charge

    def _price(self, message: Any) -> int:
        """Provider-reported cost first, configured prices second, else stop.

        The provider's own figure needs no table kept current, does not drift when
        the provider reprices, and already accounts for cache reads and writes.
        The table is a spare, not the mechanism.
        """
        meta = getattr(message, "response_metadata", None) or {}
        cost = (meta.get("token_usage") or {}).get("cost")
        if cost:
            return micro_from_provider_cost(cost)

        input_tokens, output_tokens = _usage(message)
        if input_tokens is None and output_tokens is None:
            raise Unpriceable(
                f"{self.model} reported neither a cost nor token usage for a request, "
                "so spend cannot be accounted for. Configure a model that reports one."
            )
        if self._prices is None:
            raise Unpriceable(
                f"{self.model} reported token usage but no cost, and no prices are "
                "configured for it. Add prices for this model or use one that reports cost."
            )
        return (
            (input_tokens or 0) * self._prices.input_per_mtok
            + (output_tokens or 0) * self._prices.output_per_mtok
        ) // MICRO_PER_USD


class SpendGateState(AgentState):
    """The spend fields added to the agent's persisted state.

    Private, and tracked rather than untracked, so they are written into the
    checkpoint: spend that lived only in memory would restart at zero when a
    session resumed in another process, silently doubling what it may cost.
    """

    run_spend: NotRequired[Annotated[int, PrivateStateAttr]]
    spend_ceiling: NotRequired[Annotated[int, PrivateStateAttr]]


class SpendGate(AgentMiddleware):
    """Refuses to dispatch a model request once a limit is reached.

    `wrap_model_call` rather than `before_model`, deliberately. The retry
    middleware sits outside this one, so each retried attempt passes through here
    and is both gated and priced -- which is what `spend-control` requires when it
    says retries are bounded by the same ceiling as any other spend. A
    `before_model` hook runs once per step, outside the retry loop, and would let
    a retry storm spend past the ceiling unchecked.
    """

    state_schema = SpendGateState  # type: ignore[assignment]

    def __init__(
        self,
        *,
        ledger: SpendLedger,
        ceiling: int,
        run_budget: int,
        warning_threshold: int,
        question_id: str,
        emit: Callable[[Any], None],
        trace: QuestionTrace,
    ) -> None:
        super().__init__()
        self._ledger = ledger
        self._ceiling = ceiling
        self._run_budget = run_budget
        self._warning_threshold = warning_threshold
        self._question_id = question_id
        self._emit = emit
        self._trace = trace
        self._warned = False

    def _tripped(self) -> SpendLimitReached | None:
        # Run budget first: it is the broader stop, so when both are reached the
        # ending should name the one that also prevents the next question.
        if self._ledger.run >= self._run_budget:
            return SpendLimitReached(EndReason.RUN_BUDGET, self._ledger.run, self._run_budget)
        if self._ledger.question >= self._ceiling:
            return SpendLimitReached(EndReason.SPEND_CEILING, self._ledger.question, self._ceiling)
        return None

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        limit = self._tripped()
        if limit is not None:
            self._trace.record(
                "spend.gate_declined",
                reason=limit.reason.value,
                spent=limit.spent,
                limit=limit.limit,
            )
            # Not calling the handler is the whole mechanism: the request is never
            # issued, so the ceiling is not merely observed but enforced.
            raise limit

        response = handler(request)
        charge = self._ledger.add_response(getattr(response, "result", []) or [])
        # Tokens are recorded even when None: an absent field cannot be told apart
        # from a provider that reported nothing, and that distinction is the point.
        self._trace.record(
            "spend.increment",
            model=self._ledger.model,
            increment=charge.micro,
            prompt_tokens=charge.prompt_tokens,
            completion_tokens=charge.completion_tokens,
            question_total=self._ledger.question,
            run_total=self._ledger.run,
        )

        # Warned once per question, and work continues: the threshold is notice,
        # the ceiling is the stop.
        if not self._warned and self._ledger.question > self._warning_threshold:
            self._warned = True
            self._emit(
                SpendWarning(
                    question_id=self._question_id,
                    spent=self._ledger.question,
                    threshold=self._warning_threshold,
                )
            )
        return response

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Persist the run total and the ceiling in force with the checkpoint.

        Written after each model call rather than at the end of the question, so a
        question that ends by raising still leaves its spend recorded.
        """
        return {"run_spend": self._ledger.run, "spend_ceiling": self._ceiling}


# Grounded in measurements against the 14,294-entry corpus on 2026-08-19: a capped
# search payload (50 compact rows) is about 2,100 tokens and a full entry about 180.
PROJECTED_TOOL_RESULT_TOKENS = 2_100
PROJECTED_OUTPUT_TOKENS_PER_CALL = 300
PROJECTED_PROMPT_OVERHEAD_TOKENS = 350


def project_question_cost(config: Config, question: str, calls: int) -> int | None:
    """An upper bound on what a question could cost, before any work is done.

    Deliberately the worst case -- a question that runs all the way to the
    retrieval bound, re-sending the accumulated transcript on every call -- rather
    than a prediction of how much retrieval the model will choose to do. A
    projection that guessed low would drop the flag exactly when it was wanted.
    Returns None when the model has no configured prices, since the projection
    cannot use provider-reported cost: nothing has been dispatched yet.

    This is an estimate and never enforcement; the gate acts on measured spend.
    """
    prices = config.prices_for(config.model)
    if prices is None:
        return None
    overhead = PROJECTED_PROMPT_OVERHEAD_TOKENS + len(question) // 4
    # Each call re-sends everything retrieved so far, so the transcript's cost over
    # a question grows with the square of the number of calls, not linearly.
    input_tokens = calls * overhead + PROJECTED_TOOL_RESULT_TOKENS * calls * (calls - 1) // 2
    output_tokens = calls * PROJECTED_OUTPUT_TOKENS_PER_CALL
    return (
        input_tokens * prices.input_per_mtok + output_tokens * prices.output_per_mtok
    ) // MICRO_PER_USD
