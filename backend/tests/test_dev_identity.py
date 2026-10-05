"""The development identity names the worktree whose source is running."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from services.engineering.drawing_intelligence import DRAWING_INTELLIGENCE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]


class DevIdentityTests(unittest.TestCase):
    def test_identity_reports_source_worktree_revision_and_summary_api(self):
        body = TestClient(app).get("/api/dev/identity").json()

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(Path(body["worktree"]), REPO_ROOT)
        self.assertEqual(body["revision"], head)
        self.assertEqual(body["summary_api"], DRAWING_INTELLIGENCE_VERSION)


if __name__ == "__main__":
    unittest.main()
