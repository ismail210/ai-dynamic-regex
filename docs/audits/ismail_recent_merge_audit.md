# Audit: Ismail's Recent Merge / Accuracy-Merge Branch

**Date:** 2026-08-10
**Auditor:** Claude (deep engineering audit, code + live smoke test)
**Scope:** `origin/main` (`e36fb1b`) and `origin/accuracy-merge-bassam-phase-ab` (`1c670b7`), audited against Bassam's local branch `bassam/rnd-geometry-ml-foundations` (`bb3d67c`)
**Status:** Audit only. No code changed, no flags enabled, no branches merged, nothing committed or pushed.

---

## 1. Executive Summary

The single most important finding of this audit is **structural, not cosmetic**: what Ismail describes as "merging Bassam's R&D packages into the current pipeline" is **not a git merge**. `origin/main` and `origin/accuracy-merge-bassam-phase-ab` are commits on a history that **diverged** from Bassam's R&D branch at a common ancestor (`2911a8a`) and **never incorporated it**. Ismail's branch independently re-implements `label_reconstruction`, `ml_association`, and `spatial_index` from scratch. The packages happen to end up with the same names and a similar shape to Bassam's originals, but they are a **parallel, from-scratch reimplementation**, not a merge of Bassam's actual commits. This matters because every "did the merge preserve X" question in the brief is really "did the reimplementation preserve X" — and the audit below shows the answer is: partially, with real regressions.

On the encouraging side: the core isolation guarantees genuinely hold. Feature flags default OFF, are documented accurately in `.env.example`, production modules do not directly import the experimental packages, and two dedicated isolation tests actively enforce this and pass. The label-ranker shadow hook is a clean, minimal bridge that is a true no-op when both flags are off.

On the concerning side, this audit found **five P0/P1-class bugs that are real today or will surface the moment a flag is flipped**, plus a live, reproducible example of one of them in the smoke test:

1. **P0** — The exact-section fallback path can bypass AISC catalog validation and return a confidently-labeled, non-existent shape when the primary confidence gate fails (`orchestrator.py`).
2. **P0** — The new "holdout" evaluation for the exact-section retrieval index builds a leakage-free shadow model and then discards it before scoring, silently falling back to the full (leaked) production index (`evaluate_pipeline.py`).
3. **P0** — Training-label generation for GraphSAGE role classification still hard-codes shape-family → role shortcuts for HSS/PIPE/L, and widens the shortcut versus the pre-fix code for exactly the diagonal/ambiguous-orientation members that most need correct role labels (`neural_dataset.py`, `rule_engine.py`).
4. **P1** — A module-level singleton cache (`GraphFeatureProvider`) has a check-then-write race that can attach one document's graph evidence to another document's prediction under concurrent requests.
5. **P1** — No exception handling around the label-ranker shadow/enabled call path; safe only because the flags default off today.

The live smoke test reproduced the practical consequence of #1 directly: a clean, unambiguous OCR read (`W16x26`, normalizing perfectly to catalog shape `W16X26`, 100% text-evidence score) was overridden by fusion to `W14X22` (64% text evidence) at 20% confidence, with the system's own explanation admitting "two or more candidates are near-tied; automatic selection is not reliable enough" — yet the UI still presented it as a confident "Corrected Prediction" rather than abstaining.

Test suite: **303 passed, 2 failed, 1 skipped** on the accuracy-merge branch. Both failures are real regressions (detailed in §17), not environment noise.

GraphSAGE: no `.pt` checkpoint exists in git for either branch. The `same_tag` edge-feature-width fix is implemented correctly and is checkpoint-version-safe. But any checkpoint trained today would still inherit the role-label contamination in finding #3 above — **mark any existing local GraphSAGE checkpoint as needing retraining.**

---

## 2. Git / Merge History

Executed per the safety protocol before any other action:

```
git status            → clean except pre-existing untracked local artifacts (training outputs)
git branch --show-current → bassam/rnd-geometry-ml-foundations
git remote -v          → origin = https://github.com/ismail210/ai-dynamic-regex.git (partial clone, blob:limit=1048576)
git fetch --all --prune → discovered NEW remote branch: origin/accuracy-merge-bassam-phase-ab
```

**Branch topology found (`git log --oneline --decorate --graph --all`):**

```
* 1c670b7 (origin/accuracy-merge-bassam-phase-ab) Add accuracy merge and ML association phase
* e36fb1b (origin/main, origin/HEAD) feat: restore AI multimodal pipeline and training models
| * bb3d67c (HEAD, bassam/rnd-geometry-ml-foundations, main, origin/bassam/rnd-geometry-ml-foundations) feat(rnd): add measurable geometry and ML-assisted steel inference foundations
|/
* 2911a8a feat(backend): wire canonical prediction contract, wildcard matching, and calibration
* ef6f71b fix(ui): handle legacy analyses and remove MUI prop warnings
* b9a9268 Initial commit
```

- **HEAD before:** `bb3d67c` (unchanged throughout — current branch was never touched)
- **HEAD after:** `bb3d67c` (no pull performed on the working branch; nothing to fast-forward — `bassam/rnd-geometry-ml-foundations` was already up to date with its own remote tracking branch)
- **Merge commits involved:** **none.** `1c670b7` is a single linear commit on top of `e36fb1b`, not a git merge commit (no second parent).
- **Parent branches:** `e36fb1b` and `bb3d67c` share only the common ancestor `2911a8a`; neither is an ancestor of the other.

Because merging `origin/main` or `origin/accuracy-merge-bassam-phase-ab` into the current branch was explicitly out of scope for this audit, two **isolated git worktrees** were created for read-only inspection instead (no working-tree files touched, no branches switched in place):

- `.../scratchpad/audit-origin-main` → `origin/main` @ `e36fb1b`
- `.../scratchpad/audit-accuracy-merge` → `origin/accuracy-merge-bassam-phase-ab` @ `1c670b7`

All code audit, the test run, and the live smoke test in this report were performed against the `accuracy-merge` worktree, since that is the branch that actually contains the experimental packages and is the closest thing to "Ismail's merged work."

**Practical implication:** none of Bassam's `bb3d67c` R&D commit is reachable from `origin/main`. If someone later does a real `git merge origin/main` (or the reverse) into `bb3d67c`, expect a large, non-trivial merge conflict across `label_reconstruction/`, `ml_association/`, `spatial_index.py`, and the orchestrator/graph_builder files — both sides changed the same files independently. This should be planned as a deliberate reconciliation, not a routine pull.

---

## 3. What Ismail Claimed

Per the task brief (relayed by Bassam): merged `label_reconstruction`, `ml_association`, experimental `spatial_index`, and related scripts/tests into the pipeline; all three stay behind flags defaulting OFF (`ML_LABEL_RANKER_SHADOW`, `ML_LABEL_RANKER_ENABLED`, `ML_ASSOCIATION_DATASET_ENABLED`); the label-reconstruction model has "only a safe hook" (`label_ranker_hook.py`) into the orchestrator; weak exact-section overrides are now gated with abstention instead of invention; structural parsing/OCR plausibility improved; holdout evaluation is honest; approve flow can create exact-section anchors; Drawing Review distinguishes inferred vs. text evidence; dense-page geometry cap is more length-aware; a graph-evidence UI bug ("Graph evidence: Unavailable") was fixed by carrying `source_node`/`node_kind`/`graph_available` and stopping on "first real match"; stale graphs after re-extraction are now detected/rebuilt with page+bbox+text fallback resolution; shape-family vs. structural-role were previously conflated and are now separated; GraphSAGE checkpoint loading broke when `same_tag` widened the edge feature vector and was repaired.

## 4. What the Repository Actually Contains

Confirmed present in `1c670b7` (`git diff --name-status 2911a8a..origin/accuracy-merge-bassam-phase-ab`, 112 files changed, +58,527/−43,892):

- `backend/services/label_reconstruction/` (7 new files: `__init__.py`, `candidates.py`, `corruption.py`, `features.py`, `ranker.py`, `shadow.py`, `structural_parser.py`)
- `backend/services/ml_association/` (10 new files)
- `backend/services/engineering/spatial_index.py` (new, 446 lines)
- `backend/services/prediction/label_ranker_hook.py` (new, 76 lines)
- `backend/scripts/feature_flags_status.py`, `compare_label_ranker_shadow.py`, plus 12 other new label-reconstruction/ML-association scripts
- Modified: `orchestrator.py` (+177/−), `graph_builder.py` (+268/−), `structural_graph.py` (+219/−), `exact_section_predictor.py` (+115/−), `geometry_extractor.py` (+173/−), `neural_dataset.py`, `multimodal/graph_ai.py`, `.env.example`, `config.py`, plus new frontend files (`DrawingReviewPage.jsx`, `PdfDocumentViewer.jsx`, `BboxHighlight.jsx`, `SectionResultsList.jsx`)
- 23 new/modified test files matching the new packages

All of the reported files exist. None of it is vaporware. The question this audit answers is whether the *behavior* matches the *claims* — see §5–§15.

---

## 5. Verified Changes

- **Feature flag defaults** (`config.py`): `ml_label_ranker_shadow`, `ml_label_ranker_enabled`, `ml_association_dataset_enabled` all default **False**. `learned_fusion_enabled` (pre-existing, unrelated flag) defaults **True**, correctly documented.
- **`.env.example`** accurately documents all four flags and their real defaults, plus notes `spatial_index.py` has no env flag and isn't wired into live analyze/graph_builder.
- **No direct production imports** of `label_reconstruction`, `ml_association`, or `spatial_index` from `orchestrator.py`, `staged_pipeline.py`, `multimodal/*.py`, or any router. The only import paths are through the sanctioned bridge (`label_ranker_hook.py`) and within the experimental packages themselves.
- **Two isolation tests** (`test_label_reconstruction_not_wired_into_production.py`, `test_ml_association_not_wired_into_production.py`) source-scan a fixed list of production modules for the literal package names and assert flag defaults. Both **pass** (11 tests).
- **Label-ranker shadow hook is a true no-op with both flags off** — verified by direct code trace and by test.
- **Shadow-only never changes the live prediction** — verified: `orchestrator.py` only overwrites `section` when `applied=True`, which requires `ml_label_ranker_enabled=True`.
- **Enabled path requires catalog-valid candidates** — the ranker only reorders a candidate list that was pre-filtered against `_CATALOG_LABELS`; it cannot invent an off-catalog label itself (contrast with §7 bug #1, which is a *different* code path).
- **Missing-checkpoint handling fails safe** — `ranker.get_active_ranker()` returns `None` (documented, never raises) if no model file exists; callers guard on `None`.
- **`spatial_index` is genuinely not wired into live candidate generation** — `graph_builder.py`'s pairwise-window candidate logic (`page_geom[:60]`, `candidates[i+1:i+1+12]`) is unchanged; `spatial_index.py` exists purely as a measurement/future-adoption module, consumed only by `ml_association/candidate_dataset.py` and its own test.
- **Structural-role decoupling is real in one place**: `rule_engine.py::_infer_role()` genuinely derives role from text keywords and independent geometry signals (orientation, connectivity), not from shape family — this is a correct, working fix (see §12 for where the fix does *not* extend).
- **Drawing Review's inferred-vs-text evidence distinction is real**, not cosmetic: `predictionContract.js::isInferredLocation()` checks real per-channel `available` flags sourced from `explanation_engine.py`, and the UI changes both copy and a `variant` prop based on it.
- **Dense-page geometry cap ranking is genuinely length-aware**: the retained-geometry *ranking* now sorts by `max(area, perimeter)` instead of raw bbox area, fixing the documented defect where zero-area long members were dropped first (confirmed by `test_dense_page_geometry_cap.py`).
- **Graph evidence genuinely reaches predictions**, traced end-to-end from `structural_graph.py` producer through `feature_providers.py` → `orchestrator.py` → `explanation_engine.py` → contract → frontend, with matching field names at every hop and a passing regression test (`test_graph_feature_resolution.py`). Confirmed live in the smoke test (§16): graph evidence scores of 90% vs. 53% were the deciding factor in a real prediction.
- **`same_tag` GraphSAGE edge-feature-width change is checkpoint-version-safe**: old-format checkpoints are recovered via a legacy relation-count → vocabulary mapping that was verified byte-for-byte equivalent to the pre-change schema; shape mismatches raise cleanly rather than silently corrupting.

## 6. Claims Not Verified (insufficient evidence, not necessarily false)

- **"GraphSAGE checkpoint loading broke and was repaired"** — no `.pt` checkpoint exists anywhere in either branch's git tree, and no `.gitignore` entry accounts for it either. The *code* that would load one is correctly implemented (§13), but there is no artifact in the repository to certify. Whether an actual break-and-repair happened on someone's local machine is unverifiable from the repo alone.
- **"Approve flow can create exact-section anchors"** — verified as true (`dataset_manager.py::review_token` does call `append_exact_section_anchor`), but this is entangled with a real leakage bug (§7 #2) that Ismail's report does not mention.
- **Association-dataset review loop feeding training** — the offline review-kit → decision JSON → `import_review_decisions.py` path is real and functional, but **no training script anywhere consumes the resulting outcomes JSONL**. The claim that this becomes a supervised dataset is aspirational, not yet true.

---

## 7. Bugs / Regressions Found

Ranked by priority. Each entry: root cause, affected files, production impact, priority.

### P0-1: Exact-section fallback bypasses catalog validation
**Root cause:** `orchestrator.py::_gated_exact_override()` (~L102–140) has a real, well-implemented primary gate (confidence ≥ 0.72, margin ≥ 0.06, OCR plausibility). But its fallback when that gate fails is `if is_exact_section_label(fusion_section) or lookup_shape(fusion_section): return fusion_section, False`. `is_exact_section_label()` is a **regex format check only** — not catalog membership — so a well-formatted but non-existent shape (e.g. `W12X999`) satisfies the OR and is returned as the final section with confidence *not* zeroed.
**Affected files:** `backend/services/prediction/orchestrator.py`, `backend/services/exact_section_predictor.py`, `backend/services/multimodal/modular_fusion.py` (whose `section = scored[0]["shape"] if scored else fallback_section` can hand this path a raw, uncorrected OCR token when fusion candidates are all catalog-filtered out).
**Impact:** directly contradicts "abstains instead of inventing weak sections" — can silently produce a confident, non-catalog prediction.
**Priority: P0.**

### P0-2: Holdout evaluation discards its own leakage-free model before scoring
**Root cause:** `evaluate_pipeline.py::section_prediction_performance()` builds a shadow exact-section index with `train_exact_section_model(persist=False, exclude_tokens=..., exclude_split="test")`, then immediately calls `reload_exact_section_artifact()`, which clears the global model cache. The next prediction call reloads from disk — the full production artifact, **including the test-split rows**. The carefully-built leakage-free shadow model is discarded before it's ever used to score.
**Affected files:** `backend/scripts/evaluate_pipeline.py`.
**Impact:** reported top-1/top-3 holdout accuracy for exact-section prediction is measured against a model that has seen the test tokens — not honest. This is a *new* bug in this branch (the prior version had no split at all, so this is a regression in the attempt to fix that, not equivalent to the old behavior).
**Priority: P0.**

### P0-3: GraphSAGE training-label generator reintroduces (and widens) the shape-family → role shortcut
**Root cause:** `neural_dataset.py::_member_role()` falls back to `_ROLE_FROM_FAMILY` — a straight family→role table (`HSS→column`, `PIPE→column`, `L/2L→brace`) — whenever the upstream rule engine doesn't supply a canonical role. `rule_engine.py::_infer_role()` is a genuine, context-based fix for most cases, but returns non-canonical `"bolt"`/`"member"` for bolt-pattern text and for **any member with orientation strictly between 35°–60°** — i.e. diagonal members, which in steel drawings are overwhelmingly braces. Those fall straight into the family table. A diagonal HSS brace at ~45° is trained into the model as a **column**.
**Affected files:** `backend/services/training_pipeline/neural_dataset.py` (L50–90), `backend/services/engineering/rule_engine.py` (L64–80). Two call sites (`neural_dataset.py:493, 746`) invoke `_member_role()` with **no role argument at all**, guaranteeing the shortcut fires 100% of the time for those rows.
**Impact:** any GraphSAGE checkpoint trained on current code will learn to call diagonal HSS/pipe braces "columns" and diagonal W-shape braces "beams" — reproducing, invisibly, the exact bug the redesign claims to have fixed. No test catches this (zero references to `_member_role`/`_ROLE_FROM_FAMILY` anywhere in `backend/tests/`).
**Priority: P0** — corrupts ML training signal while the rule-based code superficially looks fixed.

### P0-4 (compounding, related to P0-2): `graph_builder.py` still hard-codes W/S/M→beam, HP→column
**Root cause:** `graph_builder.py::_FAMILY_NODE_KIND` still unconditionally maps `W/S/M → NodeKind.BEAM` and `HP → NodeKind.COLUMN` when no explicit context word is present — despite an in-code comment claiming "only families whose role is genuinely implied by shape get a role kind." `structural_graph.py::_semantic_kind()` was fixed to *not* add new shape-family shortcuts, but its fallback (`node.get("kind")`) silently inherits whatever `graph_builder.py` already assigned, re-importing the shortcut.
**Affected files:** `backend/services/engineering/graph_builder.py` (L52–66), `backend/services/engineering/structural_graph.py` (L52).
**Impact:** a bare `W14X90` with no surrounding context is always classified "beam," even though the background brief explicitly says it could be beam, column, or brace.
**Priority: P1** (narrower than P0-3 — this is deterministic-path only, doesn't poison training the way P0-3 does, but it is a live production behavior, confirmed in the smoke test's extraction output).

### P1-1: `GraphFeatureProvider` singleton cache race — cross-document evidence contamination
**Root cause:** `_graph_provider = GraphFeatureProvider()` (`orchestrator.py:73`) is a **module-level singleton** shared across all requests for the process lifetime. Its internal lookup cache does a non-atomic check-then-write (`feature_providers.py:161-168`): two concurrent `analyze` calls for *different* documents can interleave such that the cached lookup index and its fingerprint become mismatched, and — because token IDs are positional (`token_pN_M`) — one document's prediction can silently attach another document's graph node as evidence during the race window. No locking/versioning exists anywhere in `artifact_store.py` or `staged_pipeline.py`.
**Affected files:** `backend/services/multimodal/feature_providers.py` (L144–176), `backend/services/prediction/orchestrator.py` (L72–73).
**Impact:** silent, no error, not exercised by any existing test (all single-threaded). Requires genuine request concurrency to trigger.
**Priority: P1.**

### P1-2: No exception handling around the label-ranker reconstruct call
**Root cause:** `label_ranker_hook.py:61` and `shadow.py::reconstruct()` have no try/except. Safe today only because both flags default off.
**Affected files:** `backend/services/prediction/label_ranker_hook.py`, `backend/services/label_reconstruction/shadow.py`.
**Impact:** the moment `ML_LABEL_RANKER_SHADOW` or `ML_LABEL_RANKER_ENABLED` is set true anywhere (including a controlled shadow test), any exception in normalization/candidate-generation/xgboost scoring will crash the analyze call for that token, rather than degrading gracefully — undermining shadow mode's entire "safe to enable" premise.
**Priority: P1**, blocking for anyone about to flip either flag.

### P1-3: Confidence/evidence not recomputed after a label-ranker override
**Root cause:** when `ML_LABEL_RANKER_ENABLED` swaps `section` (`orchestrator.py:337-341`), `confidence`, `model_probability`, and `evidence` continue to reflect the **pre-swap** fusion result for the old section. `final_correction.reason` can end up reading "Learned text, geometry, and structural-graph evidence disagreed..." even when the actual cause was the label ranker, not those modalities — a real provenance-misattribution risk (mitigated only partially by a separate, honest reason string also being appended).
**Affected files:** `backend/services/prediction/orchestrator.py` (L333–482).
**Impact:** latent (`ENABLED` defaults false); would surface immediately upon promotion. **P1**, blocking for `ML_LABEL_RANKER_ENABLED` promotion specifically.

### P1-4: `evaluate_pipeline.py` token-level holdout split doesn't cover the full prediction path it scores
**Root cause:** the new `assign_split(sample_id)` split (SHA-256 hash of `unknown_id`/token text) is token-string-level, not project/document-level, **and** the shadow retraining only excludes test tokens from the exact-match retrieval index — not from the family classifier / multimodal fusion models that `predict_token()` also calls into.
**Affected files:** `backend/scripts/evaluate_pipeline.py`, `backend/services/training_pipeline/preprocessing.py`.
**Impact:** reported accuracy is honest for the exact-match layer only, likely inflated by memorization elsewhere. Overlaps with and compounds P0-2.
**Priority: P1.**

### P2s (lower severity, still worth fixing)
- Dense-page geometry cap ceiling is still a flat count (`drawing_cap_threshold = 250`) even under the new length-aware *ranking* strategy — a sufficiently dense real page still drops valid geometry, just different geometry than before.
- `by_bbox.setdefault(...)` in graph node resolution silently keeps the first-inserted node on an exact-duplicate bbox+text+page collision (no test covers this).
- `graph_matches_document()` staleness check is coverage-only (new token IDs ⊆ old source-id set) — it can pass a graph whose *content* at a given ID has actually changed, not just been renumbered.
- Naming collision between `services/section_parser.py` (production) and `services/label_reconstruction/structural_parser.py` (R&D) — confusing, not functionally broken.
- `checkpoint["node_kinds"]` is recorded in the GraphSAGE checkpoint format but never read back — no equivalent reconciliation exists for node-feature schema drift the way there is for edge relations.
- **New React/MUI console warnings on the new Drawing Review page** (see §16) — a direct regression against the earlier `ef6f71b` commit that specifically fixed this class of warning.

---

## 8. Feature-Flag Safety Audit

| Flag | Default | Verified effect when true (alone) |
|---|---|---|
| `ML_LABEL_RANKER_SHADOW` | `false` | Runs `reconstruct()` per token, logs to `label_reconstruction_shadow_log.jsonl`; **prediction unchanged**. Adds latency + the P1-2 exception risk. |
| `ML_LABEL_RANKER_ENABLED` | `false` | Hook still gated on `shadow OR enabled`, so this alone triggers `reconstruct()`. Can replace `section` when `reason=="learned_ranker_top_candidate"`; confidence/evidence become stale (P1-3). |
| `ML_ASSOCIATION_DATASET_ENABLED` | `false` | Gates `ml_association/service.py` entry points and standalone scripts only. Zero hits in `prediction/` or `staged_pipeline.py`. No live-prediction interaction. |
| `LEARNED_FUSION_ENABLED` | `true` (pre-existing) | Independent axis; gates `multimodal_fusion.pt` override. No interaction found with the other three flags. |

No combination of these four flags was found to activate `ml_association` or `spatial_index` code in the live analyze path. Isolation holds across the full interaction matrix.

## 9. Label-Ranker Shadow Audit

See §7 (P1-2, P1-3) for the two real findings. Full call trace: `routers/documents.py` → `orchestrator.predict_from_context` → `label_ranker_hook.apply_label_ranker_for_analyze` → `label_reconstruction/shadow.reconstruct` → `candidates.generate_candidates` (catalog-filtered) → `ranker.get_active_ranker().score()` → shadow JSONL log → `meta` dict → orchestrator. Both-flags-off is a genuine zero-cost no-op (two bool checks, verified by test). Shadow-only never changes the live prediction (verified by test). Enabled path is catalog-constrained by construction but has the two P1 issues above.

## 10. Graph Evidence Audit

Traced end-to-end and **verified real**, not a UI-string fix: `structural_graph.py` (producer of `source_node`/`node_kind`/`graph_available`) → `feature_providers.py::GraphFeatureProvider` → `orchestrator.py` (`graph_evidence` dict, `available["graph"]` computed from four independent truthy signals) → `explanation_engine.py` → `contract.py` (unmodified pass-through) → `predictionContract.js` / `PredictionExplainability.jsx`. A dedicated regression test traces one token ID through the whole chain and passes. **Live-confirmed in the smoke test** (§16): graph evidence scores actively swung a real prediction.

## 11. Stale Graph Audit

1. **Detection mechanism:** coverage-only — `graph_matches_document()` checks that every current token ID is a subset of the cached graph's source-id set. **No content fingerprint/hash/version field exists anywhere** (`extraction_run_id` etc. — zero hits).
2. **Could a stale graph pass?** Yes — if re-extraction changes token count/order such that new IDs remain a subset of the old ID space, content can silently differ while the check passes. Not covered by any test.
3. **Duplicate identical labels:** handled conservatively — ambiguous `(page, text)` matches return `unresolved` rather than guessing.
4. **Bbox tolerance:** none — exact match on coordinates rounded to 1 decimal. Sub-0.05-unit drift fails *safe* (falls to text-only or unresolved), not *wrong*.
5. **Determinism:** yes at the algorithm level (fixed candidate-priority order, sha1-based deterministic node IDs) — **undermined** by the P1-1 concurrency race at the cache layer.
6. **Rebuild updates metadata:** functionally yes (overwrites `graph.json`), but with no explicit version bump — correctness depends entirely on the (unsound) coverage check.
7. **Concurrency:** a real, new bug (P1-1) — not one Ismail's report mentions.

**Recommendation (not implemented):** replace the coverage-based check with a content fingerprint (sha1 over sorted `(token_id, text, bbox)` tuples) stored in `graph["extraction_fingerprint"]`; make the `GraphFeatureProvider` lookup cache request-scoped instead of a shared singleton, or lock the check-and-set.

## 12. Node-Kind / Role Semantic Audit

Genuine partial fix. `rule_engine.py::_infer_role()` (context/orientation-based) and `structural_graph.py::_semantic_kind()` (no family patterns) are real, defensible fixes. **But**: `graph_builder.py::_FAMILY_NODE_KIND` still hard-codes W/S/M→beam, HP→column (P1, §7); and — far more seriously — `neural_dataset.py`'s training-label generator (P0-3, §7) reintroduces and *widens* the shortcut for HSS/PIPE/L specifically for the ambiguous-orientation (diagonal) members that most need correct labels. Test coverage for the claimed decoupling is weak: the one existing test (`test_wide_flange_and_plate_keep_their_roles`) actually *codifies* the family shortcut for W/HP as expected behavior rather than testing true context-based decoupling, and `rule_engine.py::_infer_role` — the one place doing it right — has **zero** test coverage. **Live-confirmed in the smoke test**: extraction output showed `HSS10x10 · column` for some tokens and `HSS8x8 · column_or_brace` for others in the same document — visibly inconsistent role assignment for the same shape family, exactly matching this finding.

## 13. GraphSAGE Checkpoint / Schema Audit

**No `.pt` checkpoint exists in git for either branch** — this is a static-code audit, not a certified-artifact audit. Findings:
- Training (`graph_ai.py::train_graphsage`) and inference (`enrich_graph_embeddings`) call the **identical** `_node_features()`/`_edge_tensors()` functions in the same file — the classic "two schemas silently diverge" failure mode cannot occur here by construction.
- `same_tag` was added to `EDGE_RELATIONS` correctly; checkpoint loading reads `input_dim`/`hidden_dim`/`edge_relations` from the checkpoint *before* building the model, so shape mismatches raise a clean, caught `RuntimeError` → `graph_ai.available=False`, not silent corruption. A legacy relation-count → vocabulary fallback exists for pre-`same_tag` checkpoints and was verified byte-for-byte order-correct.
- **Gap (P2):** `checkpoint["node_kinds"]` is saved but never read back — no equivalent reconciliation exists for node-feature schema drift, unlike the edge-relation handling. A future `NODE_KINDS` change would throw *outside* the guarded `_load_runtime()` block (loud crash, not silent — acceptable but should be hardened symmetrically).
- **Role-label contamination (P0-3, detailed in §7)** means any checkpoint trained under current code — regardless of the `same_tag` fix's correctness — should be treated as carrying residual role mislabeling for diagonal/ambiguous-orientation members.

**Verdict: NEEDS RETRAINING** — not because the `same_tag` fix is broken (it isn't), but because (a) no certified checkpoint exists to audit, and (b) the label pipeline that would produce one is still contaminated for diagonal braces until `_infer_role`/`_member_role`'s fallback is fixed.

## 14. Spatial-Index Audit

Confirmed experimental and correctly isolated (§5, §7). `graph_builder.py`'s actual candidate generation (list-order window, cap 60/12) is unchanged; `spatial_index.py` exists to *measure* the gap versus a real STRtree via its own `coverage_report()`/`legacy_windowed_pairs()` methods, not to silently replace anything. `feature_flags_status.py`'s self-description of "used by" is accurate but incomplete (omits `ml_association/feature_builder.py` as a second real consumer).

**Proposed evaluation plan** (not implemented) to compare spatial_index vs. graph_builder candidate generation:
- **True association recall**: requires a human-reviewed ground-truth (label, geometry) set — none exists yet beyond synthetic test fixtures; the `ml_association` review-kit is the only mechanism that could produce one.
- **Candidate count / false-candidate rate**: run `generate_spatial_candidates()` across a real document corpus; manually audit the `_is_area_shaped` border-exclusion heuristic (`width/height > max_distance*4`) for false rejections of large valid built-up members.
- **Isolated-node rate**: sensitivity sweep on `max_distance` (80/160/320).
- **Dense-page behavior**: extend beyond the synthetic 150-node/radius-80 test case using the real 200+-label pages the `ml_association` pilot docstring references.
- **Latency/memory**: STRtree is O(n log n) unbounded by page geometry count; the legacy loop has a hard `window_cap=60` — profile both on the largest real page found.

## 15. Association Dataset Audit

`ML_ASSOCIATION_DATASET_ENABLED` correctly gates only `ml_association/service.py` entry points and standalone scripts — zero hits in the live prediction path. Schema (`schemas.py`) covers most of the required fields (project/page/bbox/text/geometry/distance/orientation/leader/graph relations/candidate rank/review label/provenance), but two declared fields are dead: `normalized_text` and `parsed_family` are always `None` at the one call site that populates them (`candidate_dataset.py:336,341`) — honestly commented as not-yet-implemented, but still a real gap against the requested schema. **The offline review loop is real but incomplete**: `build_ml_association_review_kit.py` → manual local HTML review → `import_review_decisions.py` → `outcome_store.append_outcome()` genuinely works and was traced end-to-end, but **no training script anywhere consumes the resulting `ReviewedOutcome`/outcomes JSONL** — the pipeline terminates at a file, not a model. There is also no app-UI "approve" path into this system at all (zero hits for `ml_association` in any router or frontend file) — it is purely an offline researcher tool today, which should be stated plainly rather than implied to be integrated with the review queue.

## 16. UI / End-to-End Smoke Test Results

Performed against the `accuracy-merge` worktree with a real backend (`uvicorn`, `.venv_partner_review` + missing deps installed) and real frontend (`npm ci` + `vite`), using a real 23-page structural drawing (`ST_sample.pdf`, uploaded as `doc_0bfc2d61245dbce2` — a document ID that already had prior cached artifacts, making this an incidental re-extraction/stale-graph test).

1. **Results loads without console errors** — ✅ confirmed, no errors on Dashboard/Upload/Extract/Analyze/Results.
2. **Drawing Review loads** — ✅ loads, locates and highlights sections by page/bbox correctly.
3. **Graph evidence is no longer universally unavailable** — ✅ confirmed live: a real prediction's outcome was determined in part by a 90%-vs-53% graph-evidence gap between two candidates.
4. **Inferred/text evidence display** — ✅ correct (`OCR: W16x26 → W16X26` shown alongside evidence breakdown).
5. **Clean labels still render correctly** — ⚠️ **partially fails**: several instances of a clean, 100%-text-match candidate (`W16X26`) being overridden to a different, lower-text-evidence candidate (`W14X22`) at Low/20% confidence — a live instance of P0-1/P1-3's behavior, not merely a theoretical risk.
6. **Unresolved labels clearly marked** — the UI does show `Low` confidence and `FAIL` validation tags and an explicit "near-tied" review note, so the system is *honest* about uncertainty even where it shouldn't have overridden in the first place.
7. **Legacy analyses / missing-source-PDF / page-refresh rehydration** — refresh-rehydration spot-checked and works (577 sections reloaded correctly after a hard navigation). Legacy-analysis and missing-PDF paths were not exercised in this pass due to time; recommend as a follow-up smoke test.
8. **New React/MUI warnings** — ❌ **regression confirmed**. The new Drawing Review page (`DrawingReviewPage.jsx`, `SectionResultsList.jsx`) throws 4 distinct React console warnings: `alignItems`/`InputProps`/`secondaryTypographyProps` MUI v4-style props being forwarded to raw DOM elements, plus an invalid `<div>`-inside-`<p>` DOM nesting from a `Chip` rendered inside a `ListItemText` secondary slot. This is a direct regression against commit `ef6f71b` ("fix(ui): handle legacy analyses and remove MUI prop warnings"), which specifically eliminated this class of warning elsewhere in the app.

**Extraction-stage confirmation of §12's finding:** the "Detected structural labels" view on the Extract page showed `HSS10x10 · column` and `HSS8x8 · column_or_brace` for shapes of the same family within the same document — visible, live evidence of the inconsistent family→role handling described in §7/§12.

## 17. Test-Suite Results

Discovered via `README.md`: `cd backend && python -m venv venv && pip install -r requirements.txt -r requirements-dev.txt && pytest`. Ran the full backend suite against the `accuracy-merge` worktree (needed to supplement a working Python environment with `pytest`, `shapely`, `xgboost`, `httpx2` — a copied venv was tried first but broke numpy's DLL loading on Windows, a known pitfall; the original working venv was used instead with the missing packages added).

**Result: 303 passed, 2 failed, 1 skipped, 1 warning, 20 subtests passed** (283s).

Both failures are real regressions, not flaky/environmental:

1. `test_exact_section_predictor.py::ApprovedIngestionTests::test_approved_rows_use_exact_token_as_target` — `AttributeError: type object 'FakeSettings' has no attribute 'engineering_corrections_path'`. The new "engineering corrections become retrieval anchors" feature (`exact_section_predictor.py:211`) references a settings attribute the test's `FakeSettings` fixture was never updated to include — the test suite fell out of sync with a source change in this branch.
2. `test_prediction_orchestrator.py::ContractSerializerTests::test_aliases_and_policy_flags` — `AssertionError: 'reasoning' unexpectedly found`. The canonical contract now includes a `reasoning` alias key that a pre-existing test explicitly asserts should **not** be present (`assertNotIn("reasoning", payload)`). Either the alias was added deliberately without updating this test, or it's an accidental duplication of `explanation`/`reasoning` — either way, the canonical-contract stability guarantee from the README ("Review Queue, Validation, and Prediction Details render the same canonical explainability contract") has a live, test-confirmed inconsistency.

Also observed (not a failure): an xgboost `UserWarning` on model unpickling, recommending the model be re-exported with `Booster.save_model` for the current xgboost version rather than loaded via legacy pickle — worth doing before any model is promoted to avoid future version-compatibility surprises.

**Frontend tests** were not run in this pass (Vitest is configured in `vite.config.js` but was not exercised) — recommend as a follow-up.

## 18. Current ML vs. Rule-Based Architecture

| Component | Purpose | Status | Training data | Metric | Weakness |
|---|---|---|---|---|---|
| Family classifier (`best_model.pkl`, XGBoost) | 45-class shape+material family | **Production, real ML** | 31,273 rows (16k used) | none published in metadata | mixes shape-family and material-grade classes |
| Exact-section predictor (`exact_section_model.joblib`) | TF-IDF + cosine retrieval, 2,299 labels | **Production, real ML (retrieval)** | 60,325 rows | none published | zero stored performance metrics |
| Label-reconstruction ranker (xgb/ubj, 4 versions) | Learned re-ranking of corrupted-label candidates | **Real ML, but inert** — `active_version: null`, never promoted, shadow never run (no log file exists) | 94–98k rows | val NDCG@10 up to 0.976 | fully unmeasured against real disagreement rate |
| Calibration (isotonic regression) | Maps ranking_score → correctness | **Built but dormant** — `fit_calibration()` always returns `None`; required training columns don't exist yet in `approved_dataset.csv` | would use approved_dataset.csv | n/a — never fits | `confidence_is_calibrated=False` always; **the Drawing Review UI's "Calibrated confidence" label is misleading given this** (see note below) |
| Wildcard/mask matcher | Masked token resolution | Production, rule-based | none | deterministic | can't handle wrong (not missing) characters |
| Structural graph + entity typing | Spatial graph, semantic node typing | Production, rule-based (regex + geometry thresholds) | none | none | regex keyword typing misclassifies non-standard vocabulary |
| GraphSAGE | Graph-embedding role/context model | **No certified checkpoint in either branch**; code correctly implemented, training-label pipeline contaminated (§7 P0-3) | would use neural_dataset.py output | none available | needs retraining once label pipeline is fixed |
| Association dataset | Label↔geometry association data collection | Experimental, flag OFF, no trained model behind it, no training consumer of reviewed outcomes | n/a | n/a | data-collection harness only |
| Multimodal fusion "attention" | Combines modality confidence scores | Production | none — hand-set constants | n/a | **not learned** — `ATTENTION_PRIORS` are hardcoded (text 0.32, geometry 0.30, graph 0.17, ocr/layout 0.08, engineering_rules 0.05) despite the "attention" name |

**Note on the "Calibrated confidence" UI label**: the smoke test's prediction-detail modal displayed `CALIBRATED CONFIDENCE: Low · 97%` for the `W16x26`→`W14X22` example. Per the dataset-inventory audit, the isotonic calibration model **never actually fits** in this environment (missing training columns). This 97% figure is very likely a different internal fusion/temperature-scaling number being surfaced under a "calibrated" label it hasn't earned — a live instance of exactly the "confidence not falsely presented as calibrated probability" risk this audit was asked to check. **Recommend tracing this specific UI field to its source before trusting it in any reviewer-facing context.**

### What is actually machine learning today?
Family classifier (XGBoost), exact-section retrieval (fitted TF-IDF + cosine), and the label-reconstruction ranker (XGBoost/XGBRanker, real metrics) — the last one currently inert/unpromoted. Calibration is a real, correctly-implemented sklearn model that has never once fit on real data.

### What is still rule-based, despite ML-sounding names?
Wildcard matcher, dynamic regex knowledge base ("learning" = appending regex strings, not fitting parameters), structural graph + entity typing (100% regex/geometry thresholds), geometry extraction (PyMuPDF + hand-written heuristics, no embeddings), the `train_geometry_model`/`train_graph_model` placeholder stubs (literally hardcode `accuracy: 0.5` and self-reject), GraphSAGE (no certified checkpoint exists), and — most notably — **multimodal fusion "attention,"** which is a hand-tuned weighted-scoring function, not a trained attention mechanism.

## 19. Existing Dataset Inventory

(Inventoried from Bassam's local, fully-checked-out `bb3d67c` branch, which has real on-disk data; cross-referenced against the accuracy-merge branch's file list.)

- `backend/training/datasets/{engineering,fusion,geometry,graph,layout,ocr,text}/` — **all empty**, scaffolding only.
- `backend/training/datasets/label_reconstruction/` — the only populated dataset dir: two 97,740-row sample sets, `pairwise_v3_train_val.jsonl` (94,626 rows), and `frozen_test_analysis.jsonl` (2,772 rows) — **the only true frozen-eval artifact in the repo**.
- `backend/training/models/{engineering,exact_section,family_classifier,fusion,geometry,graph,layout,ocr}/` — all empty except `label_reconstruction/` (4 trained rankers). Legacy top-level artifacts (`best_model.pkl`, `exact_section_model.joblib`, etc.) live **outside** the registry structure entirely — a path-consistency issue worth fixing before any promotion tooling depends on the registry.
- `label_reconstruction_shadow_log.jsonl` — **does not exist on disk**; shadow mode has never been run in this environment.
- `backend/training/engineering_artifacts/` — 6 real cached document graphs (document/geometry/graph/predictions/validation JSON), tens of MB each. One validation summary showed 872 tokens at **0% "pass" rate** (806 warning, 66 fail) — worth investigating separately as its own signal.
- 7 real sample structural PDFs available for smoke/benchmark testing (`backend/training/pdf/`), several with matching Excel takeoff workbooks for ground-truth comparison.
- `models/label_reconstruction/registry.json` → `"active_version": null` — **all four trained rankers are unpromoted candidates**, explicitly noted "shadow-mode only" in their own metadata.

## 20. Proposed Graph / Association Dataset

Purpose: learn text↔member association and structural context, kept **separate** from section-designation classification. Proposed schema (superset of what `ml_association/schemas.py` already has, closing the two dead fields found in §15):

`project_id, sheet_id, page, source_extraction_run_id, text_node_id, text_bbox, raw_text, normalized_text (actually populated), geometry_node_id, geometry_bbox, centroid_distance, bbox_distance, relative_orientation, leader_support_evidence, same_region_flag, graph_neighbor_ids, node_kind, candidate_set (with each candidate's generator-time rank, not just the current production heuristic's rank), association_truth (positive/negative), role_truth, section_truth, review_provenance, pipeline_version, candidate_generator_version.`

**Negative sampling**: prefer hard negatives — nearby-but-wrong geometry (similar distance/orientation to the true match), same-family-different-instance labels on the same page, and stale/near-duplicate bbox collisions — over uniformly random wrong pairs, since those are the cases this audit found the current heuristic actually struggles with (§10, §6 first-real-match scenarios).

**Metrics**: Association — Recall@1/3/5, MRR, candidate coverage. Graph construction — true-edge recall, false-edge rate, isolated-node rate, graph coverage. Role — macro F1, per-class precision/recall, confusion matrix (with explicit tracking of family-vs-role confusion, given §7 P0-3/P1-4).

## 21. Proposed Geometry Dataset

Purpose: recover structural members from raw PDF/CAD primitives, preserving raw primitives *and* ground-truth grouping (e.g. `line_1, line_2, line_3 → member_17`).

Fields: `project, sheet, page, primitive_id, path_syntax, bbox, length, orientation, line_width, closed/open, gap_distance, collinearity, intersection_count, parallel_neighbor_count, text_proximity, grid_proximity, hatch_proximity, scale, page_region, member_group_id, structural/nonstructural_truth, member_axis_truth, member_role`.

Prioritize hard cases the audit's own findings point to: fragmented CAD lines, dense pages (§7 P2 — the 250-item flat cap), thin/long members, HSS/channels/angles/tees specifically (§7 P0-3/P1-4's role-confusion families), grid lines, hatches, leaders, repeated parallel linework, and detail sheets.

Metrics: structural primitive recall, nonstructural rejection precision, fragment-merge precision/recall, member-axis recovery, dense-page retention, thin-member retention, candidate coverage, page latency.

## 22. Evaluation Metrics (Summary)

See §20/§21 for per-dataset metric lists. Overarching principle established by this audit's findings: **every metric must be reported alongside its split methodology**, because two of the P0/P1 bugs found (§7 #2, #7 P1-4) are specifically "the metric looked honest but wasn't" failures, not missing metrics.

## 23. Data Leakage / Holdout Risks

1. **P0-2 (§7)**: exact-section holdout evaluation discards its leakage-free shadow model before scoring — the headline bug of this category.
2. **P1-4 (§7)**: even where a split exists, it's token-string-level, not project/document-level, and doesn't cover the full prediction path (family classifier / fusion) that gets scored against it.
3. **Verified safe**: `generate_label_corruption_dataset.py`'s split (dedup by raw corrupted string before split assignment, reserved-combination test set) — sound, and its negative-reuse design choice is explicitly and correctly justified in-code for a closed-catalog task.
4. **Verified safe**: `train_label_ranker*.py` scripts consume the pre-assigned split with no independent re-splitting logic.
5. **Approve-flow / eval-split conflict (§7 P0-1 related — see full detail under the Phase A findings)**: `dataset_manager.py::review_token` immediately anchors every approved token into the live production retrieval index (`train_exact_section_model(persist=True)`, no `exclude_split`), even when that same token's `eval_split` is `"test"` — meaning a human approval can retroactively contaminate what's supposed to be held-out data.

**Recommendation**: all future ML evaluation work in this codebase should split by **project ID**, not by token/row, and any "shadow"/leakage-free artifact must be scored *before* the production cache is reloaded — the exact ordering bug in P0-2 should become a permanent code-review checklist item for this codebase specifically.

## 24. Recommended Gold Benchmark

Small, targeted — not exhaustive labeling. Categories, each project-split (never randomly split):

clean W labels · clean HSS labels · C/MC · L · WT/ST/MT · damaged OCR · partial labels · repeated labels (the exact `W16X26`-style near-tied scenario hit live in this audit) · leader-based association · missing labels · geometry-only cases · fragmented members · dense pages · detail sheets · **diagonal/brace-orientation members specifically** (added based on this audit's §7 P0-3 finding — this category doesn't appear in the original brief but is now the single highest-value annotation target given what was found).

Synthetic data (the existing corruption generator) may augment training but should never be the final readiness gate — use it for volume, use the gold set for go/no-go decisions.

## 25. Prioritized Next Steps

1. Fix the P0-2 holdout-discard bug in `evaluate_pipeline.py` (one-line ordering fix: score before reload) — this is currently making every exact-section accuracy number in the repo untrustworthy.
2. Fix the P0-1 catalog-bypass fallback in `orchestrator.py::_gated_exact_override()` — require actual `lookup_shape()` catalog membership, not just regex-format validity, before returning any section without the primary confidence gate.
3. Fix `rule_engine.py::_infer_role`'s `"bolt"/"member"` fallback for diagonal-orientation members so `neural_dataset.py::_member_role` stops family-shortcutting HSS/PIPE/L braces (P0-3) — this blocks any honest GraphSAGE retraining.
4. Add exception handling around the label-ranker shadow/enabled call path (P1-2) before anyone flips `ML_LABEL_RANKER_SHADOW` in any environment.
5. Trace and fix (or relabel) the "Calibrated confidence" field shown in the Drawing Review UI — it is being populated by something other than the isotonic calibration model, which never fits in this environment.

Also worth queuing soon (not blocking): fix the two failing tests (§17) to keep the suite honest; fix the new MUI console warnings on Drawing Review (§16); harden `GraphFeatureProvider`'s cache to be request-scoped (P1-1); replace the coverage-only stale-graph check with a real content fingerprint (§11).

## 26. Production Promotion Gates

**Label ranker** — before `ML_LABEL_RANKER_ENABLED=true` anywhere outside a controlled test: fix P1-2 (exception safety) and P1-3 (confidence/evidence provenance) first; then require disagreement rate, win rate on double-reviewed gold, clean-label regression rate (this audit found a live clean-label regression risk — the `W16X26` case — so this gate is not optional), top-1/top-k accuracy, and honest abstain behavior, all measured on a **project-split** holdout, not the currently-broken evaluation path.

**GraphSAGE** — do not promote or even shadow-run against production traffic until `_infer_role`/`_member_role`'s family-fallback for diagonal/ambiguous members is fixed and the model is retrained on clean labels (P0-3). Then require macro F1 by role, measured improvement over a non-GNN baseline, no shape-family leakage (explicitly re-test the HSS/L/diagonal cases found live in this audit), and stable checkpoint/schema compatibility (already largely proven safe in §13).

**Spatial index** — promote only after the evaluation plan in §14 shows candidate recall ≥ current `graph_builder` approach, ideally better hard-case (dense page) recall, bounded candidate explosion, and acceptable latency at the largest real page size found in the corpus.

**Learned fusion** — compare with/without on the same untouched project-level holdout; no model should be promoted for performing well only on its own training examples.

No experimental system audited here currently clears its gate. All should remain in shadow/experimental status.

---

*This report reflects the repository state at commit `1c670b7` (`origin/accuracy-merge-bassam-phase-ab`) and `bb3d67c` (`bassam/rnd-geometry-ml-foundations`), audited 2026-08-10. No code was modified, no flags were enabled, no branches were merged, and nothing was committed or pushed as part of this audit.*
