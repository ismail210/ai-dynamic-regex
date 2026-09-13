# Idea A/B/C Feasibility Audit — Legend Suppression, Drawing Language Profile, Family-Preserving Prediction

**Scope:** read-only architecture audit. No files modified, no models trained, no datasets or production artifacts overwritten. This document cross-checks three user ideas against the actual current codebase, tests, and — critically — a substantial body of **prior, uncommitted R&D work already sitting in this repo and a sibling worktree** that directly addresses two of the three ideas. Do not skip §A; the single most important finding of this audit is that this work has already been scoped, partly built, and adversarially verified once, and is currently at risk of being lost because none of it is committed to git.

---

## A. Current architecture relevant to these ideas

### A.0 — Repository state is fragmented across four locations. Read this first.

| Location | Branch / HEAD | What it has that others don't |
|---|---|---|
| `C:\Users\Bassam\git\ai-dynamic-regex` (**this repo**) | `bassam/rnd-geometry-ml-foundations` @ `bb3d67c` | `label_reconstruction/` (family-aware v3 parser + shadow ranker), `ml_association/`, `spatial_index.py` — all original here. **Does not have** `document_prior.py`, `context_evidence.py`, `anonymous_dimension_resolver.py`, `feet_inch_filter.py`, `extraction_noise_filter.py`, or the Drawing Language Profile prototype. Untracked: `docs/audits/*.md` (this audit's evidence base — six prior reports, uncommitted). |
| `C:\Users\Bassam\git\ai-dynamic-regex-integration` (sibling worktree) | `bassam/estima3d-integration` @ `54745c4` | Has everything the previous column lacks (`document_prior.py`, `context_evidence.py`, `anonymous_dimension_resolver.py`, `feet_inch_filter.py`, `extraction_noise_filter.py`, `review_policy.py`, `hss_review_enrichment.py` — the "3.7-extraction-quality / 4.10-context-quality" work, merged into this branch two sessions ago). Also has `label_reconstruction/` (same origin as column 1). **Does not have** the Drawing Language Profile / contextual-fabricated-steel prototype. |
| `C:\Users\Bassam\git\ai-dynamic-regex-dlp` (sibling worktree) | `bassam/drawing-language-profile` @ `999787d` | `drawing_language_profile.py`, `drawing_language_llm.py`, `contextual_fabricated_steel.py` — a working, adversarially-audited prototype of almost exactly Idea A + Idea B. **All five of these files are untracked** — never committed, never pushed, exist only on this one machine's disk. |
| `origin/main` / `origin/accuracy-merge-bassam-phase-ab` (remote, Ismail's line) | `1c670b7` | An **independent, from-scratch reimplementation** of `label_reconstruction`/`ml_association`/`spatial_index` that diverged from a common ancestor (`2911a8a`) and never incorporated Bassam's actual commits. Confirmed (`docs/audits/ismail_recent_merge_audit.md`) to contain 3 real P0 bugs: a catalog-validation bypass, a leakage-hiding evaluation bug, and hard-coded role shortcuts that got *worse* for ambiguous members. |

**This fragmentation is itself the top architectural risk in this audit** (see §H) — four lines of development have independently built overlapping capability, one has known regressions, and the most directly relevant prototype (DLP) exists nowhere in git. Any answer below about "what exists" is therefore branch-relative; each claim is tagged with which location it's true for.

### A.1 — End-to-end pipeline (common to all branches, current production path)

```
PDF upload → services/extraction_engine.extract_engineering_document()
  → PyMuPDF text/vector extraction (services/document_intelligence.py) — no OCR dependency, no VLM, no rasterization anywhere in the runtime path
  → [estima3d-integration only] attach_document_prior() — regex legend-page scorer
  → services/token_extractor.py — token span capture (section/plate/mark regex families)
  → services/engineering_object_filter.classify_engineering_object() — per-token type classification
      → fast path: _SECTION / _PLATE / _MEMBER_MARK / _CONNECTION regexes
      → fallback: services.annotation.parser.interpret_annotation() (deterministic, rule-based — confirmed no LLM anywhere in this call chain)
  → [estima3d-integration only] extraction_noise_filter.py / feet_inch_filter.py — title-block/scale-bar/grade/layout-dimension discards
  → filter_engineering_objects() — dedup, discard-count bucketing
  → engineering_tokens[] persisted on document.json

Analyze → services/multimodal/pipeline.run_multimodal_pipeline() (per document, once)
  → geometry_extractor.py / graph_builder.py — STRtree spatial index, leader-aware label→geometry linking, GraphSAGE role/confidence
  → per token: services/multimodal/fusion_engine.py → services/prediction/orchestrator.py
      → exact_section_predictor.py — fuzzy TF-IDF candidate retrieval (family-agnostic, +0.08 prefix bonus only)
      → [estima3d-integration only] context_evidence.py / anonymous_dimension_resolver.py — spatial/leader/region evidence for anonymous dimensions, hard-abstains near title blocks/layout dims
      → services/prediction/review_policy.py — decide_review_status(), determine_abstention_reason()
      → services/prediction/canonical_contract.py — build_canonical_prediction(), MatchStatus enum, needs_review gate
  → results/Drawing Review pages read canonical predictions (unchanged by this audit's scope)
```

**Where LLM/VLM calls occur:** nowhere in the production runtime path, on any branch, today. `backend/requirements.txt` has no `openai`/`anthropic`/generative-model SDK. `services/multimodal/pipeline.py:334-347` returns a hardcoded aspirational capabilities list (`LayoutLMv3`, `Donut`, `ViT`, `YOLO`, `SAM`, ...) that has zero corresponding implementation anywhere. The one exception: `ai-dynamic-regex-dlp`'s `drawing_language_llm.py` defines an `AnthropicLLMProvider` that is inert unless the `anthropic` package is installed (it is not) and `DRAWING_LANGUAGE_LLM_ENABLED` is set (default false) — confirmed via `NullLLMProvider` being the only thing that ever actually runs today.

**Where section-family parsing occurs:** `backend/services/section_parser.py::parse_section()` (production) already returns structured partial fields (family, depth, weight, thickness — `ParsedSection` dataclass) independent of catalog validity; `services/label_reconstruction/structural_parser.py::parse_fields()` (shadow-only, all branches that have it) is a far more complete per-family grammar (W/M/S/HP/C/MC/WT/MT/ST as depth+weight; HSS as 2- or 3-field rect/round; L as leg/leg/thickness; 2L with optional back-to-back separation; PIPE via dedicated regex).

**Where candidate generation occurs:** `orchestrator.py` → `exact_section_predictor.predict_exact_sections()` → `database_loader.search_similar_shapes()` — pure fuzzy text similarity over the *entire* catalog, family used only as a +0.08 prefix-match bonus, never a filter. The hard-constraint counterpart (`label_reconstruction/candidates.py::generate_candidates_v3`) exists and is proven to fix a real regression (`test_family_misroute_fix_recovers_known_regression_cases`) but is reachable only through `services.prediction.label_ranker_hook`, gated behind `ML_LABEL_RANKER_ENABLED`/`ML_LABEL_RANKER_SHADOW` (**both default false, everywhere**).

**Where confidence/abstention/human-review decisions occur:** `review_policy.py::decide_review_status()` (thresholds: `confidence_high_threshold=0.80`, `confidence_medium_threshold=0.55`, `auto_accept_probability_threshold=0.70`, all in `config.py`) plus `canonical_contract.py`'s hard structural gate — `needs_review` and "not auto-accepted" are enforced to never disagree (comment at `canonical_contract.py:364-367`). `_gated_exact_override()` in `orchestrator.py` is a proven, tested guard specifically against "confident-looking but non-existent shape" (regression test `test_high_confidence_fuzzy_candidate_still_gated_without_text_support`).

**Where Results/Drawing Review receive their data:** unchanged from prior sessions' work in this conversation — `AnalysisContext` → `predictionContract.js` → `PredictionDetailModal.jsx`/`SectionResultsList.jsx`; out of this audit's scope except to note it is stable and not touched by any of the three ideas' proposed changes.

---

## B. Feasibility of the three main ideas

### Idea A — Do not extract takeoff items from legend/general-note pages

**Verdict: possible, and already ~70% built as a working, adversarially-verified prototype (uncommitted, `ai-dynamic-regex-dlp` worktree) — but your specific framing (page-role classifier suppressing objects) is evidence-contradicted as the primary fix.**

What already exists:
- A real, quantified, 7-project empirical audit (`docs/audits/legend_aware_extraction_audit.md`) already answered "can we reliably distinguish page roles" and found the answer is **narrower than the question**: only 3.1% of plate-family hits and 5.6% of "BENT" hits in the audited corpus occur on dedicated legend/cover sheets at all. **The dominant loss mechanism is not page-role misclassification — it's a five-line regex requiring a width×length dimension pair that real thickness-only plate callouts (`3/8" BENT PL`) never have.** This is confirmed by directly executing the production classifier against real quoted PDF text, not simulated.
- A crude but real local-keyword suppression (`engineering_object_filter.py:38-42`, `_NON_OBJECT_CONTEXT` regex: `GENERAL NOTES`, `LEGEND`, `SHEET INDEX`, etc.) already exists and is confirmed working for one case (a `W27X84` legend-caption example is correctly suppressed) and confirmed failing for a near-identical one (GCDC's `"W8"=W8x10` abbreviation-table row is not suppressed, because the page's "GENERAL NOTES" heading and the row's own text sit in different OCR text blocks). This is your Idea A concern, precisely reproduced and root-caused.
- A working page-role scorer (`document_prior.py`, present only in `estima3d-integration`) already exists but currently only **boosts confidence** on candidates (+0.06/+0.03/+0.12), never suppresses. Confirmed by direct code trace: nothing connects `document_prior`'s legend-page list to `engineering_object_filter`'s suppression logic — they are two disconnected systems today, on the one branch that has both.
- A full "Context pages → profile / Active pages → extraction" separation (exactly your Idea A.B sketch) is **already implemented as a prototype**: `ai-dynamic-regex-dlp`'s `drawing_language_profile.py` produces a structured per-document profile (designation-substitution rules, vocabulary rules, page roles) from legend/notes pages, and `attach_drawing_language_profile()` runs once per document at the same extraction stage. It was adversarially audited (`docs/audits/drawing_language_profile_implementation_audit.md`) and found **safe** (project isolation rigorously proven with a deliberately-adversarial fake rule; LLM-proposed rules structurally cannot reach "trusted" status; caching keyed correctly on content hash + schema version) but **not yet demonstrated to move the needle on real anonymous-dimension inference** — 0 of 1061 real analyzed tokens in the live Burrville test produced a contextual candidate, because the geometry shape-flags (`bent`, `plate_like`, `l_shaped`) it's gated on don't exist anywhere in the production geometry pipeline yet.

What's missing:
- The regex-arity fix itself (`_PLATE`'s `{1,3}` minimum-one quantifier) is **still unfixed in all three branches**, confirmed by direct grep just now. This is the single highest-leverage, lowest-risk, zero-AI fix identified across two independent research passes (this repo's own `estima3d_rd_roadmap.md` and a second, independently-produced report cross-checked against it) and it has not shipped.
- Page-role → suppression wiring does not exist even where `document_prior.py` does (`estima3d-integration`) — it only boosts.
- A discard log (every filtered token, with reason) does not exist — silent deletion is the current failure mode, and it's currently unmeasurable in production without re-running an ad hoc scan.

**Recommended architecture:** exactly Architecture C from the existing roadmap doc (§Q, `estima3d_rd_roadmap.md`) — variable-arity grammar fix + page-role classifier + Drawing Language Profile, LLM used once per document as a bounded proposal generator whose output must be validated against the same document's real callouts before being trusted. Not a re-recommendation from this audit; a confirmation that two independently-produced research passes already converged on it and it's already ~70% built.

### Idea B — Structured LLM summary of project-specific drawing language ("Drawing Language Profile")

**Verdict: possible, and a schema-compatible prototype already exists (uncommitted) and has been adversarially safety-audited once.**

What already exists (`ai-dynamic-regex-dlp`, uncommitted):
- A profile schema close to your sketch, refined against real evidence rather than assumed: `member_size_substitutions`, `member_modifier_abbreviations`, `fabricated_plate_terms` (with a `dimension_grammar` field — a finding your sketch didn't anticipate), `bent_plate_terms`, `page_roles`, and a per-finding `evidence` array carrying `page`, `raw_text`, `interpretation`, `validated_against_actual_callouts`, `confidence` — this directly satisfies your "each finding needs source page / exact source text / confidence / validation status" requirement.
- A two-tier trust model that is exactly your stated philosophy ("LLM proposes/interprets context; deterministic systems validate anything that affects takeoff"), enforced structurally, not just by convention: `RULE_STATUS_SOURCE_VERIFIED` (explicit sentence, catalog-validated, can influence a prediction) vs. `RULE_STATUS_PROPOSED_INFERENCE` (LLM-sourced, hardcoded at the point of generation, **structurally incapable** of reaching the trusted tier — `resolve_designation()` requires `rule_status == SOURCE_VERIFIED` exactly).
- Deterministic evidence and LLM inference are already cleanly separated in the data model: `context_evidence.py` (estima3d-integration) produces a bundle where every field traces to a concrete deterministic source (bbox distance, regex match, graph edge); the DLP prototype's LLM path is entirely separate and gated behind `DRAWING_LANGUAGE_LLM_ENABLED` (default false, no SDK even installed).
- Fail-safe LLM handling already implemented and tested: provider exceptions, malformed JSON, missing fields, and a **hallucination-grounding check** (the LLM's claimed source quote must appear, whitespace-normalized, in the actual document text passed to it) all degrade to an empty rule list, never partial application.
- Verified live against a real 81-page GCDC PDF: all 8 real member-size substitution rules extracted verbatim with correct page/quote citations; a real bug was found and fixed during the audit (garbage vocabulary pairs like `EAST→west` were being promoted to the trusted tier) — i.e., this isn't a paper design, it's been through one real adversarial pass already.

What's missing:
- Per-page granularity vs. per-drawing-set — currently per-document only (one profile per PDF), not hierarchical across a multi-document project. Not evidenced as needed yet (only 1 of 7 audited projects even needed cross-document context).
- The two-column abbreviation-table layout (GCDC's actual `PL`/`LLH`/`LLV` abbreviation table) is **not parseable** by the current same-line regex — a disclosed, real gap, not a hidden one.
- Nothing in this profile is surfaced to the frontend UI yet — it exists only as a backend artifact.

**Recommended architecture:** the existing DLP prototype's shape is sound and safety-verified; the open question is not "should we build this" but "why hasn't it been committed, and what's blocking promotion of the `SOURCE_VERIFIED` designation-substitution layer (the only layer proven safe *and* proven to move a real prediction) to production behind its existing flag."

### Idea C — Preserve section family before predicting dimensions

**Verdict: the exact mechanism you're describing already exists, is well-designed, and is proven to fix a real regression — but it is fully disconnected from the live ranking path by a deliberately enforced test, on every branch that has it.**

This is the most important finding of the whole audit. `services/label_reconstruction/structural_parser.py` (present in this repo and `estima3d-integration`, absent from the DLP worktree) is, verbatim, **Strategy 1 (hard family constraint) already implemented**:

- `parse_fields()` breaks any label into `(family, grammar, fields, ok)` using AISC's real per-family grammar (not assumed — "derived empirically from `database_loader.catalog_entries()`", per the module's own docstring).
- `compatible_catalog_labels()` only ever returns catalog entries of the **same family, same grammar, same field count**, with every known (non-wildcard) field matching exactly — this is your hard constraint, field-by-field, not whole-string similarity.
- `field_generation_compatible()` handles your exact "HSS8X8X?" example: a fully-wildcarded field is treated as "illegible," a partially-known field still requires exact length — this is preserving partial information exactly as your §5 sketch describes, already shipped.
- `nearest_by_fields()` is hard-negative mining by **numeric field distance within the same family/grammar** ("same family, nearby depth" — e.g. `W18X35` → `W16X35`/`W21X35`/`W18X30`/`W18X40`), not edit distance — this is Idea C's spirit exactly.
- `ambiguity_category()` (`UNIQUE` / `SMALL_AMBIGUOUS_SET` / `LARGE_AMBIGUOUS_SET` / `NO_EXACT_STRUCTURAL_MATCH`) is functionally Strategy 4 (family-aware abstention) — a `NO_EXACT_STRUCTURAL_MATCH` on a confidently-parsed family is exactly your "do not predict W when family is confidently HSS."
- A real regression this fixed is proven by test: `test_family_misroute_fix_recovers_known_regression_cases` shows `"BW12X26"` used to get **locked into the wrong family bucket** in the older (v2) system and fail to recover `W12X26` — direct, concrete evidence cross-family leakage is a real, previously-observed bug class in this codebase, not a hypothetical you're pre-worrying about.

But: `tests/test_label_reconstruction_not_wired_into_production.py` is an explicit, enforced guard — it source-scans `orchestrator.py`, `fusion_engine.py`, `modular_fusion.py`, `staged_pipeline.py`, and every router for the literal string `label_reconstruction` and fails the build if found. The **only** sanctioned bridge is `services.prediction.label_ranker_hook`, itself gated by two flags that both default to `False` everywhere. With defaults (i.e., today, in production, on every branch), the entire family-aware v3 system runs *zero* code — not even in shadow-logging mode.

**What production actually does today, confirmed by direct trace:** `exact_section_predictor.py`'s candidate retrieval is pure fuzzy TF-IDF similarity over the whole catalog (family gets only a +0.08 prefix bonus). `orchestrator.py:561-568` has a genuine soft spot — when the primary text-seeded candidate query returns nothing, it retries using a **separately-ML-classified** `family_label` (a different model than the text parser) as the fuzzy-query seed; if that classifier disagrees with the token's literal family, a mis-keyed candidate could be generated. `modular_fusion.py::_role_compatibility()` applies only a **soft 0.45–1.0 multiplier** for beam/column/brace role plausibility, never a hard rejection. `plausible_against_ocr()` — the one place family equality is hard-enforced — gates only the narrow, high-confidence "EXACT_OVERRIDE" fast lane, not general ranking. **No `FAMILY_MISMATCH` MatchStatus exists**; a cross-family correction today is indistinguishable from any other `CORRECTED_PREDICTION`.

Comparing your four strategies against what's already built: **Strategy 1 (hard constraint) is built** (`structural_parser.py`), **Strategy 3 (hierarchical: parse then rank within family) is built** (`generate_candidates_v3` operates exactly this way), **Strategy 4 (family-aware abstention) is built** (`ambiguity_category`). **Strategy 2 (soft penalty) is what's actually live in production** (`_role_compatibility`'s multiplier, and the +0.08 prefix bonus) — the *weakest* of your four options is the one currently running, and the strongest is fully built, tested, and turned off.

**Recommended architecture:** do not rebuild this. Investigate why `label_reconstruction`/v3 has stayed shadow-only this long (accuracy not proven at scale on real documents? integration risk? simply deprioritized while other work happened?) — that answer determines whether the next step is "promote what's built" or "extend what's built and then promote." Given `structural_parser.py`'s compatibility functions are pure catalog lookups with **no ML model dependency at all**, the hard-constraint candidate-generation layer specifically could plausibly be promoted to production independent of the (separately gated, actually ML-based) ranker — this is a much smaller, lower-risk promotion than "turn on `ML_LABEL_RANKER_ENABLED`" and deserves to be evaluated as its own decision.

---

## C. Evidence from the repository

All citations below are file:line or file-name references, verified by direct reading or execution this session (not inferred from documentation), unless marked "prior audit" (verified in an earlier, still-current session and cross-checked here).

- `backend/services/engineering_object_filter.py:14-17` — `_PLATE` regex, `{1,3}` minimum-one dimension quantifier (confirmed unfixed, all three branches, direct grep this session).
- `backend/services/engineering_object_filter.py:38-42` — `_NON_OBJECT_CONTEXT` local-keyword suppression regex.
- `backend/services/engineering_object_filter.py:98-107` — `filter_engineering_objects()`, silent `None`-drop, no discard reason recorded for classification-level drops (extraction_noise_filter.py adds a separate discard-count bucket for its own checks, on `estima3d-integration` only).
- `backend/services/label_reconstruction/structural_parser.py` (full file, this session) — `parse_fields()`, `compatible_catalog_labels()`, `field_generation_compatible()`, `nearest_by_fields()`, `ambiguity_category()`.
- `backend/tests/test_label_reconstruction_not_wired_into_production.py` (full file, this session) — the isolation guard; `FeatureFlagsDisabledByDefaultTests` confirms both flags default off.
- `backend/tests/test_groupcv_and_candidate_gen.py:161` — `test_family_misroute_fix_recovers_known_regression_cases` (prior audit, `BW12X26` regression).
- `backend/config.py:186-210` — `ml_label_ranker_enabled`, `ml_label_ranker_shadow`, both default `False`; comment explicitly states "must stay false until a promoted model + review process says otherwise."
- `backend/services/prediction/label_ranker_hook.py` (full file, this session) — the sanctioned bridge, shadow/enabled semantics.
- `backend/services/prediction/orchestrator.py:561-568` (prior fork evidence) — family-classifier fallback seeding, the one confirmed soft spot in the production candidate path.
- `backend/services/multimodal/modular_fusion.py:143` (prior fork evidence) — `_role_compatibility()`, 0.45–1.0 soft multiplier.
- `backend/services/prediction/canonical_contract.py:37-52` — full `MatchStatus` enum; no `FAMILY_MISMATCH` value exists.
- `backend/services/prediction/review_policy.py:37-88, 114-172` (prior fork evidence) — `decide_review_status()`, `determine_abstention_reason()`.
- `backend/services/prediction/orchestrator.py:235-303` (prior fork evidence) — `_gated_exact_override()`, the proven guard against forced confident-wrong predictions.
- `backend/tests/test_resolution_contract.py:75-89, 202-213` (prior fork evidence) — `test_high_confidence_fuzzy_candidate_still_gated_without_text_support`, `test_high_score_ood_still_requires_review` — direct regression-test proof abstention wins over forced prediction.
- `backend/services/prediction/calibration.py` (prior fork evidence) — isotonic calibration gated at `MIN_CALIBRATION_SAMPLES = 50`; below that, confidence is honestly reported as uncalibrated (`confidence_is_calibrated: False`), never fabricated.
- `docs/audits/legend_aware_extraction_audit.md` (this repo, untracked, 426 lines) — 7-project, 262-page empirical corpus audit; direct production-code execution against real quoted PDF text.
- `docs/audits/drawing_language_profile_implementation_audit.md` (this repo, untracked, 254 lines) — adversarial verification of the DLP prototype against a real 81-page GCDC PDF and a real, freshly-analyzed 1061-token Burrville document via the live UI.
- `docs/audits/estima3d_rd_roadmap.md` (this repo, untracked, 1074 lines) — externally-researched architecture comparison (§P), recommended architecture (§Q), phased roadmap (§R), go/no-go gates (§S).
- `docs/audits/estima3d_rd_synthesis_and_final_conclusion.md` (this repo, untracked) — cross-check against a second, independently-produced research report; no material disagreement found.
- `docs/audits/ismail_recent_merge_audit.md` (this repo, untracked, excerpted) — 3 confirmed P0 bugs in the independently-reimplemented `label_reconstruction`/`ml_association` on `origin/accuracy-merge-bassam-phase-ab`.
- `C:\Users\Bassam\git\ai-dynamic-regex-dlp\backend\services\engineering\{drawing_language_profile,drawing_language_llm,contextual_fabricated_steel}.py` — confirmed present and untracked (`git status --porcelain` this session), not reachable from any branch in this repo or `estima3d-integration`.
- `backend/services/annotation/context_evidence.py`, `anonymous_dimension_resolver.py` — confirmed absent from this repo (`bb3d67c`), present in `estima3d-integration` (`54745c4`) — direct file-existence check this session.

---

## D. Additional improvement opportunities (beyond the three ideas)

- **Historical/legacy AISC shapes may leak into candidate generation unfiltered.** `services/aisc_v16_catalog.py` already scopes every entry `"modern"`/`"historical"` and exposes `entries_by_scope()`, but `database_loader.py:131` defaults to `scope=None` (all entries) unless a caller explicitly filters — no caller was confirmed to pass `scope="modern"`. If true end-to-end, a pre-1949 shape could silently outrank a modern near-match on pure text similarity with no family/era penalty at all. **Needs one targeted trace**, not a rebuild.
- **Two independent, non-shared feature-building implementations exist** for the two production ML systems: `training_service.py` (XGBoost family classifier) uses `services.feature_extractor`/`preprocessing_pipeline`; `exact_section_predictor.py` (fuzzy retrieval) builds its own inline `TfidfVectorizer` and does its own `joblib` I/O. A normalization or feature change made in one will not automatically apply to the other — a real, currently-latent train/serve-skew risk between the two systems, not yet manifested as a bug but structurally possible.
- **No detail-bubble/grid-marker/section-marker/callout-bubble suppression exists anywhere** (`grep` across `services/engineering*` for these terms: zero hits). If a grid bubble or section-cut marker ever OCRs as a valid-looking steel string, nothing currently stops it from becoming a takeoff object except the generic noise/context filters.
- **The "relationship" evidence-source label is imprecise** in `contextual_fabricated_steel.py` (DLP prototype): both real graph-topology proximity and pure nearby-text keyword matches are labeled identically `source="relationship"`, so a human reviewer cannot tell which kind of evidence they're looking at from the label alone. Disclosed but not fixed in the prior audit; a small, worthwhile fix before this evidence is trusted in a review UI.
- **The confirmed geometry dependency gap blocks the most interesting part of the contextual-candidate architecture.** `contextual_fabricated_steel.py` checks for `bent`, `l_shaped`, `plate_like`, `hss_open_end` geometry flags — **none of these keys are ever populated anywhere in the real geometry pipeline** (confirmed by direct grep of `geometry_extractor.py`/`feature_providers.py`). The architecture is proven capable (synthetic-geometry test scores `BENT_PLATE 0.66`) but has never fired on a single real token, because this one dependency doesn't exist. This is the single highest-value next R&D investment if "truly anonymous element inference" (your Idea 5/Idea C's most ambitious case) is a priority — not more scoring-rule engineering on top of a permanently-false signal.
- **Discard-log instrumentation does not exist for classification-stage drops.** `extraction_noise_filter.py` has discard-count buckets for its own checks (on `estima3d-integration`), but `engineering_object_filter.classify_engineering_object()` returning `None` (the dominant silent-deletion path per the legend audit) is not logged anywhere with a reason. This is Immediate-phase, zero-risk, and was already scoped (`estima3d_rd_roadmap.md` §R) — just not built.
- **Branch fragmentation is itself a data-quality and engineering-velocity risk.** Four divergent lines (this repo, `estima3d-integration`, the uncommitted DLP worktree, Ismail's reimplementation) have each independently touched `label_reconstruction`, `graph_builder.py`, `orchestrator.py`, and related files. A future real `git merge` between any two of these will be a large, non-trivial conflict — this was explicitly flagged as a risk in the Ismail audit and has only grown since.

---

## E. Recommended target architecture

Based on what the repository (across all four locations) actually supports today — not a redesign, a reconciliation:

```
PDF
 ↓
services.extraction_engine (unchanged)
 ↓
┌────────────────────────────────────────────────────────┐
│ document_prior.py (page scorer, estima3d-integration)  │
│   + drawing_language_profile.py (DLP worktree)          │
│   → ONE reconciled page-role + profile pass              │
│   → Drawing Language Profile artifact, persisted,        │
│     surfaced to UI, per-finding provenance already       │
│     implemented                                          │
└────────────────────────────────────────────────────────┘
 ↓
Variable-arity plate/fabricated-element grammar
 (the _PLATE regex fix — Immediate phase, unstarted)
 ↓
services.section_parser / label_reconstruction.structural_parser
 → structured PARTIAL fields (family, dims, thickness),
   already built in production (section_parser) and more
   richly in shadow (structural_parser) — PROMOTE THE
   FAMILY-COMPATIBILITY CHECK, not necessarily the full
   learned ranker
 ↓
Family-aware candidate generation
 (label_reconstruction.candidates.generate_candidates_v3 —
  built, tested, proven to fix a real regression, currently
  disconnected by an enforced isolation test)
 ↓
Candidate ranking (existing fusion/orchestrator — add a
 measured family-mismatch penalty/status if v3 promotion
 is deferred further)
 ↓
Catalog/context validation (existing — canonical_contract,
 plausible_against_ocr; extend with DrawingLanguageProfile
 project-rule resolution, already built in DLP worktree)
 ↓
Confidence + abstention (existing — review_policy.py,
 already well-tested and NOT the weak point in this system)
 ↓
Prediction OR human review (existing, unchanged)
```

The change from the user's original sketch: **almost every box already exists somewhere in this repository's four locations.** The recommended architecture is not new construction — it is (1) the one small regex fix, (2) reconciling the three branches that each have part of this, (3) deciding whether to promote the family-hard-constraint candidate layer independent of the (separately risky) learned ranker, and (4) committing and merging the DLP prototype before it's lost.

---

## F. Prioritized backlog

| Priority | Problem | Evidence in current repo | Proposed direction | Expected impact | Risk | Requires research? |
|---|---|---|---|---|---|---|
| **P0** | DLP prototype exists only as uncommitted files in a third worktree, at risk of loss | `ai-dynamic-regex-dlp`, 5 untracked files, confirmed present this session | Commit and push to a dedicated branch immediately, even before deciding on further work | Prevents losing an already-adversarially-audited, working implementation | Low — this is a save operation, not a promotion | No |
| **P0** | Plate-family regex requires width×length; real callouts are thickness-only | `engineering_object_filter.py:14-17`, confirmed unfixed via direct grep this session, root-caused via direct production-code execution against 7 real projects | Loosen `{1,3}` to allow thickness-only when a plate-family role word co-occurs; preserve the role word into a new field instead of discarding | Recovers the majority of confirmed BENT PL/CAP PL/CONN PL/BASE PL/STIFF PL/GUSSET losses — the single largest measured gap in this whole audit | Very low — deterministic, regression-testable against an existing 491-hit corpus | No |
| **P0** | Four divergent branches independently rebuilding the same subsystems, one with confirmed P0 regressions | `docs/audits/ismail_recent_merge_audit.md`; direct branch/file comparison this session | Reconcile before any new feature work — decide one canonical line, formally merge or explicitly retire the others | Prevents a much larger, harder merge conflict later; prevents shipping the confirmed catalog-validation-bypass/leakage bugs found on Ismail's line | Medium — reconciliation itself is real work, but delaying makes it strictly worse | No |
| **P1** | Silent deletion is the dominant failure mode and is currently unmeasured | `engineering_object_filter.py:98-107`, no discard reason recorded | Add a discard log: every dropped token + reason code | Turns an invisible failure mode into an auditable, regression-testable one | Very low | No |
| **P1** | Family-aware hard-constraint candidate generation is fully built and tested but fully disconnected | `label_reconstruction/`, `test_label_reconstruction_not_wired_into_production.py` | Investigate why it's still shadow-only; consider promoting the deterministic compatibility-check layer (no ML dependency) independent of the learned ranker | Directly addresses the user's central Idea C concern with code that already exists and is already proven to fix a real regression | Medium — promotion of anything behind an enforced isolation gate needs its own careful review, but the deterministic layer has no model-drift risk | Partially — need to determine why prior promotion didn't happen (accuracy? scope? just deprioritized?) |
| **P1** | Legend-page detection exists but only boosts confidence, never suppresses | `document_prior.py` (estima3d-integration only), `orchestrator.py:570-573,638-641` | Wire `document_prior`'s `legend_pages` list into `engineering_object_filter`'s suppression path, closing the confirmed LGD-002 gap | Closes the one clearly-demonstrated Idea A false-positive case (GCDC abbreviation-table row) | Low-medium — must not suppress legitimate detail-sheet content; the audit already found detail sheets are NOT legend pages, so this is a bounded change | No — the exact fix is already scoped in `estima3d_rd_roadmap.md` §R |
| **P2** | `plausible_against_ocr`/family-equality check only guards the narrow exact-override fast lane, not general ranking | `orchestrator.py`, `modular_fusion.py:143` | Add a distinct `FAMILY_MISMATCH` signal/status visible in `MatchStatus`, even before deciding on hard-filtering candidate generation | Makes a currently-invisible failure class (cross-family correction) visible and reviewable | Low | No |
| **P2** | Historical/legacy shapes may be unfiltered in candidate generation | `aisc_v16_catalog.py` scopes exist but no confirmed caller passes `scope="modern"` | Trace whether `search_similar_shapes()` ever restricts scope; if not, decide whether to default to modern-only with historical as an explicit opt-in | Prevents a rare but real wrong-era false positive | Low | Small — one targeted trace to confirm before deciding |
| **P2** | Two independent, non-shared feature-building code paths (training vs. exact-section retrieval) | `training_service.py` vs. `exact_section_predictor.py`, confirmed by import trace | Not urgent to unify, but document the divergence explicitly so future changes don't assume shared behavior | Prevents a future silent train/serve skew bug | Low | No |
| **P3** | True anonymous-element geometric inference (bent/plate-like/l-shaped shape flags) is architecturally ready but has zero real-data support | `contextual_fabricated_steel.py` reads these flags; confirmed absent from `geometry_extractor.py`/`feature_providers.py` everywhere | Do not invest further in contextual-candidate scoring rules; invest in the geometry-flag extraction itself first, if this capability is ever prioritized | Unlocks the most ambitious part of Idea A/5 (true visual-independent inference from vector geometry) | Medium — real geometry/CV engineering work | Yes — see §G |
| **P3** | "Relationship" evidence-source label conflates graph-topology and nearby-text signals | `contextual_fabricated_steel.py`, disclosed in prior audit | Split into two distinct source labels before this evidence reaches a human reviewer | Improves reviewer trust/explainability | Low | No |

---

## G. Questions requiring external research

These are gaps this audit could not resolve from code/data alone — specific to what was actually found, not generic OCR/LLM boilerplate. Numbers 1–10 are carried forward unchanged from the existing `estima3d_rd_roadmap.md` §T (produced by a prior, still-valid research pass — re-litigating them would be wasted effort); numbers 11+ are new, surfaced specifically by this session's code-level findings that the prior research passes didn't have visibility into.

1. Does GCDC's `"W8"=W8x10` substitution rule actually get used on that project's own framing plans, or is it unused boilerplate?
2. When a plate callout gives thickness only, is the fabricated width/length ever geometrically determinable from the connecting member, or genuinely open until shop drawings?
3. Is "a detail referenced N times → N takeoff candidates" correct for all fabricated-element families, or does it break for continuous conditions (e.g., a bent-plate pour stop measured in linear feet, not count)?
4. Should BENT PLATE / POUR STOP / CLOSURE ANGLE be treated as one costing role or kept distinct despite being drafted as interchangeable?
5. Is GCDC's allowed-vs-prohibited bent-plate-connection nuance a real bolted-vs-welded engineering distinction, or boilerplate inconsistency?
6. How do estimators actually price contractor-deferred connection design today (allowance %, per-connection unit, fabricator quote cycle)?
7. Are camber/shear-stud counts directly cost-relevant line items, or fabrication metadata with no independent unit cost?
8. Does the ANSI/AISC 303-22 Option 1/2/3 delegated-design framework map cleanly onto how real project notes describe connection-design responsibility?
9. Does the confirmed word-order asymmetry (`BENT` prefix on plates, suffix on HSS) generalize to other modifiers (curved, cambered, tapered)?
10. Is the GCDC-style member-size abbreviation table a common industry practice under-sampled by 7 projects, or genuinely rare/firm-specific?
11. **[New]** Given `label_reconstruction`'s v3 family-hard-constraint system has been built, tested, and proven to fix a real regression, but has stayed shadow-only through at least two more development sessions — was there ever a specific accuracy/scale finding that blocked its promotion, or has it simply never been formally evaluated for promotion? This determines whether the next step is "run the promotion evaluation" or "extend it further first."
12. **[New]** What is the actual measured accuracy of `structural_parser.py`'s family/field-compatibility candidate generation against a real (not synthetic) held-out set of OCR-corrupted or incomplete labels drawn from real project PDFs (as opposed to the `phase*.py` scripts' presumably synthetic/corruption-simulated evaluation)? The existing `scripts/phase1..phase14_*.py`/`evaluate_label_ranker.py` tooling suggests this evaluation infrastructure already exists — the open question is what its most recent results actually showed, since no result summary was found in this pass.
13. **[New]** Is there a deterministic or cheaply-detectable geometric signal (from vector path data already in hand — closed polylines, direction changes, aspect ratio) that could populate the `bent`/`l_shaped`/`plate_like` geometry flags `contextual_fabricated_steel.py` already expects, without a full CV/VLM investment? The 2026 VLM-shortcut-learning literature already cited in the existing roadmap argues against VLM for this; the open question is specifically whether *vector-geometry heuristics* (not a trained model) can close this gap, given the corpus is 100% vector/text-native.
14. **[New]** Should the four divergent development lines (this repo, `estima3d-integration`, the DLP worktree, Ismail's reimplementation) be reconciled by picking one as canonical and formally merging the others' genuinely-new work into it, or by a from-scratch architecture decision that supersedes all four? This is a project-management/engineering-process question as much as a technical one, but it blocks confident recommendation of "build X next" until resolved, since X may already exist on a branch not being actively worked from.

---

## H. What NOT to change yet

- **Do not promote `ML_LABEL_RANKER_ENABLED` or `ML_LABEL_RANKER_SHADOW` to true without first running whatever promotion evaluation exists** (`scripts/evaluate_label_ranker.py`, `compare_label_ranker_shadow.py`) against current data and reviewing the result — the flags are off for a stated, deliberate reason ("must stay false until a promoted model + review process says otherwise," `config.py` comment), and this audit found no evidence that process has run recently.
- **Do not build a new "page-role classifier" or "Drawing Language Profile" from scratch.** Both already exist as working, tested, adversarially-audited prototypes. Building a second implementation without first reading `docs/audits/legend_aware_extraction_audit.md` and `docs/audits/drawing_language_profile_implementation_audit.md` in full would waste the two sessions of work already invested and risks diverging from evidence-based conclusions those audits already reached (e.g., the corpus-measured 3.1%/5.6% legend-page share, which contradicts an "assume the first pages are legend" starting design).
- **Do not invest further in `contextual_fabricated_steel.py`'s scoring-rule logic** (more hard-negative patterns, more evidence-source types) until the underlying geometry-flag dependency is real. The architecture is proven capable in synthetic tests; more rules on top of a permanently-`False` signal will not change real-document behavior.
- **Do not merge any of the four divergent branches into another without a deliberate reconciliation pass.** The Ismail-line audit already found three confirmed P0 bugs in an independent reimplementation of the same packages this repo already has correctly-behaving originals of — a routine `git pull`/merge here risks silently reintroducing already-fixed problems or losing already-verified-safe code.
- **Do not treat this session's five-fork evidence (about `bassam/estima3d-integration`) as automatically true of this repo (`bassam/rnd-geometry-ml-foundations`).** `document_prior.py`, `context_evidence.py`, `anonymous_dimension_resolver.py`, `feet_inch_filter.py`, and `extraction_noise_filter.py` do not exist in this branch at all — every claim in this report about those files is scoped explicitly to the branch that has them, and reconciliation (§F, P0) needs to happen before assuming they apply universally.
- **Do not treat the plate-regex fix as requiring the DLP or family-preservation work as a prerequisite.** It is independently valuable, independently safe, and was explicitly designed (in the existing roadmap) to be shippable before anything else in this report.

---

*Produced as a companion to `legend_aware_extraction_audit.md`, `drawing_language_profile_implementation_audit.md`, `estima3d_rd_roadmap.md`, `estima3d_rd_synthesis_and_final_conclusion.md`, and `ismail_recent_merge_audit.md`, all in this folder. This document adds: (1) direct verification of the family-preservation architecture (`label_reconstruction/structural_parser.py`) against the user's specific Idea C, not previously covered by the prior five audits; (2) direct verification of the confidence/abstention architecture against the user's Idea 6; (3) a four-way branch/worktree state map; (4) confirmation that the plate-regex fix identified two sessions ago remains unfixed today.*
