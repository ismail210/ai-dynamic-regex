"""Runtime registry for swapping multimodal encoder implementations."""

from __future__ import annotations

from typing import Dict, Iterable

from services.multimodal.encoder_contracts import ModalityEncoder, ModalityEncoding
from services.multimodal.encoders import (
    ClassicalGeometryEncoder,
    ClassicalGraphEncoder,
    ClassicalLayoutEncoder,
    ClassicalOCREncoder,
    ClassicalTextEncoder,
    EngineeringContextEncoder,
)


class EncoderRegistry:
    def __init__(self, encoders: Iterable[ModalityEncoder] | None = None) -> None:
        defaults = encoders or (
            ClassicalTextEncoder(),
            ClassicalOCREncoder(),
            ClassicalLayoutEncoder(),
            ClassicalGeometryEncoder(),
            ClassicalGraphEncoder(),
            EngineeringContextEncoder(),
        )
        self._encoders: Dict[str, ModalityEncoder] = {
            encoder.modality: encoder for encoder in defaults
        }

    def register(self, encoder: ModalityEncoder) -> None:
        """Replace one modality encoder (LayoutLM, PointNet, GCN, etc.)."""

        self._encoders[encoder.modality] = encoder

    def get(self, modality: str) -> ModalityEncoder:
        if modality not in self._encoders:
            raise KeyError(f"No encoder registered for modality {modality!r}")
        return self._encoders[modality]

    def encode_all(self, contexts: Dict[str, dict]) -> Dict[str, ModalityEncoding]:
        return {
            modality: encoder.encode(contexts.get(modality) or {})
            for modality, encoder in self._encoders.items()
        }

    def capabilities(self) -> Dict[str, dict]:
        return {
            modality: {
                "encoder": encoder.name,
                "output_dimension": encoder.output_dimension,
                "replaceable": True,
            }
            for modality, encoder in self._encoders.items()
        }


encoder_registry = EncoderRegistry()
