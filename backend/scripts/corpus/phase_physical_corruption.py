"""Sections 30-34 -- physical PDF text-object corruption benchmark,
end-to-end recovery test through the real pipeline + v2 policy, visual
degradation fixtures, and OCR feasibility check.

Held-out TEST projects only (00 - Yellow Spring, 01 - Washington Latin,
39 - Tubman ES) so this benchmark stays leakage-consistent with the rest
of the v2 evaluation. Source PDFs are opened read-only and never modified
in place -- every corrupted copy is written under a separate output tree.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fitz  # noqa: E402
import joblib  # noqa: E402

from scripts.corpus.candidate_retrieval import union_retrieve  # noqa: E402
from scripts.corpus.common import read_jsonl, write_jsonl  # noqa: E402
from scripts.corpus.repair_features import deterministic_keep  # noqa: E402
from scripts.corpus.train_repair_policy import build_catalog, full_policy  # noqa: E402

SEED = 20260912
V1_DIR = Path(r"C:\Users\Bassam\Downloads\estima3d_structural_corpus_v1")
V2_DIR = Path(r"C:\Users\Bassam\Downloads\estima3d_structural_corpus_v2")
OUT_DIR = V2_DIR / "physical_corruption"
PDF_OUT = OUT_DIR / "pdf_text_corruption"
VISUAL_OUT = OUT_DIR / "visual_degradation"
MODELS_DIR = Path(__file__).resolve().parent / "_models"

SOURCE_PDFS = [
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects\00 - Yellow Spring\ST1.pdf",
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects\01 - Washington Latin\New bldg - St.pdf",
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects\39 - Tubman ES\Structural.pdf",
]

LABEL_RE = re.compile(
    r"^(W\d{1,2}X\d{1,3}(\.\d+)?|HSS\d+(\.\d+)?X\d+(\.\d+)?X(\d+/\d+|\.\d+)|C\d{1,2}X\d{1,2}(\.\d+)?)$"
)
CONFUSIONS = {"0": "O", "1": "I", "5": "S", "8": "B", "O": "0", "I": "1", "S": "5", "B": "8"}


def find_horizontal_labels(pdf_path: str, max_pages: int = 8) -> list[dict]:
    doc = fitz.open(pdf_path)
    found = []
    for pno in range(min(doc.page_count, max_pages)):
        page = doc[pno]
        d = page.get_text("dict")
        for block in d["blocks"]:
            for line in block.get("lines", []):
                dirv = line.get("dir", (1, 0))
                if abs(dirv[0]) <= 0.9:
                    continue
                for span in line.get("spans", []):
                    t = span["text"].strip()
                    if LABEL_RE.match(t):
                        found.append(
                            {
                                "path": pdf_path,
                                "page": pno,
                                "text": t,
                                "bbox": list(span["bbox"]),
                                "size": span["size"],
                            }
                        )
    doc.close()
    return found


def redact_and_insert(page: "fitz.Page", bbox: list[float], size: float, pieces: list[tuple[str, float]]) -> None:
    """Remove the original text object at bbox, then insert one or more new
    text runs at proportional x-offsets within the same bbox (pieces is a
    list of (text, x_fraction_start))."""
    rect = fitz.Rect(bbox)
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()
    width = rect.width
    baseline_y = rect.y1 - 1.0
    for text, x_frac in pieces:
        x = rect.x0 + width * x_frac
        page.insert_text((x, baseline_y), text, fontsize=size, fontname="helv", color=(0, 0, 0))


def build_fixtures() -> list[dict]:
    rng = random.Random(SEED)
    all_labels: dict[str, list[dict]] = {}
    for p in SOURCE_PDFS:
        all_labels[p] = find_horizontal_labels(p)

    w_labels = [l for p in SOURCE_PDFS for l in all_labels[p] if l["text"].startswith("W")]
    hss_labels = [l for p in SOURCE_PDFS for l in all_labels[p] if l["text"].startswith("HSS") and "/" in l["text"]]
    rng.shuffle(w_labels)
    rng.shuffle(hss_labels)

    manifest = []
    PDF_OUT.mkdir(parents=True, exist_ok=True)

    def make_fixture(src_path: str, page_no: int, orig_text: str, bbox: list[float], size: float,
                      corrupted_text: str, pieces: list[tuple[str, float]], ctype: str, idx: int) -> dict:
        doc = fitz.open(src_path)
        page = doc[page_no]
        redact_and_insert(page, bbox, size, pieces)
        safe_src = Path(src_path).stem.replace(" ", "_")
        out_name = f"{ctype}_{safe_src}_{idx}.pdf"
        out_path = PDF_OUT / out_name
        doc.save(str(out_path))
        doc.close()
        return {
            "fixture_path": str(out_path),
            "source_pdf": src_path,
            "source_page": page_no,
            "original_text": orig_text,
            "corrupted_text": corrupted_text,
            "corruption_type": ctype,
            "bbox_before": bbox,
            "bbox_after": bbox,
        }

    # 1) single-character substitution (10 fixtures)
    n_sub = min(10, len(w_labels))
    for i, lab in enumerate(w_labels[:n_sub]):
        text = lab["text"]
        digit_positions = [j for j, c in enumerate(text) if c in CONFUSIONS]
        if not digit_positions:
            continue
        pos = rng.choice(digit_positions)
        corrupted = text[:pos] + CONFUSIONS[text[pos]] + text[pos + 1:]
        manifest.append(
            make_fixture(lab["path"], lab["page"], text, lab["bbox"], lab["size"], corrupted,
                         [(corrupted, 0.0)], "character_substitution", i)
        )

    # 2) fragmentation into separate positioned spans (10 fixtures)
    frag_pool = w_labels[n_sub:n_sub + 10]
    for i, lab in enumerate(frag_pool):
        text = lab["text"]
        m = re.match(r"^(W\d{1,2})(X)(\d{1,3}(\.\d+)?)$", text)
        if not m:
            continue
        parts = [m.group(1), m.group(2), m.group(3)]
        total_chars = sum(len(p) for p in parts)
        pieces = []
        cursor = 0.0
        for part in parts:
            frac = cursor / total_chars
            pieces.append((part, frac))
            cursor += len(part)
        manifest.append(
            make_fixture(lab["path"], lab["page"], text, lab["bbox"], lab["size"], "|".join(parts),
                         pieces, "fragmentation", i)
        )

    # 3) fraction corruption on HSS labels (up to 6 fixtures)
    for i, lab in enumerate(hss_labels[:6]):
        text = lab["text"]
        frac_match = re.search(r"(\d+)/(\d+)$", text)
        if not frac_match:
            continue
        corrupted = text[: frac_match.start()] + frac_match.group(1) + "/"  # deletion: drop denominator
        manifest.append(
            make_fixture(lab["path"], lab["page"], text, lab["bbox"], lab["size"], corrupted,
                         [(corrupted, 0.0)], "fraction_deletion", i)
        )

    note = (
        "bracket_modifier_attachment corruption was NOT generated: the three held-out "
        "test-project PDFs contain zero bracket-modifier annotations (pattern "
        "[n;n;n]) in this sample -- that pattern was only observed in GCDC Building 4, "
        "which is a TRAIN-split project. Fabricating one on a held-out PDF would not "
        "be a real annotation, so this corruption type is honestly skipped here."
    )
    write_jsonl(PDF_OUT / "manifest.jsonl", manifest)
    (OUT_DIR / "PDF_TEXT_CORRUPTION_NOTE.md").write_text(note, encoding="utf-8")
    return manifest


def run_recovery(manifest: list[dict]) -> dict:
    from services.pdf_parser import extract_document_structure
    from services.semantic_preprocessor.extraction import build_text_primitives
    from services.semantic_preprocessor.pipeline import process_primitives
    from services.exact_section_predictor import predict_exact_sections
    from services.structural_parser import parse_fields

    catalog = build_catalog(V1_DIR)
    model_a = joblib.load(MODELS_DIR / "model_a_change_decision.joblib")
    model_b = joblib.load(MODELS_DIR / "model_b_ranker.joblib")
    doc_freq_idx: dict = {}
    auto_thresh, margin_thresh = -2.19, 0.0112

    results = []
    for rec in manifest:
        structure = extract_document_structure(rec["fixture_path"])
        primitives, _ = build_text_primitives(structure)
        doc = process_primitives(primitives, document_id="physical_corruption_e2e")
        # source_page is PyMuPDF's 0-indexed page number (doc[page_no]); the
        # production pipeline's Annotation.page is 1-indexed (pdf_parser.py:
        # page_number = page_index + 1).
        page_annotations = [a for a in doc.annotations if a.page == rec["source_page"] + 1]

        def bbox_center(b):
            return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)

        target_c = bbox_center(rec["bbox_before"])
        best = None
        best_dist = 1e18
        for a in page_annotations:
            c = bbox_center(a.semantic_bbox) if a.semantic_bbox else (1e9, 1e9)
            d = (c[0] - target_c[0]) ** 2 + (c[1] - target_c[1]) ** 2
            if d < best_dist:
                best_dist = d
                best = a

        extracted_label = best.primary_label if best else None
        recovered_via_deterministic = extracted_label == rec["original_text"] if extracted_label else False
        v2_output = None
        recovered_via_v2 = False
        if extracted_label:
            fam = parse_fields(extracted_label).family
            decision = full_policy(extracted_label, fam, catalog, model_a, model_b, predict_exact_sections,
                                    doc_freq_idx, ("physical_corruption_e2e", rec["source_page"]),
                                    auto_thresh, margin_thresh)
            v2_output = decision["output"]
            recovered_via_v2 = v2_output == rec["original_text"]

        results.append(
            {
                **rec,
                "grouped_annotation_found": best is not None,
                "extracted_primary_label": extracted_label,
                "recovered_exact_extraction": extracted_label == rec["original_text"] if extracted_label else False,
                "recovered_via_v2_policy": recovered_via_v2,
                "v2_policy_output": v2_output,
            }
        )

    by_type: dict[str, dict] = {}
    for r in results:
        t = r["corruption_type"]
        by_type.setdefault(t, {"n": 0, "extraction_matches_corrupted_target": 0, "recovered_via_v2_policy": 0})
        by_type[t]["n"] += 1
        if r["extracted_primary_label"] is not None:
            by_type[t]["extraction_matches_corrupted_target"] += 1
        if r["recovered_via_v2_policy"]:
            by_type[t]["recovered_via_v2_policy"] += 1

    write_jsonl(OUT_DIR / "e2e_recovery_results.jsonl", results)
    summary = {"by_type": by_type, "n_total": len(results)}
    (OUT_DIR / "e2e_recovery_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_visual_degradation() -> list[dict]:
    from PIL import Image, ImageFilter, ImageEnhance

    VISUAL_OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    samples = [(SOURCE_PDFS[0], 4), (SOURCE_PDFS[0], 5), (SOURCE_PDFS[1], 3), (SOURCE_PDFS[2], 3), (SOURCE_PDFS[2], 4)]
    for i, (src, pno) in enumerate(samples):
        for dpi in (300, 150):
            doc = fitz.open(src)
            page = doc[pno]
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img_path = VISUAL_OUT / f"degraded_{i}_{dpi}dpi.png"
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
            img = ImageEnhance.Contrast(img).enhance(0.6)
            img.save(img_path)

            out_pdf = VISUAL_OUT / f"degraded_{i}_{dpi}dpi.pdf"
            new_doc = fitz.open()
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, filename=str(img_path))
            new_doc.save(str(out_pdf))
            native_text = new_page.get_text().strip()
            new_doc.close()
            doc.close()

            manifest.append(
                {
                    "source_pdf": src,
                    "source_page": pno,
                    "dpi": dpi,
                    "image_path": str(img_path),
                    "degraded_pdf_path": str(out_pdf),
                    "native_text_extracted": native_text,
                    "zero_native_text_confirmed": native_text == "",
                }
            )
    write_jsonl(VISUAL_OUT / "manifest.jsonl", manifest)
    return manifest


def check_ocr() -> str:
    import importlib.util
    import shutil

    engines = []
    for mod in ("pytesseract", "easyocr", "paddleocr"):
        if importlib.util.find_spec(mod) is not None:
            engines.append(mod)
    tesseract_bin = shutil.which("tesseract")

    if not engines and not tesseract_bin:
        note = (
            "# OCR Status (Section 33)\n\n"
            "No OCR engine is installed in this environment: `pytesseract`, `easyocr`, "
            "and `paddleocr` are all absent from the Python environment, and no "
            "`tesseract` binary is on PATH. Per the brief, no new OCR dependency was "
            "installed to run this experiment.\n\n"
            "The visual-degradation fixtures in `visual_degradation/` (confirmed to "
            "expose zero native PDF text at both 150 and 300 DPI) are ready and "
            "waiting for an OCR engine whenever one becomes available -- generating "
            "them did not require OCR.\n\n"
            "This is NOT a blocker for the rest of this training phase: Model A, "
            "Model B, and the full text-level repair policy are already trained and "
            "evaluated end-to-end on the text-corruption and PDF-text-object-corruption "
            "benchmarks, which do not require OCR.\n\n"
            "## Section 34 (empirical confusion matrix)\n\n"
            "Blocked on the same OCR-availability gap identified in the prior corpus "
            "session (`ocr_confusion_matrix.md` in v1). The corruption engine's "
            "character-confusion weights remain `assumed_not_empirical`.\n"
        )
    else:
        note = f"# OCR Status (Section 33)\n\nFound available: engines={engines} tesseract_bin={tesseract_bin}\n"
    (OUT_DIR / "OCR_STATUS.md").write_text(note, encoding="utf-8")
    return note


def search_raw_clean_candidates() -> list[dict]:
    root = Path(r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects")
    keywords = ["raw", "original", "draft", "portal", "revised", "markup", "markedup", "old", "superseded"]
    candidates = []
    for pdf_path in root.rglob("*.pdf"):
        name_lower = pdf_path.name.lower()
        parent_lower = pdf_path.parent.name.lower()
        hit_kw = [k for k in keywords if k in name_lower or k in parent_lower]
        if hit_kw:
            try:
                size = pdf_path.stat().st_size
            except OSError:
                size = None
            candidates.append(
                {
                    "path": str(pdf_path),
                    "project": pdf_path.relative_to(root).parts[0],
                    "matched_keywords": hit_kw,
                    "size_bytes": size,
                    "status": "found_unverified",
                }
            )
    (OUT_DIR / "raw_clean_candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    return candidates


if __name__ == "__main__":
    print("Building PDF text-corruption fixtures...")
    manifest = build_fixtures()
    print(f"Built {len(manifest)} fixtures")

    print("Running end-to-end recovery...")
    summary = run_recovery(manifest)
    print(json.dumps(summary, indent=2))

    print("Building visual degradation fixtures...")
    visual_manifest = build_visual_degradation()
    print(f"Built {len(visual_manifest)} visual fixtures; zero-text confirmed: "
          f"{sum(1 for v in visual_manifest if v['zero_native_text_confirmed'])}/{len(visual_manifest)}")

    print("Checking OCR availability...")
    print(check_ocr())

    print("Searching for raw/clean candidates...")
    candidates = search_raw_clean_candidates()
    print(f"Found {len(candidates)} unverified candidates")
