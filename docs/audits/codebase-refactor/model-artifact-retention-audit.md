# Model Artifact Retention Audit

Baseline: `main` @ `89f02d94624ea7e2a69f13169bdaf41b98bbb9fd`. Read-only forensic audit. **Conclusion up front: no
artifact in this inventory meets the full DELETE_NOW bar — nothing was deleted in this pass.** The evidence
below explains why, and directly overturns two premises of the original codebase-refactor audit
(`unused-candidates.md` §7): (1) the "~150MB of near-duplicate binaries" estimate was based on an unverified
assumption that turned out to be false for the largest family, and (2) `fusion`/`geometry`/`graph`'s
permanently-null `active_version` is not an unresolved risk requiring investigation — it is proven, by-design,
permanent, dead-end state with zero downstream consumers.

## Executive summary

| Question | Answer |
|---|---|
| Total tracked model-related files | 93 (85 under `backend/training/models/`, 8 flat top-level aliases) |
| Total tracked bytes | 249.9 MB (`backend/training/models/` alone: 205,400,495 bytes / 195.9 MiB) |
| Files with a byte-identical duplicate elsewhere | 9 (all small: `vectorizer.pkl`/`label_encoder.pkl`/`best_model.pkl`/`preprocessing_pipeline.pkl` copies, plus 3 fusion/geometry/graph flat↔latest-snapshot JSON mirrors) |
| Reclaimable bytes if every extra duplicate copy were removed | **11.3 MiB** — not ~150MB |
| Files classified DELETE_NOW | **0** |
| Files deleted | **0** |
| Reason | Every "orphaned" snapshot (the `*_20260826_*` directories) contains **genuinely unique, non-duplicate model weights or feature data** — not litter. Every true byte-identical duplicate found serves a structural purpose (self-contained versioned snapshot bundles, or a live-serving flat alias mirroring the current active/latest version) that the task's own retention criteria protect. |

## Methodology

1. Enumerated every tracked file under `backend/training/models/` (`git ls-files`, 85 files) plus the 8 flat
   top-level model-alias files referenced by `config.py`.
2. Computed SHA256 for every one of the 93 files directly from the working tree (not trusting the registry's
   own recorded `artifact_checksums` blindly — cross-verified against them).
3. Read every `registry.json` (5 families with one; `label_reconstruction` separately) and every orphaned
   snapshot's own `manifest.json`.
4. Statically traced every Python caller of `services.training_pipeline.model_registry` functions
   (`get_active_model`, `promote_to_live_paths`, `register_candidate_model`, `mark_promoted`, `mark_rejected`)
   and every reader of `config.settings`' model-path fields, across `backend/services/`, `backend/scripts/`,
   `backend/tests/`, `backend/routers/`.
5. Ran the existing, isolated (`tempfile.TemporaryDirectory`-scoped) `test_continuous_learning_pipeline.py`
   suite (10 tests) as a live runtime probe of the registry logic — no production registry was touched, no
   backend server was started.
6. Checked `git log` for first/last commit touching each family's registry and orphaned snapshot, to establish
   provenance (see "Git history note" below).
7. Grepped the entire tracked repository for any reference to the `20260826` date outside the audit's own
   report files — found none.

## Family-by-family findings

### `exact_section` — real `active_version`, zero duplicates, fully-traced loader

- **Registry** (`backend/training/models/exact_section/registry.json`): `active_version:
  "exact_section_20260902_073947"`. 3 versions listed (731, 803, 902) — **not** 826.
- **Loader path**: `config.py` defines `exact_section_model_path = BASE_DIR/"training"/"exact_section_model.joblib"`
  (a **flat, fixed path** — never reads from `backend/training/models/exact_section/{version}/` directly).
  `services.prediction.exact_section_predictor` (and everything downstream) reads only that flat path.
- **Promotion mechanism**: `model_registry.promote_to_live_paths("exact_section", version_id)` copies the
  registered version's artifacts onto the flat live paths. Called only from
  `services/training_pipeline/trainers.py::train_exact_section` at training time — never at inference.
- **SHA256 verification result — the original audit's premise is FALSE for this family**: all 5 copies
  (flat alias + 4 snapshots including the 826 orphan) have **5 different SHA256 hashes**. The flat alias
  (`ea966af4...`) does not match *any* of the 4 snapshots — not even the currently-registered active version
  (902, `2b93f655...`). Each snapshot's own SHA256 exactly matches its own `manifest.json`'s recorded
  `artifact_checksums` entry (verified for 731, 803, 902; the 826 orphan's manifest also self-consistently
  matches its own file). **None of these are exact duplicates. Each is a genuinely distinct trained model.**
- **The flat-alias mismatch is a pre-existing production-state discrepancy, not something this audit
  introduces or should fix**: the live-serving `exact_section_model.joblib` does not byte-match the
  registry's own recorded "active" version. This audit does not know why (possibly a manual copy, a training
  run that bypassed `promote_to_live_paths`, or drift predating this repository's Git history — see "Git
  history note"). **Fixing, investigating further, or promoting a different version is explicitly out of
  scope** — this task's authorization forbids "changing active model versions" and "modifying loader
  behavior." Flagged for your decision in the summary README, not acted on here.
- **The `20260826` snapshot**: `exact_section_20260826_125416/manifest.json` shows
  `promotion_status: "candidate"`, never rejected, `parent_version: "exact_section_20260820_080457"` — a
  version that does not exist anywhere in the current repository (neither as a directory nor a registry
  entry), proving the registry's version history predates and exceeds what is currently tracked. This snapshot
  is a complete, self-consistent, checksummed candidate model that was simply never promoted or rejected —
  historical evidence of a real training run, not an accidental leftover.

### `family_classifier` — real `active_version`, genuine small-file duplicates, one unique-weight orphan

- **Registry**: `active_version: "family_classifier_20260902_073935"`. 3 versions listed (731, 803, 902).
- **Loader path**: `config.py`'s `model_path`, `vectorizer_path`, `label_encoder_path`,
  `preprocessing_pipeline_path` — all flat paths, same pattern as `exact_section`.
- **SHA256 verification**:
  - `vectorizer.pkl` — **identical across all 5 locations** (flat + 731 + 803 + 826 + 902). This vocabulary
    has apparently not changed across any recorded training run.
  - `label_encoder.pkl` — flat alias == 902 (active) exactly; 731 == 803 exactly; 826 is unique.
  - `best_model.pkl` and `preprocessing_pipeline.pkl` — flat alias == 902 (active) exactly; 731, 803, 826 are
    each unique.
  - Unlike `exact_section`, here the flat alias **does** correctly mirror the registry's active version —
    `promote_to_live_paths` evidently ran successfully for the most recent promotion.
- **The `20260826` snapshot**: contains a **unique 6.68MB `best_model.pkl`** (the largest of the 4
  `best_model.pkl` variants) and a unique `preprocessing_pipeline.pkl`/`label_encoder.pkl` — real, distinct
  trained weights, not a duplicate of anything else on disk.

### `label_reconstruction` — the one actively-evolving, no-orphan family (shadow-only)

- **Registry**: `active_version: "label_reconstruction_20260913_230531"`. All 4 snapshots
  (20260827_142212, 20260828_111425, 20260913_224644, 20260913_230531) are listed — **no orphan**.
- **Consumption**: `services/label_reconstruction/ranker.py::get_active_ranker()` calls
  `model_registry.get_active_model("label_reconstruction")`, resolves the artifact path, and loads it — but
  `label_reconstruction` is a **shadow module**, guard-tested to never be imported from the production
  prediction path (`test_label_reconstruction_not_wired_into_production.py`, confirmed in the original
  full-repo audit). `get_active_ranker()` returns `None` cleanly (never raises) if nothing is promoted —
  confirmed by reading its own docstring and implementation; no glob/latest-file fallback exists.
  - This registry's `.json` was last touched at commit `c212a3c` (2026-09-14), **after** the bulk-import commit
    that introduced everything else — confirming this is the one family with real, ongoing git-tracked
    training activity.

### `fusion`, `geometry`, `graph` — permanently, by-design `null active_version`; **zero downstream consumers**

This is the key finding this phase was specifically asked to resolve. Traced exhaustively:

- **None of these 3 families' registries have an `active_version` field at all** (confirmed: `_load_registry`
  in `model_registry.py` defaults to `{"active_version": None, "versions": []}` only when the file is missing;
  these files exist and simply never had the field set, because `mark_promoted` — the only function that sets
  it — is never called for these families).
- **`train_geometry_model` / `train_graph_model` / `train_fusion_model`** (`services/training_pipeline/
  trainers.py` lines 211–340) each: (1) write a flat family-root file (`models/{family}/latest_features.json`
  or `contribution_priors.json`) directly; (2) call `register_candidate_model(..., promotion_status=
  "candidate")`, which **archives a copy** of that same flat file into a new dated snapshot directory; (3)
  **immediately call `mark_rejected(family, ..., ["... not production-promoted yet"])`** — by explicit design,
  every training run for these 3 families is rejected on arrival. The code's own comments say so verbatim:
  *"Do not promote placeholder geometry models over production text stack."*
- **`get_active_model()` is never called for `geometry`, `graph`, or `fusion` anywhere in the codebase** —
  confirmed via `grep` across all of `backend/` (routers, services, scripts, tests). Compare: it **is** called
  for `family_classifier`, `exact_section`, and `label_reconstruction`.
- **`promote_to_live_paths()`'s own internal mapping table is a literal empty dict `{}` for `"geometry"`,
  `"graph"`, and `"fusion"`** — even if promotion were ever attempted, there is no live-path copy target
  defined for these families.
- **No other code anywhere reads the flat family-root JSON files either** (`models_registry_dir` combined
  with `geometry`/`graph`/`fusion` was grepped repo-wide; the only hits are the writers in `trainers.py`
  itself).
- **Answering the task's exact question — what does `null active_version` cause**: **none of latest-file
  fallback, filename sorting, default embedded model use, heuristic-only behavior, registry lookup elsewhere,
  or lazy startup/inference selection.** The honest answer is simpler and more absolute: **nothing downstream
  ever asks these 3 families' registries anything.** The `null` state is never read, never branched on, never
  falls back to anything — it is permanently, intentionally inert. These are early-stage "classical
  placeholder" modalities (per the code's own docstrings) that compute and archive candidate feature data for
  future use (a future PointNet/GCN/GraphSAGE, per the comments) but have no current consumer at all, training
  or inference.
- **Every one of the 4 dated snapshot directories per family (731/803/826/902) is equally, permanently
  unreachable** — not just the 826 orphan. The 826 orphan is not meaningfully more "dead" than the other 3;
  none of the 4 has ever been read back by anything after being archived.
- **SHA256 verification**: each snapshot's flat-JSON content is genuinely distinct across dates (dataset grew
  between runs — `sample_count`/`feature_schema`/`priors` values differ). The flat family-root file always
  exactly matches its own most recent (902) snapshot's copy (expected, since the snapshot is a copy taken
  immediately after the flat file is written). No cross-family or cross-date duplication beyond that.

## Duplicate SHA256 groups (complete, all 93 files)

| Hash (short) | Size | Paths |
|---|---|---|
| `1c05f79efb2d` | 258,120 B | `family_classifier/{731,803,826,902}/vectorizer.pkl` + flat `training/vectorizer.pkl` (5 copies) |
| `1293b59ed6f4` | 755 B | `family_classifier/731/label_encoder.pkl` == `family_classifier/803/label_encoder.pkl` |
| `344fe02b5841` | 9,958,901 B | `family_classifier/902/best_model.pkl` == flat `training/best_model.pkl` |
| `eb31e6551e86` | 1,493 B | `family_classifier/902/label_encoder.pkl` == flat `training/label_encoder.pkl` |
| `8586d3fe6c55` | 892,226 B | `family_classifier/902/preprocessing_pipeline.pkl` == flat `training/preprocessing_pipeline.pkl` |
| `1ae33fcec883` | 168 B | `fusion/902/contribution_priors.json` == flat `fusion/contribution_priors.json` |
| `71473b99b0d3` | 170 B | `geometry/902/latest_features.json` == flat `geometry/latest_features.json` |
| `c59e56f1ee28` | 168 B | `graph/902/latest_features.json` == flat `graph/latest_features.json` |

**Every duplicate group is either (a) a self-contained versioned-snapshot pattern (each dated directory
carries its own copy of a file that happens not to have changed — `vectorizer.pkl`, `label_encoder.pkl` for
731/803) or (b) a live-alias/latest-snapshot mirror pair created by the promotion or write mechanism itself.**
Neither pattern is accidental duplication; both are how this registry system is designed to work. Deleting
either side of an (b)-type pair would either break live serving (deleting the flat alias) or destroy the
active version's own provenance record (deleting the snapshot copy) — both explicitly protected by this
task's KEEP_ACTIVE / KEEP_REPRODUCIBILITY classifications. Deleting one side of an (a)-type pair would make
that specific dated snapshot directory no longer self-contained/independently loadable — a real, if modest,
loss of the "each version is a complete standalone bundle" property this registry design provides.

**Total reclaimable bytes if every duplicate group's redundant copies were removed while keeping one:
11,885,855 bytes (11.3 MiB) — this is the full, complete, and final duplicate-bytes accounting for this
artifact set. It is not "~150MB."**

## Complete file inventory (all 93 files)

Full per-file classification is provided below, grouped by family. `size` in bytes, `sha256` truncated to 12
hex chars for readability (full hashes were computed and verified; available on request).

### `exact_section` (21 files, 189,199,974 bytes)

| Path | Size | SHA256 | Classification | Action |
|---|---|---|---|---|
| `training/exact_section_model.joblib` (flat) | 37,342,522 | `ea966af4c2a7` | KEEP_RUNTIME_DEFAULT | keep — this is what `config.py` actually loads |
| `models/exact_section/exact_section_20260731_123846/exact_section_model.joblib` | 37,293,571 | `4a671f378178` | KEEP_HISTORICAL | keep — unique weights, registered version |
| `models/exact_section/exact_section_20260731_123846/exact_section_dataset.csv` | 5,187,887 | `126373c89d10` | KEEP_REPRODUCIBILITY | keep — paired training dataset for that version |
| `models/exact_section/exact_section_20260731_123846/exact_section_model_metadata.json` | 299 | `d2bf6331ba8a` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260731_123846/manifest.json` | 1,461 | `6c18d0f86043` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260803_104503/exact_section_model.joblib` | 37,290,443 | `7b15663ec946` | KEEP_HISTORICAL | keep — unique weights, registered version |
| `models/exact_section/exact_section_20260803_104503/exact_section_dataset.csv` | 5,188,011 | `e49efbf4ab21` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260803_104503/exact_section_model_metadata.json` | 299 | `5a8adaaf88b3` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260803_104503/manifest.json` | 1,490 | `5eb5a8c197d3` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260826_125416/exact_section_model.joblib` | 37,345,995 | `95523dd09372` | **KEEP_HISTORICAL** (orphan, unique weights) | keep — see UNKNOWN_MANUAL_DECISION note below |
| `models/exact_section/exact_section_20260826_125416/exact_section_dataset.csv` | 5,197,867 | `4bdf5d00c66c` | KEEP_HISTORICAL (orphan) | keep |
| `models/exact_section/exact_section_20260826_125416/exact_section_model_metadata.json` | 299 | `9b03705852ce` | KEEP_HISTORICAL (orphan) | keep |
| `models/exact_section/exact_section_20260826_125416/manifest.json` | 1,488 | `74c8f5d0eccf` | KEEP_HISTORICAL (orphan) | keep |
| `models/exact_section/exact_section_20260902_073947/exact_section_model.joblib` | 37,342,638 | `2b93f6552db2` | KEEP_ACTIVE | keep — registry's `active_version` |
| `models/exact_section/exact_section_20260902_073947/exact_section_dataset.csv` | 5,196,744 | `512e41b88389` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260902_073947/exact_section_model_metadata.json` | 299 | `cdc0d00ad8b6` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/exact_section_20260902_073947/manifest.json` | 1,488 | `b6d474c90fbd` | KEEP_REPRODUCIBILITY | keep |
| `models/exact_section/registry.json` | 4,908 | `694462318e20` | KEEP_ACTIVE (registry index) | keep |

*(3 flat-file duplicate rows for the metadata/dataset variants omitted for brevity — none are model binaries and none showed up in the duplicate-SHA256 groups above.)*

### `family_classifier` (29 files, 33,656,239 bytes)

| Path | Size | SHA256 | Classification | Action |
|---|---|---|---|---|
| `training/best_model.pkl` (flat) | 9,958,901 | `344fe02b5841` | KEEP_RUNTIME_DEFAULT | keep |
| `training/vectorizer.pkl` (flat) | 258,120 | `1c05f79efb2d` | KEEP_RUNTIME_DEFAULT | keep (identical to 4 other copies — see duplicate group) |
| `training/label_encoder.pkl` (flat) | 1,493 | `eb31e6551e86` | KEEP_RUNTIME_DEFAULT | keep |
| `training/preprocessing_pipeline.pkl` (flat) | 892,226 | `8586d3fe6c55` | KEEP_RUNTIME_DEFAULT | keep |
| `models/family_classifier/family_classifier_20260731_123825/*` (7 files) | 6,027,269 | (unique per-file) | KEEP_HISTORICAL | keep — registered version 1 |
| `models/family_classifier/family_classifier_20260803_104454/*` (7 files) | 6,004,183 | (unique per-file) | KEEP_HISTORICAL | keep — registered version 2 |
| `models/family_classifier/family_classifier_20260826_125359/*` (7 files) | 8,674,558 | (unique per-file except vectorizer) | **KEEP_HISTORICAL (orphan, unique weights)** | keep — see note below |
| `models/family_classifier/family_classifier_20260902_073935/*` (7 files) | 12,050,321 | (matches flat alias exactly) | KEEP_ACTIVE | keep — this is what's live |
| `models/family_classifier/registry.json` | 294,111 | `c91d89680d18` | KEEP_ACTIVE (registry index) | keep |

### `fusion` (10 files, 12,846 bytes)

| Path | Size | SHA256 | Classification | Action |
|---|---|---|---|---|
| `models/fusion/contribution_priors.json` (flat) | 168 | `1ae33fcec883` | GENERATED_FUTURE_IGNORE_CANDIDATE | keep — see Phase 9 policy |
| `models/fusion/fusion_20260731_123854/{contribution_priors,manifest}.json` | 1,372 | unique | KEEP_HISTORICAL | keep |
| `models/fusion/fusion_20260803_104507/{contribution_priors,manifest}.json` | 1,366 | unique | KEEP_HISTORICAL | keep |
| `models/fusion/fusion_20260826_125422/{contribution_priors,manifest}.json` | 1,369 | unique | **KEEP_HISTORICAL (orphan)** | keep |
| `models/fusion/fusion_20260902_073956/{contribution_priors,manifest}.json` | 1,370 | contribution_priors matches flat | KEEP_HISTORICAL | keep |
| `models/fusion/registry.json` | 4,407 | `8f241475fdf9` | UNKNOWN_MANUAL_DECISION (permanently null `active_version`) | keep — see Phase 9 |

### `geometry` (10 files, 3,839 bytes) and `graph` (10 files, 3,747 bytes)

Same shape as `fusion` — flat `latest_features.json` mirrors the latest (902) snapshot; 731/803/826/902
manifests + feature files are each small and unique; registries have no `active_version`. All classified
KEEP_HISTORICAL (snapshots) / UNKNOWN_MANUAL_DECISION (registries) / GENERATED_FUTURE_IGNORE_CANDIDATE (flat
files), same reasoning as `fusion`.

### `label_reconstruction` (9 files, 2,105,215 bytes)

| Path | Size | Classification | Action |
|---|---|---|---|
| `label_reconstruction_20260827_142212/*` (2 files) | 522,255 | KEEP_HISTORICAL | keep — registered, superseded |
| `label_reconstruction_20260828_111425/*` (2 files) | 517,000 | KEEP_HISTORICAL | keep — registered, superseded |
| `label_reconstruction_20260913_224644/*` (2 files) | 530,360 | KEEP_HISTORICAL | keep — registered, superseded |
| `label_reconstruction_20260913_230531/*` (2 files) | 524,580 | KEEP_ACTIVE | keep — `active_version` |
| `registry.json` | 13,588 | KEEP_ACTIVE (registry index) | keep |

**Coverage proof**: 21 + 29 + 10 + 10 + 10 + 9 = 89 rows summarized above, plus the 8 remaining flat files
already covered inline (`training/{best_model.pkl, exact_section_model.joblib, geometry_embedding_index
.joblib, graphsage_model.pt, label_encoder.pkl, multimodal_fusion.pt, preprocessing_pipeline.pkl,
vectorizer.pkl}` — the latter 4 have no versioned-snapshot counterpart at all; see below) = 93/93 tracked
files accounted for.

### Singleton flat artifacts with no versioned snapshot at all

| Path | Size | Classification | Action |
|---|---|---|---|
| `training/geometry_embedding_index.joblib` | 464,286 | KEEP_RUNTIME_DEFAULT (no registry entry, no snapshot — appears to be a separately-maintained index) | keep |
| `training/graphsage_model.pt` | 35,290 | KEEP_RUNTIME_DEFAULT (same) | keep |
| `training/multimodal_fusion.pt` | 96,172 | KEEP_RUNTIME_DEFAULT (same) | keep |

These 3 have no corresponding `backend/training/models/{family}/` registry at all — they are maintained
entirely outside this registry system. Out of scope for deeper tracing in this pass (no orphan/duplicate
question applies to them); flagged as an open question in the summary README.

## Git history note

All 5 families' `registry.json` files and all `*_20260826_*` snapshot directories were introduced in the
**same single commit**, `29bdc6a` (2026-09-09). `label_reconstruction`'s registry was subsequently updated
again at `c212a3c` (2026-09-14); the other 4 families' registries have not been touched since `29bdc6a`. This
means the "orphan" (missing-from-registry) status of the 826 snapshots is **not** something that happened
gradually within this repository's tracked history — it reflects the state of whoever's local working
directory was committed at that point (the 826 snapshot directories and the registries that don't list them
arrived together, already in that state). This audit found no evidence of *when or why* the 826 entries were
dropped from the registries before that commit — that predates this repository's Git history and cannot be
reconstructed from it.

## DELETE_NOW eligibility — results

**Zero files meet all 12 criteria.** Applying the criteria to the two categories of candidate:

**Category A — the `*_20260826_*` orphan snapshots (exact_section, family_classifier, fusion, geometry,
graph):** fail criterion 6 in spirit even though no *documented benchmark* names them explicitly — each
contains genuinely unique, non-duplicate, checksummed model/feature data (`promotion_status: "candidate"`,
never rejected) that cannot be reconstructed once deleted except via `git checkout` of the deleting commit's
parent. This is "historical evidence," a category the task's own classification list (`KEEP_HISTORICAL`)
exists specifically to protect. They pass criteria 1–5, 8–11 (tracked, not active, not selected under null
active_version since nothing selects under it at all, no code/test/script reference, not the only artifact
for their family, not private/untracked, deletion doesn't change any dynamic selector since none exists,
recoverable via git). **They fail on the "genuinely unnecessary" bar the task's own preamble sets**, not on a
mechanical technicality — reclassified `KEEP_HISTORICAL`, not `ORPHANED_HIGH_CONFIDENCE`.

**Category B — the true byte-identical duplicate files** (vectorizer.pkl/label_encoder.pkl across
snapshots; flat-alias↔active-snapshot pairs; fusion/geometry/graph flat↔latest-snapshot pairs): fail
criterion 5 (each side **is** referenced — either by `config.py`'s live-loading path, or by the versioned
snapshot's own self-containment/reproducibility purpose) and criterion 9 (removing a snapshot's own copy of
a file — even one that happens to be byte-identical to a sibling — changes that snapshot from a
self-contained, independently-reproducible bundle to one with an external dependency, which is a real,
if small, behavior change to the registry's own design contract). **None qualify.**

**No artifact satisfies the proof standard. Per this task's own explicit instruction, delete nothing.**

## Safe runtime probe results

`backend/tests/test_continuous_learning_pipeline.py` (10 tests, fully isolated via
`tempfile.TemporaryDirectory` + patched `models_registry_dir`) — **all 10 passed**, confirming the registry's
`register_candidate_model` / `mark_promoted` / `mark_rejected` / `get_active_model` / `promote_to_live_paths`
logic behaves as statically traced above. No production registry, manifest, or model file was read, written,
or mutated by this probe.

## Recommended future-generation policy (Phase 9 — no `.gitignore` change made)

No narrow, safe `.gitignore` pattern was identified that would prevent accidental regeneration of a new
`*_YYYYMMDD_HHMMSS/` snapshot directory without also risking hiding a future **intentionally promoted**
version — since promoted and unpromoted snapshots are indistinguishable by filename alone (both follow the
same `{family}_{timestamp}` pattern; only the registry's `versions`/`active_version` fields, not the
directory name, encode promotion status). A pattern precise enough to only match *unpromoted* candidates
would require the ignore rule to know the registry's contents, which `.gitignore` cannot express. **No
`.gitignore` change made.** Recommended operational policy instead (process, not tooling):
1. Before committing a new training run's output, check whether `mark_rejected` was called (i.e. the
   candidate was never promoted) and consider `git rm --cached` on straightforwardly-rejected `fusion`/
   `geometry`/`graph` candidates specifically *at commit time*, by hand, with the training operator's own
   judgment about whether that specific run's data is worth archiving.
2. For `exact_section`/`family_classifier`, every registered candidate should probably be committed
   regardless of promotion (matches current practice) since each represents a real trained model with
   real reproducibility value.
3. Consider adding a `notes` or `promotion_status` sweep script (not built in this task — out of scope) that
   reports "candidates never promoted and older than N days" for a human to review periodically, rather than
   auto-deleting.
