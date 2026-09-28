"""Schedule reading measured against the hand-listed answer key.

Runs only when the answer-key PDFs are present locally (they are not in git).
Prints found / correct per class for the word-cluster baseline and the ruled
path, and fails if the ruled path regresses below the measured floor.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND / "scripts" / "schedule_eval" / "run_schedule_eval.py"


def _load_eval():
    spec = importlib.util.spec_from_file_location("run_schedule_eval", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScheduleAnswerKeyTests(unittest.TestCase):
    def test_answer_key_is_well_formed(self) -> None:
        key = _load_eval().load_answer_key()
        rows = 0
        for doc in key["documents"]:
            for table in doc.get("tables", []):
                self.assertIn(table["class"], {"steel", "non_steel"})
                rows += len(table["rows"])
            for table in doc.get("transposed", []):
                rows += len(table["rows"])
        self.assertGreaterEqual(rows, 100)

    def test_ruled_tables_beat_word_clusters_on_answer_key(self) -> None:
        run_eval = _load_eval()
        key = run_eval.load_answer_key()
        present = [d for d in key["documents"] if (_BACKEND / d["pdf"]).is_file()]
        if len(present) < len(key["documents"]):
            self.skipTest("answer-key PDFs are not available locally")
        report = run_eval.evaluate(key=key)
        print("\n" + run_eval._format(report))
        ruled = report["totals"]["ruled"]
        baseline = report["totals"]["baseline"]
        for klass in run_eval.CLASSES:
            with self.subTest(klass=klass):
                self.assertGreaterEqual(ruled[klass]["correct"], baseline[klass]["correct"])
        self.assertEqual(ruled["steel"]["correct"], ruled["steel"]["expected"])
        self.assertEqual(ruled["non_steel"]["correct"], ruled["non_steel"]["expected"])
        # SFSLS E-2..E-4 are overprinted by markup clouds.
        self.assertGreaterEqual(ruled["transposed"]["correct"], ruled["transposed"]["expected"] - 3)
        self.assertEqual(report["extra_steel"]["ruled"], 0)


if __name__ == "__main__":
    unittest.main()
