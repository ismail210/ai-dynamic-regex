# Final Accuracy Gap Audit

**Date:** 2026-09-10  
**Scope:** Investigation only — no production changes, no training, no Graph/VLM enablement.  
**Primary artifact:** 8-document cached `predictions_view.json` under `backend/training/eval_cache_backups/doc_*/`  
**Gold methodology:** printed core after shop/cut stripping (`proxy_gold_section`); incomplete L/2L → no gold / abstain is correct.

---

## 1. Executive Conclusion

### Already solved (or deliberately closed)

| Area | Status |
|---|---|
| XGB / ML label ranker | **Do not retrain / do not enable** — not the ROI path |
| Graph v2 candidate scoring | **DO NOT ENABLE** — 0 ungated ranking changes; worse than text on multi-family family argmax |
| Leader→target as ranking signal | **STOP** — 0.7% reliable (A); HSS→W lean risk |
| GraphSAGE / learned fusion / geometry missing-label inference | Remain **OFF** |
| Explicit catalog exact-label protection (incl. shop/cut strip) | **Shipped in current code + unit tests** (`catalog_valid_exact_section`, `core_section_token`) — see §8 |

### What remains (measured on cached live predictions)

On **9,396** prediction rows / **7,198** with proxy gold:

- Overall proxy-gold accuracy (with HSS decimal equivalence): **7,088 / 7,198 = 98.47%**
- Remaining wrong rows (taxonomy): **126** (denominator = wrong classifiable rows, not all tokens)
- Dominant remaining error mass is **L-family**: thickness overwrite, incomplete completion, size/leg, L→2L
- **HSS→W:** 10 / 869 HSS-gold rows (1.15%), all with printed HSS already in text/alts

### Critical cache caveat

`predictions_view.json` files are dated **2026-08-31**. Shop/cut exact-section protection was strengthened afterward (e.g. `29bdc6a`, shop-cut unit tests). Therefore:

- Many **shop-cut L thickness** failures in this cache are **likely already fixed in current code** (unit tests assert `'L4x3x1/4x6"'` stays `L4X3X1/4` against a fusion decoy).
- This audit treats cache as the **latest full multi-doc prediction snapshot**, not as proof that live still fails those protected cases.
- Gaps that are **not** clearly covered by shipped protection tests are prioritized higher.

### Not recoverable from current evidence

~**2,182** rows have **no proxy gold** (non-section / unlabeled / non-recoverable text). Geometry/graph/VLM must **not** be used to invent sections for these.

### Single best next fix

**Deterministic incomplete L/2L abstention in the production prediction path** when the printed core is legs-only (e.g. `L4x4`, `2L4x4`, `L5x3`):

- Force review/abstain — **never** emit `L4X4X1/4`, `L4X3X1/4`, or `2L4X4X1/4`.
- Evidence already present in the PDF text; no ML/Graph/VLM.
- Cache shows **16** unsafe completions; current orchestrator has HSS missing-thickness review but **no equivalent incomplete-angle abstain gate** (unlike offline Graph v2 gates).
- Small, testable, production-safe.

Do **not** implement that fix in this task — implement in a follow-up after review.

---

## 2. Current Baseline

### Artifact authority (explicitly separated)

| Layer | What it is | Used how |
|---|---|---|
| **Cached evaluation behavior** | `eval_cache_backups/doc_*/predictions_view.json` (8 docs, 2026-08-31) | Primary quantitative baseline for live `section` field |
| **Offline experiment behavior** | Graph v2 Phase 5 / leader-target investigation | Confirms Graph/leader are **not** next levers |
| **Production code behavior** | Current `orchestrator` + `catalog_valid_exact_section` + unit tests | Used for regression/protection status; **not** re-inferred by reprocessing PDFs |

### Documents evaluated (cache)

8 documents, **9,396** prediction rows total.

| Metric | Count | Denominator / note |
|---|---:|---|
| Total prediction rows | 9,396 | all cached predictions |
| Rows with proxy gold | 7,198 | printed complete core recoverable |
| Correct (equiv-normalized) | 7,088 | / 7,198 gold = **98.47%** |
| Explicit complete sections | 7,198 | proxy-gold methodology |
| Incomplete L/2L (legs only) | 16 | no gold; abstain = correct |
| No recoverable gold | 2,182 | unlabeled / non-section text |

### Family breakdown (by proxy gold or status)

| Family / status | Count | % of 9,396 |
|---|---:|---:|
| W | 6,000 | 63.9% |
| NO_GOLD | 2,182 | 23.2% |
| HSS | 869 | 9.2% |
| L | 232 | 2.5% |
| C | 56 | 0.6% |
| WT | 26 | 0.3% |
| INCOMPLETE | 16 | 0.2% |
| 2L | 15 | 0.2% |

### Cross-check vs Graph v2 Phase 5 text baseline (variant A)

Phase 5 scored **7,314** rows with candidate pools (subset filter), gold accuracy A = **7,038 / 7,193 = 97.85%** (stricter string match, no HSS decimal equivalence). Same cache family; different row filter / equivalence — **not directly comparable** without labels. Both agree: overall high; residual errors concentrate in L + rare HSS→W.

---

## 3. Remaining Error Taxonomy

Denominator for % below = **126** wrong classifiable rows (not 9,396).  
Correct / no-gold / successful incomplete abstain are excluded.

| Code | Category | Count | % of 126 | Representative examples | Root cause (cache) | Safely fixable from existing evidence? |
|---|---|---:|---:|---|---|---|
| **F** | Wrong L thickness | 49 | 38.9% | `L4x3x1/4x6"` → `L4X3X5/16` (gold `L4X3X1/4`, gold in alts) | Fusion/candidate chose alternate thickness despite printed thickness | **Yes** (printed thickness). *Likely mitigated by current shop-cut protection — refresh cache to confirm* |
| **C** | Incomplete incorrectly completed | 16 | 12.7% | `L4x4` → `L4X3X1/4`; `2L4x4` → `2L4X4X1/4`; `L5x3` → `C15X33.9` | Catalog completion / wrong family guess | **Yes — abstain** |
| **B** | Explicit shop/cut incorrectly changed | 13 | 10.3% | shop/cut HSS/L variants with length marks | Parser/protection miss or stale cache | Mostly yes if catalog core valid |
| **A** | Explicit printed incorrectly changed | 12 | 9.5% | residual explicit mismatches after equiv | Same-family size / rare norm | Case-by-case |
| **E** | Wrong L size/leg | 12 | 9.5% | `L4X3-1/2X5/16` → `L4X3X5/16`; `L6x4x5/16x4"` → `L4X4X3/8` | Leg parse / candidate swap | **Yes** when printed legs clear |
| **D** | L → 2L | 10 | 7.9% | `L3X3X3/8X0'-6"` → `2L3X3X3/8X3/4` | 2L promotion without printed `2L` | **Yes — forbid 2L unless printed** |
| **G** | HSS → W | 10 | 7.9% | `HSS10X0.625` → `W10X54` (HSS still in alts) | Family confusion in ranking/candidates | **Yes — family lock on printed HSS** |
| **I** | Other family confusion | 4 | 3.2% | rare non-HSS family swaps | Mixed | Sometimes |
| **H** | W → HSS | 0 | 0% | — | — | — |
| **J** | Correct section, wrong eligibility | 0 measured | 0% | incomplete completions were not takeoff_eligible=true in this scan | — | — |
| **K** | Missing / no textual evidence | excluded from 126 | — | 2,182 NO_GOLD | No printed section | **No** — do not invent |
| **L** | Geometry/graph-related | not primary | — | Graph contrib often 0 on HSS→W rows | Graph not the driver of residual HSS→W in cache | Do not enable Graph |
| **M** | Other | folded into A/B/same-family | — | W size, HSS size residuals | Mixed | Mixed |

### Error counts (refined, after HSS decimal / punctuation equivalence)

| Error | Count |
|---|---:|
| L_thickness_error | 49 |
| incomplete_L_completion | 16 |
| L_size_leg_error | 12 |
| L_to_2L | 10 |
| HSS_to_W | 10 |
| W_size_error | 8 |
| same_family_other | 8 |
| abstain_with_gold | 5 |
| other_family_confusion | 4 |
| HSS_size_error | 3 |
| L_same_family_other | 1 |

---

## 4. Fixable vs Unrecoverable

### GROUP 1 — Fixable from existing PDF evidence

**124** rows (of remaining wrongs), by cache measurement:

| Error | Count | Why fixable |
|---|---:|---|
| L thickness (printed matches gold) | 47 | Thickness already in callout |
| Incomplete completion | 16 | Text proves incompleteness → abstain |
| L size/leg | 12 | Legs printed |
| L→2L | 10 | Text is single-L, not 2L |
| HSS→W | 10 | `HSS…` printed; HSS in alternatives |
| W size (gold in alts) | 8 | Alternate contains printed size |
| same_family_other / abstain / HSS size / other | 21 | Mostly text-grounded |

### GROUP 2 — Not recoverable from current evidence

| Bucket | Count | Note |
|---|---:|---|
| NO_GOLD rows | 2,182 | No reliable printed section — **do not use ML/Graph/VLM to invent** |
| Ambiguous L thickness (printed≠normalized gold) | 2 | Weak gold parse |

**Do not propose Graph v2, GraphSAGE, XGB, or VLM to solve Group 2.**

---

## 5. ROI Ranking

| Priority | Error | Count (cache) | Impact | Root cause | Safe fix possible? | Recommended action |
|---:|---|---:|---|---|---|---|
| 1 | Incomplete L/2L completion | 16 | **Safety** — invents thickness/family | Completion without thickness evidence; no live incomplete-angle abstain gate found | **Yes** | **NEXT FIX:** deterministic abstain/review |
| 2 | L→2L without printed 2L | 10 | **Safety** — doubles angle qty risk | 2L candidates win on shop-cut singles | **Yes** | Deterministic: require explicit 2L/DL evidence |
| 3 | HSS→W on explicit HSS | 10 | **Safety** — wrong family | Ranking/candidates prefer W despite printed HSS | **Yes** | Family lock when `catalog_valid` / printed family is HSS |
| 4 | L thickness overwrite (shop/cut) | 49 | High frequency | Historical fusion override | Yes in principle | **First refresh cache**; current unit tests already cover shop-cut keep |
| 5 | L size/leg overwrite | 12 | Engineering | Leg parse / candidate swap | Yes | After incomplete + family locks |
| 6 | Residual W/HSS size | ~11 | Lower | Mixed / OCR | Sometimes | Case-by-case |
| 7 | Unlabeled members | 2,182 | Coverage illusion | No text | **No** | Leave as review / unknown |

### TOP 3 remaining issues

1. **Incomplete L/2L still completed** (safety; likely still live)
2. **L→2L promotion without printed 2L** (safety)
3. **Explicit HSS→W** (safety; verify after cache refresh whether protection already blocks)

### Single best next fix

**Incomplete-angle abstention in production prediction** when `core_section_token` matches incomplete L/2L (two numeric legs, no thickness):

1. Do not select any completed AISC L/2L (or other family) candidate.
2. Emit empty / review / `incomplete_label` semantics consistent with the canonical contract.
3. Unit tests: `L4x4`, `L5x3`, `2L4x4` must not become `L4X4X1/4`, `L4X3X1/4`, `2L4X4X1/4`, or `C…`.

---

## 6. L Family Audit

| Slice | Count | Current cache behavior | Current protection (code) | Remaining failure mode | Safe fix |
|---|---:|---|---|---|---|
| Complete explicit L | 232 gold | 157 correct (67.7%) | Catalog exact + shop-cut strip (tested) | Thickness/leg/2L overrides in **Aug 31 cache** | Prefer protect printed core; refresh cache |
| Complete L + shop/cut suffix | majority of thickness errs (46 shop thickness) | Often wrong thickness in cache | **Unit-tested:** `'L4x3x1/4x6"'` → `L4X3X1/4` vs decoy | Cache may be stale | Verify live; don’t re-implement blindly |
| Incomplete L | 16 | **16/16 completed** (unsafe) | `catalog_valid_exact_section("L4x4")` → `None`; **no orchestrator abstain gate found** | Completion still occurs in cache | **Abstain (recommended next fix)** |
| L → 2L | 10 | Single-L shop-cut → 2L | Exact protect should keep single L if applied | Promotion path still visible in cache | Require explicit 2L token |
| Wrong L thickness | 49 | Printed `1/4` → pred `5/16` etc. | Shop-cut protect in current code | Cache stale vs code | Refresh; then residual only |
| Wrong L dimensions | 12 | Legs mangled (`3-1/2`→`3`, `6x4`→`4x4`) | Partial | Parser / candidate | Deterministic leg lock |
| Unlabeled L | in NO_GOLD | N/A | N/A | No text | Do not invent |

### Explicit verifications (cache)

| Check | Result |
|---|---|
| `L4x4` → `L4X4X1/4` (or similar completion) | **Occurs** (multiple rows) — **must not** |
| `L4x4` → `2L…` | Not the dominant mode; `2L4x4` → `2L4X4X1/4` **does** occur |
| Valid explicit shop/cut L protected | **Intended in current code/tests**; **not** reflected in Aug 31 cache predictions |

---

## 7. HSS → W Audit

| Metric | Value | Denominator |
|---|---:|---|
| HSS gold rows | 869 | proxy gold family HSS |
| HSS → W | 10 | / 869 = **1.15%** |
| W → HSS | 0 | — |

### Source attribution (evidence-based)

| Hypothesis | Supported? | Evidence |
|---|---|---|
| Text/parser missing HSS | **No** | Raw text is `HSS10X0.625` / `HSS10X0.500` / `HSS18X…`; `printed_matches_gold=True` |
| Candidate generation lacks HSS | **No** | Candidate families include **HSS and W**; gold in alts |
| Deterministic scoring / fusion | **Yes (primary)** | Live section becomes W despite HSS in pool |
| Geometry | Weak | Some rows geo≈0; not required for the swap |
| Graph | Weak | Most HSS→W rows `graph` contrib 0; one row 0.14 — not systematic |
| Stale-cache artifact | **Possible** | Cache 2026-08-31; exact-label protection later; `catalog_valid` maps `HSS10X0.625` → catalog form in unit tests |

**Conclusion:** HSS→W here is **not** a Graph-v2 effect (Graph v2 ungated never changed ranking). Prefer **deterministic family lock** on explicit printed HSS over any model. Re-measure after cache refresh before large work.

---

## 8. Regression Check

**No code was changed for this audit.** Findings are measurement + code inspection only.

| Area | Evidence | Regression? |
|---|---|---|
| Explicit section protection | Unit tests + orchestrator `protected_exact_section` | **Not measured as regressed**; cache predates some locks |
| Shop/cut handling | Tests for `L4x3x1/4x6"`, HSS with cut length | **Intended fixed**; cache still wrong → **stale cache**, not proof of live regression |
| Incomplete L abstention | Cache completes 16/16; no orchestrator incomplete-angle gate found | **Gap remains** (not a regression of a shipped incomplete-L gate) |
| Bent plate / PL/BP | Not singled out as residual mass in taxonomy | No measured regression in this pass |
| Takeoff eligibility | Incomplete completions not marked takeoff_eligible=true in scan | No measured eligibility explosion |
| Canonical contract | Incomplete should map to incomplete/review semantics | Align next fix with contract |
| Document prior | Not implicated in top residuals | No measured regression |

---

## 9. Recommended Next Fix

### Do this next (separate implementation task)

**Production incomplete L/2L abstain gate**

- **When:** printed core is incomplete angle (`L`/`2L` + two legs, no thickness).
- **Then:** do not accept completed catalog candidates; abstain / mark incomplete for review.
- **Tests:** `L4x4`, `L5x3`, `2L4x4` never become thickness-complete or wrong-family sections.
- **Out of scope for that fix:** Graph, XGB, VLM, Excel, thickness invention.

### Immediately after (verification, not a feature)

Refresh the 8-doc `predictions_view` cache under current code and re-count L thickness / L→2L / HSS→W. If shop-cut protection already cleared thickness, prioritize **anti-L→2L** and **HSS family lock** next.

---

## 10. What We Should NOT Work On Next

- Retrain or enable XGB / ML label ranker  
- Enable Graph v2, GraphSAGE, learned fusion, geometry missing-label inference  
- Leader-target family scoring for production ranking  
- VLM / API calls to invent missing sections  
- Excel as a section predictor  
- Solving the 2,182 unlabeled / NO_GOLD rows with models  
- Re-implementing shop-cut L thickness protection without first proving live still fails (unit tests already cover the main pattern)

---

## 11. Evidence / Cache Sources

| Source | Path / note |
|---|---|
| Prediction cache (baseline) | `backend/training/eval_cache_backups/doc_*/predictions_view.json` (8 docs, **2026-08-31**) |
| Graph v2 Phase 5 | `backend/GRAPH_V2_PHASE5_REPORT.md`, `eval_cache_backups/graph_v2_phase5/` |
| Leader-target investigation | `backend/GRAPH_LEADER_TARGET_INVESTIGATION.md` |
| This audit machine summary | `backend/training/eval_cache_backups/final_accuracy_gap_audit/refined_summary.json` |
| This audit error rows | `…/final_accuracy_gap_audit/refined_errors.jsonl` (**temporary analysis artifact — do not commit unless requested**) |
| Protection tests | `backend/tests/test_protected_exact_label.py` (shop-cut L/HSS; incomplete `L4x4` → None) |

### Metric honesty notes

- Accuracy **98.47%** uses denominator **7,198 gold rows** and HSS decimal equivalence.  
- Taxonomy % uses denominator **126 wrong rows**.  
- Phase 5 gated C/D accuracy lifts were **explicit-protect artifacts**, not Graph signal — not reused as “Graph helped.”  
- Cache vs current-code protection are **labeled separately**; do not claim live still fails shop-cut L thickness without a fresh prediction dump.

---

_End of audit. No production flags changed. No commit._
