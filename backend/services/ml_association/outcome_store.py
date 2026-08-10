"""Append-only JSONL persistence for reviewed outcomes.

Format choice: JSONL (one ``ReviewedOutcome`` JSON object per line),
matching this repository's existing lightweight-file conventions for
human-in-the-loop data (``training/unknown_tokens.csv``,
``training/engineering_corrections.jsonl`` -- see
``services/engineering/correction_dataset.py`` for the precedent of a
JSONL append log in this exact area of the codebase). No database
migration is introduced: the repository has no SQL database anywhere
(confirmed in docs/geometry_graph_audit/01_workflow_map.md -- all
persistence here is file-based), so adding one now, for one new append-
only log, would be a disproportionate architectural change for what
this phase needs. JSONL gives us exactly the properties required --
append-only, line-diffable, human-inspectable, no server dependency --
without introducing anything new to operate.

Every write is append-only: existing lines are never rewritten, and a
duplicate ``outcome_id`` is rejected before it reaches the file. See
``schemas.ReviewedOutcome.supersedes_outcome_id`` for how a correction
is represented (a NEW row, not a mutation).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from config import settings
from services.ml_association.enums import AdjudicationStatus
from services.ml_association.schemas import ReviewedOutcome

# Mirrors services.engineering.correction_dataset's append-lock pattern for
# the same reason: multiple reviewer submissions could race on the same
# JSONL file otherwise.
_lock = threading.Lock()


class OutcomeStoreError(Exception):
    """Base class for outcome_store integrity violations."""


class DuplicateOutcomeError(OutcomeStoreError):
    """Raised when appending an outcome whose ID already exists."""


class SupersedesTargetNotFoundError(OutcomeStoreError):
    """Raised when ``supersedes_outcome_id`` does not reference a known outcome."""


def _resolve_path(path: Optional[Path]) -> Path:
    return path or settings.ml_association_outcomes_path


def iter_outcomes(path: Optional[Path] = None) -> Iterator[ReviewedOutcome]:
    """Stream every stored outcome, in append order (oldest first)."""

    resolved = _resolve_path(path)
    if not resolved.exists():
        return
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield ReviewedOutcome.model_validate_json(line)


def load_all_outcomes(path: Optional[Path] = None) -> List[ReviewedOutcome]:
    return list(iter_outcomes(path))


def existing_outcome_ids(path: Optional[Path] = None) -> set:
    return {outcome.outcome_id for outcome in iter_outcomes(path)}


def exists(outcome_id: str, path: Optional[Path] = None) -> bool:
    return any(o.outcome_id == outcome_id for o in iter_outcomes(path))


def append_outcome(outcome: ReviewedOutcome, path: Optional[Path] = None) -> ReviewedOutcome:
    """Append one outcome. Never rewrites or removes any existing line.

    Raises ``DuplicateOutcomeError`` if ``outcome.outcome_id`` already
    exists, and ``SupersedesTargetNotFoundError`` if
    ``supersedes_outcome_id`` is set but does not reference a known
    outcome -- callers (``review_import.py``/``validation.py``) should
    check these conditions themselves first to produce a structured
    ``ValidationError``; this is the store's own defense-in-depth
    against silent mutation regardless of caller discipline.
    """

    resolved = _resolve_path(path)
    with _lock:
        known_ids = existing_outcome_ids(resolved)
        if outcome.outcome_id in known_ids:
            raise DuplicateOutcomeError(
                f"outcome_id {outcome.outcome_id!r} already exists; outcomes are append-only"
            )
        if outcome.supersedes_outcome_id and outcome.supersedes_outcome_id not in known_ids:
            raise SupersedesTargetNotFoundError(
                f"supersedes_outcome_id {outcome.supersedes_outcome_id!r} does not "
                "reference a known outcome"
            )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(outcome.model_dump(mode="json"), ensure_ascii=False)
        with resolved.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return outcome


def latest_outcomes(path: Optional[Path] = None) -> Dict[str, ReviewedOutcome]:
    """The single latest valid outcome per ``group_id``, with full
    history still retrievable via ``load_all_outcomes``/``history_for_group``.

    Deterministic definition of "latest valid":
    1. Exclude any outcome referenced by another outcome's
       ``supersedes_outcome_id`` (it has been superseded).
    2. Exclude any outcome whose ``adjudication_status`` is
       ``REJECTED_INVALID``.
    3. Among what remains for a group, prefer the highest
       ``reviewed_at`` (ISO-8601 strings sort correctly
       lexicographically); break ties by the higher ``outcome_id``
       string so the result is fully deterministic even with identical
       timestamps.
    """

    all_outcomes = load_all_outcomes(path)
    superseded_ids = {o.supersedes_outcome_id for o in all_outcomes if o.supersedes_outcome_id}

    by_group: Dict[str, List[ReviewedOutcome]] = {}
    for outcome in all_outcomes:
        if outcome.outcome_id in superseded_ids:
            continue
        if outcome.adjudication_status == AdjudicationStatus.REJECTED_INVALID:
            continue
        by_group.setdefault(outcome.group_id, []).append(outcome)

    latest: Dict[str, ReviewedOutcome] = {}
    for group_id_value, candidates in by_group.items():
        candidates.sort(key=lambda o: (o.reviewed_at, o.outcome_id))
        latest[group_id_value] = candidates[-1]
    return latest


def history_for_group(group_id: str, path: Optional[Path] = None) -> List[ReviewedOutcome]:
    """Full, unfiltered outcome history for one group, oldest first."""

    return [o for o in load_all_outcomes(path) if o.group_id == group_id]
