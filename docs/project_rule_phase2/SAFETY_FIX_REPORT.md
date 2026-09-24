# Project-rule Phase 2 — Safety Fix Report (Gate 1)

Recorded 2026-09-23. Uncommitted on `bassam/project-rule-intelligence` (on top of `d660ffb`).

All three fixes are behind **default-off** flags. With default settings every output is unchanged:

- the full suite matches the baseline (+18 new tests);
- the 7-PDF benchmark is byte-identical to Phase 1 (latency excluded);
- the synthetic benchmark is byte-identical.

| Defect | Status | Flag (default) |
|---|---|---|
| A. Duplicate schedule definitions resolved first-row-wins | **Fixed in shadow**; legacy map **fixed behind flag** | `SCHEDULE_MARK_CONFLICT_GUARD_ENABLED` (off) |
| B. Resolver always sees `page_role="UNKNOWN"` | **Fixed behind flag** | `PROJECT_RULE_PAGE_ROLE_ENABLED` (off) |
| C. `2 L…` fused into the `2L` family | **Fixed behind flag** (tokenizer + lock) | `QUANTITY_PREFIX_GUARD_ENABLED` (off) |

## A. Conflicting duplicate schedule definitions

**Shadow policy** (`schedule_grid._definitions`), independent of row order:

| Situation | Result |
|---|---|
| Same mark + same section + same lifecycle | One `definition` keeping every source (page, region, row bbox); `duplicate_group_id = mark|section|lifecycle` |
| Same mark + different section | Every row `conflict` / `conflicting_duplicate_mark`; no mapping |
| Same mark + same section + different printed lifecycle (e.g. EXISTING vs new) | Every row `conflict` / `conflicting_lifecycle`; no mapping |
| Same mark + same section + different plate/component text | Section kept (every downstream contract carries the section only), `review_required=true`, `attribute_conflicts=["components"]`, both components retained, component quantity `null` |

Records now carry `lifecycle_status`, taken **only** from the printed schedule title (`DEMO…`, `REINF…`, `EXIST…`, `NEW`), otherwise `unknown`.

**Legacy map.** `schedule_mark_map(grids, drop_conflicts=…)`. The default keeps first-row-wins byte for byte. With the flag on, a mark defined with two sections maps to nothing, and the result is the same for any row order. It is not enabled by default because it changes public behaviour. Real-corpus impact if enabled: **0 marks** (the legacy map is empty on all 7 projects).

Tests (`tests/test_project_rule_safety_phase2.py::DuplicateScheduleDefinitionTests`): identical rows on one page, identical rows across repeated sheets, conflicting sections, conflicting plate attributes, conflicting lifecycle, reversed row order (shadow and guarded legacy), legacy default versus guard.

## B. Occurrence page role

**Root cause.** `staged_pipeline._apply_project_rule_resolution` hard-coded `page_role="UNKNOWN"`, although the `legend_profile` it receives already carries `context_pages` (the output of `legend_profile.detect_context_pages`, the existing source of truth).

**Fix** (`staged_pipeline._occurrence_page_role`, flag on):

- a page listed in `context_pages` gets its context role;
- any other page with a known number gets `DRAWING` (the classifier's own name for a non-context page, now accepted by the resolver);
- `UNKNOWN` is used only when the occurrence has no page or the profile has no classification.

No second classifier was added.

The four concerns, reported separately:

| Concern | Behaviour with the flag on |
|---|---|
| Identity resolution | Drawing-page occurrences resolve as before. A normal direct resolver call still rejects a context page; the flag-enabled overlay explicitly opts into semantic identity resolution for context evidence. |
| Occurrence classification | A resolved context occurrence is stamped `object_scope=occurrence_scope="context_definition"` and `countable_occurrence=false`, with document/page/bbox/rule provenance. |
| Takeoff eligibility | Context definitions are forced to `takeoff_eligible=false`; plan/detail occurrences keep their own eligibility. |
| Final count/export | Quantity and all traced takeoff/export routes reject the context occurrence. A separate eligible plan occurrence may consume the same-document rule. |

The invariant this enforces: a valid rule can make a real drawing occurrence semantically usable, but a schedule, legend, note or specification definition occurrence never becomes countable just because its identity was resolved.

**Real-corpus impact if enabled.** GCDC is the only project with abbreviation rules (8). Of its rule-matching tokens, 4 on drawing pages resolve with and without the flag. The one page-5 `HSS8X4` on a `LEGEND` page now resolves identity to `HSS8X4X1/4` as definition evidence, but is explicitly non-countable and excluded from takeoff. No other project is affected.

Rules remain document-scoped at the overlay boundary. An occurrence explicitly naming another document cannot consume the profile, and the decision records both source and occurrence document identifiers.

Tests (`OccurrencePageRoleTests`): direct context calls reject without opt-in; GCDC page 5 resolves as evidence-only with provenance; a plan occurrence remains eligible; context and schedule definitions are absent from quantity/export; cross-document use is rejected; exact sections are untouched; mixed-content `SCHEDULE` pages are not suppressed wholesale; `UNKNOWN` appears only without a page or classification; flag off gives legacy output.

## Evidence classification and schedule-label overcount finding

These categories must not be conflated:

| Evidence class | Current result |
|---|---|
| Code-wired behaviour | The structured schedule/project-rule path contributes zero counted rows with default flags. Existing ordinary token extraction is a separate path. |
| Synthetic regression | Author-written fixtures exercise gates and deterministic contracts; they are regression evidence, not real-corpus accuracy. |
| Unlabelled real-corpus discovery | Ordinary token extraction counted section-shaped definition labels inside all three development schedules: Burrville 59/61, GCDC 102/102, Springhill 58/64, total **219/227**. This is a likely source of section overcount. |
| Reviewer-approved measured accuracy | **None.** All reviewer-package records remain unapproved. |

The precise statement is therefore not “schedule rows were uncounted.” Zero rows were counted through the schedule/project-rule path, while 219 of 227 printed schedule definition labels were treated as ordinary drawing occurrences by the existing token path.

## C. `2L` family versus a quantity of two

**Real-corpus occurrences** (word level, all 7 PDFs; absence elsewhere is not proof of safety):

| Form | Occurrences |
|---|---|
| Fused `2L…` (a real double angle) | GCDC 10 (`2L6X6X1/2` ×4, `2L4X4` ×2, `2L8X8X5/8` ×2, `2L4X4X3/8`, `2L4X3X3/8`); Burrville 2; Sidwell 4 |
| `(n) SECTION` | GCDC `(2) HSS10X10X3/8` ×8; Ketcham `(2) L…` ×4, `(1) C6X10.5…`; Sidwell `(40) W12` |
| `n SECTION` (space) | `2 L1X1X1/4` on Burrville p.19, Sidwell p.27, Springhill p.15; `2 HSS16X0.5` on Springhill |
| `n-SECTION` | none found |

**Trace and root causes:**

1. **Tokenizer** (`token_extractor.extract_engineering_token_records` → `_candidate_windows`). Every multi-word window also gets a no-space joined variant (so `W18 X 35` can be repaired), which turns words `2` + `L1x1x1/4` into a **`2L1x1x1/4` token**. This happens on real data: the 3 `2 L1X1X1/4` occurrences each produced a fused `2L1X1X1/4` token (plus the correct `L1X1X1/4`), and the fragment grouper then merged them into `2L1x1x1/4 L1x1x1/4`.
2. **Lock** (`exact_section_predictor.resolve_trusted_explicit_section`). Whitespace normalisation turns `2 L4X4X1/2` and `2-L4X4X1/2` into `2L4X4X1/2` and **locks the double angle**. `(2) L4X4X1/2` and `2 HSS8X8X3/8` are left unlocked.

**Fix (flag on):**

- **Tokenizer.** No joined variant is offered when the window starts with a bare count (`2`, `(2)`) followed by a word that starts with a letter other than the `X` separator. The spaced token still forms; `W18 X 35` repair is unchanged.
- **Lock.** A separated leading count (`2 `, `(2) `) is stripped before matching, so the lock applies after quantity tokenisation and the count stays outside the section identity. `2-SECTION` is ambiguous and gets no lock (it falls through to the normal review path). Fused `2L…` is untouched.

The blast radius was narrowed by measurement:

| Tokenizer guard version | Real tokens changed |
|---|---|
| First version (any follower) | Hundreds of mixed-number dimension joins such as `11/2"`, plus fraction fragments |
| Letter follower | Plus `3X1` / `5X31/2X5/16` fragments on 1200 K and Ketcham |
| Final (letter follower, not `X`) | **Exactly the 3 `2L1X1X1/4` defect tokens**; nothing added |

**Call sites affected when enabled:**

- Tokenizer: `token_extractor.extract_engineering_token_records`, whose only production caller is `document_intelligence.enrich_document_structure` (every PDF extraction).
- Lock: `orchestrator.predict_from_context` (lines 416–419), `member_resolution`, and `canonical_contract` provenance.

No quantity field is written anywhere. The count is simply not part of the identity.

Tests (`SeparatedQuantityTests`): fused `2L` is kept with the flag off or on; a separated count is a quantity (`2 L`, `(2) L`, `2 HSS`); a hyphenated count is not locked; the tokenizer does not glue a count onto a section and still repairs `W18 X 35`; flag off keeps the known legacy defect (pinned).

## Verification

| Check | Result |
|---|---|
| `tests/test_project_rule_safety_phase2.py` | 18 passed |
| Schedule / project-rule / parser / tokenizer / exact-lock tier (21 files) | 356 passed, 1 skipped |
| Full backend suite | 1360 passed, 9 failed (the same pre-existing 9), 4 skipped |
| 7-PDF benchmark, two runs | deterministic; byte-identical to Phase 1 (latency excluded) |
| Synthetic benchmark | byte-identical to Phase 1 |
| Unexpected change to an exact section, quantity or eligibility (defaults) | none |

## Still open

- None of the three flags is enabled. Enabling B resolves one already-ineligible GCDC legend occurrence as explicit definition evidence; enabling C changes 3 real tokens.
- The legacy `schedule_grid` row still falls back to whole-row text when the SIZE cell is empty (the shadow path does not).
- The 71 H5 schedule-region tokens on drawing pages remain `takeoff_eligible` in production. This is the existing `context_scope` policy and was not changed here.
