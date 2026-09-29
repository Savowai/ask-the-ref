"""Edition-pinned IFAB layout parser. Stored chunks follow headings, never token counts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pdfplumber
from pdfplumber.utils import extract_words

from .config import Source

IFAB_SHA = "89398520b353c6d995a1bb2557c97dc3c5aa1712c1d3009589f580a5a23c6a7d"
LAW_STARTS = [45, 55, 59, 67, 73, 85, 93, 97, 101, 103, 109, 115, 131, 135, 141, 145, 149]
LAW_TITLES = [
    "The Field of Play",
    "The Ball",
    "The Players",
    "The Players’ Equipment",
    "The Referee",
    "The Other Match Officials",
    "The Duration of the Match",
    "The Start and Restart of Play",
    "The Ball in and out of Play",
    "Determining the Outcome of a Match",
    "Offside",
    "Fouls and Misconduct",
    "Free Kicks",
    "The Penalty Kick",
    "The Throw-in",
    "The Goal Kick",
    "The Corner Kick",
]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Chunk:
    section_key: str
    parent_section_key: str | None
    kind: str
    law_article: str
    section_title: str
    heading_path: list[str]
    blocks: list[dict] = field(default_factory=list)
    source_url: str = ""
    section_url: str = ""

    @property
    def body(self):
        return "\n".join(b["text"] for b in self.blocks) or self.section_title

    @property
    def pages(self):
        return sorted({b["page"] for b in self.blocks if b.get("page")})

    def record(self):
        return {**asdict(self), "body": self.body, "pages": self.pages}


def positioned_words(page):
    """Use text-matrix baselines: this PDF's Cambria font boxes overlap headings."""
    chars = []
    for original in page.chars:
        c = dict(original)
        baseline = page.height - c["matrix"][5]
        if not 30 < baseline < 560 or not 5 <= c["size"] <= 10:
            continue
        # Embedded figure fonts have separate prefixes and must not become rule headings.
        if "Cambria" not in c["fontname"] and not c["fontname"].startswith(
            ("DIJLNM+", "HOHJRE+", "LUFMVW+", "TLGIDG+")
        ):
            continue
        if c["size"] < 8 and "Cambria" in c["fontname"]:
            baseline += 2.997  # Superscripts share the surrounding line in reading order.
            c["size"] = 9
        c["top"], c["bottom"], c["doctop"] = baseline - c["size"], baseline, baseline - c["size"]
        chars.append(c)
    return extract_words(chars, extra_attrs=["fontname"], x_tolerance=1.5, y_tolerance=2)


def lines(words):
    groups = []
    for w in sorted(words, key=lambda w: (round(w["bottom"]), w["x0"])):
        if not groups or abs(w["bottom"] - groups[-1][0]["bottom"]) > 2:
            groups.append([w])
        else:
            groups[-1].append(w)
    return [sorted(g, key=lambda w: w["x0"]) for g in groups]


def text_of(words):
    return " ".join(w["text"] for w in words).strip()


def table_blocks(page, words, number):
    """Law 14's continued table: use its real horizontal rules and fixed column geometry."""
    if number not in (138, 139):
        return [], words
    left = 39.685 if number == 138 else 48.189
    cols = [left, left + 110.551, left + 221.102, left + 331.654]
    minimum = 419 if number == 138 else 84
    edges = sorted(
        {
            round(e["top"], 1)
            for e in page.lines
            if abs(e["x0"] - left) < 1 and abs(e["x1"] - cols[1]) < 1 and e["top"] >= minimum
        }
    )
    expected = 3 if number == 138 else 9
    if len(edges) != expected:
        raise ValueError(f"Unrecognized penalty table geometry on page {number}")
    rows = []
    for top, bottom in zip(edges, edges[1:]):
        cells = []
        for x0, x1 in zip(cols, cols[1:]):
            cell = [w for w in words if x0 <= w["x0"] < x1 and top < w["bottom"] <= bottom]
            cells.append(" ".join(text_of(line) for line in lines(cell)))
        if not all(cells):
            raise ValueError("Empty penalty table cell")
        rows.append(cells)
    headers = ["Offence", "Goal scored from the kick", "No goal scored from the kick"]
    rendered = "\n".join(" | ".join(f"{h}: {c}" for h, c in zip(headers, row)) for row in rows)
    block = {
        "type": "table",
        "page": number,
        "bbox": [left, edges[0], cols[-1], edges[-1]],
        "headers": headers,
        "rows": rows,
        "text": rendered,
    }
    # Header is represented explicitly above; keep the numbered Summary table heading.
    cutoff = 376 if number == 138 else 84
    remaining = [w for w in words if w["bottom"] <= cutoff or w["bottom"] > edges[-1]]
    return [block], remaining


def chapters():
    extras = [
        (17, 19, "Notes on the Laws"),
        (20, 21, "General modifications"),
        (22, 23, "Time-limited substitution protocol"),
        (24, 25, "Off-field treatment and assessment protocol"),
        (26, 27, "Throw-in and goal-kick countdown protocol"),
        (28, 31, "Only the captain guidelines"),
        (32, 35, "Temporary dismissals"),
        (36, 37, "Return substitutes"),
        (38, 40, "Concussion substitutions"),
    ]
    for start, end, title in extras:
        yield start, end, slug(title), title, "protocol"
    for i, (start, title) in enumerate(zip(LAW_STARTS, LAW_TITLES), 1):
        end = LAW_STARTS[i] - 2 if i < 17 else 151
        yield start, end, f"law-{i}", f"Law {i} {title}", "section"
    yield 153, 160, "var", "VAR protocol", "protocol"
    for start, end, title in [
        (195, 195, "Football bodies"),
        (196, 205, "Football terms"),
        (206, 207, "Referee terms"),
    ]:
        yield start, end, "glossary/" + slug(title), title, "definition"
    for start, end, title in [
        (209, 209, "Introduction"),
        (210, 223, "Positioning, movement and teamwork"),
        (224, 229, "Body language, communication and whistle"),
        (230, 239, "Other advice"),
    ]:
        yield start, end, "guidelines/" + slug(title), title, "guidance"


def append_line(chunk, line, page):
    text = text_of(line)
    if not text:
        return
    bbox = [
        min(w["x0"] for w in line),
        min(w["top"] for w in line),
        max(w["x1"] for w in line),
        max(w["bottom"] for w in line),
    ]
    is_list = bool(re.match(r"^(?:[•●]|\d+[.)]|[a-z][.)])\s", text))
    if (
        chunk.blocks
        and not is_list
        and chunk.blocks[-1]["type"] in ("paragraph", "list_item")
        and chunk.blocks[-1]["page"] == page
        and 0 < bbox[3] - chunk.blocks[-1]["bbox"][3] <= 14
        and bbox[0] >= chunk.blocks[-1]["bbox"][0] - 2
    ):
        last = chunk.blocks[-1]
        last["text"] += " " + text
        last["bbox"][2] = max(last["bbox"][2], bbox[2])
        last["bbox"][3] = bbox[3]
    else:
        chunk.blocks.append(
            {
                "type": "list_item" if is_list else "paragraph",
                "text": text,
                "page": page,
                "bbox": bbox,
                "indent": round(bbox[0], 1),
            }
        )


def parse_ifab(path: Path, source: Source) -> list[Chunk]:
    if (
        source.edition != "2026/27"
        or source.sha256 != IFAB_SHA
        or hashlib.sha256(path.read_bytes()).hexdigest() != IFAB_SHA
    ):
        raise ValueError("Unknown IFAB layout/hash: review a new parser profile before ingestion")
    result = []
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 260:
            raise ValueError("Unexpected page count")
        for start, end, key, title, kind in chapters():
            base = Chunk(key, None, kind, key, title, ["IFAB", title])
            result.append(base)
            active, section = base, base
            for number in range(start, end + 1):
                page = pdf.pages[number - 1]
                tables, words = table_blocks(page, positioned_words(page), number)
                for line in lines(words):
                    text = text_of(line)
                    meaningful = [w for w in line if w["text"] != "•"]
                    bold = meaningful and all("Bold" in w["fontname"] for w in meaningful)
                    numbered = bool(re.match(r"^\d+\.\s", text))
                    is_heading = bold and (kind == "definition" or line[0]["x0"] < 70)
                    if is_heading:
                        parent = base if numbered or kind == "definition" else section
                        # A multiline heading has a 13pt baseline gap and no body in between.
                        if (
                            active is not base
                            and active.blocks
                            and active.blocks[-1]["type"] == "heading"
                            and active.blocks[-1]["page"] == number
                            and abs(line[0]["bottom"] - active.blocks[-1]["bbox"][3] - 13) < 2
                            and active.blocks[-1].get("font") == meaningful[0]["fontname"]
                            and active.blocks[-1]["bbox"][2] > 330
                            and not numbered
                        ):
                            active.section_title += " " + text
                            active.heading_path[-1] = active.section_title
                            active.blocks[-1]["text"] = active.section_title
                            active.blocks[-1]["bbox"][3] = line[0]["bottom"]
                            continue
                        part = re.match(r"^(\d+)\.", text)
                        childkey = parent.section_key + "/" + (part[1] if part else slug(text))
                        if any(c.section_key == childkey for c in result):
                            childkey += f"-p{number}"
                        active = Chunk(
                            childkey,
                            parent.section_key,
                            kind,
                            key,
                            text,
                            parent.heading_path + [text],
                        )
                        result.append(active)
                        if numbered:
                            section = active
                        active.blocks.append(
                            {
                                "type": "heading",
                                "text": text,
                                "page": number,
                                "font": meaningful[0]["fontname"],
                                "bbox": [
                                    line[0]["x0"],
                                    line[0]["top"],
                                    line[-1]["x1"],
                                    line[0]["bottom"],
                                ],
                            }
                        )
                    else:
                        append_line(active, line, number)
                active.blocks.extend(tables)
            # Structural ancestors keep a location even if their content consists of children.
            for c in result:
                if c is base and not c.blocks:
                    c.blocks.append({"type": "heading", "text": title, "page": start, "bbox": None})
    # This is explicitly a future notice, not a rule in force in this edition.
    captain = next(c for c in result if c.section_key == "only-the-captain-guidelines")
    captain.blocks = [b for b in captain.blocks if "1 July 2027" not in b["text"]]
    if not captain.blocks:
        captain.blocks = [
            {"type": "heading", "text": captain.section_title, "page": 28, "bbox": None}
        ]
    for c in result:
        c.source_url = source.download_url or source.source_url
        c.section_url = c.source_url + f"#page={min(c.pages)}"
    # Law 12 nests officials' warning/caution/sending-off provisions under Team officials.
    team = next(c for c in result if c.section_key == "law-12/4/team-officials")
    for c in result:
        if c.section_key in ("law-12/4/warning", "law-12/4/caution", "law-12/4/sending-off"):
            c.parent_section_key = team.section_key
            c.section_key = team.section_key + "/" + c.section_key.rsplit("/", 1)[-1]
            c.heading_path = team.heading_path + [c.section_title]
    # Terms defined within laws receive separate definition chunks with exact source text.
    import copy

    for term, origin, needle in [
        ("Handball", "law-12/1/handling-the-ball", None),
        ("Interfering with play", "law-11/2", "interfering with play by"),
    ]:
        original = next(c for c in result if c.section_key == origin)
        definition = copy.deepcopy(original)
        definition.section_key = "definitions/" + slug(term)
        definition.parent_section_key = original.section_key
        definition.kind = "definition"
        definition.section_title = term
        definition.heading_path = original.heading_path + [term]
        if needle:
            definition.blocks = [b for b in definition.blocks if needle in b["text"]]
        result.append(definition)
    validate_chunks(result)
    return result


def validate_chunks(chunks):
    keys = {c.section_key for c in chunks}
    if len(keys) != len(chunks):
        raise ValueError("Duplicate section keys")
    for c in chunks:
        if c.parent_section_key and c.parent_section_key not in keys:
            raise ValueError("Orphan subsection")
        if not c.pages or any(166 <= p <= 193 for p in c.pages):
            raise ValueError("Missing provenance or historical comparison text")
    for law in range(1, 18):
        if f"law-{law}/1" not in keys:
            raise ValueError(f"Missing first section of Law {law}")
