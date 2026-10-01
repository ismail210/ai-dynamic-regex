# GeometryEvidence Contract (fixture / schema layer)

**Module:** `backend/services/prediction/semantic_contract.py` (`GeometryEvidence`)  
**Fixtures:** `backend/services/prediction/geometry_evidence_fixtures.py` (**SYNTHETIC / TEST ONLY**)  
**Status:** Contract + fixtures only — **no GH adapter, no association algorithm, no calibration**

---

## Why GeometryEvidence exists

Estima3D owns **semantic text** (extract → group → normalize / repair / complete → abstain → `drawing_semantics.json`).  
Grasshopper/Rhino owns **geometry processing**. Bassam’s G0–G4 work will observe the real `RH_OUT` contract.

`GeometryEvidence` lets the semantic annotation carry optional **geometry provenance** so that, later, real GH candidates can be attached **without** treating geometry as semantic truth and without changing A1–A8 inference behavior today.

---

## Geometry is evidence, not semantic truth

Attaching geometry evidence:

- **does not** rewrite `raw_text` or `normalized_text`
- **does not** complete missing thickness (`L4X4` stays `L4X4`)
- **does not** flip `completion_status` or `takeoff_eligible`
- **does not** authorize catalog/Excel completion
- **may** set `review_required` when status is conflict/ambiguous/gh_only

Forbidden representation:

> “geometry says L4X4 is probably L4X4X1/4”

Safe representation:

```text
annotation = L4X4
completion_status = missing_thickness
takeoff_eligible = false
geometry_evidence = candidate member (optional)
```

---

## Relation to A1–A8

| Track | Relation |
|---|---|
| A1 compiler surface / incomplete L visibility | Unchanged; fixtures assume abstention fields already set |
| A2–A4 text ops | Unchanged |
| A5 repair shadow | Unchanged |
| A6 SOURCE_VERIFIED completion | Still **not** enabled; geometry ≠ completion evidence |
| A7 association measurement | Separate human gold; this layer does **not** implement association |
| A8 `drawing_semantics.json` | Additive: annotations may include optional `geometry_evidence` |

---

## Supported association statuses

Additive enum `GeometryAssociationStatus` on `GeometryEvidence`:

| Status | Meaning |
|---|---|
| `agreement` | PDF-side and GH-side candidates agree on the same ref |
| `gh_only` | GH candidate present; no PDF association evidence |
| `pdf_only` | PDF association evidence; no GH |
| `conflict` | PDF and GH point at different candidates — **no forced pick** |
| `ambiguous` | Multiple candidates — **no forced pick** (`geometry_ref` may be null; `candidate_refs` lists all) |
| `unavailable` | Explicitly unavailable |

Existing fields remain: `available`, `provider`, `relationship`, `geometry_ref`, `geometry_type`, `confidence`, `coordinate_system`, `source`, `native_metadata`.

---

## Conflict and ambiguity

- **Conflict:** `association_status=conflict`, `geometry_ref=null`, `candidate_refs=[pdf_ref, gh_ref]`, typically `review_required=true`.
- **Ambiguous:** `association_status=ambiguous`, `geometry_ref=null`, `candidate_refs=[…]`, `forced_selection=false` in metadata.
- Multiple annotations may share the same `geometry_ref` **without** merging annotation identities.
- One annotation may list multiple `candidate_refs` without selecting a winner.

---

## Incomplete L / 2L with geometry

Fixtures `fixture_incomplete_l_with_geometry` and `fixture_incomplete_2l_with_geometry` prove:

- core label preserved (`L4X4` / `2L4X4`)
- `completion_status=missing_thickness`
- `takeoff_eligible=false`
- geometry may still be `available=true`

Geometry **cannot** bypass abstention.

---

## What is intentionally NOT frozen yet (Bassam G0+)

Do **not** treat synthetic fixture refs as production RH_OUT:

- Actual GH/RH_OUT field names and DataTree path semantics
- `BeamTxt[i] ↔ BeamCrv[i]` pairing
- `BeamElementID` meaning / stability
- PDF ↔ Rhino coordinate calibration
- Automatic geometry association / selection policy
- Live Rhino.Compute or GHX rewrite

`native_metadata` may carry placeholders such as `rh_out_datatree_contract: UNKNOWN_until_G0`.

---

## Tests

`backend/tests/test_geometry_evidence_contract.py` — cases A–L + drawing_semantics backward compatibility.

Existing `tests/test_semantic_contract.py` must continue to pass.
