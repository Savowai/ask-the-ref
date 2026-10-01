"""Plan, retrieve, generate, validate citations, audit support, then render.

Nothing generated is exposed until both citation validation and the support audit pass.
"""

import logging
import time
from decimal import Decimal
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from . import prompts
from .answer_types import MESSAGES, AnswerAudit, DraftAnswer, QuestionPlan
from .config import Settings
from .evidence import EvidenceError, check_audit, check_draft, render_answer
from .llm import LOCAL_MODEL, LocalClient, ProviderError


class CorpusChanged(Exception):
    pass


def usage_totals(usages):
    def total(field):
        values = [getattr(u, field) for u in usages]
        return None if any(v is None for v in values) else sum(values)

    return {
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "cached_input_tokens": total("cached_input_tokens"),
        "api_cost_usd": total("cost_usd"),
    }


def record_run(result, model):
    from .retrieval import connect

    totals = result["usage"]
    with connect() as conn:
        conn.execute(
            """INSERT INTO query_runs
          (trace_id,competition,retrieval_config,corpus_fingerprint,model,input_tokens,
           output_tokens,cost_usd,latency_ms,refused,step_timings_ms,outcome,pipeline_version,diagnostics)
          VALUES (%s,%s,'hybrid-rerank+rewrite',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                result["trace_id"],
                result["competition"],
                result["corpus_fingerprint"] or "not-retrieved",
                model,
                totals["input_tokens"],
                totals["output_tokens"],
                totals["api_cost_usd"],
                result["latency_ms"],
                result["status"] not in ("answered", "judgment"),
                Jsonb(result["timings_ms"]),
                result["status"],
                prompts.VERSION,
                Jsonb(
                    {
                        "provider_calls": result["provider_calls"],
                        "cached_input_tokens": totals["cached_input_tokens"],
                        "citation_count": len(result["citations"]),
                    }
                ),
            ),
        )


class AnswerService:
    def __init__(
        self,
        settings=None,
        *,
        client=None,
        evidence_loader=None,
        freshness_check=None,
        logger=record_run,
    ):
        self.settings = settings or Settings()
        self.client = client
        self.evidence_loader = evidence_loader
        self.freshness_check = freshness_check
        self.logger = logger
        self.search = None

    def _evidence(self, queries):
        if self.evidence_loader:
            return self.evidence_loader(queries)
        from .retrieval import Search, collect_evidence

        if self.search is None:
            self.search = Search()
        return collect_evidence(self.search, queries)

    def _fresh(self, fingerprint, ids):
        if self.freshness_check:
            return self.freshness_check(fingerprint, ids)
        from .retrieval import corpus_is_current

        return corpus_is_current(fingerprint, ids)

    def ask(self, question):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("Question must contain 1–2000 characters")
        start = time.perf_counter()
        result = {
            "trace_id": str(uuid4()),
            "status": "configuration_error",
            "competition": "generic",
            "markdown": "",
            "sections": [],
            "citations": [],
            "sources": [],
            "corpus_fingerprint": None,
            "timings_ms": {},
            "provider_calls": 0,
            "scope_note": "Currently covers IFAB Laws only; competition-specific regulations are not yet loaded.",
        }
        client = self.client
        usage_start = len(client.usages) if client else 0
        model = LOCAL_MODEL
        stage = "configuration"
        try:
            if client is None:
                client = LocalClient(self.settings)
            model = client.model

            def call(instructions, payload, schema, name):
                tick = time.perf_counter()
                try:
                    return client.structured(instructions, payload, schema, name)
                finally:
                    result["timings_ms"][name] = round((time.perf_counter() - tick) * 1000)
                    result["provider_calls"] += 1

            stage = "planning"
            plan = call(prompts.PLAN, {"question": question}, QuestionPlan, "understanding")
            result["competition"] = plan.competition
            if plan.disposition != "rules":
                result["status"] = plan.disposition
            elif plan.competition != "generic":
                result["status"] = "scope_unavailable"
            else:
                stage = "retrieval"
                if any(not q.strip() or len(q) > 200 for q in plan.queries):
                    raise EvidenceError("Invalid retrieval query")
                tick = time.perf_counter()
                bundle = self._evidence(plan.queries)
                result["timings_ms"]["retrieval"] = round((time.perf_counter() - tick) * 1000)
                result["corpus_fingerprint"] = bundle.corpus_fingerprint
                result["sources"] = bundle.sources
                if not bundle.evidence:
                    result["status"] = "insufficient_evidence"
                else:
                    stage = "generation"
                    payload = {
                        "question": question,
                        "scenario": plan.scenario,
                        "evidence": bundle.evidence,
                    }
                    draft = call(prompts.GENERATE, payload, DraftAnswer, "generation")
                    stage = "validation"
                    claims = check_draft(draft, bundle.evidence, plan.scenario)
                    if draft.status not in ("answered", "judgment"):
                        result["status"] = draft.status
                    else:
                        audit = call(
                            prompts.AUDIT,
                            {**payload, "status": draft.status, "claims": claims},
                            AnswerAudit,
                            "support_audit",
                        )
                        check_audit(audit, claims)
                        stage = "freshness"
                        if not self._fresh(
                            bundle.corpus_fingerprint, [e["chunk_id"] for e in bundle.evidence]
                        ):
                            raise CorpusChanged()
                        result.update(render_answer(draft, claims, bundle.evidence))
                        result["status"] = draft.status
        except CorpusChanged:
            result["status"] = "corpus_changed"
        except EvidenceError as exc:
            result["status"] = (
                "corpus_changed" if str(exc) == "corpus_changed" else "validation_failed"
            )
        except ProviderError:
            result["status"] = "provider_error"
        except (psycopg.Error, OSError):
            result["status"] = "retrieval_error"
        except ValueError:
            result["status"] = (
                "configuration_error" if stage == "configuration" else "validation_failed"
            )
        if result["status"] not in ("answered", "judgment"):
            result["markdown"] = MESSAGES[result["status"]]
            result["citations"] = []
            result["sections"] = []
        result["usage"] = usage_totals(client.usages[usage_start:] if client else [])
        result["latency_ms"] = round((time.perf_counter() - start) * 1000)
        result["model"] = model
        result["pipeline_version"] = prompts.VERSION
        try:
            self.logger(result, model)
            result["telemetry_logged"] = True
        except (psycopg.Error, OSError):
            result["telemetry_logged"] = False
            logging.getLogger(__name__).warning(
                "Answer telemetry unavailable; trace_id=%s", result["trace_id"]
            )
        cost = result["usage"]["api_cost_usd"]
        if isinstance(cost, Decimal):
            result["usage"]["api_cost_usd"] = float(cost)
        return result
