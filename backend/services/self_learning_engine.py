"""
Phase 4 - Self-Learning Engine
==============================

Decides, for a single token, whether the system already knows how to describe
it or whether it must *learn*. The learning loop is:

    unseen / unmatched token
        -> AI predicts the class
        -> learn (or extend) a regex from the class' example set + this token
        -> validate the new regex
        -> store it in the knowledge base
        -> reuse it next time

The engine never fabricates a hand-written regex; it delegates pattern
synthesis to the Regex Learning Engine and persistence to the Knowledge Base.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.regex_knowledge_base import knowledge_base
from services.regex_validator import full_match


# Human-readable learning outcomes surfaced through the API.
STATUS_REUSED = "reused"            # existing regex already matches the token
STATUS_LEARNED_NEW = "learned_new"  # class had no pattern before
STATUS_EXTENDED = "extended"        # pattern changed to accommodate the token
STATUS_REINFORCED = "reinforced"    # same pattern re-derived (more evidence)
STATUS_UNRESOLVED = "unresolved"    # could not produce a matching pattern


@dataclass
class LearningOutcome:
    status: str
    learned: bool
    pattern: Optional[str]
    previous_pattern: Optional[str]
    matched: bool
    regex_confidence: float
    regex_level: str
    detail: dict

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "learned": self.learned,
            "pattern": self.pattern,
            "previous_pattern": self.previous_pattern,
            "matched": self.matched,
            "regex_confidence": round(self.regex_confidence, 4),
            "regex_level": self.regex_level,
            "detail": self.detail,
        }


def _matches_class_patterns(record: Optional[dict], token: str) -> bool:
    """Match a class's readable primary pattern or any learned variant."""
    if not record:
        return False
    patterns = [record.get("pattern")]
    patterns.extend(variant.get("pattern") for variant in record.get("variants", []))
    return any(full_match(pattern, token) for pattern in patterns if pattern)


def process_token(cls: Optional[str], token: str, persist: bool = True) -> LearningOutcome:
    """
    Ensure the knowledge base can describe ``token`` for class ``cls``,
    learning or extending a regex when necessary.
    """

    if not cls:
        return LearningOutcome(
            status=STATUS_UNRESOLVED,
            learned=False,
            pattern=None,
            previous_pattern=None,
            matched=False,
            regex_confidence=0.0,
            regex_level="Low",
            detail={"reason": "no_class_predicted"},
        )

    record = knowledge_base.get(cls)
    existing_pattern = record.get("pattern") if record else None

    # Case 1: known pattern that already fully matches the token -> reuse it.
    if _matches_class_patterns(record, token):
        knowledge_base.record_usage(cls, persist=persist)
        record = knowledge_base.get(cls) or {}
        return LearningOutcome(
            status=STATUS_REUSED,
            learned=False,
            pattern=existing_pattern,
            previous_pattern=existing_pattern,
            matched=True,
            regex_confidence=record.get("confidence", 0.0),
            regex_level=record.get("confidence_level", "Low"),
            detail={"reason": "existing_pattern_matched"},
        )

    # Case 2: unknown class or the token is not matched -> learn / extend.
    result = knowledge_base.learn_and_upsert(cls, [token], source="self-learned", persist=persist)
    knowledge_base.record_usage(cls, persist=persist)

    new_pattern = result["new_pattern"]
    now_matches = _matches_class_patterns(result["record"], token)

    if existing_pattern is None:
        status = STATUS_LEARNED_NEW
    elif result["status"] in ("updated",):
        status = STATUS_EXTENDED
    elif result["status"] in ("reinforced", "unchanged", "kept_previous"):
        status = STATUS_REINFORCED if now_matches else STATUS_UNRESOLVED
    else:
        status = STATUS_EXTENDED if now_matches else STATUS_UNRESOLVED

    if not now_matches:
        status = STATUS_UNRESOLVED

    validation = result["validation"]
    return LearningOutcome(
        status=status,
        learned=status in (STATUS_LEARNED_NEW, STATUS_EXTENDED),
        pattern=new_pattern,
        previous_pattern=existing_pattern,
        matched=now_matches,
        regex_confidence=validation.get("confidence", 0.0),
        regex_level=validation.get("level", "Low"),
        detail={
            "kb_status": result["status"],
            "candidate_pattern": result.get("candidate_pattern"),
            "coverage": validation.get("coverage"),
            "example_count": result["record"].get("example_count"),
            "distinct_structures": result["record"].get("distinct_structures"),
        },
    )
