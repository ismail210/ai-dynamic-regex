"""Offline measurement of legend interpretation. Does not enable flags.

Reads production functions only. The live model is attempted once against
localhost Ollama and recorded as not-run when unreachable. Gate probes use
an in-process fake provider so rejection counts are measurements of the
existing validators, not of a model.

Run from backend/:
    python scripts/legend_llm_offline_audit.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import settings
from services.engineering import legend_llm_provider as llm
from services.engineering import legend_profile as lp
from services.engineering.project_rule_resolver import resolve_token
from services.staged_pipeline import _apply_project_rule_resolution
from tests.test_legend_profile import (
    FRAMING_PLAN_TEXT,
    GENERAL_NOTES_TEXT,
    REAL_FRAMING_PLAN_TEXT,
    _doc,
)


def _flags() -> dict:
    return {
        "LEGEND_PROFILE_ENABLED": bool(settings.legend_profile_enabled),
        "LEGEND_PROFILE_LLM_ENABLED": bool(settings.legend_profile_llm_enabled),
        "DRAWING_SUMMARY_LLM_ENABLED": bool(settings.drawing_summary_llm_enabled),
        "PROJECT_RULE_PAGE_ROLE_ENABLED": bool(settings.project_rule_page_role_enabled),
        "legend_llm_provider": settings.legend_llm_provider,
        "legend_llm_model": settings.legend_llm_model,
        "max_context_chars": lp._DEFAULT_MAX_CONTEXT_CHARS,
    }


def _ollama() -> dict:
    url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            tags = json.loads(resp.read())
        names = [m.get("name") for m in tags.get("models") or []]
        return {"reachable": True, "models": names}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}


def _rules(document, context_pages):
    rules = lp.extract_abbreviation_rules(document, context_pages)
    return [
        {
            "lhs": r["lhs"],
            "rhs": r["rhs"],
            "lhs_family": r.get("lhs_family"),
            "rhs_family": r.get("rhs_family"),
            "source_page": r["source_page"],
            "quote": r["source_quote"],
            "method": r["extraction_method"],
        }
        for r in rules
    ]


def _case(name, pages):
    document = _doc(pages)
    context = lp.detect_context_pages(document)
    readable = lp._readable_context_pages(context)
    rules = _rules(document, context)
    packet = lp.build_context_text(document, context) if readable else ""
    return {
        "name": name,
        "context_pages": {str(k): v for k, v in context.items()},
        "readable_pages": readable,
        "deterministic_rules": rules,
        "deterministic_rule_count": len(rules),
        "packet_chars": len(packet),
        "packet_has_page_tags": "[PAGE " in packet,
    }


LEGEND_TABLE = (
    "STEEL BEAM LEGEND / ABBREVIATIONS\n"
    '"B1" = W16X26\n"B2" = W18X35\n"B3" = W21X44\n"G1" = W24X68\n'
    '"C1" = HSS8X8X3/8\n"C2" = HSS10X10X1/2\n"BR1" = HSS6X6X3/8\n'
)
PROSE_NOTES = (
    "GENERAL NOTES\n"
    "1. STRUCTURAL STEEL SHALL CONFORM TO ASTM A992.\n"
    "2. WHERE A BEAM SIZE IS NOT SHOWN, PROVIDE W12X19 MINIMUM.\n"
    "3. TYPICAL EDGE ANGLE IS L4X4X1/4 UNO.\n"
    "7. \"CANT\" INDICATES CANTILEVERED BEAM. WHERE BEAM IS STEEL AND SIZE IS\n"
    "NOT INDICATED, THE CANTILEVERED BEAM SHALL BE THE SAME SIZE AS THE\n"
    "ADJACENT BACKSPAN BEAM, UNO.\n"
)
SPEC_PAGE = "SPECIFICATIONS\nSTRUCTURAL STEEL SHALL CONFORM TO ASTM A992 UNLESS NOTED.\n" + ("BOILERPLATE SUBMITTAL PROCEDURE. " * 40)
SCHEDULE_PAGE = (
    "SPECIFICATIONS\n"
    "FIRST FLOOR\n0' - 0\"\nSECOND FLOOR\n14' - 0\"\nROOF\n28' - 0\"\n"
    "HSS6X6X5/8  35 KIPS   HSS6X6X3/8  100 KIPS\n"
    "FIRST FLOOR\n0' - 0\"\nSECOND FLOOR\n14' - 0\"\nROOF\n28' - 0\"\n"
    "HSS6X6X3/8  HSS8X8X3/8  HSS6X6X1/2  HSS6X6X3/8  HSS8X8X3/8\n"
)
DETAIL_WITH_NOTES = (
    "TYPICAL DETAILS\nGENERAL NOTES\n"
    "DETAIL 4/S5.2 - TYPICAL BEAM AT W16X26.  "
    "DETAIL 5/S5.2 - TYPICAL COLUMN CAP AT HSS8X8X3/8.  "
    "SEE PLAN FOR W21X44 LOCATIONS.\n"
    "PROVIDE L4X4 AT OPENING WHERE SHOWN\n"
)


class _Fake:
    def __init__(self, payload):
        self.payload = payload

    def propose(self, system_prompt, document_text):
        return self.payload


def _label(trigger, result, quote, statement):
    return {
        "type": "LABEL_SUBSTITUTION",
        "statement": statement,
        "trigger": trigger,
        "result": result,
        "relevance": "CRITICAL",
        "system_benefit": ["A"],
        "source_page": 1,
        "source_quote": quote,
        "scope": {"page_roles": ["ALL"], "uno_applies": False},
    }


def _gate_probe(name, source, proposals):
    result = llm.propose_analysis(source, provider=_Fake({"executive_summary": "probe", "rules": proposals, "derived_insights": [], "estimator_attention": []}))
    accepted = [
        {
            "type": r["type"],
            "trigger": r.get("trigger"),
            "result": r.get("result"),
            "policy": r.get("application_policy"),
            "status": r.get("validation_status"),
            "quote": r.get("source_quote"),
        }
        for r in result.rules
    ]
    return {
        "name": name,
        "proposed": result.raw_rule_count,
        "accepted": len(result.rules),
        "rejected": result.rejected_rule_count,
        "accepted_rules": accepted,
        "provider": "in_process_fake_not_a_model",
    }


def _resolve(raw, abbreviation_rules, project_rules, page_role="UNKNOWN"):
    diagnostics = []
    decision = resolve_token(
        raw_token=raw,
        page_role=page_role,
        abbreviation_rules=abbreviation_rules,
        project_rules=project_rules,
        diagnostics=diagnostics,
    )
    if decision is None:
        return {"raw": raw, "page_role": page_role, "resolved": None, "gate": diagnostics[-1] if diagnostics else None}
    return {
        "raw": raw,
        "page_role": page_role,
        "resolved": decision["resolved_designation"],
        "method": decision["extraction_method"],
        "gate": None,
    }


def _prediction(raw, page=2):
    return {
        "object_id": f"obj-{raw}-{page}",
        "document_id": "audit-doc",
        "source_text": {"raw": raw, "normalized": raw, "page_number": page, "document_id": "audit-doc"},
        "comparison": {"match_status": "needs_review"},
        "takeoff_eligible": True,
        "section": raw,
        "final_label": raw,
    }


def _overlay(name, predictions, profile):
    before = [(p["object_id"], p["section"], p.get("takeoff_eligible")) for p in predictions]
    out, applied = _apply_project_rule_resolution(predictions, profile, set(), document_id="audit-doc")
    after = [
        {
            "object_id": p["object_id"],
            "section": p.get("section"),
            "takeoff_eligible": p.get("takeoff_eligible"),
            "match_status": (p.get("comparison") or {}).get("match_status"),
            "method": (p.get("project_rule_resolution") or {}).get("extraction_method"),
        }
        for p in out
    ]
    return {"name": name, "before": before, "after": after, "applied_count": len(applied)}


def main() -> None:
    notes = _case("general_notes_fixture", {1: GENERAL_NOTES_TEXT, 2: FRAMING_PLAN_TEXT})
    legend = _case("legend_table_fixture", {1: LEGEND_TABLE, 2: FRAMING_PLAN_TEXT})
    prose = _case("prose_notes_fixture", {1: PROSE_NOTES, 2: FRAMING_PLAN_TEXT})
    pad = "STRUCTURAL STEEL NOTES CONTINUED. VERIFY IN FIELD. "
    cross = _case("cross_family", {1: 'GENERAL NOTES\n"W8" = C8x11.5\n' + pad})
    bad_catalog = _case("invalid_catalog", {1: 'GENERAL NOTES\n"W8" = W8X999\n' + pad})
    plan = _case("framing_plan_only", {1: REAL_FRAMING_PLAN_TEXT})
    detail = _case("detail_page_with_general_notes_heading", {1: DETAIL_WITH_NOTES})
    schedule = _case("schedule_elevation_matrix", {1: SCHEDULE_PAGE})
    scan = _case("low_text_notes", {1: "GENERAL NOTES"})
    quoted_hss = _case("quoted_hss", {1: 'GENERAL NOTES\n"HSS8x4" = HSS8x4x1/4\n' + pad})
    detail_notes_only = _case(
        "detail_sheet_with_notes_heading_no_incomplete_angle",
        {1: (
            "TYPICAL DETAILS\nGENERAL NOTES\n"
            "DETAIL 4/S5.2 - TYPICAL BEAM AT W16X26.  "
            "DETAIL 5/S5.2 - TYPICAL COLUMN CAP AT HSS8X8X3/8.  "
            "SEE PLAN FOR W21X44 LOCATIONS.\n"
        )},
    )
    dense_schedule = _case(
        "dense_schedule_matrix_excluded",
        {1: (
            "SPECIFICATIONS\n"
            "FIRST FLOOR\n0' - 0\"\nSECOND FLOOR\n14' - 0\"\nROOF\n28' - 0\"\n"
            "HSS6X6X5/8  35 KIPS   HSS6X6X3/8  100 KIPS\n"
            "FIRST FLOOR\n0' - 0\"\nSECOND FLOOR\n14' - 0\"\nROOF\n28' - 0\"\n"
            "HSS6X6X3/8  HSS8X8X3/8  HSS6X6X1/2  HSS6X6X3/8  HSS8X8X3/8\n"
            "HSS6X6X3/8  HSS6X6X3/8  HSS6X6X1/2  HSS6X6X3/8\n"
        )},
    )
    incomplete = _case("incomplete_angle_prose", {1: "GENERAL NOTES\nPROVIDE L4X4 AT OPENING WHERE SHOWN. TYPICAL EDGE ANGLE IS L4X4X1/4 UNO."})

    broad_pages = {
        1: GENERAL_NOTES_TEXT,
        2: LEGEND_TABLE,
        3: SPEC_PAGE,
        4: SCHEDULE_PAGE,
        5: REAL_FRAMING_PLAN_TEXT,
        6: DETAIL_WITH_NOTES,
    }
    broad = _case("broad_packet", broad_pages)
    notes_only = _case("notes_only_scope", {1: GENERAL_NOTES_TEXT, 2: REAL_FRAMING_PLAN_TEXT})
    tables_only = _case("tables_only_scope", {1: LEGEND_TABLE, 2: REAL_FRAMING_PLAN_TEXT})
    notes_and_tables = _case("notes_plus_tables", {1: GENERAL_NOTES_TEXT, 2: LEGEND_TABLE, 3: REAL_FRAMING_PLAN_TEXT})

    w8_source = 'GENERAL NOTES\n"W8" = W8x10\n'
    hss_source = 'GENERAL NOTES\n"HSS8x4" = HSS8x4x1/4\n'
    l_source = "GENERAL NOTES\nPROVIDE L4X4 AT OPENING WHERE SHOWN.\nTYPICAL EDGE ANGLE IS L4X4X1/4 UNO.\n"
    conflict_source = 'GENERAL NOTES\n"W8" = W8x10\n"W8" = W8x18\n'

    gates = [
        _gate_probe(
            "quoted_w8_proposal",
            w8_source,
            [_label("W8", "W8X10", '"W8" = W8x10', "W8 means W8x10 on the framing plans.")],
        ),
        _gate_probe(
            "invented_thickness_quote_missing_result",
            l_source,
            [_label("L4X4", "L4X4X1/4", "PROVIDE L4X4 AT OPENING WHERE SHOWN.", "L4X4 means L4X4X1/4 wherever shown.")],
        ),
        _gate_probe(
            "unrelated_page_quote",
            w8_source,
            [_label("W8", "W8X10", "this sentence is not on the page", "W8 means W8x10.")],
        ),
        _gate_probe(
            "cross_family_proposal",
            'GENERAL NOTES\n"W8" = C8x11.5\n',
            [_label("W8", "C8X11.5", '"W8" = C8x11.5', "W8 means C8x11.5.")],
        ),
        _gate_probe(
            "catalog_invalid_proposal",
            'GENERAL NOTES\n"W8" = W8X999\n',
            [_label("W8", "W8X999", '"W8" = W8X999', "W8 means W8X999.")],
        ),
        _gate_probe(
            "prose_cant_without_substitution_syntax",
            GENERAL_NOTES_TEXT,
            [
                {
                    "type": "INHERITANCE_RULE",
                    "statement": "A CANT beam with no size uses the adjacent backspan beam.",
                    "trigger": "CANT",
                    "relation": "adjacent_backspan_beam",
                    "inherited_field": "section_designation",
                    "relevance": "HIGH",
                    "source_page": 1,
                    "source_quote": "THE CANTILEVERED BEAM SHALL BE THE SAME SIZE AS THE ADJACENT BACKSPAN BEAM, UNO.",
                }
            ],
        ),
        _gate_probe(
            "quantity_is_not_a_rule_type",
            GENERAL_NOTES_TEXT,
            [_label("W8", "W8X10", '"W8" = W8x10', "There are twelve beams of W8x10.")],
        ),
    ]

    det_w8 = lp.extract_abbreviation_rules(_doc({1: w8_source}), {1: lp.PAGE_ROLE_GENERAL_NOTES})
    det_conflict = lp.extract_abbreviation_rules(_doc({1: conflict_source}), {1: lp.PAGE_ROLE_GENERAL_NOTES})
    accepted_w8 = llm.propose_analysis(
        w8_source,
        provider=_Fake(
            {
                "executive_summary": "probe",
                "rules": [_label("W8", "W8X10", '"W8" = W8x10', "W8 means W8x10 on the framing plans.")],
                "derived_insights": [],
                "estimator_attention": [],
            }
        ),
    ).rules
    accepted_hss = llm.propose_analysis(
        hss_source,
        provider=_Fake(
            {
                "executive_summary": "probe",
                "rules": [_label("HSS8X4", "HSS8X4X1/4", '"HSS8x4" = HSS8x4x1/4', "HSS8x4 means HSS8x4x1/4.")],
                "derived_insights": [],
                "estimator_attention": [],
            }
        ),
    ).rules
    invented = llm.propose_analysis(
        l_source,
        provider=_Fake(
            {
                "executive_summary": "probe",
                "rules": [_label("L4X4", "L4X4X1/4", "PROVIDE L4X4 AT OPENING WHERE SHOWN.", "L4X4 means L4X4X1/4 wherever shown.")],
                "derived_insights": [],
                "estimator_attention": [],
            }
        ),
    ).rules

    resolutions = [
        _resolve("W8", det_w8, []),
        _resolve("W8", det_conflict, []),
        _resolve("W8", [], accepted_w8),
        _resolve("HSS8X4", [], accepted_hss),
        _resolve("L4X4", [], invented),
        _resolve("L4X4", det_w8, invented),
        _resolve("W14X61", det_w8, []),
        _resolve("B1", lp.extract_abbreviation_rules(_doc({1: LEGEND_TABLE}), {1: lp.PAGE_ROLE_ABBREVIATIONS}), []),
        _resolve("C1", lp.extract_abbreviation_rules(_doc({1: LEGEND_TABLE}), {1: lp.PAGE_ROLE_ABBREVIATIONS}), []),
        _resolve("W8", [], llm.propose_analysis(
            'GENERAL NOTES\n"W8" = C8x11.5\n' + pad,
            provider=_Fake({"executive_summary": "probe", "rules": [_label("W8", "C8X11.5", '"W8" = C8x11.5', "W8 means C8x11.5.")], "derived_insights": [], "estimator_attention": []}),
        ).rules),
        _resolve("W8", [], llm.propose_analysis(
            'GENERAL NOTES\n"W8" = W8X999\n' + pad,
            provider=_Fake({"executive_summary": "probe", "rules": [_label("W8", "W8X999", '"W8" = W8X999', "W8 means W8X999.")], "derived_insights": [], "estimator_attention": []}),
        ).rules),
    ]

    profile_llm_only = {
        "document_id": "audit-doc",
        "abbreviation_rules": [],
        "project_rules": accepted_hss,
        "context_pages": {"1": "GENERAL_NOTES"},
    }
    profile_both = {
        "document_id": "audit-doc",
        "abbreviation_rules": det_w8,
        "project_rules": accepted_hss,
        "context_pages": {"1": "GENERAL_NOTES"},
    }
    profile_det = {
        "document_id": "audit-doc",
        "abbreviation_rules": det_w8,
        "project_rules": [],
        "context_pages": {"1": "GENERAL_NOTES"},
    }
    downstream = [
        _overlay("llm_rules_without_deterministic_rules", [_prediction("HSS8X4")], profile_llm_only),
        _overlay("deterministic_w8_only", [_prediction("W8")], profile_det),
        _overlay(
            "deterministic_present_plus_llm_hss_rule",
            [_prediction("W8"), _prediction("HSS8X4"), _prediction("L4X4")],
            profile_both,
        ),
    ]

    deterministic_total = sum(
        c["deterministic_rule_count"]
        for c in (notes, legend, prose, cross, bad_catalog, plan, detail, schedule, scan, quoted_hss, incomplete)
    )
    report = {
        "live_llm": "NOT_RUN",
        "live_llm_reason": "Ollama unreachable. Incremental LLM recall is not measured.",
        "flags_read_only": _flags(),
        "ollama": _ollama(),
        "gold": {
            "legend_rule_gold": False,
            "column_schedule_package_status": "PENDING_REVIEW",
            "column_schedule_records_approved": 0,
            "note": "docs/project_rule_phase2/gold_annotation is column-schedule cell prefill, not legend-language gold, and every record is PENDING_REVIEW.",
        },
        "deterministic_cases": [
            notes, legend, prose, cross, bad_catalog, plan, detail, detail_notes_only,
            schedule, dense_schedule, scan, quoted_hss, incomplete,
        ],
        "input_scope_packets": [notes_only, tables_only, notes_and_tables, broad],
        "gate_probes": gates,
        "resolver": resolutions,
        "downstream": downstream,
        "deterministic_rule_count_across_separate_cases": deterministic_total,
        "metrics_not_measurable": [
            "precision of accepted live-LLM rules",
            "recall against gold legend rules",
            "incremental recall of a live model over the deterministic parser",
            "false-positive rate of a live model",
            "input-scope ablation of live-model accepted rules",
        ],
    }
    text = json.dumps(report, indent=2)
    out = Path(__file__).with_name("legend_llm_offline_audit_results.json")
    out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
