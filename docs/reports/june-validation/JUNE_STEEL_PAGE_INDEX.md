# JUNE STEEL-RELEVANT PAGE INDEX — Phase 0C

**Date:** 2026-09-12  
**Corpus:** `backend/Testing Projects/` (existing Phase 0B set; **no copies / renders / duplicates**)  
**Inputs:** `backend/JUNE_CORPUS_AUDIT.md`, `backend/testing_projects_manifest.json`  
**Method:** Conservative full-text scan with **strict** `W##X##`, `HSS…`, complete `L/2L…Xthickness` patterns; incomplete L only when steel context co-occurs.  
**This file only.** No production code, flags, datasets, screenshots, or PDF copies.

---

## FINAL VERDICT

**PASS**

---

## Method notes (read before using the index)

| Rule | Detail |
|---|---|
| **OBSERVED** | Extracted page text supports the claim |
| **UNKNOWN** | Sheet number / title not reliably extractable, or evidence too weak |
| **Provisional sheet IDs** | Regex may pick up **detail callouts** (e.g. `S-401`) rather than the sheet title-block number. Treat sheet columns as hints until human-confirmed |
| **Not steel** | Bare `L` / room tags / generic dimensions alone → **excluded** |
| **Excluded from validation** | Hart MS “incomplete L” pages (architectural tags); Thomas / Fort Lincoln HSS-only partition/handrail details |

Scanner kept **68** candidate pages; after confidence filtering, **usable structural material** concentrates in **River Road (25)**, **Burrville DD (20)**, **SOME (7)**, plus light coverage in MARS / William Winchester.

---

## 1. Project coverage matrix

| Project | Structural PDF present? | Structural pages found | Confidence | Notes |
|---|---|---:|---|---|
| `18 - River Road` | **No dedicated ST PDF** (Arch addendum) | **25** | **High** | Embedded structural framing/details; **real incomplete `L4X4`/`L5X3`** |
| `51 - Burrvile ES` | **No dedicated ST PDF** (DD Pricing Set) | **20** | **High** | Dense floor/roof framing; HSS; complete L / `2L4X4X3/8`; lintel schedule forms |
| `41 - SOME` | **No dedicated ST PDF** (DD set) | **7** | **High** | Foundation/framing plans; complete angles / half-leg forms |
| `02 - MARS Arcadia` | **No dedicated ST PDF** (Arch bid) | **3** (1 strong) | **Medium** | p39 canopy/post **HSS** schedule; p84/89 weak |
| `47 - William Winchester ES` | **No dedicated ST PDF** (bid set) | **2** | **Medium** | Roof framing + HSS posts |
| `04 - Thomas ES` | Arch only | 1 (weak) | **Low** | Handrail / stair HSS — **not** takeoff framing |
| `35 - Fort Lincoln Park` | Arch only | 1 (weak) | **Low** | Partition bracing HSS — **not** takeoff framing |
| `57 - Hart MS` | Arch only | 9 (mostly FP) | **Do not use** | “Incomplete L” = room/fixture tags; partition HSS only |
| `03 - The Field School` | Arch only | **0** | — | No strict steel pages under conservative rules |
| `20 - 2100 Crystal Dr` | Arch/Mech/Plumb/ID only | **0** | — | **No Structural binder in folder** |
| `34 - Fairwood ES` | Arch only | **0** | — | Coarse `L` tallies were false positives (Phase 0B) |
| `54 - Duckworth ES` | Arch only | **0** | — | Same |
| `55 - Springhill Lake` | Arch only | **0** | — | Phase 0B strict scan: 0 W/HSS/complete-L |

### Classification

**A. Usable structural material now**  
River Road · Burrville DD · SOME · (secondary) MARS p39 · William Winchester p56–57  

**B. No clear structural PDF / pages**  
Field School · Crystal Dr · Fairwood · Duckworth · Springhill Lake  

**C. Dedicated Structural PDF likely needed** (filenames/folders lack ST; only Arch or non-ST binders OBSERVED)  
Field School · Crystal Dr · Fairwood · Duckworth · Springhill · Thomas · Fort Lincoln · Hart MS · MARS (beyond canopy notes) · William Winchester (thin coverage)  

**D. Should NOT be used for structural validation**  
Hart MS (false-positive L tags) · Thomas handrail page · Fort Lincoln partition page · Crystal Mech/Plumbing/ID binders  

---

## 2. Steel-relevant page index (high / medium confidence)

### `18 - River Road` — `A-2025-09-19_252003_Addendum A - 4400 Base Bldg Dwgs.pdf`

| Page | Sheet (provisional) | Title/desc | W | HSS | complete L | Incomplete L | Examples (OBSERVED) | Why relevant |
|---:|---|---|---:|---:|---:|---|---|---|
| 19 | S-211? | FOUNDATION PLAN | 0 | 2 | 0 | — | HSS8 | HSS on foundation plan |
| 21 | S-210? | STEEL threaded rod note | 0 | 0 | 2 | — | L5X3X… | Complete L |
| 22 | UNKNOWN | Typical construction joint | 0 | 2 | 0 | — | HSS6 | HSS detail |
| 23 | UNKNOWN | Sump pit / detail | 0 | 3 | 1 | **L4X4** | HSS8, L4X4X1/4, incomplete L4X4 | Incomplete + complete angles |
| 25 | UNKNOWN | FLOOR FRAMING PLAN | 21 | 0 | 1 | — | W18X35, W24X55, W16X26 | Normal W labels |
| 26 | UNKNOWN | FLOOR FRAMING PLAN | 20 | 4 | 1 | — | W24X55, HSS…, L5X3X1/4 | W + HSS |
| 27 | UNKNOWN | FLOOR FRAMING PLAN | 20 | 0 | 1 | — | W24X55, L5X3X1/4 | W framing |
| 28 | UNKNOWN | ROOF FRAMING PLAN | 33 | 3 | 3 | — | W18X35, W24X68, HSS | Dense roof framing |
| 29 | UNKNOWN | ROOF FRAMING PLAN | 0 | 2 | 0 | — | HSS6 | HSS |
| 30 | UNKNOWN | FRAMING PLANS | 79 | 4 | 0 | — | W12X26, W24X55, W10X12 | Dense W |
| 31 | UNKNOWN | FRAMING PLANS | 27 | 0 | 0 | — | W24X76, W8X28 | W framing |
| 32 | UNKNOWN | ROOF FRAMING PLAN | 5 | 1 | 1 | — | W10X15, HSS3 | Mixed |
| 33 | UNKNOWN | Structural detail | 0 | 1 | 5 | **L4X4** | L4X4X1/4, L4X4X3/8, incomplete L4X4 | Incomplete near completes |
| 34 | UNKNOWN | Structural detail | 0 | 8 | 14 | **L4X4, L3X3** | L4X4X3/8, L3X3X1/4, incomplete L4X4 | **Completion-evidence candidate** (review only) |
| 35–37 | UNKNOWN | Angle-heavy details | 0 | 0–3 | 2–6 | — | L5X3X1/4, L3X3X… | Complete L / fractions |
| 38 | UNKNOWN | Detail | 0 | 4 | 9 | **L5X3** | L5X3X1/4, incomplete L5X3 | Incomplete L5X3 |
| 39 | UNKNOWN | TYPICAL COLUMN SPLICE | 0 | 5 | 0 | — | HSS | Connection / HSS |
| 40 | UNKNOWN | Beam-to-beam moment conn. | 1 | 4 | 4 | — | W6X15, L4X4X1/4 | Connections |
| 41 | UNKNOWN | Roof opening framing | 0 | 0 | 1 | **L4X4** | L4X4X1/4, incomplete L4X4 | Incomplete vs complete on sheet |
| 43–45, 69 | UNKNOWN | Misc. steel details | low | ≥1 | varies | — | HSS / L | Secondary |

### `51 - Burrvile ES` — `Burrville_DD Pricing Set_260317.pdf`

| Page | Sheet (provisional) | Title/desc | W | HSS | complete L | Incomplete L | Examples (OBSERVED) | Why relevant |
|---:|---|---|---:|---:|---:|---|---|---|
| 54 | UNKNOWN | Typical details / lintels | 1 | 0 | 3 | — | L4X3-1/2X5/16, L5X3-1/2X5/16, L3x3x1/4 | Half-leg + fractions (**not** incomplete) |
| 59 | UNKNOWN | FLOOR FRAMING PLAN NOTES | 156 | 2 | 0 | — | W12X16, W18X35, W21X44 | Dense W framing |
| 60 | UNKNOWN | FLOOR FRAMING PLAN NOTES | 92 | 1 | 0 | — | W16X26, W27X84 | Dense W |
| 61 | UNKNOWN | FLOOR FRAMING PLAN NOTES | 93 | 0 | 0 | — | W21X50, W24X62 | Dense W |
| 62 | UNKNOWN | ROOF FRAMING PLAN NOTES | 134 | 0 | 0 | — | W12X16, W18X40 | Dense roof W |
| 63 | UNKNOWN | ROOF FRAMING PLAN NOTES | 120 | 5 | 0 | — | W18X40, HSS… | W + HSS |
| 64 | UNKNOWN | ROOF FRAMING PLAN NOTES | 78 | 0 | 0 | — | W16X26, W18X40 | Dense W |
| 65 | UNKNOWN | ROOF FRAMING PLAN NOTES | 41 | 10 | 3 | — | W18X40, HSS…, L… | W + HSS + L |
| 68 | UNKNOWN | ROOF FRAMING PLAN | 0 | 0 | 11 | — | L4x4x3/8, L3x3x1/4 | Many complete angles |
| 69–72 | UNKNOWN | Typical structural details | varies | 0 | 2–15 | — | L…, **2L3x3x1/4** | Details / 2L / deck edge |
| 75 | UNKNOWN | Detail | 0 | 0 | 5 | — | **2L4X4X3/8**, L4X4X3/8 | Complete 2L |
| 76 | UNKNOWN | Steel framing note | 1 | 1 | 10 | — | W8X24, L4x4x3/8 | Mixed |
| 77 | UNKNOWN | Detail | 0 | 0 | 2 | — | L4x4x3/8 | Complete L |
| 78–79 | UNKNOWN | HSS-heavy | 0 | 25–26 | 0 | — | HSS6, HSS8 | HSS density |
| 80–81 | UNKNOWN | Anchor rod / column details | 50–62 | 2–6 | 0 | — | W10X33… | Column W + HSS |

### `41 - SOME` — `2025-12-18_100 DD SET-current (1).pdf`

| Page | Sheet (provisional) | Title/desc | W | HSS | complete L | Incomplete L | Examples (OBSERVED) | Why relevant |
|---:|---|---|---:|---:|---:|---|---|---|
| 57 | UNKNOWN | FOUNDATION PLAN | 31 | 0 | 0 | — | W10X33 | Foundation W |
| 58 | UNKNOWN | FRAMING PLAN | 116 | 0 | 0 | — | W12X19, W8x10, W16X26 | Dense floor framing |
| 59 | UNKNOWN | ROOF FRAMING PLAN | 102 | 0 | 0 | — | W10X22, W8X10 | Dense roof framing |
| 61 | UNKNOWN | STEEL FRAMING, SEE PLAN | 3 | 0 | 0 | — | W10X33 | Elevation / framing ref |
| 64 | UNKNOWN | Framing / stud notes | 0 | 0 | 7 | — | L3X3X3/8, L4X4X5/16 | Complete L |
| 65 | UNKNOWN | Framing plans | 0 | 0 | 4 | — | **L5X3-1/2X5/16**, L4X3-1/2X5/16 | Half-leg complete (abstention false-positive test) |
| 66 | UNKNOWN | TYPICAL DETAILS | 0 | 0 | 1 | — | L4X4X1/4 | Complete L detail |

### Secondary (medium)

| Project | PDF | Pages | OBSERVED evidence | Use? |
|---|---|---|---|---|
| MARS Arcadia | Arch bid update | **39** | HSS posts/outriggers (`HSS 5X4X5/16`, etc.) | Optional HSS-normalization |
| MARS Arcadia | same | 84, 89 | Weak single HSS mentions | Prefer skip |
| William Winchester | Bid set | **56–57** | HSS posts + roof framing W21x48… | Optional small framing sample |

### Explicitly not indexed for validation

| Project | Pages scanner hit | Why dropped |
|---|---|---|
| Hart MS | 41, 45, 47, 75, 79, 81, 88, 95, 121 | Architectural tags (`L85 x14`); partition HSS only |
| Thomas ES | 61 | Steel handrail / stair stringer — not framing takeoff |
| Fort Lincoln | 63 | Partition HSS bracing detail |

---

## 3. Recommended initial validation subset (~16 pages)

Small, representative, **no screenshots required** — point Analyze / first-run eval at these page ranges only.

| # | Project | Page | Tests (problem under test) |
|---:|---|---:|---|
| 1 | River Road | **25** | Normal W labels on floor framing |
| 2 | River Road | **28** | Roof framing W + HSS + complete L |
| 3 | River Road | **30** | Dense W labeling |
| 4 | River Road | **33** | Incomplete `L4X4` + complete `L4X4X1/4` / `L4X4X3/8` (abstention) |
| 5 | River Road | **34** | Incomplete `L4X4` near `L4X4X3/8` — **completion evidence vs abstain** (must not auto-complete) |
| 6 | River Road | **38** | Incomplete `L5X3` + completes |
| 7 | River Road | **41** | Incomplete `L4X4` on opening detail |
| 8 | Burrville | **54** | Half-leg `L5X3-1/2X5/16` must stay **complete** |
| 9 | Burrville | **59** | Dense floor framing W |
| 10 | Burrville | **63** | Roof framing W + HSS |
| 11 | Burrville | **65** | Mixed W/HSS/L on roof |
| 12 | Burrville | **72** | `2L` + complete L details |
| 13 | Burrville | **75** | Complete **`2L4X4X3/8`** (not incomplete 2L) |
| 14 | Burrville | **78** | Dense HSS |
| 15 | SOME | **58** | Dense framing W (incl. `W8x10` spacing/case) |
| 16 | SOME | **65** | Half-leg completes / detector false-positive guard |

**Optional +2:** MARS p39 (HSS schedule text); William Winchester p57 (roof W).

**Not in subset:** Crystal/Fairwood/Duckworth/Springhill/Hart/Thomas/Fort Lincoln.

---

## 4. Unresolved questions

1. Exact **title-block sheet numbers** for indexed pages (provisional IDs may be callouts).  
2. Whether June can supply **dedicated Structural PDFs** for Crystal Dr, Springhill, Fairwood, Duckworth, Field School, Hart, Thomas, Fort Lincoln.  
3. Live **GH RH_OUT** pairing still unsolved (Phase 0B) — not blocked by this index.  
4. Page-level **dense-drawing counts** not re-measured here (space-safe: no new geometry runs); Phase 0B already showed extreme density on this corpus.

---

## 5. Git / change confirmation

| Item | Status |
|---|---|
| Created | `backend/JUNE_STEEL_PAGE_INDEX.md` **only** |
| PDFs | Untouched (no copy/render/commit) |
| Production code / flags / takeoff / geometry | **Unchanged** |
| Prior dirty tree | Preserved |

```text
?? backend/JUNE_STEEL_PAGE_INDEX.md
```

---

## Summary counts

| Metric | Value |
|---|---|
| Structural projects with usable pages | **3 primary** (River Road, Burrville, SOME) + 2 secondary |
| Steel-relevant pages indexed (high/medium) | **~54** (25+20+7+1+2) |
| Projects missing dedicated ST PDF / clear S-set | **10** of 13 folders |
| Recommended initial validation pages | **16** (+2 optional) |

**NO production code changed.**
