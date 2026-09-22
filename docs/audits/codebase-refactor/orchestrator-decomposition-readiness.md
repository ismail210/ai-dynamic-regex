# Prediction Orchestrator Decomposition Readiness

Scope: a dedicated, read-only mapping and characterization phase for
`backend/services/prediction/orchestrator.py`, evaluating the hypothesis that `predict_token`'s
"exact-match/database-verification branch" is a safe first extraction boundary. **This is a readiness gate,
not an extraction.** Zero production code was changed. Starting SHA: `bf32f44e10160fc07267c8ffa95bd7cc055a0abf`.

## Headline finding

**The hypothesis as stated is false.** `predict_token` (147 LOC) contains no exact-match or
database-verification logic at all — it is a thin wrapper that builds a minimal token-only context, calls
`predict_from_context` exactly once, and then does *token-only-entry-point* post-processing (self-learning
persistence, regex-knowledge-base validation, unknown-token queueing). All exact-match locking and database
verification lives inside `predict_from_context` — a single 1,598-line function (77% of the file's physical
LOC) where the "locked exact match" concept is a cross-cutting flag (`protected_exact_section` /
`section_text_locked`) read or written at **30 distinct points** spread across the entire function, not a
contiguous branch. See **Decision** below for the corrected, evidence-based boundary.

## Structural inventory

`backend/services/prediction/orchestrator.py`: **2,068 physical LOC**, 1,802 non-blank/non-comment lines.

- **37 imports**, all `from services.*`/`from config import settings`/stdlib (`re`, `typing`). No
  `os.getenv`/`os.environ` reads in this file — all configuration goes through `config.settings` (read at
  2 points: `settings.document_prior_enabled`, `settings.spatial_association_enabled`).
- **7 module-level assignments**: `STRUCTURAL_FAMILIES` (constant set), `_geometry_provider` /
  `_graph_provider` (singleton instances of `GeometryFeatureProvider`/`GraphFeatureProvider` from
  `multimodal/feature_providers.py`, instantiated once at import time — shared mutable state across every
  call, already covered for concurrency by `tests/test_graph_feature_provider_concurrency.py`), and 4
  numeric threshold constants (`EXACT_OVERRIDE_MIN_CONFIDENCE`, `EXACT_OVERRIDE_MIN_MARGIN`,
  `LEARNED_DISAGREEMENT_GEOM_MIN`, `LEARNED_DISAGREEMENT_GRAPH_MIN`).
- **0 classes.**
- **10 top-level functions**, 8 private:

| Function | Lines | LOC | Branches (approx.) | Role |
|---|---|---|---|---|
| `_is_structural_family` | 111-112 | 2 | 1 | trivial predicate |
| `_early_confirmed_plate_type` | 115-165 | 51 | 18 | pre-fusion plate-grammar classification |
| `_plate_annotation_display_label` | 168-191 | 24 | 6 | display formatting for confirmed plates |
| `_skipped_section_fusion_result` | 194-213 | 20 | 0 | placeholder `UnifiedFusionResult` when fusion is skipped |
| `_candidate_confidence` | 216-221 | 6 | 4 | accessor helper |
| `_candidate_shape` | 224-229 | 6 | 4 | accessor helper |
| `_gated_exact_override` | 232-300 | 69 | 9 | catalog-grounds a fusion pick or rejects it |
| `_text_locked_section` | 303-319 | 17 | 5 | text-only re-derivation fallback |
| **`predict_from_context`** | **322-1919** | **1,598** | **~329** | **the entire multimodal prediction pipeline** |
| `predict_token` | 1922-2068 | 147 | 26 | token-only wrapper + self-learning/regex/queue post-processing |

The 8 private helpers are **already-extracted, single-responsibility pure functions** — the orchestrator has
already been partially decomposed at the "obvious pure function" level. What remains inline is the
*stateful, sequential orchestration* itself.

No caches, no logging calls, no metrics/tracing, no filesystem effects, and no direct database/registry
writes exist in this file — `orchestrator.py` is a pure computation over its `context` argument plus calls to
already-decoupled services (`database_loader`, `exact_section_predictor`, `multimodal.modular_fusion`,
`multimodal.feature_providers`, `annotation.*`, `prediction.{ranking,calibration,canonical_contract,
confidence_engine,explanation_engine,review_policy,label_ranker_hook}`, `regex_knowledge_base`,
`regex_validator`, `self_learning_engine`, `dataset_manager` — the last two imported function-locally inside
`predict_token`, not at module level).

## Caller classification (Phase 2)

Verified by direct read of every hit, not text search alone.

**`predict_token`** — real production callers:
- `services/dynamic_regex_service.py` (direct call) ← `routers/analysis.py` (`analyze_token`/`analyze_tokens`)
  — the token-only `/api/analyze` path.
- `scripts/evaluate_pipeline.py` (operational/research script — the holdout-evaluation harness).

Not real callers (verified): `services/prediction/canonical_contract.py`, `services/self_learning_engine.py`
(docstring/comment mentions only); `services/prediction/__init__.py` (re-export consumed only by
`tests/test_calibration.py`, not production).

**`predict_from_context`** — real production callers:
- `services/multimodal/fusion_engine.py` (direct call, line 769 per `semantic-shim-and-fusion-review.md`) ←
  `services/multimodal/pipeline.py` (`run_multimodal_pipeline`) ← `services/staged_pipeline.py` ←
  `routers/documents.py`'s `.../analyze` endpoint — the full multimodal `/api/documents/.../analyze` path.
- `scripts/feature_flags_status.py` (diagnostic string literal only — not an actual call; excluded).

Not real callers (verified): `services/multimodal/member_resolution.py`, `services/prediction/review_policy.py`
(docstring/comment mentions only).

**Both production paths converge on `predict_from_context` as the single inference entrypoint**, matching
`CLAUDE.md`'s architecture invariant exactly. No dynamic/`importlib`/string-based imports, no monkeypatch
targets outside tests, no serialized references, and no app-startup wiring reference either function.

## `predict_token` as an execution model

`predict_token(token, *, source_file="", queue_unknown=False, persist_learning=True)`:

1. Normalize the raw string; build a minimal synthetic `context` dict (`token` sub-dict with `text`,
   `normalized_text`, a fixed `confidence=0.5`, `token_id`; empty `geometry`/`graph`; `source_file`).
2. Call `predict_from_context(context)` — **exactly once, unconditionally**. All matching, HSS handling,
   fusion, and exact-match locking happen here, invisibly to `predict_token`.
3. Re-derive `review_status`/`abstention_reason` from the inner result's `detected_issues` plus the
   regex-knowledge-base match (`full_match`) — this recomputation exists specifically so a token-only caller
   sees a regex-informed status the geometry/graph-free context couldn't produce on its own; it explicitly
   does **not** run when `_section_text_locked` (popped from the inner result) is true (see `abstain`/
   `protected_label_conflict`/`near_tie` computations, all gated by `and not section_text_locked`).
4. Self-learning gate: only `match_status in {"exact_match", "normalized_match"}` and `not needs_review` may
   be learned into the regex knowledge base (`learn_from_prediction`); everything else may still be *shown*
   as a suggestion but never merged as ground truth.
5. Build `regex`/`suggested_regex`/`regex_matches_token`/`learning`/`regex_variants`/`validation` — fields
   that exist only at this token-only entry point (there is no per-token regex-knowledge-base concept in the
   full multimodal context).
6. Optionally enqueue to the unknown-token dataset when `queue_unknown and review_status == "pending_review"`.

No exact-match or database-verification decision is made in this function — steps 3-4 *consume* the already-
final `section_text_locked` flag to protect it from being recomputed away, but do not compute it.

## Exact-match / database-verification path (inside `predict_from_context`)

1. **Computation** (lines 366-369): `protected_exact_section = resolve_trusted_explicit_section(normalized)
   or resolve_trusted_explicit_section(raw_text)` — delegates entirely to
   `services/exact_section_predictor.py` (already a separate, well-tested module: catalog membership +
   `catalog_form` notation-equivalents + reliable-prefix/cut-length resolution). Computed before geometry,
   graph, or fusion run.
2. **Full pipeline still runs regardless** — fusion (`unified_multimodal_fusion.predict`), the exact-override
   gate (`_gated_exact_override`), and the label ranker (`apply_label_ranker_for_analyze`) all execute even
   when `protected_exact_section` is set, purely to produce diagnostic/provenance evidence.
3. **Enforcement** (lines 792-802): *after* fusion and the ranker have both run and potentially changed
   `section`, `if protected_exact_section:` unconditionally resets `section = protected_exact_section` and
   `retrieval_gate_failed = False`, recording any prior disagreement as
   `explicit_section_context_disagreement` (diagnostic-only, never review-forcing).
4. **Database verification** (lines 1053-1063, `db_exact = lookup_shape(section) or
   lookup_shape(catalog_form(section) or "")`) runs *after* `section` is finalized — comment: "Post-prediction
   AISC plausibility check; it never generates candidates." Feeds `signals["database"]`,
   `confidence["database_role"] = "verification_only"`, and `database_verified` for the review-status
   calculation — never re-selects `section`. This matches `CLAUDE.md`'s "AISC database verifies only" and
   `tests/test_prediction_orchestrator.py::OrchestratorPolicyTests::test_database_hit_does_not_override_ai_section`.
5. **Final lock flag** (lines 980-987): `section_text_locked = protected_exact_section and section ==
   protected_exact_section and section_from_own_text and not retrieval_gate_failed and not
   confirmed_plate_type and not missing_thickness_needs_review`. `section_from_own_text` (969-979)
   specifically excludes geometry-associated / spatially-associated / schedule-sourced / missing-label
   tokens — a locked identity only ever comes from *this object's own* extracted characters, never a
   neighbor's.
6. `section_text_locked` is then read **at least 20 more times** downstream to protect confidence
   (`model_probability`/`confidence_value` forced to `1.0`), suppress `issues` entries
   (`member_association_uncertain` instead of `geometry_conflict`/`graph_conflict`; annotation-ambiguity
   flags suppressed), set `confidence["basis"] = "explicit_catalog_exact"` /
   `confidence["type"] = "deterministic"`, pass `locked_section=section` into `build_ranking`, and pass
   `section_text_locked=section_text_locked` directly into `build_explanation` (the v2 explainability
   contract is itself lock-aware, not just the orchestrator).

**Reachable mutation site identified (see Characterization below)**: a *later* annotation-taxonomy
reclassification (`interpret_token_annotation`, lines 862-894) that confidently identifies the token as a
confirmed plate/bent-plate **does** clear an already-locked `section` — the code has no explicit
`if section_text_locked: skip this` guard at that specific point, unlike the `requires_review` branch three
lines below it (902-909), which *does* explicitly check `protected_exact_section` and preserves the label.
Proven reachable via a direct, targeted test (not theoretical) — see Characterization.

## Incomplete-HSS path

- **Detection** (lines 506-520): only when `protected_exact_section` is falsy —
  `detect_missing_thickness_hss(normalized) or detect_missing_thickness_hss(raw_text)` →
  `hss_completions = hss_completion_candidates(*hss_dimensions)`; `missing_thickness_needs_review =
  len(hss_completions) > 1`.
- **Candidate generation**: when `hss_completions` exist, `exact_candidates` is generated *only* from the
  HSS-completion designations (`predict_exact_sections_for_labels`), never from unconstrained fuzzy
  retrieval — this is what keeps e.g. `HSS10X10` candidates prefixed `HSS10X10*` and never drifting to a
  different nominal size (locked in by `tests/test_hss_missing_thickness_review.py`).
- **Review forcing** (line 923-929): `missing_thickness_needs_review` always sets
  `retrieval_gate_failed = True` and appends a review reason naming the candidate count.
- **`completion_status`** field (1766-1770) in the result: `"missing_thickness"` when `hss_completions` or
  `incomplete_angle_needs_review`, else `"complete"` — a stable, additive signal for consumers.
- **LLM-supplied completion is *not* implemented inside `orchestrator.py` at all.** It lives in
  `services/prediction/hss_review_enrichment.py`, consumed by `services/staged_pipeline.py` — a downstream,
  post-hoc enrichment step over the orchestrator's *output*, with its own dedicated test file
  (`tests/test_hss_review_enrichment.py`). Invariant 4 ("if the LLM reliably supplies the missing thickness,
  the completed section may be applied automatically") is therefore **already architecturally decoupled**
  from `predict_from_context`/`predict_token` — a future extraction of the orchestrator's own exact-match
  logic would not need to touch this module at all.

## Human-review precedence path

**`orchestrator.py` contains zero references to `human_selected`/`human_review`/`human_selections`** (grep
confirmed, whole file). Human-review precedence is implemented entirely *outside* the orchestrator, in
`services/multimodal/member_resolution.py::classify_member` and `services/human_selections.py`, applied as an
overlay over the orchestrator's output (confirmed directly by
`tests/test_trusted_explicit_section.py::HumanOverrideTests`, which builds a `{**prediction_result,
"human_selected_section": ..., "decision_source": "human_review"}` dict and passes it to `classify_member`,
a function the orchestrator never calls). **This is favorable evidence for extraction safety**: any future
extraction of the orchestrator's exact-match logic inherits this same clean separation by construction —
human-review precedence cannot be affected by orchestrator-internal changes because it does not live there.

## State and side-effect map (Phase 4)

Values crossing the `predict_from_context` exact-match "boundary" (i.e., needed by both the matching logic
and later stages), classified:

| Value | Classification | Notes |
|---|---|---|
| `normalized`, `raw_text`, `original`, `extraction_confidence` | immutable input (derived once, read-only after) | |
| `protected_exact_section` | computed result, read-only after computation | set once at line 366-369, never reassigned |
| `section` | **mutable shared state** | reassigned at ≥12 distinct points across the function (fusion result, gate override, ranker pick, protected-section force, incomplete/non-catalog-angle preservation, text-locked fallback, late-plate clearing, text-locked-family correction, `resolved_semantic_annotation` override) |
| `retrieval_gate_failed` | **mutable shared state** | reassigned at ≥8 points, tracks whether `section` should be trusted |
| `ai_reasons` | **mutable shared state** (append-only list) | accumulated across ~15 append sites; order is part of the explanation contract's `why_selected`/`why_rejected` narrative |
| `confirmed_plate_type` | **mutable shared state** | can be set both early (`_early_confirmed_plate_type`) and late (annotation-pack reclassification) |
| `section_text_locked` | computed result, read-only after computation (line 980-987) | consumed ~20 times downstream |
| `unified_fusion`, `annotation_pack`, `rules` | computed results, read-only after computation | each assigned once |
| `_geometry_provider`/`_graph_provider` | module-level singleton, mutable across calls (not per-call state) | already covered by `test_graph_feature_provider_concurrency.py` |
| exceptions | `interpret_token_annotation` never raises (catches internally, returns an `unresolved_annotation` structure); other dependency calls (`unified_multimodal_fusion.predict`, `lookup_shape`, `predict_exact_sections*`) are **not** wrapped in `try/except` inside `orchestrator.py` — an exception there propagates uncaught to the caller |

**Evaluation-order significance confirmed**: fusion and the label ranker execute even when
`protected_exact_section` is already known, specifically so their *disagreement* becomes diagnostic evidence
(`explicit_section_context_disagreement`) rather than being skipped — a "short-circuit as soon as we know
it's an exact match" reordering would silently drop that diagnostic, changing observable behavior
(`ai_reasons` content, `issues` content, `canonical.comparison` fields) even though the final `section` value
would be unchanged. **A behaviorally-equivalent extraction must preserve this "compute everything, then
override" order, not skip ahead.**

## Test coverage matrix (Phase 5)

| Scenario | Covering test(s) |
|---|---|
| Unique valid exact match | `test_trusted_explicit_section.py::ResolverUnitTests`, `CrossFamilyDecoyTests` (9 families) |
| Normalized exact match | `test_round_hss_display_consistency.py`, `test_resolution_contract.py::ExactAndFormattingMatchesRemainDeterministicTests` |
| Canonical alias match (round HSS, fractional angle legs, cut-length) | `test_protected_exact_label.py::ReliableExactCatalogLabelCutLengthTests`, `CutLengthLiveFusionIntegrationTests` |
| Database-verified match, DB never overrides AI | `test_prediction_orchestrator.py::OrchestratorPolicyTests::test_database_hit_does_not_override_ai_section` |
| Invalid/unknown token | `test_resolution_contract.py::InvalidCatalogShapeTests`, `test_protected_exact_label.py` garbage-text cases |
| Ambiguous token | `test_resolution_contract.py::AmbiguousOcrSubstitutionTests` |
| Incomplete HSS without thickness | `test_hss_missing_thickness_review.py` (7 classes, extensive) |
| Incomplete HSS with LLM-supplied thickness | `test_hss_review_enrichment.py` (separate module, outside orchestrator scope) |
| Geometry/ML/ranker disagreement with exact match | `test_resolution_contract.py::GeometryConflictTests`, `LabelRankerCannotBypassGateTests`, `test_label_ranker_evidence_recompute.py`, `test_protected_exact_label.py` (round-HSS vs. W-family fusion) |
| Exact match not sent to review | `test_trusted_explicit_section.py::ExactHssScreenshotReproTest`, `CrossFamilyDecoyTests` |
| Human-reviewed value precedence | `test_trusted_explicit_section.py::HumanOverrideTests` (via `classify_member`, confirming precedence lives outside the orchestrator) |
| Confidence/provenance preservation | `test_label_ranker_evidence_recompute.py` (all 4 tests) |
| Incomplete angle (missing thickness) / non-catalog angle | `test_incomplete_angle_abstention.py` (20 tests) |
| Plate/bent-plate confirmed annotation | `test_resolution_contract.py::UnsupportedAnnotationTests::test_plate_annotation_gets_no_forced_section` |
| Self-learning persistence gate | `test_self_learning_safety.py::PredictTokenSelfLearningGateTests` |
| Context-scope independence (legend/notes tokens) | `test_trusted_explicit_section.py::ContextScopeIndependenceTests` |
| **Late plate reclassification vs. an already-locked exact match** | **gap — now closed, see Characterization** |
| Dependency failure / malformed dependency response | **gap — not closed in this phase, see Remaining Gaps** |
| Repeated calls / module-singleton state | `test_graph_feature_provider_concurrency.py` (pre-existing, not orchestrator-specific) |

## Characterization tests added

One new test class, `tests/test_trusted_explicit_section.py::LateAnnotationReclassificationTests` (45 LOC,
1 test method): patches `services.prediction.orchestrator.interpret_token_annotation` to return a synthetic
`{"annotation": {"annotation_type": "BENT_PLATE", "structure_confirmed": True}, "understandability":
{"status": "UNDERSTOOD", ...}, "abstain_for_review": False}`, then calls `predict_token("W18X35", ...)`.

**Observed (not assumed) result**: `section` becomes `""`, `category`/`entity_type` become `"plate"`,
`needs_review` becomes `True`, `review_status` becomes `"pending_review"` — the late plate reclassification
*does* clear the already-locked exact match. This is reported as **characterization of current behavior, not
a claimed defect**: `interpret_token_annotation`'s real implementation is very unlikely to classify literal
rolled-shape catalog text (`"W18X35"`) as a plate/bent-plate with genuine geometry/graph/context inputs —
plate-grammar and rolled-shape-catalog text patterns are largely disjoint by construction (confirmed by
reading `_early_confirmed_plate_type`'s use of the same `interpret_annotation` plate grammar). This test
deliberately bypasses the real classifier to force the interaction and lock in today's actual behavior before
any future change in this area, per Phase 3's explicit instruction to "distinguish theoretical mutation sites
from reachable behavior" — the *code path* is reachable and now proven, even though real-world *triggering
input* is unproven either way.

No other characterization tests were added. The two branches of my alternative extraction candidate (the
duplicated `encoder_registry.encode_all(...)` payload-assembly block — see Decision) already have adequate
existing end-to-end coverage: `skip_section_fusion=True` via
`test_resolution_contract.py::UnsupportedAnnotationTests::test_plate_annotation_gets_no_forced_section`
(`predict_token("PL 1/2 X 8", ...)`), `skip_section_fusion=False` via essentially every other orchestrator
test in this matrix. Cited per this phase's own "if current tests already cover a case adequately, cite
those tests instead of cloning them" instruction.

## Remaining coverage gaps (not closed in this phase)

- **Dependency failure / malformed dependency response**: no test found that exercises
  `unified_multimodal_fusion.predict`, `lookup_shape`, or `predict_exact_sections*` raising or returning a
  malformed value. None of these calls inside `orchestrator.py` are wrapped in `try/except` — an exception
  propagates uncaught. Whether that is the intended contract (fail loudly) or an oversight is not determined
  by this phase; flagged for a future, separately-scoped investigation, not fixed or characterized here since
  it is orthogonal to the exact-match boundary decision.
- Full manual verification that `interpret_token_annotation`'s real (unmocked) classifier can never produce
  a plate/bent-plate result for genuine catalog-exact rolled-shape input was not performed — the disjoint-
  pattern argument above is evidence, not proof. A dedicated plate-grammar audit would be needed to close this
  with certainty.

## Documentation-vs-behavior conflicts found

None material. `docs/ENGINEERING_VALIDATION.md`'s "Human Review" section describes the review UI/workflow at
a level that does not contradict the finding that precedence enforcement lives outside `orchestrator.py`. One
pre-existing, unrelated staleness note (not a conflict introduced or discovered by this phase): that same
document's "Future Takeoff Export" section still references `takeoff_interface.py`, which was deleted in an
earlier phase of this engagement (`dead-module-reachability-review.md`) — out of scope to fix here (this
phase makes no production or unrelated-documentation edits). No standalone "resolution contract" markdown
document exists — the "resolution contract sections 8/11-20" terminology used throughout
`test_trusted_explicit_section.py`/`test_resolution_contract.py`/`test_protected_exact_label.py` is an
internal test-suite convention, not a separately published spec; noted for completeness, not a conflict.

## First-boundary decision

**`READY_WITH_DIFFERENT_BOUNDARY`**

The original hypothesis (a `predict_token` exact-match/database-verification branch) is rejected on direct
evidence: `predict_token` contains no such logic, and the real exact-match/database-verification logic inside
`predict_from_context` is a cross-cutting flag threaded through ~30 points across a 1,598-line function with
extensive shared mutable local state (`section`, `retrieval_gate_failed`, `ai_reasons`,
`confirmed_plate_type`) — it fails criteria 3 and 4 (dependencies cannot be passed without substantially
reproducing the function's own running state; it does require that shared mutable state) for anything
resembling a single first cut.

A genuinely ready, narrower, different boundary was found instead: **the near-duplicate
`encoder_registry.encode_all(...)` input-payload assembly**, present twice — lines 471-504
(`skip_section_fusion=True` branch) and lines 730-768 (normal branch) — identical in 5 of 7 top-level keys
(`ocr`, `layout`, `geometry`, `graph`, `engineering_rules` blocks are byte-identical; only `text.
model_probability` and `text.candidates` differ between the two call sites). Evaluated against all 10
criteria:

1. Coherent single responsibility: yes — "assemble the encoder-registry input dict from already-computed
   values."
2. Inputs/outputs explicitly named: yes.
3. Dependencies passable without reproducing the orchestrator: yes — takes only already-local values
   (`normalized`, `raw_text`, `corrected_text`, `extraction_confidence`, `token_record`, `geometry`, `graph`,
   `provisional_rules`, plus the 2 varying keyword values).
4. No hidden shared mutable state: yes — pure function, no `section`/`retrieval_gate_failed`/`ai_reasons`
   involvement at all.
5. Execution order preserved: yes — called at the exact same 2 points, no reordering possible or needed.
6. Sufficient characterization coverage: yes — both branches already covered (see above), no new tests were
   even required to establish this.
7. No schema/logging/exception/feature-flag/call-count change: yes — `encoder_registry.encode_all` is called
   exactly as many times, with the exact same resulting dict, as today.
8. Clear domain-appropriate owner: the function is used **only** by `predict_from_context` itself — the
   domain-appropriate owner is a new private top-level helper *inside* `orchestrator.py`
   (`_build_encoder_input(...)`), matching the file's own existing pattern of 8 already-extracted private
   helpers. It does **not** warrant a new file (see non-goals below) — moving one small, single-caller-file
   helper to a separate module would violate this phase's own "not a generic dumping ground" / "do not
   manufacture abstractions merely to relocate lines" constraint.
9. Improves comprehension: yes — one call site to audit for "what does the encoder see" instead of two
   near-identical 30+ line blocks that must be diffed by eye to confirm they're intentionally different in
   exactly 2 fields.
10. No "utils" dumping ground: yes — narrowly named, single purpose, single caller.

This is explicitly a **narrower, same-file, prerequisite** extraction — not a cross-module decomposition step.
It reduces `predict_from_context`'s own line count and duplication surface without touching the exact-match
locking, HSS, or review logic at all, and is a safe, independently reversible first cut that does not require
resolving the much harder question of how to eventually decompose the exact-match/fusion/review orchestration
itself (which remains **NOT_READY** for any extraction in this phase — the state-sharing and evaluation-order
constraints documented above are real, not merely theoretical caution).

## Proposed interface (not implemented)

- **Destination**: `backend/services/prediction/orchestrator.py` (same file — a new private top-level
  function, not a new module).
- **Responsibility statement**: "Assemble the `encoder_registry.encode_all` input payload for one token from
  already-computed context, geometry, graph, and engineering-rules values."
- **Candidate name**: `_build_encoder_input`.
- **Exact parameters**: `(*, normalized: str, raw_text: str, corrected_text: str, extraction_confidence:
  float, token_record: Dict[str, Any], geometry: Dict[str, Any], graph: Dict[str, Any], provisional_rules,
  model_probability: float, candidates: List[Any]) -> Dict[str, Any]` — a plain dict return (the existing
  input shape to `encoder_registry.encode_all`), no new dataclass/enum/wrapper type: the shape is already
  fully expressed by the existing nested-dict literal, and inventing a typed wrapper around it would be
  exactly the kind of abstraction this phase's own constraints forbid introducing "merely to make files
  shorter."
- **Dependency injection**: none needed — pure function of its arguments.
- **Exception behavior**: unchanged — no new try/except; whatever `encoder_registry.encode_all` does today
  (called with the identical structure) it continues to do.
- **Call-order requirement**: called at the exact same 2 sites, in the exact same position relative to
  `provisional_rules`/`geometry`/`graph` computation, with the same 1-call-per-branch cardinality.
- **State/provenance fields that remain owned by the orchestrator**: everything — `section`,
  `retrieval_gate_failed`, `ai_reasons`, `confirmed_plate_type`, `protected_exact_section`,
  `section_text_locked`, and all confidence/explanation/canonical-contract construction stay exactly where
  they are; this extraction touches only the dict-literal construction feeding `encoder_registry.encode_all`.
- **Tests that must pass before and after**: the full matrix in this document, at minimum
  `test_hss_missing_thickness_review.py`, `test_incomplete_angle_abstention.py`,
  `test_trusted_explicit_section.py`, `test_protected_exact_label.py`, `test_resolution_contract.py`,
  `test_label_ranker_evidence_recompute.py`, `test_prediction_orchestrator.py`,
  `test_canonical_contract.py`, plus the full backend suite.
- **Estimated moved LOC**: ~30 (one of the two near-duplicate blocks collapses into a single call).
- **Estimated net LOC**: roughly **-25 to -30** in `orchestrator.py` (removes one ~34-line duplicate block,
  adds one ~15-line helper definition plus two ~10-line call sites) — a genuine reduction, not organizational
  churn.
- **Commit sequence** (future phase, not this one):
  1. `test(prediction): characterize encoder-input payload shape` (only if the matrix above is judged
     insufficient at implementation time — currently believed sufficient).
  2. `refactor(prediction): extract encoder-input assembly in orchestrator` — add `_build_encoder_input`,
     replace both call sites, remove the duplicate dict literals. Single commit, fully reversible.
  3. `docs(refactor): record orchestrator encoder-input extraction`.

## Non-goals of this phase (explicitly not done)

No production code changed. No refactor, move, rename, or reformat of `orchestrator.py` or any other
production file. No extraction implemented. No fix attempted for the late-plate-reclassification finding
(reported as characterization, not treated as a defect requiring a decision). No fix for the
`takeoff_interface.py` documentation staleness. No dependency-failure test added. No broad Pyright run
(explicitly avoided per this task's own instruction, given the prior 4-day hang).

## Production/test LOC

- Production LOC changed: **0** (verified: `git diff --stat` on `orchestrator.py` and every other production
  file is empty).
- Test LOC changed: **+45** (`tests/test_trusted_explicit_section.py`, one new test class/method).

## Final SHA

See final report below for the exact commit SHAs and push confirmation.
