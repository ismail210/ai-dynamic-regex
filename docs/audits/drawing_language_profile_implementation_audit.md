# Drawing Language Profile & Contextual Fabricated-Steel: Adversarial Implementation Audit

**Scope of this audit:** verify, from git through source through real PDFs through the live browser, whether the Drawing Language Profile (DLP) and contextual fabricated-steel candidate layers actually behave the way they were designed to, or merely look successful because nearby text still supplies the answer. This is a verification pass on work implemented across two prior sessions (one by me, continued and substantially extended by another agent instance) — nothing here was taken on trust; every claim below was either read in the current source, executed directly, or observed live in the browser.

**Repo/worktree audited:** `C:\Users\Bassam\git\ai-dynamic-regex-dlp`, branch `bassam/drawing-language-profile`, HEAD `999787d` (tracking `origin/estima3d-integration`, no partner commits landed since the prior session — confirmed via `git fetch --all --prune` + `git log --all`). Nothing was committed or pushed.

---

## A. Git state

- Worktree: `C:/Users/Bassam/git/ai-dynamic-regex-dlp` (an isolated worktree created in the prior session specifically so this work never touches the main `ai-dynamic-regex` checkout or its uncommitted research docs).
- Branch: `bassam/drawing-language-profile`, HEAD `999787d`, same commit as `origin/estima3d-integration` — no drift, no partner pushes since last session (`git fetch --all --prune` showed no updates to any remote branch).
- Uncommitted state at audit start: 8 modified tracked files + 5 new untracked source/test files + 1 new untracked cache directory — exactly matching two sessions' worth of implementation work, nothing unexpected.
- I did **not** trust the prior session's own summary of what it built — every file below was re-read from disk in this audit.
- Final `git status` (after this audit's own fixes, and after reverting incidental training-data mutation caused by my live testing — see §K): 10 modified tracked source/test files, 5 new untracked source/test files, 1 new untracked cache directory. No tracked file outside `backend/services/` and `backend/tests/` remains modified.

---

## B. Architecture reconstruction (actual, from source)

```
PDF upload
  → services/extraction_engine.extract_engineering_document()
      → attach_document_prior()                         [pre-existing, unchanged]
      → attach_drawing_language_profile()                [NEW, gated by DRAWING_LANGUAGE_PROFILE_ENABLED/SHADOW]
          → load_or_build_profile() — cache hit? return cached profile (hash+version+catalog+LLM-prompt-version keyed)
                                     — cache miss? build_drawing_language_profile():
                                         detect_page_roles() [coarse keyword heuristic]
                                         → extract_designation_rules()   [deterministic, legend/notes pages only]
                                         → extract_vocabulary_rules()    [deterministic, wraps document_prior]
                                         → (if llm_provider given) propose_prose_rules() ONCE, on legend/notes text only
                                         → save_profile() to disk cache
      → _drawing_language_profile_tokens()  [NEW, ENABLED-mode only: synthesizes bare-shorthand tokens like a lone "W10" line on a FRAMING_PLAN page that the ordinary extractor would otherwise never surface at all]
      → filter_engineering_objects() [pre-existing, unchanged]

Analyze (per document, once)
  → services/multimodal/pipeline.run_multimodal_pipeline()
      → attach_drawing_language_profile() again (idempotent — cache hit if extraction stage already built it)
      → per token: services/multimodal/fusion_engine.WeightedFusionEngine.predict()
          → services/prediction/orchestrator.predict_from_context()   [the actual logic]
              → resolve_designation() against the cached profile — BEFORE the "protected exact label" check
              → resolve_hss_thickness_hint() — narrows hss_completion_candidates() to 1 row when a project rule matches
              → build_canonical_prediction(project_rule_applied=...)   [new MatchStatus.PROJECT_RULE_RESOLVED]
              → analyze_contextual_candidates()   [NEW, gated by CONTEXTUAL_FABRICATED_STEEL_SHADOW/ENABLED — evidence-only, never touches final_label/section/confirmed_annotation]
              → explanation["drawing_language_profile"], explanation["contextual_fabricated_steel"] attached
          → fusion_engine reconstructs a fixed-schema Explainability object from `explanation` — **this step was silently dropping both new keys until fixed in this audit, see §P defect 1**
```

Two feature families, cleanly separable:
1. **Applied** (can change a prediction): designation-substitution rules only, and only when `RULE_STATUS_SOURCE_VERIFIED`. Gated by `DRAWING_LANGUAGE_PROFILE_ENABLED` (default **false**).
2. **Shadow/diagnostic only** (never changes a prediction): everything else — vocabulary rules used as extra context, connection-default/implied-element/relationship/annotation-grammar rules (LLM-sourced, always `RULE_STATUS_PROPOSED_INFERENCE`), and the entire contextual fabricated-steel candidate layer. Gated by `*_SHADOW` flags (default **false**).

---

## C. DLP audit

| Sub-area | Verdict | Evidence |
|---|---|---|
| Rule extraction (designation) | **PASS** | Real GCDC PDF → all 8 reported rules extracted verbatim, correct pages, correct catalog targets (§D). |
| Rule extraction (vocabulary) | **FIXED** | Real GCDC PDF's abbreviation table produced 11 garbage pairs (`EAST→west`, `Z→rod or hilti hit hy 200 safe set`, etc.), all stored as `RULE_STATUS_SOURCE_VERIFIED` — the same trust tier as a real `PL=plate` mapping. Fixed with an explicit meaning-allowlist (§P defect 2). Also discovered (not a bug, a real limitation): GCDC's actual abbreviation table is a two-column layout the same-line regex can never parse, so **zero** of the project's real `PL`/`LLH`/`LLV`/etc. abbreviations are currently captured, before or after the fix (§I). |
| Source verification / status discipline | **PASS** | Explicit sentence → `SOURCE_VERIFIED` immediately, no corroboration required (confirmed live: `observed_applications` populated but never gates). LLM-proposed rules are **structurally incapable** of reaching `SOURCE_VERIFIED` — wrong type (`connection_default`/`relationship`/`implied_element`/`annotation_grammar`, never `designation_substitution`) *and* wrong status, hardcoded in `drawing_language_llm.py`. |
| Catalog validation | **PASS** | Every extracted rule's target is checked via `lookup_shape`/`parse_section` before storage; unresolvable targets are discarded, never stored as guesses. Cross-family substitutions (e.g. W→C) are explicitly rejected (`drawing_language_profile.py` lines 290–301). |
| Project isolation | **PASS (rigorously proven)** | Deliberately unusual control: a fake `W8→W8X48` rule resolved correctly *only* on the document declaring it; two documents with no profile independently produced `W8X10` via the pre-existing, unrelated baseline model — never `W8X48`. See §D. |
| Caching / invalidation | **PASS** | Keyed on content hash (not filename) + profile schema version + extractor version + catalog version + LLM-requested flag + LLM prompt version. Bumping `EXTRACTOR_VERSION` for the vocabulary fix correctly invalidated the stale cached GCDC profile on the next run (verified live). |
| LLM enabled/shadow/off | **PASS** | No LLM SDK is even a hard dependency (`try: import anthropic except ImportError: return None`). `DRAWING_LANGUAGE_LLM_ENABLED=false` (default) ⇒ `NullLLMProvider`, zero behavior difference from no LLM configured at all. LLM is called **at most once per document**, only on legend/notes-page text (bounded to 20,000 chars), never per token. |

---

## D. GCDC real-document results (from the actual PDF, via `extract_engineering_document` + `attach_drawing_language_profile`, not hardcoded strings)

| Trigger | Result | Source page | Exact source quote | Catalog valid |
|---|---|---|---|---|
| W8 | W8X10 | 5 | `"W8" = W8x10` | true |
| W10 | W10X12 | 5 | `"W10" = W10x12` | true |
| W12 | W12X19 | 5 | `"W12" = W12x19` | true |
| W14 | W14X22 | 5 | `"W14" = W14x22` | true |
| W16 | W16X26 | 5 | `"W16" = W16x26` | true |
| C8 | C8X11.5 | 5 | `"C8" = C8x11.5` | true |
| **C12** | **C12X20.7** | 5 | `"C12" = C12x20.7` | **true** |
| HSS8X4 | HSS8X4X1/4 | 5 | `"HSS8x4" = HSS8x4x1/4` | true |

All 8 rules, all `RULE_STATUS_SOURCE_VERIFIED`, all extracted from the real 81-page PDF at `...\GCDC Building\GCDC Building 4 - ST1.pdf`, not from the request's own illustrative example. `C12 → C12X20.7` specifically confirmed per the requester's explicit ask.

The synthesized-token mechanism (`_drawing_language_profile_tokens`, ENABLED-mode only) found **73 real bare-shorthand lines** on FRAMING_PLAN pages that the ordinary extractor would never have surfaced at all (e.g. a lone `"W10"` text line on pages 31–33) — this is real, additional capability beyond what I originally scoped, correctly gated to exact whole-line matches, framing-plan pages only, excluding the rule's own source page.

---

## E. HSS audit (with and without project rule, real orchestrator calls)

| Case | `section` | `match_status` | `needs_review` | `review_status` | `decision_source` |
|---|---|---|---|---|---|
| `HSS8x4`, no profile | `HSS8X4X5/16` | `missing_dimension_field` | **true** | `pending_review` | `human_or_model_pipeline` |
| `HSS8x4`, GCDC profile | **`HSS8X4X1/4`** | **`project_rule_resolved`** | **false*** | `pending_review`* | **`project_profile`** |

*`needs_review` reads false for the resolved match itself (`PROJECT_RULE_RESOLVED` is deliberately not in `_REVIEW_REASONS`, matching the `CONFIRMED_ANNOTATION` precedent); `review_status` still shows `pending_review` here because this synthetic single-token test lacked full geometry/graph context that the real pipeline's `decide_review_status` also weighs — this is the review-policy layer doing its own independent job, not the DLP feature overriding it, and is expected/correct, not a defect.

Invalid-hint fallback (Section 8's third scenario) is code-guaranteed, not merely tested: `hss_completion_candidates(..., project_thickness_hint=...)` only narrows when the hint matches **exactly one** real catalog row; any non-matching hint returns the full, unnarrowed candidate list unchanged (`hss_completion.py` lines 188–196) — a bad or typo'd project note can never hide legitimate options.

---

## F. PL/BENT PL regression audit — live UI, real Burrville PDF, real analyze run

Uploaded `Burrville ES - ST.pdf` fresh through the actual running app (not a cached artifact), extracted (918 engineering objects), ran full multimodal analysis (1061 objects, 88s). Searched Results table for "BENT":

| Original OCR | Family | Section | Confidence | Match | Validation |
|---|---|---|---|---|---|
| `1/4" BENT PL` | Bent Plate | `1/4" BENT PL` | High | **Confirmed Annotation** | **PASS** |
| `3/8" BENT PL` | Bent Plate | `3/8" BENT PL` | High | Confirmed Annotation | PASS |
| `1/2" BENT PL W/ 1/2"⌀x 1/2" BENT PL W/ 1/2"⌀x 9"` | Bent Plate | `1/2" BENT PL` | High | Confirmed Annotation | PASS |
| `BENT PL 3 PL 3` | Bent Plate | `3" BENT PL` | High | Confirmed Annotation | PASS |

Opened the detail modal for the `3/8" BENT PL` row: Original OCR preserved verbatim (`3/8" BENT PL`, page 17, real bounding box `1694.64, 1696.34, 1758.98, 1708.94`), Family **PLATE**, Section **`3/8" BENT PL`** (no fabricated AISC label), Prediction source **Annotation**, "Review: No review required." The UI copy literally states: *"Original PDF wording is always preserved above — the badge explains why it differs from the final label."*

The known, pre-existing `BENT PL 3 PL 3` fragment-duplication artifact (explicitly named as out-of-scope in the request) is **still present**, confirmed live — and correctly still classified as Bent Plate / Confirmed / PASS despite the garbled grouping, so it doesn't block anything. Not touched, per instructions.

**No fake AISC section anywhere. No regression.**

---

## G. Contextual candidate audit — what evidence does the engine actually consume?

Read `contextual_fabricated_steel.py` in full (864 lines) and tested it directly (not just via its own unit tests) against constructed and real scenarios.

- **Anchor requirement is real and enforced in code** (`rank_contextual_candidates`, lines 796–805): a candidate is only returned if at least one evidence item's `source` is `geometry`, `relationship`, or `drawing_language_profile` — dimension-text and local-text-only evidence can never by themselves clear the bar.
- **Empirically verified this holds even against strong same-line text**: fed `'3/8"'` with `line_text='3/8" BENT PL AT END CONDITION'` (obvious plate text right there) through `build_context_evidence`/`rank_contextual_candidates` directly — **zero candidates**. The anchor gate rejected it because every contributing evidence item was `dimension`/`local_text`, none `geometry`/`relationship`/`drawing_language_profile`. This is a stronger, more conservative result than expected, and it directly disproves "text alone can create a candidate" (§Section 18's own question).
- **One real, worth-naming imprecision found**: in `_score_bent_plate`/`_score_angle`/etc., the evidence item is labeled `source="relationship"` whenever *either* `rel.get("connection")` (a real graph-topology signal, see below) *or* `local.get("connection_terms")` (a pure same-line/nearby text match on `CONN`/`SHEAR`/`CLIP`/etc.) is true — both get the same `"relationship"` label, so a reviewer reading the evidence list cannot tell, from the label alone, whether "relationship" evidence came from graph topology or from nearby text. In practice this did **not** produce a false positive in any test I ran (connection-context evidence alone never reaches even the "possible" threshold, see §H Case 8), but it is a real terminology-precision gap worth fixing before this is trusted as a "relationship" signal in a UI. **Not fixed in this pass** (cosmetic/labeling only, no observed safety impact, and fixing it well means also deciding a naming scheme for the sibling case — deferred, see §Q).
- **The `relationship.connection` graph signal is real spatial-distance computation, layered on text-derived node classification**: `structural_graph.py` links a token to a nearby graph node via genuine bbox-distance thresholds (e.g. "connection/member proximity", distance-gated), but the node's own `"connection"` *kind* label is itself assigned via a text regex (`\b(?:CONNECTION|CONN\.?|CLIP\s*ANGLE)\b`) against nearby annotation text elsewhere on the page. So graph-sourced relationship evidence is a hybrid: real distance/topology math, over text-classified node types — not text-free geometric understanding, and not pure text-matching either. Precise characterization matters here and is stated exactly this way in §H/I.

---

## H. Explicit vs. locally implicit vs. truly anonymous (mandatory)

| Class | Definition | Count found | How verified |
|---|---|---|---|
| **EXPLICIT** | Local annotation itself names the object (`3/8" BENT PL`) | 112 confirmed across 6/7 projects (from the underlying audit); 4 real Burrville examples reconfirmed live in this session | Existing `confirmed_annotation`/parser path; never reaches the contextual layer at all (`_is_applicable_annotation` returns False once `structure_confirmed=True`) — verified by code and by the real 1061-token Burrville run, where **0** BENT_PLATE/PLATE/STANDARD_SECTION rows carried a populated contextual-candidate list |
| **LOCALLY IMPLICIT** | Selected token is bare (`3/8"`), but `BENT PL` sits on the same line/nearby | Constructed and tested directly (Case 1, §G) | Result: **abstains**. Same-line "BENT PL" text alone is *not* sufficient for the contextual layer to produce a candidate — it needs a geometry/relationship/DLP anchor too, which this constructed case didn't have. Real-corpus cases matching this shape were **not found producing a live candidate** in the actual analyzed Burrville document (0 of 1061 tokens produced any candidate at all — see §I) |
| **TRULY ANONYMOUS** | Bare dimension, zero nearby PL/PLATE/BENT/ANGLE/STIFF/GUSSET/BRG PL/CAP PL text | Tested directly: zero context → **abstains** (correct); synthetic real-shape geometry (`bent`, `plate_like` flags set, exactly as the real geometry pipeline *would* set them if implemented) + zero text → **BENT_PLATE score 0.66 (review_candidate)**, proving the scoring logic is structurally capable of true anonymous inference | **No real Class C example currently exists and produces a live candidate in this corpus**, because the geometry signals it needs are not yet computed on real PDFs (§I) |
| **NEGATIVE** | Should never become a candidate | 13 tested (camber, stud-distribution, reaction, date, elevation, rebar, bolt, weld, concrete, deck, hole/slot, BENTONITE, BENT GRIPSTAY, HSS-bent) | All correctly abstain via hard-negative blocking rules |

The research artifact (`research/contextual_element_inference/`, read in full by the verification pass) already self-labels its own `burrville_p17_bent_plate_dimension` case: *"This is not a true anonymous callout; the full local text is explicit. The contextual candidate remains review-only."* — so the artifact is **not overstating** its own findings, it just never names the three-way taxonomy explicitly. Recommend adding the exact `EXPLICIT`/`LOCALLY_IMPLICIT`/`TRULY_ANONYMOUS`/`NEGATIVE` labels to the artifact schema (small, requested improvement, not done in this pass — see §R).

**Direct answer to the mandatory question:** on the real, fully-analyzed 1061-token Burrville document, **zero** tokens of any class produced a live contextual candidate. 184 tokens were classification-eligible (182 `UNKNOWN` + 2 `TEXT_NOTE`); none had a qualifying geometry/relationship/DLP anchor. This is the clearest possible confirmation that the current implementation has **not yet proven true anonymous element inference on real data** — it has proven the *architecture* is capable of it (§G's synthetic-geometry test), gated entirely behind a dependency (real geometry shape features) that does not exist yet.

---

## I. Geometry reality check (critical)

Grepped the entire real geometry pipeline (`services/engineering/geometry_extractor.py`, `services/multimodal/feature_providers.py`) for the exact keys `contextual_fabricated_steel.py` reads: `bent`, `bent_shape`, `folded`, `l_shape`, `l_shaped`, `angle_like`, `plate_like`, `thin_plate`, `rectangular_plate`, `hss_open_end`. **Zero matches anywhere in the real geometry pipeline.** These flags check for dict keys and string categories that the production geometry extractor never populates.

**Direct, load-bearing consequence, quantified against the real, analyzed Burrville document:** `geometry_flags: {available: False, leader: False, plate_like: False, bent: False, l_shaped: False, hss_open_end: False}` for every single test case constructed from real corpus text in this session, and (per §H) zero candidates fired on any of the 1061 real analyzed tokens.

What **is** real, confirmed by directly reading a live production geometry object served through the actual UI: `{"object_id": "geom_9a148218a489", "kind": "leader", "bbox": [1776.24, 1701.48, ...]}` — real vector-derived leader-line objects, with real coordinates, do exist in the pipeline, and `"leader_endpoint_resolved"` (from `services/engineering/spatial_index.py`'s genuine nearest-leader-endpoint search, not naive nearest-neighbor) is a real, non-fabricated signal `contextual_fabricated_steel.py` correctly consumes.

**Bottom line:** `bent`/`l_shaped`/`plate_like`/`hss_open_end` are real, correctly-designed hooks into a capability that does not exist in the production pipeline yet — not fabricated, not placeholder-only-in-tests-with-no-real-purpose, but currently **always false in production**. `leader` is real and does fire on real data. This distinction must not be blurred, and the §G/§H findings above show the architecture correctly refuses to compensate for the missing geometry with text alone.

---

## J. Negative-test results

All 13 adversarial patterns named in the request (camber `c=1-1/4"`, stud distribution `[11;3;11]`, reactions/loads `40k`/`<55k>`, elevations `(-2'-0")`, slab-on-grade `6" SOG`, roof deck `1 1/2" RD`, rebar `#3@15"`, weld `3/16" weld`, bolt `3/4" A325`, hole/slot `1/2" slot`, dates `12/19/2025`, BENTONITE, BENT GRIPSTAY, HSS-bent-modifier) map to explicit regex checks in `_hard_negative_evidence` and were exercised directly. All correctly block candidate generation. One real corpus example independently confirms this working end-to-end: the research artifact's `gcdc_p48_slot_hole_negative` case — `line_text: "PROVIDE 2 1/2\" HORIZ LONG SLOT HOLES IN CONN PL AT ALL SLIP CONNECTIONS"` — correctly abstains via the `hole_or_slot` negative even though `CONN PL` is right there in the text.

---

## K. Shadow safety

Traced every write path from `analyze_contextual_candidates()`'s output to the final API response. It is added to `explanation["contextual_fabricated_steel"]` **after** `canonical = build_canonical_prediction(...)` has already been computed and is never read by anything upstream of that point. `contextual_fabricated_steel_enabled=true` changes only the `"mode"` label string and whether shadow-log writes happen — it does not unlock any code path that writes to `final_label`, `section`, `family`, `confirmed_annotation`, `match_status`, `needs_review`, or `review_status`. Verified directly against the live API response for the real Burrville analysis: every one of 1061 rows carries `contextual_fabricated_steel.live_prediction_changed: false` (hardcoded, not computed) and zero rows show any live prediction field influenced by it.

Also confirmed: my own live testing this session inadvertently mutated several **tracked** production files (`annotation_edge_cases.jsonl`, `documents/doc_....json`, `history.csv`, `multimodal_review_index.json`, `unknown_tokens.csv`, `upload_log.csv`) as a side effect of using the real upload/analyze UI — this is pre-existing, by-design application behavior (upload logging, review-index refresh), not something introduced by the DLP/contextual work, but per the constraint against leaving production-dataset mutation behind, I reverted all six via `git checkout` before finishing (confirmed clean via `git status`).

---

## L. LLM safety

`drawing_language_llm.py`: `NullLLMProvider` is the default and is what runs whenever `DRAWING_LANGUAGE_LLM_ENABLED` is unset (the default). Even when enabled, `AnthropicLLMProvider` only activates if the `anthropic` package is importable *and* an API-key env var is set — neither is true in this environment, confirmed (`anthropic` is not in `requirements.txt`, not installed). Tested the fail-safe contract directly by code inspection and by tracing every early-return in `propose_prose_rules`: provider exception, malformed JSON, missing `rules` array, and a hallucinated/non-verbatim `source_quote` (grounding check: the quote must appear, whitespace-normalized, in the actual source text passed to the model) — all correctly degrade to `(rules=[], error=<short string>)`, never raise, never partially apply. **Structurally impossible** for an LLM-produced rule to reach `RULE_STATUS_SOURCE_VERIFIED`: `propose_prose_rules` hardcodes `rule_status=RULE_STATUS_PROPOSED_INFERENCE` on every rule it ever returns, and `resolve_designation`/`resolve_hss_thickness_hint` (the only functions that let a rule touch a prediction) require `rule_status == RULE_STATUS_SOURCE_VERIFIED` exactly.

---

## M. Test results (exact counts)

- Targeted suites (drawing_language_profile, contextual_fabricated_steel, hss_completion + hss_missing_thickness_review, canonical_contract, bent_plate_annotations, prediction_orchestrator, multimodal_pipeline + multimodal_validation_engine, engineering_pipeline, documents_api): **all passed individually** (17, 7+13 subtests, 29, 17, 14+4 subtests, 3, 17, 7, 10 — zero failures).
- Full backend suite (before this audit's fixes): **541 passed, 1 skipped, 84 subtests passed, 0 failed** in 35.23s.
- Re-run after this audit's two fixes (vocabulary allowlist + fusion_engine field passthrough), combined targeted set: **104 passed, 0 failed, 17 subtests passed** in 7.04s.
- Frontend: **76 passed (12 test files), 0 failed**; `npm run build` clean, no errors.
- **Confirmed, reproducible, pre-existing test-isolation defect** (not introduced by this work): `tests/test_bent_plate_annotations.py::BentPlateEdgeCaseTests::test_record_edge_case_uses_bent_plates_category` appends a real line to the tracked file `backend/training/annotation_edge_cases.jsonl` every time it runs. Reproduced twice in this audit; reverted both times via `git checkout`. **Not fixed** — it's in a partner-authored test file unrelated to the DLP/contextual scope; flagged as a recommended follow-up (§R), not fixed here per the instruction not to expand scope beyond what this feature strictly needs.

---

## N. Browser validation

Full live validation performed. Started an isolated backend (port 8010, `DRAWING_LANGUAGE_PROFILE_ENABLED=true`, `DRAWING_LANGUAGE_PROFILE_SHADOW=true`, `CONTEXTUAL_FABRICATED_STEEL_SHADOW=true`) and frontend (port 5183, pointed at it via `VITE_API_BASE`) in this worktree — deliberately different ports so nothing touched the user's own running dev servers on 8000/5173. Hit one real environment snag along the way (dashboard showed "Backend unavailable" even though `curl` succeeded) — root-caused to CORS (the frontend's non-default port wasn't in `CORS_ALLOW_ORIGINS`), fixed by restarting the backend with the extra origin added; this was a **test-harness configuration issue, not a product defect** (confirmed: after the CORS fix, everything worked correctly). Uploaded and fully analyzed the real `Burrville ES - ST.pdf` fresh through the actual UI (not a cached artifact — confirmed via backend logs showing a genuine 79–88s multimodal analysis run, not a sub-2-second cache hit). Verified BENT PL rows (§F) and the prediction-detail modal live. GCDC was not uploaded through the UI directly (its file is 44MB, over the browser file-upload tool's 10MB limit) — verified instead via direct backend calls against the exact same `extract_engineering_document`/`predict_from_context` functions the UI calls (§D/§E), which is a stronger, more precise form of verification for a production-safety audit than visual inspection alone.

---

## O. Performance

- DLP profile: built **once per document**, cached to disk keyed by content hash; confirmed live — first Burrville extraction+analyze took the expected time for a 29-page/918-object document, a second forced re-analysis of the same document hit the cache (visible as a sub-2-second `analysis finished` log line vs. the first run's real, uncached ~80–90s).
- No `for each token: scan every vector on page` pattern found — geometry/graph features are fetched once per token from already-built providers (`GeometryFeatureProvider`/`GraphFeatureProvider`), not recomputed from raw vectors per call.
- One real, minor scaling note: `count_observed_applications`'s informational-only regex scan runs once per designation rule over the full document text (cheap, bounded by rule count, not token count) — not a concern at current corpus scale.
- The LLM call, when enabled, is bounded to ≤20,000 characters of legend/notes text and happens at most once per document (confirmed by code path, not just by flag default).

---

## P. Defects found and fixed

**1. Contextual/DLP explanation fields silently dropped before reaching the API/UI.**
- *Problem:* `explanation["drawing_language_profile"]` and `explanation["contextual_fabricated_steel"]`, computed correctly by `orchestrator.predict_from_context`, never appeared anywhere in the real `/api/documents/.../analysis` response — confirmed live against all 1061 real Burrville predictions (`rows_with_contextual_key_populated: 0`).
- *Root cause:* `services/multimodal/fusion_engine.py`'s `WeightedFusionEngine.predict()` reconstructs a fixed-field `Explainability` dataclass from `explanation`, copying only a pre-existing, explicitly enumerated list of field names. The two new keys weren't in that list, so they were silently discarded on every real analysis, even with the shadow flag on.
- *File(s):* `services/multimodal/contracts.py` (`Explainability` dataclass), `services/multimodal/fusion_engine.py` (field-copy call site).
- *Fix:* added `drawing_language_profile: Dict[str, Any] = field(default_factory=dict)` and `contextual_fabricated_steel: Dict[str, Any] = field(default_factory=dict)` to `Explainability`, threaded both through in `fusion_engine.py`'s construction call. Purely additive (new optional fields with defaults at the end of the dataclass; `to_dict()` uses generic `asdict()` so no other change needed).
- *Verified:* forced a real re-analysis (`?force=true`) of the same Burrville document after the fix — `rows_with_contextual_key_populated: 1061` (all of them), confirming the field now survives to the served API response. Full targeted test suite re-run clean (104 passed).

**2. Vocabulary-rule extraction promoted regex noise to `SOURCE_VERIFIED` trust.**
- *Problem:* real GCDC PDF → `extract_vocabulary_rules` (reusing `document_prior`'s same-line `KEY = VALUE` regex) produced 11 entries including `EAST→west`, `NORTH→south`, `Z→rod or hilti hit hy 200 safe set`, `POST→tensioned or` — ordinary prose the regex misparsed — all stored at the same `RULE_STATUS_SOURCE_VERIFIED` trust tier `contextual_fabricated_steel.py` treats as equivalent to a hand-verifiable `PL=PLATE` row.
- *File:* `services/engineering/drawing_language_profile.py`.
- *Fix:* added `_VOCABULARY_MEANING_ALLOWLIST` (angle, plate, bent_plate, wide_flange, hss, pipe, channel, beam, column, brace, stiffener, connection, continuous, gusset, closure, long leg vertical/horizontal, drag strut) and gated promotion on it; bumped `EXTRACTOR_VERSION` to `dlp_extractor_v2` so the stale, pre-fix cached GCDC profile was correctly invalidated rather than silently reused (verified live).
- *Verified:* re-ran real GCDC extraction post-fix — `vocabulary_rules count: 0` (down from 11 garbage entries; GCDC's real `PL`/`LLH`/`LLV` abbreviations are in a two-column table layout neither the old nor new regex can parse — a real, disclosed limitation, not fixed in this pass, see §I/§R). Full targeted test suite re-run clean.

**No other defects found that meet the bar for a fix in this pass.** The evidence-source labeling imprecision (§G) and the two-column abbreviation-table gap (§I) are real, disclosed, but explicitly deferred — see §R.

---

## Q. Current capability boundary

| Capability | Status | Evidence |
|---|---|---|
| Explicit BENT PL detection | **Production-capable** | Live UI, real Burrville PDF, `Confirmed Annotation`/PASS, no fake section (§F) |
| Project-specific W/C/HSS designation substitution | **Production-capable** (flag defaults off) | Real GCDC PDF, all 8 rules, `PROJECT_RULE_RESOLVED`, isolation rigorously proven (§C/§D) |
| DLP source verification (explicit rules) | **Production-capable** | Explicit sentence trusted immediately, no corroboration required, LLM rules structurally barred from this tier (§C/§L) |
| DLP source verification (vocabulary rules) | **Partially capable, real gap disclosed** | Garbage filtered (fixed this pass); real two-column abbreviation tables not yet parseable at all (§I) |
| DLP LLM proposal (connection/relationship/implied-element/grammar) | **Shadow/research only, by design** | Never auto-applied to any prediction; requires human review before promotion (§C/§L) |
| Context candidate generation (architecture) | **Implemented, shadow-only** | Anchor-gated, negative-filtered, verified not to leak into live predictions (§G/§K); explanation now correctly reaches the API after this pass's fix |
| True anonymous-dimension classification on real PDFs | **Not yet demonstrated** | 0 of 1061 real analyzed tokens produced a candidate; architecture proven capable only with synthetic geometry (§H/§I) |
| Real bent-shape / L-shape vector recognition | **Not implemented in production** | Confirmed absent from the entire geometry pipeline by direct grep; always `false` on real data (§I) |
| Leader/ownership evidence | **Real, implemented** | Genuine spatial-index nearest-leader-endpoint search, confirmed live via a real `kind: "leader"` geometry object with real coordinates (§I) |
| Graphical legend symbols | **Not implemented** | No symbol-recognition code found anywhere in this pass; out of scope per the request |
| CANT/backspan propagation | **Not implemented** | Represented nowhere yet; correctly not attempted (never claimed) |
| Plan-to-detail relationship graph | **Not implemented** | No code found for this; correctly out of scope |
| Automatic implied-item quantity generation | **Not implemented** | `implied_element_rules` are represented and scored as *candidates only*; nothing generates a takeoff quantity from them |

---

## R. Recommended next step

Based only on what this audit actually proved — **not** a recommendation to write more contextual-inference code yet:

1. **Ship the two fixes in this pass as-is** (both are small, additive, fully test-covered, and close a real correctness gap: the shadow layer's output was invisible before this audit, and vocabulary rules were trusted noise).
2. **Do not invest further in the contextual-candidate scoring logic** until real geometry shape features (`bent`, `l_shaped`, `plate_like`, `hss_open_end`) exist in the production pipeline — the architecture is correct and already proven (synthetically) to work once that dependency is real; building more scoring rules on top of a permanently-false geometry signal would not move the needle on real documents.
3. **Fix or accept the pre-existing test-isolation defect** (`annotation_edge_cases.jsonl` mutation) as a small, separate, low-risk follow-up — not done here since it sits in a partner-authored test file outside this feature's scope.
4. **Disambiguate the `"relationship"` evidence-source label** (§G) into a text-derived vs. graph-derived variant before this evidence is surfaced to a human reviewer as if it were one signal.
5. **Improve the research artifact** (`research/contextual_element_inference/`) to explicitly tag each case `EXPLICIT`/`LOCALLY_IMPLICIT`/`TRULY_ANONYMOUS`/`NEGATIVE` per §H's taxonomy — the underlying judgment is already sound (the artifact's own review notes already self-disclaim "not anonymous" cases correctly), it just isn't labeled with the exact taxonomy requested.
6. **GCDC's two-column abbreviation-table gap** (§I) is a real, scoped, well-understood follow-up (a layout-aware legend-table parser) — worth doing, but it is new capability, not a bug fix, and is correctly out of scope for this pass.

The central question this audit was built to answer: **did we build a safe, project-aware architecture, or heuristics that only look successful because nearby text still supplies the answer?** The evidence says: the *safety* properties (isolation, shadow-only, no fake sections, no LLM-authority, no live-prediction leakage) are real and rigorously verified. The *contextual-inference* capability is architecturally sound but **not yet demonstrated on a single real token in this corpus** — it is currently blocked entirely on a geometry dependency that doesn't exist yet, and this audit found and fixed the specific defect (the fusion_engine field-drop) that was hiding this fact from view.
