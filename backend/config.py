"""
Central configuration for the AI Structural Steel Takeoff Platform.

All paths are resolved relative to the backend package root so the app can be
launched from any working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


BASE_DIR = Path(__file__).resolve().parent


def _env_list(name: str, default: str) -> List[str]:
    return [
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


@dataclass(frozen=True)
class Settings:
    # ---- Filesystem ----------------------------------------------------
    base_dir: Path = BASE_DIR
    uploads_dir: Path = BASE_DIR / "uploads"
    database_dir: Path = BASE_DIR / "database"
    training_dir: Path = BASE_DIR / "training"

    database_file: Path = BASE_DIR / "database" / "aisc-shapes-database-v160-2.xlsx"
    database_sheet: str = "Database v16.0"
    # Derived, all-editions canonical label catalog (see
    # scripts/prepare_aisc_v16_catalog.py). Not wired into the production
    # prediction pipeline yet — services.database_loader (backed by
    # database_file/database_sheet above) remains authoritative until a
    # promoted cutover.
    aisc_v16_label_catalog_path: Path = (
        BASE_DIR / "database" / "aisc_v16_label_catalog.csv"
    )

    # ---- ML artifacts --------------------------------------------------
    model_path: Path = BASE_DIR / "training" / "best_model.pkl"
    preprocessing_pipeline_path: Path = (
        BASE_DIR / "training" / "preprocessing_pipeline.pkl"
    )
    vectorizer_path: Path = BASE_DIR / "training" / "vectorizer.pkl"
    label_encoder_path: Path = BASE_DIR / "training" / "label_encoder.pkl"
    feature_names_path: Path = BASE_DIR / "training" / "feature_names.json"
    model_metadata_path: Path = BASE_DIR / "training" / "model_metadata.json"
    exact_section_model_path: Path = (
        BASE_DIR / "training" / "exact_section_model.joblib"
    )
    exact_section_metadata_path: Path = (
        BASE_DIR / "training" / "exact_section_model_metadata.json"
    )
    exact_section_dataset_path: Path = (
        BASE_DIR / "training" / "exact_section_dataset.csv"
    )
    geometry_embedding_index_path: Path = (
        BASE_DIR / "training" / "geometry_embedding_index.joblib"
    )
    graphsage_model_path: Path = BASE_DIR / "training" / "graphsage_model.pt"
    fusion_model_path: Path = BASE_DIR / "training" / "multimodal_fusion.pt"
    # Promotion gate for the learned fusion MLP. When false, attention fusion
    # ranks candidates without letting multimodal_fusion.pt override the label
    # solely because the checkpoint file exists on disk.
    learned_fusion_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "LEARNED_FUSION_ENABLED", "true"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    # Compatibility file read by older deployments and existing API code.
    legacy_model_meta_path: Path = BASE_DIR / "training" / "model_meta.json"
    # Immutable AISC-derived dataset — never overwrite at runtime.
    training_dataset_path: Path = BASE_DIR / "training" / "training_dataset.csv"
    features_dataset_path: Path = BASE_DIR / "training" / "features_dataset.csv"
    model_comparison_path: Path = BASE_DIR / "training" / "model_comparison.csv"
    model_meta_path: Path = BASE_DIR / "training" / "model_metadata.json"

    # ---- Human-in-the-loop learning datasets --------------------------
    approved_dataset_path: Path = BASE_DIR / "training" / "approved_dataset.csv"
    unknown_tokens_path: Path = BASE_DIR / "training" / "unknown_tokens.csv"
    history_path: Path = BASE_DIR / "training" / "history.csv"
    upload_log_path: Path = BASE_DIR / "training" / "upload_log.csv"
    # Synthetic naming variants for classifier training only (not regex KB).
    augmented_dataset_path: Path = BASE_DIR / "training" / "augmented_dataset.csv"
    augmentation_enabled: bool = True
    augmentation_max_variants_per_token: int = 14

    # ---- Paired PDF + Excel ground-truth training ---------------------
    training_pdf_dir: Path = BASE_DIR / "training" / "pdf"
    training_excel_dir: Path = BASE_DIR / "training" / "excel"
    pair_manifest_path: Path = BASE_DIR / "training" / "pair_manifest.json"
    paired_dataset_path: Path = BASE_DIR / "training" / "paired_takeoff_dataset.csv"
    takeoff_exports_dir: Path = BASE_DIR / "training" / "takeoff_exports"

    # ---- Dynamic Regex knowledge base (internal service) --------------
    knowledge_base_path: Path = BASE_DIR / "training" / "dynamic_regex.json"
    max_examples_per_class: int = 60
    # Cap ranked variants stored per class (readability).
    max_regex_variants_per_class: int = 8

    # ---- Continuous learning / versioned registries -------------------
    datasets_registry_dir: Path = BASE_DIR / "training" / "datasets"
    models_registry_dir: Path = BASE_DIR / "training" / "models"
    continuous_learning_state_path: Path = (
        BASE_DIR / "training" / "continuous_learning_state.json"
    )
    dataset_schema_version: str = "1.0"
    model_schema_version: str = "1.0"
    continuous_learning_threshold: int = 25
    continuous_learning_cooldown_seconds: int = 1800
    geometry_min_samples: int = 80
    graph_min_samples: int = 80
    fusion_min_samples: int = 80
    promotion_accuracy_tolerance: float = 0.02
    promotion_f1_tolerance: float = 0.02

    # ---- ML association dataset (Phase 2, experimental) ---------------
    # Disabled by default. This gates every ml_association service entry
    # point (dataset building, outcome writes, review export/import) so
    # the new package cannot silently run in production paths even
    # though nothing currently imports it. See
    # docs/ml_association_phase/review_workflow.md.
    ml_association_dataset_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "ML_ASSOCIATION_DATASET_ENABLED", "false"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    ml_association_dir: Path = BASE_DIR / "training" / "ml_association"
    ml_association_outcomes_path: Path = (
        BASE_DIR / "training" / "ml_association" / "reviewed_outcomes.jsonl"
    )
    ml_association_export_dir: Path = (
        BASE_DIR / "training" / "ml_association" / "exports"
    )
    ml_association_schema_version: str = "2.0"

    # ---- Spatial association (leader-aware geometry linking) ------------
    # Links text labels to nearby unlabeled linework using the experimental
    # STRtree candidate generator. Associations always require human review.
    spatial_association_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "SPATIAL_ASSOCIATION_ENABLED", "true"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    schedule_ingestion_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "SCHEDULE_INGESTION_ENABLED", "true"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    detail_regions_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "DETAIL_REGIONS_ENABLED", "true"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    document_prior_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "DOCUMENT_PRIOR_ENABLED", "true"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )

    # ---- Project context profile (legend/notes deep analysis) ---------
    # Deterministic-only by default: LEGEND_PROFILE_ENABLED gates the whole
    # feature (page selection + regex abbreviation-rule extraction +
    # caching), and is safe to leave on -- it never touches
    # engineering_tokens/candidates/predictions, only attaches
    # document["legend_profile"] as read-only, informational output.
    # LEGEND_PROFILE_LLM_ENABLED additionally gates the optional one-shot
    # LLM call that proposes executive_summary/source_facts/
    # derived_insights/warnings_and_conflicts/estimator_attention_items; it
    # costs a model call per document, so it defaults off like the ranker
    # flags below, and every LLM-derived item still goes through
    # deterministic quote-grounding (facts) or grounded-evidence-refs
    # (insights) validation before being kept (see
    # services/engineering/legend_llm_provider.py).
    #
    # Default provider is Ollama (free, local, no API key, no data leaves
    # the machine) -- see docs accompanying this commit for the
    # recommended model and why. LEGEND_LLM_PROVIDER/LEGEND_LLM_MODEL/
    # OLLAMA_BASE_URL are the primary knobs; LEGEND_PROFILE_LLM_API_KEY_ENV
    # only matters for the "anthropic" provider.
    legend_profile_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "LEGEND_PROFILE_ENABLED", "true"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    legend_profile_llm_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "LEGEND_PROFILE_LLM_ENABLED", "false"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    legend_llm_provider: str = field(
        default_factory=lambda: os.getenv(
            "LEGEND_LLM_PROVIDER", "ollama"
        ).strip().lower()
    )
    legend_llm_model: str = field(
        default_factory=lambda: os.getenv(
            "LEGEND_LLM_MODEL", "llama3.1:8b"
        )
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
    )
    legend_profile_llm_api_key_env: str = field(
        default_factory=lambda: os.getenv(
            "LEGEND_PROFILE_LLM_API_KEY_ENV", "ANTHROPIC_API_KEY"
        )
    )
    legend_profile_cache_dir: Path = BASE_DIR / "training" / "legend_profiles"

    # ---- Damaged-label reconstruction ranker (shadow mode only) -------
    # Both default false. ML_LABEL_RANKER_SHADOW may be turned on
    # independently of ML_LABEL_RANKER_ENABLED to log the trained
    # ranker's disagreement with the current deterministic candidate
    # order WITHOUT changing any returned prediction; ML_LABEL_RANKER_ENABLED
    # gates actually using the ranker's ordering for a real response, and
    # must stay false until a promoted model + review process says
    # otherwise. See docs/ml_integration/partner_vs_local_comparison.md
    # and services/label_reconstruction/shadow.py.
    ml_label_ranker_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "ML_LABEL_RANKER_ENABLED", "false"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    ml_label_ranker_shadow: bool = field(
        default_factory=lambda: os.getenv(
            "ML_LABEL_RANKER_SHADOW", "false"
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    ml_label_ranker_shadow_log_path: Path = (
        BASE_DIR / "training" / "label_reconstruction_shadow_log.jsonl"
    )
    annotation_edge_cases_path: Path = (
        BASE_DIR / "training" / "annotation_edge_cases.jsonl"
    )
    compound_dimension_seed_path: Path = (
        BASE_DIR / "training" / "compound_dimensions_seed.jsonl"
    )

    # ---- Engineering validation / takeoff (additive) ------------------
    engineering_artifacts_dir: Path = BASE_DIR / "training" / "engineering_artifacts"
    engineering_corrections_path: Path = (
        BASE_DIR / "training" / "engineering_corrections.jsonl"
    )
    # Reviewer's final choice among catalog-valid completions for a
    # missing-thickness (or similarly ambiguous) designation. Separate from
    # engineering_corrections_path: that file is a training-data log, not
    # something read back at analysis-serve time. This one IS read back
    # (services.staged_pipeline.load_cached_analysis) so a human decision
    # survives a refresh instead of the served prediction reverting to
    # "select a candidate".
    human_selections_path: Path = (
        BASE_DIR / "training" / "human_selections.json"
    )
    engineering_uploads_dir: Path = BASE_DIR / "uploads" / "engineering"
    document_registry_dir: Path = BASE_DIR / "training" / "documents"

    # Analysis artifacts are regenerable caches. Cap how many documents are
    # retained and refuse to write when the volume is nearly full, so a large
    # drawing set can never exhaust the disk mid-analysis.
    artifact_retention_documents: int = field(
        default_factory=lambda: int(os.getenv("ARTIFACT_RETENTION_DOCUMENTS", "3"))
    )
    # Keep this well below a typical laptop free-space floor. A 2 GB reserve
    # blocked extraction while 1.4 GB was still free — enough for artifacts.
    artifact_min_free_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("ARTIFACT_MIN_FREE_BYTES", str(400 * 1024 * 1024))
        )
    )

    confidence_high_threshold: float = 0.80
    confidence_medium_threshold: float = 0.55

    # Model probability below this → token flagged uncertain / review candidate.
    auto_accept_probability_threshold: float = 0.70

    # ---- API -----------------------------------------------------------
    api_title: str = "AI Structural Steel Takeoff Platform"
    api_version: str = "6.0.0"
    environment: str = field(
        default_factory=lambda: os.getenv("APP_ENV", "development")
    )
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    workers: int = field(default_factory=lambda: int(os.getenv("WEB_CONCURRENCY", "1")))
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "info").lower()
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
    )
    # Wall-clock budget for one blocking analysis call behind an upload. This
    # must stay strictly below the client timeout (15 min in the API client);
    # if they are equal the browser can abort at the same moment the server
    # replies, which surfaces as a connection reset instead of an HTTP status.
    upload_analysis_timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("UPLOAD_ANALYSIS_TIMEOUT_SECONDS", "600")
        )
    )
    # Extraction and analysis are CPU-bound and hold the GIL. Running several
    # at once makes each one several times slower and starves uploads, so the
    # number of simultaneous heavy stages is capped.
    stage_concurrency: int = field(
        default_factory=lambda: max(1, int(os.getenv("STAGE_CONCURRENCY", "2")))
    )
    # Both dev loopback spellings are distinct browser origins.
    cors_allow_origins: List[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
    )


settings = Settings()
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.engineering_artifacts_dir.mkdir(parents=True, exist_ok=True)
settings.engineering_uploads_dir.mkdir(parents=True, exist_ok=True)
settings.training_pdf_dir.mkdir(parents=True, exist_ok=True)
settings.training_excel_dir.mkdir(parents=True, exist_ok=True)
settings.takeoff_exports_dir.mkdir(parents=True, exist_ok=True)
settings.datasets_registry_dir.mkdir(parents=True, exist_ok=True)
settings.models_registry_dir.mkdir(parents=True, exist_ok=True)
settings.document_registry_dir.mkdir(parents=True, exist_ok=True)
settings.ml_association_dir.mkdir(parents=True, exist_ok=True)
settings.ml_association_export_dir.mkdir(parents=True, exist_ok=True)
