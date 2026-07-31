"""
Paired PDF + Excel dataset builder.

For each training pair:
  PDF → extract tokens → classify
  Excel → ground-truth entities
  Match → canonical rich training rows → optional augmentation/features

Excel is NEVER used at inference time.

Shape / prefix / regex metadata columns use ``extract_structural_features``
(the single production feature source). ``material_hint`` remains AISC-aware
enrichment for paired rows and is not the ASTM-only ML feature.
"""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from config import settings
from services.database_loader import lookup_shape
from services.engineering.geometry_adapters import extract_geometry_document
from services.engineering.rule_engine import evaluate_engineering_rules
from services.engineering.structural_graph import build_structural_graph
from services.entity_taxonomy import classify_category
from services.feature_extractor import extract_structural_features
from services.multimodal.feature_providers import (
    GeometryFeatureProvider,
    GraphFeatureProvider,
)
from services.pdf_parser import extract_document_structure
from services.takeoff.ground_truth_excel import parse_ground_truth_excel


def _norm(token: str) -> str:
    return str(token or "").upper().replace(" ", "").replace("-", "")


def _material_hint(token: str, aisc: Optional[dict]) -> Optional[str]:
    """Paired-dataset enrichment: prefer AISC type, else taxonomy material class."""

    if aisc and aisc.get("type"):
        return str(aisc["type"])
    cat = classify_category(token)
    if cat.category == "material":
        return cat.class_name
    return None


def load_pair_manifest() -> Dict[str, Any]:
    path = settings.training_dir / "pair_manifest.json"
    if not path.exists():
        return {"version": 1, "pairs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def list_training_pairs() -> List[dict]:
    """Discover pairs from manifest and/or matching stems in pdf/ + excel/."""

    pairs: Dict[str, dict] = {}
    manifest = load_pair_manifest()
    for p in manifest.get("pairs") or []:
        pid = p.get("id") or Path(p.get("pdf_canonical") or "").stem
        pdf_path = settings.training_pdf_dir / (p.get("pdf_canonical") or f"{pid}.pdf")
        excel_path = settings.training_excel_dir / (p.get("excel_canonical") or f"{pid}.xlsm")
        # fallback to original names in pdfs/excels
        if not pdf_path.exists() and p.get("pdf"):
            pdf_path = settings.training_dir / "pdfs" / p["pdf"]
        if not excel_path.exists() and p.get("excel"):
            excel_path = settings.training_dir / "excels" / p["excel"]
        pairs[pid] = {
            "id": pid,
            "label": p.get("label") or pid,
            "pdf_path": str(pdf_path) if pdf_path.exists() else None,
            "excel_path": str(excel_path) if excel_path.exists() else None,
            "ready": pdf_path.exists() and excel_path.exists(),
        }

    # Auto-discover matching stems
    pdf_dir = settings.training_pdf_dir
    excel_dir = settings.training_excel_dir
    if pdf_dir.exists() and excel_dir.exists():
        excel_by_stem = {p.stem: p for p in excel_dir.iterdir() if p.suffix.lower() in {".xlsx", ".xls", ".xlsm"}}
        for pdf in pdf_dir.iterdir():
            if pdf.suffix.lower() != ".pdf":
                continue
            xls = excel_by_stem.get(pdf.stem)
            if not xls:
                continue
            pairs.setdefault(
                pdf.stem,
                {
                    "id": pdf.stem,
                    "label": pdf.stem,
                    "pdf_path": str(pdf),
                    "excel_path": str(xls),
                    "ready": True,
                },
            )
    return list(pairs.values())


def build_pair_rows(pdf_path: str | Path, excel_path: str | Path, pair_id: str = "") -> Dict[str, Any]:
    """Build rich training rows for one PDF/Excel pair."""

    pdf_path = Path(pdf_path)
    excel_path = Path(excel_path)
    document = extract_document_structure(str(pdf_path))
    geometry_document = extract_geometry_document(
        pdf_path, document_structure=document
    )
    graph_document = build_structural_graph(document, geometry_document)
    token_records = document.get("engineering_tokens") or []
    gt = parse_ground_truth_excel(excel_path)
    gt_by_label = { _norm(a["canonical_label"]): a for a in gt.get("aggregates") or [] }

    rows: List[dict] = []
    matched = 0
    geometry_provider = GeometryFeatureProvider()
    graph_provider = GraphFeatureProvider()
    for token_record in token_records:
        token = str(token_record.get("normalized_text") or token_record.get("text") or "")
        norm = _norm(token)
        aisc = lookup_shape(token)
        entity = classify_category(token)
        gt_hit = gt_by_label.get(norm)
        if not gt_hit and gt_by_label:
            nearest_label, nearest_score = max(
                (
                    (label, SequenceMatcher(None, norm, label).ratio())
                    for label in gt_by_label
                ),
                key=lambda item: item[1],
            )
            if nearest_score >= 0.78:
                gt_hit = gt_by_label[nearest_label]
        features = extract_structural_features(token)
        canonical = gt_hit["canonical_label"] if gt_hit else ""
        meta_source = str(canonical).strip() or token
        meta = (
            features
            if meta_source == token
            else extract_structural_features(meta_source)
        )
        entity_class = gt_hit["entity_class"] if gt_hit else {
            "structural_section": "steel_section",
            "pipe": "steel_section",
            "material": "material",
            "bolt": "bolt",
            "plate": "plate",
            "miscellaneous": "miscellaneous",
        }.get(entity.category, "unknown")
        if gt_hit:
            matched += 1
        context = {
            "token": token_record,
            "document": document,
            "geometry": geometry_document,
            "graph": graph_document,
        }
        geometry_features = geometry_provider.extract(context)
        graph_features = graph_provider.extract(context)
        rules = evaluate_engineering_rules(
            token=token,
            predicted_shape=canonical or token,
            geometry=geometry_features,
            graph=graph_document,
            graph_preview=graph_features,
        ).to_dict()
        line = token_record.get("line") or {}
        block = token_record.get("block") or {}
        row = {
            "pdf_token": token,
            "normalized_token": norm,
            "canonical_label": str(canonical).upper().replace(" ", ""),
            "entity_class": entity_class,
            "quantity": int(gt_hit["quantity"]) if gt_hit else 1,
            "source": "pdf+excel" if gt_hit else "pdf_only",
            "shape_family": meta["shape_family"],
            "material_hint": _material_hint(token, aisc),
            "company_prefix": meta["company_prefix"],
            "regex_signature": meta["regex_signature"],
            "aisc_match": bool(aisc),
            "aisc_type": aisc.get("type") if aisc else None,
            "pair_id": pair_id,
            "pdf_file": pdf_path.name,
            "excel_file": excel_path.name,
            "ocr_confidence": token_record.get("confidence"),
            "page_number": token_record.get("page"),
            "bbox": json.dumps(token_record.get("bbox") or []),
            "reading_order": token_record.get("reading_order"),
            "line_context": line.get("text"),
            "line_id": line.get("id"),
            "layout_role": block.get("role"),
            "neighboring_labels": json.dumps(
                token_record.get("neighbors") or []
            ),
            "nearby_dimensions": json.dumps(
                [
                    item
                    for item in document.get("dimensions") or []
                    if item.get("page_number") == token_record.get("page")
                ][:5]
            ),
            "geometry_features": json.dumps(geometry_features),
            "graph_features": json.dumps(graph_features),
            "engineering_rules": json.dumps(rules),
            "validation_status": "ground_truth_match" if gt_hit else "unlabeled",
            "reviewer_correction": False,
            **{f"feat_{k}": v for k, v in features.items()},
        }
        rows.append(row)

    # Excel-only members (present in GT, missing from PDF extraction)
    pdf_norms = {_norm(str(t.get("normalized_text") or "")) for t in token_records}
    missing_from_pdf = []
    for label, agg in gt_by_label.items():
        if label in pdf_norms:
            continue
        missing_from_pdf.append(agg)
        meta = extract_structural_features(agg["canonical_label"])
        rows.append(
            {
                "pdf_token": "",
                "normalized_token": label,
                "canonical_label": agg["canonical_label"],
                "entity_class": agg["entity_class"],
                "quantity": int(agg["quantity"]),
                "source": "excel_only",
                "shape_family": meta["shape_family"],
                "material_hint": None,
                "company_prefix": meta["company_prefix"],
                "regex_signature": meta["regex_signature"],
                "aisc_match": bool(lookup_shape(agg["canonical_label"])),
                "aisc_type": None,
                "pair_id": pair_id,
                "pdf_file": pdf_path.name,
                "excel_file": excel_path.name,
            }
        )

    return {
        "pair_id": pair_id,
        "pdf_file": pdf_path.name,
        "excel_file": excel_path.name,
        "pdf_pages": document["page_count"],
        "pdf_token_count": len(token_records),
        "excel_unique_labels": gt["unique_labels"],
        "matched_tokens": matched,
        "excel_only_count": len(missing_from_pdf),
        "row_count": len(rows),
        "ground_truth_summary": {
            "total_quantity": gt["total_quantity"],
            "entity_distribution": gt["entity_distribution"],
            "sheets_used": gt["sheets_used"],
        },
        "rows": rows,
    }


def build_paired_training_dataset(
    *,
    persist: bool = True,
    pair_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the rich paired dataset across all ready training pairs."""

    pairs = list_training_pairs()
    if pair_ids:
        wanted = set(pair_ids)
        pairs = [p for p in pairs if p["id"] in wanted]
    ready = [p for p in pairs if p.get("ready")]

    all_rows: List[dict] = []
    pair_reports: List[dict] = []
    for pair in ready:
        report = build_pair_rows(pair["pdf_path"], pair["excel_path"], pair_id=pair["id"])
        pair_reports.append({k: v for k, v in report.items() if k != "rows"})
        all_rows.extend(report["rows"])

    frame = pd.DataFrame(all_rows)
    out_path = settings.paired_dataset_path
    if persist and len(frame):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(out_path, index=False)

    summary = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "pair_count": len(ready),
        "row_count": len(all_rows),
        "sources": dict(frame["source"].value_counts()) if len(frame) else {},
        "entity_distribution": dict(frame["entity_class"].value_counts()) if len(frame) else {},
        "unique_labels": int(frame["canonical_label"].nunique()) if len(frame) else 0,
        "dataset_path": str(out_path) if persist else None,
        "pairs": pair_reports,
        "note": "Excel used as ground truth for training dataset creation only.",
    }
    if persist:
        meta_path = settings.training_dir / "paired_dataset_meta.json"
        meta_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
