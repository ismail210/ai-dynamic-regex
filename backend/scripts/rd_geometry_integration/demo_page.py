"""Dedicated R&D comparison page (G6). Not Semantic Review production UI."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, Sequence


def write_comparison_page(
    rows: Sequence[Dict[str, Any]],
    overlay_rel: Dict[str, str],
    out_path: Path,
    *,
    metrics: Dict[str, Any],
) -> Path:
    cards = []
    for row in rows[:80]:
        tid = str(row.get("token_id") or "")
        img = overlay_rel.get(tid)
        img_html = f"<img src='{html.escape(img)}' alt='' style='max-width:100%'>" if img else ""
        decision = row.get("shadow_decision") or {}
        cards.append(
            "<article class='card'>"
            f"<h3>{html.escape(str(row.get('text')))} · p{row.get('page')}</h3>"
            f"<p>compare={html.escape(str(row.get('status')))} · "
            f"shadow={html.escape(str(decision.get('status')))} · "
            f"abstain={html.escape(str(decision.get('abstain_reason')))}</p>"
            f"{img_html}"
            "<p>Text bbox vs member bbox are shown on the crop (blue label, green candidates, dashed production).</p>"
            "</article>"
        )
    page = f"""<!doctype html>
<meta charset="utf-8">
<title>Geometry association comparison</title>
<style>
body{{font-family:sans-serif;margin:24px;max-width:1100px}}
.card{{border:1px solid #ccc;padding:12px;margin:12px 0}}
img{{border:1px solid #ddd}}
</style>
<h1>Geometry association evidence (R&amp;D)</h1>
<p>Opt-in comparison page. Not wired into Semantic Review or takeoff.
Status is evidence: associated / ambiguous / unavailable. Geometry does not complete section size.</p>
<pre>{html.escape(json.dumps(metrics, indent=2))}</pre>
{''.join(cards)}
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page)
    return out_path
