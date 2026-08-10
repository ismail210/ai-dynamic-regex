"""Stable contracts for continuous-learning datasets and models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


MODALITIES = (
    "text",
    "ocr",
    "layout",
    "geometry",
    "graph",
    "engineering",
    "fusion",
    "label_reconstruction",
)
MODEL_FAMILIES = (
    "family_classifier",
    "exact_section",
    "ocr",
    "layout",
    "geometry",
    "graph",
    "engineering",
    "fusion",
    "label_reconstruction",
)
SPLITS = ("train", "validation", "test")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceProvenance:
    source_type: str
    source_id: str = ""
    document_id: str = ""
    object_id: str = ""
    actor: str = ""
    created_at: str = ""
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrainingSample:
    sample_id: str
    modality: str
    content_hash: str
    token: str = ""
    family: Optional[str] = None
    section: Optional[str] = None
    label: Optional[str] = None
    supervised: bool = False
    split: str = "train"
    quality_status: str = "unknown"
    features: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    parent_sample_id: Optional[str] = None
    augmented: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetManifest:
    version_id: str
    modality: str
    schema_version: str
    created_at: str
    sample_count: int
    supervised_count: int
    unlabeled_count: int
    class_distribution: Dict[str, int]
    source_counts: Dict[str, int]
    split_counts: Dict[str, int]
    checksum: str
    parent_versions: List[str] = field(default_factory=list)
    feature_schema: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelManifest:
    version_id: str
    family: str
    schema_version: str
    created_at: str
    dataset_versions: Dict[str, str]
    metrics: Dict[str, Any]
    hyperparameters: Dict[str, Any]
    feature_schema: List[str]
    artifact_checksums: Dict[str, str]
    promotion_status: str
    rejection_reasons: List[str] = field(default_factory=list)
    parent_version: Optional[str] = None
    dependencies: Dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
