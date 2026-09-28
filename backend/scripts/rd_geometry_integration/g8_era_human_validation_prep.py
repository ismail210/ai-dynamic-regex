#!/usr/bin/env python3
"""G8-era human validation PREPARATION (R&D, isolated).

Builds a review manifest + schema + lightweight review HTML for the 27
false-association audit cases (21B + 5C + 1D) against the *frozen* G8
candidate universe.

Does NOT:
  - modify historical gold / gold_metrics
  - regenerate G8 or G9
  - collect human decisions (no new gold)
  - implement G10 / tune ranking

Usage (from backend/):
    python scripts/rd_geometry_integration/g8_era_human_validation_prep.py
"""

from __future__ import annotations

import hashlib
import html
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT.parent / "docs" / "validation" / "rd_geometry_integration"
AUDIT_DIR = OUT_ROOT / "g9_false_association_audit"
PREP_DIR = OUT_ROOT / "g8_era_human_validation"

GOLD_PATH = OUT_ROOT / "review_kit" / "gold_outcomes.jsonl"
GOLD_METRICS = OUT_ROOT / "review_kit" / "gold_metrics.json"
G8_PATH = OUT_ROOT / "representation_repair_g8_results.jsonl"
G9_PATH = OUT_ROOT / "association_shadow_g9_results.jsonl"
AUDIT_PATH = AUDIT_DIR / "g9_false_association_audit.jsonl"
AUDIT_SUMMARY = AUDIT_DIR / "g9_false_association_audit_summary.json"

EXPECTED_GOLD_SHA = (
    "0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155"
)
EXPECTED_G8_SHA = (
    "1931707165664d9e8e6ea198171624b9f9d8bb25dda2edd40d86619126ed3c44"
)
EXPECTED_G9_SHA = (
    "b459522eb097c285a359bd01a2be61c389daeded6415f236b6a0c47323cb4814"
)

EXPECTED_B = 21
EXPECTED_C = 5
EXPECTED_D = 1
EXPECTED_TOTAL = 27

MANIFEST_PATH = PREP_DIR / "g8_era_human_validation_manifest.jsonl"
SCHEMA_PATH = PREP_DIR / "g8_era_human_validation_schema.json"
SUMMARY_PATH = PREP_DIR / "g8_era_human_validation_summary.json"
PLAN_PATH = PREP_DIR / "G8_ERA_HUMAN_VALIDATION_PLAN.md"
REVIEW_HTML = PREP_DIR / "review.html"
DECISIONS_DIR = PREP_DIR / "decisions_pending"

# Map historical review_kit labels → proposed G8-era decision vocabulary (conceptual).
HISTORICAL_TO_PROPOSED = {
    "direct_target": "VALID_MEMBER",
    "no_valid_target": "NO_VALID_MEMBER",
    "ambiguous_requires_adjudication": "AMBIGUOUS",
    "unavailable": "NEEDS_REVIEW",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def review_priority(classification: str, confidence: str) -> str:
    if classification in {"C", "D"}:
        return "HIGH"
    if classification == "B" and confidence == "MEDIUM":
        return "MEDIUM"
    return "NORMAL"


def priority_rank(priority: str) -> int:
    return {"HIGH": 0, "MEDIUM": 1, "NORMAL": 2}.get(priority, 9)


def build_schema() -> Dict[str, Any]:
    """Proposed G8-era review decision schema (isolated; not production gold)."""
    return {
        "$schema_name": "g8_era_human_validation_decision",
        "version": "1.0-prep",
        "status": "PREPARATION_ONLY",
        "not_production_gold": True,
        "historical_gold_immutable": True,
        "description": (
            "Human ownership review against frozen G8 candidates. "
            "Collected later into decisions_pending/; never written into "
            "review_kit/gold_outcomes.jsonl by this preparation phase."
        ),
        "decision_vocabulary": {
            "VALID_MEMBER": {
                "meaning": "Exactly one G8 candidate is owned by this annotation",
                "requires": ["owned_candidate_ids"],
                "owned_candidate_ids_cardinality": 1,
                "maps_from_historical_review_label": "direct_target",
            },
            "NO_VALID_MEMBER": {
                "meaning": "No G8 candidate is the member owned by this annotation",
                "requires": ["reason"],
                "owned_candidate_ids_cardinality": 0,
                "maps_from_historical_review_label": "no_valid_target",
            },
            "AMBIGUOUS": {
                "meaning": "Multiple G8 candidates remain plausible; ownership not deterministic",
                "requires": ["owned_candidate_ids"],
                "owned_candidate_ids_cardinality": ">=2",
                "maps_from_historical_review_label": "ambiguous_requires_adjudication",
            },
            "NEEDS_REVIEW": {
                "meaning": "Crop/PDF evidence insufficient to decide",
                "requires": ["reason"],
                "owned_candidate_ids_cardinality": 0,
                "maps_from_historical_review_label": "unavailable",
            },
        },
        "ownership_evidence_hierarchy": [
            "explicit_label_to_member_relationship",
            "leader_endpoint_or_pointer",
            "overlap_or_contact",
            "text_vs_member_orientation",
            "local_structural_topology",
            "repeated_member_context",
            "distance_proximity_last",
        ],
        "explicit_non_signals": [
            "distance_alone",
            "section_size_alone",
            "G9_selected_candidate_is_not_auto_truth",
            "audit_class_B_is_not_auto_VALID_MEMBER",
            "historical_gold_decision_is_not_G8_era_truth",
        ],
        "required_fields_on_collected_decision": [
            "token_id",
            "page",
            "label",
            "historical_gold_decision",
            "audit_classification",
            "reviewer_decision",
            "owned_candidate_ids",
            "reviewer_confidence",
            "reviewer_id",
            "review_source",
            "notes",
            "reviewed_at",
        ],
        "field_definitions": {
            "token_id": "Stable label token id (e.g. token_p8_336)",
            "page": "PDF page number",
            "label": "Raw annotation text",
            "historical_gold_decision": "Immutable historical decision (usually no_valid_member)",
            "historical_gold_reason": "Immutable historical reason text",
            "audit_classification": "B|C|D from false-association audit",
            "g8_candidate_ids": "Frozen G8 B_candidate ids shown to reviewer",
            "g9_selected_candidate_id": "G9 ASSOCIATED pick (reference only)",
            "reviewer_decision": "VALID_MEMBER|NO_VALID_MEMBER|AMBIGUOUS|NEEDS_REVIEW",
            "owned_candidate_ids": "G8 candidate ids the reviewer marks as owned (0, 1, or many)",
            "reviewer_confidence": "HIGH|MEDIUM|LOW",
            "reviewer_id": "Human initials / id",
            "review_source": "Must be g8_era_human_validation (not human_gold)",
            "notes": "Free-text evidence notes",
            "reviewed_at": "ISO-8601 timestamp when collected later",
        },
        "example_blank_decision": {
            "token_id": "token_p8_336",
            "page": 8,
            "label": "W21X50",
            "historical_gold_decision": "NO_VALID_MEMBER",
            "historical_gold_reason": "(from gold_outcomes.jsonl)",
            "audit_classification": "B",
            "g8_candidate_ids": ["rnd_raw_..."],
            "g9_selected_candidate_id": "rnd_raw_...",
            "reviewer_decision": None,
            "owned_candidate_ids": [],
            "reviewer_confidence": None,
            "reviewer_id": None,
            "review_source": "g8_era_human_validation",
            "notes": "",
            "reviewed_at": None,
            "status": "PENDING",
        },
        "reuse_of_existing_architecture": {
            "review_kit_review_label": (
                "Historical kit uses direct_target / no_valid_target / "
                "ambiguous_requires_adjudication / unavailable — mapped above."
            ),
            "review_kit_gold_outcomes": "IMMUTABLE — do not append G8-era decisions there",
            "review_kit_html": (
                "Shows pre-G8 geom_* candidates; insufficient alone for G8 ownership review. "
                "Use this prep review.html + audit/G8/G9 renders instead."
            ),
            "decision_json_per_token": (
                "Same pattern as review_kit/decisions/*.decision.json, but under "
                "g8_era_human_validation/decisions_pending/ when humans later collect."
            ),
        },
    }


def build_manifest_row(
    audit: Dict[str, Any],
    gold: Dict[str, Any],
    g8: Dict[str, Any],
    g9: Dict[str, Any],
) -> Dict[str, Any]:
    tid = audit["token_id"]
    cls = audit["classification"]
    conf = audit["confidence"]
    priority = review_priority(cls, conf)
    b_cands = list(g8.get("B_candidates") or [])
    g8_ids = [c["candidate_id"] for c in b_cands if c.get("candidate_id")]
    g8_summaries = [
        {
            "candidate_id": c.get("candidate_id"),
            "candidate_kind": c.get("candidate_kind"),
            "derivation": c.get("derivation"),
            "length": c.get("length"),
            "orientation": c.get("orientation"),
            "bbox": c.get("bbox"),
            "source_raw_id": c.get("source_raw_id")
            or (c.get("provenance") or {}).get("source_raw_id"),
            "source_geometry_id": (c.get("provenance") or {}).get("source_geometry_id"),
            "provenance_derivation": (c.get("provenance") or {}).get("derivation_type"),
        }
        for c in b_cands
    ]
    competing = audit.get("competing_candidates") or []
    if not competing and cls == "C":
        # Fall back to top G9 rankings as competing set for review display
        competing = [
            {
                "geometry_id": x.get("candidate_id"),
                "distance": x.get("distance_pt"),
                "length": x.get("length"),
                "kind": x.get("candidate_kind"),
                "provenance": x.get("derivation"),
                "score": x.get("total_score"),
            }
            for x in (g9.get("rankings") or [])[:6]
        ]

    d_ref = None
    if cls == "D":
        d_ref = {
            "g9_selected_id": audit.get("g9_selected_geometry_id"),
            "audit_best_candidate_id": audit.get("best_candidate_geometry_id"),
            "note": (
                "Audit reference only — reviewer must independently verify ownership. "
                "Do not auto-accept audit best candidate as human answer."
            ),
            "d_characterization": audit.get("d_characterization"),
        }

    guidance = {
        "B": (
            "G8 recovered a candidate previously absent/misclassified. Independently "
            "confirm whether that (or another) G8 candidate is owned by the label. "
            "Do NOT auto-convert B→VALID_MEMBER."
        ),
        "C": (
            "Multiple parallel/same-scale G8 candidates. Prefer AMBIGUOUS unless "
            "deterministic ownership is established by evidence hierarchy (not distance alone)."
        ),
        "D": (
            "Known G9 ranking failure reference. Verify whether the short L6-family "
            "candidate or another G8 candidate is owned; do not rubber-stamp the audit."
        ),
    }

    return {
        "token_id": tid,
        "page": audit.get("page"),
        "project": audit.get("project") or "Burrville ES - ST",
        "doc_id": audit.get("doc_id") or "doc_0d910a43b4a021e3",
        "label": audit.get("label") or gold.get("text"),
        "label_bbox": audit.get("label_bbox") or gold.get("label_bbox"),
        "review_priority": priority,
        "audit_classification": cls,
        "audit_confidence": conf,
        "audit_reason": audit.get("reason"),
        "new_representation_status": audit.get("new_representation_status"),
        "historical_gold_decision": "NO_VALID_MEMBER",
        "historical_gold_raw": gold.get("decision") or audit.get("human_gold_raw"),
        "historical_gold_reason": gold.get("reason"),
        "historical_gold_error_bucket": gold.get("error_bucket"),
        "historical_review_label": gold.get("review_label"),
        "historical_candidate_geometry_ids": gold.get("candidate_geometry_ids") or [],
        "g8_loss_class": g8.get("loss_class"),
        "g8_A_status": g8.get("A_status"),
        "g8_B_status": g8.get("B_status"),
        "g8_candidate_count": len(g8_ids),
        "g8_candidate_ids": g8_ids,
        "g8_candidates": g8_summaries,
        "g9_decision": g9.get("decision"),
        "g9_selected_candidate_id": g9.get("selected_candidate_id")
        or audit.get("g9_selected_geometry_id"),
        "g9_mode": g9.get("association_mode") or audit.get("g9_mode"),
        "g9_score": audit.get("g9_score"),
        "g9_rank": audit.get("g9_rank"),
        "leader_required": bool(
            gold.get("leader_required")
            or g8.get("leader_required")
            or g9.get("leader_required")
        ),
        "leader_tip": g9.get("leader_tip")
        or (g8.get("leader_audit") or {}).get("tip"),
        "leader_status": g8.get("leader_status") or g9.get("leader_status"),
        "competing_candidates": competing,
        "d_case_reference": d_ref,
        "review_guidance": guidance.get(cls, ""),
        "ownership_question": (
            "Which frozen G8 candidate, if any, is actually owned by this annotation?"
        ),
        "allowed_reviewer_decisions": [
            "VALID_MEMBER",
            "NO_VALID_MEMBER",
            "AMBIGUOUS",
            "NEEDS_REVIEW",
        ],
        "reviewer_decision": None,
        "owned_candidate_ids": [],
        "review_status": "PENDING",
        "crop_paths": {
            "audit_false_assoc": f"../g9_false_association_audit/renders/{tid}.png",
            "g9_shadow": f"../association_shadow_g9_renders/{tid}.png",
            "g8_repair": f"../representation_repair_g8_renders/{tid}.png",
            "historical_assoc": f"../renders/assoc_{tid}.png",
        },
        "do_not": [
            "overwrite_historical_gold",
            "auto_accept_g9_selection",
            "auto_convert_audit_B_to_VALID_MEMBER",
            "force_winner_on_C",
        ],
    }


def write_plan(summary: Dict[str, Any]) -> None:
    body = f"""# G8-Era Human Validation — Preparation Plan

**Status:** `G8_ERA_HUMAN_VALIDATION_PREPARATION = {summary['g8_era_human_validation_preparation']}`

**Purpose:** Prepare a separate human ownership review against the **frozen G8**
candidate universe. This is **not** a gold rewrite, not G10, not G9 tuning.

---

## 1. Two validation universes (do not conflate)

| Layer | Candidate universe | Role |
|---|---|---|
| Historical gold (`review_kit/gold_outcomes.jsonl`) | Pre-G8 association candidates | **Immutable** historical evidence |
| G8-era human validation (this folder) | Frozen G8 `B_candidates` | **Future** ownership review layer |

Historical `NO_VALID_MEMBER` often means “no listed candidate was the member,” not
“no steel exists.” The false-association audit (B=21) showed many of those decisions
are **stale relative to G8**, but audit class B is evidence — not automatic new gold.

---

## 2. Existing architecture discovered

### Human gold
- Path: `docs/validation/rd_geometry_integration/review_kit/gold_outcomes.jsonl`
- SHA (frozen): `{summary['frozen_inputs']['gold_sha']}`
- Fields include: `token_id`, `decision`, `review_label`, `selected_geometry_id`,
  `reviewed_target_geometry_ids`, `candidate_geometry_ids`, `reason`, `error_bucket`,
  `reviewer_id`, `review_source`
- Metrics: `review_kit/gold_metrics.json` (do not modify)

### Review kit tooling
- Generator: `backend/scripts/rd_geometry_integration/review_kit.py`
- UI: `review_kit/index.html` + per-token HTML; decisions in `review_kit/decisions/`
- Historical `review_label` values: `direct_target`, `no_valid_target`,
  `ambiguous_requires_adjudication`, `unavailable`, …
- **Limitation:** kit pages list **pre-G8 `geom_*` candidates**, not frozen G8
  `rnd_raw_*` / `#segN` IDs. Reuse the *decision pattern* and crops; do **not** use
  the old candidate checkboxes as G8 ownership truth.

### G8 / G9 / audit (frozen inputs)
- G8 results SHA: `{summary['frozen_inputs']['g8_sha']}`
- G9 results SHA: `{summary['frozen_inputs']['g9_sha']}`
- Audit: `g9_false_association_audit/` (21B + 5C + 1D)
- D-case forensics: `g9_false_association_audit/d_case_forensics/` (`D_CASE_ISOLATED`)

### What can be reused
- Evidence hierarchy / review discipline from `review_kit/README.md`
- Per-token decision JSON file pattern
- Existing visual crops (audit / G8 / G9 / historical assoc renders)
- Audit classifications B/C/D and competing-candidate lists

### What must not be reused as write target
- `gold_outcomes.jsonl` / `gold_metrics.json` (immutable)
- Production UI / Semantic Review / takeoff

---

## 3. Proposed G8-era decision vocabulary

| Decision | Meaning | Owned G8 IDs |
|---|---|---|
| `VALID_MEMBER` | One G8 candidate owned by the annotation | exactly 1 |
| `NO_VALID_MEMBER` | No G8 candidate is the owned member | 0 |
| `AMBIGUOUS` | Multiple plausible owners; not deterministic | ≥2 listed |
| `NEEDS_REVIEW` | Insufficient crop/PDF evidence | 0 |

Maps from historical labels: see `g8_era_human_validation_schema.json`.

Ownership question (mandatory):

> Which frozen G8 candidate, if any, is actually owned by this annotation?

Evidence hierarchy (distance last): explicit relationship → leader tip → overlap/contact
→ orientation → topology → repeated context → distance.

---

## 4. Manifest scope (exactly 27)

| Audit class | Count | Priority | Review intent |
|---|---:|---|---|
| B PREVIOUSLY_MISSING_CANDIDATE | {summary['counts']['B']} | MEDIUM if audit conf=MEDIUM else NORMAL | Confirm ownership independently |
| C AMBIGUOUS_UNDER_NEW_REPRESENTATION | {summary['counts']['C']} | HIGH | Allow AMBIGUOUS; show competitors |
| D G9_CLEARLY_WRONG | {summary['counts']['D']} | HIGH | Reference G9 fail; independent verify |
| **Total** | **{summary['counts']['total']}** | | |

Priority is workflow only, not correctness.

Tokens:
- B: {', '.join(summary['token_ids_by_class']['B'])}
- C: {', '.join(summary['token_ids_by_class']['C'])}
- D: {', '.join(summary['token_ids_by_class']['D'])}

---

## 5. How to review B cases

1. Open crop (prefer audit false-assoc render).
2. Enumerate frozen `g8_candidates` (IDs, kind, derivation, length, bbox).
3. Apply evidence hierarchy — do not accept “G8 recovered it” as ownership.
4. Decide VALID_MEMBER (one id) / NO_VALID_MEMBER / AMBIGUOUS / NEEDS_REVIEW.
5. Record notes. Leave `reviewer_decision` null until the future collection step.

**Do not** auto-convert audit B → VALID_MEMBER.

---

## 6. How to review C cases

Tokens: `token_p8_381`, `token_p8_382`, `token_p8_383`, `token_p8_384`, `token_p8_430`.

1. Show all competing same-scale / parallel candidates from the manifest.
2. If PDF does not establish deterministic ownership → **AMBIGUOUS** (list competitors).
3. Do not force a winner for dataset convenience.

---

## 7. How to review D case (`token_p24_1359`)

Reference (not auto-answer):
- G9 selected: `rnd_raw_p24_480_d0c0ca5e54d7` (405pt wall)
- Audit better: `raw_p24_10_9d8fbf0dfe5b#seg1` (short segment)

Reviewer independently verifies ownership via leader tip + short angle geometry.
See `../g9_false_association_audit/d_case_forensics/`.

---

## 8. Artifacts in this folder

| File | Role |
|---|---|
| `G8_ERA_HUMAN_VALIDATION_PLAN.md` | This plan |
| `g8_era_human_validation_schema.json` | Proposed decision schema |
| `g8_era_human_validation_manifest.jsonl` | Exact 27-case review queue |
| `g8_era_human_validation_summary.json` | Counts, SHAs, gate |
| `review.html` | Lightweight isolated review index (G8 IDs) |
| `decisions_pending/` | Empty placeholder for **future** human decisions |

---

## 9. Explicit non-goals

- No G10 / G9 weight or threshold changes
- No G8 regeneration / candidate rewrites
- No historical gold edits
- No production extraction / association / Semantic Review / takeoff changes
- No ML / VLM
- No claiming accuracy improvement from this preparation

---

## 10. Next step (not this task)

A **separate** human collection pass writes JSON into `decisions_pending/` and eventually
a **separate** outcomes file (e.g. `g8_era_review_outcomes.jsonl`) — never into
`review_kit/gold_outcomes.jsonl`.

---

## Safety / SHA verification

- Gold: `{summary['frozen_inputs']['gold_sha']}`
- G8: `{summary['frozen_inputs']['g8_sha']}`
- G9: `{summary['frozen_inputs']['g9_sha']}`
- Audit: `{summary['frozen_inputs']['audit_sha']}`
- Gold metrics path present and **not modified** by this prep
"""
    PLAN_PATH.write_text(body, encoding="utf-8")


def write_review_html(rows: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    cards = []
    for r in sorted(
        rows,
        key=lambda x: (
            priority_rank(x["review_priority"]),
            int(x.get("page") or 0),
            x["token_id"],
        ),
    ):
        cands = "".join(
            f"<tr><td><code>{html.escape(str(c.get('candidate_id')))}</code></td>"
            f"<td>{html.escape(str(c.get('candidate_kind')))}</td>"
            f"<td>{html.escape(str(c.get('derivation')))}</td>"
            f"<td>{c.get('length')}</td>"
            f"<td>{html.escape(str(c.get('source_geometry_id')))}</td></tr>"
            for c in (r.get("g8_candidates") or [])[:12]
        )
        comps = "".join(
            f"<li><code>{html.escape(str(c.get('geometry_id')))}</code> "
            f"len={c.get('length')} dist={c.get('distance')} "
            f"kind={html.escape(str(c.get('kind')))}</li>"
            for c in (r.get("competing_candidates") or [])[:8]
        )
        d_html = ""
        if r.get("d_case_reference"):
            d = r["d_case_reference"]
            d_html = (
                f"<p><b>D reference:</b> G9 selected "
                f"<code>{html.escape(str(d.get('g9_selected_id')))}</code>; "
                f"audit best "
                f"<code>{html.escape(str(d.get('audit_best_candidate_id')))}</code> "
                f"— verify independently.</p>"
            )
        crop = (r.get("crop_paths") or {}).get("audit_false_assoc") or ""
        cards.append(
            f"""
<section class="case" id="{html.escape(r['token_id'])}">
  <h2>{html.escape(r['review_priority'])} · {html.escape(r['audit_classification'])} ·
      {html.escape(r['token_id'])} · p{r['page']} · {html.escape(str(r.get('label')))}</h2>
  <p><b>Ownership question:</b> {html.escape(r.get('ownership_question') or '')}</p>
  <p><b>Guidance:</b> {html.escape(r.get('review_guidance') or '')}</p>
  <p>Historical gold: <code>{html.escape(str(r.get('historical_gold_decision')))}</code>
     — {html.escape(str(r.get('historical_gold_reason') or '')[:220])}</p>
  <p>G9 selected (reference only):
     <code>{html.escape(str(r.get('g9_selected_candidate_id')))}</code>
     · mode={html.escape(str(r.get('g9_mode')))}</p>
  {d_html}
  <img src="{html.escape(crop)}" alt="{html.escape(r['token_id'])}" loading="lazy"/>
  <h3>Frozen G8 candidates</h3>
  <table>
    <thead><tr><th>ID</th><th>kind</th><th>derivation</th><th>len</th><th>src geom</th></tr></thead>
    <tbody>{cands}</tbody>
  </table>
  <h3>Competing / context</h3>
  <ul>{comps or '<li>(none listed — use full G8 table)</li>'}</ul>
  <p class="pending"><b>Reviewer decision:</b> PENDING
     (VALID_MEMBER | NO_VALID_MEMBER | AMBIGUOUS | NEEDS_REVIEW)</p>
</section>
"""
        )
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>G8-era human validation (preparation)</title>
<style>
body{{font-family:ui-sans-serif,system-ui,sans-serif;margin:1.25rem;background:#f5f5f2;color:#111}}
.case{{background:#fff;border:1px solid #ccc;padding:1rem;margin:1rem 0}}
img{{max-width:100%;border:1px solid #bbb;background:#eee}}
table{{border-collapse:collapse;width:100%;font-size:.8rem}}
td,th{{border:1px solid #ddd;padding:.25rem .4rem;text-align:left}}
.pending{{color:#6a3d00}}
.meta{{color:#444}}
code{{font-size:.85em}}
</style></head><body>
<h1>G8-era human validation — preparation queue</h1>
<p class="meta">Gate: <b>{html.escape(summary['g8_era_human_validation_preparation'])}</b> ·
n={summary['counts']['total']}
(B={summary['counts']['B']}, C={summary['counts']['C']}, D={summary['counts']['D']}) ·
Historical gold immutable · Decisions not collected yet</p>
<p>Priority order: HIGH (C+D) → MEDIUM (B MEDIUM) → NORMAL (B HIGH).
Evidence hierarchy: relationship → leader → contact → orientation → topology → context → distance.</p>
{''.join(cards)}
</body></html>
"""
    REVIEW_HTML.write_text(doc, encoding="utf-8")


def validate_manifest(
    rows: Sequence[Dict[str, Any]],
    g8_by: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    problems: List[str] = []
    ids = [r["token_id"] for r in rows]
    if len(rows) != EXPECTED_TOTAL:
        problems.append(f"total={len(rows)}")
    if len(ids) != len(set(ids)):
        problems.append("duplicate_token_ids")
    cls = Counter(r["audit_classification"] for r in rows)
    if cls.get("B") != EXPECTED_B:
        problems.append(f"B={cls.get('B')}")
    if cls.get("C") != EXPECTED_C:
        problems.append(f"C={cls.get('C')}")
    if cls.get("D") != EXPECTED_D:
        problems.append(f"D={cls.get('D')}")
    for r in rows:
        tid = r["token_id"]
        b_ids = {
            c["candidate_id"]
            for c in (g8_by[tid].get("B_candidates") or [])
            if c.get("candidate_id")
        }
        for cid in r.get("g8_candidate_ids") or []:
            if cid not in b_ids:
                problems.append(f"{tid}:missing_g8:{cid}")
        sel = r.get("g9_selected_candidate_id")
        if sel and sel not in b_ids:
            problems.append(f"{tid}:g9_sel_not_in_B:{sel}")
        if r.get("reviewer_decision") is not None:
            problems.append(f"{tid}:decision_prematurely_filled")
        if r.get("review_status") != "PENDING":
            problems.append(f"{tid}:not_pending")
    return {"ok": not problems, "problems": problems}


def main() -> int:
    gold_sha = _sha(GOLD_PATH)
    g8_sha = _sha(G8_PATH)
    g9_sha = _sha(G9_PATH)
    audit_sha = _sha(AUDIT_PATH)
    if gold_sha != EXPECTED_GOLD_SHA:
        raise SystemExit(f"Gold SHA mismatch: {gold_sha}")
    if g8_sha != EXPECTED_G8_SHA:
        raise SystemExit(f"G8 SHA mismatch: {g8_sha}")
    if g9_sha != EXPECTED_G9_SHA:
        raise SystemExit(f"G9 SHA mismatch: {g9_sha}")

    gold_metrics_sha_before = _sha(GOLD_METRICS) if GOLD_METRICS.exists() else None
    audit_sum_sha_before = _sha(AUDIT_SUMMARY) if AUDIT_SUMMARY.exists() else None

    audit_rows = _load_jsonl(AUDIT_PATH)
    gold_by = {r["token_id"]: r for r in _load_jsonl(GOLD_PATH)}
    g8_by = {r["token_id"]: r for r in _load_jsonl(G8_PATH)}
    g9_by = {r["token_id"]: r for r in _load_jsonl(G9_PATH)}

    # Only B/C/D from audit (the 27 false-assoc cases)
    scope = [r for r in audit_rows if r.get("classification") in {"B", "C", "D"}]
    if len(scope) != EXPECTED_TOTAL:
        raise SystemExit(f"Expected {EXPECTED_TOTAL} B/C/D audit rows, got {len(scope)}")

    PREP_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    (DECISIONS_DIR / "README.md").write_text(
        "# Pending G8-era decisions\n\n"
        "This directory is intentionally empty of decisions during PREPARATION.\n"
        "A future human collection step will write `*.decision.json` here.\n"
        "Do **not** write into `review_kit/gold_outcomes.jsonl`.\n",
        encoding="utf-8",
    )

    rows = [
        build_manifest_row(a, gold_by[a["token_id"]], g8_by[a["token_id"]], g9_by[a["token_id"]])
        for a in sorted(
            scope,
            key=lambda r: (
                priority_rank(review_priority(r["classification"], r["confidence"])),
                int(r.get("page") or 0),
                r["token_id"],
            ),
        )
    ]

    v = validate_manifest(rows, g8_by)
    cls_counts = Counter(r["audit_classification"] for r in rows)
    pri_counts = Counter(r["review_priority"] for r in rows)

    summary: Dict[str, Any] = {
        "g8_era_human_validation_preparation": (
            "COMPLETE" if v["ok"] else "INCOMPLETE"
        ),
        "counts": {
            "total": len(rows),
            "B": cls_counts.get("B", 0),
            "C": cls_counts.get("C", 0),
            "D": cls_counts.get("D", 0),
            "priority": dict(pri_counts),
        },
        "token_ids": [r["token_id"] for r in rows],
        "token_ids_by_class": {
            "B": [r["token_id"] for r in rows if r["audit_classification"] == "B"],
            "C": [r["token_id"] for r in rows if r["audit_classification"] == "C"],
            "D": [r["token_id"] for r in rows if r["audit_classification"] == "D"],
        },
        "frozen_inputs": {
            "gold_sha": gold_sha,
            "g8_sha": g8_sha,
            "g9_sha": g9_sha,
            "audit_sha": audit_sha,
            "gold_metrics_sha": gold_metrics_sha_before,
            "audit_summary_sha": audit_sum_sha_before,
        },
        "validation": v,
        "safety": {
            "historical_gold_unchanged": True,
            "gold_metrics_unchanged": True,
            "g8_unchanged": True,
            "g9_unchanged": True,
            "audit_unchanged": True,
            "no_new_gold_created": True,
            "no_g10": True,
            "no_g9_tuning": True,
            "decisions_collected": False,
        },
        "reuse": {
            "existing_review_kit": "docs/validation/rd_geometry_integration/review_kit/",
            "existing_generator": "backend/scripts/rd_geometry_integration/review_kit.py",
            "limitation": "Historical kit candidate IDs are pre-G8 geom_*; use this prep manifest for G8 IDs",
        },
    }

    schema = build_schema()
    SCHEMA_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with MANIFEST_PATH.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_plan(summary)
    write_review_html(rows, summary)

    # Immutability checks
    if _sha(GOLD_PATH) != EXPECTED_GOLD_SHA:
        raise SystemExit("Gold changed during prep")
    if _sha(G8_PATH) != EXPECTED_G8_SHA or _sha(G9_PATH) != EXPECTED_G9_SHA:
        raise SystemExit("G8/G9 changed during prep")
    if _sha(AUDIT_PATH) != audit_sha:
        raise SystemExit("Audit changed during prep")
    if GOLD_METRICS.exists() and _sha(GOLD_METRICS) != gold_metrics_sha_before:
        raise SystemExit("gold_metrics changed during prep")
    if AUDIT_SUMMARY.exists() and _sha(AUDIT_SUMMARY) != audit_sum_sha_before:
        raise SystemExit("audit summary changed during prep")

    print(f"G8_ERA_HUMAN_VALIDATION_PREPARATION = {summary['g8_era_human_validation_preparation']}")
    print(
        f"manifest n={len(rows)} B={cls_counts['B']} C={cls_counts['C']} D={cls_counts['D']} "
        f"priority={dict(pri_counts)} ok={v['ok']}"
    )
    print(f"wrote {MANIFEST_PATH}")
    print(f"wrote {SCHEMA_PATH}")
    print(f"wrote {PLAN_PATH}")
    print(f"wrote {REVIEW_HTML}")
    if not v["ok"]:
        print("problems:", v["problems"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
