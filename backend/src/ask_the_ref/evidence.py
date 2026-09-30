"""Evidence packaging and deterministic citation/format checks; no generated URLs."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .answer_types import SCENARIO_LABELS, AnswerAudit, DraftAnswer


class EvidenceError(ValueError):
    pass


@dataclass
class EvidenceBundle:
    evidence: list[dict]
    corpus_fingerprint: str
    sources: list[dict]
    timings_ms: dict


def package_evidence(rows, maximum=32, character_budget=100_000):
    output = []
    used = 0
    seen = set()
    lookup = {(r["rulebook_id"], r["section_key"]): r for r in rows}
    for row in rows:
        group = [row]
        cursor = row
        ancestors = set()
        while cursor.get("parent_section_key"):
            key = (cursor["rulebook_id"], cursor["parent_section_key"])
            if key in ancestors or key not in lookup:
                raise EvidenceError("Missing or cyclic ancestor section")
            ancestors.add(key)
            cursor = lookup[key]
            group.append(cursor)
        pending = [r for r in group if str(r["id"]) not in seen]
        size = sum(len(r["body"]) for r in pending)
        if used + size > character_budget or len(output) + len(pending) > maximum:
            continue  # Keep the subsection and its ancestor conditions together, or omit both.
        used += size
        for item in pending:
            seen.add(str(item["id"]))
            output.append(
                {
                    "evidence_id": f"E{len(output) + 1}",
                    "chunk_id": str(item["id"]),
                    "rulebook_id": item["rulebook_id"],
                    "section_key": item["section_key"],
                    "heading_path": item["heading_path"],
                    "edition": item["edition"],
                    "url": item["section_url"],
                    "page_start": item["page_start"],
                    "page_end": item["page_end"],
                    "body": item["body"],
                }
            )
    return output


def check_draft(draft: DraftAnswer, evidence, scenario):
    if draft.status not in ("answered", "judgment"):
        if draft.sections:
            raise EvidenceError("Abstentions must not contain claims")
        return []
    labels = SCENARIO_LABELS if scenario else ["Answer"]
    if [s.label for s in draft.sections] != labels:
        raise EvidenceError("Incorrect answer section format")
    by_id = {e["evidence_id"]: e for e in evidence}
    checked = []
    for section_index, section in enumerate(draft.sections, 1):
        for claim_index, claim in enumerate(section.claims, 1):
            # The renderer owns formatting and links; model-supplied ones cannot bypass validation.
            if re.search(r"[\[\]<>`\n\r]|https?://|\]\(|^\s*#", claim.text):
                raise EvidenceError("Claim contains untrusted formatting")
            if not claim.text.strip():
                raise EvidenceError("Empty claim")
            supports = []
            for support in claim.supports:
                row = by_id.get(support.evidence_id)
                if row is None:
                    raise EvidenceError("Unknown evidence ID")
                start = row["body"].find(support.quote)
                if start < 0:
                    raise EvidenceError("Quotation does not occur verbatim in the source")
                url = urlparse(row["url"])
                if url.scheme != "https" or url.username or url.password:
                    raise EvidenceError("Invalid source URL")
                supports.append(
                    {
                        "evidence_id": support.evidence_id,
                        "quote": support.quote,
                        "start": start,
                        "end": start + len(support.quote),
                    }
                )
            checked.append(
                {
                    "claim_id": f"{section_index}.{claim_index}",
                    "label": section.label,
                    "text": claim.text,
                    "supports": supports,
                }
            )
    return checked


def check_audit(audit: AnswerAudit, claims):
    wanted = {c["claim_id"] for c in claims}
    got = [c.claim_id for c in audit.claims]
    if len(got) != len(set(got)) or set(got) != wanted:
        raise EvidenceError("Audit omitted or duplicated claims")
    if not (
        all(c.supported for c in audit.claims)
        and audit.answers_question
        and audit.assumptions_supported
        and audit.judgment_flag_correct
    ):
        raise EvidenceError("Support audit rejected the answer")


def render_answer(draft, claims, evidence):
    by_id = {e["evidence_id"]: e for e in evidence}
    citations = []
    numbers = {}
    sections = []
    for section in draft.sections:
        rendered = []
        for claim in [c for c in claims if c["label"] == section.label]:
            refs = []
            for support in claim["supports"]:
                key = (support["evidence_id"], support["start"], support["end"])
                if key not in numbers:
                    numbers[key] = len(citations) + 1
                    row = by_id[support["evidence_id"]]
                    citations.append({**row, **support, "number": numbers[key]})
                number = numbers[key]
                refs.append(f"[{number}]({by_id[support['evidence_id']]['url']})")
            rendered.append(claim["text"] + " " + " ".join(dict.fromkeys(refs)))
        sections.append({"label": section.label, "claims": rendered})
    paragraphs = []
    if draft.status == "judgment":
        paragraphs.append("**Referee judgment**")
    for section in sections:
        paragraphs.append("**" + section["label"] + "**\n\n" + "\n\n".join(section["claims"]))
    return {"sections": sections, "citations": citations, "markdown": "\n\n".join(paragraphs)}
