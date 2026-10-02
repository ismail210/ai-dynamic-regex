# Deploy-prep triage (Sep 23)

Decision record for Bassam’s known backend failures + isolated upload path overrides. Not full prod certification.

## Known failures — accept vs fix

Re-run on `main` @ `77f0ea0` (this checkout):

```
7 failed, 28 passed
```

| Test | Symptom | Decision |
| --- | --- | --- |
| `A2HumanReviewTests::test_partial_review_uses_reviewed_denominator` | AssertionError `3 != 2` | **ACCEPT** |
| `A2HumanReviewTests::test_unanswered_fields_remain_null` | `'YES' is not None` | **ACCEPT** |
| `A2HumanReviewTests::test_zero_reviewed_returns_na_not_fake_zero` | `2 != 0` | **ACCEPT** |
| `A7HumanReviewTests::test_method_breakdown_totals` | `6 != 3` | **ACCEPT** |
| `A7HumanReviewTests::test_precision_excludes_ambiguous` | `4 != 3` | **ACCEPT** |
| `A7HumanReviewTests::test_zero_reviewed_precision_na` | `4 != 0` | **ACCEPT** |
| `RepeatedDetailLinkerTests::test_validation_does_not_count_as_eligible_member` | `KeyError: predicted_aggregates` | **ACCEPT** |

Historically counted as **9** (8× a2_a7 + 1× repeated_detail) in refactor docs; this SHA shows **7** (6 + 1) — same fixture/contract-drift class, not production takeoff path.

**Rationale for ACCEPT (not must-fix before deploy-prep):** stale human-review / validation fixtures after `ground_truth_evaluation` contract changes; repeated_detail expects `predicted_aggregates` key removed from validation payload. None of these gate schedule quantity safety, mark map, or upload serving. Track as follow-up ticket: refresh A2/A7 fixtures + align repeated_detail linker test with current validation contract. **Do not block deploy-prep** on fixing them today.

No one-line production fix attempted — root cause is test/fixture drift, not a hot-path crash in takeoff.

## Isolated runtime path overrides

Disposable E2E uploads must not mutate preserved training trees. Two env keys now override the frozen Settings defaults (same pattern as other deploy knobs):

| Env var | Default | Purpose |
| --- | --- | --- |
| `UPLOAD_LOG_PATH` | `backend/training/upload_log.csv` | Redirect upload log appends |
| `DOCUMENT_REGISTRY_DIR` | `backend/training/documents` | Redirect document JSON registry writes |

Example (process env before starting uvicorn):

```bash
export UPLOAD_LOG_PATH=/tmp/estima-e2e/upload_log.csv
export DOCUMENT_REGISTRY_DIR=/tmp/estima-e2e/documents
mkdir -p "$DOCUMENT_REGISTRY_DIR"
```

**Still lands on default training paths unless set:** `approved_dataset.csv`, `engineering_corrections.jsonl`, `human_selections.json`, `continuous_learning_state.json`, `multimodal_review_index.json` (module-level path in review_enrichment). Tests already isolate those via `IsolatedApiTestCase`. For a live write-triggering upload, set the two keys above first; expand env overrides only if a dry-run still touches preserved files.

**Do not run a live write-triggering upload until these overrides are set in the server process.**
