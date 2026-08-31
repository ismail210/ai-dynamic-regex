"""Regex-free AI correction using multimodal and reviewed-example evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import settings
from services.dataset_manager import dataset_manager
from services.exact_section_predictor import predict_exact_sections
from services.family_codes import MODERN_FAMILY_PREFIXES


FAMILY_PREFIXES = MODERN_FAMILY_PREFIXES
CORRECTION_WEIGHTS = {
    "text": 0.38,
    "similarity_search": 0.22,
    "geometry": 0.15,
    "graph": 0.12,
    "engineering_context": 0.08,
    "review_history": 0.05,
}

_HISTORY_CACHE: tuple[float, List[dict]] = (-1.0, [])
_INDEX_CACHE: Dict[str, Any] = {"examples": None, "history": None}


def _clip(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=200_000)
def _fold_text(text: str) -> str:
    text = text.upper().strip()
    text = text.replace("×", "X").replace("✕", "X")
    return "".join(
        char for char in text if char.isalnum() or char in {"/", "."}
    )


def _fold(value: Any) -> str:
    """Comparable text form built with character operations, never regex."""

    return _fold_text(str(value or ""))


def _family(value: Any) -> str:
    folded = _fold(value)
    for prefix in FAMILY_PREFIXES:
        if folded.startswith(prefix):
            return prefix
    return ""


@lru_cache(maxsize=400_000)
def _folded_similarity(source: str, target: str) -> float:
    return SequenceMatcher(None, source, target).ratio()


def _text_similarity(left: Any, right: Any) -> float:
    """
    Ratio over folded text, memoized.

    One drawing scores the same handful of tokens against the same candidate
    pool thousands of times, and difflib dominated the per-token cost.
    """

    source = _fold(left)
    target = _fold(right)
    if not source or not target:
        return 0.0
    return _folded_similarity(source, target)


def _reviewed_examples() -> List[dict]:
    """Load human-approved corrections with a lightweight mtime cache."""

    global _HISTORY_CACHE
    path = Path(settings.approved_dataset_path)
    stamp = path.stat().st_mtime if path.exists() else -1.0
    if stamp == _HISTORY_CACHE[0]:
        return _HISTORY_CACHE[1]
    frame = dataset_manager.load_approved_dataset()
    examples = [
        {
            "original": str(row.get("token") or "").strip(),
            "corrected": str(row.get("class") or "").strip().upper(),
            "source": str(row.get("source") or "human_review"),
        }
        for _, row in frame.iterrows()
        if str(row.get("token") or "").strip()
        and str(row.get("class") or "").strip()
    ]
    _HISTORY_CACHE = (stamp, examples)
    return examples


@dataclass(frozen=True)
class _ReviewHistory:
    """Reviewed corrections plus the lookup structures derived from them."""

    examples: List[dict]
    by_corrected: Dict[str, List[dict]]
    candidate_families: tuple[tuple[str, str], ...]


def _review_history() -> _ReviewHistory:
    """
    Reviewed examples with their per-candidate indexes built once.

    Rebuilding these on every token was quadratic in reviewed-history size;
    the indexes are reused while the loaded example list is unchanged.
    """

    examples = _reviewed_examples()
    if _INDEX_CACHE["examples"] is examples:
        return _INDEX_CACHE["history"]

    by_corrected: Dict[str, List[dict]] = {}
    candidate_families: List[tuple[str, str]] = []
    seen_shapes: set[str] = set()
    for example in examples:
        shape = str(example.get("corrected") or "")
        by_corrected.setdefault(_fold(shape), []).append(example)
        if shape and shape not in seen_shapes:
            seen_shapes.add(shape)
            candidate_families.append((shape, _family(shape)))

    history = _ReviewHistory(
        examples=examples,
        by_corrected=by_corrected,
        candidate_families=tuple(candidate_families),
    )
    _INDEX_CACHE["examples"] = examples
    _INDEX_CACHE["history"] = history
    return history


def _history_evidence(
    original: str,
    candidate: str,
    examples_by_corrected: Dict[str, List[dict]],
) -> tuple[float, Optional[dict]]:
    best_score = 0.0
    best: Optional[dict] = None
    for example in examples_by_corrected.get(_fold(candidate), ()):
        score = _text_similarity(original, example.get("original"))
        if score > best_score:
            best_score = score
            best = example
    return best_score, best


def _context_score(candidate: str, expected_family: Optional[str]) -> float:
    if not expected_family:
        return 0.55
    return 1.0 if _family(candidate) == _fold(expected_family) else 0.15


def _issue_types(original: str, corrected: str) -> List[str]:
    """Describe likely defects from edit structure without pattern matching."""

    source = _fold(original)
    target = _fold(corrected)
    issues: List[str] = []
    if source == target:
        return issues
    if not source:
        return ["missing_label"]
    wrong_prefix = (
        source.startswith("WF") and target.startswith("W")
    ) or (
        source.startswith("TS") and target.startswith("HSS")
    )
    if wrong_prefix or _family(source) != _family(target):
        issues.append("wrong_prefix")
    source_digits = sum(char.isdigit() for char in source)
    target_digits = sum(char.isdigit() for char in target)
    if source_digits < target_digits:
        issues.append("missing_digits")
    if "X" not in source and "X" in target:
        issues.append("missing_separator")
    if len(source) == len(target):
        substitutions = sum(a != b for a, b in zip(source, target))
        if substitutions:
            issues.append("ocr_or_typo")
    elif source_digits == target_digits:
        issues.append("merged_or_split_label")
    if not issues:
        issues.append("wrong_label")
    return issues


@dataclass
class CorrectionCandidate:
    original: str
    corrected: str
    confidence: float
    issue_types: List[str]
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    database_match: bool = False

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "confidence": round(self.confidence, 4),
            "issue_types": self.issue_types,
            "reason": self.reason,
            "evidence": self.evidence,
            "alternative_candidates": self.alternatives,
            "database_match": False,
            "database_role": "not_used",
            "regex_used": False,
        }


@dataclass
class CorrectionResult:
    original: str
    corrected: str
    confidence: float
    reason: str
    evidence: Dict[str, Any]
    alternative_candidates: List[Dict[str, Any]]
    issue_types: List[str]

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "evidence": self.evidence,
            "alternative_candidates": self.alternative_candidates,
            "issue_types": self.issue_types,
            "regex_used": False,
            "database_used": False,
        }


class MultimodalCorrectionEngine:
    """Rank correction candidates with text, layout, topology, and history."""

    name = "multimodal_correction_engine_v1"

    def correct(
        self,
        original: str,
        *,
        expected_family: Optional[str] = None,
        geometry: Optional[dict] = None,
        graph: Optional[dict] = None,
        engineering_context: Optional[dict] = None,
        candidate_sections: Optional[Iterable[str]] = None,
        similarity_candidates: Optional[Iterable[Any]] = None,
        limit: int = 5,
    ) -> Optional[CorrectionResult]:
        original = str(original or "").strip()
        geometry = geometry or {}
        graph = graph or {}
        engineering_context = engineering_context or {}
        history = _review_history()
        examples_by_corrected = history.by_corrected

        model_candidates = list(similarity_candidates or ())
        if not model_candidates:
            model_candidates = predict_exact_sections(
                original,
                limit=max(12, limit * 3),
                geometry=geometry,
                graph=graph,
                engineering_rules=engineering_context,
            )
        pool: Dict[str, Dict[str, Any]] = {}
        for candidate in model_candidates:
            shape = str(
                getattr(candidate, "shape", None)
                or (candidate.get("shape") if isinstance(candidate, dict) else "")
            )
            if not shape:
                continue
            raw_evidence = (
                getattr(candidate, "evidence", None)
                or (candidate.get("evidence") if isinstance(candidate, dict) else {})
                or {}
            )
            retrieval = float(
                getattr(candidate, "confidence", 0.0)
                or (
                    candidate.get("confidence", 0.0)
                    if isinstance(candidate, dict)
                    else 0.0
                )
            )
            pool[shape] = {
                "shape": shape,
                "retrieval": retrieval,
                "model_evidence": dict(raw_evidence),
            }
        for section in candidate_sections or ():
            shape = str(section or "").strip().upper()
            if shape:
                pool.setdefault(
                    shape,
                    {"shape": shape, "retrieval": 0.5, "model_evidence": {}},
                )
        # Reviewed outputs are valid candidates, especially for missing labels.
        folded_family = _fold(expected_family) if expected_family else ""
        for shape, family in history.candidate_families:
            if folded_family and family != folded_family:
                continue
            pool.setdefault(
                shape,
                {"shape": shape, "retrieval": 0.45, "model_evidence": {}},
            )

        geometry_available = bool(geometry.get("available"))
        graph_available = float(graph.get("degree") or 0.0) > 0
        geometry_score = _clip(geometry.get("similarity"), 0.35)
        graph_score = _clip(graph.get("graph_consistency"), 0.35)
        rule_score = _clip(engineering_context.get("score"), 0.5)

        ranked: List[Dict[str, Any]] = []
        for item in pool.values():
            shape = item["shape"]
            history_score, history_match = _history_evidence(
                original, shape, examples_by_corrected
            )
            signals = {
                "text": _text_similarity(original, shape),
                "similarity_search": _clip(item["retrieval"]),
                "geometry": (
                    _clip(
                        item["model_evidence"].get("geometry"),
                        geometry_score,
                    )
                    if geometry_available
                    else 0.0
                ),
                "graph": (
                    _clip(item["model_evidence"].get("graph"), graph_score)
                    if graph_available
                    else 0.0
                ),
                "engineering_context": (
                    0.65 * _context_score(shape, expected_family)
                    + 0.35 * rule_score
                ),
                "review_history": history_score,
            }
            available = {
                "text": bool(original),
                "similarity_search": True,
                "geometry": geometry_available,
                "graph": graph_available,
                "engineering_context": True,
                "review_history": history_match is not None,
            }
            active = sum(
                weight
                for name, weight in CORRECTION_WEIGHTS.items()
                if available[name]
            ) or 1.0
            contributions = {
                name: (
                    CORRECTION_WEIGHTS[name] * signals[name] / active
                    if available[name]
                    else 0.0
                )
                for name in CORRECTION_WEIGHTS
            }
            score = sum(contributions.values())
            ranked.append(
                {
                    "corrected": shape,
                    "confidence": round(_clip(score), 4),
                    "evidence": {
                        "signals": {
                            key: round(value, 4)
                            for key, value in signals.items()
                        },
                        "contributions": {
                            key: round(value, 4)
                            for key, value in contributions.items()
                        },
                        "contribution_percentages": {
                            key: round(value * 100.0, 1)
                            for key, value in contributions.items()
                        },
                        "reviewed_example": history_match,
                        "expected_family": expected_family,
                        "regex_used": False,
                        "database_used": False,
                    },
                }
            )
        ranked.sort(key=lambda item: (-item["confidence"], item["corrected"]))
        if not ranked:
            return None

        best = ranked[0]
        issues = _issue_types(original, best["corrected"])
        evidence = best["evidence"]
        strongest = sorted(
            evidence["contributions"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        reason = (
            f"Multimodal correction selected {best['corrected']}; strongest "
            + ", ".join(
                f"{name.replace('_', ' ')} {value:.0%}"
                for name, value in strongest
                if value > 0
            )
        )
        # Alternatives keep their scores, not the full evidence record of the
        # winner they lost to: that record is repeated per prediction and was
        # the largest single contributor to the analysis payload.
        alternatives = [
            {
                "corrected": item["corrected"],
                "confidence": item["confidence"],
                "evidence": {
                    "contributions": (item["evidence"] or {}).get("contributions")
                    or {},
                },
            }
            for item in ranked[1:limit]
        ]
        return CorrectionResult(
            original=original,
            corrected=best["corrected"],
            confidence=float(best["confidence"]),
            reason=reason,
            evidence=evidence,
            alternative_candidates=alternatives,
            issue_types=issues,
        )


correction_engine = MultimodalCorrectionEngine()


def correct_token(
    token: str,
    *,
    expected_family: Optional[str] = None,
    geometry: Optional[dict] = None,
    graph: Optional[dict] = None,
    engineering_context: Optional[dict] = None,
    candidate_sections: Optional[Iterable[str]] = None,
    similarity_candidates: Optional[Iterable[Any]] = None,
    limit: int = 5,
) -> Optional[CorrectionResult]:
    return correction_engine.correct(
        token,
        expected_family=expected_family,
        geometry=geometry,
        graph=graph,
        engineering_context=engineering_context,
        candidate_sections=candidate_sections,
        similarity_candidates=similarity_candidates,
        limit=limit,
    )


def suggest_token_corrections(
    token: str,
    *,
    expected_family: Optional[str] = None,
    geometry: Optional[dict] = None,
    graph: Optional[dict] = None,
    engineering_context: Optional[dict] = None,
    candidate_sections: Optional[Iterable[str]] = None,
    similarity_candidates: Optional[Iterable[Any]] = None,
    limit: int = 5,
) -> List[CorrectionCandidate]:
    """Compatibility adapter returning ranked correction candidates."""

    result = correct_token(
        token,
        expected_family=expected_family,
        geometry=geometry,
        graph=graph,
        engineering_context=engineering_context,
        candidate_sections=candidate_sections,
        similarity_candidates=similarity_candidates,
        limit=limit,
    )
    if result is None:
        return []
    rows = [
        {
            "corrected": result.corrected,
            "confidence": result.confidence,
            "evidence": result.evidence,
            "reason": result.reason,
            "issues": result.issue_types,
        },
        *[
            {
                "corrected": item["corrected"],
                "confidence": item["confidence"],
                "evidence": item["evidence"],
                "reason": "Alternative multimodal correction candidate",
                "issues": _issue_types(token, item["corrected"]),
            }
            for item in result.alternative_candidates
        ],
    ]
    return [
        CorrectionCandidate(
            original=str(token or "").strip(),
            corrected=item["corrected"],
            confidence=float(item["confidence"]),
            issue_types=item["issues"],
            reason=item["reason"],
            evidence=item["evidence"],
            alternatives=result.alternative_candidates,
        )
        for item in rows[:limit]
    ]


def detect_extraction_issues(token_record: dict) -> List[str]:
    issues: List[str] = []
    original = str(token_record.get("text") or "")
    normalized = str(token_record.get("normalized_text") or "")
    if token_record.get("was_merged"):
        issues.append("split_token_repaired")
    if _fold(original) != _fold(normalized):
        issues.append("normalization_applied")
    if float(token_record.get("confidence") or 0) < 0.6:
        issues.append("low_extraction_confidence")
    if not any(char.isdigit() for char in _fold(normalized)):
        issues.append("invalid_engineering_notation")
    return issues
