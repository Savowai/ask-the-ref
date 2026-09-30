"""Opt-in checks against the local database; failed replacement must roll back."""

import os

import numpy as np
import psycopg
import pytest
from ask_the_ref import retrieval

pytestmark = pytest.mark.skipif(
    os.getenv("REF_TEST_DATABASE") != "1", reason="Set REF_TEST_DATABASE=1 for local DB checks"
)


def snapshot():
    with retrieval.connect() as conn:
        return conn.execute("SELECT id,section_key,body FROM chunks ORDER BY id").fetchall()


def test_failed_replacement_keeps_existing_corpus(monkeypatch):
    class FakeEmbedding:
        def encode(self, texts):
            return np.ones((len(texts), 384), dtype=np.float32)

    monkeypatch.setattr(retrieval, "Embedder", FakeEmbedding)
    before = snapshot()
    assert before, "Ingest IFAB before this test"
    from ask_the_ref.cli import parse

    chunks, source = parse()
    with pytest.raises(psycopg.errors.UniqueViolation):
        retrieval.ingest(chunks + [chunks[-1]], source)
    assert snapshot() == before


def test_only_current_embedding_space_is_active():
    with retrieval.connect() as conn:
        row = conn.execute(
            "SELECT count(*) n, min(vector_dims(embedding)) dimensions FROM current_chunks"
        ).fetchone()
        assert row["n"] > 300
        assert row["dimensions"] == 384
        assert (
            conn.execute(
                "SELECT count(*) n FROM current_chunks WHERE page_start BETWEEN 166 AND 193"
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) n FROM current_chunks WHERE section_key IN ('law-3/1','law-7/5') AND page_start IS NULL"
            ).fetchone()["n"]
            == 2
        )


def test_real_corpus_generated_flow_with_scripted_provider():
    """Real retrieval/provenance/logging; deliberately NOT a live model quality test."""
    from decimal import Decimal

    from ask_the_ref.answering import AnswerService
    from ask_the_ref.llm import Usage

    class ScriptedProvider:
        model = "scripted-provider-test"
        usages = []

        def structured(self, instruction, payload, schema, stage):
            self.usages.append(Usage(0, 0, 0, Decimal(0)))
            if stage == "understanding":
                data = {
                    "disposition": "rules",
                    "competition": "generic",
                    "scenario": False,
                    "queries": ["Can you be offside directly from a throw-in?"],
                }
            elif stage == "generation":
                evidence = next(e for e in payload["evidence"] if e["section_key"] == "law-11/3")
                data = {
                    "status": "answered",
                    "sections": [
                        {
                            "label": "Answer",
                            "claims": [
                                {
                                    "text": "There is no offside offence when receiving the ball directly from a throw-in.",
                                    "supports": [
                                        {
                                            "evidence_id": evidence["evidence_id"],
                                            "quote": evidence["body"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            else:
                data = {
                    "claims": [{"claim_id": "1.1", "supported": True}],
                    "answers_question": True,
                    "assumptions_supported": True,
                    "judgment_flag_correct": True,
                }
            return schema.model_validate(data)

    result = AnswerService(client=ScriptedProvider()).ask(
        "Can you be offside directly from a throw-in?"
    )
    assert result["status"] == "answered"
    assert result["citations"][0]["section_key"] == "law-11/3"
    assert result["sources"][0]["edition"] == "2026/27"
    assert result["telemetry_logged"]
    with retrieval.connect() as conn:
        row = conn.execute(
            "SELECT * FROM query_runs WHERE trace_id=%s", (result["trace_id"],)
        ).fetchone()
        assert row["outcome"] == "answered"
        assert row["model"] == "scripted-provider-test"
        assert row["cost_usd"] == 0
        assert row["diagnostics"]["provider_calls"] == 3
        assert row["pipeline_version"] == "phase3-v1"
        assert not retrieval.corpus_is_current(
            "wrong-fingerprint", [result["citations"][0]["chunk_id"]]
        )
        assert not retrieval.corpus_is_current(
            result["corpus_fingerprint"], ["00000000-0000-0000-0000-000000000000"]
        )
