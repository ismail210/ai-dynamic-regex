# Geometry Extraction Audit — Burrville ES ST, pages 8 / 18 / 24

**Status: investigation only.** No production code was modified, no Retrieval V3 was built, no
gold record was changed, and no accuracy improvement is claimed.

- Document: `doc_0d910a43b4a021e3` (Burrville ES - ST)
- Pages audited: p8 (framing plan), p18 (connection details + splice schedule), p24 (sections)
- Cases: 21 (18 failures + 3 controls)
- Script: `backend/scripts/rd_geometry_integration/extraction_audit.py`
- Data: `extraction_audit.jsonl`, `extraction_audit_summary.json`
- Renders: `extraction_audit_renders/` (blue = label, green = retained raw, **red = raw dropped by
  the dense-page cap**, purple = leader/tip, magenta = gold)

### Method and why the stage attribution is trustworthy

The audit replays the production extraction stages *by calling the production helpers*
(`_select_under_dense_cap`, `_classify_path`, `_looks_like_leader`, `_looks_like_dimension`,
`_gid`, `merge_collinear_fragments`) in production order, then checks the replay against the
shipped artifact. The replayed post-merge `geometry_id` set is **identical** to
`multimodal/geometry.json` on all three pages (435/435, 433/433, 392/392). Every claim below about
"this primitive was dropped here" is therefore a statement about the real pipeline, not a model of it.

Visual evidence is a human reading of the rendered crops, held to the same standard as the human
gold review: what the PDF visibly intends. Where a primitive is merely *near* the label but visual
evidence does not confirm it is the named member, it is recorded as "nearby only", never as a
recovery.

---

## 1. Executive Summary

**The missing visible members are overwhelmingly present in the raw PDF geometry. They are lost
after extraction, at two specific stages, and the larger of the two is the dense-page cap.**

Of 21 audited cases, **21/21 have the relevant geometry present in the raw `page.get_drawings()`
output**. Not one case was `RAW_GEOMETRY_MISSING`. The losses are:

1. **The 450-path dense-page cap** (`_DENSE_PAGE_CAP`) discards 87–91% of each page before anything
   else runs: p8 keeps 450 of 3586 paths, p18 keeps 450 of 5300, p24 keeps 450 of 4749. On the
   detail sheets this deletes whole neighborhoods. At the visually identified WT for
   `token_p18_1186`, 137 raw primitives lie within 22pt and **2** survive. At the splice plate for
   `token_p18_1162`, 198 lie within 22pt and **6** survive. For `token_p24_1385`, *every* primitive
   within 25pt of the true arrow tip is dropped.
2. **Classification of retained member strokes as `dimension` or `leader`**, which removes them
   from candidate eligibility. On p8 the retained set is 270 `leader` + 65 `dimension` + 72 `line`
   out of 435 objects — so a framing plan with ~50 labelled members retains only 72 usable `line`
   candidates.

A population scan of all 50 gold labels on p8 (not just the sampled cases) quantifies this. Every
one of the 50 labels has an on-segment stroke of length ≥ 25pt sitting a median of **8.98pt** away
(p90 = 12.08pt) — the sheet places each label a fixed offset from the member it names. The fate of
those 50 strokes:

| Fate of the stroke each p8 label sits on | Count |
| --- | ---: |
| Retained, but classified `dimension` | 27 |
| Dropped by the dense-page cap | 14 |
| Retained as `line` (usable candidate) | 9 |
| Not present in raw geometry | **0** |

So on p8 the member stroke exists for 50/50 labels and 41/50 are destroyed by the cap or by
classification. This is a coverage problem created inside our own pipeline, not a limitation of the
PDF.

Two further findings change the working hypothesis:

- **The giant-polyline theory does not hold for these cases.** `token_p8_348` (W30X90), the
  flagship "bay window" case, is not inside a bay polyline at all: the girder is its own 324pt raw
  line, retained as `geom_f35a9d1c5bd7`, and merely *classified as a dimension*. Separately, every
  p8/p18/p24 primitive with extent > 600pt has only 2–6 points, so they are simple long paths, not
  compound bays. Segmenting them would produce 1–5 sub-segments, not missing members.
- **What the leader logic latches onto on p18/p24 is frequently a weld-symbol reference line**, not
  a pointer to a member. `token_p18_1162`, `token_p24_1361` and `token_p24_1377` all show a
  retained 67.7–67.8pt horizontal "leader" that is the weld symbol's reference line, while the real
  pointer strokes are either cap-dropped or retained under the `dimension` label.

Evidence is *insufficient* to claim that fixing these two stages would produce correct
associations. It is sufficient to state the factual boundary the audit was asked for: **the correct
geometry is available in the current PDF representation for the members we are missing.**

---

## 2. Case Inventory

"Candidate reached" means *the visually correct member* reached candidate generation. "nearby only"
means some local primitive reached candidates but visual evidence does not support it as the named
member.

| Token | Page | Label | Visual member | Raw geometry found | Candidate reached | Primary failure |
| --- | --- | --- | --- | --- | --- | --- |
| `token_p8_355` | p8 | W10X15 | short W10X15 infill joist | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p8_348` | p8 | W30X90 | W30X90 diagonal girder | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p8_337` | p8 | W21X44 | W21X44 girder | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p8_381` | p8 | W18X35 | W18X35 joist (parallel bay) | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p8_430` | p8 | W18X35 | W18X35 joist (parallel bay) | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p8_332` | p8 | W14X22 | W14X22 opening-frame edge | yes | nearby only | `EXTRACTED_BUT_FILTERED` |
| `token_p8_346` | p8 | W10X15 | short W10X15 joist | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p8_359` | p8 | W18X40 | W18X40 joist (parallel bay) | yes | **yes** | `EXTRACTED_BUT_RETRIEVAL_MISS` |
| `token_p8_351` | p8 | W18X35 | W18X35 near slab edge | yes | nearby only | `DRAWING_AMBIGUITY` |
| `token_p8_340` | p8 | W21X44 | W21X44 wall beam — **control, associated** | yes | yes | `OTHER` (no failure) |
| `token_p8_367` | p8 | W14X22 | stair-opening node — **control, ambiguous** | yes | nearby only | `DRAWING_AMBIGUITY` |
| `token_p18_1186` | p18 | WT7X19 | WT7X19 stem below beam | yes | no | `EXTRACTED_BUT_FILTERED` |
| `token_p18_1178` | p18 | L4X4X1/4 | L4X4X1/4 brace angle | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p18_1169` | p18 | PL 1 1/2" | shear plate between beam and column | yes | **yes** | `EXTRACTED_BUT_RETRIEVAL_MISS` |
| `token_p18_1162` | p18 | PL 3/8" | column splice plate | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p18_1143` | p18 | W10X33 | splice-schedule cell — **control, not a member** | n/a | n/a | `OTHER` (no member) |
| `token_p24_1361` | p24 | L4X4X3/8 | hanger angle right of joist | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p24_1360` | p24 | L4x4x3/8 | continuous angle | yes | nearby only | `EXTRACTED_BUT_FILTERED` |
| `token_p24_1377` | p24 | L4x4x3/8 | DSA angle lower-left | yes | no (excluded) | `EXTRACTED_BUT_FILTERED` |
| `token_p24_1359` | p24 | L6x3-1/2x3/8 | angle at wall | yes | nearby only | `EXTRACTED_BUT_FILTERED` |
| `token_p24_1385` | p24 | L4x4x3/8 | angle at slab-edge corner | yes | no | `EXTRACTED_BUT_FILTERED` |

---

## 3. Stage-by-Stage Findings

### 3.1 p8 — plan sheet, label sits on its member

The p8 failures share one shape, so they are described once and then differentiated.

**Visual.** The framing plan sets each member label along the member line, offset by roughly one
text half-height (measured median 8.98pt across all 50 p8 gold labels). The label is *on* its
member; no leader is involved.

**Raw PyMuPDF.** The member is a single `l`-item path, usually 70–330pt long and diagonal (the plan
is rotated). Present for 50/50 labels.

**Normalization.** Faithful when the path survives the cap: the bbox, point list and length are all
preserved, and `merge_collinear_fragments` only merged 12 clusters on the whole page.

**Filtering (the cap).** 3136 of 3586 paths are removed before classification. 14 of the 50 label
strokes die here, including `token_p8_355` (67.7pt joist, `structural_keep_score` 10065.4 — a real
member scored below 450 other paths) and `token_p8_346` (75.0pt joist).

**Classification.** Of the 36 label strokes that survive the cap, 27 are relabelled `dimension` by
`_looks_like_dimension`, because a structural label such as `W21X44 [30]` or `c = 3/4"` contains
digits and sits within the nearby-text radius of its own member. The member is rebranded as an
annotation *by the text that names it*. A second variant appears on short joists: the 18pt
fragments of `token_p8_355`'s joist are retained but relabelled `leader` by `_looks_like_leader`.

**Candidate generation.** `dimension` and `leader` are not eligible member strokes, so for
`token_p8_348`, `_337`, `_381`, `_430`, `_346`, `_355` the correct geometry never reaches the
candidate set. `token_p8_355` ends with zero candidates, which is exactly consistent with the
observed "zero R&D candidates" symptom.

**Retrieval.** Not reached. Retrieval cannot be blamed for these.

Differentiated cases:

- **`token_p8_348` (W30X90)** — the case previously filed under "giant polyline / bay window". The
  girder is its own 324pt raw line (bbox 280.6 × 162.0 because it is diagonal), retained as
  `geom_f35a9d1c5bd7`, classified `dimension`. The bay polyline is a *separate* object. V2's
  reclassification rescue missed it because V2 tests thinness on the axis-aligned bbox, and a
  diagonal member has a fat bbox in both axes. Primary failure `EXTRACTED_BUT_FILTERED`, not
  `GIANT_PRIMITIVE_REPRESENTATION`.
- **`token_p8_332` (W14X22)** — five local strokes; four cap-dropped, the nearest retained one
  classified `dimension`. A different retained `line` (`geom_398d64922bf2`) *does* reach candidates,
  which is how V2 scored this as proxy-covered; the render shows the framed edge under the label is
  red (dropped), so this is a "nearby only", not a recovery.
- **`token_p8_359` (W18X40)** — the one p8 case where the pipeline works up to retrieval. The joist
  is retained *and* classified `line` (`geom_9027619e697a`), sits 8.9pt from the label center,
  on-segment, and is in the V2 candidate set. This is a genuine
  `EXTRACTED_BUT_RETRIEVAL_MISS`.
- **`token_p8_351` (W18X35)** — no stroke at the sheet's ~9pt convention distance; the nearest
  retained line is 20.8pt away, between the slab edge and the adjacent `W12 [8]` line. Visual
  evidence does not identify a unique target → `DRAWING_AMBIGUITY`.
- **Control `token_p8_340`** — human-associated; the gold stroke `geom_095898d74240` is retained and
  in the candidate set, and retrieval ranks it first. Shows the path is sound when classification
  does not intervene.
- **Control `token_p8_367`** — human abstention at a stair-opening node; several retained strokes,
  none uniquely indicated.

### 3.2 p18 — connection details

**Visual.** Labels are callouts. Two distinct attachment idioms appear: a plain leader with an
arrow (`token_p18_1186`), and a **weld symbol** whose horizontal reference line carries the text
while a separate arrow points at the part (`token_p18_1162`).

**Raw PyMuPDF.** Dense: 5300 paths, 2317 of them zero-area and 2484 tiny. The detail assemblies —
plates, bolt circles, arrowheads, angle legs — are all present.

**Filtering (the cap).** 4850 of 5300 removed. This is where the p18 details die:

| Case | Raw primitives within 22pt of the visual target | Retained |
| --- | ---: | ---: |
| `token_p18_1186` (WT stem) | 137 | 2 |
| `token_p18_1162` (splice plate) | 198 | 6 |

**Leader analysis.**

- `token_p18_1186`: LABEL → the single diagonal leader (51.1pt, bbox 47.2 × 19.7) → arrow tip at the
  WT stem → WT geometry. The **leader stroke itself is cap-dropped**, so no chain exists in the
  retained representation. Problem type: *leader not extracted*.
- `token_p18_1178`: LABEL → 14.5pt stub (cap-dropped) → target cluster (30.1pt, 89.4pt — both
  cap-dropped). Nothing local survives except an unrelated `leader`. Problem type: *leader not
  extracted*.
- `token_p18_1162`: LABEL → retained 67.7pt horizontal `leader` — which visual inspection shows is
  the **weld-symbol reference line**, ending at the weld triangle, not at a member. The two 18pt
  (12.7 × 12.7) fragments at its far end are arrowhead halves, and they are cap-dropped. The real
  arrow toward the splice plate (63.7pt and 48.1pt strokes) is also cap-dropped. Problem type:
  *endpoint resolves to the wrong structure because the true pointer was not retained*.
- `token_p18_1169`: the exception. LABEL → weld reference line → the tall shear plate, which **is**
  retained as `geom_4e68ef0da179` (rectangle, 37.8 × 112.6) and **is** in the V2 candidate set. The
  render shows the green rectangle sitting exactly where `PL 1 1/2" (Fy = 50 ksi)` points. Correct
  geometry present, extracted, and in candidates → `EXTRACTED_BUT_RETRIEVAL_MISS`.

**Control `token_p18_1143`** is a `STEEL COLUMN SPLICE` table cell; the only local stroke is a table
rule retained as `dimension`. Correctly has no member.

### 3.3 p24 — sections and clip details

**Visual.** Almost every audited p24 label is a small angle (clip, hanger, DSA, continuous angle)
reached by a leader, frequently combined with a weld symbol.

**Raw PyMuPDF.** 4749 paths, 2191 zero-area. Angles, arrowheads and leader continuations are all
present in raw.

**Filtering (the cap).** 4299 of 4749 removed. Every audited p24 case loses either its pointer, its
target, or both:

- `token_p24_1385`: the leader is drawn as a short 29.9pt stub **plus** a diagonal continuation; the
  continuation, the 12.6pt segment and the 93.4pt angle at the true arrow tip are all cap-dropped.
  Zero retained primitives within 25pt of the tip. Problem type: *leader fragmented, continuation
  not retained*.
- `token_p24_1360`: all four label-anchored strokes cap-dropped; at the visual target, 47 raw
  primitives with 13 retained, none of which is the angle. Problem type: *leader not extracted*.
- `token_p24_1359`: label-anchored strokes (10.9pt, 41.3pt) cap-dropped; the only retained neighbour
  is a 405pt wall line 21pt from the tip — "nearby only". Problem type: *leader not extracted*.
- `token_p24_1361`: the retained 67.8pt "leader" is the weld reference line for `L4X4X3/8 HGR, TYP`.
  At the hanger angle itself, 16 raw primitives exist, 4 retained — and all 4 are classified
  `dimension`. So even where the target survives the cap, classification removes it. V2's
  leader-target hop landed on joist/hatch geometry; visual QA rejects it. Problem type: *endpoint
  wrong (weld symbol) and surviving target misclassified*.
- `token_p24_1377`: the genuine pointer strokes toward the DSA angle **are** retained
  (`geom_ae18c735015e` 116.1pt, `geom_7bdc3406efaa` 110.4pt) but are classified `dimension`, so the
  leader logic never considers them; at their far end the angle's own strokes (72.0pt, 21.5pt,
  13.0pt) are cap-dropped. Problem type: *true pointer retained but classified as a dimension*.

---

## 4. Failure Distribution

| Class | Count |
| --- | ---: |
| `RAW_GEOMETRY_MISSING` | 0 |
| `RAW_GEOMETRY_PRESENT_NOT_NORMALIZED` | 0 |
| `COMPOUND_PATH_NEEDS_SEGMENTATION` | 0 |
| `EXTRACTED_BUT_FILTERED` | 15 |
| `EXTRACTED_BUT_RETRIEVAL_MISS` | 2 |
| `LEADER_ENDPOINT_FAILURE` | 0 |
| `LEADER_TARGET_GEOMETRY_MISSING` | 0 |
| `GIANT_PRIMITIVE_REPRESENTATION` | 0 |
| `DRAWING_AMBIGUITY` | 2 |
| `OTHER` | 2 (both controls: one working association, one schedule cell) |

Note on the leader classes. Nine audited cases are leader-driven, and it would have been easy to
file them under `LEADER_ENDPOINT_FAILURE` or `LEADER_TARGET_GEOMETRY_MISSING`. They are filed under
`EXTRACTED_BUT_FILTERED` because in every one of them the leader stroke, the arrow tip geometry, or
the target was **removed by the dense-page cap or by classification** — the leader logic is
operating on a representation from which the evidence has already been deleted. The per-case
leader problem type is recorded in `extraction_audit.jsonl` (`evidence_notes`,
`leader_endpoint_status`, `target_geometry_status`) so the distinction is not lost:

| Leader problem type | Cases |
| --- | ---: |
| Leader stroke not retained (cap) | 5 |
| Leader fragmented, continuation not retained | 1 |
| Weld-symbol reference line mistaken for the leader | 2 |
| True pointer retained but classified `dimension` | 1 |

---

## 5. Recoverability

Conservative, and deliberately separated from any claim about accuracy.

- **Clearly recoverable with deterministic extraction/normalization changes — 12 cases.** The
  geometry is in raw, is member-scale, and is removed by a cap or classification rule we control.
  Retaining it is a bounded change with a measurable outcome (does the stroke appear in
  `geometry.json`), independent of whether retrieval then picks it.
- **Already available but retrieval misses — 2 cases** (`token_p8_359`, `token_p18_1169`). Correct
  geometry proven to be in the candidate set.
- **Potentially recoverable with better leader endpoint handling — 3 cases.** These need the weld
  symbol to be distinguished from a leader, and pointer strokes currently labelled `dimension` to be
  usable as pointers. Both depend on the extraction fix landing first.
- **Potentially recoverable with segmentation — 0 cases.** No audited case had its member buried
  inside a compound path. Giant primitives on these pages carry 2–6 points.
- **Not recoverable from current raw PDF geometry — 0 cases.**
- **Visually ambiguous — 2 cases** (`token_p8_351`, control `token_p8_367`).
- **Not a member — 1 case** (control `token_p18_1143`).
- **No failure — 1 case** (control `token_p8_340`).

What this does *not* establish: that retaining these primitives yields correct associations. The
cap exists for a reason (bounded graph construction on 3–5k-path pages), and retaining more
primitives will also retain more distractors. Those are questions for the next experiment, not
conclusions of this audit.

---

## 6. Recommended Next Experiment

**Recommendation: A — an extraction/normalization experiment. Do not build Retrieval V3.**

Ranking was already shown not to be the bottleneck (baseline and V2 both hit 8/8 Recall@1). This
audit shows why: on the sampled failures the correct geometry usually never arrives. Two upstream
rules account for 15 of 18 failures.

The smallest deterministic experiment that would settle it, run shadow-only on these three pages:

1. **Measure the cap's cost directly.** Re-extract p8/p18/p24 with `_DENSE_PAGE_CAP` raised (or with
   a label-aware retention pass that always keeps paths within a small radius of an engineering
   token), and report only extraction-level metrics: how many of the 50 p8 label strokes survive,
   how many primitives survive within 22pt of each leader tip, and the resulting object count and
   extraction wall-time. No retrieval, no ranking, no accuracy claim.
2. **Measure the classification cost directly.** With the cap unchanged, count how many retained
   strokes flip from `dimension`/`leader` to `line` when `_looks_like_dimension` is not allowed to
   fire on text that is the member's own label. Report the flip count and, critically, the
   false-flip count on real dimension lines.

Success criterion to state up front: extraction-stage recall of the label-local member stroke on p8
rises from the current 9/50 toward the 50/50 that exists in raw, without the page object count or
extraction time growing beyond what graph construction can absorb. Only if that holds does a
candidate-eligibility or leader experiment become worth running, and only after that does any
retrieval work make sense.

Both probes are diagnostic-only and belong in `backend/scripts/rd_geometry_integration/`. Neither is
implemented here.

---

## Artifacts and safety

Created (all R&D-only):

- `backend/scripts/rd_geometry_integration/extraction_audit.py`
- `docs/validation/rd_geometry_integration/GEOMETRY_EXTRACTION_AUDIT.md` (this file)
- `docs/validation/rd_geometry_integration/extraction_audit.jsonl`
- `docs/validation/rd_geometry_integration/extraction_audit_summary.json`
- `docs/validation/rd_geometry_integration/extraction_audit_renders/` (21 crops)

Intentionally untouched: `backend/services/` (all production extraction, retrieval, association,
GHX, semantic review, takeoff, ML), `backend/scripts/rd_geometry_integration/retrieval.py`,
`retrieval_v2.py`, `nearest_geometry`, and `review_kit/gold_outcomes.jsonl`.

Human gold integrity: `gold_outcomes.jsonl` SHA-256
`0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`, verified before and after each
audit run; the script aborts if it changes. No geometry ids were assigned to gold records that
intentionally have none.
