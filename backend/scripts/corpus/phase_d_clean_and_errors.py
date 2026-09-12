"""Phase D-adjacent: build the high-confidence clean seed corpus (Section 8)
and mine real suspected corruptions (Section 10) from the Phase B/C mining
output.

Clean seed admission requirements (all must hold):
  - native PDF text (this corpus has no OCR path -- see native_text_health report)
  - structural grammar parses successfully (is_structural)
  - family is known
  - catalog-exact match succeeds
  - operation == "none" (no unresolved repair/completion)
  - grammar != "incomplete" (no shorthand)

Real suspected corruptions: annotations already flagged AMBIGUOUS or
POTENTIAL_REPAIR by the deterministic classifier, PLUS a supplementary
regex sweep over the raw mined text for patterns that look like OCR/extraction
noise near a structural label but didn't parse as one at all (so Phase C's
classifier never saw them, since it drops true NONSTRUCTURAL text).
Everything here is status=unverified_real_error -- never auto-promoted to
ground truth.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402

# A "near-miss" pattern: looks like it's trying to be a family+depth+X+number
# structural label, but contains a character our grammar rejects in a
# position a digit/letter confusion would produce (I/l/O/S/B/Z/G mixed with
# digits) -- exactly the OCR-confusion shape Section 10 asks about.
_NEAR_MISS_RE = re.compile(
    r"^(?P<family>W|M|S|HP|C|MC|L|HSS)\s*\d*[IlOSBZGilobszg]+\d*.*X.*$",
    re.IGNORECASE,
)
_SPLIT_FRACTION_RE = re.compile(r"^\d+\s*[/\\]\s*[A-Za-z]$")  # e.g. "3/B"


def looks_like_near_miss(text: str) -> str | None:
    candidate = text.strip().upper()
    if _NEAR_MISS_RE.match(candidate):
        return "family_prefix_with_letter_digit_confusion"
    if _SPLIT_FRACTION_RE.match(candidate):
        return "fraction_denominator_letter_confusion"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    out_dir: Path = args.output
    mined_path = out_dir / "clean" / "mined_annotations.jsonl"
    annotations = list(read_jsonl(mined_path))

    clean_seed = []
    for a in annotations:
        if (
            a["category"] == "CLEAN_EXACT"
            and a["family"]
            and a["catalog_exact_match"]
            and a["operation"] == "none"
            and a["grammar"] != "incomplete"
        ):
            clean_seed.append({
                "seed_id": f"seed_{a['document_sha256'][:12]}_{a['annotation_id']}",
                "project_id": a["project_id"],
                "document_sha256": a["document_sha256"],
                "relative_path": a["relative_path"],
                "page": a["page"],
                "annotation_id": a["annotation_id"],
                "original_text": a["original_text"],
                "canonical_text": a["canonical_text"],
                "family": a["family"],
                "grammar": a["grammar"],
                "fields": a["fields"],
                "semantic_bbox": a["semantic_bbox"],
                "original_anchor": a["original_anchor"],
                "original_axis": a["original_axis"],
                "source_fragments": a["source_fragments"],
                "modifiers": a["modifiers"],
            })

    write_jsonl(out_dir / "clean" / "annotations.jsonl", clean_seed)

    real_errors = []
    for a in annotations:
        if a["category"] in ("AMBIGUOUS", "POTENTIAL_REPAIR"):
            real_errors.append({
                "project_id": a["project_id"],
                "document_sha256": a["document_sha256"],
                "relative_path": a["relative_path"],
                "page": a["page"],
                "annotation_id": a["annotation_id"],
                "original_text": a["original_text"],
                "category": a["category"],
                "family": a["family"],
                "reason": "deterministic_classifier_flagged",
                "status": "unverified_real_error",
            })

    # Supplementary regex sweep over ALL mined text (including ones the
    # classifier already dropped as NONSTRUCTURAL, which happens upstream --
    # re-scan raw fragment text still present on each surviving annotation's
    # source_fragments, since a near-miss token may have been absorbed as a
    # fragment of something else or logged only at fragment level).
    seen_texts = set()
    for a in annotations:
        for frag in a.get("source_fragments", []):
            text = frag.get("text", "")
            if text in seen_texts:
                continue
            reason = looks_like_near_miss(text)
            if reason:
                seen_texts.add(text)
                real_errors.append({
                    "project_id": a["project_id"],
                    "document_sha256": a["document_sha256"],
                    "relative_path": a["relative_path"],
                    "page": a["page"],
                    "annotation_id": a["annotation_id"],
                    "original_text": text,
                    "category": "REGEX_NEAR_MISS",
                    "family": None,
                    "reason": reason,
                    "status": "unverified_real_error",
                })

    write_jsonl(out_dir / "real_errors" / "suspected_corruptions.jsonl", real_errors)

    summary = {
        "clean_seed_count": len(clean_seed),
        "clean_seed_unique_designations": len({c["canonical_text"] for c in clean_seed}),
        "clean_seed_family_counts": _counts(clean_seed, "family"),
        "clean_seed_project_counts": _counts(clean_seed, "project_id"),
        "real_suspected_corruption_count": len(real_errors),
        "real_suspected_by_category": _counts(real_errors, "category"),
    }
    write_json(out_dir / "inventory" / "clean_and_errors_summary.json", summary)
    import json
    print(json.dumps(summary, indent=2))


def _counts(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for r in rows:
        v = r.get(key)
        out[v] = out.get(v, 0) + 1
    return out


if __name__ == "__main__":
    main()
