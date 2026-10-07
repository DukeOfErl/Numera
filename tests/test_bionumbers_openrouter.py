"""The OpenRouter adapter: what it sends, and how it reads what comes back.

Driven over an `httpx.MockTransport`, because the point of every case is the request body or the
usage mapping, and neither needs a provider to be checked.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from bionumbers.extraction import ProviderRefused
from bionumbers.openrouter import (
    API_KEY_ENV,
    CHARS_PER_TOKEN,
    DEFAULT_MODEL,
    ModelRefused,
    NoCredential,
    OpenRouterModel,
    strict_schema,
)
from bionumbers.records import Frozen
from bionumbers.spend import OPENROUTER_MODEL, cost


class Inner(Frozen):
    name: str
    note: str = ""


class Answer(Frozen):
    state: str
    items: list[Inner] = []
    pair: tuple[str, str] | None = None


SYSTEM = [
    {"type": "text", "text": "the paper " * 50, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": "the instruction"},
]
MESSAGES = [{"role": "user", "content": "property: doubling time; organism: E. coli"}]


def _server(reply: dict, *, status: int = 200):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        return httpx.Response(status, json=reply)

    return seen, httpx.Client(transport=httpx.MockTransport(handler))


def _reply(content, usage=None):
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": usage
        or {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 700, "cache_write_tokens": 200},
            "cost": 0.0123,
        },
    }


class TestRequest:
    def test_system_blocks_go_through_with_their_cache_marker(self):
        seen, client = _server(_reply(json.dumps({"state": "ok"})))
        OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=99
        )

        body = seen[0]["body"]
        assert body["messages"][0] == {"role": "system", "content": SYSTEM}
        assert body["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["messages"][1:] == MESSAGES
        assert body["max_tokens"] == 99
        assert body["model"] == DEFAULT_MODEL == "openai/gpt-6.1-sol"

    def test_structured_output_is_requested_strictly_and_routed_to_enforcing_providers(self):
        seen, client = _server(_reply(json.dumps({"state": "ok"})))
        OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )

        fmt = seen[0]["body"]["response_format"]
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["name"] == "Answer"
        assert seen[0]["body"]["provider"] == {"require_parameters": True}

    def test_a_pinned_provider_is_the_only_one_allowed_and_no_fallback_is_taken(self):
        """A model served by many providers at many prices: the pin keeps the price the ledger
        projected from. `only`, not `order`, and fallbacks off, so "that provider is down" is a
        failed call rather than a dearer one."""
        seen, client = _server(_reply(json.dumps({"state": "ok"})))
        OpenRouterModel("k", client=client, provider="deepinfra").parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )

        assert seen[0]["body"]["provider"] == {
            "require_parameters": True,
            "only": ["deepinfra"],
            "allow_fallbacks": False,
        }

    @pytest.mark.parametrize("status", [401, 402, 403, 429])
    def test_a_refusal_of_the_account_is_named_so_the_run_can_stop(self, status):
        """A 402 on 2026-09-22 (the OpenRouter balance ran out) ended ten papers FAILED at $0 one
        after another. These statuses are about the account, and the next paper meets the same."""
        seen, client = _server(
            {"error": {"message": "Insufficient credits", "code": status}}, status=status
        )

        with pytest.raises(ProviderRefused, match=f"{status}.*Insufficient credits"):
            OpenRouterModel("k", client=client).parse(
                system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
            )

    def test_a_server_error_is_still_the_paper_s_failure(self):
        """The negative, varying the status: a 500 is one paper's bad luck, not the account's."""
        seen, client = _server({"error": {"message": "overloaded"}}, status=500)

        with pytest.raises(httpx.HTTPStatusError):
            OpenRouterModel("k", client=client).parse(
                system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
            )

    def test_the_cost_is_asked_for_so_the_usage_block_carries_it(self):
        seen, client = _server(_reply(json.dumps({"state": "ok"})))
        OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )

        assert seen[0]["body"]["usage"] == {"include": True}

    def test_the_key_travels_as_a_bearer_token_and_never_in_the_body(self):
        seen, client = _server(_reply(json.dumps({"state": "ok"})))
        OpenRouterModel("sk-or-secret", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )

        assert seen[0]["headers"]["authorization"] == "Bearer sk-or-secret"
        assert "sk-or-secret" not in json.dumps(seen[0]["body"])

    def test_no_key_anywhere_refuses_to_construct(self, monkeypatch):
        monkeypatch.delenv(API_KEY_ENV, raising=False)
        with pytest.raises(NoCredential):
            OpenRouterModel()

    def test_the_ask_apps_key_is_not_a_fallback(self, monkeypatch):
        # The validator's spend must land on its own key, so the ask app's variable alone is
        # a missing credential, not a credential.
        monkeypatch.delenv(API_KEY_ENV, raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "the-ask-apps-key")
        with pytest.raises(NoCredential):
            OpenRouterModel()

    def test_the_key_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        seen, client = _server(_reply(json.dumps({"state": "ok"})))
        OpenRouterModel(client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )
        assert seen[0]["headers"]["authorization"] == "Bearer from-env"


class TestStrictSchema:
    def test_every_object_requires_every_property_and_forbids_others(self):
        schema = strict_schema(Answer)
        objects = [schema, *schema["$defs"].values()]
        for node in objects:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])

    def test_defaults_and_tuple_forms_are_gone(self):
        text = json.dumps(strict_schema(Answer))
        assert '"default"' not in text
        assert "prefixItems" not in text and "minItems" not in text

    def test_the_real_model_still_validates_the_strict_shape(self):
        """Asking for every field does not change what pydantic accepts."""
        Answer.model_validate_json(json.dumps({"state": "x", "items": [], "pair": None}))


class TestResponse:
    def test_content_is_parsed_into_the_output_model(self):
        _, client = _server(_reply(json.dumps({"state": "found", "items": [{"name": "a"}]})))
        parsed = OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )
        assert parsed.parsed_output == Answer(state="found", items=[Inner(name="a")])

    def test_usage_is_mapped_so_that_cached_and_written_tokens_are_not_charged_as_input(self):
        _, client = _server(_reply(json.dumps({"state": "ok"})))
        parsed = OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )
        usage = parsed.usage
        assert (usage.input_tokens, usage.cache_creation_input_tokens) == (100, 200)
        assert (usage.cache_read_input_tokens, usage.output_tokens) == (700, 50)
        assert usage.reported_cost_usd == 0.0123
        spend = cost(OPENROUTER_MODEL, usage)
        assert spend.cache_read_tokens == 700 and spend.calls == 1
        # 100 * 5e-6 + 200 * 6.25e-6 + 700 * 0.5e-6 + 50 * 25e-6
        assert spend.usd == pytest.approx(0.0005 + 0.00125 + 0.00035 + 0.00125)

    def test_a_usage_block_without_cache_details_is_plain_input(self):
        _, client = _server(
            _reply(json.dumps({"state": "ok"}), usage={"prompt_tokens": 40, "completion_tokens": 2})
        )
        usage = (
            OpenRouterModel("k", client=client)
            .parse(system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9)
            .usage
        )
        assert (usage.input_tokens, usage.cache_read_input_tokens) == (40, 0)
        assert usage.reported_cost_usd is None

    def test_an_empty_message_is_a_refusal_not_an_empty_record(self):
        _, client = _server(_reply(""))
        with pytest.raises(ModelRefused):
            OpenRouterModel("k", client=client).parse(
                system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
            )

    def test_content_off_schema_is_a_refusal(self):
        _, client = _server(_reply(json.dumps({"wrong": 1})))
        with pytest.raises(ModelRefused):
            OpenRouterModel("k", client=client).parse(
                system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
            )

    def test_an_http_error_raises_rather_than_returning(self):
        _, client = _server({"error": {"message": "bad gateway"}}, status=502)
        with pytest.raises(httpx.HTTPStatusError):
            OpenRouterModel("k", client=client).parse(
                system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
            )

    def test_multipart_assistant_content_is_read_as_text(self):
        parts = [{"type": "text", "text": '{"state": '}, {"type": "text", "text": '"ok"}'}]
        _, client = _server(_reply(parts))
        parsed = OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )
        assert parsed.parsed_output.state == "ok"


class TestCount:
    def test_the_estimate_errs_high_and_grows_with_the_schema(self):
        model = OpenRouterModel(
            "k", client=httpx.Client(transport=httpx.MockTransport(lambda r: None))
        )
        chars = sum(len(b["text"]) for b in SYSTEM) + len(MESSAGES[0]["content"])
        bare = model.count_tokens(system=SYSTEM, messages=MESSAGES).input_tokens
        assert bare == -(-chars // int(CHARS_PER_TOKEN))
        with_schema = model.count_tokens(
            system=SYSTEM, messages=MESSAGES, output_format=Answer
        ).input_tokens
        assert with_schema > bare


class Plain(BaseModel):
    x: int


def test_a_non_frozen_pydantic_model_gets_additional_properties_false_too():
    assert strict_schema(Plain)["additionalProperties"] is False


def test_a_refused_output_still_carries_what_the_call_cost():
    """The call was billed whatever came back; a ledger told only about successes under-counts
    exactly the calls that went wrong."""
    _, client = _server(_reply(json.dumps({"wrong": 1})))
    with pytest.raises(ModelRefused) as refused:
        OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=9
        )
    assert refused.value.usage is not None
    assert refused.value.usage.cache_read_input_tokens == 700


def test_an_answer_cut_off_at_max_tokens_says_so_rather_than_blaming_the_json():
    """finish_reason 'length' with unparseable content is an unfinished answer, not a wrong one;
    the reason has to send the reader to max_tokens."""
    cut = {
        "choices": [
            {
                "message": {"role": "assistant", "content": '{"state": "found", "items": [{"na'},
                "finish_reason": "length",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8000},
    }
    _, client = _server(cut)
    with pytest.raises(ModelRefused) as refused:
        OpenRouterModel("k", client=client).parse(
            system=SYSTEM, messages=MESSAGES, output_format=Answer, max_tokens=8000
        )
    assert "max_tokens" in str(refused.value) and "8000" in str(refused.value)
    assert refused.value.usage.output_tokens == 8000
