"""Grouping dataset + deterministic-grouping descriptive benchmark (Section 24).

Positive pairs: fragment pairs from the SAME real mined annotation (i.e. the
deterministic grouping already merged them -- this measures what the
current rules actually do, not an independent ground truth).
Hard negatives: the last fragment of one annotation paired with the first
fragment of the next annotation on the same page (spatially adjacent,
belong to DIFFERENT semantic annotations).

IMPORTANT LIMITATION (documented, not hidden): this is a DESCRIPTIVE
benchmark of the deterministic grouper's own behavior, not a precision/
recall measurement against independent human-verified ground truth --
that requires the human inspection pass (Section 35), which this pilot
does not yet include at scale. Numbers reported here should be read as
"what the current rules did on real data", not "how often the rules are
right".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.corpus.common import read_jsonl, write_json, write_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    out_dir: Path = args.output
    mined = list(read_jsonl(out_dir / "clean" / "mined_annotations.jsonl"))

    by_page: dict[tuple, list[dict]] = {}
    for a in mined:
        key = (a["project_id"], a["document_sha256"], a["page"])
        by_page.setdefault(key, []).append(a)

    positive_rows = []
    negative_rows = []
    reason_counts: dict[str, int] = {}

    for key, annotations in by_page.items():
        for a in annotations:
            fragments = a.get("source_fragments", [])
            if len(fragments) > 1:
                for i in range(len(fragments) - 1):
                    positive_rows.append({
                        "project_id": a["project_id"],
                        "document_sha256": a["document_sha256"],
                        "page": a["page"],
                        "annotation_id": a["annotation_id"],
                        "fragment_a": fragments[i],
                        "fragment_b": fragments[i + 1],
                        "label": "same_annotation",
                        "grouping_reasons": a["grouping_reasons"],
                    })
                    for reason in a["grouping_reasons"]:
                        reason_counts[reason] = reason_counts.get(reason, 0) + 1

        # Hard negatives: sort annotations left-to-right/top-to-bottom by
        # anchor and pair adjacent DIFFERENT annotations' boundary fragments.
        with_anchor = [a for a in annotations if a.get("original_anchor")]
        with_anchor.sort(key=lambda a: (round(a["original_anchor"][1], 1), a["original_anchor"][0]))
        for i in range(len(with_anchor) - 1):
            a, b = with_anchor[i], with_anchor[i + 1]
            if a["annotation_id"] == b["annotation_id"]:
                continue
            frag_a = (a.get("source_fragments") or [{"text": a["original_text"], "bbox": a["semantic_bbox"]}])[-1]
            frag_b = (b.get("source_fragments") or [{"text": b["original_text"], "bbox": b["semantic_bbox"]}])[0]
            negative_rows.append({
                "project_id": a["project_id"],
                "document_sha256": a["document_sha256"],
                "page": a["page"],
                "annotation_id_a": a["annotation_id"],
                "annotation_id_b": b["annotation_id"],
                "fragment_a": frag_a,
                "fragment_b": frag_b,
                "label": "different_annotation",
            })

    write_jsonl(out_dir / "synthetic" / "grouping_examples.jsonl", positive_rows + negative_rows)

    summary = {
        "positive_pairs": len(positive_rows),
        "hard_negative_pairs": len(negative_rows),
        "positive_reason_counts": reason_counts,
        "pages_considered": len(by_page),
        "limitation": (
            "Descriptive only -- positives/negatives both come from the same "
            "deterministic grouper's own output and page ordering, not "
            "independent human-verified ground truth. See Section 35 (human "
            "inspection tool) for the real validation step, not run at scale "
            "in this pilot."
        ),
    }
    write_json(out_dir / "inventory" / "grouping_summary.json", summary)
    import json
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
