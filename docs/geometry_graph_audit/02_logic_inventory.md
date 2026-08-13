# 02 — Complete Logic and Algorithm Inventory

This is the exhaustive inventory requested in Phase 2, organized A–H. Categories **C (Geometry)** and **E (Graph)** are covered in full depth in `03_geometry_audit.md` and `04_graph_audit.md` respectively — this file summarizes them with pointers and focuses its detail on A, B, D, F, G, H. The full flat list with file/line/type/status columns is in `algorithm_registry.csv`.

Legend for **type**: `D`=deterministic rule-based, `H`=heuristic (hand-tuned weights over deterministic features), `S`=statistical/retrieval (fit on data but not a discriminative classifier), `ML`=trained discriminative/probabilistic model. Legend for **status**: `LIVE`=reachable from a router/live pipeline, `DEAD`=only reachable from tests, `LEGACY`=explicitly self-documented as transitional/scheduled for removal.

## A. Document and page logic

| Logic | File:function | Type | Status |
|---|---|---|---|
| PDF validation (header, page count) | `document_registry.py validate_pdf()` | D | LIVE |
| Defensive page iteration (skip unreadable pages) | `pdf_pages.py iter_pdf_pages()` | D | LIVE |
| Page text extraction | `pdf_parser.py _extract_page_text_objects()` | D | LIVE |
| OCG/layer name capture (document-level only) | `pdf_parser.py _layer_names()` | D | LIVE |
| Text-word/line/block neighbor indexing | `pdf_parser.py _attach_neighbors()` / `_attach_word_neighbors()` | D | LIVE |
| Text span rotation | `pdf_parser.py _span_rotation()` | D | LIVE |
| CAD (.dwg/.dxf/.3dm) adapter | `geometry_adapters.py DeferredCadAdapter` | D | **Unreachable** — upload only accepts `.pdf`; always raises `NotImplementedError` |
| Scale/DPI detection | **Not implemented anywhere** | — | — |
| Coordinate-system/rotation compensation | **Not verified as implemented**; `page.rotation` captured for metadata only | — | Unverified |
| Cropping/rotation/page transforms | **Not implemented** | — | — |

## B. Text and label logic

Full detail (regex tables, similarity formulas, ML-vs-rule verification) in the research underlying this audit; summarized here.

| Logic | File:function | Type | Status |
|---|---|---|---|
| "Conservative" normalization (whitespace/case/unicode only, no OCR guessing) | `normalization.py normalize_label_text()` | D | LIVE — drives UI match-status only |
| Section-canonicalization normalizer (phrase substitution, dash/underscore stripping) | `exact_section_predictor.py normalize_section_text()` | D | LIVE |
| Catalog-index normalizer (spaces only) | `database_loader.py` (module-level) | D | LIVE |
| Wildcard-query normalizer | `wildcard_matcher.py` (inline) | D | LIVE |
| Feature-pipeline normalizer | `feature_extractor.py normalize_token()` | D | LIVE (feeds trained classifier) |
| Correction-engine fold normalizer | `correction_engine.py _fold_text()` | D | LIVE |
| **5–7 independent normalizers coexist with different whitespace/dash/phrase rules — no shared canonical form.** | multiple | D | Flag: maintainability risk, not currently a correctness bug |
| One-directional OCR-substitution variant generation (training-time only) | `exact_section_predictor.py _ocr_variants()` | D | LIVE, training-time only — **not applied at inference** |
| Steel-family prefix list | duplicated **7×** across `wildcard_matcher.py`, `entity_taxonomy.py` (×2), `feature_extractor.py`, `data_augmentation.py`, `exact_section_predictor.py`, `correction_engine.py` | D | LIVE, consistent today, fragile to change |
| Family/size/wildcard token split | `wildcard_matcher.py _split_family()` | D | LIVE — longest-prefix-first, family segment itself can never contain a wildcard |
| Positional-mask wildcard matching | `wildcard_matcher.py _mask_pattern()`, `match_wildcard_mask()` | D | LIVE — fixed-length mask, full linear catalog scan, no index |
| Character TF-IDF cosine retrieval (exact-section candidates) | `exact_section_predictor.py` (`TfidfVectorizer`, char n-grams 2-6) | S | LIVE — the primary exact-label engine |
| Rerank formula (text/rule/geometry/graph blend) | `exact_section_predictor.py _score_candidates()` | H | LIVE |
| Fuzzy catalog similarity (verification only, never overrides prediction) | `database_loader.py search_similar_shapes()` (difflib) | H | LIVE, verification-only |
| Correction/OCR-suggestion engine (6-signal weighted blend) | `correction_engine.py correct()` | H | LIVE |
| Family classifier | `model_predictor.py predict_with_confidence()` (RF/SVM/XGBoost/LightGBM, model-selected in training) | **ML** | LIVE — the only place `predict_proba` produces a genuine model probability |
| "Dynamic regex learning" engine (segmentation, trie-merge generalization) | `regex_learning_engine.py learn_regex()` | D | LIVE — **rule-based string induction, not a trained model**, despite the name |
| Regex confidence scoring | `regex_learning_engine.py _variant_confidence()`, `regex_validator.py validate_regex()` | H | LIVE — hand-tuned linear formulas, capped at 0.97, never a probability |
| Regex knowledge-base upsert | `regex_knowledge_base.py learn_and_upsert()` | H | LIVE |
| Self-learning orchestration state machine | `self_learning_engine.py process_token()` | D | LIVE |
| Invalid-label gate | `exact_section_predictor.py is_exact_section_label()` (regex) | D | LIVE — one alternative branch (`-` in char class) is dead given upstream normalization always strips `-` first |
| Legacy artifact fallback (`legacy_tfidf` mode) | `model_predictor.py reload_model()` | D | LEGACY — auto-detected by file presence, not a flag |
| Legacy contract field aliasing | `services/prediction/contract.py apply_legacy_aliases()` | D | LEGACY — self-documented "marked for removal once frontend fully consumes canonical contract" |

**Duplication flags**: token-structure segmentation (`ALPHA`/`NUM`/`SEP` run classification) is independently reimplemented in `feature_extractor._regex_signature()` and `regex_learning_engine.segment_token()`/`token_signature()` for two different downstream consumers, with no shared code.

## C. Geometry logic

See `03_geometry_audit.md` for the full audit (representation per stage, tolerance table, spatial-index inventory, weaknesses table). One-line summary: geometry classification is purely path-syntax/size-based (no structural semantics), no scale/unit normalization exists, no line-merging exists, and a dense-page drawing cap has a sorting bug that preferentially drops orthogonal structural lines.

## D. Spatial and association logic

Covered jointly across `03_geometry_audit.md` §9–10 (indexes, O(n²) sites) and `04_graph_audit.md` §4 (nearest-neighbor/association mechanics, one-to-one vs. one-to-many, leader handling, conflict resolution). Key facts, consolidated here per the audit's requested category:

- **Nearest-neighbor search**: uniform-grid bucket hash, 4 independently-tuned instances (radii 48/120/160/180pt) plus a third independent nearest-neighbor routine inside `GeometryFeatureProvider` that bypasses the graph entirely (`04_graph_audit.md §9`).
- **Search-radius calculation**: fixed constants, not derived from drawing scale or local point density anywhere.
- **Label-to-geometry candidate generation**: greedy single-best per node (not bipartite/Hungarian) — see `04_graph_audit.md §4`.
- **Orientation compatibility**: only used for PARALLEL/PERPENDICULAR edge classification (8° tolerance), never as a filter on nearest-neighbor selection itself.
- **Leader-line relationships**: leaders are not resolved through to their target — treated as an ordinary competing node in nearest-neighbor search (`04_graph_audit.md §4`).
- **Containment/overlap/adjacency**: bbox-based (`_intersects`/`_contains`/`_touches`), duplicated with different tolerances across `pdf_parser.py`, `graph_builder.py`.
- **Conflict resolution/tie-breaking**: none beyond incidental iteration order; no documented policy.
- **One-to-one vs. one-to-many**: per-node nearest-neighbor edges are effectively one-per-source, but many-to-one fan-in across different source nodes is unconstrained; true one-to-many exists only via unbounded pairwise relations.

## E. Graph logic

See `04_graph_audit.md` for the full audit (node/edge schema, generation mechanisms, pseudocode, worked example, dead-code map, weaknesses). One-line summary: the graph is a real but shallow (list-of-dicts, no adjacency index, non-deterministic IDs) structure whose *topology* never reaches prediction — only five scalar aggregates do — and four of its ten source files are dead code in the live path.

## F. Candidate-generation logic

| Logic | File:function | Formula / mechanism | Cap |
|---|---|---|---|
| Wildcard mask match | `wildcard_matcher.py match_wildcard_mask()` | Fixed-length positional regex mask vs. full catalog scan | limit=8 |
| Exact-section TF-IDF retrieval | `exact_section_predictor.py predict_exact_sections()` | Char 2-6-gram TF-IDF cosine, top-80 pool → best-per-shape reduction, exact-string override forces score=1.0 | limit=5 (single) / 8 (multi) |
| Fuzzy catalog similarity | `database_loader.py search_similar_shapes()` | `difflib.SequenceMatcher.ratio()` + 3-char prefix bonus (0.08), quick-ratio pre-filters | limit=5 (called with 8) |
| Correction candidates | `correction_engine.py suggest_token_corrections()` | 6-signal weighted blend (`CORRECTION_WEIGHTS`), `difflib` text similarity | limit=5 (called with 8) |
| HSS/PIPE special-casing | **None found** — family restriction is a plain `startswith()` check; no dimension-format-aware validation (e.g. HSS's WxHxT vs. PIPE's diameter+schedule) exists anywhere in the traced files | — | — |
| Recall safeguard | `prediction/ranking.py NEAR_TIE_MARGIN=0.04` | Forces `needs_review=True` when top-2 scores are within the margin | — |
| Recall gap (flagged) | `orchestrator.py` wildcard branch | If a wildcard token's family resolves via the classifier but the mask matches **zero** catalog rows, `exact_candidates` stays empty — no fallback to fuzzy retrieval in that specific branch | — |

## G. Ranking and prediction logic

| Logic | File:function | Formula |
|---|---|---|
| Per-encoder confidence (6 modalities) | `multimodal/encoders.py` | Each a small fixed-weight linear blend (weights differ per modality — text 0.55/0.25/0.15/0.05, OCR 0.70/0.20/0.10, layout 0.35/0.25/0.20/0.20, geometry 0.50/0.30/0.20, graph 0.50/0.25/0.25, engineering 0.8/0.2) |
| Attention weighting (the actual selector) | `modular_fusion.py AttentionFusion.attend()` | Softmax over `log(prior) + 0.75·log(quality)`, priors = `ATTENTION_PRIORS` (text .32/ocr .08/layout .08/geometry .30/graph .17/engineering_rules .05; **database always 0.0, never a fusion input**) |
| Candidate score (selects the winning label) | `modular_fusion.py UnifiedMultimodalFusion.predict()` | Weighted sum: `Σ attention_weight[m] × modality_score[m]` |
| Overall confidence | `modular_fusion.py ConfidenceFusion.fuse()` | `0.72×modality_confidence + 0.20×top_score + 0.08×margin` — a **second, independently fixed** weight set, not derived from `ATTENTION_PRIORS` |
| Presentation re-merge (cosmetic, not re-selecting) | `prediction/ranking.py build_ranking()` | Re-sorts fusion output + wildcard hits, `(-score, label)` tiebreak, `NEAR_TIE_MARGIN` |
| Calibration | `prediction/calibration.py calibrate_score()` | Isotonic regression, gated on `MIN_CALIBRATION_SAMPLES=50` — **structurally never fires today**: the approved-dataset schema doesn't yet record `ranking_score`/`correct` columns, so `calibrate_score()` always returns `(None, False)` in the current codebase state |
| Review-status decision | `prediction/review_policy.py decide_review_status()` | Rule chain on confidence bands (0.80/0.55), modality-conflict count (≥2), model-probability threshold (0.70); **a database miss alone never forces review**, by explicit design |
| Match-status / comparison | `prediction/canonical_contract.py determine_comparison()` | Priority chain: exact → normalized (conservative-equal) → wildcard-incomplete → corrected → unresolved/geometry-only/source-not-found |
| Reason/explanation generation | `prediction/explanation_engine.py build_explanation()` | **Templated string interpolation over already-computed numbers — not an LLM, not new scoring** |

**Is anything actually a calibrated probability?** Only `family_probability` (from the trained classifier's `predict_proba`/softmax-of-decision-function) is a genuine model probability, and even that isn't post-hoc calibrated. Every "confidence"/"score" shown to users — including the top-level `confidence.overall` on every prediction — is a heuristic weighted sum or softmax-over-fixed-priors, and the codebase's own docstrings say so explicitly (`calibration.py:4-14`). The frontend correctly labels this "RANKING SCORE (uncalibrated)" (`PredictionExplainability.jsx:270-279`) given calibration never fires in the current dataset state.

**Duplication flag**: the weighted-sum-renormalized-over-available-signals pattern is independently implemented at least 3 times with 3 different weight vectors (`exact_section_predictor._score_candidates`, `correction_engine.correct`, each `ClassicalXEncoder.encode`) — `ranking.py`'s own docstring states it was created specifically to stop this kind of scattered reimplementation, but only unifies the *final* fusion step, not the upstream candidate-scoring steps that feed it.

## H. Provenance and UI logic

| Logic | File | Behavior |
|---|---|---|
| Canonical prediction schema | `prediction/canonical_contract.py` | `source_text` (raw, never overwritten) / `prediction` (final_label, ranking_score, final_confidence, confidence_is_calibrated) / `comparison` (match_status) / `decision` (used_text/geometry/graph/engineering_rules/catalog flags) / `candidates` / `evidence` (attention-weight shares, **not** per-source match quality — a naming trap flagged below) |
| Legacy-analysis detection | `frontend/src/lib/predictionContract.js isLegacyPrediction()` | `!(result.canonical \|\| result.comparison \|\| result.source_text)` — single source of truth |
| Missing-source-file handling | `frontend/src/context/AnalysisContext.jsx` | Distinguishes a 404 (pruned source PDF) from other restore failures, distinct user-facing copy for each |
| Badge-status rules | `MatchStatusBadge.jsx` | Fixed table mirroring backend `MatchStatus` enum 1:1 by design |
| Confidence-level banding | Reimplemented **4×** independently: `confidence_engine.py` (reads `config.py` settings), `contracts.py`, `contract.py`, `predictionContract.js` (all 3 of the latter hardcode `0.80`/`0.55` literally) | A change to `config.py`'s thresholds would not propagate to 3 of 4 copies |
| Third, ad hoc confidence-reading path | `UnknownReviewPage.jsx` | Reads `row.multimodal_confidence ?? row.overall_confidence` directly, bypassing the shared `getDisplayConfidence()` helper and its calibration-awareness labeling |

**Naming-trap flag**: `canonical.evidence` (and its duplicate, `features.fusion.evidence_contributions`) represents **attention-weight allocation shares** (how much each modality was trusted this token, summing to ~1.0), not **per-modality evidence quality**. A reader could easily mistake `evidence.geometry = 0.30` for "geometry strongly supports this prediction," when it can equally mean "geometry was unavailable and got a near-default weight." This is a documentation/labeling risk worth fixing regardless of scoring-method changes.

**Raw/normalized/inferred/resolved mixing flag** (repo-wide pattern, not confined to one file): the flat prediction dict returned to the frontend places `original_token` (raw), `corrected_token` (correction-engine output), `section` (AI-resolved), and `canonical.source_text.raw/.normalized` (the "clean" canonical versions) all as sibling fields with no namespace discipline — a caller can read the wrong one with no structural signal that it's the wrong one. The codebase is self-aware of this (`apply_legacy_aliases` docstring calls it deliberate migration debt) but it is live in the current schema.

---

Full per-symbol detail (inputs/outputs/formulas/thresholds/test coverage/dead-code status) for every entry above is in `algorithm_registry.csv`.
