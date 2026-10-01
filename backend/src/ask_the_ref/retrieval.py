"""Transactional current-corpus replacement and independently selectable retrieval stages."""

import hashlib
import json
import re
import time
from datetime import UTC, date, datetime
from uuid import uuid4

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import ROOT, Settings
from .models import Embedder, Reranker, model_id


def connect():
    connection = psycopg.connect(Settings().database_url.get_secret_value(), row_factory=dict_row)
    register_vector(connection)
    connection.commit()
    return connection


def migrate():
    with psycopg.connect(Settings().database_url.get_secret_value(), autocommit=True) as conn:
        conn.execute((ROOT / "db/migrations/002_local_retrieval.sql").read_text())
        conn.execute((ROOT / "db/migrations/003_answer_logging.sql").read_text())


def definition_links(chunks):
    links = []
    for definition in chunks:
        if definition.kind != "definition" or definition.parent_section_key is None:
            continue
        term = re.sub(r"\s*\([^)]*\)", "", definition.section_title).lower()
        if len(term) < 4:
            continue
        pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I)
        for target in chunks:
            if target.kind != "definition" and pattern.search(target.body):
                links.append((definition.section_key, target.section_key, "defines"))
    return links


def ingest(chunks, source):
    source.assert_current(date.today())
    # Activation must not bypass the configured authoritative replacements.
    from .corrections import fingerprint

    by_key = {chunk.section_key: chunk for chunk in chunks}
    for correction in source.corrections:
        target = by_key.get(correction.section_key)
        if target is None or target.section_url != correction.url + "#" + correction.anchor:
            raise ValueError("Required official correction is missing")
        if fingerprint(target.body.split("\n")) != correction.sha256:
            raise ValueError("Required official correction does not match its content hash")
    texts = [" > ".join(c.heading_path) + "\n" + c.body for c in chunks]
    vectors = Embedder().encode(texts)
    fingerprint = hashlib.sha256(
        json.dumps([c.record() for c in chunks], sort_keys=True).encode()
    ).hexdigest()
    ids = {c.section_key: uuid4() for c in chunks}
    links = definition_links(chunks)
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (source.id,))
        source.assert_current(date.today())
        conn.execute("DELETE FROM rulebooks WHERE id=%s", (source.id,))
        conn.execute(
            """INSERT INTO rulebooks
          (id,title,authority,competition_scope,edition,effective_from,effective_until,
           source_url,discovery_url,sha256,last_checked_at,ingested_at,status,embedding_model,content_fingerprint)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),'ready',%s,%s)""",
            (
                source.id,
                source.title,
                source.authority,
                source.competition_scope,
                source.edition,
                source.effective_from,
                source.effective_until,
                source.source_url,
                source.discovery_url,
                source.sha256,
                datetime.combine(source.verified_on, datetime.min.time(), UTC),
                model_id("embedding"),
                fingerprint,
            ),
        )
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO chunks
              (id,rulebook_id,edition,section_key,parent_section_key,kind,law_article,
               section_title,heading_path,body,blocks,page_start,page_end,printed_page_labels,
               source_url,section_url,embedding)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    (
                        ids[c.section_key],
                        source.id,
                        source.edition,
                        c.section_key,
                        c.parent_section_key,
                        c.kind,
                        c.law_article,
                        c.section_title,
                        c.heading_path,
                        c.body,
                        Jsonb(c.blocks),
                        min(c.pages) if c.pages else None,
                        max(c.pages) if c.pages else None,
                        [str(p) for p in c.pages],
                        c.source_url,
                        c.section_url,
                        vectors[i],
                    )
                    for i, c in enumerate(chunks)
                ],
            )
            cursor.executemany(
                "INSERT INTO chunk_links(from_chunk_id,to_chunk_id,relation) VALUES (%s,%s,%s)",
                [(ids[a], ids[b], r) for a, b, r in links],
            )
    return {"chunks": len(chunks), "definition_links": len(links), "fingerprint": fingerprint}


def rrf(*rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
    return sorted(scores, key=lambda key: (-scores[key], str(key))), scores


FIELDS = """id,section_key,parent_section_key,heading_path,body,section_url,source_url,
            page_start,page_end,edition,rulebook,rulebook_id,kind,blocks"""
ELIGIBLE = "EXISTS (SELECT 1 FROM jsonb_array_elements(blocks) b WHERE b->>'type' IN ('paragraph','list_item','table'))"


class Search:
    def __init__(self, rerank=True):
        self.embedder = Embedder()
        self.reranker = Reranker() if rerank else None

    def ask(self, question, mode="hybrid-rerank", limit=5, *, log=True):
        if mode not in ("vector", "hybrid", "hybrid-rerank") or not 1 <= limit <= 20:
            raise ValueError("Invalid retrieval configuration")
        if not question.strip() or len(question) > 2000:
            raise ValueError("Question must contain 1–2000 characters")
        if len(self.embedder.model.tokenizer.encode(question, add_special_tokens=False)) > 128:
            raise ValueError("Phase 2 CLI accepts questions up to 128 model tokens")
        started = time.perf_counter()
        timings = {}
        vector = self.embedder.encode([question])[0]
        timings["embedding"] = round((time.perf_counter() - started) * 1000)
        with connect() as conn:
            # Keep all stages on one snapshot if an ingestion commits during the request.
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            books = conn.execute("""SELECT DISTINCT r.id,r.edition,r.last_checked_at,r.embedding_model,r.content_fingerprint
                FROM rulebooks r JOIN current_chunks c ON c.rulebook_id=r.id""").fetchall()
            if not books:
                raise ValueError("No current rules ingested; run ref ingest first")
            if any(b["embedding_model"] != model_id("embedding") for b in books):
                raise ValueError("Corpus model mismatch: re-ingest before querying")
            tick = time.perf_counter()
            vector_rows = conn.execute(
                f"""SELECT {FIELDS},embedding <=> %s AS distance
              FROM current_chunks WHERE {ELIGIBLE} AND embedding IS NOT NULL
              ORDER BY embedding <=> %s,id LIMIT 30""",
                (vector, vector),
            ).fetchall()
            rows = {r["id"]: r for r in vector_rows}
            ranks = [[r["id"] for r in vector_rows]]
            if mode != "vector":
                terms = " OR ".join(re.findall(r"[\w]+", question))
                lexical = conn.execute(
                    f"""SELECT {FIELDS} FROM current_chunks,
                  websearch_to_tsquery('english',%s) q WHERE search_document @@ q AND {ELIGIBLE}
                  ORDER BY ts_rank_cd(search_document,q) DESC,id LIMIT 30""",
                    (terms,),
                ).fetchall()
                rows.update({r["id"]: r for r in lexical})
                ranks.append([r["id"] for r in lexical])
            ordered, scores = rrf(*ranks)
            timings["database_and_fusion"] = round((time.perf_counter() - tick) * 1000)
            candidates = [rows[key] for key in ordered[:30]]
            for row in candidates:
                row["rrf_score"] = scores[row["id"]]
            if mode == "hybrid-rerank":
                if self.reranker is None:
                    raise ValueError("Reranker not loaded")
                tick = time.perf_counter()
                reranked = self.reranker.scores(
                    question, [" > ".join(r["heading_path"]) + "\n" + r["body"] for r in candidates]
                )
                for row, score in zip(candidates, reranked):
                    row["rerank_score"] = score
                candidates.sort(key=lambda r: -r["rerank_score"])
                timings["reranking"] = round((time.perf_counter() - tick) * 1000)
            results = candidates[:limit]
            # Related definitions are separate evidence, not additional ranked search hits.
            related = (
                conn.execute(
                    f"""SELECT DISTINCT {", ".join("c." + f.strip() for f in FIELDS.split(","))}
                FROM current_chunks c JOIN chunk_links l ON l.from_chunk_id=c.id
                WHERE l.to_chunk_id=ANY(%s) AND l.relation='defines' ORDER BY c.section_key""",
                    ([r["id"] for r in results],),
                ).fetchall()
                if results
                else []
            )
            elapsed = round((time.perf_counter() - started) * 1000)
            corpus = hashlib.sha256(
                "|".join(sorted(b["content_fingerprint"] for b in books)).encode()
            ).hexdigest()
            if log:
                conn.execute(
                    """INSERT INTO query_runs(competition,retrieval_config,corpus_fingerprint,
                  model,cost_usd,latency_ms,refused,step_timings_ms) VALUES ('generic',%s,%s,%s,0,%s,false,%s)""",
                    (
                        mode,
                        corpus,
                        model_id("embedding")
                        + (" + " + model_id("reranker") if mode == "hybrid-rerank" else ""),
                        elapsed,
                        Jsonb(timings),
                    ),
                )
        return {
            "corpus_fingerprint": corpus,
            "sources": [
                {
                    "id": b["id"],
                    "edition": b["edition"],
                    "last_checked_at": b["last_checked_at"].isoformat(),
                }
                for b in books
            ],
            "question": question,
            "mode": mode,
            "results": results,
            "definitions": related,
            "latency_ms": elapsed,
            "timings_ms": timings,
            "api_cost_usd": 0,
            "notice": "Retrieved evidence only. Use ref ask for a validated generated answer.",
        }


def corpus_is_current(fingerprint, chunk_ids=()):
    with connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        books = conn.execute("""SELECT DISTINCT r.id,r.content_fingerprint FROM rulebooks r
            JOIN current_chunks c ON c.rulebook_id=r.id""").fetchall()
        current = hashlib.sha256(
            "|".join(sorted(b["content_fingerprint"] for b in books)).encode()
        ).hexdigest()
        count = conn.execute(
            "SELECT count(*) n FROM current_chunks WHERE id=ANY(%s::uuid[])", (list(chunk_ids),)
        ).fetchone()["n"]
        return fingerprint == current and count == len(set(chunk_ids))


def expand_ancestors(rows):
    """Include full ancestor sections so subheadings retain conditions stated above them."""
    output = []
    seen = {(r["rulebook_id"], r["section_key"]) for r in rows}
    frontier = rows
    with connect() as conn:
        for _ in range(5):
            following = []
            for row in frontier:
                parent = row.get("parent_section_key")
                key = (row["rulebook_id"], parent)
                if not parent or key in seen:
                    continue
                seen.add(key)
                found = conn.execute(
                    f"""SELECT {FIELDS} FROM current_chunks
                    WHERE rulebook_id=%s AND section_key=%s""",
                    key,
                ).fetchone()
                if found:
                    following.append(found)
            output.extend(following)
            frontier = following
    return output


def collect_evidence(search, queries):
    from .evidence import EvidenceBundle, EvidenceError, package_evidence

    responses = [search.ask(q, limit=5, log=False) for q in dict.fromkeys(queries)]
    fingerprints = {r["corpus_fingerprint"] for r in responses}
    if len(fingerprints) != 1:
        raise EvidenceError("corpus_changed")
    # Interleave subquestion results so offence, sanction and restart get equal room.
    rows = []
    for rank in range(5):
        for response in responses:
            if rank < len(response["results"]):
                rows.append(response["results"][rank])
    rows += expand_ancestors(rows)
    evidence = package_evidence(rows, character_budget=12000)
    fingerprint = responses[0]["corpus_fingerprint"]
    if not corpus_is_current(fingerprint, [e["chunk_id"] for e in evidence]):
        raise EvidenceError("corpus_changed")
    return EvidenceBundle(
        evidence,
        fingerprint,
        responses[0]["sources"],
        {"retrieval": sum(r["latency_ms"] for r in responses)},
    )
