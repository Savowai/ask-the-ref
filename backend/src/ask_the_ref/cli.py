"""Phase 2 extractive Q&A: quote evidence without inventing a generated decision."""

import argparse
import json
import sys
from datetime import date

from .config import ROOT, load_manifest


def parse():
    from .corrections import apply_corrections
    from .parsing import parse_ifab

    source = next(s for s in load_manifest().sources if s.id == "ifab")
    source.assert_current(date.today())
    chunks = apply_corrections(parse_ifab(ROOT / "data/raw/ifab.pdf", source), source)
    target = ROOT / "data/processed/ifab.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([c.record() for c in chunks], ensure_ascii=False, indent=2))
    return chunks, source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["models", "corrections", "parse", "migrate", "ingest"]:
        commands.add_parser(name)
    ask = commands.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument(
        "--mode", choices=["vector", "hybrid", "hybrid-rerank"], default="hybrid-rerank"
    )
    ask.add_argument("--top-k", type=int, default=5)
    ask.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "models":
            from .models import download_models

            download_models()
        elif args.command == "corrections":
            from .corrections import fetch_corrections

            fetch_corrections(next(s for s in load_manifest().sources if s.id == "ifab"))
            print("Verified official section corrections downloaded.")
        elif args.command == "migrate":
            from .retrieval import migrate

            migrate()
            print("Database schema migrated.")
        elif args.command in ("parse", "ingest"):
            chunks, source = parse()
            if args.command == "ingest":
                from .retrieval import ingest

                print(json.dumps(ingest(chunks, source)))
            else:
                print(f"Parsed {len(chunks)} sections → data/processed/ifab.json")
        elif args.command == "ask":
            from .retrieval import Search

            response = Search(rerank=args.mode == "hybrid-rerank").ask(
                args.question, args.mode, args.top_k
            )
            if args.json:
                print(json.dumps(response, default=str, ensure_ascii=False, indent=2))
            else:
                print(response["notice"] + "\n")
                for i, row in enumerate(response["results"], 1):
                    print(f"[{i}] {' > '.join(row['heading_path'])} ({row['edition']})")
                    print(row["section_url"])
                    print(row["body"] + "\n")
                print(
                    f"{response['latency_ms']} ms (models already loaded); API cost $0 (local compute excluded)."
                )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
