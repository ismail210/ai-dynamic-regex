# Burrville Incomplete-L Evidence Investigation

**Date:** 2026-09-10  
**Scope:** Evidence-gathering only — no production changes, no incomplete-L gate changes, no ML/Graph/VLM enablement.  
**PDF:** `backend/uploads/Burrville ES - ST.pdf`  
**Document ID:** `doc_0d910a43b4a021e3`  
**Caches checked:** Aug 31 eval cache, post-incomplete-L refresh, engineering_artifacts multimodal predictions  
**Temporary renders:** `backend/training/eval_cache_backups/burrville_incomplete_L_evidence/`

---

## Executive finding

**Burrville does not present a Case-2 chain** of the form “plan prints incomplete `L4X4` → explicit deck/legend/detail maps it to `L4X4X1/4`.”

1. There are **no bare incomplete `L4X4` / `2L4X4` / `L5X3` (legs-only) callouts** in Burrville PDF text extraction or in any of the three prediction dumps for this document (**0 incomplete-angle rows** / 1,252 predictions).
2. Every extracted `L4X4…` callout already includes thickness.
3. **Both `L4X4X1/4` and `L4X4X3/8` appear** in the set, in **different roles** — a global `L4X4 → 1/4` rule is **unsafe**.
4. The **explicit deck-support note** specifies **`L3x3x1/4` deck support angles**, not `L4X4X1/4`.

Engineer intuition that “deck angles are often 1/4” is **Case E** for Burrville (contextual assumption), not Case 2.

---

## 1. Source materials

| Source | Path / ID |
|---|---|
| Burrville structural PDF | `backend/uploads/Burrville ES - ST.pdf` (29 pages) |
| Eval document id | `doc_0d910a43b4a021e3` |
| OLD predictions | `training/eval_cache_backups/doc_0d910a43b4a021e3/predictions_view.json` |
| NEW predictions | `training/eval_cache_backups/post_incomplete_L_abstention/doc_0d910a43b4a021e3/…` |
| Live artifacts | `training/engineering_artifacts/doc_0d910a43b4a021e3/multimodal/` |
| Page renders / text dump | `training/eval_cache_backups/burrville_incomplete_L_evidence/` |

Methods used: PyMuPDF full-text search of all 29 pages; visual inspection of rendered sheets S-002, S-205, S-203, S-207, roof plan / S-321; prediction-cache scan with `is_incomplete_angle_missing_thickness`.

---

## 2. Incomplete callouts on Burrville

| Query | Result |
|---|---|
| Bare `L4X4` (not followed by `X` thickness) in PDF text | **0** true hits |
| Bare `2L4X4` | **0** |
| Bare `L5X3` (legs-only) | **0** (hits are false positives from `L5X3-1/2X5/16`) |
| Incomplete-angle rows in NEW/OLD/artifact predictions | **0 / 0 / 0** |

**Implication:** There is nothing on Burrville for the current incomplete-L abstention gate to “resolve.” The incomplete `L4X4` / `2L4X4` / `L5X3` rows in the 8-doc evaluation came from **other** documents (e.g. GCDC, Springhill), not Burrville.

---

## 3. Complete `L4X4` evidence already printed (Case 1)

| Designation | Approx. PDF text hits | Example pages / sheets | Role (from surrounding text) | Evidence class |
|---|---:|---|---|---|
| `L4X4X3/8` | **14** | p13 (roof plan), p16 (S-203), p19 (S-206), p24 (S-321) | Horizontal bracing TYP; class angles; relieving angle; hangers / DSA / roof details | **A** — direct same-callout |
| `L4X4X1/4` | **4** | p18 (S-205), p20 (S-207) | Beam bottom-flange / cross brace TYP; interior wall-to-steel connection | **A** — direct same-callout |
| Shop/cut `L4X4X3/8X0'-8"` / `…X0'-6"` | 2 | p19, p23 | Cut lengths of **3/8** angles | **A** |

```text
L4X4 appears to map globally to one thickness: NO

Evidence:
- L4X4X3/8 is the majority complete callout (bracing, relieving, class angles, roof details).
- L4X4X1/4 appears only in specific typical details / wall connections.

Alternative L4X4 thicknesses found:
- 3/8  (dominant)
- 1/4  (minority, role-specific)
- (no L4X4X1/2 found in text extraction)
```

---

## 4. Deck / legend investigation

### 4.1 Sheet S-002 (p2) — General notes / legend

**DECK SUPPORT ANGLE** appears in the abbreviation legend (`DSA = DECK SUPPORT ANGLE`).

**Explicit steel-deck note (strongest deck-angle mapping on this set):**

> WHERE THERE IS NO BEAM FOR DECK TO BEAR, PROVIDE **`L3x3x1/4` DECK SUPPORT ANGLES** SUPPORTED BY THE NEAREST BEAMS.

| Claim | Supported? |
|---|---|
| Deck support angle defaults to `L4X4X1/4` | **NO** — drawing says **`L3x3x1/4`** |
| Legend maps symbol `DSA` → thickness | **NO** — abbreviation only; size is in the note above |
| Incomplete plan `L4X4` ↔ this note | **NO** — different size family (`L3X3` vs `L4X4`); no incomplete `L4X4` on plans |

Evidence class for deck support: **B/C** for `L3X3X1/4` only — **not** for resolving `L4X4`.

### 4.2 LINTELS schedule (S-002)

Opening-width → angle schedule (complete designations with thickness), e.g.:

- openings 3'-5" to 5'-0" → `L4X3-1/2X5/16` (LLV)
- openings 5'-1" to 6'-0" → `L5X3-1/2X5/16` (LLV)

This is **Case B** for **lintels**, not for deck `L4X4`. It does **not** map `L4X4 → 1/4`.

### 4.3 Sheet S-205 (p18) — `L4X4X1/4 TYP`

**TYPICAL BEAM BOTTOM FLANGE BRACE DETAIL** and adjacent cross-brace graphics explicitly label:

`L4X4X1/4 TYP`

Nearby text also mentions roof deck / SOMD (“SEE PLAN”).

| Question | Answer |
|---|---|
| Is `L4X4X1/4` present? | **YES** (Case A on the detail) |
| Does it define “all deck angles”? | **NO** — it defines this **brace** typical detail |
| Does a plan print bare `L4X4` that references this detail? | **NO incomplete `L4X4` found** |
| Same sheet also has generic `L ANGLE` / “HORIZ ANGLE BRACE, SEE PLAN”? | **YES** — thickness must come from the plan, not a global deck rule |

Relationship class if a future plan said only `L4X4` next to a bubble to this brace detail: would be **D/C** and would require an explicit detail reference. **That incomplete plan callout is not present on Burrville.**

### 4.4 Sheet S-207 (p20) — `L4x4x1/4` at walls

Interior wall between steel beams / joist framing: `L4x4x1/4` with spacing notes; adjacent lintel-like `L4x3x1/4x6"` pieces. Role = **wall connection**, not “generic deck edge angle.”

### 4.5 Roof plan / S-321 — `L4X4X3/8` near deck

Roof framing callouts: `L4X4X3/8 BRACING, TYP` with detail bubbles to S-321. Sheet S-321 repeats many **`L4X4X3/8`** (hangers, DSA-adjacent labels, sliding connections, etc.).

So the **deck-adjacent / roof** environment uses **3/8** heavily — opposite of a global 1/4 deck-angle assumption.

### 4.6 Desired engineer chain vs observed

**Desired (Case 2):**

```text
Plan: L4X4
  ↓ detail bubble
Deck Detail Dn: L4X4X1/4
  ↓
Resolved: L4X4X1/4
```

**Observed on Burrville:**

```text
Plan / details: already print L4X4X3/8 or L4X4X1/4 (complete)
Legend deck-support note: L3x3x1/4
No bare plan L4X4 found
No one-to-one incomplete→detail thickness map for L4X4
```

Second pattern from the task brief (“detail exists somewhere else with no explicit relationship”) would apply **if** incomplete `L4X4` existed — and must **not** auto-resolve. Here the incomplete side of the pair is missing entirely.

---

## 5. Evidence table (requested format)

| Incomplete callout | Page | Candidate thickness | Evidence location | Evidence type | Explicit relationship? | Confidence | Safe to auto-resolve? |
| ------------------ | ---: | ------------------- | ----------------- | ------------- | ---------------------- | ---------- | --------------------- |
| `L4X4` (bare) | — | — | **None found in Burrville PDF or caches** | F — no evidence | N/A | N/A | **NO** — callout absent |
| `L4X4` → `1/4` (hypothetical) | 18 | 1/4 | S-205 bottom-flange / cross brace `L4X4X1/4 TYP` | D — typical detail | **NO** plan incomplete callout to link | Low for global use | **NO** — role-specific; conflicts with 3/8 elsewhere |
| `L4X4` → `3/8` (hypothetical) | 13,16,24 | 3/8 | Roof bracing / class / relieving / S-321 | A/D — explicit complete or typical | N/A (already complete where printed) | High that 3/8 is common | **NO** as global map for bare `L4X4` |
| Deck support angle | 2 | **1/4 on L3X3** | S-002 steel deck note `L3x3x1/4 DECK SUPPORT ANGLES` | B — explicit note | Yes for **DSA / L3X3**, not `L4X4` | High for L3X3 | **NO** for `L4X4` |
| `L5X3` (bare) | — | — | Only `L5X3-1/2X5/16` lintel schedule | B — lintels | Opening-width schedule, not deck `L5X3` | High for lintels | **NO** for incomplete deck `L5X3` |
| `2L4X4` | — | — | **Not found** | F | N/A | N/A | **NO** |

---

## 6. Occurrence-level mapping

### Incomplete occurrences

```text
Occurrence: (none)
page: n/a
raw text: n/a
location: Burrville set has no incomplete L4X4 / 2L4X4 / L5X3 legs-only tokens in PDF text or prediction caches
nearby detail reference: n/a
candidate detail: n/a
candidate thickness: n/a
evidence source: full-PDF text search + 3 prediction dumps
relationship: n/a
safe automatic resolution: NO
reason: nothing to resolve; abstention gate never fires on this document
```

### Representative complete occurrences (for thickness diversity)

```text
Occurrence: roof bracing
page: 13
raw text: L4X4X3/8
location: roof framing plan near acoustic/roof deck
nearby detail reference: bubbles to S-321 (e.g. 3,6,7 / 2 S-321)
candidate thickness: 3/8 (already printed)
evidence source: plan callout Case A
relationship: complete printed section
safe automatic resolution: N/A (Case 1)
reason: thickness already on callout
```

```text
Occurrence: typical bottom flange / cross brace
page: 18 (S-205)
raw text: L4X4X1/4 TYP
location: typical detail sheet
nearby detail reference: this sheet IS the typical detail
candidate thickness: 1/4
evidence source: detail Case A
relationship: defines brace typical — not proven to govern unrelated plan L4X4
safe automatic resolution: only if a future incomplete callout explicitly references this detail (Case 2/C) — not present now
reason: role-specific; other roles use 3/8
```

```text
Occurrence: deck support note
page: 2 (S-002)
raw text: L3x3x1/4 DECK SUPPORT ANGLES
location: steel deck general notes
nearby detail reference: abbreviation DSA = DECK SUPPORT ANGLE
candidate thickness: 1/4 on L3X3
evidence source: Case B note
relationship: applies to deck support angles lacking a beam bearing — not to L4X4
safe automatic resolution: would be L3X3X1/4 for that condition, never L4X4X1/4
reason: wrong size family for the L4X4 question
```

---

## 7. Current pipeline comparison (no code changes)

Relevant production paths (actual locations):

- `backend/services/prediction/orchestrator.py` — incomplete-angle abstention gate
- `backend/services/prediction/label_ranker_hook.py` — `is_incomplete_angle_missing_thickness`, preserve core
- `backend/tests/test_incomplete_angle_abstention.py`
- `catalog_valid_exact_section` / TF-IDF exact-section retrieval
- `document_prior` (legend boosts; does **not** invent angle thickness)

### Why the pipeline abstains on `L4X4`

After shop/cut strip, `L4X4` is **not** a catalog-valid complete section. Previously, TF-IDF `predict_exact_sections` invented neighbors such as `L4X4X1/4` or even wrong family. The new gate **skips** TF-IDF / correction / document-prior completion, preserves `L4X4`, sets `missing_thickness`, and marks not takeoff-eligible.

### What information is available today

| Signal | Available? | Enough to pick 1/4 vs 3/8 on Burrville? |
|---|---|---|
| Printed token text | Yes | No thickness on incomplete tokens (and Burrville has none) |
| Document prior / legend pages | Partial (legend page detection) | Legend says **L3x3x1/4** for deck support — not L4X4X1/4 |
| Detail-bubble → sheet cross-reference | Not used as a thickness resolver | Missing for Case 2 |
| Schedule row linking member mark → section | Not for angles like this | N/A |
| Spatial “near deck” heuristic | Must not invent | Unsafe (3/8 and 1/4 both appear near deck language) |

### Is Burrville deck/legend evidence already in the pipeline?

- **Complete** `L4X4X1/4` / `L4X4X3/8` callouts: yes, as ordinary Case 1 exact text when printed.
- **Deck support `L3x3x1/4` note**: present in PDF text; **not** wired as a resolver for incomplete `L4X4`.
- **Cross-sheet typical-detail application to incomplete plan labels**: **not** implemented (and Burrville does not supply the incomplete side).

---

## 8. Case classification for Burrville

| Case | Present on Burrville? |
|---|---|
| **1 — Printed complete section** | **YES** — majority of angle work |
| **2 — Incomplete + explicit linked evidence** | **NO** — no incomplete `L4X4` + no one-to-one thickness link |
| **3 — Incomplete + general engineering assumption** | Engineer “deck ⇒ 1/4” idea is Case E; **contradicted** by multi-thickness + `L3x3x1/4` deck-support note |

---

## 9. Recommendation

## OPTION B — Evidence is insufficient

Keep the current incomplete-L abstention.

**Why not A:** Burrville never shows incomplete `L4X4` needing resolution, and even the complete evidence proves **multiple thicknesses**, so a deterministic `L4X4 → L4X4X1/4` (or “deck angle → 1/4”) rule would be **wrong** on this set.

**Why not C (for Burrville specifically):** A future detail-bubble / schedule cross-reference layer may be valuable on **other** projects that print incomplete angles and point to details — but Burrville does not provide the incomplete callouts or a reliable one-to-one map to validate that layer here. Implementing C on the basis of Burrville deck lore would be premature and risk encoding Case E as if it were Case 2.

**Do not add:** global `L4X4→1/4`, global deck-angle assumption, or any weakening of incomplete-L abstention.

---

## 10. Artifacts / safety

### Files created (investigation only)

- `backend/BURRVILLE_INCOMPLETE_L_EVIDENCE_INVESTIGATION.md` (this report)
- `backend/training/eval_cache_backups/burrville_incomplete_L_evidence/pdf_L_hits.json`
- `backend/training/eval_cache_backups/burrville_incomplete_L_evidence/page_renders/*.png`

### Files modified

- **None** (production code untouched)

### Tests run

- None (investigation-only; no behavior change)

### Confirmation

- Incomplete-L abstention **not** weakened  
- ML / XGB / GraphSAGE / VLM / geometry missing-label inference **not** enabled  
- No commit / push / reset / clean  
- Old evaluation caches **not** overwritten  
