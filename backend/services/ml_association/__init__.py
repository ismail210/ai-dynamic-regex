"""ML-association review foundation (Phase 2, EXPERIMENTAL, NOT PRODUCTION).

This package builds the versioned, append-only reviewer-data foundation
needed to eventually train a label-to-geometry association ranker
(``docs/geometry_graph_audit/08_prioritized_roadmap.md`` P2, and the
ChatGPT deep-research report's phased roadmap). It does **not** select,
rank, or influence any prediction shown to a current user.

Every entry point that reads/writes reviewer data is gated behind
``config.settings.ml_association_dataset_enabled`` (env var
``ML_ASSOCIATION_DATASET_ENABLED``, default ``false``) via
``service.require_enabled()``. Nothing in ``services/multimodal/pipeline.py``
or ``services/prediction/orchestrator.py`` imports this package — see
``backend/tests/test_ml_association_not_wired_into_production.py``, which
fails the build if that ever changes silently.

Module map
----------
``enums``             -- ReviewLabel / CalloutScope / AdjudicationStatus / ValidationErrorCode
``schemas``            -- versioned pydantic models for rows, groups, and outcomes
``identifiers``         -- deterministic ID derivation (never ``uuid.uuid4()``)
``feature_builder``      -- per-(label, geometry) relationship/context features
``candidate_dataset``     -- deterministic label-group + candidate-row construction
``outcome_store``         -- append-only JSONL reviewed-outcome persistence
``review_export``         -- deterministic JSON + SVG reviewer export
``review_import``         -- parses a reviewer submission into a candidate outcome
``validation``            -- strict import validation with stable error codes
``service``               -- the feature-flag-gated public facade
"""
