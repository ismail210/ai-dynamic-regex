"""
Exact structural-section prediction.

This is the production shape model. It learns complete engineering labels
(W18X35, HSS8X8X1/2, L4X4X3/8), not broad families. Character TF-IDF handles
OCR noise and company notation; cosine retrieval returns calibrated alternatives.
"""

from __future__ import annotations

import json
import math
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from config import settings
from services.data_augmentation import generate_variants_for_token
from services.database_loader import df, lookup_shape
from services.family_codes import MODERN_FAMILY_ALTERNATION


_LOCK = threading.RLock()
_ARTIFACT: Optional[dict] = None
_EXACT_SHAPE_RE = re.compile(
    rf"^(?:{MODERN_FAMILY_ALTERNATION})"
    r"\d[\dX./A-Z-]*$",
    re.IGNORECASE,
)


def normalize_section_text(value: object) -> str:
    text = str(value or "").upper().strip()
    text = text.replace("×", "X").replace("✕", "X")
    text = re.sub(r"\bWIDE\s*FLANGE\b", "W", text)
    text = re.sub(r"\bWF(?=\s*\d)", "W", text)
    text = re.sub(r"\bSTRUCTURAL\s+TUBE\b", "HSS", text)
    text = re.sub(r"\bTS(?=\s*\d)", "HSS", text)
    text = re.sub(r"\s+", "", text)
    text = text.replace("_", "").replace("-", "")
    return text


def is_exact_section_label(value: object) -> bool:
    return bool(_EXACT_SHAPE_RE.fullmatch(normalize_section_text(value)))


def catalog_valid_exact_section(value: object) -> Optional[str]:
    """Single shared catalog-validity check.

    Conservatively normalizes ``value`` (case/whitespace/separator only — no
    fuzzy correction) and returns the AISC catalog's own canonical label
    string when that normalized text is an authoritative catalog entry,
    otherwise ``None``.

    ``is_exact_section_label`` only checks that text is *shaped* like a
    section designation (a regex format check); it says nothing about
    whether the shape actually exists. This function is the only place that
    should be used to decide "is this text a real, exact, catalog-valid
    section" — callers must not substitute the regex check for this one.
    """

    normalized = normalize_section_text(value)
    if not normalized:
        return None
    entry = lookup_shape(normalized)
    return str(entry["shape"]) if entry else None


def _ocr_variants(label: str) -> List[str]:
    variants = {
        label,
        label.lower(),
        label.replace("X", " X "),
        label.replace("X", "×"),
    }
    if label.startswith("W"):
        variants.update({"WF" + label[1:], "WF " + label[1:]})
    if label.startswith("HSS"):
        variants.update({"TS" + label[3:], "HSS " + label[3:]})
    # Deterministic OCR confusions, one character at a time.
    for source, replacement in (("5", "S"), ("0", "O"), ("1", "I"), ("8", "B")):
        for index, char in enumerate(label):
            if char == source:
                variants.add(label[:index] + replacement + label[index + 1 :])
    return sorted(variants)


def _canonical_labels() -> List[str]:
    values = (
        df["AISC_Manual_Label"]
        .astype(str)
        .map(normalize_section_text)
        .tolist()
    )
    return sorted({value for value in values if is_exact_section_label(value)})


def train_exact_section_model(
    *,
    persist: bool = True,
    exclude_tokens: Optional[set[str]] = None,
    exclude_split: Optional[str] = None,
) -> Dict[str, Any]:
    """Train complete-label character retrieval and optionally persist it.

    ``exclude_tokens`` / ``exclude_split`` keep holdout rows out of the matrix
    for honest evaluation runs.
    """

    labels = _canonical_labels()
    texts: List[str] = []
    targets: List[str] = []
    training_rows: List[dict] = []
    seen = set()
    excluded = {
        normalize_section_text(token) for token in (exclude_tokens or set())
    }
    excluded |= {str(token).strip().upper() for token in (exclude_tokens or set())}
    for label in labels:
        variants = set(generate_variants_for_token(label, None))
        variants.update(_ocr_variants(label))
        for variant in variants:
            normalized_variant = str(variant).strip()
            key = (normalized_variant.upper(), label)
            if not normalized_variant or key in seen:
                continue
            seen.add(key)
            texts.append(normalized_variant)
            targets.append(label)
            training_rows.append(
                {
                    "token": normalized_variant,
                    "normalized_token": normalize_section_text(normalized_variant),
                    "target_section": label,
                    "source": "aisc_augmented",
                    "reviewer_correction": False,
                    "validation_status": "reference",
                }
            )

    # Real PDF/Excel pairs provide extraction variants and quantity/layout
    # metadata. They directly train the exact target, not a section family.
    if settings.paired_dataset_path.exists():
        try:
            paired = pd.read_csv(
                settings.paired_dataset_path, dtype=str, keep_default_na=False
            )
            for _, row in paired.iterrows():
                token = str(row.get("pdf_token") or "").strip()
                target = normalize_section_text(row.get("canonical_label"))
                if not token or not is_exact_section_label(target):
                    continue
                key = (token.upper(), target)
                if key in seen:
                    continue
                seen.add(key)
                texts.append(token)
                targets.append(target)
                training_rows.append(
                    {
                        "token": token,
                        "normalized_token": normalize_section_text(token),
                        "target_section": target,
                        "source": "pdf_excel_pair",
                        "reviewer_correction": False,
                        "validation_status": row.get("validation_status") or "ground_truth",
                        "quantity": row.get("quantity"),
                        "page_number": row.get("page_number"),
                        "bbox": row.get("bbox"),
                        "ocr_confidence": row.get("ocr_confidence"),
                        "line_context": row.get("line_context"),
                    }
                )
        except (OSError, ValueError):
            pass

    if settings.approved_dataset_path.exists():
        try:
            approved = pd.read_csv(
                settings.approved_dataset_path, dtype=str, keep_default_na=False
            )
            for _, row in approved.iterrows():
                token = str(row.get("token") or "").strip()
                if exclude_split and str(row.get("eval_split") or "") == exclude_split:
                    continue
                if (
                    normalize_section_text(token) in excluded
                    or token.upper() in excluded
                ):
                    continue
                # Prefer the exact token as the section target when it is a
                # full designation; fall back to class only if it is exact.
                token_target = normalize_section_text(token)
                class_target = normalize_section_text(row.get("class"))
                if is_exact_section_label(token_target):
                    target = token_target
                elif is_exact_section_label(class_target):
                    target = class_target
                else:
                    continue
                if not token:
                    continue
                key = (token.upper(), target)
                if key in seen:
                    continue
                seen.add(key)
                texts.append(token)
                targets.append(target)
                training_rows.append(
                    {
                        "token": token,
                        "normalized_token": normalize_section_text(token),
                        "target_section": target,
                        "source": "reviewer_approved",
                        "reviewer_correction": True,
                        "validation_status": "approved",
                    }
                )
        except (OSError, ValueError):
            pass

    # Engineering corrections also become retrieval anchors.
    corrections_path = settings.engineering_corrections_path
    if corrections_path.exists():
        try:
            with corrections_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = str(
                        payload.get("token")
                        or payload.get("original_token")
                        or payload.get("raw_text")
                        or ""
                    ).strip()
                    target = normalize_section_text(
                        payload.get("correct_label")
                        or payload.get("corrected_label")
                        or payload.get("section")
                        or ""
                    )
                    if not token or not is_exact_section_label(target):
                        continue
                    if (
                        normalize_section_text(token) in excluded
                        or token.upper() in excluded
                    ):
                        continue
                    key = (token.upper(), target)
                    if key in seen:
                        continue
                    seen.add(key)
                    texts.append(token)
                    targets.append(target)
                    training_rows.append(
                        {
                            "token": token,
                            "normalized_token": normalize_section_text(token),
                            "target_section": target,
                            "source": "engineering_correction",
                            "reviewer_correction": True,
                            "validation_status": "corrected",
                        }
                    )
        except OSError:
            pass

    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 6),
        min_df=1,
        sublinear_tf=True,
        lowercase=False,
        dtype=np.float32,
    )
    matrix = normalize(vectorizer.fit_transform(texts), copy=False)
    artifact = {
        "schema_version": 1,
        "target": "exact_section",
        "vectorizer": vectorizer,
        "matrix": csr_matrix(matrix),
        "targets": np.asarray(targets, dtype=object),
        "labels": labels,
    }
    metadata = {
        "schema_version": 1,
        "target": "exact_section",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model": "character_tfidf_cosine_retrieval",
        "exact_label_count": len(labels),
        "training_variant_count": len(texts),
        "database_role": "training_reference_and_post_prediction_verification",
    }
    if persist:
        settings.training_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, settings.exact_section_model_path)
        settings.exact_section_metadata_path.write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        pd.DataFrame(training_rows).to_csv(
            settings.exact_section_dataset_path, index=False
        )
    global _ARTIFACT
    _ARTIFACT = artifact
    _cached_candidate_scores.cache_clear()
    return metadata


def reload_exact_section_artifact() -> None:
    """Drop the in-memory exact-section cache so the next call reloads from disk."""

    global _ARTIFACT
    with _LOCK:
        _ARTIFACT = None
        _cached_candidate_scores.cache_clear()


def refresh_exact_section_artifact() -> None:
    """Rebuild the exact-section retrieval artifact once after approvals."""

    train_exact_section_model(persist=True)
    reload_exact_section_artifact()
    _artifact()


def append_exact_section_anchor(
    token: object,
    target: object,
    *,
    rebuild: bool = True,
) -> bool:
    """
    Fold one human-approved (token → section) pair into the index.

    When ``rebuild`` is false the approved row is persisted separately and
    callers should invoke ``refresh_exact_section_artifact()`` once after a
    bulk approval batch instead of rebuilding on every token.
    """

    token_text = str(token or "").strip()
    target_text = normalize_section_text(target)
    if not token_text or not is_exact_section_label(target_text):
        return False
    if not rebuild:
        return True
    refresh_exact_section_artifact()
    return True


def _artifact() -> dict:
    global _ARTIFACT
    if _ARTIFACT is not None:
        return _ARTIFACT
    with _LOCK:
        if _ARTIFACT is not None:
            return _ARTIFACT
        if settings.exact_section_model_path.exists():
            try:
                _ARTIFACT = joblib.load(settings.exact_section_model_path)
                return _ARTIFACT
            except (OSError, ValueError, ImportError, AttributeError):
                pass
        train_exact_section_model(persist=True)
        assert _ARTIFACT is not None
        return _ARTIFACT


@dataclass
class ExactSectionCandidate:
    shape: str
    confidence: float
    text_similarity: float
    evidence: Dict[str, float]

    def to_dict(self) -> dict:
        return {
            "shape": self.shape,
            "confidence": round(self.confidence, 4),
            "text_similarity": round(self.text_similarity, 4),
            "evidence": {
                key: round(float(value), 4) for key, value in self.evidence.items()
            },
        }


@lru_cache(maxsize=20_000)
def _cached_candidate_scores(
    normalized_input: str, pool_size: int
) -> tuple[tuple[str, float], ...]:
    """
    Retrieval is a pure function of the cleaned token, and drawings repeat
    labels heavily (a typical sheet set has ~90 distinct sections across
    thousands of occurrences), so the cosine search runs once per label.
    """

    artifact = _artifact()
    query = normalize(
        artifact["vectorizer"].transform([normalized_input]), copy=False
    )
    similarities = (artifact["matrix"] @ query.T).toarray().reshape(-1)
    if not len(similarities):
        return ()
    pool_size = min(pool_size, len(similarities))
    indices = np.argpartition(similarities, -pool_size)[-pool_size:]
    best_by_shape: Dict[str, float] = {}
    targets = artifact["targets"]
    for index in indices:
        shape = str(targets[index])
        score = float(similarities[index])
        if score > best_by_shape.get(shape, -1.0):
            best_by_shape[shape] = score
    # Exact cleaned notation is authoritative model evidence, not a database
    # lookup. It avoids fuzzy alternatives outranking a perfectly read label.
    if normalized_input in set(artifact["labels"]):
        best_by_shape[normalized_input] = 1.0
    return tuple(
        sorted(best_by_shape.items(), key=lambda item: (-item[1], item[0]))
    )


def _candidate_scores(
    token: str, *, pool_size: int = 80
) -> tuple[tuple[str, float], ...]:
    return _cached_candidate_scores(normalize_section_text(token), pool_size)


def encode_exact_section_text(token: str, *, dimension: int = 128) -> List[float]:
    """Return a compact embedding from the fitted exact-section text encoder."""

    normalized_input = normalize_section_text(token)
    if not normalized_input:
        return [0.0] * dimension
    query = normalize(
        _artifact()["vectorizer"].transform([normalized_input]), copy=False
    ).tocsr()
    vector = np.zeros(dimension, dtype=np.float32)
    for index, value in zip(query.indices, query.data):
        bucket = int(index) % dimension
        sign = 1.0 if (int(index) // dimension) % 2 == 0 else -1.0
        vector[bucket] += sign * float(value)
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return vector.round(6).tolist()

def _score_candidates(
    candidates: List[tuple],
    *,
    geometry: Optional[dict] = None,
    graph: Optional[dict] = None,
    engineering_rules: Optional[dict] = None,
) -> List[ExactSectionCandidate]:
    """
    Rerank a pool of ``(shape, text_score)`` pairs with live multimodal
    evidence. Geometry/graph do not merely affect confidence: they can
    reorder candidates when text scores are close or absent (a
    ``text_score`` of ``0.0`` is valid input — e.g. a deterministic
    wildcard-mask candidate with no text-similarity signal of its own).
    """

    if not candidates:
        return []

    geometry = geometry or {}
    graph = graph or {}
    rules = engineering_rules or {}
    orientation = float(
        (geometry.get("object") or geometry).get("orientation") or 0.0
    )
    graph_links = float(graph.get("structural_links") or 0.0)
    graph_degree = float(graph.get("degree") or 0.0)
    learned_role = str(
        geometry.get("geometry_role")
        or (geometry.get("object") or {}).get("geometry_role")
        or ""
    ).lower()
    role = learned_role or str(rules.get("member_role") or "").lower()

    scored: List[ExactSectionCandidate] = []
    for shape, text_score in candidates:
        family = re.match(r"^[A-Z]+", shape)
        family_name = family.group(0) if family else ""
        geometry_score = float(geometry.get("similarity") or 0.35)
        graph_score = float(graph.get("graph_consistency") or 0.35)

        # Learned geometry role / orientation influence family choice.
        if role == "beam" or (abs(orientation) <= 35 and graph_links >= 1):
            if family_name in {"W", "S", "M", "C", "MC"}:
                geometry_score = min(1.0, geometry_score + 0.15)
                graph_score = min(1.0, graph_score + 0.10)
            elif family_name in {"HSS", "PIPE"}:
                graph_score = max(0.0, graph_score - 0.08)
        elif role == "column" or abs(orientation) >= 55:
            if family_name in {"W", "HSS", "PIPE"}:
                geometry_score = min(1.0, geometry_score + 0.10)
        if role == "brace" and family_name in {"HSS", "L", "2L", "WT"}:
            geometry_score = min(1.0, geometry_score + 0.12)
        if learned_role and role != learned_role:
            geometry_score *= 0.9
        if graph_degree == 0 and role in {"beam", "brace"}:
            graph_score *= 0.7

        rule_score = float(rules.get("score") or 0.5)
        weighted = 0.68 * text_score + 0.05 * rule_score
        active_weight = 0.73
        if geometry.get("available"):
            weighted += 0.18 * geometry_score
            active_weight += 0.18
        if graph_degree > 0:
            weighted += 0.09 * graph_score
            active_weight += 0.09
        final = weighted / active_weight
        scored.append(
            ExactSectionCandidate(
                shape=shape,
                confidence=max(0.0, min(1.0, final)),
                text_similarity=text_score,
                evidence={
                    "text": text_score,
                    "geometry": geometry_score,
                    "graph": graph_score,
                    "engineering_rules": rule_score,
                },
            )
        )
    scored.sort(key=lambda item: (-item.confidence, item.shape))
    return scored


def predict_exact_sections(
    token: str,
    *,
    limit: int = 5,
    geometry: Optional[dict] = None,
    graph: Optional[dict] = None,
    engineering_rules: Optional[dict] = None,
) -> List[ExactSectionCandidate]:
    """Predict exact labels via fuzzy character-retrieval, reranked with live
    multimodal evidence. Callers that already have a deterministic candidate
    set (e.g. wildcard-mask matches) should use
    ``predict_exact_sections_for_labels`` instead so fuzzy retrieval never
    runs ahead of a deterministic match."""

    candidates = _candidate_scores(token)
    scored = _score_candidates(
        candidates,
        geometry=geometry,
        graph=graph,
        engineering_rules=engineering_rules,
    )
    return scored[: max(1, limit)]


def predict_exact_sections_for_labels(
    labels: List[str],
    *,
    geometry: Optional[dict] = None,
    graph: Optional[dict] = None,
    engineering_rules: Optional[dict] = None,
    limit: int = 8,
) -> List[ExactSectionCandidate]:
    """
    Rerank an already-determined, catalog-valid label set (e.g. deterministic
    wildcard-mask candidates) using the same live multimodal evidence as
    fuzzy retrieval — without running any fuzzy text-similarity search.
    ``text_similarity`` is ``0.0`` for these candidates: the match came from
    exact positional agreement, not a text-similarity model.
    """

    candidates = [(str(label), 0.0) for label in labels if label]
    scored = _score_candidates(
        candidates,
        geometry=geometry,
        graph=graph,
        engineering_rules=engineering_rules,
    )
    return scored[: max(1, limit)]
