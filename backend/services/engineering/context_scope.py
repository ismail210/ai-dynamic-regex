"""Separate legend / general-note *definitions* from real takeoff objects.

A steel designation printed inside an ABBREVIATIONS table, a LEGEND, or a
STRUCTURAL/GENERAL NOTES block (the HSS8x4x1/4 in an ``HSS8x4 = HSS8x4x1/4``
row, a W8x10 in a framing key) is a DEFINITION of project notation, not a
member that exists on the structure. It must feed the context analyzer and
the project-rule profile, but it must never be counted, priced, or routed
to human review as if it were a real member.

This module tags every engineering token with:

* ``object_scope`` -- ``"takeoff"`` (default) or ``"context_definition"``;
* ``takeoff_eligible`` -- ``True`` (default) or ``False``.

A token is demoted to ``context_definition`` **only** when its page was
confidently classified as a readable context page by
``legend_profile.detect_context_pages`` -- i.e. a page that matched a real
LEGEND / ABBREVIATIONS / GENERAL NOTES / STRUCTURAL NOTES / SPECIFICATIONS
heading AND did NOT pass
``legend_profile._has_strong_structural_drawing_evidence`` (renovation
``(E)``/``(N)`` member tags, OR >= 25 catalog-valid section labels, OR a
framing/schedule sheet title with >= 10 real labels -- see that function
for the business rationale). A note keyword alone never suppresses a page
that is doing real steel takeoff work. The old, softer ``document_prior``
legend score is deliberately NOT used here -- it over-flags steel-dense
framing plans (see the checkpoint-2 diagnosis in ``legend_profile.py``).

Fail-safe: no ``legend_profile``, or no context pages, leaves every token
``takeoff_eligible = True`` -- exactly today's behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.engineering.legend_profile import _CONTEXT_PAGE_ROLES

OBJECT_SCOPE_TAKEOFF = "takeoff"
OBJECT_SCOPE_CONTEXT_DEFINITION = "context_definition"


def context_definition_pages(document: Dict[str, Any]) -> set[int]:
    """Page numbers whose whole content is project context (legend / notes /
    abbreviations / specifications), from the strict classifier only."""

    profile = document.get("legend_profile")
    if not isinstance(profile, dict):
        return set()
    pages: set[int] = set()
    for raw_page, role in (profile.get("context_pages") or {}).items():
        if role in _CONTEXT_PAGE_ROLES:
            try:
                pages.add(int(raw_page))
            except (TypeError, ValueError):
                continue
    return pages


def annotate_takeoff_scope(document: Dict[str, Any]) -> Dict[str, Any]:
    """Tag ``document["engineering_tokens"]`` in place. Returns a small
    diagnostic count dict."""

    tokens: List[Dict[str, Any]] = document.get("engineering_tokens") or []
    context_pages = context_definition_pages(document)

    demoted = 0
    for token in tokens:
        try:
            page = int(token.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        if page and page in context_pages:
            token["object_scope"] = OBJECT_SCOPE_CONTEXT_DEFINITION
            token["takeoff_eligible"] = False
            # Existing pipeline hook: keep these out of the unknown-token
            # review queue (see multimodal/pipeline.py).
            token["_skip_unknown_queue"] = True
            demoted += 1
        else:
            token.setdefault("object_scope", OBJECT_SCOPE_TAKEOFF)
            token.setdefault("takeoff_eligible", True)

    diagnostics = (
        (document.get("legend_profile") or {}).get("diagnostics") or {}
    )
    return {
        "context_definition_pages": sorted(context_pages),
        "context_definition_tokens": demoted,
        "takeoff_tokens": len(tokens) - demoted,
        # Framing/schedule pages that carried a note/legend keyword but were
        # kept takeoff-eligible because they are dense with real steel
        # labels (see legend_profile._has_strong_structural_drawing_evidence).
        "full_page_demotion_blocked_pages": list(
            diagnostics.get("full_page_demotion_blocked_pages") or []
        ),
    }


def _prediction_page(item: Dict[str, Any]) -> int:
    source_text = item.get("source_text")
    if isinstance(source_text, dict) and source_text.get("page_number") is not None:
        candidate = source_text.get("page_number")
    else:
        candidate = item.get("page_number") or item.get("page")
    try:
        return int(candidate or 0)
    except (TypeError, ValueError):
        return 0


def reassert_prediction_scope(
    predictions: List[Dict[str, Any]], document: Dict[str, Any]
) -> int:
    """Stamp ``takeoff_eligible = False`` on any prediction that sits on a
    context-definition page, regardless of how it entered the prediction
    list. The extraction-time pass only tags ``document["engineering_tokens"]``;
    geometry/graph "missing label" predictions, schedule/spatial tokens, and
    label propagation all synthesize predictions afterwards and would
    otherwise slip a phantom member onto a legend/notes page. Returns the
    number newly demoted."""

    context_pages = context_definition_pages(document)
    if not context_pages:
        return 0
    demoted = 0
    for prediction in predictions:
        if prediction.get("takeoff_eligible") is False:
            continue
        if _prediction_page(prediction) in context_pages:
            prediction["object_scope"] = OBJECT_SCOPE_CONTEXT_DEFINITION
            prediction["takeoff_eligible"] = False
            demoted += 1
    return demoted


def is_takeoff_eligible(item: Dict[str, Any]) -> bool:
    """True unless the item was explicitly demoted to a context definition.
    Works on both raw tokens and served predictions."""

    return item.get("takeoff_eligible", True) is not False


def partition_takeoff(items: List[Dict[str, Any]]) -> tuple[list, list]:
    """Split a prediction / token list into (takeoff, context_definitions)."""

    takeoff: List[Dict[str, Any]] = []
    context_definitions: List[Dict[str, Any]] = []
    for item in items:
        (takeoff if is_takeoff_eligible(item) else context_definitions).append(item)
    return takeoff, context_definitions
