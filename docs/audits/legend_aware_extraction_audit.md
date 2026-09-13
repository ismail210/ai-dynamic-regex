# Legend-Aware / Document-Language Extraction Audit

**Scope:** investigation only. No production code, models, or training data were modified. No commits were made.
**Corpus:** the 7 real structural-steel PDF drawing sets in `backend/training/ml_association/real_project_pilot/extracted/` (the curated "real project pilot" set — the same PDFs already paired with real cost-estimate spreadsheets elsewhere in this repo).
**Method:** direct PyMuPDF text extraction and regex/keyword scanning of all pages in all 7 PDFs (script: `scan_legend_pages.py` in this folder, fully reproducible), plus **direct execution of the real production classifier functions** (`entity_taxonomy.classify_category`, `engineering_object_filter.classify_engineering_object`) against real quoted text pulled from these PDFs — not simulated behavior, actual code run against actual drawing text. A companion code-trace of the full backend pipeline was performed separately (Explore agent, cited throughout §H/§J). Evidence is tagged **confirmed** (I read the exact text or ran the exact function), **inferred** (reasoned from confirmed evidence but not independently re-verified), or **reported, not verified** (came from the user's description of the partner's VLM experiment, for which no artifacts exist in this repo).

---

## A. Executive finding

**Yes, this is worth pursuing — but the evidence points at a narrower and more specific mechanism than "add an LLM."**

The 7 real drawing sets contain real, recurring, project-specific drafting language that the current pipeline has no way to consume: an explicit member-size abbreviation table on one project ("W8" = W8x10), consistent multi-page usage of "BENT PL" as a first-class connection/edge-condition element (112 confirmed occurrences across 6 of 7 projects), and dedicated abbreviation/legend sheets on every project. Running the actual production classifier code against real quoted text from these PDFs confirms, precisely, *why* this information is lost today — and the root cause is **not** "the pipeline doesn't understand bent plates" so much as **the plate-detection regex requires a two-dimension (width × length) callout, and the great majority of real plate callouts in these drawings state only a single thickness** (`"3/8" BENT PL"`, `"1/4" CAP PL"`, `"CONN PL 1/2""`). This single, precise regex gap (`engineering_object_filter.py:14-17`) explains most of the loss for BENT PL *and* for BASE PL, CAP PL, STIFF PL, GUSSET, and CONN PL alike — it is a shared structural gap, not a bent-plate-specific one.

Separately, the audit found the codebase already has a **crude but real** legend-suppression mechanism (`engineering_object_filter.py:31-35`, a keyword search over the token's local line/block context for words like `LEGEND`/`GENERAL NOTES`) — confirmed, by direct execution, to correctly suppress a real `W27X84` example inside a "STEEL BEAM LEGEND" caption. But the same test also produced a case (GCDC's `"W8" = W8x10"` abbreviation-table line) where the identical mechanism does **not** trigger, because the suppressing keyword and the AISC-looking value don't share a line/block window. This is exactly the kind of finding that argues for a *page-role* signal (legend-aware) layered on top of the existing *local-keyword* signal, rather than a wholesale LLM rewrite.

**Recommendation:** pursue a narrow, deterministic-first "Drawing Language Profile" (§L) that (1) captures the small number of genuinely project-specific rules found in these PDFs (abbreviation substitution tables, connection-type vocabulary, plate-callout conventions), (2) is produced with a document-level LLM pass used only as a *proposal generator* whose output is validated against the same document's actual callouts before being trusted (§K, Architecture C), and (3) is threaded through the two or three insertion points identified in the code trace (§J) that already carry a whole-`document` object into the classification stage — no rewrite required for a first POC. The VLM-per-crop approach (§K, Architecture B) is not disproven by this audit, but the evidence here suggests it is solving the wrong end of the problem: most of what's lost is losable *before* an image crop is ever produced (Stage 3/4 token capture), and a legend-aware regex fix plus a project-profile pass would very likely close more of the gap, more cheaply and more explainably.

---

## B. PDF inventory

All 7 PDFs are **born-digital / vector** (PyMuPDF confirmed zero raster/scanned pages — `text_length > 30` with no reliance on embedded images — across all 7 documents, all pages). Full text extraction is available everywhere; there is no OCR dependency in this corpus. All are Structural discipline sheet sets (filenames/sheet series are `ST`/"Structural"). Project names below are as found in the `real_project_pilot/extracted/` folder names and confirmed against the paired `*Project Estimate*.xlsm` filenames in the same folders (real cost estimates tied to these same drawings) and against text visible on the sheets themselves (school/building names in title-block-adjacent text).

| Project (folder) | PDF file | Pages | Discipline | Format | Dedicated legend/general-notes/abbreviation sheet(s) found |
|---|---|---:|---|---|---|
| 1200 K | `1200 K_Permit_Bid_Dwgs - Structural.pdf` | 39 | Structural | Vector, text-native | pp. 1–2 (abbreviations, general notes, special inspections) |
| Burrville | `Burrville ES - ST.pdf` | 29 | Structural | Vector, text-native | pp. 1–2 (legend, general notes, abbreviations, typical details) |
| GCDC Building | `GCDC Building 4 - ST1.pdf` | 81 | Structural | Vector, text-native | p. 1 (index/general notes), **p. 5** (abbreviations, member-size abbreviation table, connection-type notes) |
| H5 Herndon | `ST.pdf` | 23 | Structural | Vector, text-native | p. 1 (general notes), **p. 3** (symbol legend — 44 symbol-keyword hits) |
| Ketcham | `Structure - Copy.pdf` | 17 | Structural | Vector, text-native | p. 1 (abbreviations, general notes, typical details) |
| Sidwell | `03 - SFSLS_251029_ISSUED FOR BID_2A_STRUCTURAL complied thru add 2.pdf` | 45 | Structural | Vector, text-native | pp. 1, 7, 8 (legend, abbreviations, general notes — this project splits legend content across 3 non-adjacent sheets) |
| Springhill ES | `ST - Springhill Lake.pdf` | 28 | Structural | Vector, text-native | pp. 1–2 (general notes, legend, abbreviations) |

**Confirmed:** legend/general-notes/abbreviation content is *not* confined to page 1 on 3 of 7 projects (GCDC: p.5; H5 Herndon: p.3; Sidwell: pp.7–8), directly supporting the brief's instruction not to assume page 1. Each of these "page N" legend sheets was found by ranking every page in the document by a keyword-density score (`LEGEND`, `GENERAL NOTES`, `ABBREVIATION`, `SYMBOL`, `SCHEDULE`, `TYPICAL DETAIL`, `SPECIAL INSPECTION`, `CODE`, etc.) rather than assuming a position — see `scan_legend_pages.py`.

A second, much looser pass (score ≥ 2, i.e. any page that so much as contains the word "NOTES:" or "SCHEDULE" once) flags far more pages per project (12–45 of the pages in each set) — this loose set is dominated by **typical-detail sheets and schedule sheets**, not cover/legend sheets, and is reported separately below (§G/§I) because it changes the false-positive analysis substantially.

---

## C. Legend and convention taxonomy (evidence-derived)

Forcing no predefined taxonomy, the real content on the dedicated cover sheets across these 7 projects falls into these observed categories (not all present on every project):

1. **Structural abbreviations table** (2-column: abbreviation → description) — present on all 7 projects, e.g. `PL / PLATE`, `PJP / PARTIAL JOINT PENETRATION`, in every project's abbreviation list.
2. **Steel beam legend (graphical key)** — Burrville p.2, Sidwell p.8, Springhill p.2: a diagram key explaining camber, stud-count, and moment-connection notation, using `W27X84` purely as the illustrative example section.
3. **General structural notes** (numbered, prose) — every project, covering code/design criteria, special inspection requirements, material specs, connection-design responsibility (who designs shear connections), fireproofing, camber, deflection criteria.
4. **Project-specific member-size abbreviation substitution table** — **GCDC Building p.5 only**: an explicit numbered note giving `"W8" = W8x10`, `"C8" = C8x11.5`, `"HSS8x4" = HSS8x4x1/4`, etc. (full quote in §D). This is a genuinely different category from the plain PL/PLATE abbreviation table — it redefines how to *read a real callout on the framing plan*, not just what a short label means in prose.
5. **Symbol/graphic legend** — H5 Herndon p.3 (44 distinct symbol references), Burrville p.2, Sidwell pp.1/8, Springhill p.2 (weld symbols, line-style keys).
6. **Connection-type vocabulary / allowed & prohibited connection types** — GCDC Building p.5: an itemized list of named connection types including `BENT PLATE SHEAR CONNECTIONS` as an allowed type in one note and `BENT PLATE CONNECTIONS WELDED TO THE SUPPORTING MEMBER` as a *prohibited* type in another (full quotes §E). This is the closest thing found in the corpus to an explicit definition of "bent plate" as a named structural element category — but it is prose, not a formal notation-format rule.
7. **Lintel/edge-angle schedule embedded in general notes** — Burrville p.2, Sidwell p.8, Ketcham p.1, Springhill: a small table mapping opening width → required loose-angle size (e.g. `L4X3-1/2X5/16`), with text elsewhere in the same notes explicitly permitting `"BENT PLATE"` as a substitute for the rolled angle (§E).
8. **Masonry/material specification notes** — present on most projects; incidentally contain real ASTM designations (`C90`, `C129`, `C216`) that superficially resemble section/material tokens but are masonry-unit specs, not steel takeoff items.
9. **Typical detail sheets** (not on the cover page, scattered through the set) — the single largest source of real BENT PL / plate-family text (see §G): these are drawing content, not "context-only" pages, but they describe generic/repeatable connection details rather than located, quantity-bearing members. They occupy a genuine middle ground the brief's "semantic_context_only / takeoff_candidate / both / unknown" framing is designed for (§I).

No project in this corpus was found to define an explicit **symbol or line-weight convention specifically for "bent"** fabrication (no dashed-bend-line legend entry, no "B" suffix convention, no dedicated bent-plate mark family like "BP-#"). The word "bent" is used exclusively as a plain-English adjective inside prose notes and field callouts, never as a coded symbol.

---

## D. Project-specific terminology findings

### The standout finding: an explicit, project-specific member-size substitution rule

**GCDC Building, page 5, General Note 6** (confirmed, exact quote):

> `6. THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS:`
> `"W8" = W8x10`
> `"W10" = W10x12`
> `"W12" = W12x19`
> `"W14" = W14x22`
> `"W16" = W16x26`
> `"C8" = C8x11.5`
> `"C12" = C12x20.7`
> `"HSS8x4" = HSS8x4x1/4`
> `7. "CANT" INDICATES CANTILEVERED BEAM. WHERE BEAM IS STEEL AND SIZE IS NOT INDICATED, THE CANTILEVERED BEAM SHALL BE THE SAME SIZE AS THE ADJACENT BACKSPAN BEAM, UNO...`

This is a textbook case for the hypothesis in the brief. A bare `"W8"` callout on this project's framing plan is a **complete, valid, deliberately-abbreviated designation** meaning `W8x10` — not a malformed or incomplete section string. A project-agnostic AISC-grammar parser has no way to know this without ingesting this specific note on this specific project; on a different project, a bare `"W8"` would correctly be flagged as incomplete/ambiguous. This is real evidence that identical-looking tokens require different interpretation across projects, and that the rule is stated explicitly, once, near the front of the set — exactly the kind of one-time semantic priming the brief's hypothesis describes. Note 7 (`"CANT"` = cantilever) is a second, smaller example of the same pattern (a project vocabulary word that changes how a nearby member callout should be read, not a member itself).

### Rolled sections vs. fabricated/non-catalog objects — real terminology observed

| Term family | Observed real variants (verbatim, across projects) | Notes |
|---|---|---|
| Rolled sections | `W27X84`, `W18X50`, `L4X3-1/2X5/16`, `L3-1/2X3-1/2X5/16`, `L6X4X3/8`, `HSS16X4X1/2`, `HSS12X4`, `C6X8.2`, `C6X10.5` | Standard AISC grammar; parser handles these when isolated from a modifier word. |
| Base plate | `BASE PLATE`, `BASE PL`, `BASEPLATE` | 3 spellings of the same concept in this corpus alone; only 2 of 3 are caught by the current heuristic (§E). |
| Cap plate | `CAP PL`, `CAP PLATE` | Column-cap connection element; consistently a thickness-only callout (`1/4" CAP PL`), never width×length. |
| Stiffener plate | `STIFF PL`, `STIFFENER PL`, `STIFFENER PLATE` | Caught today via a substring heuristic (`"STIF" in token`) — works, but by coincidence of that specific substring, not a designed rule. |
| Gusset (plate) | `GUSSET`, `GUSSET PL`, `GUSSET PLATE` | Brace/HSS-to-column connection element; explicitly deferred to contractor design in Burrville/Sidwell (`"GUSSET AND BENT PL TO BE DESIGNED BY CONTR"`). |
| Connection plate | `CONN PL`, `CONNECTION PL`, `CONNECTION PLATE` | Generic shear-tab/connection plate references. |
| Clip angle | `CLIP ANGLE`, `CLIP L` | Small connection angle. |
| Bent plate | `BENT PL`, `BENT PL.`, `BENT PLATE`, `BENTPL` (split across a line break in the raw text stream), `PL 1/4" MIN (BENT`, `PL3/8" MIN BENT`, `SHEET METAL BENT PL`, `CONT BENT PL 3/8"x4"`, `3/8"X4" BENT PL CONT` | See §E for the full forensic breakdown — this is the largest and most varied family found. |

### Contextual roles actually found (not assumed)

`BEAM`, `GIRDER`, `COLUMN`, `BRACE`, `KICKER` (Sidwell/Springhill: `"CFMF KICKER"`), `POST` (occasionally, e.g. `"STAIR SUPT"` framing), `SEAT` (`"BENT PL OR ANGLE SEAT, 6" LONG"`), `EMBED` (`"EMBED CONNECTION TO BE DESIGNED BY CONTR"`), `POUR STOP` / `POURSTOP` (used interchangeably with, and explicitly as an alternative to, bent plate — `"CONT. GAUGE METAL POUR STOP OR BENT PLATE"`), `CLOSURE` / `CLOSURE ANGLE` / `CLOSURE PL` (also interchangeable with bent plate — `"PROVIDE BENT PLATE OR CLOSURE ANGLE AT ALL DISCONTINUOUS EDGES"`). **Not found in this corpus:** `ledger`, `lintel edge-angle` is present but not called "lintel" for steel members specifically (lintel terminology in this corpus is masonry-focused), `collector`, `drag strut`, `hanger` (except `"STAIR HANGER"`). These absences are reported as absences, not assumed gaps.

---

## E. Bent plate / bent angle forensics

### Quantification (all 7 PDFs, full-text regex scan, confirmed counts)

| Metric | Count |
|---|---:|
| Total pages scanned | 262 |
| Raw occurrences of the word "BENT" anywhere in the corpus | 125 |
| — of which genuinely refer to a bent **plate** (manually verified by context, regex-assisted) | **112 (89.6%)** |
| — of which are a hard-negative false trigger on the substring "BENT" | **13 (10.4%)** — see breakdown below |
| Occurrences of the broader plate-family regex (`BENT PL/PLATE`, `BASE PL/PLATE`, `CAP PL/PLATE`, `STIFF PL/PLATE`, `GUSSET`, `CONN PL/PLATE`, `CLIP ANGLE`) | 491 |
| Unique surface-text variants of the plate-family regex observed | 11–19 per project (see `scan_summary.json`) |
| Projects with ≥1 confirmed bent-plate mention | 6 of 7 (all except H5 Herndon) |

**Hard-negative breakdown of the 13 non-plate "BENT" occurrences** (confirmed by reading context):

| Category | Count | Real example |
|---|---:|---|
| Proprietary masonry anchor product name | 4 | `"HOHMANN & BARNARD #365, 12GA. X 1 1/4" BENT GRIPSTAY GALVANIZED MASONRY ANCHORS"` (Ketcham p.1/p.5) |
| Unrelated material, substring collision only | 1 | `"BENTONITE ROPE WATERSTOP"` (Ketcham p.3) |
| Bent *section* member, not a plate (HSS/stringer) | 2 | `"HSS16X4X1/2 BENT"`, `"HSS12X4 SLOPE, BENT"` (Sidwell pp.12/15 — bent HSS stair stringers) |
| Ambiguous/unclassified in this pass | 6 | e.g. general prose uses of "bent" not tied to a specific object in the 60-character context window captured |

This matters directly: it demonstrates that even a **naive keyword search for "BENT"** — something between the current pipeline (which has no such search) and a proposed rule — would misfire roughly 1 time in 10 in this exact corpus, on a proprietary product name and an unrelated waterproofing material that happen to share the substring. Any rule (regex, alias table, or LLM-derived) built from this evidence needs to disambiguate by nearby object type (`PL`, `PLATE`, `HSS`) or by role words, not by the bare word "BENT" alone.

### Real field-callout variants, with project and page citations (confirmed, all quoted verbatim from the PDFs)

| Variant pattern | Real example | Project / page |
|---|---|---|
| Thickness + `BENT PL` + connector spec | `1/2" BENT PL W/ 1/2"⌀x 9" WELDED STUD @ 12" OC` | Burrville p.16 |
| `BENT PL.` (trailing period) alone | `3/8" BENT PL.` | 1200 K p.37 |
| `BENT PL` + condition clause | `BENT PL 3/8" AT END CONDITION. OMIT IF DECK CONTINUES.` | Sidwell p.27, Burrville p.19 |
| Thickness-only, no width/length | `5/16" BENT PL` | GCDC p.63 |
| Parenthetical qualifier (fabrication method) | `PL1/4" MIN (BENT OR FABRICATED)` | Springhill p.13, Burrville p.20 |
| No dimension at all — role word only | `SHEET METAL BENT PL FOR MULLION SUPT` | Springhill p.18 |
| Conditional/rule-based sizing (deck-edge overhang table) | `USE 1/4" BENT PL FOR DIM "A" = 12 1/4" TO 20"` | GCDC p.60 |
| `BENT PL` as an *alternate* to a rolled angle, with a lintel schedule reference | `L4x3x1/4x6" LLV OR SIMILAR BENT PL ES AND STAGGERED. SEE SCHEDULE FOR SPACING` | Burrville p.20, Springhill p.16, Sidwell p.28 |
| Reordered field order: dimension after the word | `CONT BENT PL 3/8"x4"` vs `3/8"X4" BENT PL CONT` (same project, two sheets) | Sidwell p.37 |
| Split across a rendered line break in the PDF text stream | `"BENT \nPLATE"` / `"BENT \nPL"` (2 and 1 raw occurrences respectively) | GCDC, H5 Herndon (raw text-extraction artifact, not a drafting convention) |

These are the same class of real-world variance the partner's small VLM pilot reported (`1/2" BENT PL W/ 1/2"⌀ x 9"`, `1/4" BENT PL`, `3/8" BENT PL`, `BENT PL 3/8" AT`) — this audit independently reproduces and substantially extends that finding across 6 projects and 112 confirmed instances, using plain text-layer extraction (no VLM needed to find these).

### Is BENT PLATE documented anywhere in the legends? (direct answer to a required question)

**Partially, and only on 2 of 7 projects, and never as a formal notation/format rule.**

- **GCDC Building p.5**, in the general notes' allowed/prohibited connection-type lists (confirmed exact quotes):
  > `- SINGLE-PLATE CONNECTIONS` / `- SHEAR END-PLATE CONNECTIONS` / **`- BENT PLATE SHEAR CONNECTIONS`** *(listed among connection types the contractor must submit design tables for)*
  > ...elsewhere on the same page: `CONNECTION TYPES ARE PROHIBITED ON BEAMS AND GIRDERS: - SINGLE & DOUBLE ANGLE CONNECTIONS WELDED TO THE SUPPORTING MEMBER. - **BENT PLATE CONNECTIONS WELDED TO THE SUPPORTING MEMBER.**`
- **Ketcham p.1**, in general notes on slab-edge and masonry-anchor conditions (confirmed exact quotes):
  > `PROVIDE CONTINUOUS SCREED ANGLE AT ALL SLAB EDGES WHERE THERE IS NO CONTINUOUS STEEL ANGLE OR BENT PLATE.`
  > `WHERE CAVITY WALLS ARE UTILIZED, PLACE ANGLE/BENT PLATE UNDER CMU AS PER SCHEDULE ABOVE...`
  > `...ASSUME THE SHELF ANGLE WILL BE 1/2" BENT PLATE ATTACHED TO SLAB WITH WEDGE INSERTS AND HAIRPINS.`

Neither project's structural-abbreviations table (the `PL / PLATE` two-column list present on every project, §D) has a distinct entry for "bent plate" — it is treated purely as `PLATE` + the plain-English adjective "bent," never as its own coded abbreviation, symbol, or mark family. So: **no formal legend/symbol entry exists anywhere in this corpus for bent plate**, but **prose documentation of it as a recognized connection/edge-condition element does exist** on 2 of 7 projects, and its *usage* (as opposed to its definition) is consistent and recurring across 6 of 7 projects.

### Recurring project-specific patterns visible across callouts (even without a formal legend definition)

Even absent a formal definition, the corpus shows **stable, cross-project conventions** that a project-language profile could capture:
1. Bent plate is near-universally interchangeable with (and explicitly offered as an alternate to) a rolled angle in edge/screed/lintel conditions — `"L4x3x1/4x6" LLV OR SIMILAR BENT PL"`, `"OR BENT PLATE"`, `"BENT PLATE OR CLOSURE ANGLE"`, `"BENT PLATE OR POUR STOP"` — this pattern recurs on Burrville, Ketcham, Sidwell, and Springhill independently.
2. When a dimension is given, it is overwhelmingly a **single thickness**, not a width×length pair (`3/8" BENT PL`, not `3/8"x4"x12" BENT PL` — the one counter-example, `"CONT BENT PL 3/8"x4""`, gives a thickness×width for a *continuous* strip, still not a bounded plate size).
3. "BENT" consistently precedes "PL"/"PLATE" as an adjective, never follows it as a suffix mark (contrast with `HSS16X4X1/2 BENT`, where "BENT" *does* follow the section — i.e., word order for the modifier differs by shape family, which any future rule needs to handle as two separate patterns, not one).

---

## F. Newly discovered unsupported notation (beyond bent plate)

These were not the audit's starting hypothesis; they emerged from reading the actual scan output.

1. **Thickness-only plate callouts are a systemic gap, independent of "bent."** Confirmed by direct execution (§H): `CAP PL`, `CONN PL`, `STIFF PL` (when the STIF substring heuristic doesn't happen to catch it), and `BASE PL` all fail the same regex gate for the same reason as bent plate when given as thickness-only. This is a bigger and more tractable finding than the bent-plate-specific hypothesis in the original brief — see §H.
2. **"BENT" as a fabrication modifier on non-plate shapes.** `HSS16X4X1/2 BENT`, `HSS12X4 SLOPE, BENT` (Sidwell — bent/curved HSS stair stringers) — a curved/bent HSS is a materially different (and more expensive) fabrication than a straight one, and the current pipeline classifies it as an ordinary `column_or_brace` steel section, silently dropping the "bent" modifier just as it does for plates. This generalizes the bent-plate problem to a "bent-\<any-shape\>" problem.
3. **Interchangeable-term families the parser has no concept of.** `BENT PLATE` / `POUR STOP` / `CLOSURE ANGLE` are used as drop-in alternates for the same physical edge condition across multiple projects (`"PROVIDE BENT PLATE OR CLOSURE ANGLE"`, `"POURSTOP OR BENT PLATE"`). A grammar-only parser treats these as three unrelated categories; the drawings treat them as one functional role with three acceptable fabrications.
4. **Contractor-deferred design elements with no dimension at all.** `"GUSSET AND BENT PL TO BE DESIGNED BY CONTR"`, `"BENT PLATES AND CONNECTORS TO BE DESIGNED BY CONTR"`, `"BOLTS TO BE DESIGNED BY CONTR"` — these are real structural elements the drawing explicitly declines to dimension, deferring to contractor engineering. No current stage of the pipeline has a concept of "real object, deliberately undimensioned" — it can only capture or drop; there's no "flag for contractor-design, do not expect a takeoff quantity" bucket.
5. **Legend-only symbolic shorthand that is *not* prose.** The `"STEEL BEAM LEGEND"` graphic key (Burrville/Sidwell/Springhill) uses bracket notation (`W27X84 [88] c=1"`) where `[88]` means "88 shear studs" and `c=1"` means "1 inch camber" — a compact positional-symbol convention with no text label at all next to the numbers. This is a case where the *legend itself* uses non-obvious shorthand that would need decoding before the legend's own content is even usable as context.
6. **Split-token line breaks from PDF text extraction, not drafting convention.** `"BENT \nPLATE"`, `"STIFFENER \nPLATE"`, `"GUSSET \nPLATE"` — PyMuPDF's `get_text()` sometimes inserts a line break mid-phrase where the underlying PDF content stream wraps a text run; this is an extraction artifact, not something a drafter wrote, but it has the same practical effect as the brief's concern about annotations "split across multiple text spans" and would defeat a naive single-line regex.

---

## G. Legend-to-drawing mapping

| Legend/notes definition (page) | Actual observed callout variants on other sheets | Current Estima3D interpretation | Desired interpretation |
|---|---|---|---|
| `PL / PLATE` (abbreviation table, all 7 projects) | `PL1/4X6`, `PLATE 3/8X12`, and — far more often — thickness-only `PL 3/8"`, `1/4" PL` | Width×length form → `category=plate` (works). Thickness-only form → `UNKNOWN`/dropped (fails). | Both forms → `plate`, with a `dimension_confidence: partial` flag on the thickness-only form rather than a binary catch/miss. |
| GCDC "W8" = W8x10 (p.5, only on GCDC) | Not independently re-verified on GCDC's own framing plans in this pass (would require locating a bare "W8" callout on a plan sheet and confirming it is meant as the substitution, not a typo/incomplete label) — flagged **requires engineer review**. | Bare `"W8"` today would either fail the section grammar (no weight/`X`) or, if captured, be treated as an incomplete/ambiguous section string. | Recognize the project-declared substitution and resolve to `W8x10` with full provenance back to the note. |
| `BENT PLATE SHEAR CONNECTIONS` (GCDC p.5, connection-type note) | 10 confirmed field instances of `BENT PL`/`BENT PLATE` on GCDC detail sheets (pp.60/63/73/75), consistent with this vocabulary | `UNKNOWN` category or thickness-only drop (§H) | Recognize `BENT PL` as a first-class connection-plate sub-type distinct from flat `PLATE`. |
| `OR BENT PLATE` / `ANGLE/BENT PLATE` (Ketcham p.1, edge-condition notes, presenting bent plate as an *alternate* to a rolled angle) | Ketcham pp.3–6 detail sheets: `"BENT PLATE, TYPICAL"`, `"PROVIDE BENT PL. 1/4" FOR OVERHANGS..."`, `"POUR STOP OR BENT PLATE"` | Same as above | Same as above, plus recognize `POUR STOP` / `BENT PLATE` / `CLOSURE ANGLE` as a shared functional-role group (§F.3) |
| `STEEL BEAM LEGEND` bracket notation `[##]`/`c=#"` (Burrville p.2, Sidwell p.8, Springhill p.2) | Not searched for on framing plans in this pass — flagged as a candidate for a follow-up scan, since it would require locating the same bracket pattern next to real (non-legend) beam marks | No current handling of bracket-suffix notation at all | Would need a dedicated bracket-suffix parser keyed to this legend's own decode table, per project |

**Does the same project use multiple variants?** Yes — Burrville alone uses `BENT PL`, `BENT PLATE`, and the reordered `BENT PL ES` (edge-and-staggered shorthand) across different detail sheets in the same set. **Do details use different notation than framing plans?** Consistent with that: every confirmed BENT PL instance in this corpus occurs on a **detail/section sheet**, never on a plan-view framing sheet directly (the framing plans reference the details by callout bubble, e.g. `"SEE PLAN"`, rather than repeating the dimension). This matters for §I: it means BENT PL evidence in this corpus is concentrated on detail sheets, which are legitimate drawing content (not "context-only" legend pages) but also not literally quantity-bearing plan callouts — a genuine third bucket, not just "legend" vs. "takeoff."

---

## H. Current-pipeline failure analysis

This section reports **directly-executed** results: the real repository functions `entity_taxonomy.classify_category()` and `engineering_object_filter.classify_engineering_object()` were imported and run (not reimplemented or guessed) against real quoted text from these PDFs. Full detail and reproducible code: `hard_case_corpus.json` in this folder.

### The dominant, precise root cause: the plate regex requires two dimensions

`engineering_object_filter.py:14-17`:
```python
_PLATE = re.compile(
    r"^(?:PL|PLATE)\s*\d+(?:[./]\d+)?(?:X\d+(?:[./]\d+)?){1,3}$",
    re.IGNORECASE,
)
```
The `{1,3}` quantifier on the `X\d+...` group has a **minimum of 1** — meaning this pattern can only ever match a plate given as **thickness × (at least one more dimension)**. Running it directly:

| Captured token text (what `token_extractor.py` would realistically capture — the leading `BENT`/`CAP`/`CONN`/`GUSSET` word is dropped upstream because those words aren't part of the `PL\d...` regex span) | `classify_engineering_object()` result |
|---|---|
| `PL1/2X9` (has a width×length-shaped pair) | **`"plate"`** ✅ |
| `PL3/8` (thickness only — from `"BENT PL 3/8""`) | **`None`** ❌ — dropped |
| `PL1/4` (thickness only — from `"1/4" CAP PL"` or `"PL1/4" MIN (BENT..."`) | **`None`** ❌ — dropped |
| `PL1/2` (thickness only — from `"CONN PL 1/2""`) | **`None`** ❌ — dropped |

Of 6 real, confirmed BENT PL field callouts tested this way, **5 of 6 fail Stage 4 for this reason alone**, independent of whether the word "BENT" survived extraction. And the same failure mode was confirmed for `CAP PL` and `CONN PL` — **this is not a bent-plate-specific bug; it is a plate-family bug that happens to hit bent plate hardest because bent plate is overwhelmingly given as thickness-only in real drawings** (§E, pattern 2).

### Where "BENT" itself is lost (secondary mechanism, confirmed via the code trace)

Per the separately-run pipeline trace (§J), Stage 3 (`services/token_extractor.py`) matches candidate spans starting at a section/plate-prefix regex; a preceding adjective like `BENT` is a *contributing word* for the token's bounding box but is **not included in `normalized_text`**. So even in the one case that *does* pass Stage 4 (`PL1/2X9` → `"plate"`), the resulting record has permanently lost the fact that it was bent — it becomes an ordinary flat plate, with no error, no low-confidence flag, and no record that a modifier word was dropped.

### There is no "TEXT_NOTE" bucket in the current codebase — a discrepancy worth flagging

The user's brief (and reportedly the partner's VLM experiment) describes BENT PL annotations as being "classified as `TEXT_NOTE`." **A repository-wide, case-insensitive grep for the literal string `TEXT_NOTE` across the entire repository — backend, frontend, training data, docs — returns zero matches.** The actual current failure mode, confirmed above, is not misclassification into a note bucket; it is **silent deletion** (`services/engineering_object_filter.py:98-107`, `filter_engineering_objects()` simply omits any token where `classify_engineering_object()` returns `None` — no replacement label is written) or, less often, **silent truncation** (the plate survives, "bent" doesn't). This is flagged here per the audit's own instruction to be skeptical and separate raw evidence from claims: either the "TEXT_NOTE" language describes an older pipeline version, a human-review-tool default label outside this codebase, or the general *effect* ("looks like inert text to the system") rather than a literal code path. **Requires engineer/partner clarification** — see §N.

### The existing legend-suppression mechanism — confirmed to work in one case, confirmed to miss in another

`engineering_object_filter.py:31-35`:
```python
_NON_OBJECT_CONTEXT = re.compile(
    r"\b(?:GENERAL\s+NOTES?|REVISION|REVISIONS|SPECIFICATIONS?|"
    r"MATERIAL\s+NOTES?|ASTM|DESIGN\s+CRITERIA|SHEET\s+INDEX|LEGEND)\b",
    re.IGNORECASE,
)
```
This already exists and already runs on every token's local line/block/neighbor text (not the whole page). Directly tested:

- **Case LGD-001** (Burrville p.2): token `W27X84`, line context `"STEEL BEAM LEGEND NUMBER OF STUDS ... W27X84 [88] c=1" BEAM CAMBER AT MID SPAN AFTER ERECTION"` → `classify_engineering_object()` returns **`None`** — correctly suppressed, because the word `LEGEND` shares the token's context window. **Confirmed working today**, for this case.
- **Case LGD-002** (GCDC p.5): token `W8X10`, line context `"THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS: "W8" = W8x10"` (the actual sentence containing the abbreviation rule; note it does **not** contain the words `GENERAL NOTES` — that heading is elsewhere on the page, likely a different text block) → `classify_engineering_object()` returns **`"steel_section"`** — **not suppressed**. If `token_extractor.py` did manage to capture `W8x10` out of this sentence (plausible, since it matches the section grammar cleanly), it would pass through as a live steel-section candidate despite being an example inside a general-notes abbreviation rule.

This is precise, directly-relevant evidence for the brief's Part 7/14 questions: **the existing mechanism is real but is a local-keyword check, not a page-role check** — it works when the suppressing word happens to fall in the same text block as the token, and fails when it doesn't (which is common, since a numbered general-notes page routinely has a page-level "GENERAL NOTES" heading far from any individual numbered item's own text block).

---

## I. Legend false-positive analysis

Restricting to the **strict, dedicated legend/general-notes/abbreviation cover sheets only** (the pages listed in §B's last column — 12 pages total across all 7 projects, out of 262):

| | plate-family hits | BENT hits |
|---|---:|---:|
| On dedicated legend/cover sheets | 15 | 7 |
| Total in corpus | 491 | 125 |
| **Share on dedicated legend sheets** | **3.1%** | **5.6%** |

**This is the single most important quantitative correction this audit makes to the brief's framing:** the overwhelming majority (≈94–97%) of BENT PL / plate-family text in this corpus is **not** on legend/cover pages at all — it's on **typical-detail sheets** (§G). A much looser keyword pass (any page mentioning "SCHEDULE" or "NOTES:" even once) does sweep in 12–45 pages per project and 80–84% of the hits, but that loose set is measuring "pages with any local note," not "context-only pages" — conflating the two would have led to over-stating the false-positive risk and under-stating the real problem (detail-sheet dimensional grammar, §H).

Within the strict legend-sheet set, real AISC-shaped strings do appear as pure illustrative examples — confirmed instances: `W27X84` (steel-beam-legend key, 3 projects), `W18X50`, `L4X3-1/2X5/16` and siblings (lintel-schedule examples embedded in general notes), `W8x10`/`W10x12`/etc. (GCDC's abbreviation table, §D). §H shows the current pipeline **already suppresses the first category** (legend-caption examples, via the local `LEGEND` keyword match) but **does not suppress the second** (abbreviation-table values, where the table's own heading isn't in the same text block as each row). A page-role signal (a document-level "this page is a legend/general-notes sheet, suppress any bare section-looking string on it unless it's inside an actual takeoff table") would close this remaining gap more reliably than the current per-line keyword approach, without needing to touch the framing-plan pages at all.

The brief's `semantic_context_only / takeoff_candidate / both / unknown` framing is supported by this evidence, with one refinement: typical-detail sheets need a **fifth** status distinct from all four — call it `template_detail` — because a `"3/8" BENT PL"` on a detail sheet is neither a located, quantifiable takeoff item (it has no plan reference or count) nor pure "context" (it's real, dimensioned, buildable content that a human estimator does use, typically by counting how many times the detail is called out elsewhere). Collapsing detail-sheet content into "context_only" would silently drop real cost information; collapsing it into "takeoff_candidate" would risk one detail's dimension being double-counted across every plan reference to it.

---

## J. Current code-path trace (full detail from the Explore-agent pass, condensed)

Full stage-by-stage trace with file:line citations was produced by a dedicated code-tracing pass over the pipeline and is summarized here; see that pass's numbered stages 0–11 for exhaustive detail. Headline findings:

- **No document-level or project-level context object exists anywhere in the runtime path.** Confirmed by exhaustive grep for `page_type`, `page_role`, `is_legend`, `project_context`, `document_profile`, `DrawingLanguageProfile`, `drawing_language`, `legend` (case-insensitive) across `backend/` — the only production hits are the file-identity manifest in `services/document_registry.py` (id/hash/page-count only, no semantic content) and the per-page scalar `engineering_relevance_score` in `services/pdf_parser.py:446,469`. Every classification/filter/prediction function inspected takes token/line/page-scoped arguments only.
- **The one existing whole-document computation** (`services/engineering/rule_engine.py:266`, `evaluate_document_rules()`) is a post-hoc graph-topology sanity check (beams without columns, etc.) that runs *after* predictions and never feeds back into classification.
- **Cleanest insertion point:** `services/multimodal/pipeline.py:68-115` already builds a `document` dict once per request and passes it by reference into every per-token prediction context (`"document": document`, line 108); `services/prediction/orchestrator.py:87-91` already reads `context.get("document")` (currently only for `source_file`). Attaching a `drawing_language_profile` key to that same `document` object and reading it at that same call site requires no signature changes anywhere downstream for a first pass.
- **Next-cleanest insertion points** (small, additive signature changes, not rewrites): `services/engineering_object_filter.py:53` `classify_engineering_object()` and `services/entity_taxonomy.py:127/175` — both are currently pure functions of the token text (+ optional AI/DB hints) with no document parameter; adding an optional `profile: dict | None = None` parameter to each and threading it from `extraction_engine.py:28` is a contained change.
- **What would need new code, not just threading:** actual legend-parsing logic. `services/document_intelligence.py:169` `_extract_tables()` today only hints on `SCHEDULE, TAKEOFF, QUANTITY, QTY, MEMBER SIZE, BEAM MARK, COLUMN MARK` — no `LEGEND` or `GENERAL NOTES` hint exists, and no function anywhere parses a legend's key/value pairs into structured data. This is a real gap, not a threading problem.
- **The `multimodal/` scaffolding is honestly named but does not contain any vision/VLM code.** `services/multimodal/pipeline.py:334-347` returns a hardcoded capabilities list — `["LayoutLMv3", "Donut", "ViT", "YOLO", "SAM", "PointNet", "Point Transformer", "GCN", "GraphSAGE"]` — that is pure aspiration; no import, class, or call for any of them exists anywhere in the backend. What's actually implemented and working (`services/multimodal/encoders.py`) is fusion of *feature modalities* (text/OCR/layout/geometry/graph), all derived from the PDF text layer and vector geometry — **there is no page-rasterization, no pixel encoder, and no VLM call anywhere in this repository's runtime pipeline.** The partner's Moondream experiment, whatever it consisted of, is not integrated here and left no artifacts in this repo (confirmed: the `multimodal/document.json`/`predictions.json`/etc. files under `backend/training/engineering_artifacts/doc_*/multimodal/` are all 0 bytes).

---

## K. Architecture options

| | A. Static deterministic (current) | B. Per-callout VLM | C. Legend-aware LLM → profile → deterministic | D. Hybrid |
|---|---|---|---|---|
| Accuracy on this corpus's failure modes | Misses ~83% of confirmed BENT PL instances (thickness-only regex gap, §H) and 100% of the GCDC-style abbreviation-substitution case | Unproven here — no in-repo evidence; user-reported pilot had 4 crops, positive results confounded by visible "BENT PL" text in the crop (§O) | Directly targets the two confirmed root causes (§H): a profile pass reading GCDC p.5 would supply the `"W8"=W8x10` rule and the `BENT PLATE` connection-type vocabulary in one read; the *regex* fix (allow thickness-only plates) is a code change, not an LLM job, and should happen regardless of what else is built | Best of both, but only pays for the VLM on what's left after A+C — likely a small residual set based on this corpus |
| Latency | Fastest, no external call | Slowest, per-crop; partner reported "slow inference" already | One call per document (or per legend page), amortized over the whole set — much cheaper than per-callout | Same as C plus occasional VLM calls |
| Explainability | Fully deterministic, but silent drops are currently unexplained (§H) | Weak — partner already hit malformed structured JSON output | Strong if implemented as "quote the exact legend sentence that justified this rule" (a natural fit — every finding in this audit is exactly that: a quoted sentence + a page citation) | Strong, inherits C's explainability for the deterministic majority |
| Hallucination risk | None (but silent-drop risk is real and currently untracked) | Real — partner's positive detections were confounded by the crop literally containing the words "BENT PL," which is a strong argument the model may be reading text, not geometry (§O) | Bounded, if (and only if) every LLM-proposed rule is validated against the same document's actual callouts before being trusted (the brief's own "validate that schema against actual callouts" step) — §G shows this validation is very feasible: most legend claims in this corpus *do* show up verbatim or near-verbatim in the detail sheets | Same bound as C |
| Structured-output reliability | N/A (regex) | Partner already observed malformed JSON | One document-scoped call is far easier to constrain/retry/validate than dozens of per-crop calls | Same as C |
| Scalability to 50–100pp sets | Trivial | Expensive — GCDC alone is 81 pages; a per-callout VLM pass over even a fraction of its confirmed 98 plate-family hits is a lot of calls for one document | Cheap — one call (or a handful, for the 3 projects that split legend content across multiple non-adjacent sheets, §B) per document regardless of total page count | Same as C, plus bounded residual VLM calls |
| Engineering effort | None (already built) | Moderate-high (already attempted, already hit real obstacles per the brief) | Moderate: needs (1) the regex/threshold fix in §H (small), (2) a legend-page locator (§B's scoring approach already works reasonably as a first pass), (3) a profile-extraction call + validation-against-real-callouts step (§G shows this is checkable), (4) the threading in §J (small, 2-3 files) | Highest total effort, but each piece is independently justified by this audit's evidence |
| Privacy/deployment | On-prem, no external call | Depends on hosting; partner already running locally (Moondream) | If self-hosted, same profile as B; if using a hosted LLM, means sending legend/notes text (not images) off-box — smaller and more redactable payload than a page image | Mixed |
| Learns project-specific notation | No | Only implicitly, per-crop, with no persistence | Yes, explicitly — that's the entire point, and this audit found real project-specific notation worth learning (GCDC's abbreviation table) that a per-crop VLM would never see, since it lives on the general-notes page, not near any individual callout | Yes |
| Distinguishes context from takeoff | Partial, and inconsistently (§H's LGD-001 vs LGD-002 finding) | No inherent mechanism | Yes, if the profile explicitly tags each extracted rule with where it applies (framing-plan callout vs. detail-sheet template vs. legend-example-only) — §I's proposed `template_detail` status maps directly onto this | Yes |

**The evidence does not favor B over C.** Nothing in this audit's real-PDF evidence argues for per-crop VLM classification as the next investment; it argues for (1) a small, high-confidence regex fix that is not an ML problem at all, and (2) a document-scoped profile extraction whose main value (per GCDC's abbreviation table) is only visible at the *document* level, not the crop level.

---

## L. Proposed "Drawing Language Profile" (schema grounded in what was actually found)

```json
{
  "project_id": "GCDC Building",
  "source_pages": {
    "abbreviations": [5],
    "general_notes": [1, 5],
    "connection_type_vocabulary": [5],
    "member_size_substitutions": [5],
    "legend_graphic_keys": []
  },
  "member_size_substitutions": {
    "W8": "W8x10", "W10": "W10x12", "W12": "W12x19",
    "W14": "W14x22", "W16": "W16x26",
    "C8": "C8x11.5", "C12": "C12x20.7",
    "HSS8x4": "HSS8x4x1/4"
  },
  "member_modifier_abbreviations": {
    "CANT": "cantilevered beam; size follows adjacent backspan if not indicated"
  },
  "fabricated_plate_terms": {
    "recognized": ["BASE PL", "BASE PLATE", "CAP PL", "CAP PLATE",
                    "STIFF PL", "STIFFENER PL", "STIFFENER PLATE",
                    "GUSSET", "GUSSET PL", "GUSSET PLATE",
                    "CONN PL", "CONNECTION PLATE", "CLIP ANGLE"],
    "dimension_grammar": "thickness_only_typical",
    "evidence_count": 98
  },
  "bent_plate_terms": {
    "recognized": ["BENT PL", "BENT PL.", "BENT PLATE"],
    "documented_as_connection_type": true,
    "documented_as_connection_type_evidence": [
      {"page": 5, "quote": "- BENT PLATE SHEAR CONNECTIONS", "status": "allowed_type"},
      {"page": 5, "quote": "BENT PLATE CONNECTIONS WELDED TO THE SUPPORTING MEMBER.", "status": "prohibited_when_welded_to_supporting_member"}
    ],
    "dimension_grammar": "thickness_only_typical",
    "interchangeable_with": ["POUR STOP", "CLOSURE ANGLE"],
    "modifier_word_order": "prefix (\"BENT PL\"), not suffix",
    "evidence_count": 10
  },
  "bent_modifier_on_other_shapes": {
    "observed": true,
    "example": "HSS16X4X1/2 BENT",
    "modifier_word_order": "suffix, opposite of bent-plate order",
    "note": "distinct grammar from bent_plate_terms; do not merge"
  },
  "page_roles": {
    "5": "legend_and_general_notes",
    "60": "typical_detail",
    "63": "typical_detail",
    "73": "framing_detail"
  },
  "evidence": [
    {
      "page": 5,
      "raw_text": "THE FOLLOWING MEMBER SIZE ABBREVIATIONS ARE USED ON THE FRAMING PLANS: \"W8\" = W8x10 ...",
      "interpretation": "project_specific_abbreviation_substitution_table",
      "validated_against_actual_callouts": "not yet performed - requires_engineer_review",
      "confidence": 0.95
    }
  ]
}
```

Deviations from the brief's starting sketch, driven by evidence: added `member_size_substitutions` and `member_modifier_abbreviations` as top-level keys (the single highest-value finding in this corpus, §D, wasn't anticipated in the brief's sketch at all); added `dimension_grammar` per term family, since §H shows the *grammar* gap (thickness-only vs. width×length) is a bigger lever than the vocabulary gap; added `bent_modifier_on_other_shapes` as a sibling to `bent_plate_terms` rather than folding it in, since §F.2 shows the word-order differs by shape family; kept `page_roles` deliberately coarse (legend/notes vs. typical-detail vs. framing-detail) rather than the brief's finer four-way split, per §I's `template_detail` finding.

### Where this profile could safely influence the pipeline (mapped to real insertion points, §J)

- **Candidate generation:** a token matching `PL\d+(?:[./]\d+)?$` (thickness only, no `X` group) should not be silently dropped by `classify_engineering_object` when a fabricated-plate role word (`BENT`, `CAP`, `CONN`, `STIFF`, `GUSSET`, `BASE`) appears in its line context — this is a **code fix** (loosen `_PLATE`'s `{1,3}` to `{0,3}` with a role-word co-requirement when the count is 0), independent of any profile, and should be prioritized first since §H shows it explains most of the loss on its own.
- **Classification:** once a profile exists, `entity_taxonomy.classify_category` can special-case `member_size_substitutions` (resolve `"W8"` → `"W8x10"` with `source="project_profile"`, distinct from `source="heuristic"`) exactly as the confidence dataclass already supports (`EntityClassification.source`, `entity_taxonomy.py:104-118`).
- **Token grouping:** not strongly evidenced in this corpus — the confirmed cases where "BENT" is lost are same-line adjacency losses (§H), not cross-line/spatial grouping failures; the brief's "BENT PL one span, 3/8" immediately above" scenario was not observed as the dominant pattern here (thickness and role-word were almost always same-line).
- **Parser selection:** already partially working — the routing fix the user mentioned (`STRUCTURAL_FAMILIES` in `orchestrator.py` excludes `PL`) is confirmed correctly preventing AISC-shape prediction on plate-family tokens (§J, Stage 7).
- **Context priors:** the profile's `page_roles` map is exactly what's missing from §I's false-positive analysis — a page tagged `legend_and_general_notes` should suppress bare section-looking strings site-wide on that page, closing the LGD-002 gap (§H) that the current line-local keyword check misses.
- **Human review:** every row in §D/§E/§G already carries a page citation and exact quote — that's precisely the "show the note that caused this" surface the brief asks for, and it cost nothing extra to produce this way.

---

## M. Controlled experiment proposal (smallest useful next POC)

1. **Fix the regex gap first, with no LLM at all** (§H): change `_PLATE` in `engineering_object_filter.py` to accept thickness-only plate callouts when a plate-family role word (`BENT|BASE|CAP|CONN|CONNECTION|STIFF|STIFFENER|GUSSET`) co-occurs in the token's context, and preserve the role word into a new `fabrication_modifier` field rather than discarding it. Re-run this exact 7-project corpus and measure the before/after recovery rate against the 491 plate-family / 112 bent-plate occurrences already catalogued here (`hard_case_corpus.json` gives the exact test cases). This alone is testable without any LLM and has a known, bounded evidence base to validate against — do this before anything else in this section.
2. **One-document legend-profile extraction, validated, on GCDC only** (the project with the richest, most decisive evidence — the abbreviation-substitution table): feed page 5's text (not an image) to an LLM with a constrained schema matching §L, then **programmatically re-scan the other 80 pages of the same PDF for literal occurrences of `"W8"`, `"W10"`, `"C8"`, `"C12"`, `"HSS8x4"`** to see whether the substitution table is actually used elsewhere in the set (this was flagged `requires_engineer_review` in §G because it wasn't checked in this pass) — this is the direct "validate the schema against actual callouts" step the brief calls for, and it's cheap because the corpus and expected values are already known.
3. **Only after both above:** a small, deliberately-designed VLM comparison — not per the partner's original 4-crop pilot, but structured per §O below (positive/negative/masked/unmasked, image-only vs. image+text vs. image+document-profile) — scoped to the residual cases that steps 1–2 don't resolve (e.g., detail-sheet `template_detail` classification, §I, which is a genuinely visual/layout judgment, not a text-grammar one).

---

## N. Engineer questions

1. **GCDC's `"W8"=W8x10` table (§D/§G):** does this substitution rule actually appear used on GCDC's own framing plans, or is it boilerplate general-notes language carried from a firm's template that happens not to apply to this particular building? (This audit did not check the other 76 pages for it — flagged `requires_engineer_review`.)
2. **The "BENT PL" vs "TEXT_NOTE" discrepancy (§H):** was the partner's VLM pilot run against this same pipeline/repo, an older version, or a different labeling/review tool? The string `TEXT_NOTE` does not exist anywhere in this repository — clarifying this matters for whether §H's silent-deletion finding is the actual mechanism the partner observed, or whether there's a separate code path (e.g. a labeling UI) not covered by this audit.
3. **Thickness-only plate callouts (§H, the dominant root cause):** when a drawing gives only a thickness (`"3/8" BENT PL"`, `"1/4" CAP PL"`) with no width/length, is the actual fabricated size ever fully determined by the detail geometry itself (e.g., scaled off the drawing, or a fixed leg length implied by the connecting member), or is it genuinely open-ended pending shop drawings? This determines whether "thickness-only plate → still a valid, quantifiable takeoff candidate with an inferred size" or "→ correctly not quantifiable without a shop drawing" is the right target behavior.
4. **Detail-sheet BENT PL occurrences (§E/§G/§I):** every confirmed bent-plate instance in this corpus was found on a detail/section sheet, referenced by callout bubble from framing plans, rather than dimensioned directly on a plan. Is the correct estimating behavior to count *callout-bubble references* to a detail (i.e., how many times detail 4/S-301 is invoked) as the real quantity driver, rather than trying to extract a quantity from the detail sheet itself?
5. **The `BENT PLATE` prohibited-connection-type note (GCDC p.5, §E):** the same phrase is documented once as an *allowed* type (design-table submittal requirement) and once as *prohibited* (when welded to the supporting member) elsewhere on the same page. Is this a real, meaningful distinction (bolted bent-plate connections allowed, welded ones prohibited) that a future profile needs to preserve, or could this be a boilerplate-notes inconsistency worth flagging back to the source firm?
6. **Interchangeable terms (§F.3):** is it engineering-accurate to treat `BENT PLATE` / `POUR STOP` / `CLOSURE ANGLE` as one functional role with three acceptable fabrications for cost-estimating purposes, or do they carry meaningfully different unit costs that must stay distinguished even when the drawing treats them as interchangeable?

---

## O. VLM experiment critique and recommendation for Deep Research

### What the partner's Moondream pilot established vs. did not (per the user's description — no artifacts exist in this repo to independently verify, confirmed via file check: the `multimodal/*.json` files under `backend/training/engineering_artifacts/doc_*/` are all 0 bytes)

**Established (as reported):** local VLM inference is technically runnable against real drawing crops; the model can, in at least some of 4 cases, output a string resembling "BENT_PLATE."

**Not established, and this audit's independent findings sharpen exactly why:** genuine visual/geometric understanding of a bent fold-line in a section view — because, per the brief's own description, the crops "literally contained the words `BENT PL`," and this audit independently confirms (§E) that the literal phrase `BENT PL`/`BENT PLATE` is present, unambiguously, in the surrounding text of essentially every real instance in this corpus. A model that is a strong OCR/text-reasoner would score identically to a model with real geometric/visual understanding on this exact test design, because the two capabilities were never separated by the experiment. Also not established: negative-case discrimination (this audit's §E hard-negative set — `BENTONITE`, `BENT GRIPSTAY`, `BENT HSS` — is exactly the kind of confusable-but-wrong case a real test needs and the 4-crop pilot didn't include); generalization beyond 4 hand-picked crops; structured-output reliability (partner already reported malformed JSON); and production viability (latency already reported as slow).

### Stronger experiment design (proposed, not run)

Grounded in this audit's real corpus rather than abstract categories: use the hard-case corpus already built here (`hard_case_corpus.json` — 6 positive BENT-plate variants, 4 sibling fabricated-plate terms, 4 hard negatives including the confirmed `BENTONITE`/`BENT GRIPSTAY`/`BENT HSS` confusables, 5 legend/false-positive-risk cases including the GCDC abbreviation table) as the seed set, and specifically:

1. Run each case **image-only**, then **image with the class word masked/redacted from the crop**, then **image + extracted text**, then **image + extracted text + the relevant Drawing Language Profile entry from §L** — this is the only way to separate "reads the word BENT" from "sees a bend" from "knows this project calls this a recognized connection type."
2. Include the confirmed hard negatives (§E) as required cases, not optional ones — a model that can't distinguish `BENT GRIPSTAY` (masonry anchor) from `BENT PL` (plate) on text alone hasn't demonstrated anything the current pipeline couldn't get closer to with a role-word regex.
3. Treat the LGD-002 case (`"W8"=W8x10` inside general notes) as a required negative for any candidate-generation experiment — a system that fires on this text as a "real member" has the exact false-positive failure this audit found the current pipeline only partially guards against (§H).

### What should drive the external Deep Research — specific to unexplained patterns found here, not generic OCR/VLM/LLM questions

1. **The thickness-only-plate regex gap (§H) explains 5 of 6 real bent-plate failures and is not an ML problem.** Before any Deep Research into legend-aware LLMs, research whether this same "grammar assumes two dimensions, reality gives one" pattern recurs for *other* AISC/fabricated-element families in a larger corpus (this audit only had 7 projects) — e.g., do angle callouts, HSS wall thicknesses, or bolt callouts show the same single-vs-paired-dimension mismatch? If so, the highest-leverage next investment across the whole pipeline may be dimension-arity flexibility generally, not anything legend-specific.
2. **Why is bent-plate dimension grammar (thickness-only) so different from rolled-section grammar (which is fully specified, e.g. `W18X50`)?** This audit didn't determine whether that's a drafting-standard convention (AISC/industry-wide) or a coincidence of these 7 firms/projects. If it's an industry convention, a *general* rule ("fabricated plate elements are conventionally single-dimensioned; catalog sections are conventionally fully dimensioned") could apply far beyond bent plate — worth researching against a larger, cross-firm sample before building anything project-specific.
3. **Does the GCDC-style member-size substitution table (§D) recur across a larger sample, and in what form?** This audit found it on exactly 1 of 7 projects, as a numbered general note. Deep Research should determine whether this is a rare, firm-specific practice (in which case a legend-aware profile is high-value but low-frequency) or a common-but-inconsistently-worded practice across many firms (in which case it's worth a dedicated, higher-priority detector rather than a generic profile-extraction pass).
4. **The `template_detail` third bucket (§I):** this audit found essentially all real bent-plate evidence lives on detail sheets referenced by callout bubble, not on plan sheets directly. Research how estimators actually convert "detail referenced N times across the plan set" into a takeoff quantity today (manually) — this determines whether a `template_detail`-tagged candidate should ever become a takeoff line item automatically, or whether its only job is to inform a human reviewer counting callout-bubble references elsewhere.
5. **The two-line, contradictory GCDC "bent plate" allowed/prohibited note (§E, §N Q5):** research whether this pattern (a term appearing in both an allowed-types list and a prohibited-conditions note on the same sheet) is common industry boilerplate that a real project-language profile needs to know how to *not* over-simplify into a single true/false "is bent plate allowed" flag.

---

## P. Quantification summary (all counts, tagged by confidence)

*(See `scan_summary.json` and `hard_case_corpus.json` in this folder for the full machine-readable data behind every number in this report.)*

- **Confirmed:** 7 PDFs inspected, 262 total pages, all vector/text-native (0 raster pages).
- **Confirmed:** 12 pages across the 7 projects are dedicated legend/general-notes/abbreviation cover sheets (strict definition, §B); 92 pages (loose definition, any page mentioning "SCHEDULE"/"NOTES:" once) — the loose set is dominated by typical-detail and schedule sheets, not cover pages (§I).
- **Confirmed:** 491 plate-family regex hits corpus-wide; 125 raw "BENT" occurrences, of which 112 (89.6%) are genuine bent-plate references and 13 (10.4%) are hard-negative false triggers (§E).
- **Confirmed:** only 3.1% of plate-family hits and 5.6% of BENT hits occur on dedicated legend/cover sheets — the rest is on detail/schedule/framing sheets (§I).
- **Confirmed (by direct execution of production code):** 5 of 6 representative real bent-plate field callouts fail the current plate-detection regex specifically because they give only a thickness, not a width×length pair (§H); this same failure was independently confirmed for CAP PL and CONN PL callouts.
- **Confirmed:** 2 of 7 projects (GCDC, Ketcham) document "bent plate" in general-notes prose; 0 of 7 give it a formal abbreviation-table or symbol-legend entry (§E).
- **Confirmed:** 1 of 7 projects (GCDC) has an explicit project-specific member-size abbreviation substitution table (§D) — the highest-value single finding in this audit.
- **Confirmed, one case each way:** the existing local-keyword legend-suppression mechanism correctly suppresses a legend-caption AISC example (LGD-001) but does not suppress an abbreviation-table AISC example when the suppressing heading isn't in the same text block (LGD-002) (§H/§I).
- **Not established / requires engineer review:** whether GCDC's abbreviation table is actually used on that project's own framing plans (§N Q1); whether thickness-only plate callouts have a determinable size without a shop drawing (§N Q3); whether the partner's "classified as TEXT_NOTE" description maps to any code path that actually exists in this repository (§H, §N Q2).
