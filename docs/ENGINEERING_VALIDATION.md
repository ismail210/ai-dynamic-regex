# Engineering Validation & Structural Takeoff Architecture

## Goal

Support **AI-assisted engineering validation and structural takeoff** as backend
services used by the primary **Validation** UI (`/validation` → multimodal +
takeoff APIs). The standalone `/engineering` frontend page has been retired;
`/api/engineering/*` remains for pipeline/API access. Human review lives on
`/review`.

```
PDF → Rich Parse → Geometry → Graph → Excel → Match → Validate
    → Confidence → Classical ML Suggestions → Human Review
    → Correction Dataset → (future) Takeoff Excel Export
```

Primary product path (Validation / Upload):

```
PDF → Multimodal pipeline → Fusion → XGBoost → AISC verification → Review Queue
```

Legacy token path (still used by `/api/analyze` and takeoff export):

```
PDF → Text → Tokens → Classify → Regex Learn → Review Queue
```

## Module Map

| Module | Path | Responsibility |
|--------|------|----------------|
| PDF Parser (extended) | `backend/services/pdf_parser.py` | Legacy text + rich JSON structure |
| Geometry Extractor | `backend/services/engineering/geometry_extractor.py` | Lines, curves, dims, symbols, bbox metrics |
| Graph Builder | `backend/services/engineering/graph_builder.py` | Nodes + spatial/semantic edges |
| Excel Loader | `backend/services/engineering/excel_loader.py` | Project schedule + AISC catalog JSON |
| Matching Engine | `backend/services/engineering/matching_engine.py` | Extracted vs Excel discrepancies |
| Validation Engine | `backend/services/engineering/validation_engine.py` | Extraction quality report |
| Object Confidence | `backend/services/engineering/object_confidence.py` | Text/geometry/match/overall scores |
| Suggestion Engine | `backend/services/engineering/suggestion_engine.py` | Classical ML suggestions (no LLM) |
| Correction Dataset | `backend/services/engineering/correction_dataset.py` | HITL training samples (JSONL) |
| Takeoff Interface | `backend/services/engineering/takeoff_interface.py` | Preview + future exporter stubs |
| Pipeline | `backend/services/engineering/pipeline.py` | Orchestrator |
| API | `backend/routers/engineering.py` | `/api/engineering/*` |

## JSON Schemas (summary)

### Document structure (`document.json`)

```json
{
  "document_id": "doc_...",
  "page_count": 1,
  "layers": ["..."],
  "pages": [{"page_number": 1, "width": 612, "height": 792, "rotation": 0}],
  "words": [{"object_id": "word_...", "text": "...", "bbox": [x0,y0,x1,y1], "font_size": null, "rotation": 0, "page_number": 1, "reading_order": 0, "neighbors": [], "drawing_references": []}],
  "lines": [{"object_id": "line_...", "text": "...", "bbox": [...], "font_size": 12.0, "rotation": 0.0, "spans": [], "neighbors": []}],
  "blocks": [{"object_id": "block_...", "text": "...", "bbox": [...], "line_ids": []}]
}
```

### Geometry (`geometry.json`)

```json
{
  "geometry_count": 12,
  "counts_by_kind": {"line": 4, "rectangle": 2, "circle": 1},
  "objects": [{
    "geometry_id": "geom_...",
    "kind": "line|polyline|curve|arc|circle|rectangle|dimension|leader|symbol|block|path",
    "bbox": [x0,y0,x1,y1],
    "length": 120.5,
    "width": 40.0,
    "area": 100.0,
    "center": [x,y],
    "orientation": 0.0,
    "page_number": 1
  }]
}
```

### Graph (`graph.json`)

```json
{
  "nodes": [{"node_id": "txt_...", "kind": "text|label|beam|column|geometry|dimension", "text": "W18X35", "bbox": [...], "center": [...]}],
  "edges": [{"edge_id": "edge_...", "source": "...", "target": "...", "relationship": "nearest_label|nearest_geometry|distance|intersection|containment|touching|connected|reference", "distance": 24.5}]
}
```

### Match statuses

`perfect_match`, `missing_label`, `wrong_label`, `missing_geometry`, `extra_geometry`, `extra_label`, `count_mismatch`, `length_mismatch`, `width_mismatch`

### Confidence

```json
{
  "object_id": "...",
  "text_confidence": 0.82,
  "geometry_confidence": 0.71,
  "matching_confidence": 0.90,
  "overall": 0.81,
  "level": "High"
}
```

### Suggestion (classical ML)

```json
{
  "object_id": "...",
  "expected_label": "W18X35",
  "expected_type": "Beam",
  "confidence": 0.91,
  "reason": "Exact AISC database match; nearby geometry support",
  "features": {"min_distance": 18.2, "has_geometry_link": 1.0}
}
```

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/documents` | Upload-only PDF registration |
| POST | `/api/documents/{document_id}/extract` | Engineering extraction |
| POST | `/api/documents/{document_id}/analyze` | Multimodal analysis and validation |
| POST | `/api/engineering/excel/parse` | Excel → JSON |
| GET | `/api/engineering/aisc-catalog` | Sample AISC JSON |
| GET | `/api/engineering/artifacts/{document_id}/{name}` | Persisted JSON artifact |
| GET | `/api/engineering/pdf/{filename}` | Serve uploaded PDF for review UI |
| POST | `/api/engineering/corrections` | Save human correction sample |
| GET | `/api/engineering/corrections` | List correction dataset |
| POST | `/api/takeoff/generate` | Generate takeoff from analyzed document |

`/upload/` remains an upload-only compatibility alias.

## Human Review

Frontend routes: `/validation` (multimodal + Excel) and `/review` (HITL queue).  
Shows PDF, detected labels, geometry summary, match findings, suggestions, and Approve / Reject / Edit actions that write to `training/engineering_corrections.jsonl`.

## Future Learning

Corrections with `ready_for_training=true` are stored for a future classical ML retrain job. Deep learning is intentionally out of scope.

## Future Takeoff Export

`takeoff_interface.py` defines `TakeoffExporter`, `ExcelTakeoffExporter`, and `build_takeoff_preview()`. Exporters raise `NotImplementedError` until productized.
