# Project-rule Phase 1 — Baseline State (Gate 0)

Recorded 2026-09-23. Read-only audit; no production code changed before this document.

## Repository state

| Item | Value |
|---|---|
| Worktree | `C:\Users\Bassam\git\ai-dynamic-regex-integration` |
| Branch | `main`, tracking `origin/main`, 0 ahead / 0 behind |
| HEAD | `77f0ea03692358e0718f3975156f23bd4808c31c` (= expected audited SHA) |
| Pre-existing drift (preserved, not touched) | `M backend/training/documents/doc_0d910a43b4a021e3.json`, `M backend/training/multimodal_review_index.json`, `M backend/training/upload_log.csv`; untracked `backend/training/documents/doc_{06009aaef05256fa,71b87553b617833f,8c6dfa0d820abb35,fba71e49fb20a89e}.json`, `backend/training/label_reconstruction_tmp/`, `docs/deep_research_project_rule_intelligence/`, 17 `docs/validation/phase_{c,d1,d2}_*` files |

No drift overlaps the project-rule surface.

## Verified architecture (static wiring, traced from code)

| Flow | Evidence | Finding |
|---|---|---|
| PDF words | `services/pdf_parser.py::extract_document_structure` | One flat `document["words"]` list over **all pages**, each word has `page_number` + `bbox`. |
| Schedule grid | `services/extraction_engine.py:37` → `schedule_grid.attach_schedule_grid` → `build_schedule_grids(document["words"])` | Runs on every page, **not gated by page role**. The only page filter is `_page_has_mark_size_headers`: literal words `MARK` and `SIZE` must both appear on the page. A schedule embedded in a plan page is eligible only if it uses exactly those header words. |
| Row model | `schedule_grid._parse_body_row` | `{mark, size_text, section, catalog_valid, plate_text, plate_role, member_plate_roles}`. No row bbox, no cell bboxes, no status/reason. Grid carries `page` + `kind` only. |
| Mark grammar | `schedule_grid._MARK_RE = ^(?:L\|C)\d+[A-Z]?$` | Only `L1`, `C1`, `L1A` forms. `C-1`, `LB-1`, `B-1` are rejected. |
| Legacy map | `schedule_grid.schedule_mark_map` | `mapping.setdefault(mark, section)` — **duplicate marks with different sections silently keep the first row** (no conflict detection, no review routing). |
| Prior merge | `document_prior.attach_document_prior` (flag `SCHEDULE_MARK_MAP_ENABLED`) | Schedule map merged into `document_prior.mark_map` (setdefault). Separate regex `_MARK_SECTION_RE` also fills `mark_map` from free text (`BM3 W27X84`), used only as ranking boost. |
| Mark resolution | `orchestrator.py:431-437` → `schedule_grid.resolve_schedule_mark` | Only after `protected_exact_section` is empty (exact lock wins). Only bare `L/C` marks. A hit sets `protected_exact_section = mapped` and `token_record["schedule_mark_resolved"]`. |
| Exact lock | `orchestrator.py:416-419` (`resolve_trusted_explicit_section`, `services/exact_section_predictor.py:111`), `section_text_locked` / `schedule_mark_locked` at `orchestrator.py:1029-1052` | Present and authoritative. Schedule-mark hits get the same lock strength as exact text. |
| Contract | `canonical_contract.py:264` | `schedule_mark_resolved` → `MatchStatus.PROJECT_RULE_RESOLVED`. |
| Plate roles downstream | `rg member_plate_roles\|plate_text` | **Only in `schedule_grid.py`.** `bottom_plate` / `hung_plate` / PLATE-cell text never reach any prediction, canonical contract, takeoff row, or API response. They exist only in the side artifact `document["schedule_grid"]`. |
| Page roles | `legend_profile.detect_context_pages` | Context roles only (LEGEND, ABBREVIATIONS, GENERAL/STRUCTURAL NOTES, SPECIFICATIONS, VISION_REQUIRED). Drawing/schedule pages have no role (`None` / `"DRAWING"` in diagnostics). `VISION_REQUIRED` = context heading + <40 chars text; no vision call site exists anywhere. |
| Deterministic abbreviation rules | `legend_profile.extract_abbreviation_rules` → `legend_profile["abbreviation_rules"]` | Quoted-trigger regex only. |
| LLM rules | `legend_profile_hook` → `legend_llm_provider` → `project_rules.validate_rule` | Gated by `LEGEND_PROFILE_LLM_ENABLED` (default **false**). |
| Resolver | `staged_pipeline._apply_project_rule_resolution` → `project_rule_resolver.resolve_token` | LABEL_SUBSTITUTION only. **Caller always passes `page_role="UNKNOWN"`**, so the `_CONTEXT_PAGE_ROLES` rejection and rule `scope.page_roles` gates are inert in production. Overlay never writes `takeoff_eligible`. |
| Other 9 rule types | `rg` for each constant outside `project_rules.py` / `legend_llm_provider.py` | **No downstream consumer.** Only `INHERITANCE_RULE` / `DERIVED_INSIGHT` are named in the resolver (as exclusions). |
| Takeoff eligibility | `canonical_contract.member_prediction_takeoff_eligible` (`orchestrator.py:1823`), `context_scope.annotate_takeoff_scope` | Derived from `match_status` ∈ trusted set, which **includes `PROJECT_RULE_RESOLVED`**. So schedule-mark resolution does not *write* `takeoff_eligible`, but it **changes the derived value** for a bare mark occurrence (unresolved `L1` → not eligible; resolved `L1`→`W8X21` → eligible; see `tests/test_struct_notation.py::MarkResolutionTests`). Schedule pages are not context pages, so SIZE-cell tokens on a schedule page remain `takeoff_eligible=True`. |

### Differences from the prior research audit

1. The audit said identity resolution and takeoff eligibility are structurally orthogonal. True for `project_rule_resolver` (staged overlay). **Not true for the orchestrator schedule-mark path**: resolution flips derived eligibility of the mark occurrence. This is plausibly intended (a plan mark *is* a member), but it is a coupling, not orthogonality.
2. The resolver's page-role gates exist but are fed a constant `"UNKNOWN"`.
3. Duplicate schedule marks are resolved first-wins, not routed to review.
4. Plate roles are extracted but not carried into any output contract.

None of these contradicts the Phase 1 plan's premise (current behavior is narrow and deterministic). Gate 1 measures them; this sprint changes none of them in production.

## Current flags (defaults, `backend/config.py`)

| Flag | Default |
|---|---|
| `SCHEDULE_GRID_ENABLED` | true |
| `SCHEDULE_MARK_MAP_ENABLED` | true |
| `LEGEND_PROFILE_ENABLED` | true |
| `LEGEND_PROFILE_LLM_ENABLED` | **false** |
| `DOCUMENT_PRIOR_ENABLED` | see `config.py` (unchanged) |
| `SHADOW_CONTEXT_PAGE_GATE_ENABLED` | false |

## Terminology handling (current, probed via `extract_engineering_tokens` + `resolve_trusted_explicit_section`)

| Input | Tokens | Whole-string exact lock | Note |
|---|---|---|---|
| `W10X33` | `W10X33` | `W10X33` | locked |
| `HSS8X4` | `HSS8X4` | — | incomplete, not locked |
| `L4X4X1/4` | `L4X4X1/4` | `L4X4X1/4` | locked |
| `L1` | `L1` | — | mark (`MEMBER_MARK`) |
| `ANGLE 4X4X1/4` | `4X4X1/4` | — | prefix cue **unsupported** (safe miss) |
| `4X4X1/4 ANGLE` | `L4X4X1/4` | `L4X4X1/4` | suffix cue supported |
| `4X4X1/4` | `4X4X1/4` | — | unresolved (correct) |
| `CHANNEL` | — | — | unresolved (correct) |
| `TUBE 4X4` | `4X4` | — | not HSS (correct) |
| `BENT PLATE 12X4X3/8` | `PLATE12X4X3` | — | annotation `BENT_PLATE` (not L); token text truncates `3/8` |
| `2L4X4X1/2` | `2L4X4X1/2` | `2L4X4X1/2` | double angle |
| `2 L4X4X1/2` | `L4X4X1/2` | **`2L4X4X1/2`** | **whole-string lock collapses a spaced quantity into the 2L family** when a token's raw text carries the space |
| `LB-1`, `C-1` | — | — | hyphen marks unsupported |

## Real-corpus probe (7 projects, `~/Downloads/PDF & Excel (1).zip`, extracted to scratchpad, not committed)

`build_schedule_grids` on every real document:

| Project | Pages | Pages with MARK+SIZE words | `schedule_mark_map` |
|---|---|---|---|
| 1200 K | 39 | 32 | `{}` |
| Burrville | 29 | — | `{}` |
| GCDC Building | 81 | 5, 56 | `{}` |
| H5 Herndon | 23 | 3, 7, 8, 23 | `{}` |
| Ketcham | 17 | 10, 12 | `{}` |
| Sidwell | 45 | — | `{}` |
| Springhill ES | 28 | — | `{}` |

**The current schedule-mark path resolves zero marks on the real corpus.** What the MARK+SIZE pages actually contain:

- H5 pp. 7–8: `EXISTING COLUMN SCHEDULE` embedded in a *foundation plan* page, rows `C-1 W8x24`, `C-2 W8x24` (hyphenated marks → rejected by `_MARK_RE`), sharing a header band with a concrete PIER schedule.
- H5 p. 23: column *reinforcing* schedules (`RI-1 … W8x31`) — the W section is the host column, not the mark's identity. Must never become `RI-1 → W8X31`.
- Ketcham p. 10: bearing-plate schedule (`BP1 4"x14" 1/2"`) — fabricated components, no rolled section.
- GCDC p. 56, Ketcham p. 12, 1200 K pp. 25/32, Sidwell p. 30: concrete footing/pier/FRP/beam-bar schedules and legends — correct abstention.
- GCDC pp. 77–79 column schedules are level×location matrices with no MARK/SIZE header (out of this grid's shape).

## Test baseline

Interpreter: `backend/venv/Scripts/python.exe` (system `python` lacks pytest).

| Command (from `backend/`) | Result |
|---|---|
| `python -m pytest -q tests/test_project_rules.py tests/test_project_rule_resolver.py tests/test_legend_profile.py tests/test_schedule_spatial_pipeline.py tests/test_protected_exact_label.py tests/test_exact_section_predictor.py tests/test_semantic_takeoff_projection.py tests/test_struct_notation.py` | 204 passed, 1 skipped |
| `python -m pytest -q` | 1324 passed, **9 failed**, 4 skipped |

Pre-existing failures (before any Phase 1 edit):

- `tests/test_a2_a7_human_review.py` — 8 tests (A2/A7 gold SHA-256 mismatch with a review artifact).
- `tests/test_repeated_detail_linker.py::RepeatedDetailLinkerTests::test_validation_does_not_count_as_eligible_member`.

## Supported vs unsupported today

Supported: `L1`/`C1`/`L1A` marks in a MARK|SIZE column-band table with a catalog-valid SIZE; `WITH BOTTOM/HUNG PLATE` retained as a row role (artifact only); exact-section lock precedence; LABEL_SUBSTITUTION via quoted legend rules.

Unsupported: hyphenated/prefixed marks; schedules without literal `MARK`+`SIZE` headers; duplicate-mark conflict detection; row/cell provenance; plate/component data in output contracts; quantity-per-assembly; scope other than whole-document; vision.
