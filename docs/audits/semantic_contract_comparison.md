# Semantic Contract Comparison — Consumer Audit

**Date:** 2026-09-13. **Scope:** `services/prediction/semantic_contract.py`
vs `services/semantic_preprocessor/models.py`, and every real consumer of
either, before consolidation. See `docs/architecture/unified_semantic_contract.md`
for the resulting design; this doc records what the audit actually found.

## 1. Repo-wide consumer search

```
grep -rl "semantic_preprocessor" backend --include="*.py"
  routers/semantic.py
  scripts/generate_demo_semantic_fixture.py
  services/semantic_document_service.py
  tests/test_semantic_preprocessor_{association,coordinate_transform,
    drawing_language_profile,geometry_evidence,grouping,normalization,
    pipeline,serialization}.py

grep -rl "prediction.semantic_contract" backend --include="*.py"
  scripts/recompute_june_phase3_metrics.py
  scripts/run_june_phase3_validation.py
  services/prediction/drawing_semantics.py
  tests/test_semantic_contract.py
```

**Key finding, corrected from the prior session's assumption:** the
`semantic_preprocessor` package was *not* "foundation work, not yet wired
in." Commit `98d8955` ("feat(semantic-review): add evidence-backed semantic
drawing demo") already wired it into a real FastAPI router
(`routers/semantic.py`), an orchestration service
(`services/semantic_document_service.py`) that runs the pipeline on real
uploaded PDFs, and a full "Semantic Review" frontend page
(`SemanticReviewPage.jsx`, `semanticContract.js`, `AnnotationInspector.jsx`)
— all already passing tests before this session touched anything.

`services.prediction.semantic_contract`, by contrast, is a **read-only
projection** (see its own docstring): it never runs pipeline logic, only
maps the *existing* dict-shaped orchestrator/`canonical_contract.py`
prediction payload into a typed schema for the A8 `drawing_semantics.json`
emitter and two offline validation scripts. It is not on the live request
path for the main prediction pipeline at all.

## 2. Field-by-field comparison (major differences)

| Concept | Partner (`semantic_contract.py`) | Preprocessor (`semantic_preprocessor/models.py`) |
|---|---|---|
| Container | Pydantic `BaseModel` | `@dataclass` |
| Document identity | none (annotation-only schema) | `SemanticDocument.document_id` |
| Annotation identity | `annotation_id` from caller-supplied `object_id`/`component_id` | `f"ann_{page}_{i}"` — **loop-position ID, not content-stable** |
| Original text | `raw_text: str` | `original_text: str` |
| Source fragments | none — one `source_bbox: List[float]` | `source_fragments: List[SourceFragment]`, full per-fragment bbox/text |
| Semantic/group bbox | n/a | `semantic_bbox` (derived union, fragments preserved separately) |
| Anchor/axis | none | `original_anchor`, `original_axis` |
| Structural parse | none (`structural_family: str` only) | `StructuralParse{is_structural, family, grammar, fields, catalog_exact_match, reason}` |
| Operation history | `operations: List[OperationRecord]`, 4 kinds incl. ASSOCIATION | single `correction: Correction`, reassigned in place per stage |
| Evidence | `SemanticEvidence` typed (`EvidenceType`/`EvidenceStrength` enums) | `EvidenceItem{type: str, value: Any, weight}` — untyped |
| Completion evidence | evidence list on the operation | `evidence_ids: List[str]` referencing external rule dicts |
| Geometry | one `geometry_evidence: Optional[GeometryEvidence]`, typed `provider` string | `geometry_associations: List[AssociationCandidate]`, `source: str` untyped |
| Geometry candidates | at most one | multiple, ranked, with independent `review_status` per candidate |
| Takeoff eligibility | `takeoff_eligible: Optional[bool]` | absent |
| Review | `review_required: bool`, `review_status: Optional[str]` | `review_status: str` (4 plain-string constants) |
| Confidence | bare `Optional[float]` everywhere | bare `Optional[float]` everywhere, plus `confidence_is_calibrated: bool` on `Correction` only |
| Serialization | `to_dict()` via `model_dump(mode="json")`; consumed only by `drawing_semantics.py`'s A8 emitter (`drawing_semantics_v1`) | `to_dict()` hand-written; written to the per-document `semantic.json` artifact via `services.artifact_store` |

## 3. Semantically-different fields that share a name (Section 5 pitfall)

- **"bbox"**: partner's `source_bbox` is the raw extracted span; a
  `GeometryEvidence.bbox` (both models) is a geometry object's own bounding
  box; preprocessor's `semantic_bbox` is a derived union over multiple
  fragments. All three now exist as distinct fields in the unified model
  (`SourceFragment.bbox`, `GeometryEvidence.bbox`, `SemanticAnnotation.semantic_bbox`)
  — none collapsed.
- **"confidence"/"score"**: OCR confidence, a deterministic normalization's
  self-reported 1.0, an uncalibrated repair candidate score, and a
  human-review-adjacent notion of "evidence strength" were all bare floats
  named `confidence` in one model or the other. The unified model's
  `ScoreValue{value, kind, calibrated}` keeps these distinguishable by
  `kind` rather than silently averaging them into one generic number.

## 4. Verdict: compatible-but-divergent, not duplicate-for-no-reason

Both models encode the same underlying ideas (KEEP/NORMALIZE/REPAIR/COMPLETE,
evidence, review, geometry-as-evidence) but neither was strictly a superset
of the other — partner's had richer operation/evidence typing and takeoff
integration; preprocessor's had richer spatial/source fidelity and
multi-candidate geometry. Neither could simply "win"; see
`docs/architecture/unified_semantic_contract.md` §3 for how each strength
was carried into the one canonical model.
