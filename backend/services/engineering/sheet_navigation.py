"""Sheet role from the printed sheet title.

Display only. Does not read the page body, does not treat a dimension as a
grid, and does not change a schedule, a mark, or a quantity. A title that
names more than one drawing type stays ``review`` instead of picking one.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

SHEET_ROLE_VERSION = "sheet_role_v1"

_DETAIL = re.compile(r"\bDETAILS?\b", re.I)
_SECTION = re.compile(r"\bSECTIONS?\b", re.I)
_ELEVATION = re.compile(r"\bELEVATIONS?\b", re.I)
_SCHEDULE = re.compile(r"\bSCHEDULES?\b", re.I)
_PLAN = re.compile(r"\bPLANS?\b", re.I)
_FRAMING = re.compile(r"\bFRAMING\b", re.I)
_FOUNDATION = re.compile(r"\bFOUNDATION\b", re.I)
_SLAB = re.compile(r"\bSLAB ON GRADE\b", re.I)
_ROOF = re.compile(r"\bROOF\b", re.I)
_FLOOR = re.compile(r"\bFLOOR\b", re.I)
_LOADING = re.compile(r"\bLOADING\b|\bLOAD PLANS?\b", re.I)
_NOTES = re.compile(
    r"\bGENERAL NOTES\b|\bABBREVIATIONS\b|\bSPECIAL INSPECTIONS?\b|\bNOTATIONS\b",
    re.I,
)
_CONCRETE = re.compile(r"\bCONCRETE\b", re.I)
_STEEL = re.compile(r"\bSTEEL\b", re.I)
_MASONRY = re.compile(r"\bMASONRY\b", re.I)

_READ_TITLE = frozenset({"read", "read_unlabeled"})


def _role(role: Optional[str], label: str, status: str, evidence: str,
          candidates: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "sheet_role": role,
        "sheet_role_label": label,
        "classification_status": status,
        "classification_evidence": evidence,
        "role_candidates": candidates if candidates is not None else ([role] if role else []),
    }


def classify_sheet_title(title: Optional[str], title_status: Optional[str]) -> Dict[str, Any]:
    """Role of one sheet from its title block title alone."""

    if title_status not in _READ_TITLE or not str(title or "").strip():
        status = "review" if title_status == "ambiguous" else "unresolved"
        evidence = "title is ambiguous" if title_status == "ambiguous" else "no printed sheet title"
        return _role(None, "Unknown", status, evidence, [])

    text = str(title)
    evidence = "printed sheet title"
    detail = _DETAIL.search(text)
    section = _SECTION.search(text)
    elevation = _ELEVATION.search(text)
    schedule = _SCHEDULE.search(text)
    plan = _PLAN.search(text)
    framing = _FRAMING.search(text)
    foundation = bool(_FOUNDATION.search(text) or (_SLAB.search(text) and (plan or detail)))
    roof = _ROOF.search(text)
    loading = _LOADING.search(text)

    # A detail, section, or schedule sheet stays that type when the title also
    # names the system (foundation sections, steel framing details).
    kinds: List[str] = []
    if detail:
        kinds.append("detail")
    if section:
        kinds.append("section")
    if elevation:
        kinds.append("elevation")
    if schedule:
        kinds.append("schedule")
    if (plan or framing) and not detail and not section:
        kinds.append("plan")

    if loading and not detail and not section and "elevation" not in kinds:
        return _role("loading", "Loading", "read", evidence)

    if len(kinds) > 1:
        return _role(None, "Review", "review", "title names more than one sheet type", kinds)

    if detail:
        if foundation:
            return _role("foundation_details", "Foundation details", "read", evidence)
        if _CONCRETE.search(text):
            return _role("concrete_details", "Concrete details", "read", evidence)
        if _STEEL.search(text):
            return _role("steel_details", "Steel details", "read", evidence)
        if _MASONRY.search(text):
            return _role("masonry_details", "Masonry details", "read", evidence)
        return _role("detail", "Detail", "read", evidence)
    if section:
        return _role("section", "Section", "read", evidence)
    if elevation:
        return _role("elevation", "Elevation", "read", evidence)
    if schedule:
        return _role("schedule", "Schedule", "read", evidence)
    if foundation and (plan or framing):
        if framing:
            label, why = "Foundation and framing plan", "title names foundation and framing"
        elif _FLOOR.search(text):
            label, why = "Foundation and floor plan", "title names foundation and floor"
        else:
            label, why = "Foundation plan", evidence
        return _role("foundation_plan", label, "read", why)
    if roof and (plan or framing):
        return _role("roof_plan", "Roof plan", "read", evidence)
    if plan or framing:
        if framing:
            label = "Framing plan"
        elif _FLOOR.search(text):
            label = "Floor plan"
        else:
            label = "Plan"
        return _role("framing_plan", label, "read", evidence)
    if _NOTES.search(text):
        return _role("general_notes", "General notes", "read", evidence)
    return _role(None, "Review", "review", "printed title does not name a sheet type", [])


def annotate_sheet_roles(index: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of a sheet index with a role on each page. The source index is unchanged."""

    pages = []
    for page in index.get("pages") or []:
        pages.append({
            **page,
            **classify_sheet_title(page.get("sheet_title"), page.get("title_status")),
        })
    return {**index, "role_version": SHEET_ROLE_VERSION, "pages": pages}


def printed_issue(pages: List[Dict[str, Any]]) -> Optional[str]:
    """The issue printed in the title block. A revision-row word is not an issue."""

    phrases = [p["issue"] for p in pages if p.get("issue_status") == "read" and p.get("issue")]
    if not phrases:
        return None
    phrase, count = Counter(phrases).most_common(1)[0]
    if count == len(pages):
        return phrase
    return f"{phrase} ({count} of {len(pages)} sheets)"
