"""Source-annotation identity for duplicate prediction merge."""

from __future__ import annotations

import unittest

from services.multimodal.duplicate_detector import merge_duplicate_predictions


def _pred(
    *,
    object_id: str,
    token: str,
    page: int,
    bbox,
    confidence: float = 0.8,
    geometry_preview=None,
    token_id: str = "",
    missing_label: bool = False,
) -> dict:
    payload = {
        "object_id": object_id,
        "component_id": f"comp_{object_id}",
        "section": token,
        "original_token": token,
        "raw_text": token,
        "confidence": confidence,
        "page_number": page,
        "bounding_box": list(bbox) if bbox else None,
        "source_text": {
            "raw": token,
            "normalized": token,
            "page_number": page,
            "bounding_box": list(bbox) if bbox else None,
            "token_id": token_id or object_id,
        },
        "geometry_preview": geometry_preview or {},
        "prediction_source": "Fusion",
    }
    if missing_label:
        payload["source_text"] = {"raw": "", "normalized": "", "page_number": page}
        payload["bounding_box"] = None
        payload["original_token"] = ""
        payload["raw_text"] = ""
        payload["missing_label"] = True
        payload["prediction_source"] = "Geometry"
    return payload


class DuplicateDetectorTests(unittest.TestCase):
    def test_two_w10x19_at_different_positions_stay_separate(self) -> None:
        result = merge_duplicate_predictions(
            [
                _pred(object_id="a", token="W10X19", page=4, bbox=[10, 10, 40, 20]),
                _pred(object_id="b", token="W10X19", page=4, bbox=[400, 10, 430, 20]),
            ]
        )
        self.assertEqual(len(result["predictions"]), 2)
        self.assertEqual(result["duplicate_count"], 0)

    def test_same_text_from_two_extraction_passes_keeps_highest_confidence(self) -> None:
        result = merge_duplicate_predictions(
            [
                _pred(
                    object_id="token_p4_1",
                    token_id="token_p4_1",
                    token="W16X26",
                    page=4,
                    bbox=[10, 10, 40, 20],
                    confidence=0.4,
                ),
                _pred(
                    object_id="token_p4_1b",
                    token_id="token_p4_1",
                    token="W16X26",
                    page=4,
                    bbox=[11, 10, 41, 20],
                    confidence=0.9,
                ),
            ]
        )
        self.assertEqual(len(result["predictions"]), 1)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["predictions"][0]["confidence"], 0.9)

    def test_twelve_w10x33_sharing_one_gridline_are_not_collapsed(self) -> None:
        gridline = {"bbox": [0, 0, 2000, 40]}
        predictions = [
            _pred(
                object_id=f"t{index}",
                token="W10X33",
                page=7,
                bbox=[20 + index * 80, 50, 50 + index * 80, 62],
                geometry_preview=gridline,
            )
            for index in range(12)
        ]
        result = merge_duplicate_predictions(predictions)
        self.assertEqual(len(result["predictions"]), 12)

    def test_page_identity_is_respected(self) -> None:
        box = [10, 10, 40, 20]
        result = merge_duplicate_predictions(
            [
                _pred(object_id="p1", token="W12X16", page=1, bbox=box),
                _pred(object_id="p2", token="W12X16", page=2, bbox=box),
            ]
        )
        self.assertEqual(len(result["predictions"]), 2)

    def test_geometry_preview_on_and_off_deduplicate_identically(self) -> None:
        low = _pred(
            object_id="token_same",
            token_id="token_same",
            token="W18X35",
            page=5,
            bbox=[10, 10, 40, 20],
            confidence=0.5,
            geometry_preview={"bbox": [0, 0, 900, 900]},
        )
        high = _pred(
            object_id="token_same_b",
            token_id="token_same",
            token="W18X35",
            page=5,
            bbox=[10, 10, 40, 20],
            confidence=0.95,
            geometry_preview={},
        )
        with_geo = merge_duplicate_predictions([low, high])
        without_geo = merge_duplicate_predictions(
            [{**low, "geometry_preview": {}}, {**high, "geometry_preview": {}}]
        )
        self.assertEqual(with_geo["duplicate_count"], 1)
        self.assertEqual(without_geo["duplicate_count"], 1)
        self.assertEqual(len(with_geo["predictions"]), len(without_geo["predictions"]))

    def test_geometry_inferred_token_without_source_bbox_never_merges_by_section(
        self,
    ) -> None:
        labeled = _pred(
            object_id="callout",
            token="W10X33",
            page=8,
            bbox=[10, 10, 40, 20],
        )
        inferred = _pred(
            object_id="geo1",
            token="W10X33",
            page=8,
            bbox=None,
            missing_label=True,
        )
        inferred["section"] = "W10X33"
        other = dict(inferred)
        other["object_id"] = "geo2"
        result = merge_duplicate_predictions([labeled, inferred, other])
        self.assertEqual(len(result["predictions"]), 3)

    def test_overlapping_source_boxes_same_label_merge(self) -> None:
        result = merge_duplicate_predictions(
            [
                _pred(
                    object_id="ocr-1",
                    token="W12X16",
                    page=1,
                    bbox=[100, 100, 120, 110],
                ),
                _pred(
                    object_id="ocr-2",
                    token="W12X16",
                    page=1,
                    bbox=[101, 100, 121, 110],
                ),
            ]
        )
        self.assertEqual(len(result["predictions"]), 1)

    def test_component_id_is_not_identity(self) -> None:
        result = merge_duplicate_predictions(
            [
                {
                    "object_id": "geom_a",
                    "component_id": "beam_1",
                    "section": "W10X19",
                    "original_token": "W10X19",
                    "page_number": 3,
                    "bounding_box": [10, 10, 30, 20],
                    "source_text": {
                        "raw": "W10X19",
                        "page_number": 3,
                        "bounding_box": [10, 10, 30, 20],
                    },
                    "confidence": 0.8,
                },
                {
                    "object_id": "geom_b",
                    "component_id": "beam_1",
                    "section": "W10X19",
                    "original_token": "W10X19",
                    "page_number": 3,
                    "bounding_box": [300, 10, 330, 20],
                    "source_text": {
                        "raw": "W10X19",
                        "page_number": 3,
                        "bounding_box": [300, 10, 330, 20],
                    },
                    "confidence": 0.8,
                },
            ]
        )
        self.assertEqual(len(result["predictions"]), 2)


if __name__ == "__main__":
    unittest.main()
