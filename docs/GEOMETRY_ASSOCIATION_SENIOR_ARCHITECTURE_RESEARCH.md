# Geometry Association — Senior Architecture Research

**Status:** Research + architecture only. No production changes.  
**Date:** 2026-09-17  
**Scope:** Steps after Mike’s corrected-PDF validation; builds on existing geometry-graph audit, ML-association phase, Step 2/3 R&D, and GHX Phase 0D — **does not restart** those investigations.

**Core question answered:**  
*Can we reliably retrieve PDF geometry and constrain it to the correct drawing/detail region well enough to justify the next association implementation — and what is the best technically defensible path to text↔member association?*

**Verdict in one line:**  
Build **deterministic candidate generation + explainable evidence + human gold**, treat **GHX as silver/reference export (not GT)**, keep regions/leaders as **soft evidence**, and only later consider a **pairwise ranker** if gold data shows a measurable gap. **Do not train on GHX alone. Do not enable ML now.**

---

## 1. Executive Summary

### What we already have (evidence-backed)

| Layer | Reality in repo |
|-------|-----------------|
| PDF text | PyMuPDF `words` + `dict`/spans/blocks with bbox; **span/line rotation from `dir`**; word `rotation` is always `0.0` (`pdf_parser.py`) |
| PDF geometry | `page.get_drawings()` → objects with kind/bbox/orientation/length/points; dense-page cap **450** (`structural_first`) (`geometry_extractor.py`) |
| Normalization | Collinear fragment merge exists (`geometry_normalizer.py`); scale still largely raw PDF points |
| Production association | STRtree top‑K + leader-endpoint hop → **one** `nearest_geometry` edge (`spatial_index.py`, `graph_builder.py`) |
| Detail regions | X-gap clustering; Step 3 showed **1 region/page** on Burrville details — insufficient for multi-detail sheets |
| Semantic geometry contract | **Live:** `services.semantic.models.GeometryEvidence` (object) + `GeometryAssociation` (link, `review_status`/`reason_codes`). **Fixture/docs drift:** `GEOMETRY_EVIDENCE_CONTRACT.md` / synthetic fixtures describe annotation-embedded `association_status` enums not present on the live dataclass; `prediction/semantic_contract.py` is a deprecated re-export shim. GHX capture adapter exists but **no live RH_OUT** |
| Shadow ML dataset | `services/ml_association/` already implements **pairwise candidate rows**, review workflow, provenance — **not wired to production** |
| Step 2 R&D | On Burrville p8/18/24: 47/75 agreement-family vs production nearest; 34 ambiguous; leaders distort nearest-bbox |
| Step 3 R&D | Soft region constraint blocked 2 cross-region tops on p18 only — **too thin for hard gates** |
| Live GHX | **Blocked** — no `.ghx` in repo, no Rhino run, RH_OUT contract **UNRESOLVED** (`GHX_REAL_DRAWINGS_EXPERIMENT.md`) |

### Architectural conclusion

The desired end state is **not** “nearest line.” It is:

```text
semantic text (immutable meaning)
        ↓
geometry candidates (evidence only; role often unknown)
        ↓
relationship features + leader/region context
        ↓
rank / abstain / review
        ↓
verified association (human gold)
```

The training unit — if ML is ever justified — must be:

```text
(text, candidate_geometry, context) → {associated | not_associated | ambiguous}
```

**not** `text → geometry_id` and **not** “reproduce GHX pick.”

### What is *not* ready

- Treating GHX (or production `nearest_geometry`) as ground truth  
- Hard detail-region constraints in production  
- Inventing beam/column/brace roles from PDF lines  
- Geometry-driven section completion (`L4X4` → thickness)  
- GraphSAGE / VLM / XGB enablement  
- Training any model before a gold subset exists  

---

## 2. Current Architecture

```text
PDF (immutable)
 ├── pdf_parser → document.json (words/lines/blocks/tokens, bboxes, rotation)
 ├── geometry_extractor → geometry.json (primitives + heuristic kinds)
 ├── geometry_normalizer → merged fragments (when enabled in pipeline)
 ├── detail_regions → region_id on entities (X-gap; weak on vertical details)
 └── graph_builder + spatial_index → graph.json
        └── nearest_geometry edge (single pick; leader_resolved meta)

Semantic path (separate):
  extract → group → normalize/repair/abstain → SemanticAnnotation
  optional GeometryEvidence attachment (provider grasshopper|pdf|unavailable)
  association.py can fuse GHX pairing + PDF nearest — never rewrites label text

Prediction path:
  orchestrator owns section prediction; geometry graph mostly supplies scalar aggregates
  Excel / AISC = verify only

Shadow (disconnected):
  ml_association LabelGroup / AssociationCandidateRow / ReviewedOutcome
```

**Invariant preserved:** semantic meaning ≠ geometry retrieval ≠ association ≠ completion.

---

## 3. Current GHX Association Architecture

### What exists in Estima3D

| Artifact | Status |
|----------|--------|
| `estima3d_web_plan.ghx` | **Not in repository** |
| Live Rhino / Grasshopper | **Not available** in Phase 0D environment |
| `RH_OUT:*` live captures | **None** |
| `GrasshopperGeometryEvidenceProvider` | Consumes **already-captured** dict; maps `RH_OUT:BeamCrv`, `PlanColumnClosed`, etc. → typed geometry evidence |
| `associate_via_ghx_pairing` | Uses **explicit** text↔geometry pairs only; text disagreement → discrepancy note, **never** label rewrite |
| `fuse_candidates` | Agreement merge OR both candidates + `GHX_PDF_DISAGREEMENT` — **no forced winner** |
| 3DM/DWG adapters | Deferred / `NotImplemented` |

### What GHX is *documented* to produce (contract **aspirational**, not measured)

Expected capture keys (from provider + June/GHX audits — **unverified live**):

- `RH_OUT:BeamTxt`, `BeamCrv`, `BeamTxtUnpaired`, `BeamElementID`  
- `RH_OUT:PlanText`, `PlanCrv`, `PlanColumnClosed` / `Open`, `MiscBeamCrv`, `MomentRect`  
- Optional `*_paired_text` — **must not** assume list-index alignment  

### PointGrouping / MatchingTexttoCurve / DO / recovery

**UNKNOWN in-repo.** Names appear in stakeholder discussion / product intent, not as inspectable GHX source or measured RH_OUT. This research **must not invent** their algorithms. Any future GHX export spec should be written from a **live instrumented run**, not from memory of component names.

### Honest classification of GHX outputs (when they become available)

| Classification | When it applies |
|----------------|-----------------|
| Ground truth | **Never by default** |
| Silver / reference-system labels | Explicit BeamTxt↔BeamCrv pairs after capture validation |
| Heuristic labels | Any path that is nearest-curve / recovery / unmatched-fill |
| Mixed by route | Likely — primary match vs recovery vs DO/repeat logic |

Until route provenance is exported, treat **all** GHX associations as **mixed heuristic reference**.

---

## 4. Existing PDF Geometry Architecture

### Extraction (`geometry_extractor.py`)

- `page.get_drawings()` → path items classified by syntax/size into `line|polyline|curve|arc|circle|rectangle|path`  
- Narrow post-heuristics: `_looks_like_leader` (short thin strokes), `_looks_like_dimension` (length + nearby numeric text)  
- **No** beam/column/brace/grid/hatch semantic role from geometry alone  
- Dense-page cap currently **450** with structural-span-preferring retention strategies (historical bug: area-sort dropped axis-aligned members — partially mitigated; still a coverage risk)  
- Object fields include: geometry_id, kind, bbox, center, orientation, length, points, optional leader endpoints  

### Association (`spatial_index.nearest_geometry_candidates`)

1. Same-page (and same-region if set) STRtree query by bbox distance  
2. Skip dimensions; skip oversized sheet furniture  
3. If candidate is `leader`: hop to far **bbox corner** (approximation — not true polyline endpoint), re-query for non-leader/non-dimension target  
4. Prefer `leader_endpoint_resolved` sources, then structural kinds, then distance  
5. Return top‑K; **production graph keeps only #1** as `nearest_geometry`

### Known failure modes (measured)

- Leaders compete / contaminate (~28.8% leader-as-target class issues in ML-assoc pilot; leader-target investigation: reliability A only ~0.7% among graph docs)  
- Ambiguous neighborhoods (Step 2: 34/75)  
- Detail sheets: production regions collapse to 1  
- Primitive ≠ member; fragment members without merge  
- No scale-aware thresholds globally  

---

## 5. What GHX Can Export

### Recommended export contract (when Mike can run GH live)

For **each association attempt** (including rejects / unmatched):

| Field | Required? | Notes |
|-------|-----------|-------|
| `page` / sheet id | Yes | Align to PDF page |
| `text_content` | Yes | As GH saw it |
| `text_bbox` or anchor | Strongly preferred | Else PDF-side text match only |
| `geometry_id` / `BeamElementID` | Yes if paired | Stability must be measured across 2 runs |
| `geometry_type` / output name | Yes | BeamCrv vs Misc vs Column |
| curve points / bbox / length / orientation | Yes | For PDF↔Rhino alignment |
| `association_origin` / route | **Critical** | primary / leader / recovery / DO / unmatched |
| `candidate_set` + rejected | Highly valuable | Otherwise dataset learns only winners |
| distance / orientation features | If GH computes them | Reference features, not targets |
| confidence-like | Optional | Never treat as calibrated probability |
| ambiguity / conflict flags | If exist | Preserve abstention |

### Realistically obtainable vs speculative

| Obtainable with instrumentation | Speculative until measured |
|---------------------------------|----------------------------|
| Paired BeamTxt↔BeamCrv with shared element_id | Index-aligned lists without explicit pairing |
| Curve polylines + lengths | Perfect PDF↔Rhino transform without calibration points |
| Unpaired / misc lists | PointGrouping internals without source |
| Two-run ID stability test | “Confidence” semantics |

### GHX → JSON?

**Yes — export JSON as reference/provenance**, with route tags.  
**No — do not use that JSON as the ML target.**

---

## 6. GHX as Reference vs Ground Truth

### Critical question #1 answer

Training directly on GHX associations would teach the model to **reproduce GHX’s selection policy**, including:

- nearest-curve / greedy assignment bias  
- recovery fills that hide unmatched cases  
- crowded-geometry mistakes  
- detail-sheet cross-contamination (if GH also lacks regions)  
- any DO/repeat shortcuts  

That is classic **label leakage from a heuristic teacher**: the student becomes a faster copy of the teacher’s errors, and evaluation against GHX becomes circular.

**Technically:** GHX labels are **silver at best**, **bronze/heuristic when route is recovery**, and **never gold** without human verification.

### Danger statement

> If we train on GHX output, the model will largely learn to reproduce GHX’s mistakes wherever GHX is systematically wrong — especially leaders, dense framing, and recovery paths — while appearing accurate on metrics that use GHX as the test oracle.

---

## 7. Dataset Strategy

### Three strategies

#### Strategy A — GHX → direct training labels

- **Advantages:** scalable, fast  
- **Risks:** teacher bias; circular eval; silent false certainty  
- **Quality:** low–medium; unknown route mix  
- **Suitability for ML:** **Reject as first strategy**

#### Strategy B — GHX silver → human verification → gold subset → ML

- **Advantages:** humans focus on disagreements / ambiguous; GHX accelerates shortlist  
- **Risks:** anchoring bias (reviewers over-trust GHX pick)  
- **Quality:** gold where reviewed; silver elsewhere  
- **Suitability:** **Best first ML-oriented strategy *after* export exists**

#### Strategy C — GHX reference only; PDF geometry + human labels = training

- **Advantages:** cleanest truth; no Rhino dependency for gold  
- **Risks:** higher human cost; need good candidate recall  
- **Quality:** highest for PDF-native association  
- **Suitability:** **Best strategy for Estima3D PDF path today** (GHX live still blocked)

### Which FIRST?

**Strategy C first** (PDF candidates + human review), because:

1. Live GHX export is currently **blocked**  
2. `ml_association` already implements candidate groups + review protocol  
3. Step 2 shows PDF retrieval often surfaces production’s pick — candidates exist  
4. Excel remains **forbidden** as GT  

When GHX export becomes available, **upgrade to Strategy B** for Rhino-curve association research — still keep GHX out of the target field.

### Provenance hierarchy (recommended)

| Tier | Definition | Train? | Eval? | Explore? |
|------|------------|--------|-------|----------|
| **GOLD** | Human `ReviewedOutcome` with adjudication resolved | Yes (primary) | Yes (primary) | Yes |
| **SILVER_AGREE** | GHX route=primary **and** PDF top‑K contain same member **and** no conflict flag | Weak pretrain only / calibration | Secondary | Yes |
| **SILVER_GHX** | GHX pair only, route known, unverified | No (except ablation) | Reference baseline vs GHX | Yes |
| **BRONZE_HEURISTIC** | Production `nearest_geometry` only | No | Baseline comparison | Yes |
| **AMBIGUOUS / CONFLICT** | Explicit multi-candidate or GHX≠PDF | Train as abstain class | Yes | Yes |

---

## 8. Text Representation

### Authoritative bbox model

Keep **separate** fields:

| Field | Meaning |
|-------|---------|
| `source_word_bboxes[]` | Raw PyMuPDF words |
| `source_span_bboxes[]` | Dict spans (rotation-aware) |
| `grouped_text_bbox` | Union after semantic grouping (W8+X+10 → one label) |
| `semantic_bbox` | Contract bbox used in Semantic Review overlays |
| `text_rotation` | From **span** `dir` when available; do not trust word-level rotation (always `0.0` today) |

**Do not** silently replace originals with the union.

### Split labels

`W8` / `X` / `10` and `L4` / `X4` / `X` / `3/8` must use the **semantic grouper’s union bbox** as the association query bbox, while retaining fragment IDs for audit (fraction-suffix split defect noted in Phase 2.5 readiness).

### Hard cases

Rotated / stacked / dense detail / inside bubbles: association features must use centers + orientation + region, **not** IoU with member as primary signal.

---

## 9. Geometry Representation

### Comparison

| Representation | Retrieval | Association | Viz | ML | Notes |
|----------------|-----------|-------------|-----|----|-------|
| Raw PDF primitives | Base | Weak alone | Debug | Input | Keep always |
| Line segments | Good | Good | OK | Good | Fragmentation risk |
| Polylines / curve samples | Better for curves | Better | Good | Good | Prefer for centerline |
| Connected components | Member proxy | Strong | Strong | Strong | Needs merge rules |
| Axis-aligned bbox | Fast | Insufficient alone | Overlay | Feature | Can be huge for long beams |
| Oriented bbox + centerline | Best balance | Best | Best | Best | **Recommended hybrid** |
| Full local geometry graph | Context | Future | Heavy | GNN later | Defer |

### Minimal representation for next phase

```text
geometry_id
primitive_ids[]          # provenance
geometry_kind            # line/polyline/leader/... (NOT beam)
geometry_role            # unknown | leader_support | dimension_suspect | ...
bbox_aabb
centerline_polyline      # or endpoints + samples
orientation_deg
length_pdf_pt
region_id?               # soft
```

**Member geometry** is a **hypothesis over primitives**, not a PDF kind rename.

---

## 10. Member Bbox Strategy

| Approach | Pros | Cons | Use |
|----------|------|------|-----|
| A. Primitive bbox | Cheap, deterministic | Leaders/fragments wrong | Candidate feature only |
| B. Connected segments | Closer to member | Merge errors | Preferred deterministic |
| C. Full centerline bbox | Stable for long beams | Over-large AABB | + centerline for viz |
| D. Oriented bbox | Better for diagonal | More compute | Visualization + features |
| E. Cluster bbox | Catches assemblies | Over-merge | Soft only |
| F. After strip leaders/dims | Cleaner | Classification errors | Filter before bbox |
| G. GHX curve bbox | Rhino-quality | Coord frame; not PDF-native | Reference channel |
| H. Hybrid | Best | Needs clear provenance | **Recommended** |

**Recommended deterministic member bbox (PDF path):**

1. Start from candidate primitives (not leaders/dimensions).  
2. Optionally merge collinear fragments (`geometry_normalizer`).  
3. Emit `member_aabb` + `member_centerline` + `orientation` + `source_primitive_ids`.  
4. Never claim primitive bbox = member bbox without merge/role evidence.

---

## 11. Leader Architecture

### Prior evidence

- Production now prefers leader-resolved targets in candidate ranking.  
- Far endpoint ≈ bbox corner — coarse.  
- Winning edge often **does not store which leader** was used (`leader_path_ids` empty in ml_association).  
- Step 2 disagreements often look leader-related.  
- Leader→family for incomplete-L completion: **must stay unused** (investigation: 0 justification).

### Recommendation

Treat leaders as **explicit graph nodes / typed edges**, not as equal member candidates:

```text
TEXT --near--> LEADER --points_to--> MEMBER_CANDIDATE
TEXT --direct--> MEMBER_CANDIDATE
```

Leaders are:

- **routing mechanism** + **secondary evidence** (`leader_supported=true`)  
- **never** the association target for training (`leader_support_not_target` already in review guidelines)  
- **not** a completion signal  

Prefer a **leader graph** over treating all strokes equally.

---

## 12. Detail Region Architecture

### Prior evidence

- Production X-gap: 1 region on Burrville p8/18/24.  
- R&D 2D: multiple candidates but false splits; blocked 2 contaminations on p18 only.  

### Recommendation

```text
PAGE
 ├── detail_region_candidate A  (soft)
 ├── detail_region_candidate B
 └── title_block / sheet furniture (filtered)
```

**Initially regions must be:**

| Role | Now? |
|------|------|
| Feature / evidence (`same_region`, `region_available`) | Yes |
| Soft penalty in ranking | Yes (shadow) |
| Review-only overlay | Yes |
| Hard production filter | **No** |
| Candidate filter that drops all out-of-region | **No** until IoU vs human frames |

Plan pages may be **harmed** by over-segmentation — region features should be sheet-type aware.

---

## 13. Candidate Generation

Deterministic shortlist (K≈5–10):

1. Same page  
2. Exclude dimension / oversized furniture  
3. Direct proximity (bbox + point-to-line when points exist)  
4. Leader-hop targets  
5. Optional soft same-region boost (not hard drop)  
6. Orientation compatibility as score feature  
7. Always include **no_match** placeholder for review  

Preserve full candidate set in artifacts — never only the winner.

Step 2 / Phase 2.5: high candidate coverage is **plausible** (~96.5% top‑10 in pilot) but **unverified without gold**.

---

## 14. Feature Engineering

Train/score on **pairs**, not IDs:

**Text:** bbox, center, rotation, height, family, page, region  
**Geometry:** aabb, centerline, orientation, length, kind, endpoints, curvature proxy  
**Relationship:** centroid/bbox/perp distance, projection, overlap, parallelism, relative position, same_region, leader_supported, intervening density, candidate_rank, candidate_count  
**Context:** local line density, nearby steel labels  

**Forbidden features as model inputs:** GHX geometry_id, GHX selected bit, Excel, catalog completion hints that invent thickness.

GHX fields live only under `ghx_reference`.

---

## 15. Deterministic Association

Before any ML:

1. Generate candidates + features  
2. Score with transparent weighted rules (distance, leader support, orientation, soft region)  
3. **Abstain** on near-ties (existing 15% relative margin pattern in `association.py`)  
4. Emit evidence object for review UI  
5. Compare to production `nearest_geometry` and (later) GHX as **reference**, not truth  

Deterministic layer remains the **safety / explainability backbone** even if a ranker is added later.

---

## 16. ML Alternatives

| Option | Fit now | Notes |
|--------|---------|-------|
| A. Deterministic scoring | **Primary now** | Enough to start measuring |
| B. Logistic regression | Later | Needs gold; highly explainable |
| C. XGBoost / LightGBM pairwise/ranking | **First learned model if needed** | Matches existing repo tooling pattern |
| D. Pairwise ranking (LambdaMART-style) | Natural for LabelGroup | After gold ≥ few hundred pairs |
| E. Neural MLP | Optional | Marginal vs GBT on tabular |
| F–H. GNN / GraphSAGE | **Not justified** | Graph GT absent; teacher bias risk |
| I. VLM | **Not justified** for association core | Costly; non-auditable for production steel |
| J. Hybrid det + ML ranker | **Target end-state** | ML reorders candidates; det abstains / safety |

**Recommendation:** ML **later**, only after gold + candidate-recall gates. Prefer **pairwise ranking / GBT**, never geometry-ID classification, never GraphSAGE/VLM for this phase.

---

## 17. Dataset Provenance

See §7 hierarchy. Additional rules:

- Append-only human outcomes (already in `ml_association.outcome_store`)  
- Version independently: schema / candidate_generator / feature_generator / extraction  
- Record `candidate_generation_miss` explicitly  
- Project-level splits only (no page leakage across train/test)  
- Excel = never target, never feature for association GT  

---

## 18. Evaluation Framework

### Primary metrics (need gold)

- Candidate **recall@K** (release gate)  
- Association precision / recall / F1 on non-abstain  
- **Abstention rate** + abstention precision (were abstains truly hard?)  
- False-positive association rate (costly)  
- Leader confusion rate  
- Cross-detail contamination rate  
- Geometry-kind confusion (leader/dim selected as member)  

### Secondary

- Distance / orientation distributions for correct vs incorrect  
- Text bbox quality (group union vs fragments)  
- Member bbox quality vs human-drawn member extents (IoU on **member↔member**, not text↔member)  

### IoU for TEXT ↔ MEMBER?

**Generally inappropriate as primary metric** — labels sit beside members. Prefer:

- distance-to-centerline / perpendicular distance  
- leader endpoint consistency  
- projection along member  
- same-region consistency  

Use IoU for: text-group quality, region detection vs human frames, member-extent quality.

### Never score “accuracy vs GHX” as primary success.

---

## 19. Small Experiment

**Do not train.** Build a **100–300 pair** research pack:

| Page | Role |
|------|------|
| Burrville p8 | Plan |
| Burrville p18 | Multi-detail |
| Burrville p24 | Dense detail |

**Per label group:**

- PDF candidates (K=5) + features  
- Production `nearest_geometry` reference  
- GHX reference **if available** (else null)  
- Human review on prioritized disagreements / ambiguous / leader cases (~50–108 groups already prepared in ml_association pilot tooling)

**Success criteria for architecture (not model):**

1. Candidate recall@5 ≥ useful threshold on gold (target directionally >90%, measure not claim)  
2. Leader-as-target rate quantified and reduced in deterministic scoring  
3. Soft region feature separates ≥ some contamination cases without wrecking plan pages  
4. Agreement/disagreement taxonomy vs production documented  

Reuse: `docs/validation/rd_geometry_integration/`, `services/ml_association/`, Burrville artifacts `doc_0d910a43b4a021e3`.

---

## 20. Architecture Options

### Option 1 — Pure deterministic retrieval + evidence

**Flow:** PDF extract → candidates → rule score → abstain/associate → review  
**Pros:** explainable, shippable as evidence, no train risk  
**Cons:** brittle thresholds; scale sensitivity  
**Risk:** Low  
**Migration:** Shadow alongside `nearest_geometry`

### Option 2 — Deterministic candidates + ML ranking

**Flow:** Option 1 + pairwise ranker trained on **gold**  
**Pros:** handles non-linear feature interactions  
**Cons:** needs gold; can overconfident without abstain layer  
**Risk:** Medium if abstain weak  
**Migration:** Shadow ranker; production still det until held-out proof

### Option 3 — GHX reference + verified dataset + ML + deterministic safety

**Flow:** PDF path + GHX export as silver; humans resolve; ML ranks; det safety / conflict with semantic  
**Pros:** fullest long-term  
**Cons:** blocked on live GHX; dual coordinate frames  
**Risk:** High if GHX treated as GT  
**Migration:** Export-first; never replace GHX overnight

### Option 4 — Hybrid evidence engine (recommended)

```text
PDF semantic path ──┐
PDF geometry path ──┼→ region soft context → leader graph → candidates
GHX capture (opt) ──┘                         ↓
                                    relationship features
                                         ↓
                         deterministic evidence scorer
                                         ↓
                    confident | ambiguous | conflict | unavailable
                                         ↓
                              human verification (gold)
                                         ↓
                         offline pairwise ML experiment
                                         ↓
                              shadow eval on held-out projects
                                         ↓
                    controlled production only if gates pass
```

This matches the investigated target architecture (§22) with one critical correction: **regions stay soft**, **GHX stays optional reference**, **ML is offline until gold**.

---

## 21. Recommended Architecture

**Adopt Option 4.**

### Answers to the 20 mandatory questions

1. **Export GHX to JSON?** Yes, when live run possible — reference/provenance.  
2. **What to export?** See §5 table; route/origin and candidate/reject sets are critical.  
3. **GHX as GT?** No.  
4. **Human verification?** Create GOLD associations; mark leaders/not-targets/ambiguous; never invent section sizes.  
5. **ML target?** Pair label ∈ {associated, not_associated, ambiguous} / ranking relevance — **not** GHX id.  
6. **Predict IDs or rank?** **Rank / score candidates.**  
7. **Deterministic?** Extraction, candidate gen, leader hop, feature math, abstain rules, safety filters.  
8. **ML learn?** Reordering among candidates given features — not inventing geometry or text.  
9. **Leaders?** Explicit nodes/edges; support evidence; never training targets.  
10. **Regions?** Soft features / review overlays until human-framed IoU validates.  
11. **Text bbox?** Preserve fragments + grouped/semantic union separately.  
12. **Member bbox?** Hybrid aabb + centerline from non-leader primitives (+ merge).  
13. **Canonical association object?** See companion schema doc.  
14. **First dataset?** Burrville p8/18/24 pairwise candidates + human gold; GHX null until export.  
15. **Min experiment before training?** §19 gold pack + recall@K + taxonomy.  
16. **Justify training?** Gold ≥ ~200–300 labeled pairs, recall@K high, det baseline plateau, held-out project split ready.  
17. **Do not train if?** Only GHX labels; recall@K poor; majority ambiguous; eval oracle = GHX.  
18. **Remain in GHX?** Rhino-native curve quality, fabrication/takeoff geometry ops, existing estimator workflow until Estima3D proven.  
19. **Move into Estima3D?** PDF-native candidate evidence, review UI association, eventually ranked association for semantic sidecar — still not section invention.  
20. **Never auto-infer?** Section size/thickness; beam/column/brace without evidence; forcing winners under ambiguity; Excel-as-association-GT.

---

## 22. Migration Plan

| Phase | Work | Production? |
|-------|------|-------------|
| M0 | This research (done) | No |
| M1 | GHX export schema + one live capture (Mike) | No |
| M2 | Extend shadow dataset: leader_path_ids, soft region features, member_centerline | No |
| M3 | Human gold on 100–300 pairs (Burrville + 1 other ST) | No |
| M4 | Deterministic scorer shadow vs `nearest_geometry` | No |
| M5 | Offline pairwise GBT only if M3–M4 gates pass | No |
| M6 | Held-out project shadow | No |
| M7 | Controlled flag — evidence in Semantic Review only | Opt-in |
| M8 | Association influences takeoff **only** with explicit product approval | Later |

Mike Step 1 (corrected PDF → workflow) remains parallel and out of scope.

---

## 23. Risks

| Risk | Mitigation |
|------|------------|
| Teacher bias from GHX/production | Gold hierarchy; never train on heuristic alone |
| Leader bbox-corner hop errors | Store true endpoints on nodes; keep leader ids |
| Region false merge/split | Soft features; human frames |
| Dense-page cap dropping members | Coverage diagnostics; do not chase with ML |
| Reviewer anchoring to heuristic overlay | Blind options; show multiple candidates |
| Conflating association with completion | Contract tests already forbid; keep |
| Dual / triple GeometryEvidence shapes | Live semantic object evidence ≠ ml_association pairwise geometry evidence ≠ fixture `association_status` contract — align explicitly in any future schema work; do not silently merge |
| Unused association reason codes | `PDF_LEADER_INTERSECTION`, `ORIENTATION_MATCH`, `PROJECTED_OVERLAP` are defined in `association.py` but unused — do not assume they run in production |

---

## 24. Explicit Non-Goals

- Modify production GHX / Grasshopper association  
- Replace `nearest_geometry` in production this phase  
- Enable ML/VLM/GraphSAGE/XGB  
- Full 3DM converter  
- Large corpus training  
- Inventing geometry semantic roles  
- Geometry → section completion  
- Excel as association ground truth  
- Hard region gates in production  
- Restarting completed GHX deep-research as if unanswered (live run still blocked — that fact stands)

---

## 25. Open Questions

1. Live RH_OUT tree shape and BeamTxt↔BeamCrv pairing mechanism (still UNRESOLVED).  
2. BeamElementID stability across runs.  
3. PDF↔Rhino coordinate calibration method.  
4. Acceptable association error tolerance on dense connection details (domain).  
5. How to bound TYP / repeated callout scope.  
6. Grid-line vs member discrimination cues available in PDF.  
7. Whether plan sheets should disable region features entirely.  
8. Product decision: wire vs retire dead engineering matching modules (from geometry_graph_audit).  
9. Whether GHX recovery associations should be export-excluded from silver tier.  
10. Minimum gold N for first GBT experiment on this domain (estimate 200–300 pairs — validate empirically).  
11. Reconcile live `GeometryAssociation` vs fixture/docs `association_status` GeometryEvidence contract before any production sidecar claims one schema.  
12. Whether word-level rotation should be backfilled from overlapping spans (today words always store `0.0`).

---

## Critical evaluation of the proposed target diagram (§22 of brief)

The staged pipeline (semantic ∥ geometry → region → leader → candidates → det ∥ ML → associate → review → dataset → shadow → production) is **directionally correct**.

**Required modifications:**

1. Region block = **soft evidence**, not a hard partition.  
2. ML block = **offline until gold**; not parallel-equal to deterministic at day one.  
3. GHX enters as optional third input to reference/provenance, not as a primary geometry path replacing PDF.  
4. Ambiguity/conflict must be first-class outputs (live path: `GeometryAssociation.review_status` + reason codes / fuse disagreement; fixture `association_status` is aspirational until reconciled).  
5. Completion remains outside this diagram entirely.

---

## References (inspected, not re-executed)

- `docs/GEOMETRY_RETRIEVAL_COMPARISON.md`, `docs/DETAIL_PAGE_EXTENTS_PROTOTYPE.md`  
- `docs/validation/rd_geometry_integration/`  
- `docs/geometry_graph_audit/00–09`  
- `docs/ml_association_phase/*` (schema, phase3 readiness, annotation guidelines)  
- `backend/GEOMETRY_EVIDENCE_CONTRACT.md`, `backend/GHX_REAL_DRAWINGS_EXPERIMENT.md`, `backend/GRAPH_LEADER_TARGET_INVESTIGATION.md`  
- Code: `pdf_parser.py`, `geometry_extractor.py`, `geometry_normalizer.py`, `detail_regions.py`, `spatial_index.py`, `graph_builder.py`, `semantic_preprocessor/{geometry_evidence,association}.py`, `services/ml_association/*`, `services/semantic/models.py`
