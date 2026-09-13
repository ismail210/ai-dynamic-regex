"""Thin orchestration layer wiring the semantic_preprocessor pipeline into
the existing staged-document architecture.

Routers call into this module; this module calls into
``services.semantic_preprocessor`` and the existing ``document_registry`` /
``artifact_store``. No router imports the pipeline directly (see
``.claude/rules/backend.md``: routers are HTTP transport only).

Persistence reuses the existing per-document artifact store
(``services.artifact_store``) under the artifact name ``"semantic.json"`` --
no new storage mechanism was introduced.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from services.artifact_store import read_artifact, write_artifact
from services.document_registry import document_source
from services.pdf_parser import extract_document_structure
from services.semantic.models import OperationKind, OperationRecord, ReviewStatus
from services.semantic.serialization import load_semantic_document, to_dict
from services.semantic_preprocessor.extraction import build_text_primitives
from services.semantic_preprocessor.pipeline import process_primitives
from services.semantic_preprocessor.structural_parser import parse_structural_label

_ARTIFACT_NAME = "semantic.json"
_NOTE_LINE_RE = re.compile(r'^"(?P<trigger>[A-Z0-9]+)"\s*=\s*(?P<target>[A-Z0-9x./]+)$', re.IGNORECASE)


def extract_abbreviation_note_rules(structure: dict) -> list[dict]:
    """Real, minimal drawing-language-rule extractor.

    Matches ONLY the literal `"TRIGGER" = TARGET` shape (a real, common
    general-note convention for member-size abbreviations), and validates
    the target against the real structural grammar before accepting it --
    this is what rejects incidental unrelated quoted text elsewhere in a
    drawing (e.g. a callout note that happens to also use quote-equals
    punctuation for something else). Every accepted rule keeps the real
    page number, bbox, and quoted line as its source evidence.

    This is intentionally narrow. It is not the full Drawing Language
    Profile prototype (see docs/upstream_semantic_preprocessor.md) -- that
    remains uncommitted, in the sibling `ai-dynamic-regex-dlp` worktree,
    and should replace this function once promoted.
    """
    rules = []
    for line in structure.get("lines", []):
        match = _NOTE_LINE_RE.match(line["text"].strip())
        if not match:
            continue
        trigger = match.group("trigger").upper()
        target = match.group("target").upper()
        if trigger == target:
            continue
        target_parse = parse_structural_label(target)
        if not target_parse.is_structural or target_parse.grammar == "incomplete":
            continue
        rules.append({
            "rule_id": f"note_{trigger}",
            "trigger": trigger,
            "result": target,
            "rule_status": "source_verified",
            "scope": {"pages": []},
            "source_evidence": [{
                "page": line["page_number"],
                "bbox": line["bbox"],
                "quote": line["text"],
            }],
            "confidence": 0.95,
        })
    return rules


def get_cached_semantic_document(document_id: str) -> Optional[dict]:
    return read_artifact(document_id, _ARTIFACT_NAME)


def run_semantic_pipeline(document_id: str, *, force: bool = False) -> dict:
    """Run (or return the cached result of) the semantic pipeline for a document.

    Runs with no geometry provider -- there is no live Rhino.Compute
    integration anywhere in this codebase (see docs/ghx_geometry_audit.md),
    so geometry evidence is simply absent rather than faked. This matches
    the architectural invariant that the semantic pipeline must succeed
    without Grasshopper.
    """
    if not force:
        cached = get_cached_semantic_document(document_id)
        if cached is not None:
            return cached

    pdf_path = str(document_source(document_id))
    structure = extract_document_structure(pdf_path)
    primitives, page_classes = build_text_primitives(structure)
    rules = extract_abbreviation_note_rules(structure)

    document = process_primitives(
        primitives,
        document_id=document_id,
        drawing_language_rules=rules,
    )
    payload = to_dict(document)
    payload["diagnostics"]["page_classes"] = {str(k): v for k, v in page_classes.items()}
    write_artifact(document_id, _ARTIFACT_NAME, payload)
    return payload


def apply_review_action(
    document_id: str, annotation_id: str, action: str, edited_text: Optional[str] = None
) -> dict:
    """Apply a reviewer decision to one annotation and persist it.

    Session/file-scoped persistence: this writes back to the same
    per-document artifact the pipeline itself produces, via the existing
    artifact store -- not an in-memory-only mock, but also not a durable
    audit-trail database. Sufficient for this sprint; a real review-history
    table is the natural next step (see docs/upstream_semantic_preprocessor.md).
    """
    document_dict = get_cached_semantic_document(document_id)
    if document_dict is None:
        raise KeyError(f"No semantic document cached for {document_id!r}")

    document = load_semantic_document(document_dict)
    annotation = next(
        (a for a in document.annotations if a.annotation_id == annotation_id), None
    )
    if annotation is None:
        raise LookupError(f"Annotation {annotation_id!r} not found")

    if action == "accept":
        annotation.review.status = ReviewStatus.HUMAN_ACCEPTED
    elif action == "reject":
        # Preserve the proposal -- never mutate the annotation as though it
        # never existed (Section 45). Mark the last operation as no longer
        # in effect; effective_text then falls back to the prior accepted
        # operation (or the original text) on its own.
        annotation.review.status = ReviewStatus.HUMAN_REJECTED
        if annotation.operations:
            annotation.operations[-1].accepted = False
    elif action == "edit":
        if not edited_text:
            raise ValueError("edited_text is required for the 'edit' action")
        prior = annotation.current_operation
        annotation.operations.append(
            OperationRecord(
                operation=prior.operation if prior else OperationKind.KEEP,
                input_text=annotation.effective_text,
                output_text=edited_text,
                deterministic=False,
                provenance="human",
            )
        )
        annotation.review.status = ReviewStatus.HUMAN_ACCEPTED
    else:
        raise ValueError(f"Unknown review action: {action!r}")

    annotation.review.history.append({"action": action, "edited_text": edited_text})

    payload = document.to_dict()
    write_artifact(document_id, _ARTIFACT_NAME, payload)
    return next(a for a in payload["annotations"] if a["annotation_id"] == annotation_id)


def list_review_queue(document_id: str) -> list[dict]:
    document = get_cached_semantic_document(document_id)
    if document is None:
        return []
    return [
        a for a in document["annotations"]
        if a["review_status"] == ReviewStatus.NEEDS_REVIEW.value
    ]


def document_summary(document: dict[str, Any]) -> dict[str, Any]:
    """Only-real-numbers summary for the top document bar (Section 8)."""
    annotations = document.get("annotations", [])
    op_counts = {"normalization": 0, "repair": 0, "completion": 0, "keep": 0}
    needs_review = 0
    geometry_linked = 0
    for a in annotations:
        op = a.get("correction", {}).get("operation", "keep")
        op_counts[op] = op_counts.get(op, 0) + 1
        if a.get("review_status") == ReviewStatus.NEEDS_REVIEW.value:
            needs_review += 1
        if a.get("geometry_associations"):
            geometry_linked += 1
    return {
        "annotation_count": len(annotations),
        "normalized_count": op_counts["normalization"],
        "repaired_count": op_counts["repair"],
        "completed_count": op_counts["completion"],
        "unchanged_count": op_counts["keep"],
        "needs_review_count": needs_review,
        "geometry_linked_count": geometry_linked,
        "drawing_rule_count": len(document.get("drawing_language_rules", [])),
    }
