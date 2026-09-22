# Pre-Orchestrator Consolidation Review

Baseline: `main` @ `578aa7430e4b3871c31fcb23c4f5c56272de1133`. Final pre-orchestrator-decomposition consolidation
pass: inspected every remaining recorded consolidation opportunity, found none still open, then ran a fresh
scoped search for genuine utility/parsing/formatting/configuration duplication and the dynamic test-loader
count. Selected exactly 3 low-risk production consolidations and 1 test-loader consolidation; implemented all
4; zero rejected after implementation (all measured a real net simplification before being kept).

## Remaining recorded opportunities (Phase 1)

`refactor-opportunities.md`'s 7 items are all already `IMPLEMENTED`/`RESOLVED`/`REJECTED`-by-design — none
open. `refactor-roadmap.md` Phase 6 ("Backend module-boundary cleanup") is resolved with no code change
(`fusion_engine.py`/`modular_fusion.py`, no overlap). Phase 9 ("Configuration consolidation") in that document
is a narrow, unrelated metadata task (`.env.example` completeness, `skills-lock.json` provenance gaps for 2
Claude skills) — not backend utility/config-reading duplication, out of this task's scope, left untouched.
**Conclusion: zero remaining recorded backend consolidation candidates.** This phase therefore ran its own
scoped search (regex/normalization/boolean-env-parsing patterns across `services/`) per the task's own
fallback instruction, while explicitly not reopening any already-decided item (StatsCards/KpiCard, badge/chip,
semantic shims, fusion_engine/modular_fusion, the 4 deleted engineering modules, the 14 verified-active
generic modules).

## Dynamic test loaders (Phase 2) — count corrected: 5, not 7

Two independent greps (`spec_from_file_location` and the broader `importlib.util|module_from_spec|
exec_module` set) both return exactly **5** files, not the 7 `unused-candidates.md` §9 claimed — the same
kind of imprecision already found and corrected in the prior phase's "14 candidates" discrepancy.

| Test | Loads | Classification | Reason |
|---|---|---|---|
| `test_anonymous_dimension_resolver_context.py` | `services/annotation/anonymous_dimension_resolver.py` (a real package module) | **MIGRATE_TO_NORMAL_IMPORT** | No isolation purpose found. The sibling test `test_anonymous_dimension_resolver.py` already imports the same module normally; so do 2 real production callers (`orchestrator.py`, `extraction_noise_filter.py`). Only a single plain function (`resolve_anonymous_dimension`) is used — no dataclass/enum/`isinstance` concern, no module-level mutable state, no optional-dependency isolation need. Dual module identity (this file's private `anonymous_dimension_resolver_under_test` vs. the real `services.annotation.anonymous_dimension_resolver`) was pure risk with no offsetting benefit. |
| `test_evaluate_pipeline_holdout.py` | `scripts/evaluate_pipeline.py` | **KEEP_ISOLATION_REQUIRED** (necessity, not preference) | `scripts/` has no `__init__.py` — confirmed not a package — so `spec_from_file_location` is the only way to load it as a module at all. |
| `test_import_review_decisions.py` | `scripts/import_review_decisions.py` | **KEEP_ISOLATION_REQUIRED** | same reason |
| `test_ml_association_review_kit_builder.py` | `scripts/build_ml_association_review_kit.py` | **KEEP_ISOLATION_REQUIRED** | same reason |
| `test_select_double_review_subset.py` | `scripts/select_double_review_subset.py` | **KEEP_ISOLATION_REQUIRED** | same reason |

None of these 5 loaders were ever treated as evidence for any production-module reachability conclusion in
this or any prior phase — they load scripts/one package module for their own tests' use, nothing about
production entrypoints.

## Fresh candidate search (Phase 3) — genuine duplication found

A targeted grep sweep (not a repeat of the 908-file audit) for the task's named categories — duplicated
regex, normalization, boolean-env-var parsing, trivial wrappers — across `services/` turned up:

- **Zero** remaining shape-token regex or inline `.upper().replace(...)`-chain duplication (the one
  instance that existed, in `matching_engine.py`/`suggestion_engine.py`, was already resolved by their
  deletion in the dead-module-removal phase).
- **One** exact-duplicate boolean env-var parser: `services/multimodal/feature_providers.py::
  _ablation_active` and `services/multimodal/pipeline.py::_ablate` — byte-identical bodies
  (`os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")`), same two env var names
  (`ABLATE_GEOMETRY`/`ABLATE_GRAPH`), and `pipeline.py`'s own docstring already cross-references
  `feature_providers._ablation_active` as "the real one" — a duplication its own author had already
  half-acknowledged without ever finishing the consolidation.
- **Two trivial-wrapper duplicates**: `services/multimodal/schedule_ingestion.py::_norm` and
  `services/multimodal/spatial_association.py::_norm` were both single-line pass-throughs
  (`return normalize_engineering_token(text)`) around a function **both files already imported directly**
  from `services/token_extractor.py` — pure unnecessary indirection, not even a real second implementation.
- **One exact-duplicate normalization function across a runtime/training boundary**:
  `services/takeoff/takeoff_validation.py::_norm` and `services/training_pipeline/neural_dataset.py::_norm`
  — byte-identical bodies (`str(x or "").upper().replace(" ", "").replace("-", "")`), used as a cheap
  case/whitespace/hyphen-folded identity key for comparing a predicted label to a ground-truth label (**not**
  full catalog canonicalization — verified distinct from `canonical_takeoff_eval.canonical_section`, which
  does AISC-catalog resolution, a different operation entirely).
- A visually similar `_norm` in `services/takeoff/paired_dataset_builder.py` was checked and is **not** a
  duplicate — it additionally strips unicode `×`/`✕` and underscores, a materially different normalization
  rule; merging it would have either lost behavior or silently widened what callers of the simpler version
  accept. Left alone (same-name/different-semantics, correctly excluded).
- `services/engineering/validation_engine.py::_norm` (`.replace("×", "X")` instead of hyphen-stripping) is
  also a different rule — not touched.

No configuration-object duplication (direct `os.getenv`/`os.environ` bypassing `config.py`) was found beyond
the ablation-flag case above and `torch_runtime.py`'s one-off `os.environ.setdefault` calls for
BLAS/OpenMP thread-count env vars (single-file, not duplicated, not touched).

## Selected consolidation groups (Phase 4)

| Group | Category | Files | Benefit | Risk | Selected? |
|---|---|---|---|---|---|
| A | trivial wrapper | `schedule_ingestion.py`, `spatial_association.py` | removes pure indirection, both already import the real function | low — behavior is a straight pass-through, zero logic change | yes |
| B | parsing/normalization duplication | `takeoff_validation.py`, `neural_dataset.py` | one canonical, domain-correct owner instead of 2 copies; +4 new characterization tests (zero prior coverage) | low-medium — crosses a runtime/training package boundary, but the import direction (training → `services.takeoff`) was already established by 2 existing imports in the same file | yes |
| C | configuration/env-var-parsing duplication | `feature_providers.py`, `pipeline.py` | removes an already-acknowledged duplicate; +5 new characterization tests (zero prior coverage) | low — pipeline.py's own docstring already named feature_providers as canonical; no circular import | yes |
| D (test-loader) | dynamic-loader duplication + 1 unnecessary isolation | 5 test files + new `tests/helpers/script_loader.py` | 1 file moved off unneeded dynamic loading entirely; the remaining 4's identical boilerplate collapsed to 1 shared, tested helper | low — collection/test count/names proven unchanged before and after | yes |

Exactly 3 production groups (the maximum allowed) and 1 test-loader group (the maximum allowed) were
selected. No candidate was rejected after selection — each measured a genuine net simplification and was
kept; none needed reverting.

## Canonical owners (Phase 7)

- **Group A**: `services/token_extractor.py::normalize_engineering_token` — already the real implementation
  both files were already importing; no new module needed.
- **Group B**: `services/takeoff/takeoff_validation.py` (renamed `_norm` → `normalize_takeoff_label`, public)
  — domain-correct home (comparing a predicted label to a ground-truth label is exactly this module's job,
  alongside `ground_truth_evaluation.py`/`canonical_takeoff_eval.py`/`ground_truth_excel.py` in the same
  package); `neural_dataset.py` already imports 2 other `services.takeoff.*` modules, so this adds no new
  dependency direction. `training_pipeline` was rejected as the owner (wrong direction — a runtime module
  should not import from the training system).
- **Group C**: `services/multimodal/feature_providers.py::_ablation_active` — already carried the fuller
  docstring and was already named as canonical by `pipeline.py`'s own comment.
- **Group D**: `backend/tests/helpers/script_loader.py::load_script_module` — follows the established
  `tests/helpers/` pattern from the prior test-fixture-cleanup phase (`isolated_api.py`,
  `geometry_fixtures.py`); a narrowly-named, single-purpose loader, not a generic dumping ground.

## Characterization tests added (Phase 6)

Neither the ablation-flag parser nor the takeoff-label normalizer had any existing dedicated test —
confirmed by grep before writing anything. Added:

- `tests/test_multimodal_pipeline.py::AblationFlagParsingTests` (5 tests): unset → off; all 4 truthy spellings
  case-insensitive; falsy/garbage values; whitespace stripped; reads only the named variable.
- `tests/test_takeoff_platform.py::NormalizeTakeoffLabelTests` (4 tests): case/whitespace folding; hyphen
  stripping; already-canonical passthrough; empty/`None` handling.

Both target the new canonical public names directly, so they needed no changes across the consolidation
itself (written once, passed both before and after each respective move).

## Implementation (Phases 8-11)

- **Group A**: removed both `_norm` wrapper functions; the 4 call sites across the 2 files now call
  `normalize_engineering_token(...)` directly. Zero behavior change (pure delegation removed, not the
  delegated behavior).
- **Group B**: `takeoff_validation._norm` renamed to public `normalize_takeoff_label` (its 1 internal call
  site updated); `neural_dataset.py`'s local `def _norm(...)` replaced with
  `from services.takeoff.takeoff_validation import normalize_takeoff_label as _norm` — all 15+ existing call
  sites in that file untouched (same local name, same behavior, same import-time evaluation).
- **Group C**: `pipeline.py`'s local `def _ablate(...)` (and the now-unused `import os`) replaced with
  `from services.multimodal.feature_providers import _ablation_active as _ablate` — all 7 existing call sites
  in that file untouched.
- **Group D**: `test_anonymous_dimension_resolver_context.py` now does a plain
  `from services.annotation.anonymous_dimension_resolver import resolve_anonymous_dimension`. The 4
  scripts/-loading tests now call `tests.helpers.script_loader.load_script_module(filename, module_name)`,
  preserving the exact `sys.modules` registration name each test used before (`test_evaluate_pipeline_module`,
  `import_review_decisions`, `build_ml_association_review_kit`, `select_double_review_subset`).

No circular imports were introduced (verified: `feature_providers.py` does not import `pipeline.py`;
`takeoff_validation.py` does not import `training_pipeline`, only a function-local, not module-level, import
of `services.multimodal.pipeline`). No public API, route, schema, environment-variable name, or default
changed.

## Static verification (Phase 12)

- Zero remaining references anywhere in the tree to: `def _ablate`, `_load_resolver`,
  `anonymous_dimension_resolver_under_test`, or `from services.takeoff.takeoff_validation import _norm`.
- Remaining `spec_from_file_location` usage in `tests/`: exactly 1 (the new shared helper itself) — down
  from 5 independent inline definitions.
- `py_compile` clean on all 13 touched production/test files plus the new helper.
- `import app` succeeds; 15 routes register (unchanged).
- Full test collection: 1308 (1299 + 9 new characterization tests), zero collection errors.

## Regression testing (Phase 13)

- Directly affected + broad targeted set (28 files spanning prediction orchestration, multimodal fusion,
  human review, ML association guard, continuous learning, normalization, HSS, anonymous-dimension
  resolution, feature-schema parity, takeoff evaluation, schedule/spatial pipeline, member resolution):
  **224 passed, 1 skipped, 0 failed, 40 subtests passed.**
- Full backend suite: **1296 passed, 9 failed, 3 skipped, 349 subtests passed** (1308 collected total). The 9
  failures are byte-for-byte the same pre-existing, unrelated set (`test_a2_a7_human_review.py` × 8,
  `test_repeated_detail_linker.py` × 1) — confirmed unrelated by name and message; neither imports any file
  touched in this phase. 1296 = the prior 1287-passed baseline + exactly the 9 new characterization tests.
  **Zero new failures.**
- Drift fingerprints re-verified identical after every group and before every commit.

## Measurement (Phase 14)

| Group | Production LOC before → after | Test LOC before → after | Net |
|---|---|---|---|
| A (trivial wrapper) | 2 files, -6 net | unchanged | **-6** |
| B (`_norm` dedup) | 2 files, +4/-2 (docstring added) net **+2** in `takeoff_validation.py`, -2 in `neural_dataset.py` | +20 (4 new characterization tests) | production ~net 0, +20 test (real new coverage, not organizational) |
| C (`_ablate` dedup) | `pipeline.py` -14, `feature_providers.py` +0 (already had the real one) | +34 (5 new characterization tests) | production **-14**, +34 test (real new coverage) |
| D (test-loader) | n/a (test-only) | 5 files -43, +31 new helper = **-12** | **-12** |

**Totals**: production LOC **-18** (18 insertions, 30 deletions across 5 files — a real reduction, not
organizational). Test LOC **+42** (54 lines of genuine new characterization coverage for 2 previously-untested
functions, minus 12 lines of loader-boilerplate deduplication). Definitions removed: 4 (`_norm` ×3,
`_ablate` ×1). Imports removed: 1 unused `import os` in `pipeline.py`. New abstractions introduced: exactly
1, narrowly scoped (`tests/helpers/script_loader.py`, 31 LOC, single function, single responsibility) — no
`common.py`/`utils.py`-style dumping ground created anywhere.

Every group meets this phase's success bar: Groups A/C/D are net production-or-test-LOC reductions with zero
behavior change; Group B is LOC-neutral in production but replaces 2 unverified duplicate implementations
with 1 verified, newly-tested one, with a clear domain-correct owner — "materially clearer ownership with
minimal LOC growth and strong justification," the explicitly allowed alternative success condition.
