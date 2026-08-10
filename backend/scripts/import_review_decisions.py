"""Batch-import downloaded review-kit decision files into the outcome store.

Companion to ``build_ml_association_review_kit.py``: each group's HTML
review page (see that script) produces one ``<group_id>.decision.json``
file per "Save decision" click, matching
``services.ml_association.schemas.ReviewImportEntry``. This script reads
every ``*.decision.json`` file in a local input directory, validates each
one against the matching group export in
``training/ml_association/real_project_pilot/exports/`` (the same JSON
metadata the review kit was built from), and appends every valid outcome
through the normal ``service.submit_review`` -> ``outcome_store``
pipeline. Nothing is uploaded or transmitted anywhere; this is a local
file-to-file operation, matching the pilot phase's "work locally only"
guardrail.

Requires ``ML_ASSOCIATION_DATASET_ENABLED=true`` in the environment
(same feature flag as every other ``service.py`` entry point) --
refuses to run otherwise, by design (see ``service.require_enabled``).

``known_page_geometry_ids`` is intentionally NOT supplied here: no
full-page geometry-id index is built anywhere in this phase (only each
group's own top-K candidate set), so a ``candidate_generation_miss=true``
correction is accepted at face value rather than cross-checked against
the complete page geometry. This is a documented limitation, not an
oversight -- see docs/ml_association_phase/human_review_protocol.md.

Usage:
    ML_ASSOCIATION_DATASET_ENABLED=true python scripts/import_review_decisions.py \\
        --decisions-dir <folder of downloaded *.decision.json files> \\
        [--exports-dir training/ml_association/real_project_pilot/exports] \\
        [--outcomes-path training/ml_association/real_project_pilot/working_notes/outcomes.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ml_association import service  # noqa: E402
from services.ml_association.schemas import LabelGroup, ReviewExportPayload  # noqa: E402

DEFAULT_EXPORTS_DIR = (
    Path(__file__).resolve().parents[1] / "training" / "ml_association" / "real_project_pilot" / "exports"
)
DEFAULT_OUTCOMES_PATH = (
    Path(__file__).resolve().parents[1]
    / "training"
    / "ml_association"
    / "real_project_pilot"
    / "working_notes"
    / "outcomes.jsonl"
)


def _load_group(group_id: str, exports_dir: Path) -> LabelGroup:
    export_path = exports_dir / f"{group_id}.json"
    if not export_path.exists():
        raise FileNotFoundError(
            f"no export found for group_id={group_id!r} at {export_path} "
            "-- was this decision file downloaded from a different review kit build?"
        )
    payload = ReviewExportPayload.model_validate_json(export_path.read_text(encoding="utf-8"))
    return payload.group


def import_all(decisions_dir: Path, exports_dir: Path, outcomes_path: Path) -> Dict[str, List[str]]:
    accepted: List[str] = []
    rejected: List[str] = []

    decision_files = sorted(decisions_dir.glob("*.decision.json"))
    if not decision_files:
        print(f"No *.decision.json files found in {decisions_dir}", file=sys.stderr)

    for decision_file in decision_files:
        raw = json.loads(decision_file.read_text(encoding="utf-8"))
        group_id = raw.get("group_id", "")
        try:
            group = _load_group(group_id, exports_dir)
        except FileNotFoundError as exc:
            print(f"[SKIP] {decision_file.name}: {exc}", file=sys.stderr)
            rejected.append(decision_file.name)
            continue

        result = service.submit_review(raw, group, outcomes_path=outcomes_path)
        if result.valid:
            accepted.append(decision_file.name)
            print(f"[OK]   {decision_file.name} -> outcome {result.outcome.outcome_id}")
        else:
            rejected.append(decision_file.name)
            reasons = "; ".join(f"{e.code}: {e.message}" for e in result.errors)
            print(f"[FAIL] {decision_file.name}: {reasons}", file=sys.stderr)

    return {"accepted": accepted, "rejected": rejected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions-dir", required=True, type=Path)
    parser.add_argument("--exports-dir", type=Path, default=DEFAULT_EXPORTS_DIR)
    parser.add_argument("--outcomes-path", type=Path, default=DEFAULT_OUTCOMES_PATH)
    args = parser.parse_args()

    if not service.is_enabled():
        print(
            "ML_ASSOCIATION_DATASET_ENABLED is not set -- refusing to run. "
            "Set it to 'true' in the environment and re-run.",
            file=sys.stderr,
        )
        return 2

    summary = import_all(args.decisions_dir, args.exports_dir, args.outcomes_path)
    print(
        f"\n{len(summary['accepted'])} accepted, {len(summary['rejected'])} rejected "
        f"(outcomes written to {args.outcomes_path})"
    )
    return 0 if not summary["rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
