#!/usr/bin/env python3
"""Quick validation metrics for ST.pdf extraction quality."""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.extraction_engine import EXTRACTION_VERSION, extract_engineering_document  # noqa: E402


def main() -> int:
    pdf = BACKEND / "uploads" / "ST__0bfc2d61245d.pdf"
    if not pdf.exists():
        print(f"Missing PDF: {pdf}")
        return 1

    started = time.perf_counter()
    document = extract_engineering_document(pdf, document_id="doc_validation")
    elapsed = time.perf_counter() - started

    tokens = document.get("engineering_tokens") or []
    anonymous = [
        t for t in tokens if t.get("engineering_object_type") == "anonymous_dimension"
    ]
    noise = [
        t
        for t in tokens
        if str(t.get("normalized_text") or t.get("text") or "")
        in ('4"', "6\"", '8"', '3/64"')
    ]
    repeat_labels = Counter(
        str(t.get("normalized_text") or t.get("text") or "").upper()
        for t in tokens
        if t.get("engineering_object_type")
        in {"steel_section", "column", "column_or_brace", "brace", "beam"}
    )

    print(f"extraction_version={EXTRACTION_VERSION}")
    print(f"elapsed_s={elapsed:.2f}")
    print(f"engineering_objects={len(tokens)}")
    print(f"anonymous_dimension={len(anonymous)}")
    print(f"layout_noise_left={len(noise)}")
    print(f"discard_breakdown={document.get('extraction_discard_counts')}")
    print(f"top_repeated_labels={repeat_labels.most_common(10)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
