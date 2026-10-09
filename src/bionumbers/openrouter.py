"""OpenRouter as the model behind extraction and the second text.

The pipeline's two model-facing modules code against a `Model` protocol -- `parse` and
`count_tokens` -- so which provider answers is an adapter's business. This adapter speaks
OpenRouter's chat-completions API over plain `httpx`, which is already a dependency, rather than
the `openai` SDK, which is not: forty lines of request shaping do not justify a second SDK, and
the shape is the OpenAI one every provider-neutral gateway speaks.

**Why OpenRouter rather than Anthropic directly.** Yoav's standing position (2026-09-18) is that
the project should not be tied to one provider or model family, and the ask app already reaches
models this way. Three things the direct SDK offered are handled as follows:

- *Prompt caching*: OpenRouter passes Anthropic's `cache_control` through on content parts and
  reports reads and writes under `usage.prompt_tokens_details` (`cached_tokens`,
  `cache_write_tokens`; read from openrouter.ai/docs/features/prompt-caching on 2026-09-18). The
  system blocks the pipeline builds carry the marker already; they go through unchanged.
- *Structured output*: `response_format` of type `json_schema` with `strict: true`, and
  `provider.require_parameters` so the request is routed only to an endpoint that enforces it.
  The schema is rewritten by `strict_schema` into the dialect strict mode accepts (every property
  required, no defaults, no tuple forms), which pydantic on our side still validates the same way.
- *Spend projection*: OpenRouter has no token-count endpoint, so `count_tokens` estimates from
  character count at a deliberately low characters-per-token figure, which over-counts and so
  fails in the cheap direction. Actual spend still comes from the usage block the provider
  reports, mapped into the field names `spend.cost` reads.

**What has not been checked live.** No key was available when this was written; the request shape
follows OpenRouter's documentation, and the first live `bionumbers extract` is its validation. If
strict mode rejects the schema, the error names the path; loosen `strict_schema` there, not the
records.
"""

from __future__ import annotations

import copy
import json
import math
import os
from dataclasses import dataclass
from typing import Any

import httpx

from bionumbers.extraction import ProviderRefused

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
#: The validator's own key, distinct from the ask app's `OPENROUTER_API_KEY` by decision
#: (2026-09-22): the prototype's spend is to be readable on its own key. There is no fallback to
#: the ask app's variable -- one would bill the wrong key silently, which is the thing to prevent.
API_KEY_ENV = "BIONUMBERS_OPENROUTER_API_KEY"
#: GPT-6.1 Sol since 2026-10-04 (the harvest seed's model, ADR-0950's comparison): Opus 4.7 at
#: harvest's twenty second-text calls a paper meets the $2 per-paper ceiling before the last claims
#: (code review of 2026-10-07), and Sol does not.
DEFAULT_MODEL = "openai/gpt-6.1-sol"

#: Characters per token assumed when projecting spend. Opus 4.7's tokenizer yields roughly 3.2 to
#: 3.6 characters per token on English prose and fewer on the JSON and rendered tables this
#: pipeline sends. Three is below every figure observed, so the projection errs high: the ceiling
#: refuses a call that would have fitted rather than admitting one that would not.
CHARS_PER_TOKEN = 3.0

#: Sent as OpenRouter's app attribution headers; optional, and not a credential.
APP_HEADERS = {
    "HTTP-Referer": "https://github.com/DukeOfErl/BioNumbers",
    "X-Title": "SciNumbers validator prototype",
}


#: Statuses that are about the account rather than the request: the next paper meets the same
#: answer, so the run stops instead of ending every paper FAILED (seen 2026-09-22 with a 402
#: when the OpenRouter balance ran out under a key whose own limit was not reached).
_ACCOUNT_REFUSALS = frozenset({401, 402, 403, 429})


def _error_of(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return response.text[:200]


class NoCredential(Exception):
    """No OpenRouter key was given and none is in the environment."""


class ModelRefused(Exception):
    """The provider answered without a parseable structured output: an empty message, a
    refusal, or content that is not the schema. The paper ends `FAILED`, never half-read.

    Carries the usage block when there is one: the call was billed whatever came back, and a
    ledger that only hears about successes under-counts exactly the calls that went wrong.
    """

    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


@dataclass(frozen=True, slots=True)
class Usage:
    """The provider's usage block in the field names `spend.cost` reads.

    OpenRouter reports `prompt_tokens` as the whole prompt, cached and written parts included;
    Anthropic's SDK reports the three parts separately. `input_tokens` here is the *uncached,
    unwritten* remainder, so that pricing each part at its own rate does not charge the cached
    article twice.
    """

    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    reported_cost_usd: float | None
    """What OpenRouter itself says the call cost, for reconciling the price table against reality.
    Not what `spend.cost` uses: the table is what the projection was priced from, and a ceiling
    checked in one currency and recorded in another cannot be reasoned about."""


@dataclass(frozen=True, slots=True)
class Parsed:
    parsed_output: Any
    usage: Usage
    raw: dict


@dataclass(frozen=True, slots=True)
class Counted:
    input_tokens: int


def strict_schema(output_format: type) -> dict:
    """A pydantic model's JSON schema in the dialect strict structured output accepts.

    Strict mode wants every property listed in `required`, `additionalProperties: false` on every
    object, and no `default` keys; it has no tuple form, so a `prefixItems` array becomes a plain
    array of its first item type. Pydantic still validates the response against the real model,
    so a field that was optional stays optional on our side -- the model is simply asked to
    always emit it, which for a record whose absence must be explicit is the right ask anyway.
    """
    schema = copy.deepcopy(output_format.model_json_schema())

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            node.pop("default", None)
            if "prefixItems" in node:
                first = node["prefixItems"][0] if node["prefixItems"] else {"type": "string"}
                node.pop("prefixItems")
                node.pop("minItems", None)
                node.pop("maxItems", None)
                node["items"] = first
            for value in list(node.values()):
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


class OpenRouterModel:
    """The `Model` protocol over OpenRouter's chat completions."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        client: httpx.Client | None = None,
        url: str = OPENROUTER_URL,
        timeout: float = 600.0,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        if not key:
            raise NoCredential(f"{API_KEY_ENV} is not set and no key was given")
        self._headers = {"Authorization": f"Bearer {key}", **APP_HEADERS}
        self._model = model
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self._url = url

    @property
    def model(self) -> str:
        return self._model

    def parse(
        self, *, system: list[dict], messages: list[dict], output_format: type, max_tokens: int
    ) -> Parsed:
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            # Anthropic-style text blocks are also OpenAI-style text parts, `cache_control`
            # included, so the system blocks the pipeline builds go through as one system
            # message with multipart content -- the form OpenRouter documents for caching.
            "messages": [{"role": "system", "content": system}, *messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_format.__name__,
                    "strict": True,
                    "schema": strict_schema(output_format),
                },
            },
            "provider": {"require_parameters": True},
            # Without this the usage block carries no `cost`, and `reported_cost_usd` was
            # always None on the first two live runs (code review of 2026-09-21, finding 8).
            "usage": {"include": True},
        }
        response = self._client.post(self._url, headers=self._headers, json=body)
        if response.status_code in _ACCOUNT_REFUSALS:
            raise ProviderRefused(
                f"HTTP {response.status_code} from OpenRouter: {_error_of(response)}"
            )
        response.raise_for_status()
        raw = response.json()
        usage = _usage_of(raw.get("usage") or {})
        choices = raw.get("choices") or []
        content = _text_of(choices[0].get("message", {}).get("content")) if choices else ""
        if not content.strip():
            reason = choices[0].get("finish_reason") if choices else "no choices"
            raise ModelRefused(f"empty structured output (finish_reason={reason!r})", usage)
        finish = choices[0].get("finish_reason")
        try:
            parsed = output_format.model_validate_json(content)
        except ValueError as invalid:
            if finish == "length":
                # The JSON is not wrong, it is unfinished: the provider stopped at max_tokens.
                # Said in the reason, because "Invalid JSON: EOF while parsing" reads as a
                # model fault and sends whoever triages it to the wrong place (the first live
                # run, 2026-09-18, on a correction call at 8,000 output tokens).
                raise ModelRefused(
                    f"output cut off at max_tokens (finish_reason 'length', "
                    f"{usage.output_tokens} output tokens); {output_format.__name__} unparsed",
                    usage,
                ) from None
            raise ModelRefused(
                f"output does not match {output_format.__name__}: {invalid}", usage
            ) from None
        return Parsed(parsed_output=parsed, usage=usage, raw=raw)

    def count_tokens(
        self, *, system: list[dict], messages: list[dict], output_format: type | None = None
    ) -> Counted:
        chars = len(_text_of(system)) + sum(len(_text_of(m.get("content"))) for m in messages)
        if output_format is not None:
            chars += len(json.dumps(strict_schema(output_format)))
        return Counted(input_tokens=math.ceil(chars / CHARS_PER_TOKEN))


def _usage_of(usage: dict) -> Usage:
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    written = int(details.get("cache_write_tokens") or 0)
    prompt = int(usage.get("prompt_tokens") or 0)
    cost = usage.get("cost")
    return Usage(
        input_tokens=max(prompt - cached - written, 0),
        cache_creation_input_tokens=written,
        cache_read_input_tokens=cached,
        output_tokens=int(usage.get("completion_tokens") or 0),
        reported_cost_usd=float(cost) if cost is not None else None,
    )
