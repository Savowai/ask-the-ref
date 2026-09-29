"""Strict, data-driven source configuration. Never infer effective dates from titles."""

import os
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(os.environ.get("ASK_THE_REF_ROOT", Path(__file__).resolve().parents[3]))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: SecretStr = SecretStr(
        "postgresql://ref:ref_local_only@localhost:5432/ask_the_ref"
    )
    openai_api_key: SecretStr | None = None
    llm_model: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=384, ge=384, le=384)
    reranker_model: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "ask-the-ref"


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_key: str
    url: str
    anchor: str = Field(pattern=r"^[a-z0-9-]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_on: date
    notes: str


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    title: str
    authority: str = Field(pattern=r"^[A-Z][A-Z0-9_-]*$")
    competition_scope: list[str] = Field(min_length=1)
    edition: str
    discovery_url: str
    source_url: str
    download_url: str | None = None
    allowed_hosts: list[str] = Field(min_length=1)
    effective_from: date | None = None
    effective_until: date | None = None
    verified_on: date
    verification: Literal["current", "needs_review"]
    ingest_phase: int = Field(ge=2, le=5)
    coverage: list[str] = Field(min_length=1)
    corrections: list[Correction] = Field(default_factory=list)
    notes: str = ""
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_source(self):
        for url in [self.source_url, self.discovery_url, self.download_url] + [c.url for c in self.corrections]:
            if url is not None:
                parsed = urlparse(url)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname not in self.allowed_hosts
                    or parsed.username
                    or parsed.password
                    or parsed.port not in (None, 443)
                ):
                    raise ValueError("Source URLs must use HTTPS on an explicitly allowed host")
        if self.effective_until and self.effective_from:
            if self.effective_until <= self.effective_from:
                raise ValueError("effective_until is exclusive and must follow effective_from")
        return self

    def assert_current(self, today: date) -> None:
        if self.verification != "current":
            raise ValueError(f"{self.id}: current edition needs review")
        if not self.effective_from or self.effective_from > today:
            raise ValueError(f"{self.id}: effective date unverified or in the future")
        if self.effective_until and today >= self.effective_until:
            raise ValueError(f"{self.id}: edition has expired")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    checked_on: date
    sources: list[Source]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source ids")
        return self


def load_manifest(path: Path = ROOT / "sources.yaml") -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text()))
