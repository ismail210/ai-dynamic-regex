#!/usr/bin/env python3
"""Run CURRENT production extraction vs human extraction gold (isolated).

Does not modify production flags/code. Captures intermediates by calling
existing public helpers separately (structure parse vs full extract).

Usage (from backend/):
  python scripts/extraction_gold_eval/run_eval.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.annotation.fragment_grouper import group_annotation_fragments  # noqa: E402
from services.extraction_engine import extract_engineering_document  # noqa: E402
from services.pdf_parser import extract_document_structure  # noqa: E402
from services.token_extractor import (  # noqa: E402
    canonical_extracted_token,
    normalize_engineering_token,
)

ART = Path(__file__).resolve().parent / "artifacts"
GOLD_PATH = ART / "extraction_gold.json"


def safe_norm(text: str) -> str:
    """Safe formatting-only normalize for matching (case/x/whitespace)."""
    return normalize_engineering_token(text)


def match_keys(text: str) -> set[str]:
    """Matching keys: raw safe-norm + canonical (does not equate L4X4 to L4X4X1/4)."""
    n = safe_norm(text)
    keys = {n, n.replace("-", "")}
    try:
        c = canonical_extracted_token(text)
        if c:
            keys.add(safe_norm(c))
            keys.add(safe_norm(c).replace("-", ""))
    except Exception:
        pass
    return {k for k in keys if k}


def token_page(tok: dict) -> int:
    pn = tok.get("page_number")
    if pn in (None, 0, "0"):
        pn = tok.get("page")
    return int(pn or 0)


def token_text(tok: dict) -> str:
    return str(
        tok.get("normalized")
        or tok.get("text")
        or tok.get("raw_text")
        or tok.get("canonical")
        or ""
    )


def index_tokens(tokens: list[dict], pages: set[int] | None = None) -> dict[tuple[int, str], list[dict]]:
    idx: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for tok in tokens:
        pn = token_page(tok)
        if pages is not None and pn not in pages:
            continue
        for k in match_keys(token_text(tok)):
            idx[(pn, k)].append(tok)
    return idx


def find_match(idx: dict, page: int, gold_norm: str) -> list[dict]:
    keys = match_keys(gold_norm)
    # Also try hyphen-stripped gold for C-1 vs C1
    found: list[dict] = []
    seen = set()
    for k in keys:
        for tok in idx.get((page, k), []):
            tid = id(tok)
            if tid not in seen:
                seen.add(tid)
                found.append(tok)
    return found


def classify_fn(
    gold: dict,
    *,
    raw_idx: dict,
    grouped_idx: dict,
    filtered_idx: dict,
    page_text: str,
) -> str:
    """Attribute FN / usable-miss to stage A–G."""
    page = gold["page"]
    gn = gold["normalized"]
    in_filtered = find_match(filtered_idx, page, gn)
    if in_filtered:
        tok = in_filtered[0]
        if tok.get("takeoff_eligible") is False:
            return "CONTEXT_DEMOTION"
        return "NORMALIZATION_MISMATCH"

    in_grouped = find_match(grouped_idx, page, gn)
    in_raw = find_match(raw_idx, page, gn)

    # Present after regex extract, dropped by fragment grouping
    if in_raw and not in_grouped:
        return "TOKENIZATION_MISS"

    # Survived grouping, removed by engineering-object filter
    if in_grouped and not in_filtered:
        return "FILTER_MISS"

    page_u = (page_text or "").upper().replace("×", "X")
    gn_u = gn.upper()
    gn_flex = gn_u.replace("-", "")
    compact_page = page_u.replace(" ", "").replace("-", "")
    present = gn_u.replace("-", "") in compact_page
    spaced2 = re.sub(r"X", " X ", gn_u)
    frag_present = spaced2 in page_u

    if frag_present and not present:
        return "TOKENIZATION_MISS"
    if present or gold.get("source"):
        # hyphenated marks (C-1) visible but never tokenized
        return "RAW_EXTRACTION_MISS"
    return "UNKNOWN"


def run() -> dict:
    gold = json.loads(GOLD_PATH.read_text())
    rows = gold["rows"]
    docs = {d["document_id"]: d for d in gold["documents"]}

    # Group gold pages per doc
    gold_by_doc: dict[str, list] = defaultdict(list)
    for r in rows:
        gold_by_doc[r["document_id"]].append(r)

    per_doc_results = {}
    all_tp = []
    all_fn = []
    all_fp_tokens = []  # unmatched extracted on gold pages
    clbp_rows = []
    incomplete_rows = []
    demotion_details = []

    for doc_id, g_rows in gold_by_doc.items():
        meta = docs[doc_id]
        path = meta["path"]
        pages = set(meta["gold_pages"])
        print(f"\n=== Extracting {meta['document_name']} ({path}) ===", flush=True)

        # Pre-filter raw structure tokens
        structure = extract_document_structure(path)
        raw_tokens = list(structure.get("engineering_tokens") or [])

        # Full production extraction path
        document = extract_engineering_document(path, document_id=f"eval_{doc_id}")
        eng_tokens = list(document.get("engineering_tokens") or [])
        discard = document.get("extraction_discard_counts") or {}
        ctx_summary = document.get("context_scope_summary") or {}

        # Page texts for attribution
        page_texts = {
            int(p.get("page_number") or p.get("page") or 0): str(p.get("text") or "")
            for p in (document.get("pages") or structure.get("pages") or [])
        }

        grouped_tokens = group_annotation_fragments(list(raw_tokens))
        raw_idx = index_tokens(raw_tokens, pages)
        grouped_idx = index_tokens(grouped_tokens, pages)
        filt_idx = index_tokens(eng_tokens, pages)

        # Usable = takeoff_eligible != False
        usable = [t for t in eng_tokens if t.get("takeoff_eligible") is not False]
        usable_idx = index_tokens(usable, pages)

        matched_token_ids: set[int] = set()
        doc_tp, doc_fn = [], []

        for g in g_rows:
            page = g["page"]
            # Primary extraction match: any post-filter engineering token
            hits = find_match(filt_idx, page, g["normalized"])
            usable_hits = find_match(usable_idx, page, g["normalized"])

            extraction_hit = bool(hits)
            usable_hit = bool(usable_hits)

            record = {
                **{k: g[k] for k in (
                    "gold_id", "document_id", "document", "page", "raw_text",
                    "normalized", "category", "kind", "ambiguity_flag",
                    "incomplete_angle", "context",
                )},
                "extraction_matched": extraction_hit,
                "usable_matched": usable_hit,
                "matched_token_id": None,
                "matched_token_text": None,
                "object_scope": None,
                "takeoff_eligible": None,
                "failure_stage": None,
            }

            if extraction_hit:
                tok = hits[0]
                matched_token_ids.add(id(tok))
                # mark all hit tokens as matched for FP calc
                for t in hits:
                    matched_token_ids.add(id(t))
                record["matched_token_id"] = tok.get("object_id") or tok.get("token_id")
                record["matched_token_text"] = token_text(tok)
                record["object_scope"] = tok.get("object_scope")
                record["takeoff_eligible"] = tok.get("takeoff_eligible")
                if not usable_hit:
                    record["failure_stage"] = "CONTEXT_DEMOTION"
                    demotion_details.append(
                        {
                            "page": page,
                            "document": g["document"],
                            "raw": g["normalized"],
                            "token_id": record["matched_token_id"],
                            "object_scope": tok.get("object_scope"),
                            "takeoff_eligible": tok.get("takeoff_eligible"),
                            "why": tok.get("scope_reason")
                            or tok.get("demotion_reason")
                            or tok.get("object_scope"),
                            "raw_token_exists": True,
                        }
                    )
                doc_tp.append(record)
                all_tp.append(record)
            else:
                stage = classify_fn(
                    g,
                    raw_idx=raw_idx,
                    grouped_idx=grouped_idx,
                    filtered_idx=filt_idx,
                    page_text=page_texts.get(page, ""),
                )
                # If classify said CONTEXT but no token — reclassify
                if stage == "CONTEXT_DEMOTION" and not hits:
                    stage = "RAW_EXTRACTION_MISS"
                record["failure_stage"] = stage
                doc_fn.append(record)
                all_fn.append(record)

            # C/L/CL/BP special table
            cat = g["category"]
            if cat in (
                "annotation_C", "annotation_L", "annotation_CL", "annotation_BP",
            ) or (
                cat == "member_mark" and re.match(r"^(?:C|L)-?\d", g["normalized"])
            ) or re.match(r"^(?:BP|CL)-?\d", g["normalized"]):
                resolved = None
                # resolution is downstream — check schedule-related fields if present
                if hits:
                    tok = hits[0]
                    resolved = (
                        tok.get("resolved_section")
                        or tok.get("resolved_size")
                        or tok.get("mark_resolution")
                        or tok.get("section")
                    )
                clbp_rows.append(
                    {
                        "document": g["document"],
                        "page": page,
                        "raw": g["raw_text"],
                        "expected": g["normalized"],
                        "extracted": record["matched_token_text"],
                        "resolved": resolved,
                        "final_scope": record["object_scope"],
                        "takeoff_eligible": record["takeoff_eligible"],
                        "correct_raw_extraction": extraction_hit,
                        "failure_stage": record["failure_stage"]
                        if not extraction_hit
                        else (
                            "CONTEXT_DEMOTION"
                            if record["failure_stage"] == "CONTEXT_DEMOTION"
                            else "OK"
                        ),
                    }
                )

            if g.get("incomplete_angle"):
                incomplete_rows.append(record)

        # False positives: eng tokens on gold pages whose text doesn't match any gold
        gold_keys_by_page: dict[int, set[str]] = defaultdict(set)
        for g in g_rows:
            for k in match_keys(g["normalized"]):
                gold_keys_by_page[g["page"]].add(k)

        fp_list = []
        for tok in eng_tokens:
            pn = token_page(tok)
            if pn not in pages:
                continue
            text = token_text(tok)
            keys = match_keys(text)
            if keys & gold_keys_by_page.get(pn, set()):
                continue
            # classify FP
            n = safe_norm(text)
            fp_class = "other"
            if re.match(r"^S-\d+", n):
                fp_class = "sheet_reference"
            elif re.match(r"^(?:A|F)\d{3}", n):
                fp_class = "material_grade_or_note"
            elif re.search(r"\d+['’]\-", n) or re.search(r"\d+/\d+", n) and not re.match(
                r"^(?:W|HSS|L|2L|C|PL|PIPE|BP|CL)", n
            ):
                fp_class = "dimension_feet_inch_contamination"
            elif re.match(r"^(?:BP|CL|L|C)-?\d", n):
                fp_class = "annotation_or_mark_omitted_from_gold"
            elif re.match(r"^(?:W|WT|HSS|L|2L|C|MC|PL|PIPE)", n):
                fp_class = "legitimate_steel_omitted_from_gold"
            elif "BENT" in n or "PLATE" in n:
                fp_class = "annotation"
            else:
                fp_class = "regex_false_positive_or_other"

            fp_list.append(
                {
                    "document_id": doc_id,
                    "page": pn,
                    "text": text,
                    "normalized": n,
                    "token_id": tok.get("object_id"),
                    "takeoff_eligible": tok.get("takeoff_eligible"),
                    "object_scope": tok.get("object_scope"),
                    "fp_class": fp_class,
                }
            )
        all_fp_tokens.extend(fp_list)

        # Metrics — EXTRACTION (token exists) and USABLE
        tp_e = len(doc_tp)
        fn_e = len(doc_fn)
        # FP for extraction: unique norms on page not in gold
        fp_e = len(fp_list)
        prec_e = tp_e / (tp_e + fp_e) if (tp_e + fp_e) else 0.0
        rec_e = tp_e / (tp_e + fn_e) if (tp_e + fn_e) else 0.0
        f1_e = (2 * prec_e * rec_e / (prec_e + rec_e)) if (prec_e + rec_e) else 0.0

        # Usable-view: demoted TPs become FN
        tp_u = sum(1 for r in doc_tp if r.get("takeoff_eligible") is not False)
        fn_u = fn_e + sum(1 for r in doc_tp if r.get("takeoff_eligible") is False)
        fp_u = sum(1 for f in fp_list if f.get("takeoff_eligible") is not False)
        prec_u = tp_u / (tp_u + fp_u) if (tp_u + fp_u) else 0.0
        rec_u = tp_u / (tp_u + fn_u) if (tp_u + fn_u) else 0.0
        f1_u = (2 * prec_u * rec_u / (prec_u + rec_u)) if (prec_u + rec_u) else 0.0

        per_doc_results[doc_id] = {
            "document": meta["document_name"],
            "pages": meta["page_count"],
            "gold_pages": meta["gold_pages"],
            "gold": len(g_rows),
            "extraction": {
                "tp": tp_e,
                "fn": fn_e,
                "fp": fp_e,
                "precision": round(prec_e, 4),
                "recall": round(rec_e, 4),
                "f1": round(f1_e, 4),
            },
            "usable": {
                "tp": tp_u,
                "fn": fn_u,
                "fp": fp_u,
                "precision": round(prec_u, 4),
                "recall": round(rec_u, 4),
                "f1": round(f1_u, 4),
            },
            "raw_token_count": len(raw_tokens),
            "engineering_token_count": len(eng_tokens),
            "discard_counts": discard,
            "context_scope_summary": ctx_summary,
            "extraction_version": document.get("extraction_version"),
        }
        print(
            f"  gold={len(g_rows)} extract TP/FN/FP={tp_e}/{fn_e}/{fp_e} "
            f"R={rec_e:.3f} P={prec_e:.3f} | usable R={rec_u:.3f}",
            flush=True,
        )

        # persist per-doc token dump (gold pages only) for audit
        slim = [
            {
                "object_id": t.get("object_id"),
                "page": token_page(t),
                "text": token_text(t),
                "takeoff_eligible": t.get("takeoff_eligible"),
                "object_scope": t.get("object_scope"),
            }
            for t in eng_tokens
            if token_page(t) in pages
        ]
        (ART / f"tokens_{doc_id}.json").write_text(json.dumps(slim, indent=2))

    # Overall extraction metrics
    tp = len(all_tp)
    fn = len(all_fn)
    fp = len(all_fp_tokens)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0

    # Usable overall
    demoted_tps = [r for r in all_tp if r.get("takeoff_eligible") is False]
    tp_u = tp - len(demoted_tps)
    fn_u = fn + len(demoted_tps)
    fp_u = sum(1 for f in all_fp_tokens if f.get("takeoff_eligible") is not False)
    prec_u = tp_u / (tp_u + fp_u) if (tp_u + fp_u) else 0.0
    rec_u = tp_u / (tp_u + fn_u) if (tp_u + fn_u) else 0.0
    f1_u = (2 * prec_u * rec_u / (prec_u + rec_u)) if (prec_u + rec_u) else 0.0

    # FN stages: for usable-view FNs = extraction FNs + demoted
    stage_counts = Counter(r["failure_stage"] for r in all_fn)
    stage_counts["CONTEXT_DEMOTION"] = stage_counts.get("CONTEXT_DEMOTION", 0) + len(demoted_tps)

    # Per-category extraction
    cat_stats = {}
    by_cat = defaultdict(list)
    for r in all_tp + all_fn:
        by_cat[r["category"]].append(r)
    for cat, items in by_cat.items():
        c_tp = sum(1 for r in items if r["extraction_matched"])
        c_fn = sum(1 for r in items if not r["extraction_matched"])
        cat_stats[cat] = {
            "n": len(items),
            "tp": c_tp,
            "fn": c_fn,
            "recall": round(c_tp / (c_tp + c_fn), 4) if (c_tp + c_fn) else None,
        }

    # Broad buckets
    def bucket(cat: str) -> str:
        if cat == "section_designation":
            return "W_wide_flange_and_sections"
        if cat == "channel":
            return "C_channel"
        if cat == "HSS":
            return "HSS"
        if cat == "angle_designation":
            return "L_2L"
        if cat == "plate":
            return "PL"
        if cat == "annotation_BP":
            return "BP"
        if cat == "annotation_CL":
            return "CL"
        if cat == "annotation_C":
            return "bare_C"
        if cat == "annotation_L":
            return "bare_L"
        if cat == "member_mark":
            return "member_marks"
        return cat

    bucket_stats = {}
    by_b = defaultdict(list)
    for r in all_tp + all_fn:
        by_b[bucket(r["category"])].append(r)
    for b, items in by_b.items():
        c_tp = sum(1 for r in items if r["extraction_matched"])
        c_fn = sum(1 for r in items if not r["extraction_matched"])
        bucket_stats[b] = {
            "n": len(items),
            "tp": c_tp,
            "fn": c_fn,
            "recall": round(c_tp / (c_tp + c_fn), 4) if (c_tp + c_fn) else None,
        }

    fp_classes = Counter(f["fp_class"] for f in all_fp_tokens)
    steel_fp = [
        f for f in all_fp_tokens
        if f["fp_class"] not in (
            "dimension_feet_inch_contamination",
            "regex_false_positive_or_other",
        )
    ]
    # Steel-conditioned precision: ignore anonymous dimension FPs
    steel_fp_n = len(steel_fp)
    steel_prec = tp / (tp + steel_fp_n) if (tp + steel_fp_n) else 0.0

    report = {
        "schema": "extraction_gold_eval_report_v1",
        "primary_metric": "extraction_token_presence (post-filter engineering_tokens)",
        "overall_extraction": {
            "gold": tp + fn,
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        },
        "overall_usable": {
            "gold": tp_u + fn_u,
            "tp": tp_u,
            "fn": fn_u,
            "fp": fp_u,
            "precision": round(prec_u, 4),
            "recall": round(rec_u, 4),
            "f1": round(f1_u, 4),
            "context_demotions_of_extracted": len(demoted_tps),
        },
        "fn_breakdown_usable_view": dict(stage_counts),
        "fn_breakdown_extraction_only": dict(Counter(r["failure_stage"] for r in all_fn)),
        "per_document": per_doc_results,
        "per_category": cat_stats,
        "per_bucket": bucket_stats,
        "fp_classes": dict(fp_classes),
        "steel_conditioned_precision": {
            "fp_excluding_dimensions": steel_fp_n,
            "precision": round(steel_prec, 4),
            "note": "Precision after excluding anonymous dimension / weak regex FPs",
        },
        "demotion_details": demotion_details,
        "clbp_table": clbp_rows,
        "incomplete_l_rows": incomplete_rows,
        "fn_records": all_fn,
        "tp_records": [
            {k: r[k] for k in (
                "gold_id", "document_id", "page", "normalized", "category",
                "takeoff_eligible", "object_scope", "matched_token_id",
            )}
            for r in all_tp
        ],
        "fp_sample": all_fp_tokens[:80],
    }
    out = ART / "eval_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote report → {out}")
    print(
        f"OVERALL extraction R={rec:.3%} P={prec:.3%} F1={f1:.3%} "
        f"(TP={tp} FN={fn} FP={fp})"
    )
    print(
        f"OVERALL usable     R={rec_u:.3%} P={prec_u:.3%} F1={f1_u:.3%} "
        f"(demotions={len(demoted_tps)})"
    )
    print("FN stages (usable view):", dict(stage_counts))
    return report


if __name__ == "__main__":
    run()
