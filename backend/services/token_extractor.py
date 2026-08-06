"""Engineering token extraction with legacy and metadata-rich APIs."""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional


TOKEN_PATTERNS = (
    r"\b(?:W|WT|S|M|HP|C|MC)\s*\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?\b",
    r"\bHSS\s*\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?"
    r"(?:\s*[X×]\s*(?:\d+/\d+|\d+(?:\.\d+)?))?\b",
    r"\b(?:L|2L)\s*\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?"
    r"(?:\s*[X×]\s*(?:\d+/\d+|\d+(?:\.\d+)?))?\b",
    r"\bPIPE\s*\d+(?:\.\d+)?\b",
    r"\bPL(?:ATE)?\s*(?:\d+(?:\.\d+)?|\d+/\d+)"
    r"(?:\s*[X×]\s*(?:\d+(?:\.\d+)?|\d+/\d+)){0,2}\b",
    r"\bS-\d+\b",
    r"\b(?:A|F)\d{3,4}M?\b",
)
_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in TOKEN_PATTERNS]
# One alternation replaces seven separate scans of every candidate window. The
# longest, most specific families come first so a shorter family prefix cannot
# win inside them.
_COMBINED = re.compile(
    "|".join(
        f"(?:{pattern})"
        for pattern in (
            TOKEN_PATTERNS[1],  # HSS
            TOKEN_PATTERNS[2],  # L / 2L
            TOKEN_PATTERNS[3],  # PIPE
            TOKEN_PATTERNS[4],  # PL / PLATE
            TOKEN_PATTERNS[0],  # W / WT / S / M / HP / C / MC
            TOKEN_PATTERNS[5],  # sheet reference
            TOKEN_PATTERNS[6],  # material grade
        )
    ),
    re.IGNORECASE,
)
_DIGIT_RE = re.compile(r"\d")
EXTRACTION_STATUSES = ("VALID", "SUSPICIOUS", "BROKEN", "INVALID")
_NOISE_RE = re.compile(r"^[\W_]+$")


def normalize_engineering_token(text: str) -> str:
    """Normalize spacing and multiplication glyphs while preserving fractions."""

    normalized = (
        str(text or "")
        .strip()
        .upper()
        .replace("×", "X")
        .replace("✕", "X")
    )
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _matches(text: str) -> Iterable[re.Match[str]]:
    value = str(text or "")
    if not _DIGIT_RE.search(value):
        # Every engineering token carries at least one digit.
        return ()
    return _COMBINED.finditer(value)


def _token_status(
    *,
    confidence: float,
    text: str,
    was_merged: bool,
    repair_count: int,
    rotation: float,
    has_context: bool,
) -> tuple[str, List[str]]:
    """Classify extraction quality independently from prediction quality."""

    issues: List[str] = []
    # Successful repairs and rotated drawing text are recorded for traceability
    # but do not degrade extraction status: both are normal on steel drawings.
    if was_merged:
        issues.append("split_label_reconstructed")
    if repair_count:
        issues.append("ocr_cleanup_applied")
    if abs(rotation) > 2:
        issues.append("rotated_text")
    if not has_context:
        issues.append("missing_layout_context")
    if _NOISE_RE.fullmatch(text) or not re.search(r"[A-Z0-9]", text, re.I):
        issues.append("non_semantic_noise")
        return "INVALID", issues
    if confidence < 0.35:
        return "INVALID", issues + ["very_low_extraction_confidence"]
    if confidence < 0.50:
        return "BROKEN", issues + ["low_extraction_confidence"]
    if confidence < 0.65 or not has_context:
        return "SUSPICIOUS", issues
    return "VALID", issues


def _candidate_windows(ordered: List[dict]) -> Iterable[tuple[str, List[dict]]]:
    """Yield bounded adjacent-word windows to repair split labels safely.

    A window is only offered when it can still form a label: it must contain a
    digit and start with an alphanumeric word. Multi-word windows are limited to
    the joined form once, which keeps large drawings from generating millions of
    candidates that cannot match.
    """

    max_words = min(6, len(ordered))
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for start in range(len(ordered)):
        first = str(ordered[start].get("text") or "")
        if not first or not first[0].isalnum():
            continue
        for size in range(1, max_words + 1):
            window = ordered[start : start + size]
            if len(window) < size:
                break
            texts = [str(word.get("text") or "") for word in window]
            spaced = " ".join(texts)
            if not _DIGIT_RE.search(spaced):
                continue
            variants = (spaced,) if size == 1 else (spaced, "".join(texts))
            source_ids = tuple(str(word.get("object_id") or "") for word in window)
            for variant in variants:
                key = (variant, source_ids)
                if variant and key not in seen:
                    seen.add(key)
                    yield variant, window


def extract_engineering_tokens(text: str) -> List[str]:
    """
    Backward-compatible plain token API.

    Results remain unique and sorted, while the accepted engineering
    vocabulary is broader than the original five patterns.
    """

    return sorted(
        {
            normalize_engineering_token(match.group(0))
            for match in _matches(text)
        }
    )


def extract_engineering_token_records(
    words: List[dict],
    *,
    lines: Optional[List[dict]] = None,
    blocks: Optional[List[dict]] = None,
) -> List[dict]:
    """
    Extract metadata-rich tokens from positioned PDF words.

    Adjacent words on the same line are merged before matching, repairing
    broken forms such as ``W18 X 35``. Duplicate records at the same page and
    coordinates are removed, but repeated member labels elsewhere are kept.
    """

    lines = lines or []
    blocks = blocks or []
    line_index: Dict[tuple, dict] = {
        (
            line.get("page_number"),
            line.get("block_no"),
            line.get("line_no"),
        ): line
        for line in lines
    }
    block_index = {block.get("object_id"): block for block in blocks}

    grouped: Dict[tuple, List[dict]] = {}
    for word in words:
        key = (
            int(word.get("page_number") or 0),
            word.get("block_no"),
            word.get("line_no"),
        )
        grouped.setdefault(key, []).append(word)

    records: List[dict] = []
    seen = set()
    reading_order = 0
    for (page_number, block_no, line_no), line_words in sorted(
        grouped.items(), key=lambda item: item[0]
    ):
        ordered = sorted(
            line_words,
            key=lambda word: (
                word.get("word_no") if word.get("word_no") is not None else 9999,
                (word.get("bbox") or [0])[0],
            ),
        )
        joined = " ".join(str(word.get("text") or "") for word in ordered)
        candidate_matches: List[tuple[re.Match[str], List[dict]]] = []
        for candidate_text, candidate_words in _candidate_windows(ordered):
            candidate_matches.extend(
                (match, candidate_words) for match in _matches(candidate_text)
            )
        for match, candidate_words in candidate_matches:
            raw = match.group(0)
            normalized = normalize_engineering_token(raw)
            contributing = [
                word
                for word in candidate_words
                if normalize_engineering_token(word.get("text", "")) in normalized
                or normalized in normalize_engineering_token(word.get("text", ""))
            ]
            if not contributing:
                contributing = candidate_words
            raw_source = " ".join(
                str(word.get("raw_text") or word.get("text") or "")
                for word in contributing
            ).strip()
            x0 = min(word["bbox"][0] for word in contributing)
            y0 = min(word["bbox"][1] for word in contributing)
            x1 = max(word["bbox"][2] for word in contributing)
            y1 = max(word["bbox"][3] for word in contributing)
            bbox = [round(value, 2) for value in (x0, y0, x1, y1)]
            dedupe_key = (
                page_number,
                normalized,
                tuple(round(value, 1) for value in bbox),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            line = line_index.get((page_number, block_no, line_no))
            block_id = (
                contributing[0].get("block_id")
                or (line or {}).get("block_id")
            )
            block = block_index.get(block_id) or {}
            confidence_values = [
                float(word.get("confidence") or 0.5) for word in contributing
            ]
            confidence = sum(confidence_values) / max(len(confidence_values), 1)
            was_merged = len(contributing) > 1
            repairs = sorted(
                {
                    repair
                    for word in contributing
                    for repair in (word.get("ocr_repairs") or [])
                }
            )
            rotation_values = [
                float(
                    word.get("rotation")
                    or (line or {}).get("rotation")
                    or 0.0
                )
                for word in contributing
            ]
            rotation = sum(rotation_values) / max(len(rotation_values), 1)
            line_text = str((line or {}).get("text") or joined)
            block_text = str(block.get("text") or "")
            neighbor_text = [
                str(neighbor.get("text") or "")
                for word in contributing
                for neighbor in (word.get("neighbors") or [])
                if neighbor.get("text")
            ]
            surrounding = " | ".join(
                dict.fromkeys(
                    text.strip()
                    for text in [line_text, block_text, *neighbor_text]
                    if text and text.strip()
                )
            )[:1200]
            status, issues = _token_status(
                confidence=confidence,
                text=normalized,
                was_merged=was_merged,
                repair_count=len(repairs),
                rotation=rotation,
                has_context=bool(line or block or neighbor_text),
            )
            records.append(
                {
                    "token_id": f"token_p{page_number}_{reading_order}",
                    "text": raw.strip(),
                    "raw_text": raw_source or raw.strip(),
                    "corrected_text": raw.strip(),
                    "normalized_text": normalized,
                    "page": page_number,
                    "bbox": bbox,
                    "rotation": round(rotation, 2),
                    "font": contributing[0].get("font"),
                    "font_size": contributing[0].get("font_size"),
                    "line": {
                        "id": (line or {}).get("object_id")
                        or contributing[0].get("line_id"),
                        "number": line_no,
                        "text": (line or {}).get("text", joined),
                    },
                    "block": {
                        "id": block_id,
                        "number": block_no,
                        "role": block.get("hierarchy_role", "body"),
                    },
                    "confidence": round(min(0.99, confidence), 4),
                    "extraction_status": status,
                    "status": status,
                    "diagnostics": {
                        "issues": issues,
                        "ocr_repairs": repairs,
                        "source_word_count": len(contributing),
                        "reconstructed": was_merged,
                    },
                    "reading_order": reading_order,
                    "source_word_ids": [
                        word.get("object_id") for word in contributing
                    ],
                    "was_merged": was_merged,
                    "context": {
                        "line_text": line_text,
                        "block_text": block_text,
                        "block_role": block.get("hierarchy_role", "body"),
                        "neighbor_text": list(dict.fromkeys(neighbor_text))[:8],
                    },
                    "surrounding_text": surrounding,
                }
            )
            reading_order += 1

    # Report repeated labels without removing legitimate repeated members.
    repeated = Counter(record["normalized_text"] for record in records)
    for record in records:
        count = repeated[record["normalized_text"]]
        record["repeat_count"] = count
        if count > 1:
            record["diagnostics"]["issues"].append("repeated_label")
    return records