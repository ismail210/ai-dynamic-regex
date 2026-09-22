# Final Refactor and Verification

This is the concluding phase of the codebase-refactor engagement: reconcile local and partner git history,
fix a confirmed exact-match-locking semantic defect, run one final bounded refactor sweep, and verify the
whole repository (backend, frontend, and live-route UI) before pushing.

- **Starting local SHA**: `a0b0c3087784425528ef874416f78e796c7d8d27`
- **Starting remote SHA (observed at merge time)**: `afb692671d9b45347bd1efee4b44e3daf4ae2486`
- **Shared merge base**: `492b61225a2150ea8a2f419e75e3fdceb387d178`
- **Final local SHA (this phase)**: `84a780e...` (see Final Report for the exact post-push value)

## 1. Divergence and merge-base analysis

`origin/main` had advanced to `afb6926` — a merge commit (parents `85f333a`, `492b612`) landed by a partner
(Hiba Reda, via Cursor) who had merged `origin/main` (my `492b612`) into their own feature branch
(`estima3d-integration`) after independently committing `85f333a` ("feat(extraction): schedule mark map,
inch angles, and review viewer windowing") on top of an older shared ancestor. `afb6926` had already cleanly
resolved that side; the only remaining reconciliation needed was between my 3 unpushed commits
(`9b8c98c`/`e7c20ec`/`a0b0c30`, the `_build_encoder_input` extraction) and `afb6926`.

Confirmed before merging: `git diff --name-only 492b612 85f333a` showed a large file list, but this was an
artifact of `85f333a` being based on old history, not `85f333a`'s own real diff — comparing `492b612` directly
against `origin/main` (`afb6926`, the already-integrated state) showed only `backend/services/prediction/
orchestrator.py` (86 insertions, 14 deletions) among the 4 files my 3 commits touched; my test file and both
doc files were untouched on origin's side. No remote commit touched any preserved-drift path (verified via
`git diff --name-only 492b612 85f333a | grep` against the 3 tracked drift paths — no match).

## 2. Integration strategy and conflict resolution

Used `git merge --no-commit --no-ff origin/main` (not rebase, no autostash) so the combined result could be
inspected before committing, exactly as directed. **Result: automatic merge, zero manual conflicts.** Git's
own 3-way merge cleanly combined both sides because they touch disjoint regions of `orchestrator.py`:
partner's schedule-mark-map/`block_fuzzy_catalog`/`schedule_mark_locked` logic lives in the candidate-
generation and section-resolution regions (roughly lines 380-440, 590-720, 940-1050, 1300-1320, 1660-1815);
my `_build_encoder_input` helper and its two call sites (~322-370, ~530, ~780) are untouched by the partner's
diff. Verified by direct post-merge inspection of both call sites (byte-identical to what I wrote) and a
fresh `py_compile`/import pass. `services/multimodal/pipeline.py` also merged cleanly without a conflict
marker despite both sides touching it (partner added a `shadow_page_gate` import; an earlier phase's already-
merged `_ablation_active as _ablate` import stayed intact) — confirmed via direct read of the merged file.

No conflict markers ever appeared, so no per-hunk "ours/theirs" decision was required. Staged the merge,
confirmed preserved drift was not staged (`git status --short` showed drift files as unstaged `M`/untracked
`??`, never staged), ran the merge-verification test set (see below), then committed as `c15bd56`.

## 3. Partner functionality preserved

All of it, verified directly: `resolve_schedule_mark`/`is_bare_schedule_mark` (schedule MARK→SIZE grid
join), `block_fuzzy_catalog` (renamed from `angle_catalog_abstain`, now also covers unresolved schedule
marks), `schedule_mark_locked` (a new confidence/provenance state parallel to `section_text_locked`), the 2
new config flags (`schedule_grid_enabled`, `schedule_mark_map_enabled`, `shadow_context_page_gate_enabled`,
all additive with safe defaults), `services/engineering/schedule_grid.py` and `shadow_page_gate.py` (both
new files, 297 and 76 lines), inch-angle normalization in `token_extractor.py`/`annotation/parser.py`/
`plate_grammar.py`, and the review-viewer PDF page-mounting windowing in `PdfDocumentViewer.jsx`/
`DrawingReviewPage.jsx`. Partner's own 2 new test files (`test_own_label_dimension_fix.py`,
`test_struct_notation.py`, 708 lines combined) pass unchanged.

## 4. Encoder-input extraction preserved

`_build_encoder_input` and its 2 call sites are present, byte-identical to the pre-merge commits, at their
original relative position in the function. `EncoderInputContractTests` (2 tests, spying on the real
`encoder_registry.encode_all`) pass unchanged post-merge. No adaptation was needed — the partner's diff never
touches the encoder-input dict construction or its 2 call sites.

## 5. Combined baseline

- **Collection**: 1336 tests, 0 errors (immediately post-merge, before Phase 3/4 changes).
- **Full backend suite** (immediately post-merge): **1323 passed, 9 failed, 4 skipped, 385 subtests** (up
  from the pre-merge local baseline of 1299/9/3/349 — the extra pass count and 1 extra skip are partner's own
  new/skipped tests; the known-failure set is byte-identical by name and message).
- **Frontend**: 217 passed, 0 failed, 21 test files (unchanged from the pre-merge baseline — no frontend test
  file overlapped with the partner commit's own additions in a way that changed the count).
- **Frontend build**: succeeded (`npm run build`, ~19s).
- No eslint/lint config exists in this repository (`frontend/` has no `.eslintrc*`/`eslint.config*`) — no
  separate lint step was skipped; there simply isn't one configured.
- Drift fingerprints and `git status --short` re-checked identical immediately after establishing this
  baseline.

## 6. Exact-match late-reclassification defect — root cause

A prior mapping phase (`orchestrator-decomposition-readiness.md`) characterized, but did not fix, a real,
reachable gap: in `predict_from_context`, a *later* annotation-taxonomy interpretation
(`interpret_token_annotation`) that confidently classifies a token as a confirmed plate/bent-plate could
clear an *already-locked* exact catalog match (`protected_exact_section`/`section_text_locked`) — the branch
had no guard checking "was this already a protected exact match" before clearing `section` and setting
`confirmed_plate_type`. This conflicts with the repository's authoritative exact-match-locking rule: a
locked identity may be enriched or associated with later evidence, but never changed, cleared, demoted, or
sent to review by it. The neighboring `requires_review`/annotation-ambiguity branch a few lines below already
had exactly this guard (`if protected_exact_section: pass  # keep the label`); the late-plate branch was the
one place this pattern was missing.

## 7. Exact-match fix — tests added/changed

Rewrote `LateAnnotationReclassificationTests` in `tests/test_trusted_explicit_section.py` (commit `5e7e5de`)
to express the corrected contract instead of merely characterizing the bug:

- `test_protected_exact_match_survives_late_plate_reclassification` — asserts `section` stays `"W18X35"`
  (not cleared), `needs_review` is `False`, `review_status` is not `pending_review`, `confidence.overall ==
  1.0`, `section_resolution == "explicit_catalog_exact"`, and that the annotation classifier's diagnostic
  evidence (`annotation_interpretation.annotation.annotation_type == "BENT_PLATE"`) remains visible —
  enrichment, not suppression. **Verified to FAIL against the pre-fix code**
  (`AssertionError: '' != 'W18X35'`), proving the defect, before the fix commit.
- `test_late_reclassification_still_applies_to_a_non_protected_token` — same mocked classifier, a token with
  no protected exact match (`"NOTACATALOGSHAPE"`) — asserts the late-plate branch still clears the section
  and routes to plate handling exactly as before. **Verified to already pass**, establishing the safe-path
  baseline the fix must not break.

## 8. Exact-match fix — implementation

One-line guard added (commit `eea2b46`): `if not confirmed_plate_type:` → `if not confirmed_plate_type and
not protected_exact_section:`, with a short comment explaining the reasoning and cross-referencing the
neighboring branch's identical pattern. `interpret_token_annotation` still runs unconditionally just above
(diagnostic evidence gathering is unaffected); only the *act* of clearing the section based on its result is
now gated. No other line changed.

## 9. Proof: non-protected/unresolved behavior remains functional

`test_late_reclassification_still_applies_to_a_non_protected_token` passes both before and after the fix,
unchanged. `protected_exact_section` is `None` for any incomplete (`HSS8X8`), invalid, or non-catalog token
by construction (`resolve_trusted_explicit_section`'s own contract, unchanged), so the guard never engages
for those cases — confirmed by the full `NegativeSafetyTests`/`CrossFamilyDecoyTests`/`ResolverUnitTests`
suite (already existing, 182 passed post-fix) continuing to pass with zero changes.

## 10. Repository-wide candidate matrix (Phase 4 sweep)

An AST-based exact-function-body duplicate scan across `backend/services/` (excluding `label_reconstruction/`
and `ml_association/`, both guard-tested shadow modules explicitly meant to stay isolated per `CLAUDE.md`)
found 4 genuine exact-body duplicate groups (after excluding trivial `__init__`/`to_dict` noise):

| Candidate | Files | Decision | Reason |
|---|---|---|---|
| `_torch()` lazy-loader | `multimodal/graph_ai.py`, `multimodal/learned_fusion.py` | **Implemented** | Byte-identical 3-line wrapper around `torch_runtime.load_torch()`, already the canonical function both files call. Consolidated via aliased import (`from ...torch_runtime import load_torch as _torch`); all 6 call sites unchanged; lazy-loading behavior preserved (no eager top-level torch import). |
| `_length_of_segments`, `_orientation_deg` | `engineering/geometry_extractor.py`, `engineering/geometry_normalizer.py` | **Implemented** | Byte-identical signatures and bodies. `geometry_extractor.py` already imports `merge_collinear_fragments` from `geometry_normalizer.py` (established safe dependency direction), so both duplicates were removed from `geometry_extractor.py` and now imported from the same existing line. |
| `_bbox_overlap` | `engineering/extraction_noise_filter.py`, `extraction_engine.py` | **Rejected** | Identical body, but **different default `min_ratio`** (0.25 vs. 0.3) and neither caller passes it explicitly — merging would silently change behavior for one of the two callers. A real false-positive caught by checking signatures, not just bodies. |
| `_add` (×2, same file) | `label_reconstruction/candidates.py` | **Deferred** | Inside a guard-tested shadow module (`test_label_reconstruction_not_wired_into_production.py`) explicitly meant to stay isolated, not actively refactored, per `CLAUDE.md`. |

**Orchestrator-specific**: re-examined `predict_from_context` post-merge for further safe extraction seams
per this phase's explicit criteria (contiguous, pure, explicit I/O, no hidden shared state). One additional
near-duplicate was found — the `section_resolution`/`inference_required` 3-way ternary chain, computed
identically in 2 places (once as `build_canonical_prediction` kwargs, once inlined into the legacy output
dict) — but **rejected**: it is only ~8 lines in each of 2 places; a helper's own definition overhead would
almost certainly exceed the savings, repeating the exact lesson already measured and documented in the prior
`_build_encoder_input` extraction (+9 net LOC against a -25/-30 estimate). No further orchestrator extraction
was implemented this phase; none met the safety-and-payoff bar together.

**Frontend**: a bounded check of the partner-touched files (`PdfDocumentViewer.jsx` 697 LOC,
`DrawingReviewPage.jsx` 505 LOC, `SemanticReviewPage.jsx` 869 LOC, `BboxHighlight.jsx` 252 LOC) found no
obvious, safe, high-confidence duplication. The repository's frontend consolidation surface was already
substantially mined in an earlier phase (`StatsCards`→`KpiCard` implemented, a forced generic `MetaChip`
badge/chip abstraction correctly rejected after measuring +30 LOC). No frontend refactor was forced without
comparable evidence; none is implemented this phase.

## 11. Refactors implemented, by commit

- `c15bd56` — merge integration (no code change of its own; git's automatic 3-way merge).
- `5e7e5de` — `test(prediction): lock exact section through late reclassification` (test-first).
- `eea2b46` — `fix(prediction): preserve exact match after annotation classification` (the one intentional
  semantic behavior change authorized this phase).
- `84a780e` — `refactor(backend): eliminate exact duplicate private helpers` (`_torch` × 2 files,
  `_length_of_segments`/`_orientation_deg` × 1 file).

## 12. Candidates rejected/deferred, with reasons

- `_bbox_overlap` (extraction_noise_filter.py / extraction_engine.py) — different default parameter values;
  merging would change behavior. **Rejected.**
- `_add` (label_reconstruction/candidates.py, same-file duplicate) — inside an isolated, guard-tested shadow
  module; not touched by design. **Deferred indefinitely, by repository policy.**
- `section_resolution`/`inference_required` ternary duplication inside `predict_from_context` — too small to
  justify a helper's own definition overhead, per the measured lesson from the prior encoder-input
  extraction. **Rejected.**
- Any further `predict_from_context` decomposition beyond the already-completed `_build_encoder_input`
  extraction — the function's exact-match/HSS/fusion/review control flow remains deeply interwoven with
  extensive shared mutable local state (`section`, `retrieval_gate_failed`, `ai_reasons`,
  `confirmed_plate_type`), exactly as mapped in the readiness phase; no new contiguous, pure, low-risk
  boundary was found post-merge. **Deferred — this remains real, non-speculative future work, not a
  "recommended cleanup phase" placeholder.**
- Frontend components in partner-touched files — no genuine net-simplification candidate found in a bounded
  check. **Deferred, not forced.**

## 13. Production LOC before/after

| Area | Before (`492b612`) | After (this phase, `HEAD`) | Delta | Attribution |
|---|---|---|---|---|
| `orchestrator.py` | 2,068 | 2,155 | **+87** | +72 net from partner's schedule-mark-map feature (86 ins/14 del), +9 from `_build_encoder_input` extraction (measured, not estimated — see prior phase), +7/-1 from the 1-line exact-lock guard + comment, -1 from consolidation-adjacent whitespace |
| `graph_ai.py` + `learned_fusion.py` | — | — | **-10** | this phase's `_torch` consolidation |
| `geometry_extractor.py` | — | — | **-13** | this phase's `_length_of_segments`/`_orientation_deg` consolidation |
| Partner's new files (`schedule_grid.py`, `shadow_page_gate.py`, + ~8 other touched backend files) | — | — | **+~470** (not this phase's work) | partner's own genuine new feature, preserved as-is |

This phase's own net production LOC change (excluding partner's independent feature work and the
already-reported prior-phase extraction): **-23** (`-10` + `-13`), plus the 1 intentional +6 semantic-fix
line.

## 14. Test LOC before/after

This phase: `test_trusted_explicit_section.py` +59/-26 (net +33, the exact-lock test rewrite) is already
counted; no other test files were added or removed in Phase 3/4. Combined with the merge (which brought in
partner's 2 new test files, 708 LOC, not this phase's own authorship), total test LOC in the touched-file set
grew substantially, entirely attributable to partner's own new coverage plus this phase's +33-line contract
correction.

## 15. Orchestrator LOC and complexity before/after

2,068 → 2,155 physical LOC (+87, net +4% — see attribution table above; the great majority is partner's
genuine new schedule-mark-map feature, not refactor bloat). `predict_from_context` itself grew similarly in
proportion (still the dominant complexity center, ~1,650-1,700 LOC post-merge); `predict_token` (147 LOC) was
not touched by any commit in this entire engagement. No net complexity reduction was achieved or claimed this
phase beyond the already-reported prior-phase `_build_encoder_input` extraction and this phase's 2 small
private-helper de-duplications — consistent with this phase's own finding that no further safe
orchestrator-internal extraction exists without a materially larger restructuring effort.

## 16-20. Test/build/UI results

See the Final Report below for exact, non-duplicated figures (backend suite, frontend suite, build, route-by-
route UI, critical workflow, console/network, responsive check).

## 21. Preserved-drift verification

The 3 tracked drift files' SHA256 fingerprints (`9da44ace...`, `76d66bc7...`, `a07d4220...`) were re-verified
identical: at the start of this phase, after the merge, after the Phase 3 test-first run, after the Phase 3
fix, after the Phase 4 consolidation, after the full backend suite, and after the live-server UI testing
phase (which used a real backend on port 8000 but was deliberately restricted to read-only route navigation
— see the Final Report's explicit note on why a full live write-triggering upload→extract→analyze workflow
was not attempted). Zero deviation at any checkpoint. All documented untracked drift
(`doc_06009aaef05256fa.json`, `label_reconstruction_tmp/`, `docs/validation/phase_c_*`/`phase_d1_*`/
`phase_d2_*`) remained present and untouched throughout.

## 22-25. Final commits, SHA, remaining failures, remaining high-risk work

See the Final Report below.
