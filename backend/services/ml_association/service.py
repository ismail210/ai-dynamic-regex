"""Feature-flag-gated public facade for the ml_association package.

Every function here calls ``require_enabled()`` first. With the default
configuration (``ML_ASSOCIATION_DATASET_ENABLED`` unset or falsy), every
one of these raises ``FeatureDisabledError`` immediately -- including
the read-only ``build_dataset``. This is deliberately uniform (not just
gating the write paths) so "is ml_association allowed to run at all
right now" has exactly one answer, and so tests can assert the disabled
default with a single check per function rather than reasoning about
which subset of operations happen to be gated.

This module is the ONLY intended entry point for callers outside this
package (routers, scripts, notebooks). ``candidate_dataset``,
``review_export``, ``review_import``, and ``outcome_store`` remain
importable directly for testing and composition, but production code
that wants to use this feature should go through here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from config import settings
from services.ml_association import candidate_dataset, outcome_store, review_export, review_import
from services.ml_association.schemas import (
    LabelGroup,
    ReviewedOutcome,
    ReviewExportPayload,
    ValidationResult,
)


class FeatureDisabledError(RuntimeError):
    """Raised by every service.py entry point when the feature flag is off."""


def is_enabled() -> bool:
    return bool(settings.ml_association_dataset_enabled)


def require_enabled() -> None:
    if not is_enabled():
        raise FeatureDisabledError(
            "ml_association is disabled by default. Set the environment "
            "variable ML_ASSOCIATION_DATASET_ENABLED=true to use it. See "
            "docs/ml_association_phase/review_workflow.md."
        )


def build_dataset(
    document_structure: dict,
    geometry: dict,
    *,
    project_id: str,
    document_id: str,
    created_at: str,
    **kwargs: Any,
) -> List[LabelGroup]:
    """Build deterministic label groups. See
    ``candidate_dataset.build_label_groups`` for the full parameter list.
    """

    require_enabled()
    return candidate_dataset.build_label_groups(
        document_structure,
        geometry,
        project_id=project_id,
        document_id=document_id,
        created_at=created_at,
        **kwargs,
    )


def export_groups(
    groups: List[LabelGroup],
    *,
    pdf_path: str,
    output_dir: Optional[Path] = None,
) -> List[ReviewExportPayload]:
    """Write JSON + SVG reviewer export files for each group."""

    require_enabled()
    resolved_dir = output_dir or settings.ml_association_export_dir
    return [
        review_export.write_group_export(group, pdf_path=pdf_path, output_dir=resolved_dir)
        for group in groups
    ]


def submit_review(
    raw: Dict[str, Any],
    group: LabelGroup,
    *,
    known_page_geometry_ids: Optional[Set[str]] = None,
    outcomes_path: Optional[Path] = None,
) -> ValidationResult:
    """Validate a reviewer submission and, if valid, append it as a new
    outcome. Returns the ``ValidationResult`` either way -- check
    ``result.valid`` before assuming anything was written.
    """

    require_enabled()
    existing_ids = outcome_store.existing_outcome_ids(outcomes_path)
    result = review_import.import_review(
        raw,
        group,
        known_page_geometry_ids=known_page_geometry_ids,
        existing_outcome_ids=existing_ids,
    )
    if result.valid and result.outcome is not None:
        outcome_store.append_outcome(result.outcome, path=outcomes_path)
    return result


def latest_outcomes(outcomes_path: Optional[Path] = None) -> Dict[str, ReviewedOutcome]:
    require_enabled()
    return outcome_store.latest_outcomes(outcomes_path)


def outcome_history(group_id: str, outcomes_path: Optional[Path] = None) -> List[ReviewedOutcome]:
    require_enabled()
    return outcome_store.history_for_group(group_id, outcomes_path)
