"""Prioritized human-review kit from the geometry evidence pack (R&D, offline)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


def prioritize_rows(rows: Sequence[Dict[str, Any]], *, limit: int = 108) -> List[Dict[str, Any]]:
    def key(row: Dict[str, Any]) -> tuple:
        status = row.get("status") or ""
        meta = (row.get("current_association") or {}).get("meta") or {}
        page = int(row.get("page") or 0)
        disagreement = 0 if status == "disagreement" else 1
        leader = 0 if meta.get("leader_resolved") else 1
        detail = 0 if page in {18, 24} else 1
        amb = 0 if "ambiguous" in status else 1
        return (disagreement, leader, detail, amb, page, str(row.get("token_id") or ""))

    ordered = sorted(rows, key=key)
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in ordered:
        tid = row.get("token_id")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def write_review_kit(rows: Sequence[Dict[str, Any]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    decisions = out_dir / "decisions"
    decisions.mkdir(exist_ok=True)
    index_items = []
    for row in rows:
        gid = str(row.get("token_id") or "unknown")
        page = write_group_page(row, out_dir)
        index_items.append(
            {
                "token_id": gid,
                "text": row.get("text"),
                "page": row.get("page"),
                "status": row.get("status"),
                "href": page.name,
            }
        )
    (out_dir / "manifest.json").write_text(
        json.dumps({"count": len(index_items), "groups": index_items}, indent=2)
    )
    gold_path = out_dir / "gold_outcomes.jsonl"
    if not gold_path.exists():
        gold_path.write_text("")
    index = [
        "<!doctype html><meta charset='utf-8'><title>Geometry gold review</title>",
        "<h1>Geometry association gold (human)</h1>",
        "<p>Decide before revealing the production pick. Do not invent thickness. Leaders are not members.</p>",
        "<ol>",
    ]
    for item in index_items:
        index.append(
            f"<li><a href='{html.escape(item['href'])}'>{html.escape(str(item['text']))}</a> "
            f"p{item['page']} ({html.escape(str(item['status']))})</li>"
        )
    index.append("</ol>")
    path = out_dir / "index.html"
    path.write_text("\n".join(index))
    return path


def write_group_page(row: Dict[str, Any], out_dir: Path) -> Path:
    token_id = str(row.get("token_id") or "unknown")
    cands = row.get("new_candidates") or []
    options = []
    for cand in cands:
        gid = html.escape(str(cand.get("geometry_id")))
        options.append(
            f"<label><input type='checkbox' name='target' value='{gid}'> "
            f"{gid} kind={html.escape(str(cand.get('geometry_kind')))} "
            f"d={cand.get('bbox_distance')} leader={cand.get('leader_supported')}</label><br>"
        )
    body = f"""<!doctype html><meta charset='utf-8'>
<title>{html.escape(token_id)}</title>
<h1>{html.escape(str(row.get('text')))} (page {row.get('page')})</h1>
<p>Label bbox: {html.escape(str(row.get('label_bbox')))}</p>
<form>
<p>Review label:
<select name='review_label'>
<option value='direct_target'>direct_target</option>
<option value='leader_support_not_target'>leader_support_not_target</option>
<option value='not_target'>not_target</option>
<option value='no_valid_target'>no_valid_target</option>
<option value='ambiguous_requires_adjudication'>ambiguous_requires_adjudication</option>
<option value='unavailable'>unavailable</option>
</select></p>
<p>Notes: <textarea name='reason' rows='3' cols='60'></textarea></p>
<p>Targets:</p>
{''.join(options) or '<p>No candidates</p>'}
<p><button type='button' onclick='this.nextElementSibling.hidden=false'>Reveal production pick</button>
<pre hidden>{html.escape(json.dumps(row.get('current_association'), indent=2))}</pre></p>
<p>Reviewer id: <input name='reviewer_id'></p>
<button type='button' onclick='save()'>Save decision</button>
</form>
<script>
function save(){{
  const targets=[...document.querySelectorAll('input[name=target]:checked')].map(x=>x.value);
  const payload={{
    token_id:{json.dumps(token_id)},
    review_label:document.querySelector('[name=review_label]').value,
    reviewed_target_geometry_ids:targets,
    reviewer_id:document.querySelector('[name=reviewer_id]').value,
    page:{json.dumps(row.get('page'))},
    text:{json.dumps(row.get('text'))},
    reason:(document.querySelector('[name=reason]')||{{}}).value||''
  }};
  const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download={json.dumps(token_id + '.decision.json')};
  a.click();
}}
</script>
"""
    path = out_dir / f"{token_id}.html"
    path.write_text(body)
    return path


def load_gold(outcomes_path: Path) -> Dict[str, List[str]]:
    gold: Dict[str, List[str]] = {}
    if not outcomes_path.exists() or not outcomes_path.read_text().strip():
        return gold
    for line in outcomes_path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        tid = rec.get("token_id")
        if not tid:
            continue
        if rec.get("review_label") in {"direct_target", "valid_secondary_target"}:
            gold[tid] = list(rec.get("reviewed_target_geometry_ids") or [])
    return gold
