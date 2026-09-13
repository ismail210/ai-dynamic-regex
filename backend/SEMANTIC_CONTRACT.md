# Semantic Annotation Contract (Phase 2 — schema only)

**Module:** `backend/services/prediction/semantic_contract.py`  
**Version:** `1.0` (`SEMANTIC_CONTRACT_VERSION`)  
**Status:** Contract / schema only — **no new semantic intelligence**

---

## Purpose

Provide a stable backend representation for one drawing annotation that can record:

1. raw printed text  
2. normalized representation  
3. repair  
4. completion  
5. association / evidence  
6. confidence  
7. review state  
8. takeoff eligibility (as a **recorded** decision)  
9. optional geometry evidence (including future Grasshopper — **not required**)

This contract does **not** implement normalization, repair, completion, or association
logic. It does not enable ML / VLM / LLM / GraphSAGE, rewrite PDFs, or integrate GHX.

Production prediction remains owned by `services.prediction.orchestrator`. Existing
fields (`raw_text`, `normalized_text`, `completion_status`, `takeoff_eligible`,
`needs_review`, …) stay authoritative for behavior.

---

## Relationship to existing contracts

| Existing | Role | Relation to this contract |
|---|---|---|
| `prediction/canonical_contract.py` (`SourceText`, `CanonicalPrediction`) | Prediction outcome + source extraction | **Reuse terminology** (`raw` / `normalized`, review). Not replaced. |
| `prediction/contract.py` | TokenPrediction serialization + legacy aliases | Unchanged |
| `multimodal/contracts.py` (`MultiModalPrediction`) | Document multimodal payload | Already has `completion_status`, `takeoff_eligible`, `member_geometry` — **unchanged** this phase |
| `annotation/parser.py` (`AnnotationParse`) | Plate / section type taxonomy | Orthogonal; not duplicated |
| `ml_association/*` | Experimental association datasets | Remains unwired / flag-off |

**Extension choice:** new additive module (not a breaking change to `CanonicalPrediction`
builders). Optional read-only projection: `project_semantic_annotation(payload)`.

---

## Four operations

Do **not** collapse these into one generic “correction”.

| Operation | Meaning | May change semantic text? |
|---|---|---|
| **NORMALIZATION** | Same information; representation cleanup (`W8×10` → `W8X10`) | Yes (representation only) |
| **REPAIR** | Printed text corrupted; intended meaning supported by evidence | Yes (with evidence) |
| **COMPLETION** | Information missing; additional drawing-local evidence supplies it | Yes (with evidence) |
| **ASSOCIATION** | Link annotation to geometry / context | **No** — text must stay unchanged |

A record may list multiple `operations` over time for provenance. No workflow state
machine is introduced.

---

## Fields (`SemanticAnnotation`)

| Field | Notes |
|---|---|
| `schema_version` | `"1.0"` |
| `annotation_id` | Stable id (often prediction `object_id`) |
| `raw_text` | **Always preserved** printed form |
| `extraction_source` | Optional |
| `source_page` / `source_bbox` | Optional location |
| `normalized_text` | Core representation; never replaces `raw_text` |
| `structural_family` | Optional family code |
| `parser_status` | Optional |
| `operations[]` | Provenance of NORMALIZATION / REPAIR / COMPLETION / ASSOCIATION |
| `completion_status` | `complete` \| `missing_thickness` (matches production strings) |
| `original_text_preserved` | Must remain `true` |
| `takeoff_eligible` | **Records** existing decision; this module does not compute it |
| `evidence[]` | Multi-source evidence list |
| `confidence` / `confidence_basis` | Representation only — no new scorer |
| `review_required` / `review_status` / `review_reason` | Review state |
| `geometry_evidence` | **Optional**; may be absent / unavailable |
| `pipeline_version` / `created_by` / `document_id` | Provenance |

Confidence of representation ≠ license to bypass safety policy.

---

## Evidence model (`SemanticEvidence`)

| Field | Purpose |
|---|---|
| `evidence_type` | `pdf_text`, `nearby_note`, `legend`, `schedule`, `detail`, `structural_context`, `grasshopper_geometry`, `pdf_geometry`, `human_review`, `other` |
| `evidence_source` | Free-form source label |
| `evidence_reference` | Cite (string / id) |
| `evidence_strength` | `explicit` \| `inferred` \| `unknown` |
| `confidence` | Optional |
| `page_number` / `bounding_box` | Optional location |

**Safety:** Geometry association is **evidence**, not semantic truth. Associating a
beam curve with nearby text does **not** by contract authorize completing `W8` →
`W8X10`. Completion still requires appropriate semantic / drawing-local evidence.

Catalog existence is not completion evidence. Excel is never a predictor.

---

## Geometry evidence (optional)

`GeometryEvidence`:

- `available` (default `false`)
- `provider` (e.g. `grasshopper`, `pdf`, `unavailable`)
- `relationship` (`associated_with` \| `unpaired` \| `unknown` \| `unavailable`)
- `geometry_ref` / `geometry_type` / `confidence` / `coordinate_system` / `source`
- `native_metadata` — opaque bag for future RH_OUT fields

**Explicitly unresolved (do not assume in consumers):**

- `BeamTxt[i] == BeamCrv[i]`
- `BeamElementID` stability
- PDF ↔ Rhino coordinate calibration

Grasshopper evidence is representable but **never required**.

---

## Completion / abstention

Incomplete L / 2L (existing Phase 1 behavior) can be represented as:

```text
raw_text: "L4X4,"          # or "2L4X4"
normalized_text: "L4X4"    # core form; raw still recoverable
completion_status: missing_thickness
takeoff_eligible: false
review_required: true
```

No default thickness. No catalog-selected completion encoded as truth by this schema.

---

## Serialization

- Primary: Pydantic `SemanticAnnotation.model_dump` / `.to_dict()`
- Projection: `project_semantic_annotation(existing_prediction_dict)`
- **Not** implemented this phase: `drawing_semantics.json` pipeline, PDF rewrite, GH consume path

---

## Backward compatibility

- No changes to orchestrator / label ranker / catalog / Excel / takeoff calculation
- No feature-flag changes
- Existing prediction response shapes unchanged (contract is additive / opt-in)
- Phase 1 incomplete-angle abstention unchanged

---

## Examples (schema only — not new implemented behaviors)

### 1. Normalization — `W8×10` → `W8X10`

`example_normalization_w8x10()` — operation `normalization`; `raw_text` remains `W8×10`.

### 2. Repair — corrupted label (schema example only)

`example_repair_corrupted_w8()` — `W8XI0` → `W8X10` via `repair` + nearby-note evidence.
**Not** production repair logic.

### 3. Completion candidate — `W8` (schema example only)

`example_completion_candidate_w8()` — `completion` with schedule evidence.
**Not** production completion; still requires drawing-local evidence in any future impl.

### 4. L4X4 abstention

`example_l4x4_abstention()` — `missing_thickness`, `takeoff_eligible=false`.

### 5. 2L4X4 abstention

`example_2l4x4_abstention()`.

### 6. Association with optional GH evidence

`example_association_with_optional_gh()` — `W12X26` associated; text unchanged;
`native_metadata` records that BeamTxt/Crv index equality is **not** assumed.

---

## Tests

`backend/tests/test_semantic_contract.py` — schema cases A–I (raw preservation,
four operations distinct, multi-source evidence, optional geometry, L/2L
abstention representation, complete eligible representation).

Phase 1 production safety is unchanged by this phase (no edits to
`label_ranker_hook.py` / `orchestrator.py` / takeoff / catalog / flags). Re-run
`tests/test_incomplete_angle_abstention.py` in a full venv outside sandbox when
numpy is available (sandbox currently FPE on `import numpy`).

---

## What this phase deliberately does not do

- New normalizer / repairer / completer / associator
- Fuzzy matching, LLM, VLM, GNN, XGB / GraphSAGE enablement
- Catalog-as-evidence, Excel-as-predictor
- Auto-complete `L4X4` / `2L4X4`
- GHX / Rhino.Compute / PDF↔Rhino transforms / member bbox pipeline
