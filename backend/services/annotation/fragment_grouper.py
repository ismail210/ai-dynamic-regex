"""Group split / rotated text fragments into one annotation candidate."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence

from services.annotation.normalize import as_float


def _center(bbox: Sequence[float]) -> tuple[float, float]:
    return (
        (float(bbox[0]) + float(bbox[2])) / 2.0,
        (float(bbox[1]) + float(bbox[3])) / 2.0,
    )


def _rot_delta(a: Any, b: Any) -> float:
    left = as_float(a)
    right = as_float(b)
    if left is None or right is None:
        return 0.0
    delta = abs(left - right) % 180.0
    return min(delta, 180.0 - delta)


def _is_dim_token(text: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?|\d+/\d+", str(text or "").strip()))


def _is_family_token(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:2L|WT|MT|ST|MC|HP|HSS|PIPE|W|S|M|C|L)",
            str(text or "").strip(),
            re.I,
        )
    )


def _is_separator_token(text: str) -> bool:
    return str(text or "").strip().lower() in {"x", "×", "✕", "*", "-"}


def _strip_outer_brackets(text: str) -> str:
    raw = str(text or "").strip()
    if len(raw) >= 2 and raw[0] in "[(" and raw[-1] in "])":
        return raw[1:-1].strip()
    return raw


def _exact_beside_schedule_mark(left_text: str, right_text: str) -> bool:
    """A catalog-exact section next to a BP/CL/C/L mark (``W14x90`` / ``BP3``).

    Joining them destroys the locked exact label, so they never merge.
    """

    from services.engineering.schedule_grid import is_schedule_table_mark
    from services.exact_section_predictor import catalog_valid_exact_section

    def mark(text: str) -> bool:
        return is_schedule_table_mark(re.sub(r"[,.;:]+$", "", text))

    return bool(
        (mark(right_text) and catalog_valid_exact_section(left_text))
        or (mark(left_text) and catalog_valid_exact_section(right_text))
    )


def _compatible(
    left: Dict[str, Any],
    right: Dict[str, Any],
    *,
    max_gap: float = 28.0,
    max_rot_delta: float = 8.0,
) -> bool:
    lb = left.get("bbox") or []
    rb = right.get("bbox") or []
    if len(lb) < 4 or len(rb) < 4:
        return False
    if int(left.get("page") or 0) != int(right.get("page") or 0):
        return False
    if _rot_delta(left.get("rotation"), right.get("rotation")) > max_rot_delta:
        return False
    lc = _center(lb)
    rc = _center(rb)
    gap = math.hypot(lc[0] - rc[0], lc[1] - rc[1])
    # Rotated callouts (≈90°) often sit farther apart along the reading axis.
    rot = as_float(left.get("rotation")) or 0.0
    gap_limit = max_gap
    if 70.0 <= (abs(rot) % 180.0) <= 110.0:
        gap_limit = max_gap * 1.55
    # Family + dimension fragments (``W`` ``12`` ``x`` ``26``) tolerate a
    # slightly larger gap than arbitrary text.
    lt = _strip_outer_brackets(str(left.get("text") or ""))
    rt = _strip_outer_brackets(str(right.get("text") or ""))
    if (
        _is_family_token(lt)
        or _is_dim_token(lt)
        or _is_separator_token(lt)
    ) and (
        _is_family_token(rt)
        or _is_dim_token(rt)
        or _is_separator_token(rt)
    ):
        gap_limit = max(gap_limit, max_gap * 1.25)
    if gap > gap_limit:
        return False
    left_font = as_float(left.get("font_size"))
    right_font = as_float(right.get("font_size"))
    if left_font and right_font and abs(left_font - right_font) > 3.0:
        return False
    return not _exact_beside_schedule_mark(lt, rt)


def group_annotation_fragments(
    fragments: List[Dict[str, Any]],
    *,
    max_gap: float = 28.0,
) -> List[Dict[str, Any]]:
    """Merge nearby fragments such as ``6`` ``x`` ``4`` ``x`` ``5/6``.

    Returns annotation candidates. Each keeps ``fragments`` (original pieces)
    and a joined ``text`` / ``raw_text``. Unmerged fragments pass through.
    """

    ordered = sorted(
        [dict(item) for item in fragments if str(item.get("text") or "").strip()],
        key=lambda item: (
            int(item.get("page") or 0),
            float((item.get("bbox") or [0, 0, 0, 0])[1]),
            float((item.get("bbox") or [0, 0, 0, 0])[0]),
        ),
    )
    if not ordered:
        return []

    groups: List[List[Dict[str, Any]]] = []
    current = [ordered[0]]
    for item in ordered[1:]:
        if _compatible(current[-1], item, max_gap=max_gap):
            current.append(item)
        else:
            groups.append(current)
            current = [item]
    groups.append(current)

    joined: List[Dict[str, Any]] = []
    for group in groups:
        if len(group) == 1:
            # Nothing was merged -- pass the original record through
            # untouched. Reconstructing text/normalized_text from the raw
            # ``text`` field below (needed for real multi-fragment merges)
            # would otherwise clobber the already-correct, whitespace-
            # stripped ``normalized_text`` that token_extractor produced
            # for the common single-token case with a re-spaced version of
            # the raw OCR text.
            seed = dict(group[0])
            seed["fragments"] = [
                {
                    "text": group[0].get("text"),
                    "bbox": group[0].get("bbox"),
                    "rotation": group[0].get("rotation"),
                    "font_size": group[0].get("font_size"),
                    "page": group[0].get("page"),
                }
            ]
            seed["was_merged"] = False
            joined.append(seed)
            continue
        texts = [
            _strip_outer_brackets(str(part.get("text") or "").strip())
            for part in group
        ]
        raw = " ".join(t for t in texts if t)
        if any(_is_separator_token(t) for t in texts) or all(
            _is_dim_token(t) or _is_family_token(t)
            for t in texts
            if not _is_separator_token(t)
        ):
            raw = "".join(texts)
        elif all(len(t) <= 2 for t in texts):
            raw = "".join(texts)
        bboxes = [part.get("bbox") for part in group if part.get("bbox")]
        bbox = None
        if bboxes:
            bbox = [
                min(float(b[0]) for b in bboxes),
                min(float(b[1]) for b in bboxes),
                max(float(b[2]) for b in bboxes),
                max(float(b[3]) for b in bboxes),
            ]
        seed = dict(group[0])
        seed["text"] = raw
        seed["raw_text"] = raw
        seed["normalized_text"] = raw
        seed["bbox"] = bbox or seed.get("bbox")
        seed["fragments"] = [
            {
                "text": part.get("text"),
                "bbox": part.get("bbox"),
                "rotation": part.get("rotation"),
                "font_size": part.get("font_size"),
                "page": part.get("page"),
            }
            for part in group
        ]
        seed["was_merged"] = len(group) > 1
        joined.append(seed)
    return joined
