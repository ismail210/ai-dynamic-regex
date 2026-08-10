# Real-Project Annotation Status (Phase 2.5)

## What was built

A prioritized human-review batch of **108 label groups** across all 11 processed real pilot pages (10 groups exported per page, except `pilot_12` which only had 8 total groups on that page). Each group has a matching JSON metadata file and SVG visual export in the git-ignored `backend/training/ml_association/real_project_pilot/exports/{pilot_id}/run1/` directory. A reviewer index (`working_notes/review_index.json`, ignored) links every group to its page, label text, candidate count, leader-evidence flag, and current-heuristic selection.

**Selection was difficulty-prioritized, not random**, per the pilot spec: for each page, groups were ranked (1) ambiguous groups (2+ real candidates) or groups with leader evidence first, (2) sparse groups (0-1 candidates) second, (3) straightforward groups last, then the top 10 per page were exported. Because every one of the 11 real pages had at least 10 ambiguous/leader-evidence groups available, **all 108 exported groups have 2 or more real candidates, and 64/108 (59.3%) have leader evidence** — the batch is intentionally weighted toward the hard cases the pilot spec asked to prioritize (adjacent parallel members, leader-supported callouts, repeated labels), not a representative random sample of "typical" difficulty.

## Review status: **no groups have been reviewed**

Every one of the 108 groups' `review_status` is `"unreviewed"`. **No reviewed outcomes were created or written to the outcome store during this pilot.** This is intentional, per the pilot spec's explicit instruction: *"Do not fabricate the reviewed decisions yourself unless the relationship is completely unambiguous"* and *"For ambiguous structural interpretation, leave the group unreviewed."*

In practice, essentially every group in this batch involves genuine structural-drawing interpretation (which of several parallel members a label refers to, whether a leader-resolved candidate or the leader itself is correct, whether a repeated designation's several instances are all valid targets) that requires either a licensed structural-domain reviewer looking at the actual sheet, or at minimum domain knowledge this pilot does not have and should not simulate. Manually inspecting rendered crops (`real_project_error_taxonomy.md` items 1-2) was used only to **diagnose pipeline defects** (is the *candidate generation and export mechanism* working correctly), never to assert which candidate is the structurally correct answer.

## What this means for Phase 3+

- `outcome_store.latest_outcomes()` returns an empty dict for every one of these 108 groups today — there is no reviewed truth yet to train or evaluate against.
- The 108-group batch, its JSON+SVG exports, and the reviewer index are ready to hand to an actual reviewer (internal estimator or licensed structural engineer) as the literal next step — the mechanism is proven (deterministic, validated, append-only), only the human decisions are missing.
- Recommend prioritizing review of the 64 leader-evidence groups first, given `real_project_error_taxonomy.md`'s finding that the current production heuristic mis-selects a leader stroke as the final target in 28.8% of cases population-wide — confirming or correcting these specific groups would directly validate (or refute) that finding against real human judgment.

## Batch composition by pilot page

| Pilot page | Groups exported | Leader-evidence groups | All groups have 2+ candidates? |
|---|---|---|---|
| pilot_01 | 10 | (subset) | Yes |
| pilot_02 | 10 | (subset) | Yes |
| pilot_03 | 10 | (subset) | Yes |
| pilot_04 | 10 | (subset) | Yes |
| pilot_05 | 10 | (subset) | Yes |
| pilot_07 | 10 | (subset) | Yes |
| pilot_08 | 10 | (subset) | Yes |
| pilot_09 | 10 | (subset) | Yes |
| pilot_10 | 10 | (subset) | Yes |
| pilot_11 | 10 | (subset) | Yes |
| pilot_12 | 8 (page only had 8 total groups) | (subset) | Yes |
| **Total** | **108** | **64 (59.3%)** | **108/108** |

Note: because the prioritization filled every page's quota from ambiguous/leader-evidence groups, **none of the 108 exported groups happen to be a clean "zero valid candidates" example**, even though `pilot_11` was specifically selected as a page likely to contain such cases (`real_project_pilot_manifest.json`). The full, unbounded per-page group population (1,253 groups across all 11 pages, not just the exported 108) does contain 44 zero-candidate groups (3.5% — see `real_project_pilot_results.md`); a future export pass could specifically target those if "no-valid-target" examples are needed for review.
