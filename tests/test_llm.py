"""The answer adapter is local-only, credential-free and refuses truncated output."""

import json
from decimal import Decimal

import httpx
import pytest
from ask_the_ref.answer_types import QuestionPlan
from ask_the_ref.config import ROOT, Settings
from ask_the_ref.llm import LOCAL_MODEL, LOCAL_URL, LocalClient, ProviderError

PLAN = {
    "disposition": "off_topic",
    "competition": "generic",
    "scenario": False,
    "queries": ["weather"],
}


def body():
    return {
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 1000,
        "eval_count": 100,
        "message": {"role": "assistant", "content": json.dumps(PLAN)},
    }


def provider(handler):
    digest = json.loads((ROOT / "local-model.lock.json").read_text())["digest"]

    def route(request):
        assert str(request.url).startswith(LOCAL_URL + "/api/")
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": LOCAL_MODEL, "digest": digest}]})
        return handler(request)

    return LocalClient(Settings(), transport=httpx.MockTransport(route))


def test_local_wire_contract_never_sends_keys_or_uses_cloud(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unused-secret")
    monkeypatch.setenv("HTTP_PROXY", "http://remote.invalid:9999")

    def handle(request):
        assert str(request.url) == LOCAL_URL + "/api/chat"
        assert "authorization" not in request.headers
        request_body = json.loads(request.content)
        assert request_body["model"] == LOCAL_MODEL
        assert request_body["format"]["additionalProperties"] is False
        assert request_body["stream"] is False
        assert request_body["options"]["num_ctx"] == 32768
        assert "unused-secret" not in request.content.decode()
        return httpx.Response(200, json=body())

    client = provider(handle)
    assert (
        client.structured("Classify", {}, QuestionPlan, "understanding").disposition == "off_topic"
    )
    assert client.usages[0].cost_usd == Decimal(0)
    assert client.usages[0].input_tokens == 1000


@pytest.mark.parametrize(
    "case", ["timeout", "http_error", "redirect", "incomplete", "bad_json", "bad_shape"]
)
def test_local_errors_fail_closed(case):
    def handle(request):
        if case == "timeout":
            raise httpx.ReadTimeout("private", request=request)
        if case == "http_error":
            return httpx.Response(500, text="private")
        if case == "redirect":
            return httpx.Response(302, headers={"Location": "https://remote.invalid"})
        raw = body()
        if case == "incomplete":
            raw["done_reason"] = "length"
        if case == "bad_json":
            raw["message"]["content"] = "{"
        if case == "bad_shape":
            raw["message"] = None
        return httpx.Response(200, json=raw)

    client = provider(handle)
    with pytest.raises(ProviderError) as exc:
        client.structured("Classify", {}, QuestionPlan, "understanding")
    assert "private" not in str(exc.value)
    assert client.usages[0].cost_usd == 0


def test_oversized_context_rejected_before_request():
    def unexpected(request):
        pytest.fail("Oversized prompt must never be silently truncated by the server")

    client = provider(unexpected)
    with pytest.raises(ProviderError, match="context_budget"):
        client.structured("Classify", {"body": "x" * 40000}, QuestionPlan, "understanding")


def test_changed_model_digest_refused():
    client = LocalClient(
        Settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"models": [{"name": LOCAL_MODEL, "digest": "wrong"}]}
            )
        ),
    )
    with pytest.raises(ProviderError, match="missing_or_changed"):
        client.structured("Classify", {}, QuestionPlan, "understanding")
