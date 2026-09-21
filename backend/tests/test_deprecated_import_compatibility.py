"""Locks the compatibility guarantee of the remaining deprecated-import
shims: every symbol they still re-export must be the exact same object as
its canonical counterpart (never a copy), so callers using either import
path always get identical behavior. See
docs/architecture/unified_semantic_contract.md for why these shims exist.
"""

from __future__ import annotations

import unittest


class SemanticContractShimIdentityTests(unittest.TestCase):
    """services.prediction.semantic_contract re-exports a subset of
    services.semantic.models -- identity (not equality) is the guarantee:
    the shim must never define a second, divergent class."""

    def test_semantic_annotation_is_the_canonical_class(self):
        from services.prediction.semantic_contract import SemanticAnnotation as shim_cls
        from services.semantic.models import SemanticAnnotation as canonical_cls

        self.assertIs(shim_cls, canonical_cls)

    def test_evidence_type_is_the_canonical_enum(self):
        from services.prediction.semantic_contract import EvidenceType as shim_enum
        from services.semantic.models import EvidenceType as canonical_enum

        self.assertIs(shim_enum, canonical_enum)

    def test_evidence_strength_is_the_canonical_enum(self):
        from services.prediction.semantic_contract import EvidenceStrength as shim_enum
        from services.semantic.models import EvidenceStrength as canonical_enum

        self.assertIs(shim_enum, canonical_enum)

    def test_review_status_is_the_canonical_enum(self):
        from services.prediction.semantic_contract import ReviewStatus as shim_enum
        from services.semantic.models import ReviewStatus as canonical_enum

        self.assertIs(shim_enum, canonical_enum)

    def test_geometry_provider_is_the_canonical_enum(self):
        from services.prediction.semantic_contract import GeometryProvider as shim_enum
        from services.semantic.models import GeometryProvider as canonical_enum

        self.assertIs(shim_enum, canonical_enum)


class TextPrimitiveIsNotAShimTests(unittest.TestCase):
    """services.semantic_preprocessor.models.TextPrimitive is a genuine,
    original definition (extraction-stage working type) with no canonical
    replacement -- it must NOT be confused with the deprecated re-export
    block that used to live alongside it in the same file."""

    def test_text_primitive_has_no_canonical_counterpart(self):
        from services.semantic_preprocessor.models import TextPrimitive

        self.assertFalse(hasattr(TextPrimitive, "__wrapped__"))
        self.assertEqual(TextPrimitive.__module__, "services.semantic_preprocessor.models")


if __name__ == "__main__":
    unittest.main()
