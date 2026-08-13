# Partner deep-learning checkpoint governance plan

Scope: this document specifies what must be true before ANY neural checkpoint
(partner's `graphsage_model.pt` / `multimodal_fusion.pt` / geometry embedding
index, or any future one) is permitted to load in a production request path.
It does not modify any partner code -- `origin/main` has not been merged, and
no production file is touched by this document.

## Why this exists

The partner-vs-local comparison
(`docs/ml_integration/partner_vs_local_comparison.md`, section 2) found that
`graphsage_model.pt` and `multimodal_fusion.pt` currently load **unconditionally**
in `services/multimodal/pipeline.py` -- gated only by "does a file exist at a
fixed path" -- and the fusion checkpoint can directly override the final
predicted label. Neither checkpoint has a real held-out accuracy number
anywhere in the repository; the only "accuracy" figures that exist for them
(`0.5`/`0.6` in `backend/training/models/{graph,fusion}/registry.json`) are
hardcoded literal constants written by a completely disconnected training
system, which itself marked both lanes `"rejected"` / `"not production-promoted"`.
**File existence alone must never again be treated as production approval.**

## Required checklist before any checkpoint is allowed to load in production

A checkpoint may only be loaded from a production request path (anything
reachable from `routers/*` -> `staged_pipeline.py` / `pipeline.py` /
`prediction/orchestrator.py`) once ALL seven of the following exist and are
verifiable by inspecting committed files -- not by trusting a comment or a
commit message:

1. **Registry entry.** The checkpoint's family (`graph`, `fusion`, `geometry`,
   `label_reconstruction`, ...) has an entry in
   `backend/training/models/<family>/registry.json` written by
   `services.training_pipeline.model_registry.register_candidate_model` --
   the SAME code path other promoted models (`family_classifier`,
   `exact_section`) already use. Ad hoc `.pt`/`.joblib` files sitting at a
   fixed top-level path with no registry entry (today's situation for
   `graphsage_model.pt`/`multimodal_fusion.pt`) do not qualify.
2. **Model version.** A specific `version_id` (e.g. `graph_20260803_104505`)
   is named as the thing being loaded -- never "whatever file happens to be
   at `settings.graphsage_model_path`."
3. **Preprocessing version.** Whatever feature-extraction/encoding code
   produced the checkpoint's training inputs is itself versioned (a
   `feature_schema` list or equivalent, recorded in the manifest) and the
   inference code path is checked to use the SAME version -- not merely
   "the same function name," since a function can change behavior across
   commits while keeping its name.
4. **Evaluation dataset + version.** A named, versioned held-out evaluation
   set exists (e.g. via `dataset_registry`) that the checkpoint was scored
   against, and that dataset is NOT the same rows/documents used for
   training (see leakage findings in the comparison doc -- today's
   `learned_fusion.train_fusion_model()` calibration slice is not reliably
   independent of training).
5. **Real recorded metrics.** The manifest's `metrics` field contains
   numbers actually computed by running the checkpoint against the
   evaluation dataset above -- verifiable by finding the code that computes
   them, not a hardcoded dict literal. (`trainers.py::train_graph_model()`'s
   `metrics = {"accuracy": 0.5, ...}` is the canonical example of what does
   NOT satisfy this requirement.)
6. **Approval status.** `promotion_status == "promoted"` in the registry,
   set only via `model_registry.mark_promoted`, by a human decision after
   reviewing metrics -- not automatically on training completion.
7. **Compatibility validation.** A smoke test confirms the checkpoint's
   expected input feature vector shape/order matches what the CURRENT
   inference code actually produces (a version bump anywhere upstream --
   e.g. a changed geometry feature -- can silently desync a checkpoint from
   its own preprocessing without either side erroring).

## Enforcement pattern

Follow the `ml_association` isolation pattern already used elsewhere in this
repo (`test_ml_association_not_wired_into_production.py`,
`test_label_reconstruction_not_wired_into_production.py`): any inference
loader for a governed checkpoint should call a single
`model_registry.get_active_model(family)`-style gate, and a structural test
should assert the loader never falls back to "load by file path" when the
registry has no promoted version for that family. This is a change to make
if/when partner's commit is actually integrated -- it is described here as
the acceptance bar, not implemented against partner's code yet, since
`origin/main` is not merged.

## Current status of partner's three DL components against this checklist

| Component | Registry entry | Version | Preproc version | Eval dataset | Real metrics | Approved | Compat. validated |
|---|---|---|---|---|---|---|---|
| GraphSAGE (`graph_ai.py`) | Exists but for a different, disconnected system | No | No | No | No (hardcoded) | No (`"rejected"`) | No |
| Fusion MLP (`learned_fusion.py`) | Exists but for a different, disconnected system | No | No | No (calibration slice not independent) | No (hardcoded) | No (`active_version: null`) | No |
| Geometry embedding (`geometry_ai.py`) | No | No | N/A (frozen backbone) | No | No | No | No |
| `label_reconstruction` ranker (this session's work) | Yes (`model_registry`) | Yes | Yes (`FEATURE_NAMES`) | Yes (frozen test split) | Yes (measured, not hardcoded) | **No -- deliberately kept `"candidate"`, shadow-only** | Not yet formalized |

Even this session's own `label_reconstruction` ranker does not clear the bar
for production promotion -- not because it's ungoverned, but because its
measured improvement over the deterministic baseline is not yet material
(see the v3 evaluation results). It is the template for what "governed but
appropriately still shadow-only" looks like, not an exception to this policy.
