# Post-Incomplete-L Abstention Evaluation

**Date:** 2026-09-10  
**Scope:** Evaluation only — no new accuracy fix, no Graph/XGB/HSS/takeoff logic changes, no training, no commit.  
**Question:** Did the shipped incomplete L/2L abstention gate remove unsafe completions on the shared 8-document set, without regressing complete / shop-cut L?

---

## 1. Evaluation Setup

### Old cache (preserved)

| Item | Value |
|---|---|
| Location | `backend/training/eval_cache_backups/doc_*/predictions_view.json` |
| Timestamp | **2026-08-31** (filesystem mtimes) |
| Documents | 8 (same set as FINAL accuracy gap audit / shadow eval) |
| Rows | **9,396** |

| Document ID | Source PDF (from shadow summary) | Labels |
|---|---|---:|
| `doc_0bfc2d61245dbce2` | ST.pdf | 628 |
| `doc_0d910a43b4a021e3` | Burrville ES - ST.pdf | 1,252 |
| `doc_240bd2541fbca147` | 1200 K_Permit_Bid_Dwgs - Structural.pdf | 667 |
| `doc_47dc7ef27f6e5d7e` | GCDC Building 4 - ST1.pdf | 3,304 |
| `doc_683e6eef0a945c9a` | Struct.pdf | 1,215 |
| `doc_6a9a9684bb19343b` | 03 - SFSLS_…_STRUCTURAL… | 922 |
| `doc_9414716bffc67596` | Structure - Copy.pdf | 475 |
| `doc_f6ddc4a7e233ffb0` | ST - Springhill Lake.pdf | 933 |

### How predictions were originally produced

Full Analyze / staged multimodal pipeline writes `predictions_view.json` (OCR + fusion + geometry/graph fields). There is **no** dedicated “refresh 8-doc predictions” script; ranker/Graph scripts **read** this cache and do not regenerate it.

### Refresh method (current code, cheapest established path)

| Item | Value |
|---|---|
| Entry point | `services.prediction.orchestrator.predict_token` (same text path as `scripts/evaluate_pipeline.py`) |
| Inputs | Cached `raw_text` / `original_token` from the Aug 31 dumps (780 unique strings → memoized) |
| Output | `backend/training/eval_cache_backups/post_incomplete_L_abstention/doc_*/predictions_view.json` |
| Meta | `…/post_incomplete_L_abstention/run_meta.json` |
| Code under test | Working tree including incomplete-angle abstention in `orchestrator.py` + `label_ranker_hook.py` |
| Commit base | `29bdc6a` + local incomplete-L changes |

**Not used / not enabled:** Graph v2, GraphSAGE, learned fusion, ML label ranker, geometry missing-label inference, VLM/API. Production flags left unchanged (`document_prior_enabled` remains True; incomplete-angle path skips TF-IDF / corrections / document-prior completion).

**Caveat:** OLD = full multimodal Aug 31 snapshot. NEW = current **text** `predict_token` replay on the same printed tokens. That is the right cheap comparison for the incomplete-L gate (text completion was the failure mode). Broader OLD↔NEW deltas also include shop-cut protection and other post-Aug-31 text-path behavior — not only the incomplete-L gate. Gate-attributable rows are called out separately in §8.

### Gold methodology (same as FINAL audit)

- Proxy gold = printed core after shop/cut strip (`proxy_gold_section`)
- Incomplete L/2L → **no gold**; abstain / preserve legs-only is correct
- Equivalence: engineering normalize + HSS decimal / punctuation tolerance
- Denominator for accuracy = rows with proxy gold (**7,198**)

---

## 2. Old vs New Baseline

| Metric | OLD (Aug 31 cache) | NEW (current-code refresh) |
|---|---:|---:|
| Total rows | 9,396 | 9,396 |
| Gold rows | 7,198 | 7,198 |
| Correct | 7,099 | 7,143 |
| Wrong | 99 | 55 |
| Proxy-gold accuracy | **98.62%** | **99.24%** |
| Incomplete printed | 16 | 16 |
| Incomplete bad completions | **16** | **0** |
| Incomplete abstentions | 0 | **16** |

*(Prior FINAL audit reported 7,088/7,198 = 98.47% on OLD with a slightly stricter refined pass; this refresh uses one consistent OLD/NEW scorer. Denominator and document set are identical.)*

| Category | Old | New | Delta |
| -------------------------- | --: | --: | ----: |
| Incomplete L completion | 16 | 0 | −16 |
| Incomplete 2L completion | 2 | 0 | −2 |
| L → 2L | 10 | 9 | −1 |
| L thickness error | 41 | 3 | −38 |
| Complete explicit L errors | 67 | 27 | −40 |
| Shop-cut L errors | 53 | 10 | −43 |
| HSS → W | 10 | 0 | −10 |

---

## 3. Incomplete L Results

| Check | Result |
|---|---|
| Incomplete L printed | **16** (unchanged denominator) |
| Incorrectly completed (OLD) | **16 / 16** |
| Abstentions (NEW) | **16 / 16** (`completion_status=missing_thickness`, `takeoff_eligible=False`) |
| Still completed incorrectly (NEW) | **0** |

### Required probes

| Printed | OLD prediction | NEW prediction | Status | Takeoff |
|---|---|---|---|---|
| `L4x4` (multiple docs) | `L4X3X1/4` or `L4X4X3/8` | **`L4X4`** | `missing_thickness` | **False** |
| `2L4x4` | `2L4X4X1/4` | **`2L4X4`** | `missing_thickness` | **False** |
| `L5x3` | `C15X33.9` / `L5X3X5/16` | **`L5X3`** | `missing_thickness` | **False** |
| `L5x5` | `L5X5X1/2` | **`L5X5`** | `missing_thickness` | **False** |
| `L6x3` | `L6X6X3/4` | **`L6X3`** | `missing_thickness` | **False** |

**Verified:** `L4X4` does **not** become `L4X4X1/4`, `L4X3X1/4`, `2L4X4X1/4`, or any other complete section.  
**Verified:** `2L4X4` does **not** become `2L4X4X1/4`.

---

## 4. L → 2L Results

| | Old | New |
|---|---:|---:|
| L → 2L count | 10 | 9 |

### OLD shop-cut L→2L (mostly stale vs current shop-cut protection)

Examples that **no longer** fail as L→2L after refresh (stale-cache / shop-cut path):

- `L3X3X3/8X0'-6"` → was `2L3X3X3/8X3/4` → now **`L3X3X3/8`**
- `L4X4X3/8X0'-8"` → was `2L…` → now protected core
- `L3x3x3/8x0'-6"` → was `2L…` → now **`L3X3X3/8`**

### NEW remaining L → 2L (live text-path errors — **not** caused by incomplete-L gate)

| Document | Raw | Gold | New pred |
|---|---|---|---|
| `doc_0d910a43b4a021e3` | `L3X3X5/16,` | `L3X3X5/16` | `2L3X3X5/16` |
| `doc_240bd2541fbca147` | `L4X4X5/16,` | `L4X4X5/16` | `2L4X4X5/16` |
| `doc_47dc7ef27f6e5d7e` | `L2x2x10` | `L2X2X10` | `2L2X2X1/4` |
| `doc_47dc7ef27f6e5d7e` | `L6x6x5/16;` | `L6X6X5/16` | `2L6X6X5/16` (×2) |
| `doc_47dc7ef27f6e5d7e` | `L5x5x5/16"` | `L5X5X5/16"` | `2L5X5X5/16` |
| `doc_47dc7ef27f6e5d7e` | `L6x6x1/2@2'-0"` | `L6X6X1/2@2-0"` | `2L6X6X1/2` |
| `doc_6a9a9684bb19343b` | `L3x3x5/16,` | `L3X3X5/16` | `2L3X3X5/16` |
| `doc_9414716bffc67596` | `L4x4x5/16,` | `L4X4X5/16` | `2L4X4X5/16` |

Root pattern: trailing `,` / `;` / `"` often leaves `catalog_valid_exact_section` / `core_section_token` without a clean lock → TF-IDF can promote **L → 2L**. Incomplete-L abstention does not cover these (they already have thickness).

---

## 5. L Thickness Results

| | Old | New |
|---|---:|---:|
| L thickness errors | 41 | 3 |

### Stale-cache shop-cut thickness (fixed by current shop-cut protection, not by incomplete-L gate)

OLD often had e.g. `L4x3x1/4x6"` → `L4X3X5/16`.  
NEW live check: `L4x3x1/4x6"` → **`L4X3X1/4`**; `L3x3x3/8x0'-6"` → **`L3X3X3/8`**.

~**43** shop-cut L rows that were wrong in OLD are correct in NEW (`stale_shop_fixed.jsonl`).

### Remaining live L thickness errors (NEW)

| Document | Raw | Gold | New pred |
|---|---|---|---|
| `doc_47dc7ef27f6e5d7e` | `L3x3x1/4@8'` | `L3X3X1/4@8` | `L3X3X3/8` |
| `doc_47dc7ef27f6e5d7e` | `L6x4x1/4x4"` | `L6X4X1/4` | `L6X4X3/4` |
| `doc_6a9a9684bb19343b` | `L5x5x1/4` | `L5X5X1/4` | `L5X5X1/2` |

---

## 6. Complete / Shop-Cut L Regression Check

### Complete explicit L (clean designations)

Live `predict_token` probes:

| Input | Output | Status |
|---|---|---|
| `L4X4X1/4` | `L4X4X1/4` | complete, takeoff-eligible |
| `L5X3X3/8` | `L5X3X3/8` | complete |
| `L4X3X1/4` | `L4X3X1/4` | complete |

Aggregate explicit L gold: **165/232 → 205/232** correct (OLD → NEW). Net improvement; remaining misses are mostly punctuation / odd tokens (§4–5), not incomplete-gate damage.

### Shop-cut L

| Input | Output |
|---|---|
| `L4x3x1/4x6"` | **`L4X3X1/4`** |
| `L3x3x3/8x0'-6"` | **`L3X3X3/8`** |

Shop-cut L gold rows: **4/57 → 47/57** correct. Remaining **10** “wrong” include gold-string artifacts (`…X0-3"` still attached) where the **section core** is already right (`L3X3X1/4`, `L8X6X1/2`, …) plus a few live `@` / punctuation failures.

**Incomplete-L gate did not regress clean complete or standard shop-cut L.**

---

## 7. HSS → W Check

| | Old | New |
|---|---:|---:|
| HSS gold rows | 869 | 869 |
| HSS → W | **10** | **0** |

HSS logic was **not** changed in this task. The drop reflects **text-path refresh vs Aug 31 multimodal fusion**, not the incomplete-L gate. Do not treat this as an HSS fix proof without a full multimodal re-Analyze.

---

## 8. Changed Predictions

### A. Caused by the new incomplete-L gate (all 16 incomplete printed rows)

| Document | Raw | Old prediction | New prediction | Status | Takeoff eligible |
|---|---|---|---|---|---|
| `doc_240bd2541fbca147` | `L5x5` | `L5X5X1/2` | `L5X5` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `L4x4` | `L4X3X1/4` | `L4X4` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `L4x4` | `L4X3X1/4` | `L4X4` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `L5x3` | `C15X33.9` | `L5X3` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `L5x3` | `C15X33.9` | `L5X3` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `2L4x4` | `2L4X4X1/4` | `2L4X4` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `L5x5` | `L5X5X1/2` | `L5X5` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `2L4x4` | `2L4X4X1/4` | `2L4X4` | `missing_thickness` | False |
| `doc_47dc7ef27f6e5d7e` | `L6x3` | `L6X6X3/4` | `L6X3` | `missing_thickness` | False |
| `doc_9414716bffc67596` | `L5X3` | `L5X3X5/16` | `L5X3` | `missing_thickness` | False |
| `doc_f6ddc4a7e233ffb0` | `L4x4` | `L4X3X1/4` | `L4X4` | `missing_thickness` | False |
| `doc_f6ddc4a7e233ffb0` | `L4x4` | `L4X3X1/4` | `L4X4` | `missing_thickness` | False |
| `doc_f6ddc4a7e233ffb0` | `L4x4` | `L4X4X3/8` | `L4X4` | `missing_thickness` | False |
| `doc_f6ddc4a7e233ffb0` | `L4x4` | `L4X3X1/4` | `L4X4` | `missing_thickness` | False |
| `doc_f6ddc4a7e233ffb0` | `L4x4` | `L4X3X1/4` | `L4X4` | `missing_thickness` | False |
| `doc_f6ddc4a7e233ffb0` | `L5X3` | `L5X3X5/16` | `L5X3` | `missing_thickness` | False |

### B. Other OLD→NEW deltas (current code broadly, not the incomplete gate)

- Large share of shop-cut L thickness / L→2L fixes = **stale Aug 31 cache** vs already-shipped shop-cut exact protection.
- Some complete-L rows with trailing punctuation now fail catalog lock and get TF-IDF 2L (see §4) — **pre-existing text-path gap**, exposed by refresh methodology.
- Artifacts: `changed_rows.jsonl`, `stale_shop_fixed.jsonl`, `live_shop_remain.jsonl`, `regressions.jsonl` under the NEW cache dir.

---

## 9. Safety Verification

| Requirement | Confirmed |
|---|---|
| Explicit complete sections remain protected | Yes (`L4X4X1/4`, `L5X3X3/8`, `L4X3X1/4`) |
| Shop-cut sections remain protected | Yes (`L4x3x1/4x6"`, `L3x3x3/8x0'-6"`) |
| Incomplete L cannot receive thickness | Yes (0/16 completions) |
| Incomplete L cannot become 2L | Yes |
| Incomplete L cannot receive document-prior / TF-IDF / graph-geometry completion | Yes (gate skips candidate injection; Graph not enabled) |
| Incomplete L not takeoff-eligible as complete AISC | Yes (`takeoff_eligible=False`, `missing_thickness`) |
| No production flags enabled for this experiment | Yes (GraphSAGE / learned fusion / ranker / geometry-ML all False) |
| No Graph code changes in this task | Yes (evaluation only) |
| Old Aug 31 cache preserved | Yes (not overwritten) |

---

## 10. Conclusion

1. **Did the incomplete-L gate remove unsafe completions?**  
   **Yes.** **16 → 0** unsafe incomplete completions. All 16 now preserve the printed core with `missing_thickness` and are not takeoff-eligible.

2. **Did it introduce regression on complete / shop-cut L?**  
   **No** for the gate’s scope. Clean complete and standard shop-cut probes pass. Broader refresh still shows punctuation-driven L→2L issues that are **outside** the incomplete-L gate.

3. **How many L → 2L errors remain?**  
   **9** on the NEW text refresh (was 10 on OLD). Most OLD shop-cut L→2L cases are gone; remaining are punctuation / odd-token live failures.

4. **How many L thickness errors remain?**  
   **3** on NEW (was 41 on OLD). The bulk of the drop is **stale-cache shop-cut** correction already present in current production code.

5. **Are remaining shop-cut errors stale or live?**  
   - **Stale (fixed by refresh / current shop-cut protection):** ~43 rows.  
   - **Live remain:** ~10 gold-mismatched shop-cut rows; several are gold-string artifacts with correct cores; a few are real (`@` length / odd forms).

6. **Did HSS→W change?**  
   **10 → 0** on this text refresh. **Not** attributed to incomplete-L; HSS logic untouched. Treat as methodology/context difference until a full multimodal re-Analyze.

7. **What should be fixed NEXT?**  
   **Deterministic “printed L must not become 2L”** (and strip trailing `,;"` / odd length marks so `catalog_valid_exact_section` locks), especially for tokens like `L3X3X5/16,` and `L5x5x5/16"`. Secondary: harden `@`-suffixed / odd shop-cut thickness cases that still miss the core lock. Do **not** enable Graph / ranker / VLM for this.

---

### Artifact index

| Path | Role |
|---|---|
| `training/eval_cache_backups/doc_*/predictions_view.json` | OLD Aug 31 (preserved) |
| `training/eval_cache_backups/post_incomplete_L_abstention/` | NEW current-code dump + compare artifacts |
| `POST_INCOMPLETE_L_ABSTENTION_EVAL.md` | This report |
