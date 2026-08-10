"""Strongly-typed enums for the ML-association review workflow.

Follows this repository's existing enum convention
(``services.engineering.models.NodeKind`` et al.): plain ``str, Enum``
subclasses so values serialize as their string value in JSON without a
custom encoder.
"""

from __future__ import annotations

from enum import Enum


class ReviewLabel(str, Enum):
    """What a reviewer decided about one (label, geometry candidate) pair."""

    DIRECT_TARGET = "direct_target"
    VALID_SECONDARY_TARGET = "valid_secondary_target"
    LEADER_SUPPORT_NOT_TARGET = "leader_support_not_target"
    NOT_TARGET = "not_target"
    NO_VALID_TARGET = "no_valid_target"
    AMBIGUOUS_REQUIRES_ADJUDICATION = "ambiguous_requires_adjudication"


class CalloutScope(str, Enum):
    """How many real-world members one label's review decision covers."""

    SINGLE = "single"
    MULTIPLE = "multiple"
    TYPICAL = "typical"
    REPEATED = "repeated"
    DETAIL_REFERENCE = "detail_reference"
    SCHEDULE_REFERENCE = "schedule_reference"
    UNKNOWN = "unknown"


class AdjudicationStatus(str, Enum):
    """Lifecycle state of a reviewed outcome, independent of its content."""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    NEEDS_SECOND_REVIEW = "needs_second_review"
    ADJUDICATED = "adjudicated"
    REJECTED_INVALID = "rejected_invalid"


class ValidationErrorCode(str, Enum):
    """Stable codes for review-import rejection reasons.

    Stable means: safe to branch on programmatically (e.g. in a reviewer
    UI) without parsing free-text messages. Every code below corresponds
    1:1 to one bullet in the Phase 2 spec's "Reject an imported review
    when..." list.
    """

    UNKNOWN_ID = "unknown_id"
    PROJECT_MISMATCH = "project_mismatch"
    DOCUMENT_MISMATCH = "document_mismatch"
    PAGE_MISMATCH = "page_mismatch"
    REGION_MISMATCH = "region_mismatch"
    GEOMETRY_NOT_ON_PAGE = "geometry_not_on_page"
    LABEL_NOT_FOUND = "label_not_found"
    TARGET_OUTSIDE_CANDIDATE_SET = "target_outside_candidate_set"
    MISSING_REVIEWER_ID = "missing_reviewer_id"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_REVIEW_LABEL = "invalid_review_label"
    INVALID_CALLOUT_SCOPE = "invalid_callout_scope"
    NO_VALID_TARGET_WITH_SELECTED_TARGETS = "no_valid_target_with_selected_targets"
    SINGLE_SCOPE_MULTIPLE_TARGETS = "single_scope_multiple_targets"
    MULTI_TARGET_SCOPE_NO_TARGETS = "multi_target_scope_no_targets"
    LEADER_SUPPORT_AS_FINAL_TARGET = "leader_support_as_final_target"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    DUPLICATE_OUTCOME_ID = "duplicate_outcome_id"
    OUTCOME_WOULD_BE_OVERWRITTEN = "outcome_would_be_overwritten"
    FEATURE_DISABLED = "feature_disabled"
