"""
AI Shape Classifier
===================

Loads the trained model artifacts once and exposes prediction helpers.

- ``predict_shape``            : backward-compatible label-only prediction.
- ``predict_with_confidence``  : returns the label together with the model's
                                 probability and the full class distribution,
                                 which feeds the confidence-scoring engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional

import joblib
import numpy as np

from config import settings


# ==========================================
# Load AI Components (only once)
# ==========================================
model = None
preprocessing_pipeline = None
# Kept only as a migration fallback for pre-v2 artifacts.
vectorizer = None
encoder = None
_artifact_mode = ""
_CLASS_LABELS: List[str] = []


def reload_model() -> bool:
    """Reload model artifacts so retraining takes effect without restart."""
    global model, preprocessing_pipeline, vectorizer, encoder, _artifact_mode
    global _CLASS_LABELS

    try:
        loaded_model = joblib.load(settings.model_path)
        loaded_encoder = joblib.load(settings.label_encoder_path)
        if settings.preprocessing_pipeline_path.exists():
            loaded_preprocessing = joblib.load(settings.preprocessing_pipeline_path)
            loaded_vectorizer = None
            artifact_mode = "feature_pipeline"
        else:
            loaded_preprocessing = None
            loaded_vectorizer = joblib.load(settings.vectorizer_path)
            artifact_mode = "legacy_tfidf"
    except (FileNotFoundError, OSError, ValueError, ImportError, AttributeError):
        model = preprocessing_pipeline = vectorizer = encoder = None
        _artifact_mode = ""
        _CLASS_LABELS = []
        _cached_prediction.cache_clear()
        return False

    model = loaded_model
    preprocessing_pipeline = loaded_preprocessing
    vectorizer = loaded_vectorizer
    encoder = loaded_encoder
    _artifact_mode = artifact_mode
    _CLASS_LABELS = list(encoder.classes_)
    _cached_prediction.cache_clear()
    return True


def _normalize(token: str) -> str:
    return str(token).upper().strip().replace(" ", "")


def _transform(token: str):
    if _artifact_mode == "feature_pipeline" and preprocessing_pipeline is not None:
        # Normalization and engineered feature extraction are pipeline steps.
        return preprocessing_pipeline.transform([str(token)])
    if _artifact_mode == "legacy_tfidf" and vectorizer is not None:
        return vectorizer.transform([_normalize(token)])
    return None


def _encoded_prediction(prediction) -> int:
    values = np.asarray(prediction).reshape(-1)
    if values.dtype.kind in {"U", "O", "S"}:
        values = values.astype(float)
    return int(values[0])


def _class_index_map(proba_width: int) -> np.ndarray:
    classes = getattr(model, "classes_", None)
    if classes is None:
        return np.arange(proba_width, dtype=int)
    encoded = np.asarray(classes).reshape(-1)
    if encoded.dtype.kind in {"U", "O", "S"}:
        encoded = encoded.astype(float)
    return encoded.astype(int)


@dataclass
class Prediction:
    label: Optional[str]
    probability: float
    distribution: Dict[str, float]

    def to_dict(self) -> dict:
        top = sorted(
            self.distribution.items(), key=lambda kv: kv[1], reverse=True
        )[:5]
        return {
            "label": self.label,
            "probability": round(self.probability, 4),
            "top_classes": [
                {"class": c, "probability": round(p, 4)} for c, p in top
            ],
        }


def predict_shape(token: str) -> Optional[str]:
    """Backward-compatible: return only the predicted class label."""

    if not token:
        return None
    if model is None or encoder is None:
        return None
    X = _transform(token)
    if X is None:
        return None
    prediction = model.predict(X)
    return encoder.inverse_transform([_encoded_prediction(prediction)])[0]


def predict_with_confidence(token: str) -> Prediction:
    """
    Predict the class and return the winning probability plus the full
    probability distribution across classes.

    Cached per token because one drawing set repeats the same few hundred
    labels thousands of times. A copy is returned so callers can never mutate
    the cached distribution.
    """

    cached = _cached_prediction(str(token))
    return Prediction(
        label=cached.label,
        probability=cached.probability,
        distribution=dict(cached.distribution),
    )


@lru_cache(maxsize=20_000)
def _cached_prediction(token: str) -> Prediction:
    """Run the estimator once per distinct token."""

    if not token:
        return Prediction(label=None, probability=0.0, distribution={})
    if model is None or encoder is None:
        return Prediction(label=None, probability=0.0, distribution={})

    X = _transform(token)
    if X is None:
        return Prediction(label=None, probability=0.0, distribution={})

    if hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X)[0], dtype=float)
        idx = int(np.argmax(proba))
        encoded_classes = _class_index_map(len(proba))
        label = encoder.inverse_transform([encoded_classes[idx]])[0]
        distribution = {
            str(encoder.inverse_transform([encoded_classes[i]])[0]): float(proba[i])
            for i in range(len(proba))
        }
        return Prediction(
            label=label,
            probability=float(proba[idx]),
            distribution=distribution,
        )

    # LinearSVC / similar: map decision_function scores to a soft distribution.
    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(X), dtype=float).reshape(-1)
        if len(scores) == 1 and len(_CLASS_LABELS) == 2:
            # Binary decision score → two-class softmax-ish
            scores = np.array([-scores[0], scores[0]])
        exp = np.exp(scores - np.max(scores))
        proba = exp / exp.sum()
        idx = int(np.argmax(proba))
        encoded_classes = _class_index_map(len(proba))
        label = encoder.inverse_transform([encoded_classes[idx]])[0]
        distribution = {
            str(encoder.inverse_transform([encoded_classes[i]])[0]): float(proba[i])
            for i in range(len(proba))
        }
        return Prediction(
            label=label,
            probability=float(proba[idx]),
            distribution=distribution,
        )

    # Estimator without probabilities: report a single deterministic class.
    label = predict_shape(token)
    return Prediction(
        label=label,
        probability=1.0 if label else 0.0,
        distribution={label: 1.0} if label else {},
    )


def list_classes() -> List[str]:
    return list(_CLASS_LABELS)


reload_model()
