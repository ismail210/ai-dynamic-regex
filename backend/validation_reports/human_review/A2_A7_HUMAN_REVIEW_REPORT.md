# Human Review — A2 + A7

_Generated: 2026-09-13T11:54:32.458796+00:00_

## A2 — Extraction / Grouping / Semantic Review

- source dataset: `training/eval_cache_backups/accuracy_gold/a2_human_review_70.json`
- total rows = 70
- reviewed = 0
- remaining = 70
- coverage = 0.0000
- extraction = {'yes_rate': 'N/A — no reviewed samples', 'no_rate': 'N/A — no reviewed samples', 'ambiguous_rate': 'N/A — no reviewed samples', 'n': 0}
- grouping = {'yes_rate': 'N/A — no reviewed samples', 'no_rate': 'N/A — no reviewed samples', 'ambiguous_rate': 'N/A — no reviewed samples', 'n_applicable': 0, 'n_not_applicable': 0}
- operation = {'yes_rate': 'N/A — no reviewed samples', 'no_rate': 'N/A — no reviewed samples', 'ambiguous_rate': 'N/A — no reviewed samples', 'n': 0}
- normalization = {'correct': 'N/A — no reviewed samples', 'incorrect': 'N/A — no reviewed samples', 'ambiguous': 'N/A — no reviewed samples', 'n': 0}
- abstention = {'correct_abstention_count': 'N/A — no reviewed samples', 'unsafe_completion_count': 'N/A — no reviewed samples', 'missed_abstention_count': 'N/A — no reviewed samples', 'ambiguous_abstention_count': 'N/A — no reviewed samples'}
- safety = {'l4x4_thickness_invention': 'N/A — no reviewed samples', 'l5x3_thickness_invention': 'N/A — no reviewed samples', 'l_to_2l_invention': 'N/A — no reviewed samples', 'catalog_only_completion': 'N/A — no reviewed samples', 'excel_driven_completion': 'N/A — no reviewed samples', 'observed_cases': []}
- note: Human review is ready; accuracy/precision is not yet measured.

## A7 — Geometry Association Review

- source dataset: `training/eval_cache_backups/accuracy_gold/a7_human_review_100.json`
- total links = 100
- reviewed = 0
- remaining = 100
- correct = N/A — no reviewed samples
- wrong = N/A — no reviewed samples
- ambiguous = N/A — no reviewed samples
- overall CORRECT/reviewed = N/A — no reviewed samples
- precision excluding ambiguous = N/A — no reviewed samples
- breakdown by method = {'leader_tip_to_stroke': {'n_reviewed': 0, 'correct': 0, 'wrong': 0, 'ambiguous': 0, 'precision_excluding_ambiguous': 'N/A — no reviewed samples'}, 'proximity_stroke': {'n_reviewed': 0, 'correct': 0, 'wrong': 0, 'ambiguous': 0, 'precision_excluding_ambiguous': 'N/A — no reviewed samples'}, 'ambiguous_members': {'n_reviewed': 0, 'correct': 0, 'wrong': 0, 'ambiguous': 0, 'precision_excluding_ambiguous': 'N/A — no reviewed samples'}}
- note: Human review is ready; accuracy/precision is not yet measured.

## Observed Failure Modes

None observed yet — no human judgments entered.

## Safety Findings

From human-reviewed A2 rows only:
- unsafe L thickness completion: N/A — no reviewed samples (L4X4), N/A — no reviewed samples (L5X3)
- L -> 2L invention: N/A — no reviewed samples
- catalog-only completion: N/A — no reviewed samples
- Excel-as-predictor: N/A — no reviewed samples
- geometry treated as takeoff truth: not scored here (A7 judges association only)

## Recommended Next Step

Next implementation target should be selected from the measured highest-impact failure mode after human review.
