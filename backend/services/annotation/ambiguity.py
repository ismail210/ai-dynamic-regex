"""Ambiguity among Top-K valid candidates (separate from understandability)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from services.annotation.normalize import as_float


def assess_ambiguity(
    candidates: Sequence[Dict[str, Any]],
    *,
    selected: Optional[str] = None,
    text_supports_selected: bool = False,
    clear_margin: float = 0.12,
    close_margin: float = 0.05,
) -> Dict[str, Any]:
    """Score Top-K ambiguity. Never fabricates a fake winner.

    ``text_supports_selected`` means the annotation text itself resolves the
    label (undamaged designation found in the catalog). Fusion scores of
    neighbouring catalog entries are often close, so margin alone must not send
    an unambiguous designation to human review.
    """

    cleaned: List[Dict[str, Any]] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        shape = str(item.get("shape") or item.get("label") or "").strip()
        if not shape:
            continue
        cleaned.append(
            {
                "shape": shape,
                "score": as_float(item.get("score"))
                or as_float(item.get("confidence"))
                or 0.0,
                "in_catalog": bool(item.get("in_catalog", True)),
            }
        )
    cleaned.sort(key=lambda row: row["score"], reverse=True)
    top_k = cleaned[:8]
    if not top_k:
        return {
            "ambiguous": True,
            "resolution": "unresolved",
            "top_k": [],
            "margin": None,
            "selected": selected,
            "reason": "No valid candidates available.",
        }

    best = top_k[0]
    second = top_k[1]["score"] if len(top_k) > 1 else 0.0
    margin = (as_float(best["score"]) or 0.0) - (as_float(second) or 0.0)
    chosen = selected or best["shape"]

    if text_supports_selected:
        return {
            "ambiguous": False,
            "resolution": "automatic",
            "top_k": top_k,
            "margin": round(margin, 4),
            "selected": chosen,
            "reason": (
                f"Annotation text resolves to {chosen} directly; "
                "Top-K margin is not the deciding factor."
            ),
        }

    if len(top_k) == 1 or margin >= clear_margin:
        resolution = "automatic"
        ambiguous = False
        reason = f"Clear winner {best['shape']} with margin {margin:.1%}."
    elif margin >= close_margin:
        resolution = "multimodal_rerank"
        ambiguous = True
        reason = f"Close Top-K (margin {margin:.1%}); multimodal rerank required."
    else:
        resolution = "human_review"
        ambiguous = True
        reason = f"Top candidates nearly tied (margin {margin:.1%}); do not force Top-1."

    return {
        "ambiguous": ambiguous,
        "resolution": resolution,
        "top_k": top_k,
        "margin": round(margin, 4),
        "selected": chosen,
        "reason": reason,
    }
