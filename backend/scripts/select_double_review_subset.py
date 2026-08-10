"""Deterministically select the double-review stratified subset (Phase 2.6).

Reads the 108-group batch audit rows (produced during Step 2's batch
distribution audit, `training/ml_association/real_project_pilot/working_notes/
batch_audit_rows.json` -- git-ignored, contains per-group metadata but no
drawing content) and selects a stratified subset that two independent
reviewers must both review, so inter-rater agreement can be measured.

Selection is a pure, deterministic function of the row data: no
`random` module, no wall-clock input. Re-running this script against
the same `batch_audit_rows.json` always produces the same subset.

Prioritization (per the Phase 2.6 spec's instruction to prioritize
leader / repeated / multi-adjacent / cross-detail / multi-target /
candidate-miss / no-valid-target cases for double review):

- `has_leader_evidence=True` rows are prioritized -- this is the
  category behind the pilot's headline 28.8% leader-mis-selection
  finding (real_project_pilot_results.md), so agreement specifically on
  leader-involving groups is the single most decision-relevant number
  this phase can produce.
- Rows belonging to a repeated (project, page, label_raw_text) triple
  (the same label text appearing more than once on the same page) are
  prioritized -- these are exactly the cases annotation_guidelines.md
  flags as having an open scope-boundary question (`repeated` vs.
  independent instances).
- Rows whose `page_type` is one of the difficulty-selected categories
  ("leaders or arrows", "repeated steel labels", "no valid geometry
  target likely", "several adjacent candidate members", "incomplete or
  damaged labels") are prioritized, since these page types were
  specifically chosen during pilot selection to stress-test the harder
  parts of the pipeline (real_project_pilot_manifest.json).
- "cross-detail" contamination is NOT used as a selection signal here:
  no region/detail-segmentation layer exists anywhere in this
  repository (`region_id` is `None` on every row -- see
  `annotation_guidelines.md`'s "Cross-detail / cross-region mistakes"
  section), so there is no data field to stratify on. This is a known,
  documented gap, not an oversight.
- "multi-target" and "candidate-miss" outcomes cannot be used as
  selection signals either -- they are properties of a REVIEW DECISION,
  which does not exist yet before any review has happened. Using
  `page_type == "no valid geometry target likely"` as the closest
  available a priori proxy for likely no-valid-target/candidate-miss
  outcomes is the best this script can do without fabricating outcome
  data ahead of time.

Priority score and tie-breaking are both fully deterministic (an
integer sum of boolean signals, tie-broken by a SHA-1 hash of the
group_id -- the same determinism discipline used throughout this
phase's identifiers.py), so this script never depends on dict/set
iteration order or process-specific randomness.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

ROWS_PATH = (
    Path(__file__).resolve().parents[1]
    / "training"
    / "ml_association"
    / "real_project_pilot"
    / "working_notes"
    / "batch_audit_rows.json"
)

OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "training"
    / "ml_association"
    / "real_project_pilot"
    / "working_notes"
    / "double_review_subset.json"
)

_PRIORITY_PAGE_TYPES = {
    "leaders or arrows",
    "repeated steel labels",
    "no valid geometry target likely",
    "several adjacent candidate members",
    "incomplete or damaged labels",
}

# Minimum groups guaranteed from each project and each page_type, so the
# subset is never accidentally empty for any stratum even after
# priority-ranked selection.
MIN_PER_PROJECT = 2
MIN_PER_PAGE_TYPE = 2

# Target fraction of the 108-group batch. The spec asks for "20-25%+";
# 0.26 with per-stratum floors typically lands the realized fraction at
# or slightly above 25% once floors are backfilled.
TARGET_FRACTION = 0.26


def _tie_break_key(group_id: str) -> str:
    return hashlib.sha1(f"double_review|{group_id}".encode("utf-8")).hexdigest()


def _priority_score(row: Dict[str, Any], repeated_combo_ids: set) -> int:
    score = 0
    if row["has_leader_evidence"]:
        score += 2
    if row["group_id"] in repeated_combo_ids:
        score += 2
    if row["page_type"] in _PRIORITY_PAGE_TYPES:
        score += 1
    if row["candidate_count"] <= 3:
        score += 1
    return score


def select_subset(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    from collections import Counter

    combo_counts = Counter((r["project_id"], r["page_number"], r["label_raw_text"]) for r in rows)
    repeated_combo_ids = {
        r["group_id"]
        for r in rows
        if combo_counts[(r["project_id"], r["page_number"], r["label_raw_text"])] > 1
    }

    ranked = sorted(
        rows,
        key=lambda r: (-_priority_score(r, repeated_combo_ids), _tie_break_key(r["group_id"])),
    )

    target_count = max(1, round(len(rows) * TARGET_FRACTION))
    selected_ids = {r["group_id"] for r in ranked[:target_count]}

    # Backfill: guarantee minimum per-project and per-page_type coverage,
    # walking the same deterministic priority order so any additions are
    # still reproducible, not arbitrary.
    def _backfill(key_fn, minimum: int) -> None:
        by_key: Dict[Any, List[Dict[str, Any]]] = {}
        for row in ranked:
            by_key.setdefault(key_fn(row), []).append(row)
        for key, key_rows in by_key.items():
            have = sum(1 for r in key_rows if r["group_id"] in selected_ids)
            if have >= minimum:
                continue
            for row in key_rows:
                if row["group_id"] in selected_ids:
                    continue
                selected_ids.add(row["group_id"])
                have += 1
                if have >= minimum:
                    break

    _backfill(lambda r: r["project_id"], MIN_PER_PROJECT)
    _backfill(lambda r: r["page_type"], MIN_PER_PAGE_TYPE)

    selected_rows = [r for r in ranked if r["group_id"] in selected_ids]
    selected_rows.sort(key=lambda r: r["group_id"])  # stable, deterministic final order

    from collections import Counter as _Counter

    summary = {
        "total_batch_size": len(rows),
        "selected_count": len(selected_rows),
        "selected_fraction_percent": round(100.0 * len(selected_rows) / len(rows), 1),
        "by_project": dict(sorted(_Counter(r["project_id"] for r in selected_rows).items())),
        "by_page_type": dict(sorted(_Counter(r["page_type"] for r in selected_rows).items())),
        "leader_evidence_count": sum(1 for r in selected_rows if r["has_leader_evidence"]),
        "repeated_combo_count": sum(1 for r in selected_rows if r["group_id"] in repeated_combo_ids),
    }

    return {
        "selection_rule_version": "1.0",
        "summary": summary,
        "groups": [
            {
                "group_id": r["group_id"],
                "pilot_id": r["pilot_id"],
                "project_id": r["project_id"],
                "page_number": r["page_number"],
                "label_raw_text": r["label_raw_text"],
                "page_type": r["page_type"],
                "candidate_count": r["candidate_count"],
                "has_leader_evidence": r["has_leader_evidence"],
                "is_repeated_combo": r["group_id"] in repeated_combo_ids,
            }
            for r in selected_rows
        ],
    }


def main() -> int:
    rows = json.loads(ROWS_PATH.read_text(encoding="utf-8"))
    result = select_subset(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print(f"\nWrote {result['summary']['selected_count']} group IDs to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
