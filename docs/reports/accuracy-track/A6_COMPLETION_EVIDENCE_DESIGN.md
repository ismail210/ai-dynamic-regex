# A6 — SOURCE_VERIFIED completion evidence design

**Track:** Extraction & Compilation Accuracy  
**Status:** Design + fixtures only (no auto `L4X4`→thickness)

---

## Rule

Completion may fill a missing dimension **only** when drawing-local evidence is
`SOURCE_VERIFIED`. Catalog membership alone is never thickness evidence.

| Strength | Allowed to complete? |
|---|---|
| `SOURCE_VERIFIED` (same sheet legend / schedule / detail note naming the same member core) | Yes, if unique and non-conflicting |
| `INFERRED` (nearby complete callout of same family/legs) | **Abstain** (River Road conflict cases) |
| Catalog-only | **Abstain** |
| Conflicting verified sources | **Abstain** |

Incomplete printed `L` / `2L` stay `completion_status=missing_thickness` unless a
verified source supplies thickness for that exact core on the drawing.

---

## Evidence registry (Phase 2 contract)

Reuse `SemanticEvidence` / `EvidenceType`:

- `LEGEND` / `SCHEDULE` / `DETAIL` / `NEARBY_NOTE` with `evidence_strength=explicit`
- `evidence_reference` must cite page + quote / object id
- Association evidence does **not** rewrite text

---

## Fixture classes (`a6_completion_evidence_fixtures.json`)

1. **catalog_alone_abstain** — `L4X4` with only AISC rows → abstain  
2. **nearby_complete_conflict_abstain** — `L4X4` near both `L4X4X1/4` and `L4X4X3/8` → abstain  
3. **legend_unique_verified** — schedule defines `L4X4X3/8 TYP` uniquely for that core → eligible for future gated completion (not enabled)  
4. **half_leg_complete** — `L6X3-1/2X3/8` is already complete → no completion op  

Production flags remain off; fixtures measure policy only.
