"""Small Responses API adapter; bounded calls, strict JSON, no secret/error-body logging."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings

T = TypeVar("T", bound=BaseModel)
# Standard text rates per million tokens, checked 2026-09-29 against the official model page.
# Unknown model overrides are logged with NULL cost, never guessed to be free.
PRICES = {"gpt-4.1-mini-2025-04-14": (Decimal("0.40"), Decimal("0.10"), Decimal("1.60"))}
PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1-mini"


class ProviderError(Exception):
    """Intentionally contains a safe code, not a provider response/request body."""


@dataclass
class Usage:
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None


def parse_usage(raw, model):
    if not isinstance(raw, dict):
        return Usage(None, None, None, None)
    i, o = raw.get("input_tokens"), raw.get("output_tokens")
    details = raw.get("input_tokens_details") or {}
    if not isinstance(details, dict):
        return Usage(None, None, None, None)
    cached = details.get("cached_tokens", 0)
    if any(type(n) is not int or n < 0 for n in [i, o, cached]) or cached > i:
        return Usage(None, None, None, None)
    price = PRICES.get(model)
    cost = (
        ((i - cached) * price[0] + cached * price[1] + o * price[2]) / 1_000_000 if price else None
    )
    return Usage(i, cached, o, cost)


class ResponsesClient:
    def __init__(self, settings: Settings, transport=None):
        if not settings.openai_api_key or not settings.openai_api_key.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY is not configured")
        self.settings = settings
        self.model = settings.llm_model.strip() or "gpt-4.1-mini-2025-04-14"
        self.transport = transport
        self.usages: list[Usage] = []

    def structured(self, instruction: str, payload: dict, schema: type[T], stage: str) -> T:
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.settings.llm_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": "Bearer " + self.settings.openai_api_key.get_secret_value()
                    },
                    json={
                        "model": self.model,
                        "instructions": instruction,
                        "input": json.dumps(payload, ensure_ascii=False, default=str),
                        "store": False,
                        "max_output_tokens": self.settings.llm_max_output_tokens,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": stage,
                                "strict": True,
                                "schema": schema.model_json_schema(),
                            }
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            self.usages.append(Usage(None, None, None, None))
            raise ProviderError("request_failed") from None
        if not isinstance(data, dict):
            self.usages.append(Usage(None, None, None, None))
            raise ProviderError("invalid_response")
        self.usages.append(parse_usage(data.get("usage"), data.get("model", self.model)))
        if data.get("status") != "completed":
            raise ProviderError("incomplete_response")
        try:
            blocks = [
                b
                for item in data.get("output", [])
                if item.get("type") == "message"
                for b in item.get("content", [])
            ]
            if any(b.get("type") == "refusal" for b in blocks):
                raise ProviderError("provider_refusal")
            content = "".join(b.get("text", "") for b in blocks if b.get("type") == "output_text")
            return schema.model_validate_json(content)
        except (ValidationError, TypeError, AttributeError):
            raise ProviderError("invalid_structured_output") from None
