"""Synthetic unit fixtures; real copyrighted rule text stays in ignored local files."""

from pathlib import Path

import pytest
from ask_the_ref.config import ROOT, load_manifest
from ask_the_ref.corrections import apply_corrections, extract_section, fingerprint
from ask_the_ref.parsing import Chunk, append_line, lines, parse_ifab, text_of
from ask_the_ref.retrieval import definition_links, rrf


def word(text, x, y=50, font="Cambria"):
    return {
        "text": text,
        "x0": x,
        "x1": x + len(text) * 3,
        "top": y - 9,
        "bottom": y,
        "fontname": font,
    }


def test_reading_order():
    result = lines([word("two", 40), word("next", 10, 65), word("one", 10)])
    assert [text_of(line) for line in result] == ["one two", "next"]


def test_list_item_continuation_keeps_number_and_indent():
    chunk = Chunk("a", None, "section", "1", "Title", ["Title"])
    append_line(chunk, [word("1.", 10), word("First", 25)], 1)
    append_line(chunk, [word("continued", 25, 63)], 1)
    append_line(chunk, [word("•", 20, 76), word("Nested", 35, 76)], 1)
    assert [b["type"] for b in chunk.blocks] == ["list_item", "list_item"]
    assert chunk.blocks[0]["text"] == "1. First continued"
    assert chunk.blocks[1]["indent"] > chunk.blocks[0]["indent"]


def test_rrf_combines_independent_rankings_without_double_counting():
    ordered, scores = rrf(["a", "b", "a"], ["b", "c"])
    assert ordered == ["b", "a", "c"]
    assert scores["a"] == 1 / 61
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)


def test_corrections_exclude_deleted_words_and_other_sections():
    html = '<article id="x"><div class="laws-accordion-content"><p>Use <del>old</del><b>new</b> words.</p></div></article><p>Unrelated</p>'
    assert extract_section(html, "x") == ["Use new words."]
    with pytest.raises(ValueError):
        extract_section(html, "missing")
    assert fingerprint(["a", "b"]) != fingerprint(["ab"])


def test_definition_links_require_word_boundaries():
    definition = Chunk("def", "glossary", "definition", "Glossary", "Play", ["Play"])
    target = Chunk("law", None, "section", "1", "Law", ["Law"], [{"text": "play resumes"}])
    wrong = Chunk("other", None, "section", "2", "Law", ["Law"], [{"text": "player enters"}])
    assert definition_links([definition, target, wrong]) == [("def", "law", "defines")]


def test_unknown_pdf_fails_closed(tmp_path: Path):
    path = tmp_path / "unknown.pdf"
    path.write_bytes(b"%PDF-new-edition")
    with pytest.raises(ValueError, match="Unknown IFAB"):
        parse_ifab(path, load_manifest().sources[0])


@pytest.fixture(scope="module")
def corpus():
    path = ROOT / "data/raw/ifab.pdf"
    if not path.exists():
        pytest.skip("Download IFAB PDF for local parser integration checks")
    return {c.section_key: c for c in parse_ifab(path, load_manifest().sources[0])}


def test_real_pdf_structure_and_current_only(corpus):
    assert all(f"law-{i}/1" in corpus for i in range(1, 18))
    assert len([k for k in corpus if k.startswith("glossary/")]) > 60
    assert "law-3/2/official-competitions" in corpus
    assert "1st teams" in corpus["law-3/2/official-competitions"].body
    assert all(not any(166 <= p <= 193 for p in c.pages) for c in corpus.values())
    assert "1 July 2027" not in "\n".join(c.body for c in corpus.values())
    assert "should be used." in corpus["law-11/2"].body
    assert corpus["law-12/1/handling-the-ball"].parent_section_key == "law-12/1"
    assert corpus["definitions/interfering-with-play"].blocks


def test_real_penalty_table_keeps_ten_rows_and_three_columns(corpus):
    tables = [b for b in corpus["law-14/3"].blocks if b["type"] == "table"]
    assert [len(t["rows"]) for t in tables] == [2, 8]
    assert all(len(row) == 3 and all(row) for t in tables for row in t["rows"])
    double = next(row for t in tables for row in t["rows"] if "Double touch" in row[0])
    assert "Accidental: penalty is retaken" in double[1]
    assert "Accidental: indirect free kick" in double[2]


def test_real_glossary_no_heading_body_interleaving(corpus):
    abandon = corpus["glossary/football-terms/abandon"]
    assert "end/terminate" in abandon.body
    assert "Additional time" not in abandon.body
    assert "Careless" in corpus["glossary/football-terms/careless"].body


def test_real_corrections_replace_pdf_without_fake_page(corpus):
    source = load_manifest().sources[0]
    if not (ROOT / "data/raw/ifab-number-of-players.json").exists():
        pytest.skip("Download official correction receipts first")
    changed = apply_corrections(list(corpus.values()), source)
    rule = next(c for c in changed if c.section_key == "law-3/1")
    assert "forfeited" in rule.body
    assert not rule.pages
    assert rule.section_url.endswith("#number-of-players")
