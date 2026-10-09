# Integration audit — Bassam (origin/main) × Hiba (drawing-intelligence-plan-detail)

Date: 2026-10-09 · Stage 1 audit, followed by the approved Stage 2 integration (see the end).
Repository: the shared repository (common git dir) · remote `origin` =
`https://github.com/ismail210/ai-dynamic-regex.git` · fetched without prune at the start of the audit.

**Short answer.** Since the two lines last met, your work and Hiba's barely overlap.

- **Hiba's new work** is one feature commit, `feee364`. It makes Drawing Summary
  references and Locate more conservative and more informative.
- **Your new work** is Docker packaging, the bounded Locate cache and the shipped-asset updater.
- **Duplicate merge.** Both of you independently made the same merge of `dcca690` with `68bb739`
  (`233cf30` on your side, `3db0eb7` on hers). It is the source of every textual conflict:
  - The two merge results differ in **5 files**, and only in cosmetic ordering and cache-version
    *names*.
  - The one real decision is which cache-version string wins.
- **One shared file.** The only code both sides changed is `column_trace.py`. Git merges it cleanly,
  and the combined behavior was verified by tests and in the browser.
- **Protected areas untouched.** Neither side's unique work touches prediction, semantic locking, HSS,
  schedule quantities, corrections, exports or validation.

---

## A. Repository state

| Ref | SHA | Relationship |
|---|---|---|
| `origin/main` (= `origin/HEAD`, `origin/integrate/summary-main`, local `integrate/summary-main`) | `d9a3ea6` | Integration target. Live remote head confirmed with `git ls-remote`. |
| Local `main` (HEAD of this worktree `ai-dynamic-regex-integration`) | `e32cc5b` | 0 ahead / **12 behind** `origin/main`, so a fast-forward is possible. The working tree is dirty (see below). |
| **Partner tip** `origin/drawing-intelligence-plan-detail` (Hiba Reda) | `feee364` | **2 ahead / 7 behind** `origin/main`. It is the only remote branch with work not on main. |
| Merge base (partner tip, `origin/main`) | `dcca690` | Tip of your `bassam/drawing-summary-osse`. |
| Shared parent of both duplicate merges | `68bb739` (Hiba, sheet intelligence + confirmed grid, on top of `56a0bbc`) | Already on `origin/main` through `233cf30`. |
| Partner merge `3db0eb7` (parents `68bb739`, `dcca690`) | `3db0eb7` | **Equivalent to your `233cf30`** (parents `dcca690`, `68bb739`). The trees differ in 5 files with no functional difference (§C1). |
| Partner unique feature commit | `feee364` | 11 files, +791/−47. Callouts, view numbers, evidence-only offsets and grid hits. |
| Your unique commits on main | `da6d325`, `91d50df` (Docker), merge `de0de8f`, `1812501` (Locate cache + asset sync), `a04ab1c`, `d9a3ea6` (docs) | Not on the partner branch. |
| `bassam/docker-estima3d` (local + origin) | `91d50df` | Fully contained in `origin/main` (`git cherry`: 0 unique). Worktree `aidr-docker` is clean. |
| `bassam/drawing-summary-osse` (local + origin) | `dcca690` | Fully contained. Worktree `aidr-summary-osse` has 3 untracked `training/documents/*.json` files (runtime). |
| `bassam/levels-elevations-phase2` (local only, upstream set to origin/main) | `9522744` | Fully contained. Worktree `aidr-levels-p2` is clean. |
| `integrate/summary-main` (local + origin) | `d9a3ea6` | Same commit as `origin/main`. Its worktree `aidr-integrate-summary-main` is the **Docker build source** (127.0.0.1:8080; Docker Desktop is not running right now). |
| Main checkout `ai-dynamic-regex` (detached) | `7cfc223` | 4 commits not on main (R&D semantic-preprocessor foundations). Already preserved by 3 tags (`archive/rnd-geometry-ml-foundations-local-2026-09-18`, …). Out of scope. |
| Other detached worktrees | `5b60a69`, `999787d`, `1ee323b`, `6116e83`, `02b852a`, `700c72f`, `7558f44` | All contained in main. Several have pre-existing uncommitted edits (mostly `backend/training/*` runtime churn; `-dlp` and `-accuracy-sprint` also have source edits). **Not touched; out of scope.** |
| Stashes | `stash@{0}` `5aa3e0f` (2026-08-31), `stash@{1}` `3093c0c` (2026-08-24) | Old training/runtime churn from `bassam/estima3d-integration`. Unrelated to this integration. Kept. |
| Archive/backup tags | 33 `archive/*`, `backup/*` tags | Recovery points from earlier consolidations. |

### Uncommitted work in this worktree (a separate source of work)

| Path | Nature | Treatment |
|---|---|---|
| `frontend/src/components/FileUpload.jsx`, `frontend/src/pages/UploadExtractPage.jsx`, `…/UploadExtractPage.test.jsx` | **A useful feature that is on no branch.** It adds:<br>• an "Upload a different PDF" button after a restored document;<br>• acceptance of a `.pdf` file the browser reports with no MIME type;<br>• re-choosing the same file after an error.<br>It comes with 2 new tests. `origin/main` has not touched these files since `e32cc5b`, so the change applies cleanly. | Proposed as its own commit in Stage 2 (decision F4). |
| `backend/training/{history.csv,unknown_tokens.csv,upload_log.csv,multimodal_review_index.json}`, `documents/doc_4ed3038af56ee2a3.json`, plus 3 untracked `documents/doc_*.json` | Runtime state from local uploads. | **Not published.** Left in place. |
| `backend/.venv/`, `.playwright-mcp/` | Local tooling. | Ignored, not published. |

---

## B. Feature comparison

Baseline for both sides: `dcca690` + `68bb739`, which is the content of either duplicate merge.

| Feature | Your implementation | Partner's implementation | User-visible difference | Commits / code | Interaction / conflict | Recommended combined behavior | Verification |
|---|---|---|---|---|---|---|---|
| **Stacked plan callouts** (a `7` printed above `S-301`) | — | Stacked label-over-sheet pairs are read as references. A pair is kept only when it is unique (one label to one sheet). Callouts in the bottom band are kept; the title-block strip (right 16%) is skipped. | Drawing Summary → "Views, references, and conflicts" lists more references, e.g. OSSE shows **66** references. | `feee364`: `intelligence_layer._stacked_callouts`, `_reference_record(bbox, stacked)` | None. | Take the partner's. | 11 new unit tests (they fail on main and pass on the partner tip and the combined preview). E2E on OSSE in the combined preview. |
| **View number beside a bare SECTION/DETAIL title** | — | `_paired_view_number`: exactly one short line on the same row, within 40 pt. Zero or several candidates leave the title unchanged. | References to those views resolve as `target view found` instead of `target sheet only`. | `feee364` | None. | Take the partner's. | 2 new unit tests. |
| **Callout regex boundaries** | — | `6.1/S-103` no longer matches as `1/S-103`. A SEE note with neither a sheet nor a view number is dropped. | Fewer false references. | `feee364`: `_BUBBLE` and `_SEE` handling | None. | Take the partner's. | Unit tests. |
| **Reference sentence + "Target" button** | — | Each reference is a sentence ("section 2 is printed on S-401-O") with **Source** and **Target** "View page" buttons; the Target button highlights the target view's bbox. The `target_view_found` chip changes from green to neutral. | Visible in Drawing Summary → relationships. | `feee364`: `EngineeringIntelligence.jsx` (`referenceSentence`, `target_bbox`) | Additive API fields: `target_bbox`, `target_view_type`. | Take the partner's. | Vitest. E2E: Target buttons rendered for OSSE (e.g. `2/S-401-O` → PDF p. 15). |
| **Grid allocations shown as evidence only** | — | "confirmed" is shown as **"closest crossing"**, "candidate" as "proposed", and so on. The text states "A proposed grid location is not a column, a beam, or a quantity." | Wording only; there is no quantity effect. | `feee364`: `ALLOCATION_LABEL` | Consistent with the quantity-safety rule (grid hits never become quantities). | Take the partner's. | Vitest + E2E text observed. |
| **Locate: offset inside the search window is not placed** | Placed a symbol found at the offset point even when that point was inside the crossing's own 6 pt search window. | `_reliable_offset`: a side counts only when the distance is at least 2 × 6 pt + ½ the mark's span. Otherwise the status is `candidate` + `search_window_limited`, the UI state is `offset_unresolved`, and the highlight stays on the crossing. | **Intentional replacement.** OSSE `C.1(-6")-7.3` changes from "Column symbol identified at the printed offset" to **"Offset direction or scale unresolved"**, with the note "9.0 pt … reliable only from 20.4 pt". | `feee364`: `column_trace._place_offset`, `_place_two_offsets`, `locate_location`. Real-PDF fixture `reference_levels.json` was updated. | Same file as your cache change; auto-merged (§C2). | Take the partner's. It is more conservative and evidence-only. | `test_view_scale` (new tests) + real-PDF `test_level_reference_set` 8/8 in the combined preview + E2E dialog observed. |
| **Locate: "toward grid" only in the same label family** | Named the nearest parallel axis, whatever its family. | Named only an axis printed in the same family (letter, number, decimal, prefixed); otherwise unnamed. | Fewer wrong "toward grid X" notes. | `feee364`: `_label_family`, `_toward_grid` | Auto-merged. | Take the partner's. | 2 new unit tests. |
| **Locate wording** | "Column symbol identified" | "Possible column symbol drawn here" (and the matching variants) | **Visible label change** in the Locate dialog and the locations table. | `feee364`: `locate.jsx` `LOCATE_STATE` / `STATUS_TEXT` | A product wording decision (F2). | Take the partner's (recommended). | Vitest. |
| **Bounded Locate plan cache** | `PlanPages` LRU limited by `LOCATE_PLAN_CACHE_MB` (default 256); a per-document lock; context dropped on re-extraction; `plan_geometry` keeps only symbol-sized paths. Measured: 802 → 309 MiB, results unchanged. | — (the partner branch has the old unbounded `context["analysed"]` / `context["geometry"]`) | No visual change. Memory stays bounded, and concurrent Locate requests are safe. | `1812501`: `column_trace.PlanPages`, `staged_pipeline.forget_locate_context`, `config.locate_plan_cache_mb` | The partner code reads `seen["symbol"]["bbox"]`, which is still produced. It does not use the removed `words`, `analysed` or `geometry` keys (checked in the merged tree). | Keep yours. | `test_summary_locate_review` passes in the combined preview. E2E Locate works through the cache. |
| **Docker / private deployment** | Backend and frontend images, compose, nginx, entrypoint, `/api/version`, build-identity pairing, `scripts/docker-build.*`, `docs/DOCKER.md` | — | A new deployment path. `/api/version` is behind the existing access token. | `da6d325`, `91d50df`, `d9a3ea6` | Additive; no partner file overlaps. | Keep yours. | `test_access_token`, `devIdentity.test.js` pass. **The Docker image was not rebuilt in this audit** (Docker Desktop is off). |
| **Shipped-asset sync** | `services/asset_sync.py`: SHA-256 manifest of `training/`; adds new files only; `apply` / `rollback`; refuses an older image. | — | Container startup log / CLI only. | `1812501`, `a04ab1c` | None. | Keep yours. | `test_asset_sync` passes. |
| **Dependency pins** | `requirements.txt`: numpy **2.5.3**; torch and torchvision moved to `requirements-torch.txt` (a separate training environment); transitive pins added. | Not changed. The partner tip still has numpy 1.26.4 and torch 2.2.2 in `requirements.txt`. | A partner's local `pip install -r requirements.txt` will change numpy and no longer install torch. | `da6d325` | **Environment conflict, not a code conflict** (F5). | Keep yours, and tell the partner to use `requirements-torch.txt` in a separate venv for training. | All three sides were tested in one venv built from main's pins. The partner's macOS environment was **not** reproduced. |
| **Upload fixes (local, uncommitted)** | Described in §A. | — | Upload & Extract page: an "Upload a different PDF" button. | Working tree only | None. | Commit separately (F4). | Vitest +2 tests; E2E: the button rendered in the combined preview. |
| Already integrated partner work | — | `56a0bbc`/`68bb739` sheet intelligence and confirmed grid extraction. Earlier: BP/CL marks, ruled schedules, structured locations, plates, level labels. | — | On `origin/main` | Already integrated. | Nothing to do. | Part of the full suite. |

**Workflows 1–3 and 5–7** (upload/OCR/section parsing/catalog; semantic resolution, exact-match locking, HSS, ambiguous labels; schedule marks, project rules, shadow/quarantine; analysis, filters, quantities, exports; review, corrections, persistence; validation and takeoff):

- **Neither side's unique diff touches these.** This was checked file by file; the only hit was a test file for Locate.
- **Their behavior is therefore what is already on main.** Within this audit, the evidence is the regression suite passing identically on all three trees, including the exact-label, HSS, correction, schedule-quantity-safety, dedup, shadow/not-wired and export test groups (about 150 tests).
- **No new runtime E2E was run for those workflows in Stage 1.** Stage 2's gates include one (§E5).

---

## C. Conflict analysis

### C1. Textual conflicts: 5 files, all caused by the duplicate merge

`git merge-tree origin/main origin/drawing-intelligence-plan-detail` reports conflicts in exactly the 5
files where `233cf30` and `3db0eb7` differ.

| File | Your side (`233cf30`) | Partner side (`3db0eb7`) | Resolution | Tradeoff |
|---|---|---|---|---|
| `legend_profile.py` `EXTRACTOR_VERSION` | `legend_extractor_v6v-summary-and-grid` | `v6v-grid-and-summary`, then `feee364` bumps it to **`v6y-callout-boundaries`**, with v6w/v6x/v6y notes | **Take `v6y`.** Keep your v6v comment plus her v6w–v6y comments. This string keys the profile cache, and `feee364` changed profile output (views and references). Keeping a v6v string would serve stale summaries. | Cached profiles are rebuilt once. That cost is intended. |
| `extraction_engine.py` `EXTRACTION_VERSION` | `3.30-summary-and-sheet-grid` | `3.30-grid-and-locate` | **Keep yours.** Both mean the same extraction output, and `feee364` does not change extraction. Keeping the published string avoids a needless re-extraction of documents already cached by the Docker deployment. | The partner's local caches re-extract once after she pulls main. |
| `column_schedule.py` | `location_tables` key before `plate_counts` | after | Keep yours. Dict order has no effect. | None. |
| `drawing_intelligence.py` | One-line set comprehension | Multi-line | Keep yours (identical semantics). | None. |
| `DrawingSummaryPanel.jsx` | Import order | Import order | Keep yours (identical imports). | None. |

- **Which side's text is kept for the cosmetic files doesn't matter.** Choosing either side alone for
  `legend_profile.py` would be wrong. "Ours" serves stale cached views and references. "Theirs" is
  right for that line, but would also take her `EXTRACTION_VERSION` and invalidate the published
  caches for no reason.
- **Verification.** This exact resolution was built as a scratch preview, tree
  **`b130e0c26f1a1ad6fa8ce7fdfeb3a1444b807a3a`** (= `origin/main` + `git diff 3db0eb7 feee364` + this
  resolution). The Stage 2 merge commit's tree must equal it, before the separate upload-fix commit.

### C2. Behavioral interaction Git merges silently: `column_trace.py`

| | |
|---|---|
| **Your change** (`1812501`) | Bound memory. `plan_geometry` no longer keeps `words` or all drawings; per-context `analysed` and `geometry` dicts are replaced by `PlanPages`; requests are serialized with a lock. |
| **Partner's change** (`feee364`) | Make offsets and "toward" evidence-only. It adds `_symbol_span(seen["symbol"])`, `_reliable_offset` and `_window_limited`, and changes `locate_location`'s state mapping. |
| **Risk checked** | Does the partner code depend on anything your cache removed? **No.** `_observe` still returns `symbol: {"bbox": …}`, and nothing in the merged tree reads `geometry["words"]`, `context["analysed"]` or `context["geometry"]`. |
| **Can both coexist?** | **Yes.** Cache keys are `(page, names)`. The partner's logic runs after the cached `_analyse_plan`, so cached results stay correct under her rule. |
| **Verification** | Combined preview:<br>• `test_summary_locate_review` (yours) and `test_view_scale` (hers) both pass;<br>• real-PDF `test_level_reference_set` passes 8/8 (OSSE `C.1(-6")-7.3` → `offset_unresolved`);<br>• E2E in the browser: the Locate dialog shows the window-limited note through the cached path. |

### C3. Behavioral replacement (intentional, not a regression)

Offset placement changes for short offsets.

| Version | OSSE `C.1(-6")-7.3` on S121 |
|---|---|
| Baseline / yours | `column_symbol_at_offset` (a symbol found at a 9 pt offset, inside the 6 pt crossing window) |
| Partner | `offset_unresolved` with an explanatory note |
| Combined | Same as the partner's, verified at runtime |

**Recommendation: accept the partner's.** It prevents a symbol drawn at the crossing from being credited
to the offset side, which matches the "evidence only, never invent" rule. Nothing loses data: the
crossing is still highlighted.

### C4. Environment conflict: the numpy/torch pins (§B)

There is no code conflict. Main's pins are the verified Windows/Docker environment. On a partner Mac
that relies on `torch==2.2.2` in the API environment, the update would break, so she needs to switch to
the separate `requirements-torch.txt` environment for training.

### Requirement check

| Established requirement | Status after the proposed integration |
|---|---|
| Exact catalog-label lock | Unaffected: neither side changed the code path. Tests pass on all trees. |
| Corrections persist and agree across results, review and exports | Unaffected (same). |
| Schedule rows don't become drawing occurrences | Unaffected. The partner's grid-allocation wording *strengthens* the message ("not a quantity"). |
| Dedup keeps genuine repeated occurrences | Unaffected. The partner's stacked callouts keep repeated callouts (`test_repeated_callouts_are_kept`). |
| Shadow-only features stay non-mutating | Unaffected. The not-wired guards pass. |
| Settings, flags, defaults, API compatibility | The OpenAPI route set of the combined preview is exactly the union of both sides (67 routes; only `/api/version` is new). New response fields are additive. New setting: `LOCATE_PLAN_CACHE_MB` (default 256). No flag defaults changed. |

---

## D. Preservation checklist

| # | Feature | Source | How the merge retains it | Proven by |
|---|---|---|---|---|
| 1 | Stacked callouts | Hiba `feee364` | Merge commit includes `feee364` | 11 tests + E2E (66 refs on OSSE) |
| 2 | Adjacent view numbers | Hiba | same | 2 tests |
| 3 | Callout regex boundaries / SEE filter | Hiba | same | tests |
| 4 | Reference sentences + Target button | Hiba | same | Vitest + E2E |
| 5 | Grid allocations as evidence-only wording | Hiba | same | Vitest + E2E |
| 6 | Window-limited offsets | Hiba | same; auto-merged with #9 | `test_view_scale`, real-PDF fixture, E2E |
| 7 | Same-family "toward grid" | Hiba | same | tests |
| 8 | Conservative Locate wording | Hiba | same (pending F2) | Vitest |
| 9 | Bounded Locate cache + lock + invalidation | Bassam `1812501` | Already on main; untouched by the merge | `test_summary_locate_review` + E2E |
| 10 | Docker images/compose/nginx/build scripts | Bassam | Already on main | Unit tests; **image rebuild = Stage 2 gate** |
| 11 | `/api/version` + build pairing | Bassam | Already on main | `test_access_token`, OpenAPI diff |
| 12 | Asset sync apply/rollback | Bassam | Already on main | `test_asset_sync` |
| 13 | Dependency pins split | Bassam | Already on main | Test venv built from them |
| 14 | Upload fixes (uncommitted) | Local worktree | Separate commit after the merge (F4) | Vitest +2; E2E button seen |
| 15 | Sheet intelligence / confirmed grid (`56a0bbc`/`68bb739`) | Hiba (already integrated) | Already on main | Suite (except the pre-existing Burrville subtests, §E5) |
| 16 | Hiba's merge `3db0eb7` (history/attribution) | Hiba | Ancestor of the merge commit | `git log` |
| 17 | Old stashes `5aa3e0f`, `3093c0c` | Local | Left untouched | — |
| 18 | `7cfc223` R&D commits | Local | Already tagged; left untouched | Tags listed in §A |

**Uncertainties:**
- Docker image behavior after the merge has not been exercised.
- The partner's macOS environment has not been exercised.
- Workflows 1–3 and 5–7 are covered only by the regression suite in this stage.

---

## E. Integration and cleanup plan (Stage 2, after approval)

1. **Refresh.** `git fetch` without prune. Stop and re-audit if `origin/main` ≠ `d9a3ea6` or the partner tip ≠ `feee364`.
2. **Recovery references.** Create lightweight tags:
   - `archive/integration-20261009/origin-main` → `d9a3ea6`
   - `archive/integration-20261009/partner-plan-detail` → `feee364`
   - `archive/integration-20261009/local-main` → `e32cc5b`

   Save the uncommitted upload fix as a patch file in the scratchpad. There is no stash and no new
   permanent branch.
3. **Integrate in a fresh detached worktree from `origin/main`.** Run
   `git merge --no-ff origin/drawing-intelligence-plan-detail`, resolving as in §C1. Check that the
   merge tree equals **`b130e0c`**. This is a real merge: it keeps Hiba's two commits and her
   authorship, and it makes her branch an ancestor of main so it can be retired cleanly.
4. **Second commit: the upload fixes** (3 frontend files), authored by you with a clear message. Do not
   include `backend/training/*`, `.venv`, `.playwright-mcp` or uploaded PDFs.
5. **Validation gates on the final candidate:**
   - **Backend.** Full `pytest`. Expected: same results as now, i.e. only the 5 pre-existing
     `test_sheet_index_reference_set` Burrville subtests fail.
     - Why they fail: on all three trees and at `68bb739` itself, the local copy of
       `ST-Burrville.pdf` prints issue "DD PRICING SET", while the fixture expects
       "50% DESIGN DEVELOPMENT". The local PDF is a different issue of that drawing set.
   - **Frontend.** Vitest (expect 315) and `npm run build`.
   - **OpenAPI.** The route set equals the union.
   - **Browser E2E on an isolated backend/frontend pair from the candidate** (OSSE):
     - upload, extract, Drawing Summary references and Target buttons, Locate `C.1(-6")-7.3`;
     - then **Analyze → Results filters → manual correction → Review → Validation (GT workbook) →
       Takeoff export**, checking that the corrected label is consistent everywhere.
   - **Docker** (if you start Docker Desktop): `scripts/docker-build.ps1`, start the stack, check that
     `/api/version` reports the candidate SHA, then run a smoke test.
6. **Publish.** Re-check `origin/main`, then do a normal `git push origin HEAD:main` (no force).
   - If the push is rejected by protection, open a PR instead. (`gh` isn't installed here, so
     protection could not be checked. `d9a3ea6` was pushed directly.)
7. **Verify.** Check that `git ls-remote` `main` equals the tested SHA. Fast-forward local `main` in
   *this* worktree only if the 3 frontend files match the committed fix. Otherwise leave the working
   tree alone and report it. The `backend/training/*` runtime churn stays as it is.
8. **Retire, only what you approve (F6).** Each retirement below is preceded by an archive tag at its
   tip, `archive/integration-20261009/<name>`.

| Branch | Status | Action |
|---|---|---|
| `origin/drawing-intelligence-plan-detail` + no local copy | Integrated after the merge (ancestor) | Delete the remote branch **only with Hiba's OK** (F6). |
| `bassam/docker-estima3d` (local + origin) | Integrated, 0 unique | Delete both; remove the clean worktree `aidr-docker`. |
| `bassam/drawing-summary-osse` (local + origin) | Integrated, 0 unique | Delete both. Worktree `aidr-summary-osse` holds only 3 untracked runtime JSONs: remove it after confirming that, or keep it if you want those files. |
| `bassam/levels-elevations-phase2` (local) | Integrated | Delete; remove the clean worktree `aidr-levels-p2`. |
| `integrate/summary-main` (local + origin) | Equals the old main | Delete after moving the Docker build to a `main` checkout (F7); remove worktree `aidr-integrate-summary-main` (clean). |
| Audit scratch: `aidr-audit-{main,partner,combined}` worktrees, `aidr-audit-venv` | Created by this audit | Remove. |
| Detached dirty worktrees, the 2 stashes, the main checkout at `7cfc223` | Pre-existing, unrelated | **Not touched.** Listed in the final report as remaining. |

---

## F. Decisions

**Routine (I'll handle these within the approved plan):**
- the cache-version strings (§C1);
- the cosmetic merge sides;
- the tag names;
- excluding runtime files;
- reproducing pre-existing failures on the base before attributing them.

**Product / team decisions:**

| # | Decision | Options | Recommendation |
|---|---|---|---|
| F1 | Integration method | (a) a real merge of the partner branch; (b) cherry-pick `feee364` only, so the duplicate merge `3db0eb7` never enters history | **(a)**. It keeps Hiba's history and attribution, and lets her branch retire as "merged". The duplicate merge is harmless. |
| F2 | Locate wording "Column symbol identified" → "Possible column symbol drawn here" | Partner's / keep the old | **Partner's.** A detected symbol is evidence, not a confirmed column. |
| F3 | Short offsets inside the search window are no longer placed (OSSE `C.1(-6")-7.3`) | Accept / keep the old placement | **Accept.** It is conservative and the crossing is still highlighted. |
| F4 | Uncommitted upload fixes | Commit to main as a separate commit / leave local | **Commit separately.** They are tested, small and independent. |
| F5 | numpy 2.5.3 / torch moved out of `requirements.txt` | Keep main's / restore torch to the API requirements | **Keep main's.** Tell Hiba to recreate her API venv, and to use `requirements-torch.txt` in a separate venv for training. |
| F6 | Delete `origin/drawing-intelligence-plan-detail` after the merge | Delete (after her OK) / keep | **Delete after Hiba confirms** she has nothing local on top of `feee364`. It is her branch. |
| F7 | The Docker stack's build source | Rebuild from a `main` checkout and retire `integrate/summary-main` / keep building from that branch | **Rebuild from main.** It meets the goal of a single active branch. |

---

## Verification log (Stage 1)

**Environment:**
- Windows 11.
- One isolated venv, a scratch venv: Python 3.12.10, built from `origin/main`'s
  `requirements.txt` + `requirements-dev.txt` (numpy 2.5.3, pytest 9.1.1).
- Node with `npm ci` from the identical lockfile (`4cea6c49` on all three revisions).
- Real-PDF reference sets from the local reference-PDF folder (not in the repository).
- No existing service was stopped. Uploads went only to the scratch worktree.

**Code inspection vs runtime.** Sections B and C are based on reading the diffs. Every "Verification"
cell names the runtime evidence behind it.

| Tree | Command | Result |
|---|---|---|
| main `d9a3ea6` | `python -m pytest -q` | 1975 passed, 5 failed, 12 skipped |
| partner `feee364` | same | 1990 passed, 5 failed, 13 skipped |
| combined preview (`b130e0c` + upload fix) | same | **1999 passed**, 5 failed, 13 skipped |
| `68bb739` | `pytest tests/test_sheet_index_reference_set.py` | 5 failed. The failure is **pre-existing**, with the same 5 Burrville subtests. |
| main with partner's tests | intelligence/view-scale/grid tests | 17 failed. These are the partner's new behaviors, absent on main, as expected. |
| combined preview | `pytest tests/test_level_reference_set.py` (real PDFs) | 8 passed |
| main / partner / combined | `npx vitest run` | 312 / 310 / **315** passed |
| main / partner / combined | `npm run build` | all ok |
| main / partner / combined | OpenAPI route set | 67 / 66 / 67; combined = union |
| combined preview | Browser at 5174 → backend 8001. The dev identity reported worktree `aidr-audit-combined`. | Upload OSSE (26 pp.) → extract (30 s) → Drawing Summary: 66 references, Target buttons and evidence-only grid text rendered → Locate `C.1(-6")-7.3`: "Offset direction or scale unresolved", with the window note and S121/S122/S123 plan tabs. |

**Not run in Stage 1:**
- the Docker build;
- Analyze → Review → Validation → Takeoff E2E;
- the partner's macOS environment;
- a GitHub branch-protection check.

---

## Stage 2 — executed (2026-10-09)

Approved: F1–F5 and F7. F6 (retiring Hiba's branch) is conditional on her confirmation.

- **Inputs re-verified unchanged:** `origin/main` `d9a3ea6`, partner tip `feee364`, local `main` `e32cc5b`.
  Recovery tags `archive/integration-20261009/*` were created at those heads and at each branch
  approved for retirement.
- **Merge:** `git merge --no-ff origin/drawing-intelligence-plan-detail` from `origin/main`, resolved
  hunk by hunk as in §C1. Git also auto-merged Hiba's relocated `EngineeringIntelligence` import into
  a non-conflicting region of `DrawingSummaryPanel.jsx`, which duplicated main's import. The duplicate
  was removed. The merge commit's tree then equalled the verified preview `b130e0c` exactly.
- **Upload improvements:** a separate commit (F4).
- **This report:** with local paths removed, in its own commit.

Verification results, the Docker check and the branch cleanup outcome are reported with the
publication. Re-running the checks in §E5 against `main` reproduces them.

### Correction found during Stage 2 verification

§C1 kept `EXTRACTION_VERSION` on the premise that `feee364` does not change extraction output. That
premise was wrong:
- The cached `document.json` embeds the Drawing Summary's `engineering_intelligence`.
- That cache is keyed by `EXTRACTION_VERSION` alone.
- The container smoke test showed the three documents already in the data volume still serving
  `engineering_intelligence_v2`, with no stacked callouts and no `target_bbox`.

`5726367` moves it to `3.31-callout-boundaries` on top of the verified merge (merge tree still
`b130e0c`). Documents cached by earlier builds are extracted and analysed again on first use.
