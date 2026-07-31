# Services Documentation

## Prediction

- `prediction/orchestrator.py` — sole production owner of per-token inference.
- `prediction/contract.py` — canonical v2 response serialization and legacy
  aliases.
- `prediction/explanation_engine.py` — ranked candidates, selection/rejection
  rationale, and modality evidence.
- `prediction/confidence_engine.py` — confidence levels and score policy.
- `prediction/review_policy.py` — auto-accept versus engineer review.

## Multimodal

- `multimodal/pipeline.py` — full document orchestration and artifact
  persistence.
- `multimodal/modular_fusion.py` — modality encoding, attention, candidate
  scoring, and fused confidence.
- `multimodal/fusion_engine.py` — compatibility adapter from the canonical
  orchestrator to the `FusionModel` contract; it does not perform independent
  inference.
- `multimodal/correction_engine.py` — OCR/extraction correction candidates.
- `multimodal/validation_engine.py` — canonical PASS/WARNING/FAIL checks.
- `multimodal/review_enrichment.py` — preserves complete prediction evidence
  for Review Queue rows.
- `multimodal/duplicate_detector.py` — component-level duplicate consolidation.

## Engineering

- `engineering/geometry_adapters.py` — normalized geometry providers.
- `engineering/structural_graph.py` — graph construction and relationships.
- `engineering/rule_engine.py` — engineering compatibility findings.
- `engineering/correction_dataset.py` — durable engineer decisions.
- `engineering/excel_loader.py` — flexible/AISC workbook normalization.

## Takeoff and ground truth

- `takeoff/ground_truth_excel.py` — schedule and AISC takeoff parsing. Its
  output role is always `ground_truth`.
- `takeoff/ground_truth_evaluation.py` — precision, recall, quantity, length,
  weight, member, missing, and extra metrics.
- `takeoff/takeoff_validation.py` — PDF prediction versus Excel evaluation.
- `takeoff/paired_dataset_builder.py` — automatic PDF+Excel training rows.
- `takeoff/takeoff_exporter.py` — takeoff workbook generation.

## Training

- `training_pipeline/orchestrator.py` — continuous-learning control plane.
- `training_pipeline/source_ingestion.py` — source lanes and provenance.
- `training_pipeline/preprocessing.py` — shared train/evaluation transforms.
- `training_pipeline/feature_engineering.py` — modality feature rows.
- `training_pipeline/augmentation.py` — train-only augmentation.
- `training_pipeline/trainers.py` — candidate model training.
- `training_pipeline/dataset_registry.py` and `model_registry.py` — immutable
  versions and promotion metadata.

## Supporting services

- `pdf_parser.py` and `document_intelligence.py` — extraction and layout.
- `database_loader.py` — AISC verification and metadata only.
- `dataset_manager.py` — review queue and historical CSV compatibility.
- `component_tracker.py` — stable component identifiers.
- `model_predictor.py` and `exact_section_predictor.py` — model inference
  primitives called by the orchestrator.

## Dependency rule

Routers depend on services. Domain services must not import routers. Frontend
code consumes API contracts only. Prediction services may query the database
after selection for verification, but database results cannot alter the
selected `family` or `section`.
