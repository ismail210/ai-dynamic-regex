"""Generate the demo drawing_semantics.json fixture from a REAL pipeline run.

This is not invented data. It runs the actual `semantic_preprocessor`
pipeline (extraction -> grouping -> normalization -> completion) against a
real, already-registered project PDF (GCDC Building 4 - ST1,
document_id=doc_47dc7ef27f6e5d7e), so the demo UI has a reliable, precomputed
result to load instead of depending on live processing during a
stakeholder demo (see docs/upstream_semantic_preprocessor.md's "Demo Mode"
policy).

Two things in this fixture are worth being explicit about:

1. Drawing-language rules come from a REAL general note on page 5 of this
   drawing ("6. THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE
   FRAMING PLANS:" followed by `"W8" = W8x10` etc.) via a small, honestly
   scoped extractor below -- not hand-typed rule data. The exact quote and
   bbox for each rule are the real PDF line.

2. Exactly ONE annotation in this fixture is synthetic: a repair-case demo
   ("W8XI0"), injected because this is a clean, born-digital, vector-text
   PDF with no naturally occurring OCR-style corruption to demonstrate the
   repair path against (confirmed: the previous session's audit found zero
   scanned/garbled pages anywhere in this project's corpus). Its canonical
   output ("W8X10") is 100% real pipeline output against the real AISC
   catalog -- only the corrupted input string is injected, and it is
   flagged `"demo_synthetic": true` in its diagnostics so the UI can label
   it honestly and it is never confused with a real drawing annotation.

Usage:
    python backend/scripts/generate_demo_semantic_fixture.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.document_registry import document_source  # noqa: E402
from services.pdf_parser import extract_document_structure  # noqa: E402
from services.semantic_document_service import extract_abbreviation_note_rules  # noqa: E402
from services.semantic_preprocessor.extraction import build_text_primitives  # noqa: E402
from services.semantic_preprocessor.models import TextPrimitive  # noqa: E402
from services.semantic_preprocessor.pipeline import process_primitives  # noqa: E402
from services.semantic.serialization import to_dict  # noqa: E402

DOCUMENT_ID = "doc_47dc7ef27f6e5d7e"  # GCDC Building 4 - ST1


def inject_repair_demo_primitive(primitives: list[TextPrimitive]) -> None:
    """Add one clearly-flagged synthetic repair-case primitive.

    Placed in real empty margin space on page 5 (the same page as the real
    note and grouping examples, so the demo can stay on one page for that
    beat) rather than overlapping any real annotation.
    """
    primitives.append(TextPrimitive(
        primitive_id="demo_synth_repair_1",
        page=5,
        text="W8XI0",
        bbox=[80.0, 80.0, 140.0, 92.0],
        font_size=9.0,
        extraction_source="native_pdf",
    ))


def main() -> None:
    pdf_path = str(document_source(DOCUMENT_ID))
    print(f"Extracting: {pdf_path}")
    structure = extract_document_structure(pdf_path)
    primitives, page_classes = build_text_primitives(structure)
    print(f"Pages: {structure['page_count']}  Words: {len(structure['words'])}  Primitives: {len(primitives)}")

    rules = extract_abbreviation_note_rules(structure)
    print(f"Real drawing-language rules extracted: {len(rules)}")
    for r in rules:
        print(f"  {r['trigger']} -> {r['result']} (page {r['source_evidence'][0]['page']})")

    inject_repair_demo_primitive(primitives)

    document = process_primitives(
        primitives,
        document_id=DOCUMENT_ID,
        drawing_language_rules=rules,
    )
    # Mark the synthetic annotation's diagnostics explicitly so the UI can
    # never present it as a real drawing finding.
    for ann in document.annotations:
        if "demo_synth_repair_1" in ann.source_fragment_ids:
            ann.correction.reason_codes = list(ann.correction.reason_codes) + ["demo_synthetic_case"]

    payload = to_dict(document)
    payload["diagnostics"]["page_classes"] = {str(k): v for k, v in page_classes.items()}
    payload["diagnostics"]["demo_fixture"] = {
        "source_pdf": pdf_path,
        "generated_by": "backend/scripts/generate_demo_semantic_fixture.py",
        "note": (
            "All annotations are real pipeline output against the real GCDC "
            "Building 4 - ST1 drawing, except one clearly flagged synthetic "
            "repair-case primitive (see reason_codes containing "
            "'demo_synthetic_case')."
        ),
    }

    print(f"Annotations: {len(document.annotations)}")
    print(f"Metrics: {document.metrics}")

    from services.artifact_store import write_artifact
    path = write_artifact(DOCUMENT_ID, "semantic.json", payload)
    print(f"Wrote fixture via artifact store: {path}")


if __name__ == "__main__":
    main()
