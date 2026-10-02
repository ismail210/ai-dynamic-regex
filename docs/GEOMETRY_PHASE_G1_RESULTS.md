# Geometry Phase G1–G6 Results (team demo)

**Project:** Burrville ES - ST (`doc_0d910a43b4a021e3`)  
**Harness:** `backend/scripts/rd_geometry_integration/run_prototype.py`  
**Demo page:** [docs/validation/rd_geometry_integration/comparison.html](../validation/rd_geometry_integration/comparison.html)  
**Production association:** **unchanged**

Blue = text bbox · green = new candidates / centerline · dashed orange = production `nearest_geometry`.

## G1 — Leader-aware evidence pack

75 section-like labels on p8 / p18 / p24. Retrieval excludes leaders as member targets and hops up to 3 nearby leaders.

| | G1 (leader-aware, show this) |
|--|--:|
| Labels | 75 |
| Agreement-family vs production | **56** |
| Disagreement | **3** |
| Ambiguous neighborhood | **34** |
| Leader as unconstrained top (G4) | **0** |

**What to tell the team:** we can retrieve a shortlist that usually contains production’s pick, and we can stop treating leader strokes as the member.

**Not claimed:** G1 is more accurate than production (no human gold yet).

## G2 — Detail extents (soft)

Title-seeded **research_proposed_frames** (from sheet lines, not human-drawn gold):

| Page | Frames | IoU vs production X-gap | IoU vs R&D 2D (examples) |
|------|-------:|-------------------------|--------------------------|
| 8 | 0 | n/a (plan, no TYPICAL DETAIL titles) | n/a |
| 18 | 7 | ~0.02–0.03 (full-page merge) | up to **0.84**, typically ~0.16–0.21 |
| 24 | 8 | ~0.01–0.02 | ~0.12–0.27 |

Contamination probe unchanged: **2** cross-region tops blocked on p18.

**Team line:** production X-gap is not a detail boundary. 2D + titles are promising **overlays / features**. Do **not** hard-gate.

Human gold frames: still empty (`human_gold_frames: []`). Reviewers can draw over the blue title-seeded boxes.

## G3 — Gold review kit

[docs/validation/rd_geometry_integration/review_kit/index.html](../validation/rd_geometry_integration/review_kit/index.html)

- **75** prioritized groups (all golden-page labels; disagreements first)
- Production pick hidden until “Reveal”
- First human gold: **75 / 75** groups in [`review_kit/gold_outcomes.jsonl`](../validation/rd_geometry_integration/review_kit/gold_outcomes.jsonl)
- Report: [`docs/validation/rd_geometry_integration/HUMAN_GOLD_REVIEW_REPORT.md`](../validation/rd_geometry_integration/HUMAN_GOLD_REVIEW_REPORT.md)

Recall@K among the 8 associated labels is in that report. Semantic Review stays **unwired**.

## G4 — Shadow scorer (vs production, not gold)

| Metric | Value |
|--------|------:|
| Labels | 75 |
| Shadow agree production | 23 |
| Shadow disagree production | 25 |
| Abstain (near-tie / leader / none) | 17 |
| Leader as unconstrained top | 0 |
| Gold groups / recall@5 | **8 associated / 1.00 on that set of 8** (see human-gold report; 58 visible members never entered candidates) |

**Team line:** the scorer can **abstain**. Do not treat 23/25 as accuracy.

## G5 — Workflow safety

- Unit test: geometry sidecar does not complete `L4X4` or flip takeoff eligibility — **pass**
- Corrected PDF for this doc is present on disk; live Mike stream compare remains **Mike’s** check
- See `g5_workflow_verify.json`

## G6 — Comparison page, not Semantic Review

`comparison.html` is the opt-in demo. Semantic Review production is **not** wired: human gold exists, but retrieval coverage is insufficient (see the human-gold report).

## How to re-run

```bash
cd backend
python -m pytest tests/test_rd_geometry_phase.py -q
python scripts/rd_geometry_integration/run_prototype.py
```
