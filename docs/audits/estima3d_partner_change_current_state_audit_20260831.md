# Estima3D — Current-State Audit After Partner's Latest Changes
**Date:** 2026-08-31
**Auditor:** Claude Code (5 parallel read-only investigation forks + coordinator git forensics)
**Scope:** Full verification of partner-reported changes against actual git history, code, tests, datasets, and call paths. No production code, data, or model artifacts were modified. One isolated detached-HEAD worktree was created at `.../scratchpad/partner-estima3d-integration` (origin/estima3d-integration@228062c) purely for read-only inspection; it can be removed with `git worktree remove` when no longer needed.

---

## A. Executive status

The repository is in a **worse fragmentation state than the "work was kept on estima3d-integration" framing suggests**. There are not one but **two actively-diverging branches both named/derived from "estima3d-integration"**:

- **`bassam/estima3d-integration`** (local, `54745c4`, worktree `ai-dynamic-regex-integration`) — Bassam's line, carries the corrected/consolidated human-review UI.
- **`origin/estima3d-integration`** (remote, `228062c`, pushed 2026-08-28 by Hiba Reda) — the partner's actual latest line, carries the candidate-safety hardening, plate-grammar extension, and label-reconstruction dataset/eval work described in the partner's report.

These forked immediately after their one shared commit (`dcdcb9b`, 2026-08-24) and have **never been merged back together**. 107 files differ between their tips (+213,786/−82,078 lines), including both sides independently rewriting the same human-review React components. **This is the single most important finding of this audit** — it means neither branch currently has both feature sets, and the partner's report describes a branch Bassam does not have checked out anywhere locally until this audit fetched it.

Substantively, the partner's engineering claims hold up **better than a skeptical read of the prompt would suggest**: the candidate-generation safety guards are real, tested, and correctly staged; the three literal semantic-eligibility examples in the prompt are already fixed; plate grammar is materially improved (not fully closed); the ranker-isolation boundary genuinely keeps XGB out of production. Where the claims do **not** hold up: the specific 83.1%/86.5% dataset/model artifacts do not exist anywhere accessible (gitignored, never shared/committed), the "68 regression tests" number doesn't match the real count (85 passing tests found, similar in spirit), the "ST.pdf cache missing" claim is contradicted on this machine (it's *Struct.pdf's* cache that's missing everywhere; ST.pdf's cache exists in two worktrees), and the reported real-document "0 regressions" safety counts cannot be reproduced because their source artifact was never shared. A new, previously-unflagged live production bug was also confirmed: cut-length/trailing-annotation suffixes (e.g. `X0'-6"`) defeat the exact-label catalog guard in the live fusion path, letting weighted geometry/graph evidence override explicit printed text — and the fix for this already exists in the codebase, just in a module (`label_reconstruction`) that the live path can't reach.

---

## B. Git / branch / worktree status

| Item | Value |
|---|---|
| Repo root | `C:/Users/Bassam/git/ai-dynamic-regex` (+ 5 additional worktrees, see below) |
| Current branch (main worktree) | `bassam/rnd-geometry-ml-foundations` @ `bb3d67c` |
| Remote | `origin` = `https://github.com/ismail210/ai-dynamic-regex` (a third collaborator's fork used as shared origin — see `docs/audits/ismail_recent_merge_audit.md` for background) |
| Git status (main worktree) | Deleted `backend/database/aisc-shapes-database-v160-2.xlsx`; new untracked CSV, `backend/training/{datasets,models}/`, one new training document, `docs/audits/` — pre-existing local state, not part of the branch fragmentation |

**Worktrees:**

| Path | Branch / ref | HEAD | Role |
|---|---|---|---|
| `ai-dynamic-regex` | `bassam/rnd-geometry-ml-foundations` | `bb3d67c` | Main worktree, ancestor of everything else |
| `ai-dynamic-regex-integration` | `bassam/estima3d-integration` | `54745c4` | **Bassam's** integration line (human-review UI fixes) |
| `.../scratchpad/partner-estima3d-integration` | `origin/estima3d-integration` (detached) | `228062c` | **Newly created this audit**, read-only — Hiba's actual latest line |
| `ai-dynamic-regex-dlp` | `bassam/drawing-language-profile` | `999787d` | Fully merged into both integration lines (no unique commits either direction) |
| `ai-dynamic-regex-accuracy-sprint` | `accuracy-sprint/phase1-correctness` | `5b60a69` | Fully merged into both integration lines |
| `git-backups/ai-dynamic-regex-partner-review` | detached | `e36fb1b` | Old backup, predates the current fragmentation, low relevance |

**Commits added since the last shared point (`dcdcb9b`, 2026-08-24):**

*Bassam's line (`bassam/estima3d-integration`), not in Hiba's line:*
`2d6f1de` → `1bb1753` → `2c343d0` → `e015f8c` → `54745c4` — all human-review/drawing-review sync fixes.

*Hiba's line (`origin/estima3d-integration`), not in Bassam's line:*
`5c61815` (Aug24, "Ship balanced next phase: stricter extraction, review UX, learning loop") → `ae187dd` (Aug26, "Preserve label instances at extraction v3.9") → `cf728a5` (Aug26, "Extend plate grammar for CAP CONN and thickness-first plates") → `ea82a23` (Aug26, "Fix structural reconstruction candidate safety") → `228062c` (Aug28, "Harden label reconstruction ranking safety").

**Subsystem ownership (verified, not assumed):**

| Subsystem | Authoritative location | Fragmentation status |
|---|---|---|
| `structural_parser.py`, candidate generation, XGB ranker | `backend/services/label_reconstruction/{structural_parser,candidates,ranker,shadow}.py` | One module tree — **not** competing old/new systems (see §F). Present, further evolved, on Hiba's line only since `ea82a23`. |
| Plate grammar, HSS completion | `services/annotation/parser.py`, `label_reconstruction/candidates.py` | Extended on Hiba's line (`cf728a5`) only |
| DLP (SOURCE_VERIFIED/PROPOSED_INFERENCE) | `drawing_language_profile.py`, `drawing_language_llm.py` — **exist only in the orphaned `ai-dynamic-regex-dlp` worktree** | Dropped from history at the `999787d` merge point; absent from **both** current integration lines |
| Legend/context reranking (DLP's diluted survivor) | `document_prior.py` | Present, identical, on both integration lines |
| Human review UI/state | `SectionReviewSelector.jsx`, `PredictionDetailModal.jsx`, `SectionResultsList.jsx`, `human_selections.py` | **Actively diverged** — see §L |
| Accuracy-sprint / phase-ab work | Ancestor of both integration lines | Fully merged, no fragmentation |

No old/abandoned branch was found holding functionality absent from both current lines, **except DLP**, which is genuinely at risk of permanent loss (no later commit on any active line references those two files).

---

## C. Production architecture today

Traced against **Hiba's line** (`origin/estima3d-integration@228062c`), cross-checked against Bassam's line where they still share code (they do, for everything upstream of the Aug24 split):

```
PDF
 → extraction_engine.py (group_annotation_fragments → attach_document_prior → filter_engineering_objects)
     filter_engineering_objects = classify_engineering_object() + classify_extraction_noise_reason() + dedupe
     [deterministic; can drop tokens entirely; runs unconditionally, no flag]
 → document["engineering_tokens"]  (only tokens that survive classification + noise filter)
 → staged_pipeline.py → orchestrator.py: predict_from_context()
     - protected_exact_section = catalog_valid_exact_section(normalized_or_raw_text)   [deterministic fast path]
     - apply_prior_to_candidates() ×2 (document_prior legend reranking)                 [deterministic, reranks only]
     - correction_engine.correct(): weighted blend of text / similarity_search /
       geometry / graph / engineering_context / review_history                          [hybrid; CAN override explicit text]
 → apply_label_ranker_for_analyze() (label_ranker_hook.py)                              [ML; gated off by default]
 → protected_exact_section override guard (always wins if set)
 → final result / human review
```

**Feature flags — confirmed by direct code read, not inference:**
- `ML_LABEL_RANKER_ENABLED` = `false` (default, `config.py:187-208`, no env override in `.env.example` or anywhere found)
- `ML_LABEL_RANKER_SHADOW` = `false` (same)
- `label_ranker_hook.py` is the **only** bridge into `services.label_reconstruction`; production modules are forbidden from importing it directly, enforced by a passing source-scan test (`test_label_reconstruction_not_wired_into_production.py`).
- With both flags off, `label_ranker_meta["applied"]` is always `False`; the ranker's `section = ranker_label` assignment in `orchestrator.py` is confirmed dead code in production today.
- `document_prior_enabled` = `true` by default (`config.py:177-181`) — this **is** live in production, but only as a candidate reranker, not an eligibility gate.

**Confirmed: the new XGB ranker does not serve production Analyze.** This matches the partner's claim and the team's stated intent.

---

## D. Previous roadmap scorecard

| Roadmap item | Status | Evidence | Remaining work |
|---|---|---|---|
| 1. Consolidate branches/worktrees | **REGRESSED** | New fragmentation created after the last audit: `bassam/estima3d-integration` vs `origin/estima3d-integration` diverged 2026-08-24, never merged; 107 files differ | Deliberate reconciliation merge (P0, see §O) |
| 2. Fix known deterministic defects (plate grammar) | **PARTIALLY DONE** | `cf728a5` fixed CAP PL/CONN PL/thickness-first/bent-plate (27 tests pass); `BASE PL` still falls through to `TEXT_NOTE`; 3-part flat-plate thickness field bug found | Add BASE PL (+ likely STIFF PL/GUSSET PL) head words; fix thickness field mapping |
| 3. Merge + shadow-test family-aware structural reconstruction | **IMPLEMENTED BUT DISABLED** | `label_reconstruction/` fully built, tested (85 passing tests), isolated via enforced import boundary; flags default false | Decide promotion path; independently, its deterministic field-safety logic should be reachable from the live fusion path even without enabling the ML ranker (§O) |
| 4. Merge + validate DLP without letting it create takeoff truth | **REGRESSED (full DLP) / DONE (constraint trivially held)** | Full DLP (`drawing_language_profile.py`) dropped from history at `999787d`, exists only on orphaned branch; the survivor (legend reranking) never creates takeoff truth by construction (reranking only) | Explicit decision: recover/merge DLP's eligibility concept, or formally retire it |
| 5. Build one regression benchmark | **NOT DONE** | 71 test files exist but are unit/synthetic/token-level; the only two "real-document" scripts either lack ground truth by their own admission (`evaluate_label_ranker_shadow_real_docs.py`) or are extraction-only with no scoring (`validate_st_extraction.py`); neither has a saved/shared completed run | Build the real benchmark (§O, P1) |
| 6. Measure what still fails | **PARTIALLY DONE** | This audit surfaced two confirmed, previously-unmeasured real defects (cut-length exact-guard bypass; angle/L keyword gap) | Needs the real benchmark from item 5 to measure systematically rather than by spot-check |
| 7. Deep research only remaining failures | **PENDING** | Blocked on items 1, 5, 6 | See §P |
| 8. Implement next architectural phase | **NOT STARTED (correctly deferred)** | No evidence of new-phase work; correctly gated on unresolved fragmentation | — |

**Future research questions:**

| Question | Status | Evidence |
|---|---|---|
| Confidence/abstention architecture | **PARTIALLY DONE** | Real, working: `no_candidates` reasons (`ineligible`, `missing_thickness`, `no_valid_candidate`) in `label_reconstruction/candidates.py`; not reachable from live path (see above) |
| Page → region → object hierarchy | **PARTIALLY DONE** | `document_prior` detects legend pages and reranks; does **not** gate object eligibility — falls short of "every page contributes context, only eligible objects become takeoff objects" |
| Detail-reference reasoning (e.g. "14-2" → Table 14-2) | **NOT STARTED as an architecture** | The literal example is currently suppressed, but by incidental keyword/regex matching in the noise filter, not by any table/detail-reference reasoning capability |
| Mixed-page/mixed-region semantics | **NOT STARTED** | No code found addressing this |
| Geometry association | **EXPERIMENTAL / ISOLATED** | `correction_engine.py` has real weighted geometry/graph signals in production, but (per the prior `idea_abc` audit, not contradicted this session) the underlying geometry-flag extraction (`bent`/`l_shaped`/`plate_like`) is not populated from real vector data — not independently re-verified this round, flagged as carried-over |
| When VLM/pixel reasoning adds value | **ALREADY ANSWERED** (prior audit) | Do not re-research per the user's own instruction |

---

## E. Partner-change verification

| Claim | Verified? | Evidence | Caveat |
|---|---|---|---|
| W cannot become WT | **VERIFIED** | `candidates.py`; regression test `test_w_queries_do_not_emit_wt` passes | — |
| HSS without reliable thickness abstains | **VERIFIED** | `is_missing_thickness_hss()` (candidates.py:257), enforced in `shadow.py:137` | — |
| Reliable HSS dimensions protected / mixed wildcard-numeric not "reliable" | **VERIFIED** | `_is_clean_numeric_field()` (candidates.py:153) | — |
| Anonymous/dimension-only strings → `no_candidates`, model never loads | **VERIFIED live** | Ran all 5 reported strings through `reconstruct()`; all returned `no_candidates`/`None`; `get_active_ranker()` confirmed unreached | Eligibility check is **not pure grammar** — it lazily consults upstream `interpret_annotation()` semantic classification for the DIMENSION case specifically |
| Dataset `label_reconstruction_production_aligned_20260828`, model `label_reconstruction_20260828_111425` | **CANNOT VERIFY — artifacts do not exist** anywhere on this machine, in git history (all branches, pickaxe-searched), or on the partner's own pushed branch | `backend/training/{datasets,models}/` is gitignored (`.gitignore:56`); the **generation code is real** (`generate_label_reconstruction_production_aligned.py`, committed) but its output was never shared/committed | Treat 83.1%/86.5% as **self-reported, unreproducible** until the actual output files are shared |
| Metric is synthetic ranking accuracy, not drawing-level accuracy | **CONFIRMED — and self-disclosed** | `evaluate_label_ranker_production_aligned.py:150` literally labels its own metric `"synthetic_ocr_ranking_not_production_accuracy"` | Good practice by the partner, not a strike against them |
| Struct.pdf / Burrville shadow eval, "ST.pdf not reprocessed, cache missing" | **PARTIALLY CONTRADICTED** | On this machine: **Struct.pdf's** cache is missing everywhere; **ST.pdf's** cache (a third, distinct document) exists in two worktrees; Burrville's exists in one | Cache state is per-machine (gitignored) — "missing" was true wherever the partner ran it, not universally; the disagreement examples quoted could not be independently reproduced (no saved run output found anywhere) |
| Shadow eval is genuine end-to-end | **CONTRADICTED — it is ranking-only** | Script's own docstring: *"Uses existing predictions_view.json caches so OCR/fusion/MobileNet/GraphSAGE are not re-run"*; ground truth field literally says `"GT unavailable; TP/FP/FN/TN not measurable"` | Must be reported as re-ranking against frozen cached predictions, not end-to-end |
| Field compatibility gate exists and enforces reliable-field non-contradiction | **VERIFIED** | `candidate_respects_reliable_query_fields()` (candidates.py:234), docstring explicitly cites the `L3X3X3/8X0'-6"` case; wired post-ranking in `shadow.py` | Deterministic top-1 pick is not explicitly re-asserted against this gate the same way the ranker pick is — minor asymmetry, not a known exploit |
| "68 focused regression tests passed" | **PARTIALLY VERIFIED** | Ran the real safety-related test files live: **85 tests / 90 subtests, all passing** | Correct in spirit ("large suite, all green"); the specific number 68 does not match anything found |
| Specific safety counts (0 regressions, 4 field-gate rejections, etc.) | **CANNOT VERIFY** | Producing script (`evaluate_label_ranker_shadow_real_docs.py`) is real and internally consistent with these metric names, but its output (`summary.json`) does not exist in this checkout | Numbers are plausible in shape but unreproducible here |
| Is the field gate duplicating `structural_parser.py`? | **NO — corrected premise** | `structural_parser.py` is a primitive layer *inside* the same `label_reconstruction/` package the field gate lives in (imported directly by `candidates.py`), not a separate/old system | The real duplication is elsewhere — see §F |

---

## F. Reconstruction architecture comparison

**Corrected framing:** it is **not** "production vs. old structural_parser vs. new XGB." `structural_parser.py` is load-bearing infrastructure *underneath* `candidates.py`/`ranker.py`/`shadow.py`, all evolved together in the same commits. This is **one architecture** (`label_reconstruction/`), still evolving, not two competing ones.

| Dimension | Current production (live fusion, no reconstruction) | `label_reconstruction/` (structural_parser + candidates + shadow + ranker) |
|---|---|---|
| Wired into live Analyze | Yes (baseline path) | No — isolated behind `label_ranker_hook`, flags default off |
| Supported families | Catalog/fuzzy exact match only | W/M/S/HP/C/MC/WT/MT/ST, HSS rect+round, L, 2L, PIPE |
| Partial-field handling | None | Full field-by-field parsing + wildcard tolerance |
| Family preservation | Not attempted | Structural-compatibility checks prevent cross-family drift |
| Exact-label protection | **String-exact only — confirmed to fail on trailing cut-length/annotation suffixes** | `reliable_acceptance_parse` explicitly tolerant of trailing cut-length fields — **stronger**, and literally designed around this exact failure case |
| HSS behavior | None | Missing-thickness detection forces abstention |
| Ambiguous/dimension-only tokens | Falls through to weighted fuzzy correction | Explicit semantic-eligibility gate (`ineligible_for_section_reconstruction`, consults `interpret_annotation`) |
| Abstention | None explicit | Explicit `no_candidates` reasons |
| Explainability | Low | Per-candidate `generation_reasons`/`fuzzy_ranks` |
| Production safety today | **Weakest exact-label guard — confirmed live bug (§H)** | Never touches live output while flags are off |

**Where real duplication exists (the "B" answer, but narrower than the prompt assumed):** production's own live fusion path (`orchestrator.py`) reimplements its own weaker "protect the exact label" check instead of reusing `label_reconstruction`'s already-built, stronger version. **`label_reconstruction`'s field-safety logic should become authoritative** for this specific concern — it already demonstrably handles a case production's own guard does not, and doing so does not require enabling the ML ranker at all (only its deterministic primitives need to be reachable).

A second, more urgent duplication is not architectural but literal: **two independently-evolving human-review UI implementations** across the two unmerged branches (§L).

---

## G. P0 semantic-eligibility blocker

**Verdict: PARTIALLY DONE.** The three literal examples in the prompt are already fixed; a different, real gap was found in their place.

- Upstream semantic classification is real and used: `engineering_object_filter.classify_engineering_object()` (called unconditionally from `extraction_engine.py`) plus `services/annotation/parser.interpret_annotation()` classify every token into a structural type, `anonymous_dimension`, or `None` (dropped). The resulting `engineering_object_type` field is written into `document["engineering_tokens"]` and is genuinely read downstream (`orchestrator.py` special-cases `anonymous_dimension`).
- Tokens that fail classification **never enter** `document["engineering_tokens"]` — reconstruction/candidate generation, which operates strictly on that list, never sees them. This is a real filter, not a shadow/logged-only check.
- **Live-executed results for the prompt's three examples:** `"1-1/2\""` near `"NON-SHRINK GROUT"` → dropped; `"14-2\""` near `"SEE TABLE 14-2\""` → dropped; `"1/2\"x5/16\"ANGLE"` → dropped. **All three are already correctly suppressed**, on both branches (the mechanism predates the fork point).
- **New confirmed gap:** the structural-context whitelist that rescues an otherwise-ambiguous dimension (`_STRUCTURAL_NEARBY_RE` in `extraction_noise_filter.py`) does **not** contain `ANGLE` or `L`. Live-executed: `"2X4X1/4"` next to `'2"X4"X1/4" ANGLE'` → classified `anonymous_dimension`, then discarded as `weak_anonymous` — a genuinely damaged/OCR-fragmented angle label, sitting right next to the word "ANGLE," is silently dropped, because the whitelist doesn't recognize that word. `"3X4X6"` next to `"3X4X6 ANGLE BRACE"` survives only because "BRACE" happens to also be present.
- No regression test currently pins either the three original examples or this new angle counterexample.

**Answers to the required 7 questions are embedded above; summary: (1) real upstream classification exists; (2) `engineering_object_type` field; (3) dropped only for tokens that fail classification (by design, not a bug, for the three named cases); (4) reconstruction does not receive dropped tokens at all (they never exist downstream); (5) `filter_engineering_objects()` in `extraction_engine.py` is already the right boundary — no new boundary needed; (6) yes, confirmed — the angle/L whitelist gap; (7) tests pinning the three named examples as literal-string regressions, plus a new test asserting angle/L family words belong in the structural-context whitelist.**

---

## H. Fusion/correction findings

- Fusion lives in `correction_engine.MultimodalCorrectionEngine.correct()` — a **weighted blend of six signals** (text, similarity_search, geometry, graph, engineering_context, review_history). Text is one vote among six, not authoritative by construction.
- **Root cause of the reported `L3X3X3/8X0'-6"` → `L3X3X1/2` corruption — confirmed live, not inferred:**

```
RAW TEXT: L3X3X3/8X0'-6"
 → normalized text unchanged (cut-length suffix still attached)
 → catalog_valid_exact_section("L3X3X3/8X0'-6\"") → None   [confirmed by direct execution]
 → catalog_valid_exact_section("L3X3X3/8") (suffix stripped) → 'L3X3X3/8'   [would have worked]
 → PROTECTED EXACT LABEL fast path does NOT fire (guard failed on the untrimmed string)
 → falls through to correction_engine.correct(): six-signal weighted score
 → if geometry/graph/review_history evidence outweighs the text signal, a different
   real AISC row (e.g. L3X3X1/2) can be selected
 → FINAL OUTPUT: printed thickness silently overridden
```
  Root cause is **confirmed**; the literal end-to-end output value is **plausible, not reproduced** (would need live geometry/graph payloads from a real document).
- **The fix already exists in the codebase** — `label_reconstruction/candidates.py`'s `reliable_acceptance_parse()` was specifically written to handle this exact cut-length case (its own docstring cites it) — but it is unreachable from the live path because `label_reconstruction` is only reachable via `label_ranker_hook`, a no-op with both flags off.
- Family compatibility (`plausible_against_ocr`) is enforced only inside the narrow "exact-candidates top-1 override" branch, **not** inside `correction_engine.correct()`'s general scoring — cross-family drift is possible through the general path even when the narrower guard would have caught it.

---

## I. Plate grammar status

**Classification: PARTIAL** (materially improved from the last audit's "STILL OPEN P0").

| Pattern | Result |
|---|---|
| `PL 3/8`, `3/8 PL`, `3/8" PL` | OK — flat_plate, confirmed |
| `3/8" BENT PL`, `BENT PL 3/8` | OK — bent_plate, confirmed |
| `CAP PL`, `CONN PL` | OK — **new in `cf728a5`** |
| `PL 3/8 X 6` | OK — candidate created |
| `PL 3/8 X 6 X 10` | Classifies correctly, **but `thickness` field is wrongly set to "10" (length) instead of "3/8"** — field-mapping bug |
| `BP` | OK — bent_plate, confirmed even bare |
| `BASE PL` | **FAILS — falls through to `TEXT_NOTE`, not recognized as a plate at all** |

27 tests pass for what's covered. `BASE PL` (and likely `STIFF PL`/`GUSSET PL` per the prior audit's list) were never added despite `CAP PL`/`CONN PL` being fixed in the same commit — the fix was half-completed.

---

## J. DLP / context status

- Full DLP (`drawing_language_profile.py`, `drawing_language_llm.py`, `SOURCE_VERIFIED`/`PROPOSED_INFERENCE`) exists **only** in the orphaned `ai-dynamic-regex-dlp` worktree. It is a confirmed ancestor of both integration lines but was **dropped from history at the `999787d` merge** — neither current line references it, no tests for it exist on either line.
- What survived: `document_prior.py`'s legend-page detection, identical on both lines, **live in production by default** (`document_prior_enabled=true`), called twice in `orchestrator.py` to rerank candidates.
- This is reranking, **not** eligibility gating — it does not decide whether a page/region/object may produce a takeoff object at all. The architecture remains short of "every page contributes context, only eligible objects become takeoff truth."
- Classification: **full DLP = EXPERIMENTAL/ISOLATED, at real risk of loss**; **legend-reranking survivor = IMPLEMENTED, live, but scope-limited**.

---

## K. Extraction / filtering status

- Real, verified gate: `extraction_engine.py` → `filter_engineering_objects()` (classification + noise-reason veto + dedup), producing both `engineering_tokens` (survivors) and `extraction_discard_counts` (aggregate reason counts: `layout_dims`, `title_block`, `standalone_refs`, `weak_anonymous`, `duplicates`).
- This **closes the prior audit's P1 finding** ("silent deletion, no discard reason") — reasons are now counted, though only in aggregate, not per-token (a reviewer can't see *which* token was dropped for *which* reason, only totals).
- No duplication found between this filter and later reconstruction eligibility — single-gate design, reconstruction operates strictly downstream on the survivor list.
- Confirmed false-negative risk: the angle/L whitelist gap from §G is a real, reproducible instance of this filter silently dropping genuine damaged steel labels.

---

## L. Human-review status

**This is the sharpest concrete consequence of the branch fragmentation.**

| | Bassam's line (`bassam/estima3d-integration`) | Hiba's line (`origin/estima3d-integration`) |
|---|---|---|
| Candidate picker | Single shared `SectionReviewSelector.jsx` (261 lines), used by both Results and Drawing Review | **Does not exist.** `PredictionDetailModal.jsx` (390 lines) still has the pre-refactor duplicates (`applyLocalSelection`, `CandidateSectionPicker`, `SemanticCandidatePicker`) that Bassam's line explicitly removed |
| Sync regression coverage | `HumanReviewSync.test.jsx` (329 lines) exists | **Does not exist at all** |
| Shared overlay function | `human_selections.apply_human_selection_overlay(..., semantic_type=...)`, used by both the corrections router and `staged_pipeline` | No such function; `staged_pipeline.py` sets fields inline; corrections router has no overlay call |
| Test execution | **Ran live: 33/33 frontend tests passed** | Not executable (no `node_modules`); static evidence (missing test file) already establishes the coverage gap |

**Bassam's line has the more correct/complete human-review implementation; Hiba's line has the newer backend safety/plate-grammar work but a regressed, duplicated review UI relative to what Bassam already fixed on 2026-08-24.** Merging today will conflict on all of the files above, and naively taking either side wholesale will either reintroduce the duplicate-picker architecture (if Hiba's side wins) or lose the backend safety work (if Bassam's side wins as-is).

Human-reviewed-value precedence over automated reconstruction was **not fully re-verified pixel-for-pixel** in this pass (out of the assigned fork's time budget) — the picker-architecture and overlay-precedence findings above are the load-bearing results.

---

## M. Benchmark / ground-truth status

- 71 test files exist; the plate/HSS/reconstruction/eligibility ones are real and passing, but all are unit/synthetic/token-level.
- The only two "real-document" scripts: `evaluate_label_ranker_shadow_real_docs.py` (re-ranking against **frozen cached predictions only** — OCR/fusion/geometry/graph are not re-run, and it self-reports `"GT unavailable"`) and `validate_st_extraction.py` (extraction-only, no scoring against truth).
- **No genuine project-level benchmark exists that can answer "did the new architecture improve actual steel-takeoff interpretation."** This confirms the user's suspicion.
- Real ground truth (the ~12 disagreement patterns): **not started.** No file matching this exists anywhere. The team's own `docs/ml_association_phase/human_review_status.md` already documents a standing policy against fabricating ground truth — consistent with this audit's constraint.
- Cheapest real next step: a real ST.pdf cache already exists on this machine (two worktrees); Struct.pdf's cache is missing everywhere and would need regeneration first; Burrville's cache exists in one worktree. Run the real shadow-eval script against what's available, then have a human adjudicate a small sample — do not invent labels.

---

## N. Remaining failure taxonomy

| Category | Confirmed failure |
|---|---|
| Extraction / semantic eligibility | Angle/L keyword gap in structural-context whitelist can silently drop genuine damaged angle labels |
| Parsing (plate grammar) | `BASE PL` unrecognized; thickness field mis-mapped for 3-part flat plates |
| Fusion/correction | Cut-length/trailing-annotation suffixes defeat the exact-label catalog guard, allowing weighted evidence to override explicit printed text |
| Review/persistence | Two unreconciled human-review UI implementations, one missing sync regression coverage entirely |
| Evaluation/data | No real end-to-end benchmark; no shared/reproducible model-eval artifacts; no real ground truth set |
| Page/region context | Legend detection reranks only, does not gate eligibility — architecture gap remains vs. the desired design |
| Candidate generation / ranking | No confirmed failures this round — this layer is in the best-verified state of anything audited |
| Geometry association | Not independently re-verified this round; carried-over concern (real geometry-flag extraction likely still absent) |

---

## O. Updated prioritized roadmap

### P0 — blocks safe progress

**1. Reconcile the two diverged "estima3d-integration" lines.**
- Files: `frontend/src/components/{SectionReviewSelector,PredictionDetailModal,SectionResultsList}.jsx`, `frontend/src/pages/DrawingReviewPage.jsx`, `backend/services/human_selections.py`, `backend/services/label_reconstruction/*`.
- Action: deliberate hand-merge — keep Bassam's single-picker UI + shared overlay architecture, re-port Hiba's backend candidate-safety/plate-grammar/dataset work onto it (re-adding `semantic_type` support to whatever review path Hiba's backend changes assume).
- Validation: both existing test suites (33 frontend + 85 backend) plus a manual Results↔Drawing-Review sync smoke test.
- Expected benefit: removes the single largest active risk — two people currently building on incompatible assumptions.
- Regression risk: medium — real logic conflicts, not a mechanical git merge.

**2. Fix the confirmed live exact-label-protection bug.**
- Files: `backend/services/prediction/orchestrator.py` (`catalog_valid_exact_section` usage), `backend/services/label_reconstruction/candidates.py` (`reliable_acceptance_parse`).
- Action: strip/normalize trailing cut-length and annotation fragments before the catalog-exact check, or make the live path call `reliable_acceptance_parse`'s logic directly (deterministic only — does not require enabling the ML ranker).
- Validation: new regression tests with cut-length suffixes across L/W/C/HSS families; existing `correction_engine` tests must still pass.
- Expected benefit: fixes a confirmed, currently-live accuracy bug — the highest-confidence concrete fix in this entire audit.
- Regression risk: low-medium.

**3. Close the angle/L keyword gap in extraction noise filtering.**
- Files: `backend/services/engineering/extraction_noise_filter.py` (`_STRUCTURAL_NEARBY_RE`, `_DETAIL_CONTEXT_RE`).
- Action: add ANGLE/L and other missing family role words to the structural-context whitelist.
- Validation: new tests with angle-only context; paired precision test to confirm this doesn't over-rescue truly-anonymous dimensions.
- Expected benefit: prevents silent loss of real damaged steel labels — the actual failure mode the original P0 blocker was worried about.
- Regression risk: low (additive), but needs a precision check.

### P1 — high-value next

**4. Wire `label_reconstruction`'s deterministic field-safety primitives into the live fusion path, independent of the ML ranker promotion decision.** This both fixes item 2 more durably and resolves the architectural duplication in §F/§H.

**5. Build the real regression benchmark.** Regenerate Struct.pdf's cache, use the existing ST.pdf/Burrville caches, run the real (not synthetic) shadow-eval end-to-end where possible, and commit/share its output so numbers are reproducible by anyone.

**6. Create the small, real, manually-verified ground-truth set** (12 patterns as originally proposed) — do not fabricate; use the caches that already exist.

**7. Make model/dataset evaluation artifacts shareable.** Commit or otherwise share `manifest.json`/`evaluation_*.json` outputs from `generate_label_reconstruction_production_aligned.py` and `evaluate_label_ranker_shadow_real_docs.py` so claims like "83.1%/86.5%" and "0 regressions" are independently checkable in the future.

### P2 — useful but not blocking

**8. Finish plate grammar:** add `BASE PL` (and likely `STIFF PL`/`GUSSET PL`), fix the 3-part flat-plate thickness-field mapping bug.

**9. Decide DLP's fate explicitly:** either merge its eligibility-gating concept (not full LLM-driven takeoff truth — already correctly ruled out) into one of the reconciled lines, or formally archive/retire the orphaned branch so it stops being an at-risk loose end.

**10. Add per-token discard logging** (not just aggregate counts) to `extraction_noise_filter` for auditability.

### P3 — later / research

**11. Mixed-page/mixed-region semantics, detail-reference reasoning as a real capability, page→region→object eligibility hierarchy** (beyond today's legend-reranking-only implementation).

**12. Real geometry-flag extraction** (`bent`/`l_shaped`/`plate_like`) from vector path data — prerequisite for geometry association to mean anything beyond a permanently-inert weighted signal.

---

## P. Research vs. engineering decision

**Not ready for another deep-research phase.** Every concrete finding in this audit is an internal engineering or measurement task with a clear owner and file location: branch reconciliation, a confirmed code bug with a known fix already present in the codebase, a whitelist gap, and a missing shared-evaluation-artifact process. None of these require external research to resolve.

The **one legitimate carried-over research question** (not re-litigated, not previously answered): is there a cheap, deterministic **vector-geometry heuristic** (closed polylines, direction changes, aspect ratio — not a trained model) that could populate the `bent`/`l_shaped`/`plate_like` flags that `correction_engine`'s geometry signal already expects but currently never receives real data for? This remains open and is worth a scoped research pass **after** the P0/P1 engineering items above, since geometry association can't matter until this exists regardless of what else changes.

---

## Q. Bottom line

1. **Genuinely solved:** candidate-generation safety guards (W→WT, HSS abstention, reliable-field protection) are real, tested, correctly staged; anonymous-dimension rejection genuinely short-circuits before the model loads; ranker isolation is enforced by a passing test; the three literal semantic-eligibility examples from the prompt are already fixed.
2. **Partially solved:** plate grammar (bulk fixed, `BASE PL` + a field-mapping bug remain); semantic eligibility (closes note/table/material-text cases, but has an angle-vocabulary blind spot); DLP (diluted legend-reranking survives, full context architecture doesn't reach eligibility gating).
3. **Duplicated:** not structural_parser vs. XGB (one tree) — it's production's live fusion guard vs. `label_reconstruction`'s stronger guard, and, more urgently, two independently-evolving human-review UI implementations across the unmerged branches.
4. **Disabled:** `ML_LABEL_RANKER_ENABLED`/`SHADOW` both false, confirmed no override; `label_reconstruction` fully isolated from production by an enforced test; full DLP isolated on an orphaned, unreferenced branch.
5. **Still unsafe:** a confirmed live bug where cut-length/annotation suffixes defeat exact-label protection and let weighted evidence override printed text; the angle/L whitelist gap that can silently drop real damaged labels; neither integration branch alone has both the newer backend safety work and the correct review UI.
6. **Biggest accuracy problem:** there is no real end-to-end benchmark, so actual drawing-level accuracy is genuinely unmeasured — the one confirmed concrete defect is the cut-length exact-protection bug.
7. **Biggest production-safety problem:** the unreconciled branch divergence itself — every day of continued independent work increases the chance of silently losing already-fixed work on one side or the other.
8. **Implement next:** reconcile the two branches; fix the cut-length exact-label bug by reusing `label_reconstruction`'s existing logic; close the angle/L keyword gap.
9. **Don't work on yet:** don't enable the ML ranker; don't rebuild DLP/page-role classification from scratch (a working prototype already exists, just orphaned); don't invest further in geometry-scoring rules until real geometry-flag extraction exists; don't start mixed-region/page-hierarchy work.
10. **Ready for deeper research?** No — everything found is internal engineering/process work with a clear fix already scoped; only one narrow, previously-identified research question (vector-geometry heuristics for shape flags) remains legitimately open, and it can wait until after the P0/P1 items above.
