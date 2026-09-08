"""
Canonical takeoff ground-truth parsing + evaluation.

ONE implementation, used by BOTH the production ``validate_takeoff`` path and
the research benchmark harness, so the UI can never show a number the
benchmark would not reproduce on the same inputs.

Three concepts are kept strictly separate (see the engineering principle in
the sprint brief):

  * reading a section label   -> ``canonical_section`` / prediction aggregation
  * how many physical members a label represents -> quantity, per scope
  * matching the estimator's final takeoff -> ``evaluate``

Scope is explicit. Every workbook row lands in exactly one bucket and the
quantity in each bucket is reported. The success metric is computed against
``PRIMARY_FRAMING`` only; ``PLATES`` and ``CONNECTION_MISC`` quantities are
surfaced as "unsupported" (not counted against the model), and out-of-scope
/ unparseable rows as "excluded". Nothing is dropped silently.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from services.database_loader import catalog_form

# --- scope -----------------------------------------------------------------

PRIMARY_FRAMING = "primary_framing"     # beams, columns, braces, joists
PLATES = "plates"                       # base plates, gusset / stiffener plates
CONNECTION_MISC = "connection_misc"     # connection angles, clips, misc steel
OUT_OF_SCOPE = "out_of_scope"           # deck, floor fill, non-steel, details
SCOPES = (PRIMARY_FRAMING, PLATES, CONNECTION_MISC, OUT_OF_SCOPE)

# Revit structural-schedule sheet names -> scope. Matched on a normalized
# (lowercased, de-spaced) sheet name, substring-aware.
_SHEET_SCOPE = [
    ("structuralframingschedule", PRIMARY_FRAMING),
    ("structuralcolumnschedule", PRIMARY_FRAMING),
    ("structuralbracingschedule", PRIMARY_FRAMING),
    ("structuraljoistschedule", PRIMARY_FRAMING),
    ("momentconnectionschedule", CONNECTION_MISC),
    ("structuralconnectionschedule", CONNECTION_MISC),
    ("baseplateschedule", PLATES),
    ("structuralplateschedule", PLATES),
    ("miscellaneousplateschedule", PLATES),
    ("structuraldeckschedule", OUT_OF_SCOPE),
    ("structuralfloorschedule", OUT_OF_SCOPE),
    ("miscellaneousdetails", OUT_OF_SCOPE),
    ("steelelementssummary", OUT_OF_SCOPE),  # a rollup -> would double count
]
_KEYWORD_SCOPE = [  # non-Revit / flexible workbooks
    ("framing", PRIMARY_FRAMING), ("beam", PRIMARY_FRAMING),
    ("column", PRIMARY_FRAMING), ("bracing", PRIMARY_FRAMING),
    ("brace", PRIMARY_FRAMING), ("joist", PRIMARY_FRAMING),
    ("moment", CONNECTION_MISC), ("connection", CONNECTION_MISC),
    ("baseplate", PLATES), ("plate", PLATES),
    ("deck", OUT_OF_SCOPE), ("floor", OUT_OF_SCOPE), ("detail", OUT_OF_SCOPE),
]

_MEMBER_TYPE = {
    PRIMARY_FRAMING: "member", PLATES: "plate",
    CONNECTION_MISC: "connection", OUT_OF_SCOPE: "misc",
}

_SECTION_SHAPED = re.compile(r"^(2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)\d", re.I)


def _sheet_scope(sheet_name: str) -> Optional[str]:
    key = re.sub(r"\s+", "", sheet_name.strip().lower())
    for needle, scope in _SHEET_SCOPE:
        if needle == key:
            return scope
    for needle, scope in _KEYWORD_SCOPE:
        if needle in key:
            return scope
    return None


# --- section normalization ----------------------------------------------

def canonical_section(value: Any) -> Optional[str]:
    """The one section normalizer. Returns the AISC catalog spelling of
    ``value`` (case / whitespace / separator / unicode-cross folded, round-HSS
    shorthand resolved), or ``None`` when the text is not an exact catalog
    designation. Never substitutes a similar-but-different shape."""

    text = str(value or "").upper().strip()
    if not text or text in {"NAN", "NONE", "TYPE"}:
        return None
    text = text.replace("×", "X").replace("✕", "X")
    text = text.replace(" ", "").replace("-", "").replace("_", "")
    resolved = catalog_form(text)
    return resolved or None


# --- workbook parsing --------------------------------------------------

def _find_type_col(raw: pd.DataFrame) -> tuple[int, Dict[str, int]]:
    """Header row + column map. Scans the first 15 rows for a 'Type' cell and
    records Length/Weight/Count/Mark/Comments alongside it."""

    for i in range(min(15, len(raw))):
        mapping: Dict[str, int] = {}
        for j, cell in enumerate(raw.iloc[i].tolist()):
            key = str(cell or "").strip().lower()
            if key == "type":
                mapping["type"] = j
            elif key in {"length", "len"}:
                mapping.setdefault("length", j)
            elif key in {"weight", "wt", "overall weight", "overall weigth"}:
                mapping.setdefault("weight", j)
            elif key == "count":
                mapping.setdefault("count", j)
            elif key == "mark":
                mapping.setdefault("mark", j)
            elif key in {"comments", "comment"}:
                mapping.setdefault("comments", j)
        if "type" in mapping:
            return i, mapping
    return -1, {}


def parse_workbook_ground_truth(path: str | Path) -> Dict[str, Any]:
    """Parse a project estimate workbook into scoped, canonicalized GT.

    Returns a dict with:
      scope[bucket][section] -> [ {sheet,row,raw,length,weight,mark} ... ]
      scope_quantity[bucket] -> int
      dropped -> [ {sheet,row,raw,canonical,reason} ]   (non-catalog rows)
      sheets  -> [ {name, scope, rows} ]
    plus the legacy ``items`` / ``aggregates`` / ``unique_labels`` /
    ``total_quantity`` keys (populated from PRIMARY_FRAMING) so existing
    consumers keep working while counting only real members.
    """

    file_path = Path(path)
    sheet_frames: Dict[str, pd.DataFrame] = {}
    with pd.ExcelFile(file_path) as xl:
        sheet_names = list(xl.sheet_names)
        for name in sheet_names:
            if _sheet_scope(name) is not None:
                sheet_frames[name] = pd.DataFrame(xl.parse(sheet_name=name, header=None))

    scope: Dict[str, Dict[str, List[dict]]] = {s: defaultdict(list) for s in SCOPES}
    dropped: List[dict] = []
    sheets_meta: List[dict] = []

    for sheet in sheet_names:
        bucket = _sheet_scope(sheet)
        if bucket is None:
            continue
        raw = sheet_frames[sheet]
        hdr, cols = _find_type_col(raw)
        if hdr < 0:
            continue
        tcol = cols["type"]
        rows_kept = 0
        for i in range(hdr + 1, len(raw)):
            cell = raw.iloc[i, tcol] if tcol < raw.shape[1] else None
            if cell is None or bool(pd.isna(cell)):
                continue
            s = str(cell).strip()
            if not s or s.upper() in ("NAN", "TYPE"):
                continue
            if s.upper().startswith("STRUCTURAL") or "SCHEDULE" in s.upper():
                # "StructuralConnection_BasePlates" literal Type strings, sheet titles
                continue
            count = 1
            if "count" in cols and cols["count"] < raw.shape[1]:
                try:
                    cv = raw.iloc[i, cols["count"]]
                    if pd.notna(cv):
                        count = max(1, int(float(cv)))
                except (TypeError, ValueError):
                    count = 1
            rec = {
                "sheet": sheet, "row": int(i), "raw": s,
                "length": _cell(raw, i, cols.get("length")),
                "weight": _cell(raw, i, cols.get("weight")),
                "mark": _cell(raw, i, cols.get("mark")),
            }
            canon = canonical_section(s)
            if canon is None:
                if _SECTION_SHAPED.match(re.sub(r"[\s_-]", "", s.upper())):
                    dropped.append({**rec, "canonical": None,
                                    "reason": "not_an_exact_aisc_label"})
                # else: not section-shaped at all -> silently skip (deck names etc.)
                continue
            for _ in range(count):
                scope[bucket][canon].append(rec)
                rows_kept += 1
        if rows_kept or bucket != OUT_OF_SCOPE:
            sheets_meta.append({"name": sheet, "scope": bucket, "rows": rows_kept})

    # Flexible / AISC-style workbook fallback: no Revit schedule matched.
    parser_used = "canonical_takeoff_eval"
    if not any(scope[s] for s in SCOPES):
        if _flexible_fallback(file_path, scope, sheets_meta):
            parser_used = "engineering_excel_loader"

    scope_quantity = {s: sum(len(v) for v in scope[s].values()) for s in SCOPES}

    primary = scope[PRIMARY_FRAMING]
    aggregates = [
        {
            "canonical_label": section,
            "entity_class": "steel_section",
            "member_type": _MEMBER_TYPE[PRIMARY_FRAMING],
            "quantity": len(occ),
            "occurrences": occ,
            "source": "canonical_ground_truth",
        }
        for section, occ in sorted(primary.items(), key=lambda kv: -len(kv[1]))
    ]
    items = [
        {"canonical_label": section, "entity_class": "steel_section",
         "member_type": _MEMBER_TYPE[PRIMARY_FRAMING], "quantity": 1,
         "sheet": o["sheet"], "length": o["length"], "weight": o["weight"],
         "mark": o["mark"], "source": "canonical_ground_truth"}
        for section, occ in primary.items() for o in occ
    ]

    return {
        "source_file": file_path.name,
        "source_path": str(file_path),
        "parser": parser_used,
        "sheets_used": [s["name"] for s in sheets_meta if s["scope"] == PRIMARY_FRAMING],
        "scope": {s: {k: v for k, v in scope[s].items()} for s in SCOPES},
        "scope_quantity": scope_quantity,
        "scope_sections": {s: dict(sorted(
            ((k, len(v)) for k, v in scope[s].items()), key=lambda kv: -kv[1]
        )) for s in SCOPES},
        "dropped": dropped,
        "dropped_quantity": len(dropped),
        "sheets": sheets_meta,
        # legacy compatibility (PRIMARY_FRAMING only -- real members)
        "items": items,
        "aggregates": aggregates,
        "unique_labels": len(primary),
        "total_quantity": scope_quantity[PRIMARY_FRAMING],
        "entity_distribution": {"steel_section": scope_quantity[PRIMARY_FRAMING]},
        "row_count": len(items),
        "role": "ground_truth",
        "excel_is_prediction": False,
    }


def _cell(raw: pd.DataFrame, i: int, j: Optional[int]) -> Optional[str]:
    if j is None or j >= raw.shape[1]:
        return None
    v = raw.iloc[i, j]
    return None if pd.isna(v) else str(v)


def _flexible_fallback(file_path: Path, scope: Dict[str, Dict[str, List[dict]]],
                       sheets_meta: List[dict]) -> bool:
    """Hand-built / AISC-style workbook with no Revit schedule sheet. Returns
    True when it produced any primary-framing rows."""

    try:
        from services.engineering.excel_loader import load_engineering_excel
        flexible = load_engineering_excel(file_path)
    except Exception:
        return False
    added = 0
    for item in flexible.get("items") or []:
        canon = canonical_section(item.get("shape") or item.get("section") or "")
        if canon is None:
            continue
        qty = int(item.get("count") or item.get("quantity") or 1)
        rec = {"sheet": item.get("sheet") or "flexible", "row": -1,
               "raw": str(item.get("shape") or item.get("section")),
               "length": item.get("length"), "weight": item.get("weight"),
               "mark": item.get("mark")}
        for _ in range(max(1, qty)):
            scope[PRIMARY_FRAMING][canon].append(rec)
            added += 1
    if added:
        sheets_meta.append({"name": "flexible_excel", "scope": PRIMARY_FRAMING, "rows": added})
    return added > 0


# --- prediction aggregation + evaluation -------------------------------

def aggregate_predictions(predictions: List[dict]) -> Dict[str, Any]:
    counts: Dict[str, int] = defaultdict(int)
    object_ids: Dict[str, List[str]] = defaultdict(list)
    abstained = plate_or_dim = catalog_invalid = 0
    for p in predictions:
        if p.get("takeoff_eligible") is False:
            continue
        qty = int(p.get("quantity") or 1)
        if p.get("section_prediction_not_applicable") or p.get("plate_annotation_type"):
            plate_or_dim += qty
            continue
        raw = p.get("section") or p.get("predicted_shape") or p.get("prediction") or ""
        if not raw:
            abstained += qty
            continue
        canon = canonical_section(raw)
        if canon is None:
            catalog_invalid += qty
            continue
        counts[canon] += qty
        object_ids[canon].append(str(p.get("object_id") or p.get("component_id") or ""))
    return {
        "counts": dict(counts), "object_ids": dict(object_ids),
        "abstained": abstained, "plate_or_dimension": plate_or_dim,
        "catalog_invalid": catalog_invalid,
    }


def evaluate(
    predictions: List[dict],
    ground_truth: Dict[str, Any],
    *,
    scope: str = PRIMARY_FRAMING,
) -> Dict[str, Any]:
    """Estimator-facing takeoff evaluation against one GT scope.

    caught(s)        = min(predicted(s), gt(s))
    success(s)       = caught / gt
    overall_success  = Σ caught / Σ gt        (never > 100%)
    precision        = Σ caught / Σ predicted
    false_positives  = Σ max(predicted - gt, 0)
    """

    gt_scope: Dict[str, List[dict]] = ground_truth.get("scope", {}).get(scope, {})
    gt_counts: Dict[str, int] = {}
    if gt_scope:
        gt_counts = {k: len(v) if isinstance(v, list) else int(v) for k, v in gt_scope.items()}
    else:
        # A caller passed a bare {items|aggregates} ground-truth dict.
        for s in ground_truth.get("aggregates") or []:
            label = canonical_section(s.get("canonical_label") or s.get("shape") or "")
            if label:
                gt_counts[label] = gt_counts.get(label, 0) + int(s.get("quantity") or 0)
                gt_scope.setdefault(label, list(s.get("occurrences") or []))
        if not gt_counts:
            for it in ground_truth.get("items") or []:
                label = canonical_section(it.get("canonical_label") or it.get("shape") or "")
                if label:
                    gt_counts[label] = gt_counts.get(label, 0) + int(it.get("quantity") or 1)
                    gt_scope.setdefault(label, []).append(it)

    agg = aggregate_predictions(predictions)
    pred_counts = agg["counts"]

    rows: List[dict] = []
    sum_caught = sum_gt = sum_pred = fp = 0
    for section in sorted(set(gt_counts) | set(pred_counts)):
        g = int(gt_counts.get(section, 0))
        pr = int(pred_counts.get(section, 0))
        caught = min(pr, g)
        sum_caught += caught
        sum_gt += g
        sum_pred += pr
        fp += max(pr - g, 0)
        occ = gt_scope.get(section) or []
        rows.append({
            "section": section,
            "ground_truth": g,
            "predicted": pr,
            "caught": caught,
            "delta": pr - g,
            "success_pct": round(100.0 * caught / g, 1) if g else None,
            "status": (
                "missing" if pr == 0 and g > 0
                else "extra" if g == 0 and pr > 0
                else "over" if pr > g
                else "under" if pr < g
                else "match"
            ),
            "gt_rows": [
                {"sheet": o.get("sheet"), "row": o.get("row"), "raw": o.get("raw")}
                for o in (occ if isinstance(occ, list) else [])[:50]
            ],
            "predicted_object_ids": agg["object_ids"].get(section, [])[:50],
        })

    sq = ground_truth.get("scope_quantity", {})
    return {
        "scope": scope,
        "overall_success_pct": round(100.0 * sum_caught / sum_gt, 2) if sum_gt else 0.0,
        "caught": sum_caught,
        "ground_truth_total": sum_gt,
        "predicted_total": sum_pred,
        "false_positives": fp,
        "precision_pct": round(100.0 * sum_caught / sum_pred, 2) if sum_pred else 0.0,
        "sections_ground_truth": len(gt_counts),
        "sections_predicted": len(pred_counts),
        "sections_missing": sum(1 for r in rows if r["status"] == "missing"),
        "sections_extra": sum(1 for r in rows if r["status"] == "extra"),
        "abstained_predictions": agg["abstained"],
        "plate_or_dimension_predictions": agg["plate_or_dimension"],
        "catalog_invalid_predictions": agg["catalog_invalid"],
        "unsupported_gt_quantity": int(sq.get(PLATES, 0)) + int(sq.get(CONNECTION_MISC, 0)),
        "excluded_gt_quantity": int(sq.get(OUT_OF_SCOPE, 0)) + int(ground_truth.get("dropped_quantity", 0)),
        "scope_quantity": dict(sq),
        "rows": rows,
    }
