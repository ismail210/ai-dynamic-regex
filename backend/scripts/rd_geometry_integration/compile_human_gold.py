"""Write Burrville human-gold outcomes into the existing review-kit schema (R&D only)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
ROWS_PATH = ROOT / "docs/validation/rd_geometry_integration/g1_rows.jsonl"
KIT = ROOT / "docs/validation/rd_geometry_integration/review_kit"
RENDERS = ROOT / "docs/validation/rd_geometry_integration/renders"

REVIEWER = "human_gold_rd"

# token_id -> (geometry_id, reason, error_bucket or None, leader_required)
ASSOCIATED: Dict[str, Tuple[str, str, Optional[str], bool]] = {
    "token_p8_340": (
        "geom_095898d74240",
        "Label sits on the W21X44[50] wall beam; the selected candidate overlay matches that wall segment.",
        None,
        False,
    ),
    "token_p8_395": (
        "geom_cf1c1b4a4515",
        "Label sits on W16X31[24] along the expansion-joint wall; the green overlay matches that wall line, not a neighboring joist.",
        None,
        False,
    ),
    "token_p8_396": (
        "geom_0b5ef1f9c497",
        "Label sits on the upper W16X31[24] along the expansion-joint wall; the green overlay matches that wall line.",
        None,
        False,
    ),
    "token_p8_397": (
        "geom_90463060295d",
        "Label is placed on the W12X19[20] infill; production and R&D overlays both match that infill segment.",
        None,
        False,
    ),
    "token_p8_398": (
        "geom_485e0c733148",
        "Label is placed on the W12X16[14] infill; the overlay matches that infill, not the adjacent W14X22 or W10X15 joists.",
        None,
        False,
    ),
    "token_p8_421": (
        "geom_5f6b0423ca08",
        "Label is placed on the W14X22[30] infill; the overlay matches that infill member.",
        None,
        False,
    ),
    "token_p8_427": (
        "geom_edbfa26d671d",
        "Label sits on the W21X44[50] retaining-wall beam; the overlay follows that wall stroke.",
        None,
        False,
    ),
    "token_p8_432": (
        "geom_edbfa26d671d",
        "Label sits on W16X26[18] on the same extracted wall stroke as token_p8_427. Associated to the existing primitive; no split was invented.",
        None,
        False,
    ),
}

AMBIGUOUS: Dict[str, Tuple[str, str]] = {
    "token_p8_367": (
        "Label sits at a crowded opening/stair node among W12X16[12], W14X22, and the W12X16[14] infill. The overlay is the neighboring infill. Multiple members remain plausible; no unique target.",
        "crowded_neighborhood",
    ),
    "token_p8_424": (
        "W16X26[20] at the wall kink: text lies on the wall beam while a small infill triangle is immediately adjacent. Wall-beam vs infill cannot be uniquely decided from the crop.",
        "crowded_neighborhood",
    ),
}

SCHEDULE = {
    "token_p18_1143": "W10X33 is STEEL COLUMN SPLICE table text (W10X33 TO W10X112), not a member callout. Orange overlay is a table/detail line, not a column.",
    "token_p18_1144": "W10X112 is the second line of a splice-schedule cell, not a member on geometry.",
    "token_p18_1145": "W12X40 is splice-schedule table text. Orange overlay is the generic column-splice diagram, not this schedule row.",
    "token_p18_1148": "W12X230 is splice-schedule table text, not a member callout.",
    "token_p18_1149": "W12X252 is splice-schedule table text, not a member callout.",
    "token_p18_1150": "W12X336 is splice-schedule table text, not a member callout.",
    "token_p18_1151": "W14X43 is splice-schedule table text, not a member callout.",
}

P18_LEADER_MISS = {
    "token_p18_1162": "Leader points to the splice plate on the WF column. Retrieved candidates are a dimension line and column outlines, not the plate.",
    "token_p18_1169": "Leader points to the cap plate on the HSS/WF detail. Overlays are beam/weld lines, not the plate rectangle.",
    "token_p18_1173": "Leader points to the cap plate on the HSS-or-pipe detail. Overlay is a lower flange/dimension stroke, not the plate.",
    "token_p18_1178": "Leader points to the bottom-flange L4X4X1/4 brace. Zero candidates retrieved for that brace.",
    "token_p18_1180": "Leader points to the cross-brace. Green overlay is the 1\" MAX TYP dimension box, not the brace.",
    "token_p18_1186": "Leader points to the WT under the beam. Green overlay is the W-beam top flange / roof deck, not the WT.",
    "token_p18_1188": "Leader points to the embed plate. Green overlay is studs/rebar left of the plate, not the embed plate.",
}

P24_LEADER_MISS = {
    "token_p24_1359": "Leader points to the small L6 relieving angle at the brick/slab. Green overlay is the long brick-hatch wall line.",
    "token_p24_1360": "Leader points to the small L4x4 at the roof/wall junction. Green overlay is the long wall face, not the angle.",
    "token_p24_1361": "Leader points to the L4X4X3/8 hanger at the joist bottom chord. Green overlay is a joist-web panel, not the hanger.",
    "token_p24_1362": "Leader points to the small angle at the curtain-wall/column. Green overlay is still the joist-web panel.",
    "token_p24_1370": "Leader points to the short L4X3 clip at the 4\" brick/slab. Green overlay is the roof-wall line (the L4x4 CONT member), not this clip.",
    "token_p24_1377": "Leader points to the small L4x4 DSA on the deck. Green overlay is a remote break-line, not the L.",
    "token_p24_1378": "Leader points to the L4X4X3/8 DSA on the roof deck. Green overlay is the long wall face, not the angle.",
    "token_p24_1379": "Leader points to the L4x4 DSA at the deck/wall. Green overlay is the long wall line.",
    "token_p24_1385": "Leader points to the L4x4 at the deck/wall. Green overlay is a hatch/diagonal in the wall, not the angle.",
    "token_p24_1387": "Leader points to the L4x4 at the deck/wall. Green overlay is a wall-hatch diagonal, not the angle.",
    "token_p24_1389": "Leader points to the short L3X3 clip on the HSS. Green overlay is the long HSS/wall line.",
}

P8_MISS_REASONS: Dict[str, str] = {
    "token_p8_332": "Label sits on W14X22[25] at the opening frame. Overlay is an X-brace inside the opening, not the W14X22 edge.",
    "token_p8_336": "Label sits on the W21X50 girder. Overlays are a distant infill and a stair stroke, not the girder.",
    "token_p8_337": "Label sits on the upper W21X44[30] girder. Candidates are a giant bay polyline / EJ wall, not this girder segment.",
    "token_p8_338": "Label sits on the lower W21X44[30] girder. Candidates are a giant bay polyline, not this girder segment.",
    "token_p8_341": "Label sits on W16X26[30] c=1\" joist. Green is the W16X31 EJ wall; orange is the W21X44 wall beam.",
    "token_p8_343": "Label sits on W16X26[30] c=1\" joist. Overlays are a distant infill and the W21X44 wall, not this joist.",
    "token_p8_345": "Label sits on W10X15[9] between the two W21X44 girders. No candidate is that short joist.",
    "token_p8_346": "Label sits on W10X15[9] between the two W21X44 girders. No candidate is that short joist.",
    "token_p8_347": "Label sits on W16X26[28] joist. Green is the S-311 callout; orange is a giant bay polyline.",
    "token_p8_348": "Label sits on the W30X90 girder. Green is the S-311 area; production is a giant bay polyline. The W30 stroke was not retrieved.",
    "token_p8_351": "Label sits on W18X35[38] joist. Green follows the SOG/wall line, not this joist among parallel W18s.",
    "token_p8_352": "Label sits on W16X26[10] girder. Green is S-311/S-401; orange is a giant polyline.",
    "token_p8_353": "Label sits on a W18X35 joist among parallel W18s. Green is the W21X44 wall; orange is the W12X16 infill.",
    "token_p8_354": "Label sits on W18X35[32] joist. Overlays are a distant infill and the W21X44 wall.",
    "token_p8_355": "Label sits on W10X15[9]. Zero R&D candidates; production is a giant bay polyline far to the right.",
    "token_p8_356": "Label sits on W16X26[20] girder. Overlays are the W14X22 and W12X16 infills, not the girder.",
    "token_p8_359": "Label sits on W18X40[40] among parallel W18X40s. Green is the SOG/wall line.",
    "token_p8_361": "Label sits on W16X26[30] c=1\" joist. Green is W16X31 at the EJ; orange is a tall wall box.",
    "token_p8_363": "Label sits on a W16X26 joist. Only candidate is a giant bay polyline to the right, not this joist.",
    "token_p8_368": "Label sits on W10X15[9]. Green is the W14X22 infill; orange is the stair.",
    "token_p8_369": "Label sits on W16X26[30] c=3/4\" joist. Overlay is the W21X44 wall beam.",
    "token_p8_371": "Label sits on W10X15[9]. Overlay is the W14X22 infill.",
    "token_p8_372": "Label sits on W10X15[9]. Green is the W14X22 infill; orange is the stair. The joist was not retrieved.",
    "token_p8_381": "Label sits on W18X35[35] joist among parallel W18s. Overlay is the W21X44 wall beam.",
    "token_p8_382": "Label sits on W18X35[34] joist. Overlay is the SOG/wall line.",
    "token_p8_383": "Label sits on W18X35[34] joist. Green is S-311; orange is a giant bay polyline.",
    "token_p8_384": "Label sits on W18X40[40] among parallel W18X40s. Overlay is the SOG/wall line.",
    "token_p8_386": "Label sits on W18X40[40] among parallel W18X40s. Orange is a giant bay polyline.",
    "token_p8_392": "Label sits on W18X40[44]. Green is a large pour-stop/region polyline covering several parallel W18s, not this joist.",
    "token_p8_394": "Label sits on W12X16 at the EJ between the two W21X44 girders. No candidate overlay matches that short wall segment.",
    "token_p8_399": "Label sits on W10X15[9]. Green is the W14X22 infill; orange is the stair.",
    "token_p8_407": "Label sits on W12X16[12] at the opening frame. Overlay is an X-brace inside the opening.",
    "token_p8_410": "Label sits on W10X15[10] at the wall. Green is W16X31; orange is the W21X44 wall.",
    "token_p8_411": "Label sits on W10X15[10] at the wall. Overlay is W16X31 at the EJ.",
    "token_p8_412": "Label sits on W10X15[10] at the wall. Overlay is W16X31 at the EJ.",
    "token_p8_416": "Label sits on W12X19[18] at the stair. Overlay is a large stair triangle below, not that short member.",
    "token_p8_419": "Label sits on W16X26[30] c=3/4\" joist. Overlay is the wall beam / a neighboring infill.",
    "token_p8_430": "Label sits on W18X35[28] joist among parallel W18s. Overlay is the W21X44 wall beam.",
    "token_p8_431": "Label sits on W18X35[34] joist among parallel W18s. Overlay is the W21X44 wall beam.",
    "token_p8_433": "Label sits on the W16X26[12] X-infilled member. Overlay is the bent-plate pour-stop region, not that infill.",
}


def _bucket_for_no_valid(token_id: str) -> str:
    if token_id in SCHEDULE:
        return "schedule_table_not_member"
    if token_id in P18_LEADER_MISS or token_id in P24_LEADER_MISS:
        return "missing_retrieval"
    if token_id == "token_p8_355":
        return "missing_retrieval"
    if token_id in {
        "token_p8_351",
        "token_p8_359",
        "token_p8_384",
        "token_p8_386",
        "token_p8_381",
        "token_p8_382",
        "token_p8_383",
        "token_p8_430",
        "token_p8_431",
        "token_p8_341",
        "token_p8_343",
        "token_p8_354",
        "token_p8_361",
        "token_p8_369",
        "token_p8_419",
        "token_p8_392",
    }:
        return "parallel_member_confusion"
    if token_id in {
        "token_p8_332",
        "token_p8_407",
        "token_p8_416",
        "token_p8_348",
        "token_p8_353",
        "token_p8_372",
        "token_p8_336",
        "token_p8_337",
        "token_p8_338",
        "token_p8_356",
        "token_p8_399",
        "token_p8_368",
        "token_p8_371",
        "token_p8_345",
        "token_p8_346",
        "token_p8_347",
        "token_p8_352",
        "token_p8_363",
        "token_p8_394",
        "token_p8_410",
        "token_p8_411",
        "token_p8_412",
        "token_p8_433",
    }:
        return "missing_retrieval"
    return "missing_retrieval"


def _leader_required_no_valid(token_id: str) -> bool:
    return token_id in P18_LEADER_MISS or token_id in P24_LEADER_MISS


def load_rows() -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for line in ROWS_PATH.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rows[str(rec["token_id"])] = rec
    return rows


def build_record(row: Dict[str, Any]) -> Dict[str, Any]:
    token_id = str(row["token_id"])
    cands = row.get("new_candidates") or []
    cand_ids = [c.get("geometry_id") for c in cands if c.get("geometry_id")]
    prod_id = (row.get("current_association") or {}).get("geometry_id")
    crop = f"renders/assoc_{token_id}.png"
    crop_exists = (RENDERS / f"assoc_{token_id}.png").exists()
    base = {
        "token_id": token_id,
        "page": row.get("page"),
        "text": row.get("text"),
        "label_bbox": row.get("label_bbox"),
        "production_geometry_id": prod_id,
        "candidate_geometry_ids": cand_ids,
        "reviewer_id": REVIEWER,
        "review_source": "human_gold",
        "crop": crop,
        "crop_available": crop_exists,
        "g1_status": row.get("status"),
    }
    if not crop_exists:
        base.update(
            {
                "review_label": "unavailable",
                "decision": "unavailable",
                "reviewed_target_geometry_ids": [],
                "selected_geometry_id": None,
                "reason": "Association crop is missing; visual decision not made from JSON alone.",
                "error_bucket": "unavailable_evidence",
                "leader_required": False,
            }
        )
        return base
    if token_id in ASSOCIATED:
        gid, reason, bucket, leader = ASSOCIATED[token_id]
        if gid not in cand_ids:
            raise SystemExit(f"{token_id}: selected {gid} not in candidates {cand_ids}")
        base.update(
            {
                "review_label": "direct_target",
                "decision": "associated",
                "reviewed_target_geometry_ids": [gid],
                "selected_geometry_id": gid,
                "reason": reason,
                "error_bucket": bucket,
                "leader_required": leader,
                "association_mode": "direct",
            }
        )
        return base
    if token_id in AMBIGUOUS:
        reason, bucket = AMBIGUOUS[token_id]
        base.update(
            {
                "review_label": "ambiguous_requires_adjudication",
                "decision": "ambiguous",
                "reviewed_target_geometry_ids": [],
                "selected_geometry_id": None,
                "reason": reason,
                "error_bucket": bucket,
                "leader_required": False,
            }
        )
        return base
    if token_id in SCHEDULE:
        reason = SCHEDULE[token_id]
    elif token_id in P18_LEADER_MISS:
        reason = P18_LEADER_MISS[token_id]
    elif token_id in P24_LEADER_MISS:
        reason = P24_LEADER_MISS[token_id]
    elif token_id in P8_MISS_REASONS:
        reason = P8_MISS_REASONS[token_id]
    else:
        raise SystemExit(f"No decision for {token_id}")
    base.update(
        {
            "review_label": "no_valid_target",
            "decision": "no_valid_member",
            "reviewed_target_geometry_ids": [],
            "selected_geometry_id": None,
            "reason": reason,
            "error_bucket": _bucket_for_no_valid(token_id),
            "leader_required": _leader_required_no_valid(token_id),
            "visible_member_on_drawing": token_id not in SCHEDULE,
        }
    )
    return base


def recall_at_k(records: List[Dict[str, Any]], k: int) -> Optional[float]:
    associated = [r for r in records if r["decision"] == "associated"]
    if not associated:
        return None
    hits = 0
    for rec in associated:
        gid = rec.get("selected_geometry_id")
        ids = list(rec.get("candidate_geometry_ids") or [])[:k]
        if gid in ids:
            hits += 1
    return hits / len(associated)


def metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(r["decision"] for r in records)
    associated = [r for r in records if r["decision"] == "associated"]
    n_assoc = len(associated)
    prod_match = sum(
        1
        for r in associated
        if r.get("selected_geometry_id") and r.get("selected_geometry_id") == r.get("production_geometry_id")
    )
    rd_top1 = sum(
        1
        for r in associated
        if r.get("candidate_geometry_ids") and r["candidate_geometry_ids"][0] == r.get("selected_geometry_id")
    )
    visible_missing = sum(
        1
        for r in records
        if r["decision"] == "no_valid_member" and r.get("visible_member_on_drawing", True) and r.get("error_bucket") != "schedule_table_not_member"
    )
    schedule_n = sum(1 for r in records if r.get("error_bucket") == "schedule_table_not_member")
    buckets = Counter(r.get("error_bucket") for r in records if r.get("error_bucket"))
    disagreement_tokens = [r["token_id"] for r in records if r.get("g1_status") == "disagreement"]
    leader_assoc = sum(1 for r in associated if r.get("leader_required"))
    leader_miss = sum(1 for r in records if r.get("leader_required") and r["decision"] == "no_valid_member")
    return {
        "n_reviewed": len(records),
        "decision_counts": dict(counts),
        "n_associated": n_assoc,
        "n_ambiguous": counts.get("ambiguous", 0),
        "n_no_valid_member": counts.get("no_valid_member", 0),
        "n_unavailable": counts.get("unavailable", 0),
        "n_schedule_not_member": schedule_n,
        "n_visible_member_missing_from_candidates": visible_missing,
        "recall_at_1": recall_at_k(records, 1),
        "recall_at_3": recall_at_k(records, 3),
        "recall_at_5": recall_at_k(records, 5),
        "recall_denominator": n_assoc,
        "production_match_among_associated": prod_match,
        "production_match_rate_among_associated": (prod_match / n_assoc) if n_assoc else None,
        "rd_top1_match_among_associated": rd_top1,
        "rd_top1_rate_among_associated": (rd_top1 / n_assoc) if n_assoc else None,
        "g1_disagreement_tokens": disagreement_tokens,
        "leader_required_associated": leader_assoc,
        "leader_required_no_valid_member": leader_miss,
        "error_buckets": dict(buckets),
        "note": (
            "Recall@K is among human-associated labels only. "
            "no_valid_member / ambiguous / unavailable are excluded from the denominator. "
            "Production nearest_geometry is a reference, not ground truth."
        ),
    }


def qc(records: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    ids = [r["token_id"] for r in records]
    if len(records) != 75:
        errors.append(f"expected 75 records, got {len(records)}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate token_id")
    for rec in records:
        dec = rec["decision"]
        sel = rec.get("selected_geometry_id")
        targets = rec.get("reviewed_target_geometry_ids") or []
        if dec == "associated":
            if not sel:
                errors.append(f"{rec['token_id']}: associated without selected geometry")
            if sel not in (rec.get("candidate_geometry_ids") or []):
                errors.append(f"{rec['token_id']}: selected geometry not in candidates")
            if targets != [sel]:
                errors.append(f"{rec['token_id']}: target list mismatch")
        else:
            if sel:
                errors.append(f"{rec['token_id']}: {dec} has selected geometry")
            if targets:
                errors.append(f"{rec['token_id']}: {dec} has target ids")
        if rec["review_label"] == "direct_target" and dec != "associated":
            errors.append(f"{rec['token_id']}: review_label/decision mismatch")
        if rec["review_label"] == "no_valid_target" and dec != "no_valid_member":
            errors.append(f"{rec['token_id']}: review_label/decision mismatch")
        if rec["review_label"] == "ambiguous_requires_adjudication" and dec != "ambiguous":
            errors.append(f"{rec['token_id']}: review_label/decision mismatch")
        if rec["review_label"] == "unavailable" and dec != "unavailable":
            errors.append(f"{rec['token_id']}: review_label/decision mismatch")
    return errors


def main() -> None:
    rows = load_rows()
    if len(rows) != 75:
        raise SystemExit(f"expected 75 g1 rows, got {len(rows)}")
    covered = set(ASSOCIATED) | set(AMBIGUOUS) | set(SCHEDULE) | set(P18_LEADER_MISS) | set(P24_LEADER_MISS) | set(P8_MISS_REASONS)
    missing = sorted(set(rows) - covered)
    extra = sorted(covered - set(rows))
    if missing or extra:
        raise SystemExit(f"decision coverage gap missing={missing} extra={extra}")
    records = [build_record(rows[tid]) for tid in sorted(rows, key=lambda t: (rows[t].get("page") or 0, t))]
    problems = qc(records)
    if problems:
        raise SystemExit("QC failed:\n" + "\n".join(problems))
    decisions_dir = KIT / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    for rec in records:
        (decisions_dir / f"{rec['token_id']}.decision.json").write_text(json.dumps(rec, indent=2) + "\n")
    (KIT / "gold_outcomes.jsonl").write_text("".join(json.dumps(rec) + "\n" for rec in records))
    summary = metrics(records)
    summary["qc"] = {"ok": True, "n": len(records)}
    (KIT / "gold_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
