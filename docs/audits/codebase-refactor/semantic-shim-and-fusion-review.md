# Semantic-Compatibility Shim and Fusion-Engine Review

Baseline: `main` @ `339429f9be59fdb5882ca1ffbcf7d8d5c0456eba`. Full forensic verification of the 3 deprecated
shim modules and the `fusion_engine.py`/`modular_fusion.py` relationship identified by the original
codebase-refactor audit. Every finding below was re-verified against the current tree, not assumed.

## Shim classification table

| Shim | Canonical target | Genuinely original content (never a re-export) | Re-exported content | Removal status |
|---|---|---|---|---|
| `services/prediction/semantic_contract.py` | `services/semantic/{models,projection}.py` | 6 `example_*` schema-demo functions, `_needs_review` helper, `COMPLETION_STATUS_COMPLETE`/`COMPLETION_STATUS_MISSING_THICKNESS` constants | `SemanticAnnotation`, `EvidenceType`, `EvidenceStrength`, `ReviewStatus`, `GeometryProvider` (kept — used internally by the example functions); `SEMANTIC_CONTRACT_VERSION`, `SemanticEvidence`, `GeometryAssociation`, `SemanticOperationKind`, `OperationRecord`, `SemanticDocument`, `project_semantic_annotation` (removed — zero callers after migration) | **KEEP_CURRENTLY_REQUIRED** (dead tail trimmed) |
| `services/semantic_preprocessor/models.py` | `services/semantic/models.py` | `TextPrimitive` dataclass + 6 page-quality classification constants (`NATIVE_TEXT_HEALTHY`, `NATIVE_TEXT_GARBLED`, `NO_NATIVE_TEXT`, `IMAGE_DOMINANT`, `OUTLINED_TEXT_SUSPECTED`, `UNKNOWN_PAGE_CLASS`) | 17 re-exported names (`CoordinateTransform`, `DrawingLanguageRule`, `EvidenceItem`, `AssociationCandidate`, `GeometryEvidence`, `GeometryProvider`, `Modifier`, `OperationKind`, `OperationRecord`, `ReviewState`, `ReviewStatus`, `ScoreValue`, `SemanticAnnotation`, `SemanticDocument`, `SourceFragment`, `StructuralParse`, `derive_annotation_id`, `SCHEMA_VERSION`) + 9 derived legacy constants (`OP_NONE`, `OP_NORMALIZATION`, `OP_REPAIR`, `OP_COMPLETION`, `REVIEW_ACCEPTED`, `REVIEW_AUTO_ACCEPTED`, `REVIEW_NEEDS_REVIEW`, `REVIEW_PENDING`, `Correction`) — **all removed, zero callers found for any of them** | **KEEP_CURRENTLY_REQUIRED** (dead tail trimmed) |
| `services/semantic_preprocessor/serialization.py` | `services/semantic/serialization.py` | none | `to_dict`, `to_json` (2 symbols, pure re-export) | **MIGRATE_AND_DELETE — done** |

## Internal callers found (before migration)

| Shim | File | Symbols imported | Real caller or docstring-only? |
|---|---|---|---|
| `semantic_contract.py` | `scripts/recompute_june_phase3_metrics.py` | `SemanticOperationKind`, `project_semantic_annotation` | real |
| `semantic_contract.py` | `scripts/run_june_phase3_validation.py` | `SemanticOperationKind`, `project_semantic_annotation` | real |
| `semantic_contract.py` | `tests/test_semantic_contract.py` | 6 `example_*` functions + `project_semantic_annotation` | real |
| `semantic_contract.py` | `services/prediction/drawing_semantics.py`, `services/semantic/{models,projection,serialization}.py` | — | docstring-only (historical/compatibility prose) |
| `semantic_preprocessor/models.py` | `services/semantic_preprocessor/{extraction,grouping,pipeline}.py` | `TextPrimitive` (+ page constants in `extraction.py`) | real, but importing the **genuine** symbols — no migration needed/possible |
| `semantic_preprocessor/models.py` | `scripts/generate_demo_semantic_fixture.py`, `tests/test_semantic_preprocessor_{grouping,pipeline,serialization}.py`, `tests/test_semantic_repair_shadow.py` | `TextPrimitive` only | real, genuine symbol, no migration needed |
| `semantic_preprocessor/models.py` | `services/prediction/semantic_contract.py`, `services/semantic/{models,serialization}.py` | — | docstring-only |
| `semantic_preprocessor/serialization.py` | `scripts/generate_demo_semantic_fixture.py` | `to_dict` | real — **migrated** |
| `semantic_preprocessor/serialization.py` | `tests/test_semantic_preprocessor_serialization.py` | `to_dict`, `to_json` | real — **migrated** |

No dynamic imports, no `__all__` declarations, no CI job references (no `.github/` exists in this repo), no
package `__init__.py` re-exports of any of the 3 shims were found anywhere.

## Phase 3 — serialization/pickle compatibility findings

All 32 tracked binary model artifacts (`.joblib`/`.pkl`/`.pt`/`.ubj`) were byte-scanned for the literal strings
`services.semantic_preprocessor.models`, `services.semantic_preprocessor.serialization`,
`services.prediction.semantic_contract` (and their `backend.`-prefixed forms) — **zero hits**. All tracked
`.json` files were `git grep`-scanned for the same 3 strings — **one hit**,
`backend/JUNE_PHASE3_VALIDATION_MANIFEST.json` line 145, a purely descriptive `"semantic_projection"` field in
a generated report (confirmed never read back by any code — grep shows it is only ever *written* by the two
migrated scripts). Not a compatibility risk; left untouched as a preserved historical report, per its own
protected-file status from the earlier documentation-organization phase.

**Symbol identity verified** (not just import success) via the new `tests/test_deprecated_import_compatibility.py`:
`services.prediction.semantic_contract.SemanticAnnotation is services.semantic.models.SemanticAnnotation`,
and likewise for `EvidenceType`, `EvidenceStrength`, `ReviewStatus`, `GeometryProvider` — all 5 pass,
confirming the shim never held a second, divergent definition.

## Fusion-engine reachability matrix

| Capability | `fusion_engine.py` (`WeightedFusionEngine`) | `modular_fusion.py` (`UnifiedMultimodalFusion`) |
|---|---|---|
| Public entrypoint | `fusion_engine.predict(context: dict) -> MultiModalPrediction` | `unified_multimodal_fusion.predict(*, encodings, candidates, fallback_section) -> UnifiedFusionResult` |
| Exact production caller | `services/multimodal/pipeline.py:253` | `services/prediction/orchestrator.py:769` |
| Calls the other? | Calls `orchestrator.predict_from_context()` (not `modular_fusion` directly) | Not called by `fusion_engine.py` at all |
| Confidence calculation | Reshapes `orchestrator`'s already-computed confidence dict | Computes it (`ConfidenceFusion`, attention-weighted, MLP-calibrated when `settings.learned_fusion_enabled`) |
| Evidence/explanation handling | Reshapes `orchestrator`'s explanation dict into `Explainability` dataclass (40+ fields) | Produces `reasons: List[str]` + `contributions: Dict[str, float]` + `candidate_scores` |
| Geometry/graph handling | Passthrough of `orchestrator`'s already-fused geometry/graph evidence | Computes per-modality scores (`_role_compatibility`, modality slices) directly |
| Exact-match handling | Passthrough — does not itself implement exact-match logic | Not applicable — operates on already-filtered candidates; exact-match locking happens upstream in `orchestrator.py`, before this is ever called |
| Human-review handling | Passthrough (`review_status` field) | Not applicable — a lower-layer scoring function, has no concept of review state |
| Error/fallback behavior | None of its own — errors propagate from `orchestrator.predict_from_context` | `fallback_section` param + graceful `_missing_encoding()` for absent modalities |
| Production entrypoints | Explicitly listed in both `_PRODUCTION_MODULES` guard-test lists | Imported directly by `orchestrator.py` (the sole recognized inference owner) |
| Test usage | `test_multimodal_pipeline.py`, `test_semantic_takeoff_projection.py` (call `.predict()` directly) | `test_modular_multimodal_fusion.py`, `test_incomplete_angle_abstention.py`, `test_label_ranker_evidence_recompute.py`, `test_protected_exact_label.py`, `test_resolution_contract.py`, `test_self_learning_safety.py`, `test_trusted_explicit_section.py` |
| Training-only usage | None found | `services/training_pipeline/neural_dataset.py` also imports `unified_multimodal_fusion` |
| Equivalent? | **No — not comparable.** Different input shape (`dict` vs. `encodings`+`candidates`+`fallback_section`), different output type, different responsibility layer. | |

**Classification: wrapper/adapter, not a duplicate.** `fusion_engine.py` and `modular_fusion.py` do not overlap
in responsibility at all — they are sequential layers of the same pipeline
(`pipeline.py` → adapter → `orchestrator` → algorithm), each independently required. Per the task's own Phase 9
rule ("If behavior differs or roles are distinct: keep both; document their separate purposes clearly"),
**no consolidation was attempted, and no differential testing (Phase 8) applies** — the two functions do not
accept meaningfully comparable inputs, so a side-by-side behavioral comparison would not be meaningful.

## Pre-existing issues observed (not caused by, and not fixed in, this phase)

- `scripts/recompute_june_phase3_metrics.py` (1 occurrence) and `scripts/run_june_phase3_validation.py`
  (3 occurrences) reference `SemanticOperationKind.ASSOCIATION`, which does not exist on the canonical
  `OperationKind` enum (`KEEP`/`NORMALIZATION`/`REPAIR`/`COMPLETION` only — `GeometryAssociation` was
  deliberately made *not* an `OperationRecord` at all, per `unified_semantic_contract.md`'s own design
  rationale). Confirmed present verbatim at `HEAD` before this phase's changes — this predates the import-path
  migration and is unrelated to it. Not exercised by any test in the current suite (would only surface if
  someone actually ran these report-generation scripts with association-type operations present). Left
  untouched — out of scope for a shim-migration task.
- `scripts/generate_demo_semantic_fixture.py` line 90 references `ann.correction`, an attribute that does not
  exist on `SemanticAnnotation` (operations are `ann.operations: List[OperationRecord]`, not a single
  `correction` field, per the same unified-model design). Confirmed pre-existing at `HEAD`. Not touched.
