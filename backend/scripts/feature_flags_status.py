"""Activation playbook: print ML experimental flag + spatial_index status.

Run from backend/:
  ./venv/bin/python scripts/feature_flags_status.py

Does not enable anything. Use this to confirm defaults before flipping env
vars for shadow logging or association dataset work.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402


def _flag(name: str, enabled: bool, effect: str, default: str = "false") -> dict:
    return {
        "env": name,
        "default": default,
        "current": enabled,
        "effect": effect,
    }


def status() -> dict:
    shadow_log = settings.ml_label_ranker_shadow_log_path
    return {
        "playbook": [
            "1. Defaults stay OFF — analyze predictions unchanged.",
            "2. Shadow only: set ML_LABEL_RANKER_SHADOW=true, restart API, "
            "run analyze; disagreements append to the shadow JSONL. "
            "Section labels do not change.",
            "3. Review with scripts/compare_label_ranker_shadow.py and the "
            f"log at {shadow_log}.",
            "4. Promote ordering only after measured wins: "
            "ML_LABEL_RANKER_ENABLED=true (changes analyze section when the "
            "learned ranker supplies a catalog-valid pick).",
            "5. ML_ASSOCIATION_DATASET_ENABLED unlocks association dataset "
            "scripts/exports only — never live section choice.",
            "6. spatial_index.py stays experimental: used by association "
            "dataset builders / coverage reports, not live graph_builder or "
            "analyze.",
        ],
        "flags": [
            _flag(
                "ML_LABEL_RANKER_SHADOW",
                settings.ml_label_ranker_shadow,
                "Analyze calls label_ranker_hook → reconstruct; logs "
                "deterministic vs ML vs live section; does NOT change "
                "predictions when ENABLED is false.",
            ),
            _flag(
                "ML_LABEL_RANKER_ENABLED",
                settings.ml_label_ranker_enabled,
                "When true, analyze may replace section with the learned "
                "ranker top pick (catalog-valid candidates only).",
            ),
            _flag(
                "ML_ASSOCIATION_DATASET_ENABLED",
                settings.ml_association_dataset_enabled,
                "Gates ml_association dataset build / review export-import. "
                "Not wired into live prediction.",
            ),
            _flag(
                "LEARNED_FUSION_ENABLED",
                settings.learned_fusion_enabled,
                "Gates multimodal_fusion.pt override in live ranking.",
                default="true",
            ),
        ],
        "paths": {
            "shadow_log": str(shadow_log),
            "ml_association_dir": str(settings.ml_association_dir),
            "ml_association_outcomes": str(settings.ml_association_outcomes_path),
        },
        "spatial_index": {
            "module": "services.engineering.spatial_index",
            "status": "experimental",
            "wired_into_live_analyze": False,
            "wired_into_graph_builder": False,
            "used_by": [
                "services.ml_association.candidate_dataset",
                "backend/tests/test_spatial_index.py",
            ],
            "note": (
                "STRtree spatially-complete candidates for R&D / association "
                "datasets. Isolation tests forbid importing it from "
                "orchestrator or multimodal pipeline."
            ),
        },
        "wiring": {
            "label_ranker_analyze_entry": (
                "services.prediction.label_ranker_hook.apply_label_ranker_for_analyze"
            ),
            "called_from": "services.prediction.orchestrator.predict_from_context",
            "isolation": (
                "orchestrator must not mention label_reconstruction in source; "
                "hook is the bridge."
            ),
        },
    }


def main() -> int:
    print(json.dumps(status(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
