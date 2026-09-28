"""Fetch official PDFs without committing content or treating downloads as ingestions."""

import argparse
import hashlib
import io
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ask_the_ref.config import ROOT, Source, load_manifest

MAX_BYTES = 100 * 1024 * 1024


def fetch_pdf(client: httpx.Client, source: Source) -> tuple[bytes, str]:
    if not source.download_url:
        raise ValueError(f"{source.id}: no verified PDF URL; see {source.discovery_url}")
    url = source.download_url
    # Validate every hop before making the request, not only after following redirects.
    for _ in range(6):
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in source.allowed_hosts
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError(f"{source.id}: disallowed redirect host")
        with client.stream("GET", url, follow_redirects=False) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect has no Location")
                url = str(response.url.join(location))
                continue
            response.raise_for_status()
            data = bytearray()
            for block in response.iter_bytes():
                data.extend(block)
                if len(data) > MAX_BYTES:
                    raise ValueError("PDF exceeds 100 MiB limit")
            content = bytes(data)
            if not content.startswith(b"%PDF-"):
                raise ValueError("Expected PDF bytes, got HTML or other content")
            return content, url
    raise ValueError("Too many redirects")


def validate_pdf(content: bytes, expected_sha256: str | None = None) -> tuple[str, int]:
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("SHA-256 changed: review the source before accepting replacement")
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted or not reader.pages:
        raise ValueError("PDF is encrypted or has no pages")
    return digest, len(reader.pages)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def download_source(source: Source, client: httpx.Client, output: Path) -> dict:
    source.assert_current(datetime.now(UTC).date())
    content, resolved_url = fetch_pdf(client, source)
    digest, pages = validate_pdf(content, source.sha256)
    # Fixed filename per rulebook; updates do not accumulate old editions.
    target = output / f"{source.id}.pdf"
    sidecar = output / f"{source.id}.json"
    old = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    changed = old.get("sha256") != digest or old.get("edition") != source.edition
    metadata = {
        "id": source.id,
        "edition": source.edition,
        "source_url": source.source_url,
        "download_url": source.download_url,
        "resolved_url": resolved_url,
        "sha256": digest,
        "pdf_pages": pages,
        "last_download_checked_at": datetime.now(UTC).isoformat(),
        "effective_from": source.effective_from.isoformat(),
        "effective_until": source.effective_until.isoformat() if source.effective_until else None,
        "ingested": False,
    }
    # Validation finishes before replacing the previous PDF. The sidecar is a receipt,
    # not a database activation signal; ingestion must verify its checksum again.
    atomic_write(target, content)
    atomic_write(sidecar, (json.dumps(metadata, indent=2) + "\n").encode())
    return {"id": source.id, "changed": changed, "sha256": digest, "pdf_pages": pages}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", help="Source id; repeatable")
    parser.add_argument("--list", action="store_true", help="Validate and list sources offline")
    args = parser.parse_args()
    manifest = load_manifest()
    known = {source.id for source in manifest.sources}
    if args.source and set(args.source) - known:
        parser.error("Unknown source: " + ", ".join(sorted(set(args.source) - known)))
    selected = [s for s in manifest.sources if not args.source or s.id in args.source]
    if args.list:
        for source in selected:
            print(json.dumps(source.model_dump(mode="json")))
        return
    errors = []
    with httpx.Client(
        timeout=60, headers={"User-Agent": "AskTheRef/0.1 (official rulebook fetcher)"}
    ) as client:
        for source in selected:
            try:
                print(json.dumps(download_source(source, client, ROOT / "data/raw")))
            except (ValueError, httpx.HTTPError, OSError, PyPdfError) as exc:
                errors.append(source.id)
                print(json.dumps({"id": source.id, "error": str(exc)}))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
