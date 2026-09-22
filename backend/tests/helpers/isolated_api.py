"""
Shared HTTP-test isolation infrastructure, used by every FastAPI
``TestClient``-based test suite in ``backend/tests``.

Every path that would otherwise read/write real operational or training
data (uploads, artifacts, the regex knowledge base, the unknown-token queue,
approved corrections, ...) is redirected to a temporary directory for the
duration of each test. ``config.settings`` is a frozen dataclass singleton
shared by reference across every module that does ``from config import
settings``, so patching its attributes here (via ``object.__setattr__``,
restored in ``tearDown``) takes effect everywhere without ever touching real
repository data -- consumers of this module must not add noise to files like
``backend/training/dynamic_regex.json`` or ``unknown_tokens.csv``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import config
from app import app
from services.regex_knowledge_base import knowledge_base


# Every settings attribute touched by the routes under test that points at a
# real file/directory under the repository. Redirected to a temp dir per test.
_REDIRECTED_SETTINGS = [
    "uploads_dir",
    "engineering_uploads_dir",
    "engineering_artifacts_dir",
    "document_registry_dir",
    "takeoff_exports_dir",
    "knowledge_base_path",
    "unknown_tokens_path",
    "history_path",
    "upload_log_path",
    "approved_dataset_path",
    "engineering_corrections_path",
    "annotation_edge_cases_path",
    "compound_dimension_seed_path",
    "human_selections_path",
    "continuous_learning_state_path",
]


class IsolatedApiTestCase(unittest.TestCase):
    """Base class redirecting all operational/training data paths to a temp
    directory so HTTP-level tests never mutate real repository data."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self._originals = {
            name: getattr(config.settings, name) for name in _REDIRECTED_SETTINGS
        }
        for name in _REDIRECTED_SETTINGS:
            original = self._originals[name]
            replacement = base / name
            if original.suffix:  # file path — keep the same extension
                replacement = replacement.with_suffix(original.suffix)
            else:
                replacement.mkdir(parents=True, exist_ok=True)
            object.__setattr__(config.settings, name, replacement)

        # These two read their path once at import/construction time, not
        # per-call from `settings`, so redirecting settings above does not
        # reach them — patch the already-constructed singleton/module
        # constant directly instead.
        self._original_kb_path = knowledge_base.path
        knowledge_base.path = base / "dynamic_regex.json"

        review_index_patcher = patch(
            "services.multimodal.review_enrichment._INDEX_PATH",
            base / "multimodal_review_index.json",
        )
        review_index_patcher.start()
        self.addCleanup(review_index_patcher.stop)

    def tearDown(self) -> None:
        for name, value in self._originals.items():
            object.__setattr__(config.settings, name, value)
        knowledge_base.path = self._original_kb_path
        self.temp.cleanup()
