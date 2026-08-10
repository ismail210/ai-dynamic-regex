"""Phase B2 helper: compare damaged-label shadow ranker vs deterministic order.

Usage (from backend/):
  ML_LABEL_RANKER_SHADOW=true \\
  ./venv/bin/python scripts/compare_label_ranker_shadow.py "W18X3?" "W12X2O"

Analyze traffic also logs via services.prediction.label_ranker_hook when
ML_LABEL_RANKER_SHADOW=true (section unchanged). Enable live ordering only
after this (or evaluate_label_ranker.py) shows a clear win:
  ML_LABEL_RANKER_ENABLED=true
Keep ML_LABEL_RANKER_ENABLED=false by default.

See also: scripts/feature_flags_status.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from services.label_reconstruction.candidates import generate_candidates  # noqa: E402
from services.label_reconstruction.shadow import reconstruct  # noqa: E402


def main(argv: list[str]) -> int:
    queries = argv[1:] or ["W18X3?", "W12X2O", "HSS6X6X1/?"]
    print(
        json.dumps(
            {
                "ml_label_ranker_enabled": settings.ml_label_ranker_enabled,
                "ml_label_ranker_shadow": settings.ml_label_ranker_shadow,
                "note": (
                    "Set ML_LABEL_RANKER_SHADOW=true to log ranker disagreements. "
                    "Set ML_LABEL_RANKER_ENABLED=true only after shadow wins on gold."
                ),
            },
            indent=2,
        )
    )
    for query in queries:
        deterministic = generate_candidates(query)
        result = reconstruct(query)
        payload = {
            "query": query,
            "deterministic_top": (
                deterministic.candidates[0] if deterministic.candidates else None
            ),
            "selected_prediction": result.selected_prediction,
            "reason": result.reason,
            "shadow": result.shadow,
            "prediction_changed": (
                result.selected_prediction
                != (
                    deterministic.candidates[0]
                    if deterministic.candidates
                    else None
                )
            ),
        }
        print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
