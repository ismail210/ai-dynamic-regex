# First-Run Validation Guide

**Policy:** User-edited Excel is **not** official ground truth and **not** a predictor.  
It may be used only as a **reference / diff signal** for error classification.

The existing 8-document proxy-gold cache under  
`training/eval_cache_backups/doc_*/predictions_view.json` remains the **internal regression suite**. Do not overwrite it for stakeholder validation.

---

## Already persisted first-run outputs

After Analyze (`staged_pipeline` / multimodal pipeline), each document stores:

| Artifact | Path | Role |
|---|---|---|
| Raw predictions | `engineering_artifacts/<doc_id>/multimodal/predictions.json` | Full first-run model output (includes context definitions, quantity engine, duplicates) |
| Served prediction view | `engineering_artifacts/<doc_id>/multimodal/predictions_view.json` | First-run predictions as returned to the client (**comment in code: stays raw model output**) |
| Validation snapshot | `…/validation.json` | Pipeline validation summary |
| Optional Excel parse | `…/expected_excel.json` | Uploaded workbook for **this run’s comparison only** |

No new production write path was required — first-run is already preserved when `persist=True`.

---

## How to run a first-run report

```bash
cd backend
python scripts/evaluate_first_run.py --document-id doc_<id>
# Optional Excel as reference/diff only:
python scripts/evaluate_first_run.py --document-id doc_<id> --excel /path/to/workbook.xlsx \
  --output training/eval_cache_backups/first_run_<id>.json
```

---

## Metrics (separated — not one “accuracy”)

| Metric | Meaning |
|---|---|
| Extraction / missing extraction | Row present vs no section |
| Normalization / format correction | Spacing, `×`, case → catalog spelling |
| Catalog-match / catalog-equivalent | Exact or notation-equivalent (e.g. HSS decimals) |
| Incomplete-label recovery | **Semantic** — must stay abstained without evidence |
| Unsafe completion rate | Incomplete printed → completed catalog section |
| Abstention behavior | `missing_thickness` + not takeoff-eligible |
| Bounding-box coverage | Share of rows with `bounding_box` |
| Geometry-association coverage | Share with `geometry_preview` / `graph_preview` |
| Duplicate/repetition | From pipeline duplicate audit (see predictions.json) |

---

## Bounding box / geometry (audit only — no redesign)

| Step | Where |
|---|---|
| Text bbox | `services/pdf_parser.py` — word/span/line boxes from PDF extract |
| Prediction bbox | Carried on multimodal prediction rows as `bounding_box` |
| Association | `services/multimodal/spatial_association.py` — STRtree leader-aware link; result surfaced as `geometry_preview` / `graph_preview` |
| Eval today | First-run script reports **coverage** (has bbox / has preview). Distinguishing text error vs bbox error still needs **manual review** of crops + Excel/reference diff — no automatic IoU gold in-repo. |
| Bassam merge | Member-resolution / repeated-detail gating may change *which* row is takeoff-eligible; it does **not** replace bbox generation or reopen GraphSAGE. |

GraphSAGE / geometry-missing-label inference remain **disabled**.

**Format correction ≠ semantic inference**

- Format: `L4 x 4 x 1/4` → `L4X4X1/4` (OK)  
- Semantic: `L4X4` → `L4X4X1/4` (NOT OK without linked evidence)

---

## Error taxonomy labels

See `TAXONOMY` in `scripts/evaluate_first_run.py`  
(`ocr_error`, `normalization_error`, `punctuation_trailing_noise_error`,  
`unsafe_completion`, `incomplete_abstention_ok`, `catalog_equivalent_ok`, …).

---

## Recommended stakeholder flow

```text
RAW PDF
→ FIRST-RUN Analyze (persist artifacts)
→ evaluate_first_run.py on predictions_view
→ optional Excel reference DIFF (not GT)
→ REVIEW / manual correction
→ error classification by taxonomy
→ metrics by stage
```

Keep proxy-gold 8-doc cache for engineering regression only.

---

## Future AI / LLM (not implemented)

Bassam’s meeting LLM (`W8 → W8X10` style inference) is **not** in the consolidated `estima3d-integration` tree. Do not call external APIs or train a substitute.

Safest future slot (when a real model/repo is shared):

```text
PDF → extraction → engineering parser → normalization
  → candidate generation → AI/LLM candidate correction
  → evidence validation → takeoff eligibility
```

The LLM must **not** bypass evidence validation or incomplete-L/2L abstention.
