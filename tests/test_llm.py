import json
from decimal import Decimal

import httpx
import pytest
from ask_the_ref.answer_types import QuestionPlan
from ask_the_ref.config import Settings
from ask_the_ref.llm import ProviderError, ResponsesClient, parse_usage

PLAN = {
    "disposition": "off_topic",
    "competition": "generic",
    "scenario": False,
    "queries": ["weather"],
}


def response_body():
    return {
        "status": "completed",
        "model": "gpt-4.1-mini-2025-04-14",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 200},
        },
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(PLAN)}]}
        ],
    }


def client(handler):
    return ResponsesClient(
        Settings(openai_api_key="test-only-secret", llm_model="gpt-4.1-mini-2025-04-14"),
        transport=httpx.MockTransport(handler),
    )


def test_wire_contract_uses_responses_strict_schema_and_store_false():
    def handle(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert "tools" not in body
        assert request.headers["authorization"] == "Bearer test-only-secret"
        return httpx.Response(200, json=response_body())

    provider = client(handle)
    plan = provider.structured("Classify", {"question": "weather"}, QuestionPlan, "understanding")
    assert plan.disposition == "off_topic"
    assert provider.usages[0].cost_usd == Decimal("0.0005")


@pytest.mark.parametrize(
    "case", ["timeout", "http_error", "redirect", "refusal", "incomplete", "bad_json", "bad_shape"]
)
def test_provider_fails_closed_and_keeps_billing_uncertainty(case):
    def handle(request):
        if case == "timeout":
            raise httpx.ReadTimeout("secret", request=request)
        if case == "http_error":
            return httpx.Response(401, text="secret")
        if case == "redirect":
            return httpx.Response(302, headers={"Location": "https://evil.example/"})
        raw = response_body()
        if case == "refusal":
            raw["output"][0]["content"] = [{"type": "refusal", "refusal": "secret"}]
        if case == "incomplete":
            raw["status"] = "incomplete"
        if case == "bad_json":
            raw["output"][0]["content"][0]["text"] = "{"
        if case == "bad_shape":
            raw["output"] = [None]
        return httpx.Response(200, json=raw)

    provider = client(handle)
    with pytest.raises(ProviderError) as error:
        provider.structured("Classify", {}, QuestionPlan, "understanding")
    assert "secret" not in str(error.value)
    assert len(provider.usages) == 1
    if case in ("timeout", "http_error", "redirect"):
        assert provider.usages[0].cost_usd is None


def test_unknown_pricing_or_tokens_never_become_zero_cost():
    assert parse_usage({"input_tokens": 1, "output_tokens": 1}, "unpriced-model").cost_usd is None
    assert parse_usage(None, "gpt-4.1-mini-2025-04-14").cost_usd is None
    assert (
        parse_usage(
            {"input_tokens": 1, "output_tokens": 1, "input_tokens_details": {"cached_tokens": 2}},
            "gpt-4.1-mini-2025-04-14",
        ).cost_usd
        is None
    )
