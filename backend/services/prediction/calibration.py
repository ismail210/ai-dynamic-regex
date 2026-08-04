"""
Optional confidence calibration.

``ranking_score`` (the existing multimodal attention-fusion score) is a
weighted combination of heterogeneous evidence sources — it is NOT a
calibrated probability. This module maps ``ranking_score`` to an observed
correctness rate via isotonic regression, but ONLY when there is enough
held-out, human-reviewed ground truth to do so responsibly, and it never
touches the family/exact-section model training data itself (no retraining
happens here).

If there is not enough trustworthy data, ``calibrate_score`` returns
``(None, False)`` rather than fabricating a percentage. Callers must then
present ``ranking_score`` as a score, not a probability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import pandas as pd

from config import settings

logger = logging.getLogger("takeoff.calibration")

# Below this many labeled, held-out examples, a calibration curve is not
# trustworthy enough to show a user as a probability.
MIN_CALIBRATION_SAMPLES = 50


@dataclass
class CalibrationModel:
    thresholds: List[float]
    calibrated_values: List[float]
    sample_count: int
    fitted_at: str

    def predict(self, score: float) -> float:
        import numpy as np

        return float(np.interp(score, self.thresholds, self.calibrated_values))

    def to_dict(self) -> dict:
        return {
            "thresholds": self.thresholds,
            "calibrated_values": self.calibrated_values,
            "sample_count": self.sample_count,
            "fitted_at": self.fitted_at,
        }


_CACHED: Optional[CalibrationModel] = None
_CACHE_CHECKED = False


def _load_holdout_examples() -> pd.DataFrame:
    """
    Load reviewer-approved corrections as candidate calibration data.

    ``services.dataset_manager.APPROVED_COLUMNS`` currently records
    ``token``/``class``/``category``/``source``/``approved_at``/``unknown_id``
    — it does not yet record the ranking score that produced each approval,
    or an explicit correct/incorrect label relative to that score. Until that
    schema is extended, this function (and therefore calibration) has nothing
    to fit, which is why ``fit_calibration`` returns ``None`` today rather
    than inventing a curve. Extending ``APPROVED_COLUMNS`` to capture
    ``ranking_score`` and ``correct`` at approval time is the natural next
    step — see the final report for this as a decision for the team.
    """

    if not settings.approved_dataset_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(
            settings.approved_dataset_path, dtype=str, keep_default_na=False
        )
    except (OSError, ValueError):
        return pd.DataFrame()


def fit_calibration(*, force: bool = False) -> Optional[CalibrationModel]:
    """Fit isotonic calibration from approved corrections, or return ``None``."""

    global _CACHED, _CACHE_CHECKED
    if _CACHED is not None and not force:
        return _CACHED
    if _CACHE_CHECKED and not force:
        return None
    _CACHE_CHECKED = True

    frame = _load_holdout_examples()
    if "ranking_score" not in frame.columns or "correct" not in frame.columns:
        logger.info(
            "Calibration skipped: approved dataset lacks ranking_score/correct "
            "columns (%d rows available)",
            len(frame),
        )
        return None

    scores = pd.to_numeric(frame["ranking_score"], errors="coerce")
    labels = pd.to_numeric(frame["correct"], errors="coerce")
    mask = scores.notna() & labels.notna()
    if int(mask.sum()) < MIN_CALIBRATION_SAMPLES:
        logger.info(
            "Calibration skipped: %d labeled samples < required %d",
            int(mask.sum()),
            MIN_CALIBRATION_SAMPLES,
        )
        return None

    from sklearn.isotonic import IsotonicRegression

    regressor = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    regressor.fit(scores[mask].to_numpy(), labels[mask].to_numpy())

    model = CalibrationModel(
        thresholds=[float(v) for v in regressor.X_thresholds_],
        calibrated_values=[float(v) for v in regressor.y_thresholds_],
        sample_count=int(mask.sum()),
        fitted_at=datetime.now(timezone.utc).isoformat(),
    )
    _CACHED = model
    return model


def calibrate_score(ranking_score: float) -> Tuple[Optional[float], bool]:
    """Return ``(final_confidence, confidence_is_calibrated)`` for one score."""

    model = fit_calibration()
    if model is None:
        return None, False
    return round(model.predict(float(ranking_score)), 4), True


def reset_cache() -> None:
    """Test/operational hook forcing recomputation on the next call."""

    global _CACHED, _CACHE_CHECKED
    _CACHED = None
    _CACHE_CHECKED = False
