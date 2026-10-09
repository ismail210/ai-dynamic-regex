"""Versioned shipped assets on the data volume (services/asset_sync.py)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import asset_sync as a


def _image(root: Path, files: dict[str, str], revision: str) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    (root / a.MANIFEST).write_text(json.dumps(a.build_manifest(root, revision)), encoding="utf-8")
    return root


class AssetSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.data = base / "data"
        self.v1 = _image(base / "img1", {"model.pkl": "m1", "catalog.json": '{"v": 1}', "history.csv": "h"}, "rev1")
        self.v2 = _image(base / "img2", {"model.pkl": "m2", "catalog.json": '{"v": 2}', "history.csv": "h",
                                         "new.json": "{}"}, "rev2")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def live(self, rel: str) -> str:
        return (self.data / "training" / rel).read_text(encoding="utf-8")

    def test_first_start_seeds_and_a_later_image_never_overwrites_on_startup(self):
        a.Assets(self.v1, self.data).startup()
        self.assertEqual(self.live("model.pkl"), "m1")
        (self.data / "training" / "history.csv").write_text("h + user rows", encoding="utf-8")
        plan = a.Assets(self.v2, self.data).startup()
        self.assertEqual(sorted(plan["update"]), ["catalog.json", "model.pkl"])
        self.assertEqual(plan["modified"], ["history.csv"])
        self.assertEqual(plan["missing"], ["new.json"])
        self.assertEqual((self.live("model.pkl"), self.live("new.json")), ("m1", "{}"))   # only new files added
        self.assertEqual(a.Assets(self.v2, self.data).applied()["revision"], "rev1")  # rev2 not applied yet

    def test_apply_backs_up_replaces_updates_keeps_user_changes_and_rolls_back(self):
        a.Assets(self.v1, self.data).startup()
        (self.data / "training" / "history.csv").write_text("h + user rows", encoding="utf-8")
        (self.data / "training" / "catalog.json").write_text('{"v": "edited"}', encoding="utf-8")
        result = a.Assets(self.v2, self.data).apply()
        self.assertEqual(result["replaced"], ["model.pkl"])
        self.assertEqual(sorted(result["kept_modified"]), ["catalog.json", "history.csv"])
        self.assertEqual((self.live("model.pkl"), self.live("catalog.json")), ("m2", '{"v": "edited"}'))
        status = a.Assets(self.v2, self.data).plan()
        self.assertEqual(status["update"], [])
        backup = Path(result["backup"]).name
        a.Assets(self.v1, self.data).rollback(backup)
        self.assertEqual(self.live("model.pkl"), "m1")
        self.assertEqual(a.Assets(self.v1, self.data).applied()["revision"], "rev1")
        self.assertEqual(self.live("history.csv"), "h + user rows")          # user data untouched throughout

    def test_an_interrupted_apply_is_completed_by_running_it_again(self):
        a.Assets(self.v1, self.data).startup()
        assets = a.Assets(self.v2, self.data)
        real = a.Assets._copy_verified
        calls = []

        def fail_second(self, rel):
            calls.append(rel)
            if len(calls) == 2:
                raise KeyboardInterrupt
            real(self, rel)

        with mock.patch.object(a.Assets, "_copy_verified", fail_second), self.assertRaises(KeyboardInterrupt):
            assets.apply()
        self.assertEqual(a.Assets(self.v1, self.data).applied()["revision"], "rev1")   # record not yet moved
        a.Assets(self.v2, self.data).apply()
        self.assertEqual((self.live("model.pkl"), self.live("catalog.json")), ("m2", '{"v": 2}'))
        self.assertFalse(list((self.data / "training").rglob("*.asset-new")))

    def test_a_corrupt_image_file_or_a_newer_volume_format_is_refused_with_guidance(self):
        a.Assets(self.v1, self.data).startup()
        (self.v2 / "model.pkl").write_text("tampered", encoding="utf-8")
        with self.assertRaises(SystemExit) as bad:
            a.Assets(self.v2, self.data).apply()
        self.assertIn("does not match the image manifest", str(bad.exception))
        self.assertEqual(self.live("model.pkl"), "m1")
        record = json.loads((self.data / ".assets" / "applied.json").read_text(encoding="utf-8"))
        record["format"] = a.ASSET_FORMAT + 1
        (self.data / ".assets" / "applied.json").write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(SystemExit) as newer:
            a.Assets(self.v1, self.data).startup()
        self.assertIn("Run an image of revision", str(newer.exception))


if __name__ == "__main__":
    unittest.main()
