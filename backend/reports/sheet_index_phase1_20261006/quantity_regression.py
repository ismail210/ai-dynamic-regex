"""Before/after snapshot of the production path on the 8 benchmark PDFs.

Runs extraction -> multimodal prediction (persist=False, no artifacts) ->
QuantityEngine, and records what Phase 1 must not change: quantity rows and
totals, mark map, schedule rows, prediction digest, Drawing Intelligence
profile (every key except the new ``sheet_index``), plus a hash of every file
under backend/training/ taken before and after the run.

python reports/sheet_index_phase1_20261006/quantity_regression.py before|after
python reports/sheet_index_phase1_20261006/quantity_regression.py diff [first second]
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
OUT = Path(__file__).resolve().parent
TESTING = Path("/Users/hibareda/Desktop/Testing Projects")
PDFS = {
    "furley": BACKEND / "uploads" / "Struct.pdf",
    "burrville": BACKEND / "uploads" / "Burrville ES - ST.pdf",
    "brandywine": BACKEND / "uploads" / "Structural4__3aa51f661bdf.pdf",
    "springhill": BACKEND / "uploads" / "ST - Springhill Lake__f6ddc4a7e233.pdf",
    "osse": TESTING / "OSSE - ST.pdf",
    "yellowspring": TESTING / "ST1.pdf",
    "washlatin": TESTING / "New bldg - St.pdf",
    "fortdavis": TESTING / "Structure - Copy1 - edit.pdf",
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _training_hashes() -> dict:
    root = BACKEND / "training"
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _snapshot(key: str, pdf: Path) -> dict:
    from services.extraction_engine import extract_engineering_document
    from services.multimodal.pipeline import run_multimodal_pipeline
    from services.takeoff.quantity_engine import QuantityEngine
    from services.takeoff.takeoff_exporter import build_takeoff_rows

    started = time.time()
    document = extract_engineering_document(pdf)
    result = run_multimodal_pipeline(pdf, persist=False, document_structure=document)
    predictions = result.get("predictions") or []
    report = QuantityEngine().count(predictions)
    rows = build_takeoff_rows(predictions, quantity_report=report)
    profile = dict((document.get("legend_profile") or {}).get("drawing_intelligence") or {})
    sheet_index = profile.pop("sheet_index", None)
    grids = [
        {
            "page": g.get("page"), "kind": g.get("kind"), "source": g.get("source"),
            "rows": [
                {k: r.get(k) for k in ("mark", "section", "size_text", "plate_text", "plate_status", "level")}
                for r in g.get("rows") or []
            ],
        }
        for g in document.get("schedule_grid") or []
    ]
    return {
        "pdf": str(pdf),
        "seconds": round(time.time() - started, 1),
        "prediction_count": len(predictions),
        "prediction_digest": _digest([
            (p.get("object_id"), p.get("section") or p.get("predicted_section"), p.get("takeoff_eligible"),
             p.get("object_scope"), p.get("prediction_source"))
            for p in predictions
        ]),
        "quantity_rows": [(r["Section"], r["Quantity"], r["Quantity Method"]) for r in rows],
        "quantity_total": int(sum(r["Quantity"] for r in rows)),
        "mark_map": document.get("schedule_mark_map") or {},
        "schedule_grid_digest": _digest(grids),
        "schedule_row_count": sum(len(g["rows"]) for g in grids),
        "token_count": len(document.get("engineering_tokens") or []),
        "profile_keys": sorted(profile),
        "profile_digest": _digest(profile),
        "levels_digest": _digest(profile.get("levels")),
        "column_schedule_digest": _digest(profile.get("column_schedule")),
        "definitions_digest": _digest(profile.get("definitions")),
        "has_sheet_index": sheet_index is not None,
    }


def run(label: str) -> None:
    import tempfile

    from config import settings

    if label == "before":
        # The only production change is the sheet_index key, so "before" is
        # this code with that one call removed.
        import services.engineering.drawing_intelligence as di
        di.sheet_index = lambda document: None
    payload = {"training_before": _training_hashes(), "documents": {}}
    # A fresh legend-profile cache: every profile is rebuilt, nothing replayed
    # from (or written to) backend/training/legend_profiles.
    with tempfile.TemporaryDirectory(prefix="sheet_index_regression_") as tmp:
        object.__setattr__(settings, "legend_profile_cache_dir", Path(tmp))
        for key, pdf in PDFS.items():
            print(f"{label}: {key}", flush=True)
            payload["documents"][key] = _snapshot(key, pdf)
            print(f"  total={payload['documents'][key]['quantity_total']} "
                  f"preds={payload['documents'][key]['prediction_count']} "
                  f"{payload['documents'][key]['seconds']}s", flush=True)
    payload["training_after"] = _training_hashes()
    (OUT / f"regression_{label}.json").write_text(json.dumps(payload, indent=2, default=str))


def diff(first: str = "before", second: str = "after") -> None:
    before = json.loads((OUT / f"regression_{first}.json").read_text())
    after = json.loads((OUT / f"regression_{second}.json").read_text())
    for label, data in ((first, before), (second, after)):
        changed = [k for k, v in data["training_after"].items() if data["training_before"].get(k) != v]
        print(f"training files changed during {label} run: {changed or 'none'}")
    for key, old in before["documents"].items():
        new = after["documents"][key]
        diffs = [
            field for field in old
            if field not in ("seconds", "has_sheet_index", "pdf") and old[field] != new.get(field)
        ]
        print(key, "IDENTICAL" if not diffs else f"DIFF {diffs}",
              f"total {old['quantity_total']} -> {new['quantity_total']}",
              f"sheet_index before={old['has_sheet_index']} after={new['has_sheet_index']}")


if __name__ == "__main__":
    diff(*sys.argv[2:]) if sys.argv[1] == "diff" else run(sys.argv[1])
