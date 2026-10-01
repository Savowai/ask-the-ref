"""Export the current processed IFAB corpus for the no-key Vercel app."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "ifab.json"
TARGET = ROOT / "apps" / "web" / "src" / "data" / "ifab.json"

FIELDS = (
    "section_key",
    "kind",
    "law_article",
    "section_title",
    "heading_path",
    "body",
    "section_url",
)


def main() -> None:
    chunks = json.loads(SOURCE.read_text())
    exported = []
    for chunk in chunks:
        item = {field: chunk[field] for field in FIELDS}
        pages = chunk["pages"]
        item["page_start"] = min(pages) if pages else None
        item["page_end"] = max(pages) if pages else None
        exported.append(item)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(exported, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Exported {len(exported)} current IFAB sections to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
