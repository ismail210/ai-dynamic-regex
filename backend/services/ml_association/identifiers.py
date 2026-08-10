"""Deterministic identifier derivation for the ML-association package.

Every ID here is a SHA-1 hash of stable, semantically-meaningful inputs
-- never ``uuid.uuid4()``. This is a direct continuation of the Phase 1
fix to ``geometry_extractor._gid`` / ``graph_builder._nid``
(``docs/geometry_graph_audit/04_graph_audit.md`` §7): two runs over the
same inputs must always produce byte-identical IDs, so datasets, exports,
and outcome files stay diffable and reproducible.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Sequence


def _stable_id(prefix: str, *parts: object) -> str:
    seed = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def page_id(document_id: str, page_number: int) -> str:
    """Stable page identifier, scoped to its document."""

    return _stable_id("page", document_id, page_number)


def group_id(
    text_entity_id: str,
    candidate_generator_version: str,
) -> str:
    """Stable label-group (query group) identifier.

    Deliberately excludes the candidate set itself from the hash: a
    group's identity is "this label entity, under this generator
    version", not "this label plus whatever candidates happened to be
    found" -- otherwise a generator bugfix that changes candidate counts
    would silently orphan every previously-reviewed group for that
    label.
    """

    return _stable_id("group", text_entity_id, candidate_generator_version)


def association_candidate_id(
    text_entity_id: str,
    geometry_entity_id: Optional[str],
    candidate_generator_version: str,
) -> str:
    """Stable per-row identifier for one (label, geometry) candidate pair.

    ``geometry_entity_id=None`` is the reserved no-valid-target
    placeholder row -- see ``schemas.NO_MATCH_CANDIDATE_TOKEN``.
    """

    geometry_key = geometry_entity_id if geometry_entity_id is not None else "no_match"
    return _stable_id("assoc", text_entity_id, geometry_key, candidate_generator_version)


def outcome_id(
    group_id_value: str,
    reviewer_id: str,
    reviewed_at: str,
    supersedes_outcome_id: Optional[str] = None,
) -> str:
    """Stable reviewed-outcome identifier.

    Same reviewer + same group + same recorded ``reviewed_at`` timestamp
    always yields the same ID -- this is what lets
    ``outcome_store`` detect and reject an accidental duplicate
    resubmission (docs/ml_association_phase/schema.md "append-only
    outcomes"). A genuine correction must carry a new ``reviewed_at``
    (or a different reviewer), which naturally produces a new ID and is
    accepted as a supersession, not a duplicate.
    """

    return _stable_id(
        "outcome", group_id_value, reviewer_id, reviewed_at, supersedes_outcome_id
    )


def leader_path_id(leader_node_id: str, target_node_id: str) -> str:
    """Stable identifier for one resolved leader-path (leader -> target)."""

    return _stable_id("leaderpath", leader_node_id, target_node_id)
