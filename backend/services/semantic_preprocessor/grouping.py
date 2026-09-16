"""Conservative semantic annotation grouping (Section 20-21).

Groups raw text primitives into one semantic annotation only when there is
an explicit, named reason to do so. Every merge records which rule fired
(``grouping_reasons``) so a reviewer -- or a future test -- can see why two
fragments were joined, rather than trusting an opaque distance threshold.

Original per-fragment geometry is never discarded: ``source_fragment_ids``
always preserves the contributing primitives, and ``semantic_bbox`` is a
union box over their bboxes, never a replacement rectangle that erases the
originals (Section 21).
"""
from __future__ import annotations

import re
from typing import List, Optional

from services.semantic.models import Modifier, SemanticAnnotation, SourceFragment, derive_annotation_id
from services.semantic_preprocessor.models import TextPrimitive

_BRACKET_TAG_RE = re.compile(r"^\[(?P<value>[^\[\]]+)\]$")

# A structural-looking fragment missing its numeric fields entirely, or
# missing a trailing field (e.g. "HSS8X8" with no thickness) -- used only to
# decide whether a cross-line continuation merge is even plausible.
_INCOMPLETE_HSS_RE = re.compile(r"^HSS\d+(?:\.\d+)?X\d+(?:\.\d+)?$")
_BARE_FRACTION_OR_DECIMAL_RE = re.compile(r"^[\d./]+$")

_SAME_LINE_GAP_MULTIPLE = 1.5  # gap tolerance, in units of font size
# Gaps above this fraction of font size are treated as intentional spaces
# (damage "W 18 X 46"); tighter gaps are glyph splits ("W"+"8"+"X"+"10").
_VISUAL_SPACE_GAP_FRACTION = 0.2


def _font_size_or_default(primitive: TextPrimitive) -> float:
    return primitive.font_size or 10.0


def _visual_text_for_chain(chain: List[TextPrimitive]) -> str:
    """Join chain text, inserting spaces only for clearly spaced glyphs."""
    if not chain:
        return ""
    if len(chain) == 1:
        return chain[0].text
    parts: List[str] = [chain[0].text]
    for prev, cur in zip(chain, chain[1:]):
        gap = _horizontal_gap(prev, cur)
        threshold = _font_size_or_default(prev) * _VISUAL_SPACE_GAP_FRACTION
        if gap > threshold:
            parts.append(" ")
        parts.append(cur.text)
    return "".join(parts)


def _union_bbox(boxes: List[List[float]]) -> List[float]:
    xs0 = [b[0] for b in boxes]
    ys0 = [b[1] for b in boxes]
    xs1 = [b[2] for b in boxes]
    ys1 = [b[3] for b in boxes]
    return [min(xs0), min(ys0), max(xs1), max(ys1)]


def _horizontal_gap(left: TextPrimitive, right: TextPrimitive) -> float:
    return right.bbox[0] - left.bbox[2]


def _same_baseline(a: TextPrimitive, b: TextPrimitive) -> bool:
    # Two fragments share a baseline if their rotation matches and their
    # vertical extents overlap substantially -- a conservative proxy for
    # "on the same line" without requiring identical block/line ids (OCR
    # primitives may not carry those).
    if abs(a.rotation_deg - b.rotation_deg) > 1.0:
        return False
    a_mid = (a.bbox[1] + a.bbox[3]) / 2
    b_mid = (b.bbox[1] + b.bbox[3]) / 2
    tolerance = max(_font_size_or_default(a), _font_size_or_default(b)) * 0.4
    return abs(a_mid - b_mid) <= tolerance


def group_primitives(
    primitives: List[TextPrimitive], page: int, document_id: str = ""
) -> List[SemanticAnnotation]:
    """Group same-page primitives into semantic annotations.

    Only three merge rules fire, each with its own reason code:
    ``bracket_modifier_attachment``, ``same_baseline_merge`` (adjacent
    same-line fragments that only combine into a complete structural label
    together, e.g. "W" "8" "X" "10"), and ``split_structural_label_merge``
    (a two-line continuation like "HSS8X8" over "3/8", gated tightly to
    avoid merging unrelated adjacent lines).
    """
    ordered = sorted(
        [p for p in primitives if p.page == page],
        key=lambda p: (round(p.bbox[1], 1), p.bbox[0]),
    )
    used = set()
    annotations: List[SemanticAnnotation] = []
    by_id = {p.primitive_id: p for p in ordered}

    for i, prim in enumerate(ordered):
        if prim.primitive_id in used:
            continue

        # Rule 1: same-baseline chain merge (handles "W" "8" "X" "10" and
        # already-whole "W8X10" fragments alike).
        chain = [prim]
        used.add(prim.primitive_id)
        j = i + 1
        while j < len(ordered):
            nxt = ordered[j]
            if nxt.primitive_id in used:
                j += 1
                continue
            last = chain[-1]
            if not _same_baseline(last, nxt):
                break
            gap = _horizontal_gap(last, nxt)
            if gap < 0 or gap > _font_size_or_default(last) * _SAME_LINE_GAP_MULTIPLE:
                break
            # Never fold a bracket tag into the chain here -- that's handled
            # explicitly below so it becomes a Modifier, not part of the
            # primary label text.
            if _BRACKET_TAG_RE.match(nxt.text.strip()):
                break
            chain.append(nxt)
            used.add(nxt.primitive_id)
            j += 1

        combined_text = "".join(p.text for p in chain)
        # Preserve intentional PDF spacing (wide gaps) in original_text so
        # NORMALIZATION can rewrite the drawing; keep primary_label compact.
        visual_text = _visual_text_for_chain(chain)
        reasons = ["same_baseline_merge"] if len(chain) > 1 else []
        source_ids = [p.primitive_id for p in chain]
        bbox = _union_bbox([p.bbox for p in chain])
        anchor = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
        axis = [1.0, 0.0] if abs(chain[0].rotation_deg) < 1.0 else [0.0, 1.0]

        modifiers: List[Modifier] = []
        last_prim = chain[-1]

        # Rule 2: bracket modifier attachment, e.g. "W8X10" + "[24]".
        k = j
        while k < len(ordered):
            candidate = ordered[k]
            if candidate.primitive_id in used:
                k += 1
                continue
            if not _same_baseline(last_prim, candidate):
                break
            gap = _horizontal_gap(last_prim, candidate)
            if gap < 0 or gap > _font_size_or_default(last_prim) * _SAME_LINE_GAP_MULTIPLE:
                break
            bracket_match = _BRACKET_TAG_RE.match(candidate.text.strip())
            if not bracket_match:
                break  # unrelated nearby text -- must NOT merge
            modifiers.append(Modifier(
                type="bracket_tag",
                raw_text=candidate.text,
                value=bracket_match.group("value"),
                primitive_ids=[candidate.primitive_id],
                bbox=list(candidate.bbox),
            ))
            used.add(candidate.primitive_id)
            source_ids.append(candidate.primitive_id)
            bbox = _union_bbox([bbox, candidate.bbox])
            reasons.append("bracket_modifier_attachment")
            last_prim = candidate
            k += 1
            break  # at most one bracket tag per annotation in this pass

        # Rule 3: split structural label continuation across lines, e.g.
        # "HSS8X8" on one line and "3/8" directly below it at a similar
        # x-position. Deliberately narrow: only fires when the upper
        # fragment is a recognizably incomplete HSS designation AND the
        # candidate below is a bare fraction/decimal token.
        if _INCOMPLETE_HSS_RE.match(combined_text.strip()):
            continuation = _find_line_continuation(ordered, used, chain)
            if continuation is not None:
                # The line break stands in for the missing "X" separator
                # between the incomplete "HSSaXb" and its thickness field.
                combined_text = combined_text + "X" + continuation.text
                visual_text = visual_text + "X" + continuation.text
                source_ids.append(continuation.primitive_id)
                bbox = _union_bbox([bbox, continuation.bbox])
                reasons.append("split_structural_label_merge")
                used.add(continuation.primitive_id)

        raw_text = visual_text + ("".join(f" {m.raw_text}" for m in modifiers) if modifiers else "")
        source_fragments = [
            SourceFragment(primitive_id=pid, text=by_id[pid].text, bbox=list(by_id[pid].bbox))
            for pid in source_ids
        ]
        annotation = SemanticAnnotation(
            annotation_id=derive_annotation_id(document_id, page, source_ids),
            page=page,
            original_text=raw_text.strip(),
            source_fragment_ids=source_ids,
            source_fragments=source_fragments,
            semantic_bbox=bbox,
            original_anchor=anchor,
            original_axis=axis,
            primary_label=combined_text.strip(),
            modifiers=modifiers,
            grouping_reasons=reasons,
        )
        annotations.append(annotation)

    return annotations


def _find_line_continuation(
    ordered: List[TextPrimitive], used: set, chain: List[TextPrimitive]
) -> Optional[TextPrimitive]:
    top = chain[-1]
    top_x_start = chain[0].bbox[0]
    font_size = _font_size_or_default(top)
    best: Optional[TextPrimitive] = None
    best_dy = None
    for candidate in ordered:
        if candidate.primitive_id in used:
            continue
        if not _BARE_FRACTION_OR_DECIMAL_RE.match(candidate.text.strip()):
            continue
        if abs(candidate.rotation_deg - top.rotation_deg) > 1.0:
            continue
        dy = candidate.bbox[1] - top.bbox[3]
        if dy < 0 or dy > font_size * 1.2:
            continue  # not directly below within one line-height
        if abs(candidate.bbox[0] - top_x_start) > font_size * 2.0:
            continue  # not aligned with the start of the upper fragment
        if best_dy is None or dy < best_dy:
            best, best_dy = candidate, dy
    return best
