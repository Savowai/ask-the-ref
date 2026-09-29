"""Pinned official section replacements. Never append corrections alongside obsolete wording."""

import hashlib
import json
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from .config import ROOT, Source
from .download import atomic_write


def extract_section(html: str, anchor: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article", id=anchor)
    if article is None:
        raise ValueError(f"Missing official section {anchor}")
    content = article.select_one(".laws-accordion-content")
    if content is None:
        raise ValueError("Missing section content")
    for deleted in content.select("del, s, strike, removed, deleted"):
        deleted.decompose()
    paragraphs = [" ".join(p.get_text("", strip=False).split()) for p in content.find_all("p")]
    if not paragraphs or any(not p for p in paragraphs):
        raise ValueError("Empty official replacement")
    return paragraphs


def fingerprint(paragraphs):
    return hashlib.sha256("\n".join(paragraphs).encode()).hexdigest()


def fetch_corrections(source: Source):
    for item in source.corrections:
        # URLs validated by Source; redirects deliberately rejected.
        response = httpx.get(item.url, timeout=30, follow_redirects=False)
        response.raise_for_status()
        paragraphs = extract_section(response.text, item.anchor)
        if fingerprint(paragraphs) != item.sha256:
            raise ValueError(
                f"{item.section_key}: official wording changed; source review required"
            )
        receipt = {
            "url": item.url,
            "anchor": item.anchor,
            "sha256": item.sha256,
            "checked_at": datetime.now(UTC).isoformat(),
            "paragraphs": paragraphs,
        }
        atomic_write(ROOT / "data/raw" / f"ifab-{item.anchor}.json", json.dumps(receipt).encode())


def apply_corrections(chunks, source: Source):
    for item in source.corrections:
        receipt = json.loads((ROOT / "data/raw" / f"ifab-{item.anchor}.json").read_text())
        if receipt["url"] != item.url or fingerprint(receipt["paragraphs"]) != item.sha256:
            raise ValueError("Invalid correction receipt")
        matches = [c for c in chunks if c.section_key == item.section_key]
        if len(matches) != 1:
            raise ValueError("Correction target missing or ambiguous")
        chunk = matches[0]
        chunk.source_url = item.url
        chunk.section_url = item.url + "#" + item.anchor
        chunk.blocks = [
            {
                "type": "paragraph",
                "text": p,
                "page": None,
                "bbox": None,
                "provenance": "official HTML amendment",
                "source_sha256": item.sha256,
            }
            for p in receipt["paragraphs"]
        ]
    return chunks
