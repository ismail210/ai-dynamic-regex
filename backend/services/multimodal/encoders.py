"""Classical encoders implementing the replaceable multimodal contracts."""

from __future__ import annotations

from typing import Any, Dict

from services.feature_extractor import extract_structural_features
from services.multimodal.encoder_contracts import ModalityEncoder, ModalityEncoding


def _clip(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


class ClassicalTextEncoder(ModalityEncoder):
    """Text encoder backed by exact-section and family model outputs.

    LayoutLM can replace this class without changing fusion or orchestration.
    """

    modality = "text"
    name = "classical_text_encoder_v1"

    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        token = str(context.get("token") or "")
        model_probability = _clip(context.get("model_probability"), 0.0)
        extraction_confidence = _clip(
            context.get("extraction_confidence"), 0.5
        )
        regex_confidence = _clip(context.get("regex_confidence"), 0.0)
        candidates = context.get("candidates") or []
        top_text = _clip(
            getattr(candidates[0], "text_similarity", None)
            if candidates
            else model_probability,
            model_probability,
        )
        engineered = extract_structural_features(token)
        length_score = min(1.0, len(token) / 16.0)
        digit_ratio = min(
            1.0,
            float(engineered.get("digit_count") or 0) / max(len(token), 1),
        )
        alpha_ratio = min(
            1.0,
            float(engineered.get("alpha_count") or 0) / max(len(token), 1),
        )
        candidate_margin = 0.0
        if len(candidates) > 1:
            candidate_margin = max(
                0.0,
                float(candidates[0].confidence)
                - float(candidates[1].confidence),
            )
        elif candidates:
            candidate_margin = float(candidates[0].confidence)

        confidence = _clip(
            0.55 * model_probability
            + 0.25 * extraction_confidence
            + 0.15 * top_text
            + 0.05 * regex_confidence
        )
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[
                model_probability,
                extraction_confidence,
                top_text,
                regex_confidence,
                length_score,
                digit_ratio,
                alpha_ratio,
                _clip(candidate_margin),
            ],
            confidence=confidence,
            available=bool(token),
            features={
                "token": token,
                "candidate_count": len(candidates),
                "top_text_similarity": top_text,
                "candidate_margin": round(candidate_margin, 4),
                "shape_family": engineered.get("shape_family"),
            },
            reasons=[
                f"Text model confidence {model_probability:.0%}",
                f"Extraction confidence {extraction_confidence:.0%}",
                f"Top candidate text similarity {top_text:.0%}",
            ],
        )


class ClassicalOCREncoder(ModalityEncoder):
    """OCR quality and correction encoder, replaceable by Donut/LayoutLM."""

    modality = "ocr"
    name = "classical_ocr_encoder_v1"

    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        original = str(context.get("original") or "")
        corrected = str(context.get("corrected") or original)
        confidence = _clip(context.get("confidence"), 0.5)
        repairs = context.get("repairs") or []
        max_length = max(len(original), len(corrected), 1)
        edit_similarity = 1.0 - (
            sum(a != b for a, b in zip(original, corrected))
            + abs(len(original) - len(corrected))
        ) / max_length
        edit_similarity = _clip(edit_similarity)
        correction_applied = 1.0 if original != corrected else 0.0
        quality = _clip(
            0.70 * confidence
            + 0.20 * edit_similarity
            + 0.10 * (1.0 if original else 0.0)
        )
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[
                confidence,
                edit_similarity,
                correction_applied,
                min(1.0, len(repairs) / 4.0),
                min(1.0, len(original) / 16.0),
                min(1.0, len(corrected) / 16.0),
            ],
            confidence=quality,
            available=bool(original),
            features={
                "original": original,
                "corrected": corrected,
                "correction_applied": bool(correction_applied),
                "repairs": repairs,
            },
            reasons=[
                f"OCR extraction confidence {confidence:.0%}",
                (
                    f"OCR correction changed {original} to {corrected}"
                    if correction_applied
                    else "OCR token required no character correction"
                ),
            ],
        )


class ClassicalLayoutEncoder(ModalityEncoder):
    """Drawing-layout encoder, replaceable by LayoutLM/Donut."""

    modality = "layout"
    name = "classical_layout_encoder_v1"

    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        bbox = context.get("bbox") or []
        page = float(context.get("page") or 0.0)
        reading_order = float(context.get("reading_order") or 0.0)
        font_size = float(context.get("font_size") or 0.0)
        rotation = abs(float(context.get("rotation") or 0.0)) % 360.0
        role = str(context.get("member_role") or "").lower()
        neighbors = context.get("neighbors") or []
        available = len(bbox) == 4
        confidence = _clip(
            0.35 * (1.0 if available else 0.0)
            + 0.25 * min(1.0, len(neighbors) / 4.0)
            + 0.20 * (1.0 if font_size > 0 else 0.0)
            + 0.20 * (1.0 if role else 0.0)
        )
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[
                min(1.0, page / 100.0),
                min(1.0, reading_order / 1000.0),
                min(1.0, font_size / 72.0),
                min(1.0, rotation / 360.0),
                min(1.0, len(neighbors) / 8.0),
                1.0 if available else 0.0,
            ],
            confidence=confidence,
            available=available,
            features={
                "bbox": bbox,
                "page": page,
                "reading_order": reading_order,
                "font_size": font_size,
                "rotation": rotation,
                "member_role": role,
                "neighbors": neighbors,
            },
            reasons=[
                f"Layout context includes {len(neighbors)} neighboring labels",
                f"Drawing role is {role or 'unknown'}",
            ],
        )


class ClassicalGeometryEncoder(ModalityEncoder):
    """Vector-geometry encoder. PointNet/ViT can replace this adapter."""

    modality = "geometry"
    name = "classical_geometry_encoder_v1"

    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        geometry = context.get("geometry") or {}
        available = bool(geometry.get("available"))
        obj = geometry.get("object") or {}
        similarity = _clip(geometry.get("similarity"), 0.35)
        distance = float(geometry.get("nearest_distance") or 999.0)
        proximity = max(0.0, min(1.0, 1.0 - distance / 180.0))
        orientation = abs(float(obj.get("orientation") or 0.0)) % 180
        horizontal = max(0.0, 1.0 - min(orientation, 180 - orientation) / 90.0)
        vertical = max(0.0, 1.0 - abs(90.0 - orientation) / 90.0)
        length = min(1.0, float(obj.get("length") or 0.0) / 300.0)
        kind = str(obj.get("kind") or "")
        structural_kind = 1.0 if kind in {
            "line", "polyline", "dimension", "leader", "rectangle"
        } else 0.0
        confidence = _clip(
            0.50 * similarity + 0.30 * proximity + 0.20 * structural_kind
        ) if available else 0.0
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[
                similarity,
                proximity,
                horizontal,
                vertical,
                length,
                structural_kind,
                1.0 if obj.get("bbox") else 0.0,
                1.0 if available else 0.0,
            ],
            confidence=confidence,
            available=available,
            features={
                "kind": kind,
                "orientation": orientation,
                "nearest_distance": distance,
                "object_id": obj.get("object_id"),
            },
            reasons=(
                [
                    f"Nearest geometry similarity {similarity:.0%}",
                    f"Geometry proximity {proximity:.0%}",
                    f"Orientation {orientation:.1f}°",
                ]
                if available
                else ["No linked geometry object"]
            ),
        )


class ClassicalGraphEncoder(ModalityEncoder):
    """Structural graph encoder. GraphSAGE/GCN can replace this adapter."""

    modality = "graph"
    name = "classical_graph_encoder_v1"

    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        graph = context.get("graph") or {}
        degree = float(graph.get("degree") or 0.0)
        links = float(graph.get("structural_links") or 0.0)
        consistency = _clip(graph.get("graph_consistency"), 0.35)
        distance = float(graph.get("min_distance") or 999.0)
        proximity = max(0.0, min(1.0, 1.0 - distance / 180.0))
        available = degree > 0
        confidence = _clip(
            0.50 * consistency
            + 0.25 * min(1.0, degree / 6.0)
            + 0.25 * min(1.0, links / 4.0)
        ) if available else 0.0
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[
                consistency,
                min(1.0, degree / 8.0),
                min(1.0, links / 6.0),
                proximity,
                1.0 if degree >= 2 else 0.0,
                1.0 if links >= 1 else 0.0,
                1.0 if graph.get("source_node") else 0.0,
                1.0 if available else 0.0,
            ],
            confidence=confidence,
            available=available,
            features={
                "degree": degree,
                "structural_links": links,
                "min_distance": distance,
            },
            reasons=(
                [
                    f"Graph consistency {consistency:.0%}",
                    f"{int(degree)} graph edges and {int(links)} structural links",
                ]
                if available
                else ["No graph neighborhood available"]
            ),
        )


class EngineeringContextEncoder(ModalityEncoder):
    """Engineering-rule/context encoder, replaceable independently."""

    modality = "engineering_rules"
    name = "engineering_context_encoder_v1"

    def encode(self, context: Dict[str, Any]) -> ModalityEncoding:
        rules = context.get("rules") or {}
        score = _clip(rules.get("score"), 0.5)
        findings = rules.get("findings") or []
        role = str(rules.get("member_role") or "").lower()
        material = str(rules.get("material_grade") or "")
        severity_penalty = min(1.0, len(findings) / 5.0)
        role_vector = {
            "beam": (1.0, 0.0, 0.0),
            "column": (0.0, 1.0, 0.0),
            "brace": (0.0, 0.0, 1.0),
        }.get(role, (0.0, 0.0, 0.0))
        confidence = _clip(0.8 * score + 0.2 * (1.0 - severity_penalty))
        return ModalityEncoding(
            modality=self.modality,
            encoder=self.name,
            vector=[
                score,
                1.0 - severity_penalty,
                *role_vector,
                1.0 if material else 0.0,
                min(1.0, len(findings) / 5.0),
                1.0,
            ],
            confidence=confidence,
            available=True,
            features={
                "member_role": role or None,
                "material_grade": material or None,
                "finding_count": len(findings),
            },
            reasons=[
                f"Engineering-rule consistency {score:.0%}",
                f"Member role {role or 'unknown'}",
            ],
        )
