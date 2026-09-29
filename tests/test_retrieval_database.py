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
