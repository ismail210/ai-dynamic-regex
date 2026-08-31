"""Production model comparison, selection, evaluation, and persistence."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, label_binarize
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

from config import settings
from services.feature_extractor import (
    CATEGORICAL_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    TEXT_FEATURE_COLUMN,
)
from services.preprocessing_pipeline import (
    build_preprocessing_pipeline,
    transformed_feature_names,
)


RANDOM_STATE = 42
COMPARISON_SAMPLE_CAP = 6000
FINAL_TRAIN_CAP = 16000
CATBOOST_MAX_FIT_ROWS = 4000


class DenseCompatibleClassifier(BaseEstimator, ClassifierMixin):
    """Adapt dense-only estimators (notably CatBoost) to sparse pipeline output."""

    def __init__(
        self,
        estimator: Any | None = None,
        max_fit_rows: int = CATBOOST_MAX_FIT_ROWS,
        random_state: int = RANDOM_STATE,
    ):
        self.estimator = estimator
        self.max_fit_rows = max_fit_rows
        self.random_state = random_state

    def _to_dense(self, X, y=None, *, fitting: bool = False):
        labels = None if y is None else np.asarray(y)
        if hasattr(X, "toarray"):
            matrix = X
            if fitting and matrix.shape[0] > self.max_fit_rows:
                rng = np.random.RandomState(self.random_state)
                indices = rng.choice(
                    matrix.shape[0], size=self.max_fit_rows, replace=False
                )
                matrix = matrix[indices]
                if labels is not None:
                    labels = labels[indices]
            dense = matrix.toarray()
        else:
            dense = np.asarray(X)
            if fitting and dense.shape[0] > self.max_fit_rows:
                rng = np.random.RandomState(self.random_state)
                indices = rng.choice(
                    dense.shape[0], size=self.max_fit_rows, replace=False
                )
                dense = dense[indices]
                if labels is not None:
                    labels = labels[indices]
        return (dense, labels) if y is not None else dense

    def fit(self, X, y):
        if self.estimator is None:
            raise ValueError("DenseCompatibleClassifier requires an estimator")
        dense, labels = self._to_dense(X, y, fitting=True)
        self.estimator_ = clone(self.estimator)
        self.estimator_.fit(dense, labels)
        self.classes_ = np.asarray(
            getattr(self.estimator_, "classes_", np.unique(labels))
        )
        return self

    def predict(self, X):
        return np.asarray(self.estimator_.predict(self._to_dense(X))).reshape(-1)

    def predict_proba(self, X):
        return np.asarray(self.estimator_.predict_proba(self._to_dense(X)))


def load_model_metadata() -> dict[str, Any]:
    """Load current metadata, including the legacy filename during migration."""

    for path in (settings.model_metadata_path, settings.legacy_model_meta_path):
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _candidate_estimators(min_class_count: int) -> tuple[dict[str, Any], dict[str, str]]:
    """Create all requested estimators and report unavailable optional models."""

    svm_base = LinearSVC(
        class_weight="balanced",
        max_iter=4000,
        random_state=RANDOM_STATE,
    )
    if min_class_count >= 2:
        svm_model: Any = CalibratedClassifierCV(
            svm_base,
            cv=min(3, min_class_count),
        )
    else:
        # Rare-class comparison folds cannot calibrate; predictor still has
        # a decision_function fallback for LinearSVC.
        svm_model = svm_base

    models: dict[str, Any] = {
        "Random Forest": RandomForestClassifier(
            n_estimators=160,
            max_depth=22,
            min_samples_leaf=1,
            class_weight="balanced_subsample",
            n_jobs=2,
            random_state=RANDOM_STATE,
        ),
        "SVM": svm_model,
        "XGBoost": XGBClassifier(
            n_estimators=120,
            max_depth=6,
            learning_rate=0.12,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=RANDOM_STATE,
            eval_metric="mlogloss",
            n_jobs=2,
            tree_method="hist",
        ),
    }
    unavailable: dict[str, str] = {}

    try:
        from lightgbm import LGBMClassifier

        models["LightGBM"] = LGBMClassifier(
            n_estimators=180,
            learning_rate=0.08,
            num_leaves=31,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            verbosity=-1,
            n_jobs=2,
        )
    except Exception as exc:  # pragma: no cover - depends on optional package
        unavailable["LightGBM"] = str(exc)

    try:
        from catboost import CatBoostClassifier

        models["CatBoost"] = DenseCompatibleClassifier(
            CatBoostClassifier(
                iterations=120,
                depth=6,
                learning_rate=0.1,
                loss_function="MultiClass",
                verbose=False,
                random_seed=RANDOM_STATE,
                allow_writing_files=False,
                thread_count=2,
            ),
            max_fit_rows=CATBOOST_MAX_FIT_ROWS,
            random_state=RANDOM_STATE,
        )
    except Exception as exc:  # pragma: no cover - depends on optional package
        unavailable["CatBoost"] = str(exc)
    return models, unavailable


def _probability_matrix(model: Pipeline, X: pd.Series, class_count: int):
    if hasattr(model, "predict_proba"):
        probabilities = np.asarray(model.predict_proba(X), dtype=float)
    elif hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(X), dtype=float)
        if scores.ndim == 1:
            scores = np.column_stack((-scores, scores))
        scores -= scores.max(axis=1, keepdims=True)
        probabilities = np.exp(scores)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
    else:
        return None

    if probabilities.ndim != 2 or probabilities.shape[1] != class_count:
        return None
    return probabilities


def _evaluate(
    model: Pipeline,
    X_test: pd.Series,
    y_test: np.ndarray,
    encoder: LabelEncoder,
    *,
    fit_encoder: LabelEncoder | None = None,
) -> dict[str, Any]:
    eval_encoder = fit_encoder or encoder
    if fit_encoder is not None:
        X_test, y_test = _filter_eval_split(
            X_test, y_test, encoder, fit_encoder
        )

    predicted = np.asarray(model.predict(X_test)).reshape(-1).astype(int)
    labels = np.arange(len(eval_encoder.classes_))
    metrics: dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "precision_weighted": round(
            float(
                precision_score(
                    y_test, predicted, average="weighted", zero_division=0
                )
            ),
            4,
        ),
        "recall_weighted": round(
            float(recall_score(y_test, predicted, average="weighted", zero_division=0)),
            4,
        ),
        "f1_weighted": round(
            float(f1_score(y_test, predicted, average="weighted", zero_division=0)),
            4,
        ),
        "confusion_matrix": confusion_matrix(
            y_test, predicted, labels=labels
        ).tolist(),
        "classification_report":         classification_report(
            y_test,
            predicted,
            labels=labels,
            target_names=[str(value) for value in eval_encoder.classes_],
            output_dict=True,
            zero_division=0,
        ),
        "roc_auc_weighted_ovr": None,
    }

    probabilities = _probability_matrix(model, X_test, len(labels))
    if probabilities is not None:
        try:
            if len(labels) == 2:
                auc = roc_auc_score(y_test, probabilities[:, 1])
            else:
                binary_targets = label_binarize(y_test, classes=labels)
                auc = roc_auc_score(
                    binary_targets,
                    probabilities,
                    average="weighted",
                    multi_class="ovr",
                )
            metrics["roc_auc_weighted_ovr"] = round(
                float(auc),
                4,
            )
        except ValueError:
            pass
    return metrics


def _atomic_joblib_dump(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(value, temporary)
    os.replace(temporary, path)


def _atomic_json_dump(value: Any, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _comparison_sample(
    X_train: pd.Series,
    y_train: np.ndarray,
) -> tuple[pd.Series, np.ndarray]:
    if len(X_train) <= COMPARISON_SAMPLE_CAP:
        return X_train, y_train
    try:
        sampled, _, sampled_y, _ = train_test_split(
            X_train,
            y_train,
            train_size=COMPARISON_SAMPLE_CAP,
            random_state=RANDOM_STATE,
            stratify=y_train,
        )
        return sampled, sampled_y
    except ValueError:
        sampled, _, sampled_y, _ = train_test_split(
            X_train,
            y_train,
            train_size=COMPARISON_SAMPLE_CAP,
            random_state=RANDOM_STATE,
        )
        return sampled, sampled_y


def _maybe_cap_training(
    X: pd.Series,
    y: np.ndarray,
    *,
    max_rows: int,
) -> tuple[pd.Series, np.ndarray]:
    if len(X) <= max_rows:
        return X, y
    try:
        capped, _, capped_y, _ = train_test_split(
            X,
            y,
            train_size=max_rows,
            random_state=RANDOM_STATE,
            stratify=y,
        )
    except ValueError:
        capped, _, capped_y, _ = train_test_split(
            X,
            y,
            train_size=max_rows,
            random_state=RANDOM_STATE,
        )
    return capped, capped_y


def _encoder_for_training_subset(
    y_train: np.ndarray,
    encoder: LabelEncoder,
) -> tuple[np.ndarray, LabelEncoder, list[str]]:
    """
    Remap the post-split training labels to contiguous 0..k-1.

    XGBoost (via sklearn) requires training ``y`` to contain every class id
    from 0..n-1. After stratified split + row capping, a globally-encoded
    label column can have gaps (e.g. class id 2 absent while id 52 present).

    ``excluded`` is descriptive metadata for the rows that were actually
    selected: it contains only global dataset classes absent from
    ``y_train``. A rare class retained by the cap is therefore trained and
    must not be reported as excluded.
    """

    present_names = encoder.inverse_transform(np.unique(y_train))
    fit_encoder = LabelEncoder()
    fit_encoder.fit(present_names)
    train_names = encoder.inverse_transform(y_train)
    y_fit = fit_encoder.transform(train_names)
    excluded = [
        str(label)
        for label in encoder.classes_
        if str(label) not in {str(value) for value in fit_encoder.classes_}
    ]
    return y_fit, fit_encoder, excluded


def _filter_eval_split(
    X_test: pd.Series,
    y_test: np.ndarray,
    global_encoder: LabelEncoder,
    fit_encoder: LabelEncoder,
) -> tuple[pd.Series, np.ndarray]:
    test_names = global_encoder.inverse_transform(y_test)
    mask = np.isin(test_names, fit_encoder.classes_)
    if not mask.any():
        raise ValueError("No held-out rows remain for trained classes")
    X_eval = X_test.iloc[mask] if hasattr(X_test, "iloc") else X_test[mask]
    y_eval = fit_encoder.transform(test_names[mask])
    return X_eval, y_eval


def train_xgboost(
    training_frame: pd.DataFrame,
    *,
    actor: str = "user",
    canonical_rows: int | None = None,
    approved_examples: int = 0,
    augmentation: dict[str, Any] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    """Fit only the established production XGBoost model and save artifacts."""

    def progress(step: str, percent: int) -> None:
        if progress_callback:
            progress_callback(step, percent)

    if "token" not in training_frame or "class" not in training_frame:
        raise ValueError("Training data must contain token and class columns")

    progress("Preparing training data", 10)
    clean = training_frame[["token", "class"]].copy()
    clean["token"] = clean["token"].fillna("").astype(str).str.strip()
    clean["class"] = clean["class"].fillna("").astype(str).str.strip().str.upper()
    clean = clean[(clean["token"] != "") & (clean["class"] != "")]
    if clean.empty or clean["class"].nunique() < 2:
        raise ValueError("At least two populated classes are required to train")

    encoder = LabelEncoder()
    y = encoder.fit_transform(clean["class"])
    X = clean["token"]
    if int(np.bincount(y).min()) < 2:
        raise ValueError("Every class requires at least two samples to train")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    X_train, y_train = _maybe_cap_training(
        X_train, y_train, max_rows=FINAL_TRAIN_CAP
    )
    global_encoder = encoder
    y_train, fit_encoder, excluded_classes = _encoder_for_training_subset(
        y_train, global_encoder
    )

    progress("Building preprocessing pipeline", 25)
    estimator = XGBClassifier(
        n_estimators=120,
        max_depth=6,
        learning_rate=0.12,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=RANDOM_STATE,
        eval_metric="mlogloss",
        n_jobs=2,
        tree_method="hist",
    )
    pipeline = Pipeline(
        steps=[
            ("preprocessing", build_preprocessing_pipeline()),
            ("model", estimator),
        ]
    )

    progress("Training XGBoost", 40)
    started = time.perf_counter()
    pipeline.fit(X_train, y_train)
    training_time = round(time.perf_counter() - started, 3)

    progress("Evaluating model", 78)
    metrics = _evaluate(
        pipeline,
        X_test,
        y_test,
        global_encoder,
        fit_encoder=fit_encoder,
    )
    preprocessing = pipeline.named_steps["preprocessing"]
    best_model = pipeline.named_steps["model"]
    feature_names = transformed_feature_names(preprocessing)

    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "schema_version": 2,
        "trained_at": now,
        "actor": actor,
        "model": "XGBoost",
        "training_mode": "fast_retrain",
        "feature_extractor": (
            "Character TF-IDF ngrams 2-5 + engineered structural features"
        ),
        "rows": int(len(clean)),
        "trained_rows": int(len(X_train)),
        "canonical_rows": int(canonical_rows or len(clean)),
        "classes": int(len(fit_encoder.classes_)),
        "class_labels": [str(value) for value in fit_encoder.classes_],
        "excluded_training_classes": excluded_classes,
        "dataset_classes": int(len(global_encoder.classes_)),
        "approved_examples": int(approved_examples),
        "augmentation": augmentation or {},
        "model_comparison": [],
        "metrics": {
            **metrics,
            "training_time_sec": training_time,
        },
        "artifacts": {
            "model": settings.model_path.name,
            "preprocessing_pipeline": settings.preprocessing_pipeline_path.name,
            "label_encoder": settings.label_encoder_path.name,
            "metadata": settings.model_metadata_path.name,
            "feature_names": settings.feature_names_path.name,
        },
    }
    feature_manifest = {
        "schema_version": 2,
        "raw_input": "token",
        "engineered_columns": FEATURE_COLUMNS,
        "text_column": TEXT_FEATURE_COLUMN,
        "numeric_columns": NUMERIC_FEATURE_COLUMNS,
        "categorical_columns": CATEGORICAL_FEATURE_COLUMNS,
        "transformed_feature_count": len(feature_names),
        "transformed_feature_names": feature_names,
    }

    progress("Saving model artifacts", 88)
    settings.training_dir.mkdir(parents=True, exist_ok=True)
    _atomic_joblib_dump(best_model, settings.model_path)
    _atomic_joblib_dump(preprocessing, settings.preprocessing_pipeline_path)
    _atomic_joblib_dump(fit_encoder, settings.label_encoder_path)
    _atomic_json_dump(feature_manifest, settings.feature_names_path)
    _atomic_json_dump(metadata, settings.model_metadata_path)
    _atomic_json_dump(metadata, settings.legacy_model_meta_path)
    progress("Model artifacts saved", 94)
    return metadata


def train_models(
    training_frame: pd.DataFrame,
    *,
    actor: str = "user",
    canonical_rows: int | None = None,
    approved_examples: int = 0,
    augmentation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compare requested classifiers and persist the best feature-based pipeline.

    Every candidate is an sklearn ``Pipeline`` containing raw-token feature
    extraction, a ``ColumnTransformer``, and the estimator. The winning fitted
    preprocessing and estimator are persisted separately for explicit runtime
    stages without duplicating any preprocessing logic.
    """

    if "token" not in training_frame or "class" not in training_frame:
        raise ValueError("Training data must contain token and class columns")

    clean = training_frame[["token", "class"]].copy()
    clean["token"] = clean["token"].fillna("").astype(str).str.strip()
    clean["class"] = clean["class"].fillna("").astype(str).str.strip().str.upper()
    clean = clean[(clean["token"] != "") & (clean["class"] != "")]
    if clean.empty or clean["class"].nunique() < 2:
        raise ValueError("At least two populated classes are required to train")

    encoder = LabelEncoder()
    y = encoder.fit_transform(clean["class"])
    X = clean["token"]
    class_counts = np.bincount(y)
    min_class_count = int(class_counts.min())
    if min_class_count < 2:
        raise ValueError("Every class requires at least two samples to train")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    X_train, y_train = _maybe_cap_training(
        X_train, y_train, max_rows=FINAL_TRAIN_CAP
    )
    global_encoder = encoder
    y_train, fit_encoder, excluded_classes = _encoder_for_training_subset(
        y_train, global_encoder
    )
    X_compare, y_compare = _comparison_sample(X_train, y_train)
    compare_min_class_count = int(np.bincount(y_compare).min())
    candidates, unavailable = _candidate_estimators(compare_min_class_count)

    comparison: list[dict[str, Any]] = []
    best_name: str | None = None
    best_score = (-1.0, -1.0)

    for name, estimator in candidates.items():
        print(f"[train] comparing {name} on {len(X_compare)} rows…", flush=True)
        candidate = Pipeline(
            steps=[
                ("preprocessing", build_preprocessing_pipeline()),
                ("model", estimator),
            ]
        )
        started = time.perf_counter()
        try:
            candidate.fit(X_compare, y_compare)
            metrics = _evaluate(
                candidate,
                X_test,
                y_test,
                global_encoder,
                fit_encoder=fit_encoder,
            )
            elapsed = round(time.perf_counter() - started, 3)
            print(
                f"[train] {name} acc={metrics['accuracy']} "
                f"f1={metrics['f1_weighted']} t={elapsed}s",
                flush=True,
            )
            result = {
                "model": name,
                "status": "trained",
                "training_time_sec": elapsed,
                **metrics,
            }
            comparison.append(result)
            score = (metrics["f1_weighted"], metrics["accuracy"])
            if score > best_score:
                best_score = score
                best_name = name
        except Exception as exc:
            print(f"[train] {name} failed: {exc}", flush=True)
            comparison.append(
                {
                    "model": name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "training_time_sec": round(time.perf_counter() - started, 3),
                }
            )

    for name, reason in unavailable.items():
        comparison.append(
            {
                "model": name,
                "status": "unavailable",
                "error": reason,
                "training_time_sec": 0.0,
            }
        )

    if best_name is None:
        raise RuntimeError("No candidate model trained successfully")

    final_estimator = clone(candidates[best_name])
    final_pipeline = Pipeline(
        steps=[
            ("preprocessing", build_preprocessing_pipeline()),
            ("model", final_estimator),
        ]
    )
    # Prefer the capped training split for the final fit when the full merged
    # set is very large; still larger than the comparison sample.
    X_final, y_final = X_train, y_train
    print(
        f"[train] refitting winner={best_name} on {len(X_final)} rows…",
        flush=True,
    )
    refit_started = time.perf_counter()
    final_pipeline.fit(X_final, y_final)
    refit_time = round(time.perf_counter() - refit_started, 3)
    preprocessing = final_pipeline.named_steps["preprocessing"]
    best_model = final_pipeline.named_steps["model"]
    feature_names = transformed_feature_names(preprocessing)

    selected_metrics = next(
        row for row in comparison if row.get("model") == best_name
    )
    comparison_rows = [
        {
            "Model": row.get("model"),
            "Status": row.get("status"),
            "Accuracy": row.get("accuracy"),
            "Precision": row.get("precision_weighted"),
            "Recall": row.get("recall_weighted"),
            "F1": row.get("f1_weighted"),
            "ROC AUC": row.get("roc_auc_weighted_ovr"),
            "Training Time (sec)": row.get("training_time_sec"),
            "Error": row.get("error", ""),
        }
        for row in comparison
    ]

    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "schema_version": 2,
        "trained_at": now,
        "actor": actor,
        "model": best_name,
        "feature_extractor": (
            "Character TF-IDF ngrams 2-5 + engineered structural features"
        ),
        "rows": int(len(clean)),
        "canonical_rows": int(canonical_rows or len(clean)),
        "classes": int(len(fit_encoder.classes_)),
        "class_labels": [str(value) for value in fit_encoder.classes_],
        "excluded_training_classes": excluded_classes,
        "dataset_classes": int(len(global_encoder.classes_)),
        "approved_examples": int(approved_examples),
        "augmentation": augmentation or {},
        "model_comparison": comparison_rows,
        "model_comparison_details": comparison,
        "metrics": {
            "accuracy": selected_metrics["accuracy"],
            "precision_weighted": selected_metrics["precision_weighted"],
            "recall_weighted": selected_metrics["recall_weighted"],
            "f1_weighted": selected_metrics["f1_weighted"],
            "roc_auc_weighted_ovr": selected_metrics["roc_auc_weighted_ovr"],
            "training_time_sec": round(
                float(selected_metrics["training_time_sec"]) + refit_time, 3
            ),
            "confusion_matrix": selected_metrics["confusion_matrix"],
            "classification_report": selected_metrics["classification_report"],
        },
        "artifacts": {
            "model": settings.model_path.name,
            "preprocessing_pipeline": settings.preprocessing_pipeline_path.name,
            "label_encoder": settings.label_encoder_path.name,
            "metadata": settings.model_metadata_path.name,
            "feature_names": settings.feature_names_path.name,
        },
    }
    feature_manifest = {
        "schema_version": 2,
        "raw_input": "token",
        "engineered_columns": FEATURE_COLUMNS,
        "text_column": TEXT_FEATURE_COLUMN,
        "numeric_columns": NUMERIC_FEATURE_COLUMNS,
        "categorical_columns": CATEGORICAL_FEATURE_COLUMNS,
        "transformed_feature_count": len(feature_names),
        "transformed_feature_names": feature_names,
    }

    settings.training_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(comparison_rows).to_csv(
        settings.model_comparison_path, index=False
    )
    _atomic_joblib_dump(best_model, settings.model_path)
    _atomic_joblib_dump(preprocessing, settings.preprocessing_pipeline_path)
    _atomic_joblib_dump(fit_encoder, settings.label_encoder_path)
    _atomic_json_dump(feature_manifest, settings.feature_names_path)
    _atomic_json_dump(metadata, settings.model_metadata_path)
    # Preserve current statistics/history readers during rolling deployments.
    _atomic_json_dump(metadata, settings.legacy_model_meta_path)
    return metadata
