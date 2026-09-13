"""Learned candidate ranker: scores catalog-valid candidates, never invents them.

This module never calls ``services.database_loader`` or
``services.label_reconstruction.candidates`` itself -- it only scores the
candidate list it is given. The caller (shadow-mode wiring, evaluation
scripts) is responsible for first getting a catalog-valid candidate set from
``candidates.generate_candidates``/``generate_candidates_v3``. This keeps the
"AISC catalog is the final validity constraint" invariant enforced by
construction: this ranker CANNOT produce a label that wasn't already in its
input list.

Scores are plain model outputs (probability of "is a plausible reconstruction
of this corrupted text" from the underlying binary classifier), useful for
RANKING candidates against each other. They are not currently calibrated
probabilities in the "80% score means correct 80% of the time" sense --
Part L of the integration spec explicitly separates ranking-score status
from calibration, which is future work if this graduates out of shadow mode.

Each ``LabelRanker`` carries its OWN ``feature_names`` (read from that
version's registry manifest, i.e. ``feature_schema``), not the module-level
``features.FEATURE_NAMES`` -- ``features.py`` has grown new columns since v2
was trained (v3's structural-compatibility features), and scoring an older
booster with a newer/reordered feature vector raises an xgboost feature-name
mismatch rather than silently producing wrong scores. Always load through
``LabelRanker.load(..., feature_names=<that version's registry entry>)`` or
one of the module-level helpers below, never construct with a guessed schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from services.label_reconstruction.features import FEATURE_NAMES, pair_features


class LabelRanker:
    def __init__(self, booster, version_id: str, feature_names: Sequence[str]) -> None:
        self._booster = booster
        self.version_id = version_id
        self.feature_names: List[str] = list(feature_names)

    @classmethod
    def load(
        cls, model_path: Path, *, version_id: str, feature_names: Optional[Sequence[str]] = None
    ) -> "LabelRanker":
        import xgboost as xgb

        booster = xgb.Booster()
        booster.load_model(str(model_path))
        return cls(booster, version_id, feature_names or FEATURE_NAMES)

    @property
    def supports_broadened_fallback(self) -> bool:
        """True when this version's own recorded schema includes
        ``is_fallback_broadened`` -- i.e. it was trained with schema v5+.
        Callers use this to decide whether it's worth scoring broadened
        (deletion/insertion) fallback candidates with this model at all,
        versus an older promoted version that never saw that context."""

        return "is_fallback_broadened" in self.feature_names

    def score(
        self,
        query: str,
        candidates: Sequence[str],
        *,
        generation_reasons: Optional[Dict[str, List[str]]] = None,
        fuzzy_ranks: Optional[Dict[str, int]] = None,
        is_fallback_broadened: bool = False,
    ) -> List[float]:
        """``candidates`` is assumed to already be in the deterministic
        generator's own priority order (its list position IS the
        ``deterministic_rank`` feature) -- pass
        ``CandidateSet.candidates``/``.generation_reasons``/``.fuzzy_ranks``
        straight through, do not re-sort before calling this.

        ``is_fallback_broadened`` is a query-level flag (Section 10/12 of
        the broadened-ranker brief); harmlessly ignored by any model
        version whose own ``feature_names`` predates schema v5 (that column
        is simply never referenced when building ``rows`` below), so this
        is always safe to pass regardless of which version is active."""

        import xgboost as xgb

        if not candidates:
            return []
        reasons_by_candidate = generation_reasons or {}
        fuzzy_ranks = fuzzy_ranks or {}
        rows = [
            [
                row[name]
                for name in self.feature_names
            ]
            for rank, candidate in enumerate(candidates)
            for row in [
                pair_features(
                    query,
                    candidate,
                    rank=rank,
                    reasons=reasons_by_candidate.get(candidate),
                    fuzzy_rank=fuzzy_ranks.get(candidate),
                    is_fallback_broadened=is_fallback_broadened,
                )
            ]
        ]
        matrix = xgb.DMatrix(rows, feature_names=self.feature_names)
        return [float(s) for s in self._booster.predict(matrix)]

    def rank(
        self,
        query: str,
        candidates: Sequence[str],
        *,
        generation_reasons: Optional[Dict[str, List[str]]] = None,
        fuzzy_ranks: Optional[Dict[str, int]] = None,
        is_fallback_broadened: bool = False,
    ) -> List[str]:
        scores = self.score(
            query, candidates, generation_reasons=generation_reasons, fuzzy_ranks=fuzzy_ranks,
            is_fallback_broadened=is_fallback_broadened,
        )
        ranked = sorted(zip(candidates, scores), key=lambda pair: -pair[1])
        return [label for label, _score in ranked]


_CACHED_RANKER: Optional[LabelRanker] = None


def _resolve_local_artifact_path(entry: dict, model_path: str) -> Optional[Path]:
    """The registry stores the ABSOLUTE path from whichever machine trained
    and promoted the model (e.g. a teammate's ``/Users/.../backend/...``),
    which does not exist on a different machine/OS even though the same
    artifact file is present locally under ``training/models/<family>/
    <version_id>/<basename>``. Try the stored path first (still correct on
    the training machine); fall back to the local, version-scoped path
    derived from ``settings.BASE_DIR`` before giving up."""

    stored = Path(model_path)
    if stored.exists():
        return stored
    from config import BASE_DIR

    local = BASE_DIR / "training" / "models" / "label_reconstruction" / entry["version_id"] / stored.name
    if local.exists():
        return local
    return None


def get_active_ranker() -> Optional[LabelRanker]:
    """Load the promoted label_reconstruction ranker, if one exists and has
    been promoted. Returns None (never raises) when no model is active yet,
    so shadow-mode callers can no-op cleanly before the first training run."""

    global _CACHED_RANKER
    if _CACHED_RANKER is not None:
        return _CACHED_RANKER

    from services.training_pipeline.model_registry import get_active_model

    entry = get_active_model("label_reconstruction")
    if not entry:
        return None
    artifacts = entry.get("artifacts") or {}
    model_path = artifacts.get("booster")
    if not model_path:
        return None
    resolved = _resolve_local_artifact_path(entry, model_path)
    if resolved is None:
        return None
    _CACHED_RANKER = LabelRanker.load(
        resolved,
        version_id=entry["version_id"],
        feature_names=entry.get("feature_schema"),
    )
    return _CACHED_RANKER


def load_ranker_version(version_id: str) -> Optional[LabelRanker]:
    """Load a SPECIFIC registered version regardless of promotion status --
    for offline evaluation/analysis (Part 9's "identical frozen test set"
    comparisons need to score with a particular candidate/rejected version,
    not only whatever is currently promoted)."""

    from services.training_pipeline.model_registry import list_model_versions

    for entry in list_model_versions("label_reconstruction", limit=100)["versions"]:
        if entry.get("version_id") != version_id:
            continue
        model_path = (entry.get("artifacts") or {}).get("booster")
        if not model_path:
            return None
        resolved = _resolve_local_artifact_path(entry, model_path)
        if resolved is None:
            return None
        return LabelRanker.load(
            resolved, version_id=version_id, feature_names=entry.get("feature_schema")
        )
    return None
