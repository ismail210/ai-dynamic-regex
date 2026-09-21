#!/usr/bin/env python3
"""Build realistic Semantic Review damage-test PDFs by mutating REAL labels.

Copies Burrville / ST / Structure uploads in full (page count preserved), then
replaces selected structural callouts **in their original drawing locations**.

No test tables. No legend panels. Originals are never modified.

Usage:
  cd backend && ./venv/bin/python scripts/build_semantic_damage_test_pdfs.py
  ./venv/bin/python scripts/build_semantic_damage_test_pdfs.py --seed 20260914
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import fitz

ROOT = Path(__file__).resolve().parents[2]
UPLOADS = ROOT / "backend" / "uploads"
DEFAULT_OUT = ROOT / "backend" / "tests" / "fixtures" / "semantic_test_pdfs"
FRONTEND_FIXTURES = ROOT / "frontend" / "src" / "fixtures" / "semanticDamage"

# Compact AISC-like designation (single PDF word / span).
DESIGNATION_RE = re.compile(
    r"^(?:2L|WT|HSS|PIPE|W|C|MC|L|S|M|HP)"
    r"\d+(?:\.\d+)?"
    r"(?:X\d+(?:\.\d+)?(?:/\d+)?){1,2}$",
    re.I,
)

OCR_SWAPS = [
    ("0", "O"),
    ("1", "I"),
    ("5", "S"),
    ("6", "G"),
    ("8", "B"),
    ("2", "Z"),
]

FRAC_TO_DEC = {
    "1/8": "0.125",
    "3/16": "0.1875",
    "1/4": "0.250",
    "5/16": "0.3125",
    "3/8": "0.375",
    "1/2": "0.500",
    "5/8": "0.625",
    "3/4": "0.750",
}

SOURCES = [
    {
        "key": "burrville",
        "stem": "burrville_SEMANTIC_DAMAGE_TEST",
        "src": UPLOADS / "Burrville ES - ST__0d910a43b4a0.pdf",
        "project": "Burrville ES - ST",
    },
    {
        "key": "st",
        "stem": "st_SEMANTIC_DAMAGE_TEST",
        "src": UPLOADS / "ST__0bfc2d61245d.pdf",
        "project": "ST",
    },
    {
        "key": "structure",
        "stem": "structure_SEMANTIC_DAMAGE_TEST",
        "src": UPLOADS / "Structure - Copy__9414716bffc6.pdf",
        "project": "Structure - Copy",
    },
]


@dataclass
class Hit:
    page_index: int  # 0-based
    raw: str
    compact: str
    bbox: Tuple[float, float, float, float]
    fontsize: float


@dataclass
class Case:
    test_case_id: str
    category: str
    corruption_type: str
    source_page: int  # 1-based
    original_text: str
    test_text: str
    intended_semantic_result: Optional[str]
    expected_operation: str
    expected_status: str
    expected_normalized: Optional[str]
    expected_abstention: bool
    original_bbox: List[float]
    modified_bbox: List[float]
    fontsize: float


def compact_label(text: str) -> str:
    return (
        re.sub(r"\s+", "", str(text or "").upper())
        .replace("×", "X")
        .replace("✕", "X")
        .rstrip(",;:")
    )


def fraction_to_decimal_label(compact: str) -> Optional[str]:
    m = re.match(r"^(HSS\d+(?:\.\d+)?X\d+(?:\.\d+)?X)(\d+/\d+)$", compact)
    if not m:
        return None
    frac = m.group(2)
    dec = FRAC_TO_DEC.get(frac)
    if not dec:
        return None
    return f"{m.group(1)}{dec}"


def strip_angle_thickness(compact: str) -> Optional[str]:
    m = re.match(r"^((?:2L|L)\d+(?:\.\d+)?X\d+(?:\.\d+)?)X[\d./]+$", compact)
    return m.group(1) if m else None


def apply_char_swap(compact: str, rng: random.Random) -> Optional[Tuple[str, str]]:
    digits = [i for i, ch in enumerate(compact) if ch.isdigit()]
    if not digits:
        return None
    # Prefer trailing weight digits for visibility.
    idx = rng.choice(digits[-3:] if len(digits) >= 3 else digits)
    ch = compact[idx]
    for a, b in OCR_SWAPS:
        if ch == a:
            return compact[:idx] + b + compact[idx + 1 :], f"ocr_swap_{a}_to_{b}"
        if ch == b:
            return compact[:idx] + a + compact[idx + 1 :], f"ocr_swap_{b}_to_{a}"
    return None


def apply_deletion(compact: str) -> Optional[Tuple[str, str]]:
    if len(compact) < 5 or "X" not in compact:
        return None
    # Drop last character of the last field.
    return compact[:-1], "char_deletion_trailing"


def apply_insertion(compact: str, rng: random.Random) -> Optional[Tuple[str, str]]:
    if len(compact) < 4:
        return None
    idx = rng.randrange(1, len(compact))
    ch = compact[idx]
    return compact[:idx] + ch + compact[idx:], f"char_insertion_duplicate_{ch}"


def apply_spacing(compact: str) -> Tuple[str, str]:
    # W12X26 → W 12 X 26 ; HSS8X8X3/8 → HSS 8 X 8 X 3/8
    spaced = re.sub(r"([A-Z]+)(\d)", r"\1 \2", compact)
    spaced = spaced.replace("X", " X ")
    spaced = re.sub(r"\s+", " ", spaced).strip()
    return spaced, "spacing_around_fields"


def collect_hits(doc: fitz.Document) -> List[Hit]:
    hits: List[Hit] = []
    seen = set()
    for page_index in range(doc.page_count):
        page = doc[page_index]
        # Spans give reliable fontsize; fall back to words if needed.
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    raw = (span.get("text") or "").strip()
                    if not raw:
                        continue
                    compact = compact_label(raw)
                    if not DESIGNATION_RE.match(compact):
                        continue
                    bbox = tuple(float(v) for v in span["bbox"])
                    key = (page_index, compact, round(bbox[0], 1), round(bbox[1], 1))
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(
                        Hit(
                            page_index=page_index,
                            raw=raw,
                            compact=compact,
                            bbox=bbox,  # type: ignore[arg-type]
                            fontsize=float(span.get("size") or max(6.0, bbox[3] - bbox[1])),
                        )
                    )
    return hits


def replace_in_place(page: fitz.Page, bbox: Sequence[float], new_text: str, fontsize: float) -> List[float]:
    """Cover original glyph area and write replacement text at the same anchor."""
    rect = fitz.Rect(bbox)
    # Slight pad so residual ink from the original glyph is covered.
    cover = fitz.Rect(rect.x0 - 0.8, rect.y0 - 0.6, rect.x1 + 0.8, rect.y1 + 0.6)
    page.draw_rect(cover, color=None, fill=(1, 1, 1), width=0)

    # Fit font to original height; shrink if replacement is longer.
    height = max(5.0, rect.y1 - rect.y0)
    fs = min(fontsize, height * 0.92)
    width_est = fitz.get_text_length(new_text, fontname="helv", fontsize=fs)
    avail = max(4.0, cover.x1 - cover.x0)
    if width_est > avail:
        fs = max(5.0, fs * (avail / width_est))

    # Baseline near original bottom.
    insert_point = fitz.Point(rect.x0, rect.y1 - max(0.5, height * 0.12))
    page.insert_text(
        insert_point,
        new_text,
        fontsize=fs,
        fontname="helv",
        color=(0, 0, 0),
    )
    new_w = fitz.get_text_length(new_text, fontname="helv", fontsize=fs)
    return [float(rect.x0), float(rect.y0), float(rect.x0 + new_w), float(rect.y1)]


def pick_hits_for_category(hits: List[Hit], category: str, taken: set, rng: random.Random) -> List[Hit]:
    pool: List[Hit] = []
    for h in hits:
        key = (h.page_index, h.compact, round(h.bbox[0], 1), round(h.bbox[1], 1))
        if key in taken:
            continue
        c = h.compact
        if category == "decimal_fraction":
            if fraction_to_decimal_label(c):
                pool.append(h)
        elif category == "incomplete":
            if strip_angle_thickness(c):
                pool.append(h)
        elif category == "clean_control":
            if re.match(r"^(?:W|HSS|L)\d", c) and "X" in c:
                pool.append(h)
        elif category in {"char_corruption", "deletion", "insertion", "spacing"}:
            if re.match(r"^(?:W|HSS|C|MC|WT|2L|L)\d", c):
                pool.append(h)
        else:
            pool.append(h)
    rng.shuffle(pool)
    return pool


def plan_cases(hits: List[Hit], stem: str, rng: random.Random, target: int = 28) -> List[Tuple[Hit, Case]]:
    """Assign mutation categories to distinct hits."""
    quotas = [
        ("char_corruption", 6),
        ("deletion", 3),
        ("insertion", 3),
        ("decimal_fraction", 4),
        ("spacing", 4),
        ("incomplete", 4),
        ("clean_control", 4),
    ]
    # Pad with char_corruption if short.
    while sum(q for _, q in quotas) < target:
        quotas[0] = ("char_corruption", quotas[0][1] + 1)

    taken: set = set()
    planned: List[Tuple[Hit, Case]] = []
    case_i = 0

    for category, want in quotas:
        pool = pick_hits_for_category(hits, category, taken, rng)
        for hit in pool[:want]:
            case_i += 1
            key = (hit.page_index, hit.compact, round(hit.bbox[0], 1), round(hit.bbox[1], 1))
            taken.add(key)
            mutation = mutate(hit, category, rng)
            if mutation is None:
                continue
            test_text, corruption_type, expected_op, expected_status, expected_norm, abstain, intended = mutation
            case = Case(
                test_case_id=f"{stem}__c{case_i:02d}_{category}",
                category=category,
                corruption_type=corruption_type,
                source_page=hit.page_index + 1,
                original_text=hit.raw,
                test_text=test_text,
                intended_semantic_result=intended,
                expected_operation=expected_op,
                expected_status=expected_status,
                expected_normalized=expected_norm,
                expected_abstention=abstain,
                original_bbox=[float(v) for v in hit.bbox],
                modified_bbox=[float(v) for v in hit.bbox],  # updated after write
                fontsize=hit.fontsize,
            )
            planned.append((hit, case))
            if len(planned) >= target:
                return planned
    return planned


def mutate(
    hit: Hit, category: str, rng: random.Random
) -> Optional[Tuple[str, str, str, str, Optional[str], bool, Optional[str]]]:
    c = hit.compact
    if category == "clean_control":
        # Preserve exact source glyph text; do not upper-case rewrite.
        raw = hit.raw
        return raw, "none", "keep", "clean_control", c, False, c
    if category == "char_corruption":
        swapped = apply_char_swap(c, rng)
        if not swapped:
            return None
        text, ctype = swapped
        return text, ctype, "repair", "needs_review", c, False, c
    if category == "deletion":
        deleted = apply_deletion(c)
        if not deleted:
            return None
        text, ctype = deleted
        return text, ctype, "repair", "needs_review", c, False, c
    if category == "insertion":
        inserted = apply_insertion(c, rng)
        if not inserted:
            return None
        text, ctype = inserted
        return text, ctype, "repair", "needs_review", c, False, c
    if category == "decimal_fraction":
        decimal = fraction_to_decimal_label(c)
        if not decimal:
            return None
        return decimal, "fraction_to_decimal_display", "normalization", "normalized", c, False, c
    if category == "spacing":
        spaced, ctype = apply_spacing(c)
        return spaced, ctype, "normalization", "normalized", c, False, c
    if category == "incomplete":
        core = strip_angle_thickness(c)
        if not core:
            return None
        return (
            core,
            "strip_thickness_for_abstention",
            "abstention",
            "incomplete_missing_thickness",
            core,
            True,
            core,
        )
    return None


def build_one(spec: dict, out_dir: Path, seed: int) -> dict:
    src: Path = spec["src"]
    if not src.exists():
        raise FileNotFoundError(src)
    stem = spec["stem"]
    out_pdf = out_dir / f"{stem}.pdf"
    out_manifest = out_dir / f"{stem}.manifest.json"

    # Safety: never write into uploads/
    assert out_pdf.resolve() != src.resolve()
    assert UPLOADS.resolve() not in out_pdf.resolve().parents or out_dir.resolve() != UPLOADS.resolve()

    rng = random.Random(seed)
    # Full-page-count copy of the original drawing set.
    shutil.copy2(src, out_pdf)
    doc = fitz.open(out_pdf)
    hits = collect_hits(doc)
    planned = plan_cases(hits, stem, rng, target=28)

    # Apply mutations page by page (stable order).
    planned.sort(key=lambda pair: (pair[0].page_index, pair[0].bbox[1], pair[0].bbox[0]))
    cases: List[Case] = []
    changed_pages = set()
    for hit, case in planned:
        page = doc[hit.page_index]
        if case.category == "clean_control":
            # Leave glyphs untouched; still record the control.
            cases.append(case)
            continue
        new_bbox = replace_in_place(page, hit.bbox, case.test_text, hit.fontsize)
        case.modified_bbox = new_bbox
        cases.append(case)
        changed_pages.add(hit.page_index + 1)

    doc.saveIncr()
    page_count = doc.page_count
    first_rect = list(doc[0].rect)
    doc.close()

    src_doc = fitz.open(src)
    src_first = list(src_doc[0].rect)
    src_pages = src_doc.page_count
    src_doc.close()

    category_counts = {}
    for case in cases:
        category_counts[case.category] = category_counts.get(case.category, 0) + 1

    manifest = {
        "demo": True,
        "source_type": "in_place_controlled_corruption",
        "project": spec["project"],
        "source_pdf": str(src),
        "output_pdf": str(out_pdf),
        "seed": seed,
        "page_count": page_count,
        "source_page_count": src_pages,
        "page_count_preserved": page_count == src_pages,
        "page_size_first": first_rect,
        "page_size_match_first": first_rect == src_first,
        "original_pdf_modified": False,
        "case_count": len(cases),
        "changed_pages": sorted(changed_pages),
        "category_counts": category_counts,
        "cases": [asdict(c) for c in cases],
        "notes": [
            "Controlled corruptions replace selected real callouts in-place.",
            "No test table / legend panel is drawn on the PDF.",
            "Expected fields are test metadata only — not model outputs.",
            "Incomplete angle cases strip thickness to exercise abstention.",
            "Decimal cases rewrite fraction thickness to decimal form to exercise normalization.",
        ],
    }
    out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def write_frontend_fixture(manifests: Iterable[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for manifest in manifests:
        stem = Path(manifest["output_pdf"]).stem
        path = out_dir / f"{stem}.manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        index.append(
            {
                "stem": stem,
                "project": manifest["project"],
                "case_count": manifest["case_count"],
                "manifest": f"{stem}.manifest.json",
                "match_filename_substrings": [stem, Path(manifest["output_pdf"]).name],
            }
        )
    (out_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=20260914)
    parser.add_argument("--source-dir", type=Path, default=UPLOADS)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for i, spec in enumerate(SOURCES):
        local = dict(spec)
        # Allow alternate uploads root
        name = Path(spec["src"]).name
        candidate = args.source_dir / name
        if candidate.exists():
            local["src"] = candidate
        print(f"Building {local['stem']} from {local['src']} …")
        manifest = build_one(local, args.output_dir, seed=args.seed + i)
        manifests.append(manifest)
        print(
            f"  → {manifest['output_pdf']}  cases={manifest['case_count']}  "
            f"changed_pages={manifest['changed_pages']}  cats={manifest['category_counts']}"
        )

    write_frontend_fixture(manifests, FRONTEND_FIXTURES)
    print(f"Frontend fixtures → {FRONTEND_FIXTURES}")
    print(f"README (manual): {args.output_dir / 'README.md'}")


if __name__ == "__main__":
    main()
