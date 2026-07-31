"""
Backend service layer.

Canonical ownership:

- ``document_registry`` / ``staged_pipeline`` — upload, extract, analyze stages
- ``services.multimodal`` — fusion, correction, explanation, validation
- ``services.engineering`` — geometry, graph, rules, engineering helpers
- ``services.takeoff`` — paired datasets, takeoff validation, Excel export
- ML / features (flat modules) — ``model_predictor``, ``feature_extractor``,
  ``preprocessing_pipeline``, ``training_service``, ``exact_section_predictor``
- Regex (internal) — ``regex_*``, ``self_learning_engine``, ``dynamic_regex_service``
- Data / HITL — ``dataset_manager``, ``dataset_builder``, ``database_loader``,
  ``data_augmentation``, ``data_quality``
"""
