"""Build a local-only, static HTML review kit for a human-review batch.

Reads the JSON+SVG exports already produced by
``services.ml_association.service.export_groups`` (see
``docs/ml_association_phase/human_review_batch_manifest.json`` for how
the batch was selected) and generates one self-contained HTML page per
label group plus an index page, all written into the git-ignored
``backend/training/ml_association/real_project_pilot/review_kit/``
directory.

This script is tracked in version control (it contains no project data
or confidential content -- it is a template/generator, mirroring
``backend/scripts/evaluate_pipeline.py``'s existing pattern of a
tracked, reusable offline tool). Its OUTPUT is never tracked; the output
directory lives under the same ignored ``real_project_pilot/`` tree as
every other pilot artifact.

Bias-reduction measures (per docs/ml_association_phase/human_review_protocol.md):

* Candidates are displayed in a DETERMINISTIC HASH-BASED order, not the
  production ranking order, so the reviewer does not see the current
  heuristic's implicit preference through candidate position.
* The current heuristic's selection is never highlighted before a
  decision is made -- it is hidden behind an explicit "reveal" button
  the reviewer is instructed to press only after deciding.
* The true production rank/selection is preserved in the page's embedded
  metadata (for the reveal panel and for later analysis), never deleted.

No server component: each page's "Save decision" button uses only
browser JavaScript to build a JSON file matching
``services.ml_association.schemas.ReviewImportEntry`` and triggers a
local file download -- nothing is transmitted anywhere. A companion
script, ``import_review_decisions.py``, batch-imports the downloaded
decision files through the existing validated import pipeline.
"""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, List

EXPORTS_DIR = Path(__file__).resolve().parents[1] / "training" / "ml_association" / "real_project_pilot" / "exports"
BATCH_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "ml_association_phase" / "human_review_batch_manifest.json"
)
REVIEW_INDEX_PATH = (
    Path(__file__).resolve().parents[1]
    / "training"
    / "ml_association"
    / "real_project_pilot"
    / "working_notes"
    / "review_index.json"
)
OUTPUT_DIR = (
    Path(__file__).resolve().parents[1] / "training" / "ml_association" / "real_project_pilot" / "review_kit"
)

REVIEW_LABEL_OPTIONS = [
    ("direct_target", "Direct target -- this candidate IS the physical member"),
    ("valid_secondary_target", "Valid secondary target -- one of several correct targets"),
    ("leader_support_not_target", "Leader support -- this is leader evidence, NOT a final target"),
    ("not_target", "Not the target -- a real entity, but wrong for this label"),
    ("no_valid_target", "No valid target exists among the candidates (or at all)"),
    ("ambiguous_requires_adjudication", "Ambiguous -- needs a second reviewer"),
]

CALLOUT_SCOPE_OPTIONS = [
    "single", "multiple", "typical", "repeated", "detail_reference", "schedule_reference", "unknown",
]


def _display_order_key(candidate_id: str, group_id: str) -> str:
    """Deterministic, hash-based display order -- independent of the
    production ranking order, so position on screen never leaks the
    current heuristic's preference."""

    return hashlib.sha1(f"{group_id}|{candidate_id}".encode("utf-8")).hexdigest()


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _render_candidate(candidate: Dict[str, Any], display_rank: int) -> str:
    is_placeholder = candidate.get("is_no_match_placeholder")
    cid = candidate["association_candidate_id"]
    if is_placeholder:
        return (
            f'<div class="candidate placeholder" data-candidate-id="{_esc(cid)}">'
            f"<strong>Option {display_rank}: NO VALID TARGET</strong>"
            f"<div class=\"muted\">Select this if none of the listed candidates are correct.</div>"
            f"</div>"
        )
    geom = candidate.get("geometry") or {}
    rel = candidate.get("relationship") or {}
    leader_badge = (
        '<span class="badge leader">leader-resolved evidence</span>' if rel.get("leader_support_evidence") else ""
    )
    return f"""
    <div class="candidate" data-candidate-id="{_esc(cid)}">
      <label>
        <input type="checkbox" class="target-checkbox" value="{_esc(cid)}" />
        <strong>Option {display_rank}</strong> -- id {_esc(cid[:16])} {leader_badge}
      </label>
      <div class="candidate-detail">
        geometry_kind: {_esc(geom.get('geometry_kind'))} |
        bbox: {_esc(geom.get('geometry_bbox'))} |
        centroid_distance: {_esc(rel.get('centroid_distance'))} |
        graph_degree: {_esc(rel.get('graph_degree'))}
      </div>
    </div>
    """


def _render_group_page(payload: Dict[str, Any], svg_relative_path: str, review_row: Dict[str, Any]) -> str:
    group = payload["group"]
    label = group["label"]
    candidates = group["candidates"]

    ordered = sorted(candidates, key=lambda c: _display_order_key(c["association_candidate_id"], group["group_id"]))

    candidate_html = "\n".join(_render_candidate(c, i + 1) for i, c in enumerate(ordered))

    review_label_html = "\n".join(
        f'<label class="radio"><input type="radio" name="review_label" value="{value}" required /> {_esc(desc)}</label>'
        for value, desc in REVIEW_LABEL_OPTIONS
    )
    callout_scope_html = "\n".join(
        f'<label class="radio"><input type="radio" name="callout_scope" value="{value}" required /> {_esc(value)}</label>'
        for value in CALLOUT_SCOPE_OPTIONS
    )

    nearby = group.get("nearby_label_ids") or []
    diagnostics = group.get("extraction_diagnostics") or {}
    geometry_diagnostics = diagnostics.get("geometry") or {}
    graph_diagnostics = diagnostics.get("graph") or {}
    cap_applied = geometry_diagnostics.get("drawing_cap_applied")
    window_triggered = graph_diagnostics.get("geometry_pairwise_window_triggered")

    heuristic_selection_id = payload.get("heuristic_selection_candidate_id")

    # Embed the group's raw data as JSON for the JS layer to use when building the export.
    export_context = {
        "group_id": group["group_id"],
        "project_id": group["project_id"],
        "document_id": group["document_id"],
        "page_id": group["page_id"],
        "text_entity_id": group["text_entity_id"],
        "export_schema_version": payload.get("export_schema_version"),
        "candidate_ids": [c["association_candidate_id"] for c in candidates if not c.get("is_no_match_placeholder")],
    }

    return f"""<!doctype html>
<html><head><meta charset="utf-8" />
<title>Review: {_esc(group['group_id'][:16])}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #0b0f14; color: #e6edf3; }}
h1, h2 {{ font-weight: 600; }}
.meta {{ color: #9aa7b2; font-size: 0.9em; margin-bottom: 12px; }}
.panel {{ background: #131a22; border: 1px solid #26313c; border-radius: 8px; padding: 14px; margin-bottom: 14px; }}
.svg-wrap {{ max-height: 70vh; overflow: auto; border: 1px solid #26313c; border-radius: 6px; background: #fff; }}
.svg-wrap object {{ width: 100%; }}
.candidate {{ border: 1px solid #26313c; border-radius: 6px; padding: 8px; margin: 6px 0; background: #0e141b; }}
.candidate.placeholder {{ border-style: dashed; }}
.candidate-detail {{ font-size: 0.82em; color: #9aa7b2; margin-top: 4px; }}
.badge {{ font-size: 0.75em; padding: 2px 6px; border-radius: 10px; background: #2b3f2b; color: #b7f5b7; margin-left: 6px; }}
.radio {{ display: block; margin: 4px 0; }}
button {{ background: #1f6feb; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.95em; }}
button.secondary {{ background: #30363d; }}
textarea, input[type=text] {{ width: 100%; box-sizing: border-box; background: #0e141b; color: #e6edf3; border: 1px solid #26313c; border-radius: 6px; padding: 6px; }}
#heuristic-reveal {{ display: none; margin-top: 10px; padding: 10px; border: 1px solid #5a3a1a; background: #1f160c; border-radius: 6px; }}
.muted {{ color: #9aa7b2; font-size: 0.85em; }}
</style>
</head>
<body>
<a href="index.html" class="muted">&larr; back to index</a>
<h1>Label group review</h1>
<div class="meta">
  project: {_esc(group['project_id'])} | page: {_esc(group['page_number'])} |
  group_id: {_esc(group['group_id'])}
</div>

<div class="panel">
  <h2>Source label</h2>
  <div><strong>Raw text:</strong> {_esc(label['raw_text'])}</div>
  <div><strong>Normalized text:</strong> {_esc(label.get('normalized_text')) or '<em>not computed in this phase</em>'}</div>
  <div><strong>Label type (extraction classification):</strong> {_esc(label.get('label_type'))}</div>
  <div class="muted">Neighboring label entity IDs on this page: {_esc(', '.join(nearby) or 'none recorded')}</div>
  <div class="muted">Region/detail boundary: not available -- no region-segmentation layer exists yet.</div>
  <div class="muted">Page diagnostics: cap_applied={_esc(cap_applied)},
    60-object window triggered={_esc(window_triggered)}</div>
</div>

<div class="panel">
  <h2>Drawing context</h2>
  <div class="svg-wrap"><object data="{_esc(svg_relative_path)}" type="image/svg+xml"></object></div>
</div>

<div class="panel">
  <h2>Candidates (order below is randomized and independent of the production system's ranking)</h2>
  {candidate_html}
</div>

<div class="panel">
  <h2>Your decision</h2>
  <form id="review-form">
    <h3>Review label</h3>
    {review_label_html}
    <h3>Callout scope</h3>
    {callout_scope_html}
    <h3>Candidate-generation miss</h3>
    <label class="radio"><input type="checkbox" id="cg-miss" /> The correct target is NOT among the listed candidates (specify its geometry ID below)</label>
    <input type="text" id="external-target-id" placeholder="external geometry ID, if candidate_generation_miss is checked" />
    <h3>Notes</h3>
    <textarea id="notes" rows="3" placeholder="optional notes"></textarea>
    <h3>Reviewer identity</h3>
    <input type="text" id="reviewer-id" placeholder="your reviewer ID (required)" required />
  </form>
</div>

<div class="panel">
  <button type="button" class="secondary" onclick="document.getElementById('heuristic-reveal').style.display='block'">
    Reveal current system's pick (only after you have decided)
  </button>
  <div id="heuristic-reveal">
    <strong>Current production heuristic's selection:</strong>
    {_esc(heuristic_selection_id) if heuristic_selection_id else '(no selection made by the current heuristic)'}
  </div>
</div>

<div class="panel">
  <button type="button" onclick="saveDecision()">Save decision (downloads a JSON file)</button>
  <div class="muted">Saved files should be collected into one local folder and imported with
    backend/scripts/import_review_decisions.py -- nothing is uploaded or transmitted anywhere.</div>
</div>

<script>
const CONTEXT = {json.dumps(export_context)};

function saveDecision() {{
  const form = document.getElementById('review-form');
  const reviewLabel = form.querySelector('input[name="review_label"]:checked');
  const calloutScope = form.querySelector('input[name="callout_scope"]:checked');
  const reviewerId = document.getElementById('reviewer-id').value.trim();
  if (!reviewLabel || !calloutScope || !reviewerId) {{
    alert('Please select a review label, a callout scope, and enter your reviewer ID.');
    return;
  }}
  const targets = Array.from(document.querySelectorAll('.target-checkbox:checked')).map(cb => cb.value);
  const cgMiss = document.getElementById('cg-miss').checked;
  const externalId = document.getElementById('external-target-id').value.trim();
  if (cgMiss && externalId) {{
    targets.push(externalId);
  }}
  const decision = {{
    export_schema_version: CONTEXT.export_schema_version,
    group_id: CONTEXT.group_id,
    project_id: CONTEXT.project_id,
    document_id: CONTEXT.document_id,
    page_id: CONTEXT.page_id,
    text_entity_id: CONTEXT.text_entity_id,
    review_label: reviewLabel.value,
    reviewed_target_geometry_ids: targets,
    candidate_generation_miss: cgMiss,
    callout_scope: calloutScope.value,
    reviewer_id: reviewerId,
    reviewed_at: new Date().toISOString(),
    annotation_notes: document.getElementById('notes').value || null
  }};
  const blob = new Blob([JSON.stringify(decision, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = CONTEXT.group_id + '.decision.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
}}
</script>
</body></html>
"""


def _render_index(rows: List[Dict[str, Any]]) -> str:
    items = "\n".join(
        f'<tr><td>{_esc(r["project_id"])}</td><td>{_esc(r["page_number"])}</td>'
        f'<td>{_esc(r["label_raw_text"])}</td><td>{_esc(r["candidate_count"])}</td>'
        f'<td>{_esc(r["has_leader_evidence"])}</td>'
        f'<td><a href="{_esc(r["group_id"])}.html">review</a></td></tr>'
        for r in rows
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8" /><title>ML-association human review kit</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #0b0f14; color: #e6edf3; padding: 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #26313c; padding: 6px 10px; text-align: left; }}
a {{ color: #58a6ff; }}
</style></head>
<body>
<h1>ML-association human review kit</h1>
<p>{len(rows)} label groups. See docs/ml_association_phase/human_review_protocol.md for instructions.</p>
<table>
<tr><th>Project</th><th>Page</th><th>Raw label</th><th>Candidates</th><th>Leader evidence</th><th></th></tr>
{items}
</table>
</body></html>
"""


def build_review_kit() -> None:
    review_index = json.loads(REVIEW_INDEX_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for row in review_index:
        group_json_path = EXPORTS_DIR / row["json_path"]
        payload = json.loads(group_json_path.read_text(encoding="utf-8"))
        svg_source = EXPORTS_DIR / row["svg_path"]
        svg_dest = OUTPUT_DIR / f"{row['group_id']}.svg"
        svg_dest.write_bytes(svg_source.read_bytes())

        page_html = _render_group_page(payload, svg_dest.name, row)
        (OUTPUT_DIR / f"{row['group_id']}.html").write_text(page_html, encoding="utf-8")

    (OUTPUT_DIR / "index.html").write_text(_render_index(review_index), encoding="utf-8")
    print(f"Wrote {len(review_index)} review pages + index to {OUTPUT_DIR}")


if __name__ == "__main__":
    build_review_kit()
