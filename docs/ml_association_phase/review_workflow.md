# Review Workflow

Operational guide to `backend/services/ml_association/`. For what the fields mean, see `schema.md`. For how to decide what to select, see `annotation_guidelines.md`.

## Enabling the feature

Every entry point in `service.py` is gated behind one setting:

```
ML_ASSOCIATION_DATASET_ENABLED=true
```

Default is `false`. With the default, every `service.*` function raises `service.FeatureDisabledError` immediately — including read-only ones like `build_dataset`. This is intentional: the whole package should be inert unless someone has explicitly opted in for a given process/session. Nothing in the live prediction pipeline sets this variable or imports this package (`backend/tests/test_ml_association_not_wired_into_production.py` enforces this as a build-breaking test, not just a convention).

`candidate_dataset.py`, `review_export.py`, `review_import.py`, `validation.py`, and `outcome_store.py` remain directly importable (and are, throughout the test suite) without the flag — the flag gates `service.py`'s facade specifically, since that's the intended single entry point for anything outside this package (a future script, notebook, or admin route).

## End-to-end flow

```
1. Extract a document                 (existing Phase 1 pipeline, unchanged)
     pdf_parser.extract_document_structure(pdf_path)
     geometry_extractor.extract_geometry(pdf_path, document_structure)

2. Build the association dataset       (Phase 2, this package)
     service.build_dataset(document_structure, geometry,
                            project_id=..., document_id=..., created_at=...)
     -> List[LabelGroup]

3. Export for human review
     service.export_groups(groups, pdf_path=pdf_path, output_dir=...)
     -> writes {group_id}.json + {group_id}.svg per group

4. A reviewer inspects the SVG + JSON and decides:
     - which candidate(s) are the real target(s), or
     - that no valid target exists, or
     - that this needs a second opinion

5. Submit the reviewer's decision
     service.submit_review(raw_submission_dict, group, outcomes_path=...)
     -> ValidationResult(valid=True/False, errors=[...], outcome=...)
     If valid, the outcome is appended to reviewed_outcomes.jsonl automatically.

6. Retrieve current truth for training/evaluation (Phase 3+)
     service.latest_outcomes(outcomes_path=...)   -> {group_id: ReviewedOutcome}
     service.outcome_history(group_id, outcomes_path=...)  -> full audit trail
```

Nothing in steps 2-6 changes what a current user of Estima3D sees. Step 1 is the existing, unmodified extraction pipeline; everything after it writes only to new files under `training/ml_association/` (or wherever the caller points `outcomes_path`/`output_dir`).

## `project_id` / `document_id` are caller-supplied, not invented

This repository has no project-grouping concept anywhere yet (`docs/geometry_graph_audit/09_open_questions.md`). Phase 2 deliberately does not invent one — `build_dataset` requires `project_id` and `document_id` as explicit arguments. In practice, until a real project registry exists, a reasonable convention is: `document_id` = the existing `document_registry.py` convention (`doc_{sha256[:16]}`), and `project_id` = whatever external grouping (client name, job number, folder) a human operator assigns when kicking off a review batch. This is a manual/administrative decision for now, not something this package infers from file content.

## `created_at` is caller-supplied, not `datetime.now()`

`build_label_groups`/`build_dataset` require `created_at` explicitly rather than defaulting to the current wall-clock time. This is what makes two calls with the same inputs produce byte-identical output (`docs/ml_association_phase/baseline_results.md`'s determinism discipline, continued from Phase 1) — determinism requires the caller to control anything that would otherwise vary between runs. In a real pipeline, pass the document's actual extraction/analysis timestamp.

## Reviewer submission shape

A submission is a plain dict matching `ReviewImportEntry`'s fields (see `schema.md`):

```json
{
  "export_schema_version": "2.0",
  "group_id": "group_...",
  "project_id": "...",
  "document_id": "...",
  "page_id": "page_...",
  "text_entity_id": "token_p1_0",
  "review_label": "direct_target",
  "reviewed_target_geometry_ids": ["geom_..."],
  "candidate_generation_miss": false,
  "callout_scope": "single",
  "reviewer_id": "alice",
  "reviewed_at": "2026-02-01T12:00:00Z",
  "annotation_notes": "optional free text",
  "supersedes_outcome_id": null
}
```

`service.submit_review` returns a `ValidationResult`. Always check `.valid` before assuming anything was recorded — an invalid submission is never partially written; `outcome_store.append_outcome` is only called when validation passes.

## Correcting a prior review

Submit a new entry with the corrected `review_label`/targets, a new `reviewed_at`, and `supersedes_outcome_id` set to the outcome being corrected. This produces a new `ReviewedOutcome` row; the original is never modified or deleted (`schema.md`'s "append-only outcomes" section). `outcome_store.latest_outcomes()` automatically resolves to the correction; `outcome_store.history_for_group()` still shows both.

## What this phase does not include

- No model training, no ranking, no calibration (Phase 3+).
- No global assignment/conflict resolution across labels (Phase 3+, roadmap P1.6).
- No region/detail-segmentation layer (roadmap P1.4, still open) — `region_id` is always `None`.
- No production React UI — the SVG/JSON export is a backend/offline artifact, meant to be opened directly or served by a separate lightweight tool, not part of the existing Results page.
- No automatic project/document grouping.

## Reference implementation status

Real project PDFs were not available in this environment (see `unresolved_questions.md` and `repository_evidence.md`) — every test in this phase uses synthetic fixtures (hand-built extraction dicts or small PyMuPDF-generated PDFs). The package is exercised end-to-end (`service.build_dataset` → `service.export_groups` → `service.submit_review` → `service.latest_outcomes`) in `backend/tests/test_ml_association_*` and manually during development, but **no claim is made here about performance, coverage, or usability on real production drawings** — that validation is explicitly deferred to whoever runs this against real project files next.
