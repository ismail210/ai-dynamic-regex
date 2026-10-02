# Geometry Phase Charter (G0)

**Status:** Build phase, evidence-only until gates pass.  
**Demo project:** Burrville ES - ST (`doc_0d910a43b4a021e3`)  
**Pages:** p8 plan · p18 S-205 details · p24 S-321 sections  
**Date:** 2026-09-17

## One-sentence goal

Ship a **text ↔ member-geometry evidence pipeline** the team can see (boxes, candidates, abstain) without replacing GHX, inventing section sizes, or treating nearest/GHX as ground truth.

## Owners

| Stream | Owner | Work |
|--------|-------|------|
| A | Mike | Corrected PDF → existing workflow; GHX JSON export when Rhino is available |
| B | Estima3D | Candidates, soft regions, gold kit, shadow scorer, team demo pack |

## Baseline (already measured)

- Step 2: **47/75** agreement-family with production `nearest_geometry`; **8** disagree; **34** ambiguous (leaders often win raw nearest-bbox).
- Step 3: production X-gap = **1 region/page**; R&D 2D = 6/12/13 candidates; **2** cross-detail tops blocked on p18 only.
- Human gold associations: **0**.
- Live GHX / RH_OUT: **blocked**.

## What “improvement” looks like in a meeting

1. Overlay: label bbox + member bbox/centerline + top-5 candidates.  
2. Side-by-side: production pick vs new candidates (agree / disagree / abstain).  
3. Detail sheets: region boxes as **soft** context, not a hard gate.  
4. Review kit: humans mark associated / leader / ambiguous.  
5. Workflow: geometry sidecar does **not** change `L4X4` or takeoff eligibility.

## Gold is human. GHX and nearest are reference only.

## Non-goals

No production GHX change · no GraphSAGE/VLM/XGB · no train-on-GHX · no Excel-as-GT · no `line`→`beam` · no thickness completion · no hard region filter · no full-corpus run.

## Gates

| Gate | Pass |
|------|------|
| G1 | Reproducible overlays + comparison JSON for 3 pages |
| G2 | Title-seeded / proposed frames scored vs auto regions; region stays soft |
| G3 | ≥50 human gold groups (kit ready; collection is human) |
| G4 | Shadow scorer vs production; recall@5 and abstain reported |
| G5 | Geometry attach cannot rewrite text/completion (Mike stream parallel) |
| G6 | Dedicated comparison page (Semantic Review production wiring **only after** G3–G4) |
