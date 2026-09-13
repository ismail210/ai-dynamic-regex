# Accuracy Track gold (eval_cache only)

Not training data. Not Excel ground truth.

| File | Track | Purpose |
|---|---|---|
| `june_16page_extract_group_gold.json` | A2/A3/A4 | Extract / group / op / abstain labels on June 16-page subset |
| `a2_human_review_70.json` | A2 review | Separate workspace for the 70 unverified A2 rows (do not overwrite source gold) |
| `june_association_gold.json` | A7 | Label↔geometry links for association precision |
| `a7_human_review_100.json` | A7 review | Separate workspace for 100 association links |
| `a6_completion_evidence_fixtures.json` | A6 | SOURCE_VERIFIED completion conflict/abstain fixtures |

Incomplete L/2L rows in A2 gold are policy-verified (`ABSTAIN_MISSING_THICKNESS`). Human review UI: `backend/validation_reports/human_review/README.md`.
