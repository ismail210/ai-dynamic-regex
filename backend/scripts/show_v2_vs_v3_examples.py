"""Part 11: explicit v2 vs v3 output for the six spec example queries.

Run from ``backend/`` AFTER v3 is trained:
``python scripts/show_v2_vs_v3_examples.py <v3_version_id>``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.label_reconstruction.candidates import (  # noqa: E402
    generate_candidates,
    generate_candidates_v3,
)
from services.label_reconstruction.ranker import load_ranker_version  # noqa: E402
from services.structural_parser import (  # noqa: E402
    ambiguity_category,
    compatible_catalog_labels,
)

V2_RANKER_VERSION_ID = "label_reconstruction_20260807_130015"
EXAMPLES = ["W18X3?", "W18X**", "W1BX3S", "W44X3**", "HSS8X8X?", "C1?X20"]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/show_v2_vs_v3_examples.py <v3_version_id>")
        return 1
    v2_ranker = load_ranker_version(V2_RANKER_VERSION_ID)
    v3_ranker = load_ranker_version(sys.argv[1])

    report = []
    for text in EXAMPLES:
        compat = compatible_catalog_labels(text)
        ambiguity = ambiguity_category(len(compat))

        det = generate_candidates(text, limit=5)
        v3_det = generate_candidates_v3(text, limit=8)

        v2_learned_top5 = None
        if v2_ranker and det.candidates:
            # RAW text, not det.normalized -- both rankers were trained on
            # raw_corrupted query text (see analyze_frozen_test_rows.py's
            # comment / paired_compare_rankers.py's comment for why).
            v2_learned_top5 = v2_ranker.rank(
                text, det.candidates, generation_reasons=det.generation_reasons
            )[:5]

        v3_learned_top5 = None
        if v3_ranker and v3_det.candidates:
            v3_learned_top5 = v3_ranker.rank(
                text,
                v3_det.candidates,
                generation_reasons=v3_det.generation_reasons,
                fuzzy_ranks=v3_det.fuzzy_ranks,
            )[:5]

        entry = {
            "query": text,
            "compatible_catalog_count": len(compat),
            "ambiguity_category": ambiguity,
            "uniquely_identifiable_from_text_alone": ambiguity == "UNIQUE",
            "deterministic_v2_top5": det.candidates,
            "deterministic_v3_top5": v3_det.candidates[:5],
            "learned_v2_top5": v2_learned_top5,
            "learned_v3_top5": v3_learned_top5,
        }
        report.append(entry)
        print(f"\n--- {text!r} ---")
        print(f"  compatible_catalog_count={len(compat)}  category={ambiguity}")
        print(f"  deterministic v2 top5: {det.candidates}")
        print(f"  deterministic v3 top5: {v3_det.candidates[:5]}")
        print(f"  learned v2 top5:       {v2_learned_top5}")
        print(f"  learned v3 top5:       {v3_learned_top5}")

    out_path = (
        Path(__file__).resolve().parents[1]
        / "training"
        / "datasets"
        / "label_reconstruction"
        / "v2_vs_v3_examples.json"
    )
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
