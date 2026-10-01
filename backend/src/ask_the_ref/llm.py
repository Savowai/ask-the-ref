"""Local-only Ollama adapter. No credentials, paid endpoint or cloud fallback."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import ROOT, Settings

T = TypeVar("T", bound=BaseModel)
LOCAL_MODEL = "qwen2.5:7b"
LOCAL_URL = "http://127.0.0.1:11436"


class ProviderError(Exception):
    """Safe diagnostic code, never raw request or provider output."""


@dataclass
class Usage:
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None


class LocalClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.model = LOCAL_MODEL
        self.transport = transport
        self.usages: list[Usage] = []
        self.lock = json.loads((ROOT / "local-model.lock.json").read_text())
        self.verified = False

    def structured(self, instruction: str, payload: dict, schema: type[T], stage: str) -> T:
        schema_json = schema.model_json_schema()
        system = instruction + "\nReturn JSON matching this schema:\n" + json.dumps(schema_json)
        user = json.dumps(payload, ensure_ascii=False, default=str)
        # Qwen uses byte-level BPE. UTF-8 byte count is a conservative token upper bound.
        # Reject oversized evidence instead of letting the runtime drop earlier instructions.
        if len((system + user).encode()) + self.settings.llm_max_output_tokens + 512 > 32768:
            raise ProviderError("context_budget_exceeded")
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.settings.llm_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                if not self.verified:
                    tags = client.get(LOCAL_URL + "/api/tags")
                    tags.raise_for_status()
                    matching = [
                        m for m in tags.json().get("models", []) if m.get("name") == LOCAL_MODEL
                    ]
                    if len(matching) != 1 or matching[0].get("digest") != self.lock["digest"]:
                        raise ProviderError("local_model_missing_or_changed")
                    self.verified = True
                response = client.post(
                    LOCAL_URL + "/api/chat",
                    json={
                        "model": LOCAL_MODEL,
                        "stream": False,
                        "format": schema_json,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "options": {
                            "temperature": 0,
                            "seed": 42,
                            "num_ctx": 32768,
                            "num_gpu": self.settings.llm_num_gpu,
                            "num_predict": self.settings.llm_max_output_tokens,
                        },
                        "keep_alive": "5m",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            self.usages.append(Usage(None, 0, None, Decimal(0)))
            raise ProviderError("local_service_unavailable") from None
        if not isinstance(data, dict):
            self.usages.append(Usage(None, 0, None, Decimal(0)))
            raise ProviderError("invalid_local_response")

        def tokens(k):
            return data[k] if type(data.get(k)) is int and data[k] >= 0 else None

        self.usages.append(Usage(tokens("prompt_eval_count"), 0, tokens("eval_count"), Decimal(0)))
        if data.get("done") is not True or data.get("done_reason") != "stop":
            raise ProviderError("incomplete_local_response")
        try:
            return schema.model_validate_json(data["message"]["content"])
        except (ValidationError, KeyError, TypeError):
            raise ProviderError("invalid_structured_output") from None
