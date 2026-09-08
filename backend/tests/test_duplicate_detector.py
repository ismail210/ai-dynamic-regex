"""Annotation-identity dedup: geometry must never determine identity."""

from __future__ import annotations

from services.multimodal.duplicate_detector import merge_duplicate_predictions


def _pred(*, oid, page, bbox, label, conf=0.8, geom_bbox=None, section=None):
    return {
        "object_id": oid,
        "section": section if section is not None else label,
        "normalized_text": label,
        "raw_text": label,
        "original_token": label,
        "confidence": {"overall": conf},
        "source_text": {"page_number": page, "bounding_box": bbox},
        "geometry_preview": {"bbox": geom_bbox} if geom_bbox else None,
        "component_id": oid,
    }


def test_two_labels_different_positions_not_merged():
    a = _pred(oid="token_p3_10", page=3, bbox=[10, 10, 40, 20], label="W10X19")
    b = _pred(oid="token_p3_88", page=3, bbox=[400, 500, 430, 510], label="W10X19")
    out = merge_duplicate_predictions([a, b])
    assert out["duplicate_count"] == 0
    assert len(out["predictions"]) == 2


def test_same_text_duplicated_by_two_extraction_passes_is_merged():
    a = _pred(oid="token_p3_10", page=3, bbox=[10, 10, 40, 20], label="W16X26", conf=0.7)
    b = _pred(oid="line_9f2", page=3, bbox=[11, 10, 41, 20], label="W16X26", conf=0.9)
    out = merge_duplicate_predictions([a, b])
    assert out["duplicate_count"] == 1
    assert len(out["predictions"]) == 1
    # highest-confidence survivor kept
    assert out["predictions"][0]["object_id"] == "line_9f2"


def test_two_labels_on_same_gridline_stay_separate():
    # identical geometry_preview (same nearest gridline) but distinct source
    # text positions and distinct labels -> must NOT merge.
    grid = [200, 0, 205, 900]
    a = _pred(oid="token_p5_3", page=5, bbox=[100, 100, 130, 110], label="W21X44", geom_bbox=grid)
    b = _pred(oid="token_p5_4", page=5, bbox=[100, 700, 130, 710], label="W24X55", geom_bbox=grid)
    out = merge_duplicate_predictions([a, b])
    assert out["duplicate_count"] == 0
    assert len(out["predictions"]) == 2


def test_same_label_many_positions_sharing_one_gridline_not_collapsed():
    grid = [200, 0, 205, 900]
    preds = [
        _pred(oid=f"token_p5_{i}", page=5, bbox=[100, 40 * i, 130, 40 * i + 10],
              label="W10X33", geom_bbox=grid)
        for i in range(12)
    ]
    out = merge_duplicate_predictions(preds)
    assert out["duplicate_count"] == 0
    assert len(out["predictions"]) == 12


def test_page_identity_respected():
    a = _pred(oid="token_p1_10", page=1, bbox=[10, 10, 40, 20], label="C12X20.7")
    b = _pred(oid="token_p2_10", page=2, bbox=[10, 10, 40, 20], label="C12X20.7")
    out = merge_duplicate_predictions([a, b])
    assert out["duplicate_count"] == 0
    assert len(out["predictions"]) == 2


def test_geometry_association_change_does_not_alter_identity():
    """The same two source annotations, once with geometry_preview populated
    and once without, must dedup identically."""
    def scene(geom):
        return [
            _pred(oid="token_p3_10", page=3, bbox=[10, 10, 40, 20], label="W12X26",
                  geom_bbox=geom, conf=0.7),
            _pred(oid="token_p3_10b", page=3, bbox=[10, 10, 40, 20], label="W12X26",
                  geom_bbox=geom, conf=0.9),
            _pred(oid="token_p3_55", page=3, bbox=[600, 600, 630, 610], label="W12X26",
                  geom_bbox=geom, conf=0.8),
        ]
    with_geom = merge_duplicate_predictions(scene([0, 0, 5, 900]))
    no_geom = merge_duplicate_predictions(scene(None))
    assert with_geom["duplicate_count"] == no_geom["duplicate_count"] == 1
    assert len(with_geom["predictions"]) == len(no_geom["predictions"]) == 2


def test_missing_source_bbox_never_merges_by_geometry():
    # geometry-inferred token: no source text bbox. Must not merge with a
    # real label just because a section string matches.
    real = _pred(oid="token_p4_2", page=4, bbox=[10, 10, 40, 20], label="W18X40")
    inferred = {
        "object_id": "geo_abc", "section": "W18X40",
        "normalized_text": "W18X40", "raw_text": "", "original_token": "",
        "confidence": {"overall": 0.5},
        "source_text": {"page_number": 4, "bounding_box": None},
        "geometry_preview": {"bbox": [12, 12, 42, 22]},
    }
    out = merge_duplicate_predictions([real, inferred])
    assert out["duplicate_count"] == 0
    assert len(out["predictions"]) == 2
