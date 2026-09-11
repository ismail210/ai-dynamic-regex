"""
Ground-truth Excel parser for structural project estimate workbooks.

IMPORTANT
---------
Excel is used ONLY as ground truth during dataset creation and takeoff
validation -- never as an inference input for production prediction.

This is now a thin wrapper over
``services.takeoff.canonical_takeoff_eval.parse_workbook_ground_truth`` --
the single implementation shared by the production ``validate_takeoff`` path
and the research benchmark harness, so the UI can never show a number the
benchmark would not reproduce on the same inputs. That module classifies
every workbook row into an explicit scope bucket (primary framing / plates /
connection-misc / out-of-scope), canonicalizes sections against the AISC
catalog, and records what it excluded and why. The legacy ``items`` /
``aggregates`` / ``total_quantity`` / ``unique_labels`` keys it also returns
are populated from PRIMARY_FRAMING only, so existing consumers count real
members and never the ~6,000-row shop connection schedule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from services.takeoff.canonical_takeoff_eval import parse_workbook_ground_truth


def parse_ground_truth_excel(path: str | Path) -> Dict[str, Any]:
    """Parse a project estimate workbook into canonical ground-truth entities."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Ground-truth Excel not found: {file_path}")
    return parse_workbook_ground_truth(file_path)
