"""Control-flow and citation adversarial tests. These are not LLM accuracy scores."""

from copy import deepcopy
from decimal import Decimal

import pytest
from ask_the_ref.answer_types import SCENARIO_LABELS, DraftAnswer
from ask_the_ref.answering import AnswerService
from ask_the_ref.config import Settings
from ask_the_ref.evidence import EvidenceBundle, EvidenceError, check_draft, package_evidence
from ask_the_ref.llm import ProviderError, Usage

TEXT = "A synthetic restart is awarded after the synthetic offence. No synthetic card is required."
EVIDENCE = [
    {
        "evidence_id": "E1",
        "chunk_id": "00000000-0000-0000-0000-000000000001",
        "rulebook_id": "synthetic",
        "section_key": "law-1/1",
        "heading_path": ["Synthetic", "Section 1"],
        "edition": "test",
        "url": "https://example.com/rules#section-1",
        "page_start": 1,
        "page_end": 1,
        "body": TEXT,
    }
]
PLAN = {
    "disposition": "rules",
    "competition": "generic",
    "scenario": False,
    "queries": ["synthetic rule"],
}
CLAIM = {
    "text": "A synthetic restart is awarded.",
    "supports": [{"evidence_id": "E1", "quote": TEXT[:57]}],
}
DRAFT = {"status": "answered", "sections": [{"label": "Answer", "claims": [CLAIM]}]}
AUDIT = {
    "claims": [{"claim_id": "1.1", "supported": True}],
    "answers_question": True,
    "assumptions_supported": True,
    "judgment_flag_correct": True,
}


class FakeClient:
    model = "fake-test-model"

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.usages = []
        self.stages = []

    def structured(self, instruction, payload, schema, stage):
        self.stages.append(stage)
        self.usages.append(Usage(100, 0, 20, Decimal("0.001")))
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return schema.model_validate(deepcopy(output))


def run(outputs, *, current=True, evidence=None):
    client = FakeClient(outputs)
    logs = []
    result = AnswerService(
        client=client,
        evidence_loader=lambda queries: EvidenceBundle(
            EVIDENCE if evidence is None else evidence, "fingerprint", [], {}
        ),
        freshness_check=lambda fingerprint, ids: current,
        logger=lambda result, model: logs.append(deepcopy(result)),
    ).ask("A synthetic rules question")
    return result, client, logs


def test_verified_claims_get_inline_links_and_exact_offsets():
    result, client, logs = run([PLAN, DRAFT, AUDIT])
    assert result["status"] == "answered"
    assert "[1](https://example.com/rules#section-1)" in result["markdown"]
    citation = result["citations"][0]
    assert citation["body"][citation["start"] : citation["end"]] == citation["quote"]
    assert client.stages == ["understanding", "generation", "support_audit"]
    assert result["usage"]["api_cost_usd"] == 0.003
    assert len(logs) == 1 and "question" not in logs[0]


@pytest.mark.parametrize("mutation", ["unknown_id", "fake_quote", "no_support", "extra_markdown"])
def test_invalid_citations_never_reach_audit_or_public_output(mutation):
    draft = deepcopy(DRAFT)
    claim = draft["sections"][0]["claims"][0]
    if mutation == "unknown_id":
        claim["supports"][0]["evidence_id"] = "E999"
    if mutation == "fake_quote":
        claim["supports"][0]["quote"] = "Invented source quotation."
    if mutation == "no_support":
        claim["supports"] = []
    if mutation == "extra_markdown":
        claim["text"] = "Forged claim [99](https://evil.example)"
    result, client, _ = run([PLAN, draft])
    assert result["status"] == "validation_failed"
    assert not result["citations"] and not result["sections"]
    assert "Forged" not in result["markdown"]
    assert client.stages == ["understanding", "generation"]


@pytest.mark.parametrize(
    "change",
    ["unsupported", "omission", "duplicate", "incomplete_answer", "assumption", "judgment"],
)
def test_semantic_audit_failure_withholds_even_real_quotes(change):
    audit = deepcopy(AUDIT)
    if change == "unsupported":
        audit["claims"][0]["supported"] = False
    if change == "omission":
        audit["claims"] = []
    if change == "duplicate":
        audit["claims"] *= 2
    if change == "incomplete_answer":
        audit["answers_question"] = False
    if change == "assumption":
        audit["assumptions_supported"] = False
    if change == "judgment":
        audit["judgment_flag_correct"] = False
    result, _, _ = run([PLAN, DRAFT, audit])
    assert result["status"] == "validation_failed"
    assert not result["citations"]
    assert CLAIM["text"] not in result["markdown"]


@pytest.mark.parametrize("disposition", ["off_topic", "historical", "clarification"])
def test_refusals_do_not_retrieve_or_generate(disposition):
    result, client, _ = run([{**PLAN, "disposition": disposition}])
    assert result["status"] == disposition
    assert client.stages == ["understanding"]
    assert not result["citations"]


@pytest.mark.parametrize("competition", ["premier_league", "uefa", "fifa", "other"])
def test_unloaded_competition_rules_are_not_guessed(competition):
    result, client, _ = run([{**PLAN, "competition": competition}])
    assert result["status"] == "scope_unavailable"
    assert client.stages == ["understanding"]


def test_scenario_format_is_complete_and_ordered():
    draft = {
        "status": "judgment",
        "sections": [{"label": label, "claims": [CLAIM]} for label in SCENARIO_LABELS],
    }
    audit = {**AUDIT, "claims": [{"claim_id": f"{i}.1", "supported": True} for i in range(1, 5)]}
    result, _, _ = run([{**PLAN, "scenario": True}, draft, audit])
    assert result["status"] == "judgment"
    assert [s["label"] for s in result["sections"]] == SCENARIO_LABELS
    assert len(result["citations"]) == 1
    with pytest.raises(EvidenceError):
        check_draft(DraftAnswer.model_validate(DRAFT), EVIDENCE, True)


def test_corpus_replacement_during_generation_withholds_old_citations():
    result, _, _ = run([PLAN, DRAFT, AUDIT], current=False)
    assert result["status"] == "corpus_changed"
    assert result["citations"] == []


def test_no_evidence_does_not_call_generation():
    result, client, _ = run([PLAN], evidence=[])
    assert result["status"] == "insufficient_evidence"
    assert client.stages == ["understanding"]


def test_generation_abstention_does_not_masquerade_as_answer():
    result, client, _ = run([PLAN, {"status": "insufficient_evidence", "sections": []}])
    assert result["status"] == "insufficient_evidence"
    assert client.stages == ["understanding", "generation"]


def test_provider_failure_never_exposes_error_contents():
    result, _, _ = run([ProviderError("SECRET provider text")])
    assert result["status"] == "provider_error"
    assert "SECRET" not in str(result)


def test_no_api_key_or_cloud_model_setting_exists():
    assert "openai_api_key" not in Settings.model_fields
    assert "llm_model" not in Settings.model_fields


def test_evidence_budget_does_not_cut_exceptions_or_duplicate_sections():
    row = {
        "id": "1",
        "rulebook_id": "ifab",
        "section_key": "law-1",
        "heading_path": ["Law 1"],
        "edition": "test",
        "section_url": "https://example.com/1",
        "page_start": 1,
        "page_end": 1,
        "body": "x" * 100,
    }
    assert package_evidence([row], character_budget=99) == []
    assert len(package_evidence([row, row])) == 1


def test_reused_service_usage_is_per_question():
    client = FakeClient([{**PLAN, "disposition": "off_topic"}] * 2)
    service = AnswerService(client=client, logger=lambda *args: None)
    assert service.ask("First")["usage"]["input_tokens"] == 100
    assert service.ask("Second")["usage"]["input_tokens"] == 100


def test_context_budget_never_keeps_child_without_ancestor_conditions():
    parent = {
        "id": "parent",
        "rulebook_id": "test",
        "section_key": "law-1",
        "heading_path": ["Law 1"],
        "edition": "test",
        "section_url": "https://example.com/1",
        "page_start": 1,
        "page_end": 1,
        "body": "The parent conditions must be retained.",
    }
    child = {
        **parent,
        "id": "child",
        "section_key": "law-1/1",
        "parent_section_key": "law-1",
        "body": "The child provision.",
    }
    assert all(e["chunk_id"] != "child" for e in package_evidence([child, parent], maximum=1))
    assert {e["chunk_id"] for e in package_evidence([child, parent], maximum=2)} == {
        "child",
        "parent",
    }
