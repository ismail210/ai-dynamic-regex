# Phase 3A Gold Set Report

## 1. Objective

Phase 3 separates human ground truth from pipeline output so section,
association, geometry recall, and length can be evaluated independently. A
pipeline agreement is not treated as truth.

**Current status:** incomplete at the human-verification gate. Existing data
supports zero ID-stable occurrence records and zero association-verified
records. No accuracy metric is reported.

## 2. Existing Human Review Audit

Full audit: `docs/validation/phase3_human_review_audit.md`.

- Drawing Review persists the document/object, prediction snapshot, corrected
  section, action, and notes.
- Its UI does not persist selected geometry, correct orphan, association
  failure, geometry-recall failure, role, scale, or length.
- `approved_dataset.csv` and unknown-token history are token-to-class review
  data, not association ground truth.
- An offline `ml_association` review workflow already provides the required
  selected-target/no-target/ambiguous fields and append-only history.
- No completed association decision files or reviewed-outcome store were found.

## 3. Gold Set Construction

`docs/validation/gold_set_v1.json` defines schema version 1.0 and currently has
an empty `records` array.

Two de-duplicated Burrville Drawing Review decisions were considered:
`token_p7_176` (`HSS10X6X3/8`) and `token_p7_205` (`W16X26`). They were excluded
because the IDs are run-dependent and stale relative to current artifacts, and
neither stores geometry truth. Token-level approvals remain available for a
separate lexicon evaluation but are not spatial Gold records.

A reusable batch builder was added at
`backend/scripts/build_phase3_gold_review_batch.py`. It targets 35 balanced
association cases and writes confidential SVG/JSON/HTML artifacts only below
the already git-ignored real-project pilot directory. It does not write human
truth. In this environment, loading the existing association/graph review
stack did not finish after more than ten minutes, so no review batch manifest
was emitted and no decision was fabricated as a workaround.

## 4. Orphan Analysis

Burrville page 8 has 50 pipeline orphans after Phase 2.

Human-verified diagnosis:

- correct orphan: 0 established
- association failure: 0 established
- geometry recall failure: 0 established
- ambiguous: 0 established
- not yet association-reviewed: 50

The earlier statement that many Burrville cases were manually judged correct
is not represented by durable association decisions in the inspected stores.
It cannot be converted into record-level Gold truth without object-level
decisions.

## 5. Baseline Metrics

| Metric | Result |
| --- | --- |
| Gold records | 0 |
| Association-verified records | 0 |
| `verified_correct` | 0 |
| `verified_wrong` | 0 |
| `verified_orphan` | 0 |
| `ambiguous` | 0 |
| `needs_review` | not inserted into Gold |
| Section accuracy | not reportable |
| Association accuracy | not reportable |
| Verified orphan precision | not reportable |
| Role accuracy | not reportable |
| Length accuracy | not reportable |

The historical approximately 26% Top-1 value remains a section/classification
metric. It is not an association, geometry, takeoff, or product-accuracy
baseline.

## 6. Main Failure Modes

The Gold data is not yet large enough to rank failure modes. Phase 2 pipeline
counts still indicate unresolved cases, but those counts cannot determine
whether missing geometry, incorrect association, or correct abstention is
dominant.

## 7. Recommendation

Complete 30–50 decisions with the existing offline association review workflow,
starting with Burrville page-8 orphans and K1200 page-22 member/leader cases.
Import the decisions into the append-only outcome store, then regenerate
`gold_set_v1.json` and calculate only supported metrics. Do not make another
geometry, graph, or ML change before this human-review gate is complete.

## Files inspected

- `frontend/src/pages/DrawingReviewPage.jsx`
- `frontend/src/components/SectionReviewSelector.jsx`
- `backend/routers/engineering.py`
- `backend/services/human_selections.py`
- `backend/services/dataset_manager.py`
- `backend/services/engineering/correction_dataset.py`
- `backend/services/ml_association/schemas.py`
- `backend/services/ml_association/enums.py`
- `backend/services/ml_association/outcome_store.py`
- `backend/services/ml_association/review_export.py`
- `backend/scripts/build_ml_association_review_kit.py`
- `backend/scripts/import_review_decisions.py`
- `backend/training/engineering_corrections.jsonl`
- `backend/training/unknown_tokens.csv`
- `backend/training/approved_dataset.csv`
- `backend/training/history.csv`
- Phase 1 and Phase 2 reports and measurements

## Production changes

**NONE.**
