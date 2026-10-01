"""Local Phase 3 diagnostic: eight questions against the corpus and local model.

Requires make local-llm and make local-model. No API key or paid service.
"""

import json
from pathlib import Path

from ask_the_ref.answering import AnswerService
from ask_the_ref.config import Settings

CASES = [
    ("lookup", "Can you be offside directly from a throw-in?", {"answered"}, {"law-11/3"}),
    (
        "scenario",
        "During play, a player recklessly trips an opponent outside the penalty area. What is the decision, restart and card?",
        {"answered"},
        {"law-12/1"},
    ),
    (
        "slang",
        "What does DOGSO mean?",
        {"answered"},
        {"law-12/4/denying-a-goal-or-an-obvious-goal-scoring-opportunity-dogso"},
    ),
    (
        "judgment",
        "The ball hits a defender’s arm in their own penalty area. Is it always a penalty?",
        {"answered", "judgment", "clarification"},
        {"law-12/1/handling-the-ball", "definitions/handball"},
    ),
    (
        "unanswerable",
        "What is the exact universal arm angle in degrees that automatically makes contact handball?",
        {"insufficient_evidence", "judgment", "answered"},
        {"law-12/1/handling-the-ball", "definitions/handball"},
    ),
    (
        "competition",
        "How many homegrown players must a Premier League squad register?",
        {"scope_unavailable"},
        set(),
    ),
    ("off_topic", "Write me a banana bread recipe.", {"off_topic"}, set()),
    ("historical", "What were the offside rules in 1990?", {"historical"}, set()),
]


def main():
    settings = Settings()
    service = AnswerService(settings)
    rows = []
    for case, question, statuses, expected_sections in CASES:
        answer = service.ask(question)
        cited = {c["section_key"] for c in answer["citations"]}
        citation_match = (
            bool(cited & expected_sections)
            if answer["status"] in {"answered", "judgment"}
            else True
        )
        passed = answer["status"] in statuses and (citation_match or not expected_sections)
        rows.append(
            {"case": case, "question": question, "control_check_passed": passed, "answer": answer}
        )
        print(case, answer["status"], f"{answer['latency_ms']}ms", flush=True)
        if answer["status"] in {"configuration_error", "provider_error", "retrieval_error"}:
            break
    target = Path("work/answer-smoke.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    print(
        f"Wrote {target}. These checks verify controls and expected section hits, not answer correctness."
    )
    if len(rows) != len(CASES) or not all(r["control_check_passed"] for r in rows):
        raise SystemExit("Inspect live diagnostic failures before claiming Phase 3 validated.")


if __name__ == "__main__":
    main()
