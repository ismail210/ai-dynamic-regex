# ML-Association Dataset Schema

Package: `backend/services/ml_association/`. Schema version: **`2.0`** (`services.ml_association.schemas.SCHEMA_VERSION`). Status: experimental, disabled by default (`ML_ASSOCIATION_DATASET_ENABLED=false`) — see `review_workflow.md`.

This document explains the entities in `schemas.py`, why they're shaped the way they are, and the versioning/provenance discipline that makes the resulting dataset trustworthy for eventually training the Phase 3+ ranker.

## Why schema version `2.0`, not `1.0`

`config.py`'s existing `dataset_schema_version`/`model_schema_version` (used by `training_pipeline/`) are independently at `"1.0"`. This package's schema is a **new, unrelated** contract — reusing `"1.0"` would falsely imply compatibility with that older, unrelated dataset format. `2.0` signals "a new schema lineage," not "the second revision of an existing one."

## Entities

### `LabelEvidence`
Raw + lightly-derived facts about one text/label entity, **never overwritten** once written to a row (same discipline as `services.prediction.canonical_contract.SourceText`). `raw_text` is exactly what extraction produced; `normalized_text` stays `None` in this phase (Phase 2 does not run text normalization — that's the existing `services.normalization` module's job, not duplicated here) unless a caller supplies it.

### `GeometryEvidence`
Raw + lightly-derived facts about one geometry candidate. `None` on the synthetic no-match placeholder row (see below). `current_heuristic_role` is the *production* graph's node kind for this geometry (from `graph_builder.build_geometry_nodes`), included as evidence, not as a claim about the geometry's true structural role.

### `RelationshipFeatures`
Everything computed *about the pairing* of one label and one geometry candidate — the features the eventual ranker will actually train on. Two disciplines enforced throughout:

1. **Every potentially-missing value has an explicit `*_available` sibling.** `distance_normalized_by_scale` stays `None` with `distance_scale_available=False` rather than silently defaulting to `0.0`, because this repository has no drawing-scale detection yet (`docs/geometry_graph_audit/09_open_questions.md` Q4) — a `0.0` here would be indistinguishable from "scale is exactly 1:1," which is never actually known. The same pattern applies to `same_region`/`region_available` (no region-detection layer exists yet, P1.4 in the roadmap is still open).
2. **Raw pairwise geometry math is separated from page-level context.** `centroid_distance`, `bbox_distance`, `bbox_intersects`, etc. are pure functions of exactly two nodes (`feature_builder.py`). `graph_degree`, `nearby_steel_label_count`, `local_line_density`, etc. require the full page's node list and the production graph, and are assembled by `candidate_dataset.py` — this separation exists so the pure geometry math is trivially unit-testable in isolation from graph/page context.

### `HeuristicEvidence`
What the **current production heuristic** (`graph_builder.build_graph`'s greedy `nearest_geometry` edge — not this package's own experimental STRtree generator) actually did with this specific candidate. `current_heuristic_score`/`current_heuristic_rank` are populated **only** for the one candidate the production heuristic actually picked (`current_heuristic_selected=True`); every other candidate has both as `None`. This is not a gap — the production heuristic is a single greedy pick, not a ranker, so it genuinely has no opinion about alternatives (`docs/geometry_graph_audit/04_graph_audit.md §4`). Fabricating ranks 2, 3, 4... for candidates the heuristic never evaluated would misrepresent what the current system actually does.

`current_heuristic_score` must never be described or displayed as a probability — it is `1/(1+distance)`, a distance-derived weight, exactly the same caution the original audit raised about the live prediction pipeline's own "confidence" fields (`docs/geometry_graph_audit/02_logic_inventory.md`).

### `AssociationCandidateRow`
One `(text_entity_id, geometry_entity_id, local context)` row — the unit everything else is built from. `geometry_entity_id=None` with `is_no_match_placeholder=True` is the reserved **no-valid-target candidate**: every label group includes exactly one of these (when `include_no_match_candidate=True`, the default), so a reviewer always has an explicit, selectable "no real target exists" option rather than needing a special-cased UI affordance outside the candidate list.

`text_entity_id`/`geometry_entity_id` are the **stable source IDs** (`token_id`, `geometry_id`) from extraction — not the graph's own `node_id` (which is a graph-construction artifact, deterministic since Phase 1 but conceptually one layer removed from "the real-world entity").

### `LabelGroup`
One label entity plus its full candidate set — the "query group" a future LambdaMART ranker will train on (one group = one ranking problem). `group_id` is derived from `(text_entity_id, candidate_generator_version)` only — **not** the candidate set itself — so a candidate-generator bugfix that changes which/how-many candidates are found does not orphan a group's prior review history.

### `ReviewedOutcome`
One append-only reviewer decision. See "Append-only outcomes" below.

### `ReviewImportEntry`
The untrusted shape a reviewer submission is parsed from — deliberately looser than `ReviewedOutcome` (plain strings for enums, no cross-references verified yet). `validation.py` turns this into either a `ReviewedOutcome` or a list of `ValidationError`s.

### `ReviewExportPayload`
The JSON sibling of one group's SVG export file — see `review_workflow.md`.

## Raw vs. normalized vs. inferred vs. reviewed

This is the same discipline the original geometry/graph audit flagged as frequently *violated* in the production pipeline (`docs/geometry_graph_audit/02_logic_inventory.md`'s "raw/normalized/inferred/resolved mixing" findings) — Phase 2 exists partly to not repeat that mistake in the new dataset:

| Concept | Where it lives | Mutability |
|---|---|---|
| **Raw** extraction (`raw_text`, `geometry_bbox`, ...) | `LabelEvidence`/`GeometryEvidence` | Never overwritten once a row is created |
| **Heuristic** inference (current production's pick) | `HeuristicEvidence` | Evidence only — read-only snapshot of what production did, never influences what gets stored as truth |
| **Reviewed** human truth | `ReviewedOutcome` | Append-only (see below) — a **separate object type**, never merged back into `AssociationCandidateRow` |

A single object never mixes "what was extracted" with "what a human decided" — they are always two different Python objects, joined only by `group_id`/`text_entity_id`, exactly so a future consumer can never accidentally treat a heuristic pick as ground truth or a raw value as already-normalized.

## Candidate-generation misses

`candidate_generation_miss: bool` on both `AssociationCandidateRow`'s sibling context and `ReviewedOutcome` records the case where a reviewer's true target was **not** among the exported top-K candidates at all. This is not an error state to hide — it is exactly the "candidate coverage" metric the deep-research report treats as a release gate (`docs/geometry_graph_audit/06_research_findings.md`). `validation.py` requires this flag to be explicitly `true` before accepting a target outside the candidate set (`ValidationErrorCode.TARGET_OUTSIDE_CANDIDATE_SET` otherwise) — a reviewer cannot silently "correct" a miss without it being recorded as one.

## Append-only outcomes

`outcome_store.py` never rewrites or deletes a line in `reviewed_outcomes.jsonl`. A correction is **always** a new `ReviewedOutcome` whose `supersedes_outcome_id` points at the one it replaces. `outcome_id` is deterministic (`identifiers.outcome_id`, a hash of `group_id + reviewer_id + reviewed_at [+ supersedes_outcome_id]`), so:

- The exact same submission resubmitted verbatim produces the exact same `outcome_id` → rejected as a duplicate (`ValidationErrorCode.DUPLICATE_OUTCOME_ID`), not silently accepted twice.
- A genuine correction (different `reviewed_at`, or explicitly chained via `supersedes_outcome_id`) produces a new, distinct ID and is accepted as a new row.
- `outcome_store.latest_outcomes()` deterministically resolves each `group_id` to its current "head" outcome (excluding anything superseded or marked `rejected_invalid`), while `outcome_store.history_for_group()` always returns the full, unfiltered chain.

## Versioning fields, and why there are four of them

`schema_version`, `candidate_generator_version`, `feature_generator_version`, `extraction_version`/`pipeline_version` are tracked **independently** because they change independently:

- `schema_version` — the shape of these Python models.
- `candidate_generator_version` — which algorithm found the candidates (today: `spatial_index_v1`; a future STRtree improvement or a different generator entirely would bump this without touching the schema).
- `feature_generator_version` — how relationship features were computed (`feature_builder_v1` today).
- `extraction_version`/`pipeline_version` — the upstream geometry/graph extraction pipeline's own version, caller-supplied (this package does not define what that string means; it threads through whatever the caller's extraction pipeline reports).

Mixing rows from different `candidate_generator_version`s in one training run without accounting for the difference would silently conflate "the target wasn't found" with "the target wasn't looked for the same way" — the explicit version fields make that distinction auditable rather than invisible.

## Persistence format: JSONL, not a database migration

No SQL database exists anywhere in this repository (`docs/geometry_graph_audit/01_workflow_map.md`). Introducing one solely for this one append-only log would be a disproportionate architectural change for what Phase 2 needs. JSONL (one `ReviewedOutcome` per line) directly matches an existing, working precedent in this exact area of the codebase — `services/engineering/correction_dataset.py` already writes `training/engineering_corrections.jsonl` the same way, including the same threading-lock discipline for concurrent writers. See `outcome_store.py`'s module docstring for the full reasoning.
