"""Parses an untrusted reviewer submission into a validated outcome.

Two-stage validation, deliberately kept separate:

1. **Shape validation** (this module): is the submitted payload even a
   well-formed ``ReviewImportEntry`` (right types, required fields
   present)? Malformed payloads are converted into the same
   ``ValidationError``/``ValidationErrorCode`` shape as semantic
   failures, so a caller never has to catch a raw pydantic exception.
2. **Semantic validation** (``validation.validate_review_import``): does
   this well-formed submission make sense against the ``LabelGroup`` and
   outcome store it claims to review?
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from pydantic import ValidationError as PydanticValidationError

from services.ml_association.enums import ValidationErrorCode
from services.ml_association.schemas import (
    LabelGroup,
    ReviewImportEntry,
    ValidationError,
    ValidationResult,
)
from services.ml_association.validation import validate_review_import


def parse_import_entry(raw: Dict[str, Any]) -> "ReviewImportEntry | ValidationResult":
    """Parse a raw dict into a ``ReviewImportEntry``.

    Returns the parsed entry on success, or a failed ``ValidationResult``
    (one error per malformed/missing field) on failure -- callers should
    check ``isinstance(result, ReviewImportEntry)``.
    """

    try:
        return ReviewImportEntry.model_validate(raw)
    except PydanticValidationError as exc:
        errors = []
        for detail in exc.errors():
            field = ".".join(str(part) for part in detail.get("loc", ())) or None
            errors.append(
                ValidationError(
                    code=ValidationErrorCode.UNKNOWN_ID.value
                    if field in ("group_id", "project_id", "document_id", "page_id", "text_entity_id")
                    else ValidationErrorCode.INVALID_REVIEW_LABEL.value
                    if field == "review_label"
                    else ValidationErrorCode.INVALID_CALLOUT_SCOPE.value
                    if field == "callout_scope"
                    else "malformed_field",
                    message=detail.get("msg", "invalid field"),
                    field=field,
                )
            )
        return ValidationResult(valid=False, errors=errors, outcome=None)


def import_review(
    raw: Dict[str, Any],
    group: LabelGroup,
    *,
    known_page_geometry_ids: Optional[Set[str]] = None,
    existing_outcome_ids: Optional[Set[str]] = None,
) -> ValidationResult:
    """End-to-end: parse ``raw`` and validate it against ``group``.

    Never writes anything -- the caller (``service.py``) decides whether
    to persist ``result.outcome`` via ``outcome_store.append_outcome``.
    """

    parsed = parse_import_entry(raw)
    if isinstance(parsed, ValidationResult):
        return parsed

    return validate_review_import(
        parsed,
        group,
        known_page_geometry_ids=known_page_geometry_ids,
        existing_outcome_ids=existing_outcome_ids,
    )
