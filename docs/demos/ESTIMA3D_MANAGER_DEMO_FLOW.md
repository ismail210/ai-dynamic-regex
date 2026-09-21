# Estima3D — Manager Demo Flow

Verbal demo guide for Upload → Extraction → Analyse → Results → Semantic Review → Corrected PDF.

---

## 1. Product purpose

Estima3D helps teams turn imperfect structural steel PDFs into a **trusted semantic representation** before takeoff and geometry work continues.

Structural drawings are hard for software: OCR errors, missing thickness on angles, decimal vs fractional notation, and split labels all look “almost right” but are not takeoff-safe. Estima3D’s job is to **extract, understand, surface risk, and apply only approved corrections** — not to invent steel sizes from a catalog.

It is **not** “just another takeoff engine.” It prepares cleaner drawing semantics so the existing takeoff / geometry pipeline can work from better inputs.

---

## 2. Upload

When a user uploads a structural PDF:

- The file is registered as the **source document**.
- No extraction or AI work runs at this step alone.
- The **original PDF stays immutable** — byte-for-byte unchanged for the life of the document.

All later corrections produce a **separate derived artifact**, never an overwrite of the upload.

---

## 3. Extraction

Extraction pulls text (and related engineering objects) from the PDF:

- Words / tokens with **page** and **bounding box** positions.
- That spatial context matters: corrections must land on the right annotation region.

Extraction is the **raw input layer**. It does **not** assume every string is a valid structural member.

---

## 4. Analyse

Analyse applies engineering semantics to extracted information:

- Normalizes representation where safe (e.g. case / separators).
- Detects damaged or incomplete designations.
- Runs prediction / explainability for takeoff-oriented results.
- Keeps **safety gates**: missing information is not guessed from catalog presence alone.

Manager-friendly distinctions:

| Kind | Meaning |
|------|---------|
| **Normalization** | Same steel designation, cleaner writing (representation only). |
| **Repair** | Corrupted text → suggested valid designation (needs human Accept). |
| **Completion** | Missing part filled **only** when drawing-backed evidence allows it. |
| **Association** | Linking a label to nearby geometry / context as evidence — not inventing sizes. |

Example of what we **do not** do: `L4X4` does **not** automatically become `L4X4X1/4` just because that size exists in AISC.

---

## 5. Results

Results answer: **“What structural results did the system extract / predict?”**

Results stay a **clean takeoff-oriented table** (tokens, sections, confidence, validation status).

Results are **not** the place for:

- damaged-label queues  
- incomplete-angle debugging  
- Accept / Reject / Accept All  

Those belong in **Semantic Review**.

---

## 6. Semantic Review

Semantic Review is where uncertain / damaged / correctable annotations are reviewed:

- Original value  
- Detected / effective value  
- Issue type  
- Suggestion **when the backend already has one** (never fabricated in the UI)  
- Status  
- **Accept** · **Reject** · **Manual Edit** · **Accept All**

**Accept means the user has approved the correction.** There is no hidden second approval step after Accept.

Reject and Cancel leave the PDF unchanged. Manual Edit is draft until Accept.

---

## 7. Correction engine (after Accept)

Simple flow:

1. User clicks **Accept** (or Accept after Manual Edit).  
2. Semantic state is **persisted** (`semantic.json` + review history).  
3. A **derived corrected PDF** is regenerated from: original + all accepted text corrections.  
4. The API returns a **cache-busted viewer URL** (`?v=revision`).  
5. The user can **download** the corrected PDF.

Original upload is never overwritten.

---

## 8. Corrected PDF

The corrected PDF is the **authoritative visual proof** — not a React overlay alone.

```
Original PDF  +  approved corrections  =  Corrected PDF (derived)
```

Only the required annotation regions are covered and rewritten (PyMuPDF). Page structure is preserved as much as possible.

Engineering formatting is applied on write (e.g. valid third-dimension decimals → standard fractions such as `0.375` → `3/8` for rectangular HSS / complete angles). Round HSS / pipe decimals stay decimal.

---

## 9. Accept All

Accept All exists so a reviewer can approve **all currently eligible** repair proposals in one action:

1. Backend validates eligibility (skips already accepted / rejected / unsafe).  
2. Persists each acceptance with **individual history** (bulk tagged).  
3. Regenerates **one** final corrected PDF.  
4. Viewer refreshes once.

Unsafe or ineligible items are **not** auto-accepted.

---

## 10. Safety / trust

Estima3D prefers abstention over invention:

- Catalog existence ≠ evidence to complete a missing thickness.  
- Incomplete angles (e.g. `L4X4`) stay incomplete / not takeoff-eligible unless evidence rules allow completion.  
- Excel / AISC verify — they do not drive prediction selection.  
- Production inference stays on the existing orchestrated path (no VLM / XGB / GraphSAGE “demo shortcuts”).

Trust for structural takeoff depends on **not** quietly inventing member sizes.

---

## 11. Why this helps the existing takeoff pipeline

| Layer | Responsibility |
|-------|----------------|
| **Estima3D** | Understand drawing text semantics; surface risk; apply **human-approved** corrections; emit corrected PDF + semantic state. |
| **Downstream geometry / takeoff** | Consume cleaner structured information for geometry and quantity work. |

We do **not** claim Estima3D replaces the full geometry / GHX takeoff stack.

---

## 12. Demo script (verbal)

1. **Upload** the ST drawing.  
2. Run **Extraction**, then **Analyse**.  
3. Open **Results** — show a clean results table (no correction queue).  
4. Open **Semantic Review**.  
5. Select a damaged / correctable annotation.  
6. Show original → suggestion (when present).  
7. Click **Accept**.  
8. Show the **corrected PDF** in the viewer (revision URL).  
9. State clearly: **original PDF unchanged**.  
10. If multiple eligible items exist, show **Accept All** → one final PDF.  
11. **Download** the corrected PDF.

Keep the story: *clean Results for takeoff numbers; Semantic Review for trust and PDF truth.*

---

## 13. Validation status

Update after each live run. Separate **VERIFIED** from **NOT VERIFIED**.

### Backend unit / API tests (this branch)

| Check | Status |
|-------|--------|
| Angle grammar + `L4X4X0.375` → `L4X4X3/8` formatting | **VERIFIED** (pytest: 27 passed in `test_semantic_preprocessor_normalization` + `test_semantic_corrected_pdf`) |
| Incomplete `L4X4` not completed by formatter | **VERIFIED** (pytest + live controlled PDF) |
| Accept writes real corrected PDF; original hash unchanged | **VERIFIED** (pytest + live) |
| Accept All: one PDF, skips rejected, history per annotation | **VERIFIED** (pytest) |
| Placement uses measured text width (not fixed global pad) | **VERIFIED** (pytest + controlled live: W18X40 vs NEAR overlap area 0) |

### Live Burrville / ST application flow (API, not browser)

Documents used (existing semantic damage corpora + live API on `127.0.0.1:8000`):

- Burrville: `burrville_SEMANTIC_DAMAGE_TEST.pdf` → `doc_06009aaef05256fa`
- ST: `st_SEMANTIC_DAMAGE_TEST.pdf` → `doc_4a167ac3d049e172`
- Controlled synthetic PDF for fraction/spacing: `doc_cda64ab70c6b1dfd`

| Check | Burrville | ST | Controlled |
|-------|-----------|-----|------------|
| Upload | **VERIFIED** | **VERIFIED** | **VERIFIED** |
| Extraction | **VERIFIED** | **VERIFIED** | n/a (semantic-only) |
| Analyse | **VERIFIED** | **VERIFIED** | skipped |
| Results stay clean (no correction panel in code) | **VERIFIED** (code) | **VERIFIED** (code) | n/a |
| Semantic process | **VERIFIED** | **VERIFIED** | **VERIFIED** |
| Accept + history | **VERIFIED** (1421 accept history events; Accept All tagged) | **VERIFIED** (1256 accept history; 1 reject preserved) | **VERIFIED** |
| Corrected PDF download / differs from original | **VERIFIED** | **VERIFIED** | **VERIFIED** |
| Fraction in PDF (`HSS…3/8`, `L4X4X3/8`) | **VERIFIED** (`HSS6X6X3/8` in text extract) | **VERIFIED** | **VERIFIED** (`L4X4X3/8`, `HSS8X8X3/8`) |
| Accept All single bulk call | **VERIFIED** | **VERIFIED** (HTTP 200) | n/a |
| Original PDF immutable (hash) | **VERIFIED** | **VERIFIED** | **VERIFIED** |
| Spacing (bbox non-overlap vs neighbor) | not separately measured | not separately measured | **VERIFIED** (gap_x≈79, overlap 0) |
| Browser viewer click-through | **NOT VERIFIED** | **NOT VERIFIED** | **NOT VERIFIED** |
| Visual spacing eyeball in UI | **NOT VERIFIED** | **NOT VERIFIED** | PNG render saved under `training/eval_cache_backups/final_demo_fraction_spacing.png` (offline render, not browser) |

Report JSON: `backend/training/eval_cache_backups/final_demo_validation_report.json`

### Demo caution (Accept All eligibility)

On full Burrville/ST damage corpora, `repair_candidates` can attach to non-member note text. **Accept All will accept every eligible repair candidate** the backend currently marks eligible. For a manager demo, prefer **targeted Accept** on known structural damage cases (Semantic Review navigator / damage corpus), or Accept All only after reviewing the eligible queue. Tightening Accept All eligibility further is a separate safety task — not weakened here.

### Frontend

| Check | Status |
|-------|--------|
| Semantic Review Accept / Accept All unit tests | **VERIFIED** (34 vitest passed: `semanticContract` + `SemanticReviewPage`) |
| ResultsCorrectionsPanel removed; ResultsBody clean | **VERIFIED** |
| Full browser E2E (Upload → click Accept in UI) | **NOT VERIFIED** in this session |

---

*Document for managers and demo presenters. Keep claims aligned with implemented behavior only.*
