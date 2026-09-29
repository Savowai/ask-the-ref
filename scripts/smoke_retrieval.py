"""Small Phase 2 retrieval diagnostic, not the Phase 4 golden-set evaluation."""

import json
from pathlib import Path

from ask_the_ref.retrieval import Search

CASES = [
    ("Can you be offside directly from a throw-in?", ["law-11/3"]),
    ("How long can the goalkeeper hold the ball in their hands?", ["law-12/3"]),
    (
        "How many substitutions are allowed in official competitions?",
        ["law-3/2/official-competitions"],
    ),
    ("What happens if the ball bursts during play?", ["law-2/2"]),
    (
        "Is every contact between the ball and a hand an offence?",
        ["law-12/1/handling-the-ball", "definitions/handball"],
    ),
    (
        "Does a reckless tackle require a yellow card?",
        ["law-12/1", "glossary/football-terms/reckless"],
    ),
    ("Can a goal be scored directly from a corner kick?", ["law-17"]),
    ("Can a team play with fewer than seven players?", ["law-3/1"]),
    (
        "What happens if a team causes abandonment by having fewer than seven players?",
        ["law-7/5", "law-3/1"],
    ),
    ("What is the difference between careless and excessive force?", ["law-12/1"]),
    (
        "What is the result of an accidental double touch during a penalty kick?",
        ["law-14/1", "law-14/3"],
    ),
    ("When can VAR review a second yellow card?", ["var/1", "var/2", "law-6/5"]),
]


def main():
    search = Search()
    report = []
    for mode in ["vector", "hybrid", "hybrid-rerank"]:
        cases = []
        for question, expected in CASES:
            response = search.ask(question, mode)
            keys = [r["section_key"] for r in response["results"]]
            rank = next((i for i, k in enumerate(keys, 1) if k in expected), None)
            cases.append(
                {
                    "question": question,
                    "expected_any": expected,
                    "retrieved": keys,
                    "first_relevant_rank": rank,
                    "latency_ms": response["latency_ms"],
                }
            )
        row = {
            "mode": mode,
            "hits_at_5": sum(c["first_relevant_rank"] is not None for c in cases),
            "questions": len(cases),
            "cases": cases,
        }
        report.append(row)
        print(mode, row["hits_at_5"], "/", len(cases))
    Path("work/retrieval-smoke.json").write_text(json.dumps(report, indent=2))
    if report[-1]["hits_at_5"] != len(CASES):
        raise SystemExit("Inspect missed sections in work/retrieval-smoke.json")


if __name__ == "__main__":
    main()
