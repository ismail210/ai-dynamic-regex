"""Category 24 + feature-flag safety: ml_association must stay disconnected
from the live prediction pipeline, and disabled by default.

This is the structural guard the Phase 2 spec explicitly asks for:
"Add a structural test proving that the production prediction pipeline
does not import or invoke the new ml_association package." If a future
change wires ml_association into a production path, this test fails the
build immediately rather than relying on code review alone.
"""

from __future__ import annotations

import importlib
import inspect
import unittest

_PRODUCTION_MODULES = [
    "services.multimodal.pipeline",
    "services.prediction.orchestrator",
    "services.multimodal.fusion_engine",
    "services.multimodal.modular_fusion",
    "services.prediction.ranking",
    "services.prediction.canonical_contract",
    "services.staged_pipeline",
    "app",
    "routers.documents",
    "routers.analysis",
    "routers.engineering",
]


class ProductionPipelineDoesNotImportMlAssociationTests(unittest.TestCase):
    def test_no_production_module_references_ml_association_in_source(self) -> None:
        offending = []
        for module_name in _PRODUCTION_MODULES:
            module = importlib.import_module(module_name)
            source = inspect.getsource(module)
            if "ml_association" in source:
                offending.append(module_name)
        self.assertEqual(
            offending,
            [],
            f"ml_association must not be referenced by production modules: {offending}",
        )

    def test_no_production_module_directly_references_ml_association_attribute(self) -> None:
        # Belt-and-suspenders on top of the source-text scan: walk each
        # production module's own top-level namespace (not the whole
        # process's sys.modules, which other test files legitimately
        # populate with services.ml_association.* and would make an
        # import-order-dependent, flaky check) and confirm none of its
        # directly-bound names came from services.ml_association.
        for module_name in _PRODUCTION_MODULES:
            module = importlib.import_module(module_name)
            for attribute_name, value in vars(module).items():
                module_of_value = getattr(value, "__module__", "") or ""
                self.assertFalse(
                    module_of_value.startswith("services.ml_association"),
                    f"{module_name}.{attribute_name} is bound to {module_of_value}",
                )


class FeatureFlagDisabledByDefaultTests(unittest.TestCase):
    def test_settings_default_is_disabled(self) -> None:
        from config import settings

        self.assertFalse(settings.ml_association_dataset_enabled)

    def test_every_service_entry_point_is_gated_when_disabled(self) -> None:
        from services.ml_association import service

        self.assertFalse(service.is_enabled())

        with self.assertRaises(service.FeatureDisabledError):
            service.build_dataset({}, {}, project_id="p", document_id="d", created_at="2026-01-01T00:00:00Z")
        with self.assertRaises(service.FeatureDisabledError):
            service.export_groups([], pdf_path="unused.pdf")
        with self.assertRaises(service.FeatureDisabledError):
            service.submit_review({}, group=None)  # type: ignore[arg-type]
        with self.assertRaises(service.FeatureDisabledError):
            service.latest_outcomes()
        with self.assertRaises(service.FeatureDisabledError):
            service.outcome_history("group_1")

    def test_enabling_via_settings_unlocks_the_facade(self) -> None:
        from config import settings
        from services.ml_association import service

        original = settings.ml_association_dataset_enabled
        try:
            object.__setattr__(settings, "ml_association_dataset_enabled", True)
            self.assertTrue(service.is_enabled())
            service.require_enabled()  # must not raise
        finally:
            object.__setattr__(settings, "ml_association_dataset_enabled", original)
        self.assertFalse(service.is_enabled())


if __name__ == "__main__":
    unittest.main()
