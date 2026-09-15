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
from datetime import datetime, timezone
from typing import Any, Optional

from services.artifact_store import read_artifact, write_artifact
from services.document_registry import document_source
from services.pdf_parser import extract_document_structure
from services.semantic.corrected_pdf import (
    build_corrected_pdf,
    corrected_pdf_download_name,
    describe_corrected_pdf,
    list_accepted_text_corrections,
    sync_corrected_pdf,
)
from services.semantic.models import OperationKind, OperationRecord, ReviewStatus
from services.semantic.repair_shadow import attach_repair_shadow
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
    # Shadow-mode only (repair-trace sprint, Section 2/23): attaches ranked
    # repair_candidates and an UNACCEPTED proposal operation to annotations
    # the deterministic layer left unresolved. Never changes effective_text
    # by itself -- see services.semantic.repair_shadow's module docstring.
    repair_summary = attach_repair_shadow(document)
    payload = to_dict(document)
    payload["diagnostics"]["page_classes"] = {str(k): v for k, v in page_classes.items()}
    payload["diagnostics"]["repair_shadow"] = {
        "evaluated": repair_summary.evaluated,
        "candidates_found": repair_summary.candidates_found,
        "no_candidates": repair_summary.no_candidates,
        "already_clean_skipped": repair_summary.already_clean_skipped,
    }
    write_artifact(document_id, _ARTIFACT_NAME, payload)
    return payload


def apply_review_action(
    document_id: str,
    annotation_id: str,
    action: str,
    edited_text: Optional[str] = None,
    candidate_text: Optional[str] = None,
) -> dict:
    """Apply a reviewer decision to one annotation and persist it.

    ``candidate_text`` is how "Accept proposal" and "Choose alternate"
    (repair-trace sprint, Section 18) share one action: it names which
    ``repair_candidates`` entry (or already-pending proposal operation) the
    human is accepting. When omitted, Accept applies the pending REPAIR
    proposal or the top ``repair_candidates`` entry when one exists; otherwise
    it only records human acceptance of the current effective text.

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

    prior_effective = annotation.effective_text

    if action == "accept":
        _apply_accept_to_annotation(annotation, candidate_text)
    elif action == "reject":
        # Preserve every proposal -- never mutate the annotation as though
        # it never existed (Section 45). Un-accept every REPAIR operation
        # specifically (not just the last one): the deterministic single-
        # char-confusion repair auto-accepts itself by construction (see
        # semantic_preprocessor.normalization._try_repair) BEFORE a shadow
        # proposal is ever appended, so rejecting only the most recent
        # operation would leave that earlier auto-applied repair in effect
        # -- a human "reject" must mean "no repair", not "undo whichever
        # proposal happened to be appended last". NORMALIZATION/COMPLETION
        # operations are untouched: rejecting a repair proposal never
        # un-does an unrelated, already-settled representation change.
        annotation.review.status = ReviewStatus.HUMAN_REJECTED
        if annotation.operations:
            annotation.operations[-1].accepted = False  # preserves prior single-operation behavior
        for op in annotation.operations:
            if op.operation == OperationKind.REPAIR:
                op.accepted = False
    elif action == "edit":
        if not edited_text:
            raise ValueError("edited_text is required for the 'edit' action")
        annotation.operations.append(
            OperationRecord(
                operation=OperationKind.REPAIR,
                input_text=annotation.effective_text,
                output_text=edited_text,
                reason_codes=["human_manual_edit"],
                deterministic=False,
                provenance="human_manual_edit",
                accepted=True,
            )
        )
        annotation.review.status = ReviewStatus.HUMAN_ACCEPTED
    else:
        raise ValueError(f"Unknown review action: {action!r}")

    annotation.review.history.append(
        {
            "action": action,
            "edited_text": edited_text,
            "candidate_text": candidate_text,
            "from_text": prior_effective,
            "to_text": annotation.effective_text,
            "page": annotation.page,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )

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


def _annotation_eligible_for_accept_all(annotation) -> bool:
    """Eligible = has a pending repair proposal or repair_candidates, not already decided."""
    status = annotation.review.status
    if status in (ReviewStatus.HUMAN_ACCEPTED, ReviewStatus.HUMAN_REJECTED, ReviewStatus.AUTO_ACCEPTED):
        return False
    if any(
        (not op.accepted and op.operation == OperationKind.REPAIR and op.output_text)
        for op in annotation.operations
    ):
        return True
    return bool(annotation.repair_candidates)


def _apply_accept_to_annotation(annotation, candidate_text: Optional[str] = None) -> None:
    """Mutate annotation in-place with the same Accept semantics as apply_review_action."""
    resolved_candidate = candidate_text
    if not resolved_candidate:
        pending = next(
            (
                o
                for o in reversed(annotation.operations)
                if (not o.accepted and o.operation == OperationKind.REPAIR and o.output_text)
            ),
            None,
        )
        if pending is not None:
            resolved_candidate = pending.output_text
        elif annotation.repair_candidates:
            resolved_candidate = annotation.repair_candidates[0].candidate_text

    if resolved_candidate:
        target_op = next(
            (
                o
                for o in reversed(annotation.operations)
                if not o.accepted and o.output_text == resolved_candidate
            ),
            None,
        )
        if target_op is None:
            candidate = next(
                (c for c in annotation.repair_candidates if c.candidate_text == resolved_candidate),
                None,
            )
            if candidate is None:
                raise ValueError(
                    f"{resolved_candidate!r} is not a known repair candidate for this annotation"
                )
            target_op = OperationRecord(
                operation=OperationKind.REPAIR,
                input_text=annotation.effective_text,
                output_text=resolved_candidate,
                reason_codes=list(candidate.reason_codes) + ["human_chose_alternate_candidate"],
                evidence=list(candidate.evidence),
                score=(candidate.scores[0] if candidate.scores else None),
                deterministic=False,
                provenance="human_reviewed_label_reconstruction",
                accepted=False,
            )
            annotation.operations.append(target_op)
        target_op.accepted = True
    annotation.review.status = ReviewStatus.HUMAN_ACCEPTED


def accept_all_eligible_corrections(document_id: str) -> dict:
    """Accept every eligible repair proposal, persist once, regenerate corrected PDF once."""
    document_dict = get_cached_semantic_document(document_id)
    if document_dict is None:
        raise KeyError(f"No semantic document cached for {document_id!r}")

    document = load_semantic_document(document_dict)
    accepted_ids: list[str] = []
    for annotation in document.annotations:
        if not _annotation_eligible_for_accept_all(annotation):
            continue
        prior_effective = annotation.effective_text
        _apply_accept_to_annotation(annotation)
        annotation.review.history.append(
            {
                "action": "accept",
                "edited_text": None,
                "candidate_text": None,
                "from_text": prior_effective,
                "to_text": annotation.effective_text,
                "page": annotation.page,
                "at": datetime.now(timezone.utc).isoformat(),
                "bulk": "accept_all",
            }
        )
        accepted_ids.append(annotation.annotation_id)

    payload = document.to_dict()
    write_artifact(document_id, _ARTIFACT_NAME, payload)
    corrected = sync_corrected_pdf(document_id, payload)
    return {
        "accepted_annotation_ids": accepted_ids,
        "accepted_count": len(accepted_ids),
        "document": payload,
        "summary": document_summary(payload, document_id=document_id),
        "corrected_pdf": corrected,
    }


def document_summary(document: dict[str, Any], document_id: Optional[str] = None) -> dict[str, Any]:
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
    summary = {
        "annotation_count": len(annotations),
        "normalized_count": op_counts["normalization"],
        "repaired_count": op_counts["repair"],
        "completed_count": op_counts["completion"],
        "unchanged_count": op_counts["keep"],
        "needs_review_count": needs_review,
        "geometry_linked_count": geometry_linked,
        "drawing_rule_count": len(document.get("drawing_language_rules", [])),
        "accepted_correction_count": len(list_accepted_text_corrections(document)),
    }
    if document_id:
        summary["corrected_pdf"] = describe_corrected_pdf(document_id, document)
    return summary


def get_benchmark_context(document_id: str) -> Optional[dict]:
    """Dev/demo only (Section 20/34): if this document is a registered copy
    of a PDF-attack-benchmark attacked file, return its manifest summary so
    the UI can show an "Attack Benchmark" badge. Returns None for any
    ordinary document -- this must never affect normal Semantic Review use
    (Section 35)."""
    from services.semantic import benchmark_bridge

    if not benchmark_bridge.is_benchmark_available():
        return None
    try:
        source_path = str(document_source(document_id))
    except (FileNotFoundError, ValueError):
        return None
    manifest = benchmark_bridge.find_manifest_for_document(source_path)
    if manifest is None:
        return None
    return benchmark_bridge.benchmark_summary(manifest)


def get_annotation_oracle(document_id: str, annotation_id: str) -> Optional[dict]:
    """Dev/demo only: the known-clean answer key for one annotation, IF this
    document is a recognized attack case AND that annotation matches a
    mutation/control by page+bbox. Never called from the repair path itself
    (see services.semantic.repair_shadow / test_module_never_imports_the_
    attack_benchmark_package) -- this is strictly a post-decision reveal for
    the reviewer, wired only from a dedicated endpoint."""
    from services.semantic import benchmark_bridge

    if not benchmark_bridge.is_benchmark_available():
        return None
    try:
        source_path = str(document_source(document_id))
    except (FileNotFoundError, ValueError):
        return None
    manifest = benchmark_bridge.find_manifest_for_document(source_path)
    if manifest is None:
        return None

    document_dict = get_cached_semantic_document(document_id)
    if document_dict is None:
        return None
    annotation = next(
        (a for a in document_dict.get("annotations", []) if a["annotation_id"] == annotation_id), None
    )
    if annotation is None:
        return None

    match = benchmark_bridge.oracle_for_annotation(
        manifest, annotation.get("page"), annotation.get("semantic_bbox")
    )
    if match is None:
        return None

    record = match["record"]
    if match["kind"] == "mutation":
        return {
            "kind": "mutation",
            "mutation_id": record["mutation_id"],
            "clean_text": record["clean_text"],
            "corrupted_text": record["corrupted_text"],
            "target_operation": record["target_operation"],
            "mutation_type": record["mutation_type"],
            "corruption_types": record["corruption_types"],
            "human_decision_matches_truth": annotation.get("effective_text") == record["clean_text"],
        }
    return {
        "kind": "clean_control",
        "clean_text": record["clean_text"],
        "human_decision_matches_truth": annotation.get("effective_text") == record["clean_text"],
    }


def export_corrected_pdf(document_id: str) -> tuple[Path, str, int]:
    """Build (or rebuild) the corrected PDF from original + accepted edits.

    Returns ``(path, download_filename, correction_count)``.
    """
    from pathlib import Path

    document = get_cached_semantic_document(document_id)
    if document is None:
        raise KeyError(f"No semantic document cached for {document_id!r}")
    corrections = list_accepted_text_corrections(document)
    if not corrections:
        raise ValueError("No accepted corrections to export")
    path = build_corrected_pdf(document_id, document)
    try:
        original_name = Path(document_source(document_id)).name
    except (FileNotFoundError, ValueError):
        original_name = document_id
    return path, corrected_pdf_download_name(document_id, original_name), len(corrections)
