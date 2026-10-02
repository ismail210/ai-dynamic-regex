# Geometry Association — Minimum Experiment Plan

**Status:** Research plan only. No training. No production changes.  
**Parent:** `docs/GEOMETRY_ASSOCIATION_SENIOR_ARCHITECTURE_RESEARCH.md`  
**Schema:** `docs/GEOMETRY_ASSOCIATION_DATASET_SCHEMA.md`

---

## Goal

Answer, with measurable evidence on ~100–300 pairs:

> Are PDF geometry candidates + leader/region features good enough to support a trustworthy association dataset and a deterministic evidence layer — without treating GHX or production nearest as ground truth?

---

## Non-goals

- Train XGB/GraphSAGE/VLM  
- Modify GHX / production association  
- Full corpus processing  
- Claim “better than GHX”  
- Hard region gates  

---

## Assets to reuse (already exist)

| Asset | Path |
|-------|------|
| Burrville multimodal artifacts | `backend/training/engineering_artifacts/doc_0d910a43b4a021e3/multimodal/` |
| Step 2/3 harness | `backend/scripts/rd_geometry_integration/` |
| Step 2/3 outputs | `docs/validation/rd_geometry_integration/` |
| Golden pages | p8 plan, p18 detail, p24 dense detail |
| Shadow review stack | `backend/services/ml_association/` |
| Annotation guidelines | `docs/ml_association_phase/annotation_guidelines.md` |
| Prior pilot note | 108 groups prepared; **0 reviewed** (`phase3_readiness_decision.md`) |

---

## Experiment design

### Pages

1. **p8** — structural plan (agreement-rich baseline)  
2. **p18** — multi-detail contamination stress  
3. **p24** — dense detail / L-callout stress  

Optional later: one ST framing page from another project (held-out style), still small.

### Sample construction

For each section-like label on these pages:

1. Build top‑K=5 PDF candidates (existing `spatial_index` / R&D retrieval).  
2. Attach relationship features.  
3. Attach production `nearest_geometry` as `production_reference` only.  
4. Attach `ghx_reference=null` until live export exists.  
5. Emit LabelGroup-compatible export for human review.

**Target volume:** 100–300 **candidate pair rows** (≈40–80 label groups × K), not thousands.

### Human review (required for gold)

Prioritize:

- Step 2 disagreements  
- Near-tie / ambiguous neighborhoods  
- `leader_resolved` cases  
- p18/p24 cross-detail suspects  

Review labels per existing guidelines: `direct_target`, `leader_support_not_target`, `not_target`, `no_valid_target`, `ambiguous_requires_adjudication`.

**Do not** ask reviewers to invent thickness or member role beyond what the drawing shows.

### Optional region overlay study

On p18/p24 only: human-draw 2–3 detail frames; compute IoU vs production X-gap vs R&D 2D. Regions remain features, not filters.

---

## Metrics to report

| Metric | Purpose |
|--------|---------|
| Candidate recall@5 vs gold | Gate for any future ranker |
| Production agreement rate vs gold | Baseline honesty |
| Leader-as-target rate (prod vs det scorer) | Leader architecture value |
| Cross-detail false association count | Region feature value |
| Abstain rate on near-ties | Safety |
| Ambiguity prevalence | Whether forced association is even sensible |

**Not primary:** accuracy vs GHX; text–member IoU.

---

## Decision gates

### Proceed to offline ML experiment only if all hold

1. ≥ ~100 gold label groups (or ≥ ~200 labeled pairs) with project IDs  
2. Candidate recall@5 is high enough that ranking is meaningful (measure; directional target >90%)  
3. Deterministic scorer either beats production on gold **or** clearly documents remaining error classes  
4. Eval split is project-safe; oracle is **human**, not GHX  

### Do **not** train if

1. Only GHX/production labels exist  
2. Recall@5 is poor (fix candidate gen first)  
3. Majority of cases are ambiguous/unresolvable from PDF  
4. Reviewer disagreement is high without adjudication  

---

## Deliverables of the experiment (future implementation phase)

- JSONL pack under `docs/validation/` (research)  
- Short results note: agreement taxonomy + gates pass/fail  
- Explicit go/no-go for pairwise GBT shadow  

**This document does not authorize that implementation.**

---

## Work split

| Owner | Work |
|-------|------|
| Mike | Step 1 corrected-PDF validation; live GHX RH_OUT capture when environment ready |
| Estima3D research | PDF candidate pack + human gold + deterministic evidence comparison |
| Both | Coordinate transform / page alignment only after RH_OUT exists |

---

## Time box suggestion

Smallest honest path: **reuse artifacts + review 50–108 existing prioritized groups** before writing new extractors. New code only if leader_path_ids / centerline / soft region features are missing for the review export.
