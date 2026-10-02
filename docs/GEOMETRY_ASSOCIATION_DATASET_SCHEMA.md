# Geometry Association Dataset Schema (Research)

**Status:** Research contract proposal. Compatible with `services/ml_association` schema 2.0 concepts.  
**Does not** change production code or enable training.  
**Related:** `docs/GEOMETRY_ASSOCIATION_SENIOR_ARCHITECTURE_RESEARCH.md`

---

## Design rules

1. One training unit = **one (text, geometry_candidate, context) row** inside a **label group**.  
2. GHX IDs are **never** ML targets and **never** model inputs.  
3. Human outcomes are **append-only** and separate from extraction rows.  
4. Ambiguity is a first-class label, not missing data.  
5. Semantic text fields are never overwritten by geometry or GHX.

---

## Canonical association visualization object

```json
{
  "association_view_id": "av_...",
  "page": 8,
  "text": {
    "text_id": "token_...",
    "raw_text": "W8X10",
    "bbox": [x0, y0, x1, y1],
    "center": [cx, cy]
  },
  "member": {
    "geometry_id": "geo_...",
    "bbox": [x0, y0, x1, y1],
    "centerline": [[x, y], [x, y]],
    "orientation_deg": 0.0
  },
  "relationship": {
    "vector_text_to_member": [dx, dy],
    "distance_to_centerline": 12.3,
    "projection_point": [px, py],
    "leader_supported": true,
    "same_region": null
  },
  "status": "associated | ambiguous | conflict | unavailable | pending_review",
  "evidence": { "features...": "..." }
}
```

Text↔member **overlap IoU is not required** for a correct association.

---

## JSONL row schema (pairwise)

```json
{
  "sample_id": "proj_doc_page_text_geo_hash",

  "source": {
    "project_id": "burrville_es_st",
    "document_id": "doc_0d910a43b4a021e3",
    "page_number": 8,
    "page_id": "doc_...:p8",
    "source_file_hash": null
  },

  "text": {
    "text_id": "token_p8_427",
    "raw_text": "W21X44",
    "normalized_text": "W21X44",
    "word_bboxes": [],
    "span_bboxes": [],
    "grouped_bbox": [0, 0, 0, 0],
    "semantic_bbox": [0, 0, 0, 0],
    "center": [0, 0],
    "rotation_deg": 0.0,
    "text_height": 8.0,
    "parsed_family": "W",
    "label_type": "section"
  },

  "geometry": {
    "geometry_id": "geom_...",
    "primitive_ids": ["geom_..."],
    "primitive_type": "line",
    "geometry_role": "unknown",
    "bbox": [0, 0, 0, 0],
    "oriented_bbox": null,
    "center": [0, 0],
    "centerline": [[0, 0], [1, 0]],
    "orientation_deg": 0.0,
    "length": 120.0,
    "curvature_proxy": null,
    "endpoints": [[0, 0], [1, 0]]
  },

  "relationship": {
    "centroid_distance": 10.0,
    "bbox_distance": 0.0,
    "perpendicular_distance": null,
    "projection_distance": null,
    "bbox_overlap": 0.0,
    "bbox_intersects": false,
    "orientation_delta_deg": 5.0,
    "parallelism_score": null,
    "relative_position": "above",
    "same_page": true,
    "same_region": null,
    "region_available": false,
    "leader_supported": true,
    "leader_path_ids": [],
    "intervening_geometry_count": null,
    "local_geometry_density": null,
    "nearby_competing_geometry_count": null,
    "candidate_rank": 1,
    "candidate_count": 5,
    "candidate_generation_sources": ["leader_endpoint_resolved", "direct_distance"]
  },

  "context": {
    "region_id": null,
    "sheet_role": "structural_plan",
    "nearby_label_ids": []
  },

  "production_reference": {
    "nearest_geometry_id": "geom_...",
    "leader_resolved": true,
    "association_sources": ["leader_endpoint_resolved"],
    "selected": true
  },

  "ghx_reference": {
    "available": false,
    "associated_geometry_id": null,
    "element_id": null,
    "route": null,
    "association_origin": null,
    "rh_out_output": null,
    "coordinate_frame": null
  },

  "human_review": {
    "reviewed": false,
    "outcome_id": null,
    "review_label": null,
    "reviewed_target_geometry_ids": [],
    "callout_scope": null,
    "candidate_generation_miss": false,
    "adjudication_status": null,
    "reviewer_id": null
  },

  "target": {
    "label": null,
    "provenance_tier": null,
    "notes": "label in {associated, not_associated, ambiguous, no_valid_target}; null until gold/silver rules applied"
  },

  "provenance": {
    "schema_version": "assoc_research_1.0",
    "candidate_generator_version": "spatial_index_v1+rd",
    "feature_generator_version": "feature_builder_v1+rd",
    "extraction_version": null,
    "pipeline_version": null,
    "created_at": "ISO-8601"
  }
}
```

### Mapping to existing `ml_association` 2.0

| This field | Existing analogue |
|------------|-------------------|
| `text.*` | `LabelEvidence` |
| `geometry.*` | `ml_association.schemas.GeometryEvidence` (+ extend centerline) — **not** the same type as `services.semantic.models.GeometryEvidence` |
| `relationship.*` | `RelationshipFeatures` |
| `production_reference` | `HeuristicEvidence` |
| label group | `LabelGroup` |
| `human_review` | `ReviewedOutcome` |
| no-match row | `is_no_match_placeholder` |

**Naming collision:** three “GeometryEvidence” concepts exist (semantic object list, ml_association candidate geometry, fixture association-status docs). Dataset rows must use the **ml_association pairwise** shape; GHX object lists stay under `ghx_reference` / semantic provider payloads.

**Extension gaps to fill in a future shadow change (not now):** `centerline`, `ghx_reference` block, `geometry_role`, `word_bboxes`/`grouped_bbox`, non-empty `leader_path_ids`, soft `same_region` from R&D regions.

---

## Target label rules

| `target.label` | When |
|----------------|------|
| `associated` | Human `direct_target` / accepted secondary under scope |
| `not_associated` | Human `not_target` or hard negative |
| `ambiguous` | Human `ambiguous_requires_adjudication` |
| `no_valid_target` | Human `no_valid_target` |
| `null` | Unreviewed |

Silver auto-label (optional, never gold):

- `associated_silver` only if GHX primary route **and** PDF candidate set contains mapped geometry **and** human not conflicting — store under provenance_tier=`SILVER_AGREE`, still **excluded** from primary train unless explicitly ablated.

---

## ID alignment rules (anti-corruption)

1. Prefer content-hash geometry/text IDs from PDF extraction.  
2. Align GHX via explicit `element_id` + calibrated transform — never list index.  
3. If transform invalid → `ghx_reference.available=false`; do not force join.  
4. Duplicate primitives → keep `primitive_ids`; member hypothesis may merge later with provenance.  
5. Missing geometry in PDF dense-cap → record coverage flag; do not invent.

---

## Forbidden

- `target = ghx_reference.associated_geometry_id`  
- Feeding `ghx_reference.*` into model feature vectors  
- Using Excel takeoff rows as association labels  
- Completing section strings from geometry  
- Dropping ambiguous rows to inflate accuracy  
