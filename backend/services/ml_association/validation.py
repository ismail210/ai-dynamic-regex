"""Strict reviewer-import validation with stable, structured error codes.

Every rejection rule below corresponds 1:1 to one bullet in the Phase 2
spec's "Reject an imported review when..." list. Nothing here mutates
any state -- ``validate_review_import`` is a pure function that either
returns a ``ValidationResult(valid=True, outcome=...)`` ready to hand to
``outcome_store.append_outcome``, or ``valid=False`` with one
``ValidationError`` per violated rule (not just the first one found,
so a reviewer/UI can show every problem at once).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence, Set

from services.ml_association import identifiers
from services.ml_association.enums import CalloutScope, ReviewLabel, ValidationErrorCode
from services.ml_association.schemas import (
    NO_MATCH_CANDIDATE_TOKEN,
    SCHEMA_VERSION,
    LabelGroup,
    ReviewedOutcome,
    ReviewImportEntry,
    ValidationError,
    ValidationResult,
)

_MULTI_TARGET_SCOPES = {CalloutScope.MULTIPLE, CalloutScope.TYPICAL, CalloutScope.REPEATED}


def _is_valid_timestamp(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        # datetime.fromisoformat handles "Z" only from 3.11+; this repo
        # pins Python 3.11 (see docs/ml_association_phase/repository_evidence.md).
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_review_import(
    entry: ReviewImportEntry,
    group: LabelGroup,
    *,
    supported_schema_versions: Sequence[str] = (SCHEMA_VERSION,),
    known_page_geometry_ids: Optional[Set[str]] = None,
    existing_outcome_ids: Optional[Set[str]] = None,
) -> ValidationResult:
    """Validate one reviewer submission against the ``LabelGroup`` it
    claims to review.

    ``known_page_geometry_ids``, if supplied, is the FULL set of real
    geometry entity IDs on the page (not just this group's top-K
    candidates) -- when given, a target outside even that broader set is
    reported as ``GEOMETRY_NOT_ON_PAGE`` (more severe) rather than
    ``TARGET_OUTSIDE_CANDIDATE_SET``. ``existing_outcome_ids`` should be
    ``outcome_store.existing_outcome_ids()`` for the relevant store, so
    overwrite/duplicate detection happens before any write is attempted.
    """

    errors = []

    def fail(code: ValidationErrorCode, message: str, field: Optional[str] = None) -> None:
        errors.append(ValidationError(code=code.value, message=message, field=field))

    if entry.export_schema_version not in supported_schema_versions:
        fail(
            ValidationErrorCode.UNSUPPORTED_SCHEMA_VERSION,
            f"export_schema_version {entry.export_schema_version!r} is not supported "
            f"(supported: {sorted(supported_schema_versions)})",
            field="export_schema_version",
        )

    if entry.group_id != group.group_id:
        fail(
            ValidationErrorCode.UNKNOWN_ID,
            f"group_id {entry.group_id!r} does not match the referenced group "
            f"{group.group_id!r}",
            field="group_id",
        )
    if entry.project_id != group.project_id:
        fail(
            ValidationErrorCode.PROJECT_MISMATCH,
            f"project_id {entry.project_id!r} does not match group's {group.project_id!r}",
            field="project_id",
        )
    if entry.document_id != group.document_id:
        fail(
            ValidationErrorCode.DOCUMENT_MISMATCH,
            f"document_id {entry.document_id!r} does not match group's {group.document_id!r}",
            field="document_id",
        )
    if entry.page_id != group.page_id:
        fail(
            ValidationErrorCode.PAGE_MISMATCH,
            f"page_id {entry.page_id!r} does not match group's {group.page_id!r}",
            field="page_id",
        )
    if (
        entry.region_id is not None
        and group.region_id is not None
        and entry.region_id != group.region_id
    ):
        fail(
            ValidationErrorCode.REGION_MISMATCH,
            f"region_id {entry.region_id!r} does not match group's {group.region_id!r}",
            field="region_id",
        )
    if entry.text_entity_id != group.text_entity_id:
        fail(
            ValidationErrorCode.LABEL_NOT_FOUND,
            f"text_entity_id {entry.text_entity_id!r} does not match group's "
            f"{group.text_entity_id!r}",
            field="text_entity_id",
        )

    if not entry.reviewer_id or not entry.reviewer_id.strip():
        fail(ValidationErrorCode.MISSING_REVIEWER_ID, "reviewer_id is required", field="reviewer_id")

    if not _is_valid_timestamp(entry.reviewed_at):
        fail(
            ValidationErrorCode.INVALID_TIMESTAMP,
            f"reviewed_at {entry.reviewed_at!r} is missing or not a valid ISO-8601 timestamp",
            field="reviewed_at",
        )

    review_label: Optional[ReviewLabel] = None
    try:
        review_label = ReviewLabel(entry.review_label)
    except ValueError:
        fail(
            ValidationErrorCode.INVALID_REVIEW_LABEL,
            f"review_label {entry.review_label!r} is not one of "
            f"{[v.value for v in ReviewLabel]}",
            field="review_label",
        )

    callout_scope: Optional[CalloutScope] = None
    try:
        callout_scope = CalloutScope(entry.callout_scope)
    except ValueError:
        fail(
            ValidationErrorCode.INVALID_CALLOUT_SCOPE,
            f"callout_scope {entry.callout_scope!r} is not one of "
            f"{[v.value for v in CalloutScope]}",
            field="callout_scope",
        )

    targets = list(entry.reviewed_target_geometry_ids)
    real_candidate_ids = {
        c.geometry_entity_id for c in group.candidates if not c.is_no_match_placeholder
    }
    for target_id in targets:
        if target_id == NO_MATCH_CANDIDATE_TOKEN:
            fail(
                ValidationErrorCode.TARGET_OUTSIDE_CANDIDATE_SET,
                f"{NO_MATCH_CANDIDATE_TOKEN!r} is not a selectable target id; use "
                "review_label=no_valid_target with an empty target list instead",
                field="reviewed_target_geometry_ids",
            )
            continue
        if known_page_geometry_ids is not None and target_id not in known_page_geometry_ids:
            fail(
                ValidationErrorCode.GEOMETRY_NOT_ON_PAGE,
                f"geometry {target_id!r} does not exist on page {entry.page_id!r}",
                field="reviewed_target_geometry_ids",
            )
        elif target_id not in real_candidate_ids and not entry.candidate_generation_miss:
            fail(
                ValidationErrorCode.TARGET_OUTSIDE_CANDIDATE_SET,
                f"geometry {target_id!r} is outside the exported candidate set for "
                f"group {group.group_id!r}; set candidate_generation_miss=true if this "
                "is an intentional recall-gap correction",
                field="reviewed_target_geometry_ids",
            )

    if review_label == ReviewLabel.NO_VALID_TARGET and targets:
        fail(
            ValidationErrorCode.NO_VALID_TARGET_WITH_SELECTED_TARGETS,
            "review_label=no_valid_target cannot be combined with reviewed_target_geometry_ids",
            field="reviewed_target_geometry_ids",
        )

    if review_label == ReviewLabel.LEADER_SUPPORT_NOT_TARGET and targets:
        fail(
            ValidationErrorCode.LEADER_SUPPORT_AS_FINAL_TARGET,
            "review_label=leader_support_not_target cannot carry final target "
            "geometry ids -- it is evidence, not a member selection",
            field="reviewed_target_geometry_ids",
        )

    if callout_scope == CalloutScope.SINGLE and len(targets) > 1:
        fail(
            ValidationErrorCode.SINGLE_SCOPE_MULTIPLE_TARGETS,
            f"callout_scope=single but {len(targets)} targets were selected",
            field="callout_scope",
        )

    if (
        callout_scope in _MULTI_TARGET_SCOPES
        and not targets
        and review_label
        not in (ReviewLabel.NO_VALID_TARGET, ReviewLabel.LEADER_SUPPORT_NOT_TARGET)
    ):
        fail(
            ValidationErrorCode.MULTI_TARGET_SCOPE_NO_TARGETS,
            f"callout_scope={callout_scope.value} implies multiple targets but none "
            "were selected",
            field="reviewed_target_geometry_ids",
        )

    prospective_outcome_id = None
    if review_label is not None and callout_scope is not None and _is_valid_timestamp(
        entry.reviewed_at
    ) and entry.reviewer_id:
        prospective_outcome_id = identifiers.outcome_id(
            group.group_id, entry.reviewer_id, entry.reviewed_at, entry.supersedes_outcome_id
        )
        if existing_outcome_ids is not None:
            if entry.supersedes_outcome_id and entry.supersedes_outcome_id not in existing_outcome_ids:
                fail(
                    ValidationErrorCode.UNKNOWN_ID,
                    f"supersedes_outcome_id {entry.supersedes_outcome_id!r} does not "
                    "reference a known outcome",
                    field="supersedes_outcome_id",
                )
            if prospective_outcome_id in existing_outcome_ids:
                fail(
                    ValidationErrorCode.DUPLICATE_OUTCOME_ID,
                    f"outcome_id {prospective_outcome_id!r} already exists; this "
                    "review was already recorded (or resubmit with a corrected "
                    "reviewed_at/supersedes_outcome_id to record a genuine "
                    "correction)",
                    field="reviewed_at",
                )

    if errors:
        return ValidationResult(valid=False, errors=errors, outcome=None)

    assert review_label is not None
    assert callout_scope is not None
    assert prospective_outcome_id is not None

    outcome = ReviewedOutcome(
        outcome_id=prospective_outcome_id,
        group_id=group.group_id,
        project_id=group.project_id,
        document_id=group.document_id,
        page_id=group.page_id,
        text_entity_id=group.text_entity_id,
        review_label=review_label,
        reviewed_target_geometry_ids=targets,
        candidate_generation_miss=entry.candidate_generation_miss,
        callout_scope=callout_scope,
        reviewer_id=entry.reviewer_id,
        reviewed_at=entry.reviewed_at,
        annotation_notes=entry.annotation_notes,
        prior_prediction_snapshot={
            "selected_candidate_id": group.selected_candidate_id(),
        },
        candidate_set_snapshot=group.candidate_ids(),
        supersedes_outcome_id=entry.supersedes_outcome_id,
    )
    return ValidationResult(valid=True, errors=[], outcome=outcome)
