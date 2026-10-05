"""Column schedules on the real reference drawings (Oct 2 meeting set).

Runs the production extraction path (PDF -> schedule grid -> drawing
intelligence) on each PDF and checks the column entries against values read
from the rendered sheets (``fixtures/column_schedule/reference_set.json``).
Skips a document whose PDF is not present; the PDFs are not in git.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "column_schedule" / "reference_set.json"
_ROOT = Path(os.environ.get(
    "ESTIMA3D_TESTING_PROJECTS",
    r"C:\Users\Bassam\Downloads\Testing Projects-20260912T094727Z-1-001\Testing Projects",
))
_REFERENCE = json.loads(_FIXTURE.read_text(encoding="utf-8"))
_CACHE: dict = {}


def _run(spec):
    if spec["key"] not in _CACHE:
        from services.engineering import drawing_intelligence as di
        from services.engineering.schedule_grid import attach_schedule_grid
        from services.pdf_parser import extract_document_structure

        pdf = _ROOT / spec["pdf"]
        document = extract_document_structure(str(pdf))
        attach_schedule_grid(document, pdf_path=str(pdf))
        _CACHE[spec["key"]] = (document, di.build_drawing_intelligence(document))
    return _CACHE[spec["key"]]


def _find(view, expected):
    for entry in view["entries"]:
        if "mark" in expected and entry["mark"] == expected["mark"]:
            return entry
        if "location" in expected and entry["locations"] and entry["locations"][0]["raw"] == expected["location"]:
            return entry
    raise AssertionError(f"no entry for {expected}")


class ReferenceSetTests(unittest.TestCase):
    def _check_document(self, spec):
        if not (_ROOT / spec["pdf"]).is_file():
            self.skipTest(f"{spec['pdf']} is not available locally")
        document, profile = _run(spec)
        view = profile["column_schedule"]

        if spec.get("column_schedule_reported_missing") is False:
            # A schedule that was read is never reported as "referenced but not found".
            self.assertNotIn("missing_schedule", [u["kind"] for u in profile["unresolved"]])

        # Production inputs are untouched: same mark map as before the change.
        self.assertEqual(document["schedule_mark_map"], spec["mark_map_before"])

        for expected in spec.get("schedules", []):
            match = [
                s for s in view["schedules"]
                if (expected.get("name") in (None, s["name"]))
                and (expected.get("page") is None or s["page"] == expected["page"])
                and (expected.get("pages") is None or s["pages"] == expected["pages"])
            ]
            self.assertEqual(len(match), 1, (expected, [(s["name"], s["pages"]) for s in view["schedules"]]))
            schedule = match[0]
            if "key_role" in expected:
                self.assertEqual(schedule["key_role"], expected["key_role"])
            self.assertEqual(schedule["block_count"], expected["blocks"])
            if "notes_contain" in expected:
                self.assertTrue(any(expected["notes_contain"] in n for n in schedule["notes"]), schedule["notes"])
            for hidden in expected.get("hidden_contains", []):
                self.assertIn(hidden, schedule["hidden_text"])
                self.assertFalse(any(hidden in level for level in schedule["levels"]), schedule["levels"])

        for expected in spec.get("plate_tables", []):
            table = next(t for t in view["plate_tables"] if t["kind"] == expected["kind"])
            self.assertEqual(table["marks"], expected["marks"])

        for expected in spec["entries"]:
            with self.subTest(entry=expected.get("mark") or expected.get("location")):
                entry = _find(view, expected)
                self.assertTrue(entry["is_definition_not_quantity"])
                if "mark" in expected:
                    # A mark is never parsed into grids, however it is spelled.
                    self.assertEqual(entry["key_role"], "mark")
                    self.assertEqual(entry["locations"], [])
                if "sections" in expected:
                    self.assertEqual([s["designation"] for s in entry["sections"]], expected["sections"])
                if "location_count" in expected:
                    self.assertEqual(entry["listed_location_count"], expected["location_count"])
                by_raw = {l["raw"]: l for l in entry["locations"]}
                for raw, labels in expected.get("grids", {}).items():
                    self.assertEqual([g["label"] for g in by_raw[raw]["grids"]], labels)
                for raw, (index, inches) in expected.get("offsets", {}).items():
                    self.assertEqual(by_raw[raw]["grids"][index]["offset"]["inches"], inches)
                if "repeated_label" in expected:
                    self.assertEqual(entry["repeated_label"], expected["repeated_label"])
                for hidden in expected.get("hidden", []):
                    self.assertIn(hidden, entry["hidden_text"])
                for note in expected.get("notes", []):
                    self.assertIn(note, entry["notes"])
                if "cap_plate" in expected:
                    caps = [d["raw"] for p in entry["other_plates"] if p["type"] == "cap plate" for d in p["dimensions"]]
                    self.assertEqual(caps, [expected["cap_plate"]] if expected["cap_plate"] else [])
                plate, want = entry["plate"], expected.get("plate", {})
                if "status" in want:
                    self.assertEqual(plate["status"], want["status"], plate)
                if "raw" in want:
                    self.assertEqual([d["raw"] for d in plate["dimensions"]], want["raw"])
                if "labelled" in want:
                    self.assertEqual([[d["label"], d["raw"]] for d in plate["dimensions"]], want["labelled"])
                for key in ("printed", "type", "markers"):
                    if key in want:
                        self.assertEqual(plate[key], want[key])
                if "reference_page" in want:
                    self.assertEqual(plate["reference"]["detail"], want["detail"])
                    self.assertEqual(plate["reference"]["sheet"], want["sheet"])
                    self.assertEqual(plate["reference"]["page"], want["reference_page"])
                    self.assertEqual(plate["dimensions"], [])
                if "note_contains" in want:
                    self.assertIn(want["note_contains"], plate["note"])


def _make(spec):
    def test(self):
        self._check_document(spec)

    return test


for _spec in _REFERENCE["documents"]:
    setattr(ReferenceSetTests, f"test_{_spec['key']}", _make(_spec))


if __name__ == "__main__":
    unittest.main()
