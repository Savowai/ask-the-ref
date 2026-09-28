import hashlib
import io
import json
from datetime import date

import httpx
import pytest
from ask_the_ref.config import Manifest, Source, load_manifest
from ask_the_ref.download import download_source, fetch_pdf, validate_pdf
from pydantic import ValidationError
from pypdf import PdfWriter


@pytest.fixture
def source():
    return Source(
        id="test-book",
        title="Test rules",
        authority="IFAB",
        competition_scope=["generic"],
        edition="2026/27",
        discovery_url="https://example.org/books",
        source_url="https://example.org/laws",
        download_url="https://example.org/book.pdf",
        allowed_hosts=["example.org"],
        effective_from=date(2026, 1, 1),
        verified_on=date(2026, 9, 28),
        verification="current",
        ingest_phase=2,
        coverage=["laws-1-17"],
    )


@pytest.fixture
def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_manifest_has_required_sources():
    manifest = load_manifest()
    assert {s.id for s in manifest.sources} >= {
        "ifab",
        "fifa-rstp",
        "uefa-ucl",
        "uefa-uel",
        "premier-league",
    }
    for source in manifest.sources:
        source.assert_current(date(2026, 9, 28))
        assert source.download_url


@pytest.mark.parametrize(
    "updates",
    [
        {"effective_from": date(2027, 1, 1)},
        {"effective_until": date(2026, 9, 28)},
        {"verification": "needs_review"},
        {"effective_from": None},
    ],
)
def test_not_current_is_rejected(source, updates):
    with pytest.raises(ValueError):
        source.model_copy(update=updates).assert_current(date(2026, 9, 28))


def test_current_on_first_effective_day(source):
    source.assert_current(date(2026, 1, 1))


def test_duplicate_book_rejected(source):
    with pytest.raises(ValidationError):
        Manifest(schema_version=1, checked_on=date.today(), sources=[source, source])


@pytest.mark.parametrize("url", ["http://example.org/book.pdf", "https://evil.org/book.pdf"])
def test_unapproved_manifest_url_rejected(source, url):
    with pytest.raises(ValidationError):
        Source.model_validate({**source.model_dump(), "download_url": url})


def test_pdf_hash_and_page_count(pdf):
    digest, pages = validate_pdf(pdf)
    assert digest == hashlib.sha256(pdf).hexdigest()
    assert pages == 1


def test_hash_mismatch_rejected(pdf):
    with pytest.raises(ValueError, match="SHA-256 changed"):
        validate_pdf(pdf, "0" * 64)


def test_html_response_does_not_replace_existing_pdf(source, tmp_path):
    target = tmp_path / "test-book.pdf"
    target.write_bytes(b"existing-valid-file")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html>Access denied</html>")
        )
    ) as client:
        with pytest.raises(ValueError, match="Expected PDF"):
            download_source(source, client, tmp_path)
    assert target.read_bytes() == b"existing-valid-file"
    assert not (tmp_path / "test-book.json").exists()


def test_foreign_redirect_is_blocked_before_request(source):
    visited = []

    def handler(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://evil.org/file.pdf"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="disallowed redirect"):
            fetch_pdf(client, source)
    assert visited == [source.download_url]


def test_same_host_relative_redirect_allowed(source, pdf):
    def handler(request):
        if request.url.path == "/book.pdf":
            return httpx.Response(302, headers={"Location": "/download"})
        return httpx.Response(200, content=pdf)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        content, url = fetch_pdf(client, source)
    assert content == pdf
    assert url == "https://example.org/download"


def test_receipt_and_idempotence(source, pdf, tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf))
    ) as client:
        assert download_source(source, client, tmp_path)["changed"]
        assert not download_source(source, client, tmp_path)["changed"]
    receipt = json.loads((tmp_path / "test-book.json").read_text())
    assert receipt["edition"] == source.edition
    assert receipt["ingested"] is False
    assert receipt["sha256"] == hashlib.sha256(pdf).hexdigest()
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_oversize_download_rejected(source, monkeypatch):
    monkeypatch.setattr("ask_the_ref.download.MAX_BYTES", 10)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"%PDF-" + b"x" * 10)
        )
    ) as client:
        with pytest.raises(ValueError, match="limit"):
            fetch_pdf(client, source)
