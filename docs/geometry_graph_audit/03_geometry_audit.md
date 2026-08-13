# 03 — Deep Geometry Audit

Primary files: `backend/services/engineering/geometry_extractor.py` (444 lines), `geometry_adapters.py` (210 lines), `backend/services/pdf_parser.py` (545 lines), `pdf_pages.py` (86 lines), `backend/services/engineering/models.py`, `backend/services/multimodal/duplicate_detector.py`. Supplementary reads into `graph_builder.py`/`structural_graph.py` were required to answer questions 4/8/12 honestly, since geometry-shape classification alone does not carry structural semantics — see `04_graph_audit.md` for the full node/edge story.

## 1. What geometric representation is used at each stage?

| Stage | Representation | Units |
|---|---|---|
| Raw extraction | PyMuPDF `page.get_drawings()` vector paths (`geometry_extractor.py:272`): `l`/`c`/`re`/etc. items with point tuples | Raw PDF points (1/72") |
| Flattened object | `GeometryObject` dict: `bbox, center, length, width, height, area, aspect_ratio, orientation, points (≤64), kind` (`geometry_extractor.py:382-408`) | Raw PDF points, unconverted |
| Adapter enrichment | `+ object_id, angle(=orientation), centerline (points, if line/polyline/leader), profile (points, if rect/circle/curve/symbol), cross_section: None (always)` (`geometry_adapters.py:105-127`) | Same |
| Document wrapper | `GeometryDocument{units:"pdf_points", coordinate_system:"document", objects[...], layers[...]}` (`geometry_adapters.py:19-64`) | Honestly labeled `"pdf_points"` |
| Graph node | Geometry node dict, same numeric fields re-embedded (`graph_builder.py:142-161`) | Same, still raw |

**No "member axis" abstraction exists.** `cross_section` is a schema field that is always `None` — grepped repo-wide, no assignment site exists anywhere. The pipeline never derives an actual structural cross-section/axis from geometry; "member axis vs. drawing noise" is handled entirely downstream by regex-on-nearby-text, not by geometry shape (see §8 below and `04_graph_audit.md §1`).

## 2. Are transformations between coordinate systems explicit and tested?

No. `GeometryDocument.units = "pdf_points"` is set and honestly labeled, but **no downstream code ever converts or scales by it**. There is no scale-bar/title-block-scale detection, no `UserUnit` handling, and — critically — **no evidence that page rotation (`page.rotation`, captured for document-structure metadata in `pdf_parser.py:438`) is compensated for in geometry coordinates**; rotated-page drawing coordinates are used as PyMuPDF returns them, unverified against `page.rotation`. Zero tests exercise a rotated-page PDF.

## 3. Are units/scale carried with the geometry, or are thresholds based on raw coordinates?

Every threshold in the geometry-processing code is a **raw-coordinate magic number** — none are scale-aware. The single exception in the whole audited codebase is `matching_engine.py`'s catalog-dimension check (`length_tolerance=0.05`, `width_tolerance=0.05`, a relative 5% tolerance) — but that compares extracted *dimensions* against AISC catalog rows, not drawing coordinates, so it doesn't help geometry-stage decisions.

## 4. Which operations depend on hard-coded tolerances? (consolidated)

| Constant | Value | File:line | Scale-aware? |
|---|---|---|---|
| Circle aspect-ratio threshold | `1.15` | `geometry_extractor.py:126` | No |
| Circle width/height equality | `max(2.0, 0.08×max(w,h))` | `geometry_extractor.py:127` | Partially (8% relative term, but with a 2.0-unit floor) |
| Leader length band | `8.0–180.0` pt | `geometry_extractor.py:178` | No |
| Leader bbox min-dimension | `< 40.0` pt | `geometry_extractor.py:179` | No |
| Dimension min length | `≥ 12.0` pt | `geometry_extractor.py:188` | No |
| Nearby-text search radius | `48.0` pt | `geometry_extractor.py:199` | No |
| Nearest-object grid cell / k-NN | `180.0` pt, k=5 | `geometry_extractor.py:74-75` | No |
| Small-shape → SYMBOL | area `< 400` pt² | `geometry_extractor.py:379` | No |
| Dense-page drawing cap | `> 250` drawings/page | `geometry_extractor.py:292` | No (see bug, §7) |
| Prediction-dedup distance | `18.0` pt | `duplicate_detector.py:27` | No |
| Text-neighbor grid | `120.0` pt, k=5 | `pdf_parser.py:275-326` | No |
| Graph nearest-neighbor grid | `160.0` pt | `graph_builder.py:103` | No |
| Graph parallel/perpendicular angle | `8.0°` | `graph_builder.py:315,317` | **Yes** — angle is inherently scale-free, the one tolerance in the whole system that legitimately doesn't need to be |
| Catalog dimension match | `±5%` relative | `matching_engine.py:65-66` | **Yes** — proportional, not absolute |

No comment, config file, or commit message found that documents how any of the raw-coordinate constants were derived (empirical tuning vs. arbitrary guess is unknown — see `09_open_questions.md`).

## 5. Are tolerances global, page-specific, scale-aware, geometry-type-specific, or learned?

**Global and geometry-type-specific only.** Every constant above is a fixed module-level default; none are page-specific, none are derived from a detected drawing scale, and none are learned from the document. `structural_graph.py` reuses a *different* "how far is nearby" constant (`max_near_distance=180.0`) than `graph_builder.py`'s `max_edge_distance=160.0`, and `validation_engine.py` (dead code, see `04_graph_audit.md`) uses a third value, `far_label_distance=140.0` — three independently-tuned constants for a conceptually identical notion, with no shared source of truth.

## 6. How are near-collinear or fragmented lines merged?

**They are not merged anywhere in the codebase.** Grepped `services/engineering/` for merge/collapse/dedupe/stitch/combine — zero hits against vector geometry. Each PyMuPDF drawing path becomes exactly one `GeometryObject`; if the source PDF's authoring tool emitted one visual member as several separate path fragments (a common CAD-export artifact), Estima3D produces several unrelated objects with no reconciliation step. Whatever "merging" exists is only what PyMuPDF itself bundles into one `drawing["items"]` list — inherited from the source file, not app logic.

## 7. How are duplicated, overlapping, trimmed, or exploded entities handled?

At the raw-geometry level: **not handled at all** — no dedup pass over `GeometryObject`s exists. The only duplicate-handling logic in the geometry layer is `duplicate_detector.merge_duplicate_predictions()` (`duplicate_detector.py:24-107`), and it operates on **post-matching label predictions** (same page + same normalized label string + centroid distance ≤ 18.0 pt), not on overlapping/trimmed vector geometry. It is an O(n²) nested linear scan (no spatial index), acceptable at typical per-document prediction counts but a real quadratic loop.

**Correctness bug found — dense-page drawing cap (`geometry_extractor.py:292-305`)**: when a page has more than 250 raw drawings, the code keeps the 250 with the *largest bounding-box area*, on the stated rationale of keeping "structurally significant paths." But a perfectly horizontal or vertical straight line has `bbox.height=0` or `bbox.width=0`, so `_drawing_area()` returns **exactly 0.0** for essentially every clean orthogonal beam/column/grid-line stroke — precisely the entities this tool exists to extract. Python's stable sort puts all zero-area entities last, so on any page exceeding 250 raw drawings, orthogonal structural lines are the **first to be silently dropped**, while filled hatch regions and large rectangles are preferentially kept. This is the opposite of the stated intent and has no test coverage (the only geometry test PDF has 3 shapes total, never triggering this path).

## 8. How are beam axes distinguished from grid lines / dimension lines / leader lines / wall lines / detail geometry / borders / hatches?

**Direct answer: they are not, by geometry.** `GeometryKind` classification (`_classify_path`, `geometry_extractor.py:119-148`) is purely path-syntax-and-size based: `LINE / POLYLINE / CURVE / ARC / CIRCLE / RECTANGLE / PATH`, plus two narrow post-hoc reclassifications — `LEADER` (short stroke, 8–180pt, small bbox) and `DIMENSION` (stroke ≥12pt near numeric text). There is **no `GRID_LINE`, `BORDER`, or `HATCH` kind**, and no logic that suppresses borders or hatch fills from downstream processing (aside from the buggy area-based cap in §7). A rectangular sheet border becomes `RECTANGLE` (or `SYMBOL` if small); a hatch stroke becomes `LINE`/`PATH`/`CURVE` like any true member line, and both flow into the graph on equal footing.

"Beam"/"column" semantic typing happens only later, in `graph_builder._classify_text_node()` / `structural_graph._semantic_kind()`, and is driven entirely by **regex matches on nearby or attached text** (`BEAM_RE = r"^(W|S|M|HP|C|MC|WT|MT|ST|HSS|PIPE|L)\d"`), never by the line's own length, orientation, or layer. A `GeometryKind.BLOCK` enum member exists but is never produced by any classifier — dead.

**Order-dependency risk**: the leader check runs before the dimension check (`elif`, `geometry_extractor.py:373-376`); a short numeric-labeled stroke that also satisfies the leader geometry criteria is always classified `LEADER`, never reaching the dimension check — a real ambiguity in dense drawings where witness lines are also short.

## 9. Is there a spatial index?

A **uniform grid hash** (bucket by `floor(coord/cell_size)`, 3×3 neighborhood scan), not an R-tree/KD-tree/STRtree, is used in four independent places with four independent cell sizes:

| Location | Cell size | Purpose |
|---|---|---|
| `geometry_extractor._attach_nearest_objects` | 180.0 | geometry k-NN (k=5) — **output never consumed by anything downstream, grepped repo-wide** |
| `geometry_extractor._nearby_text` | 48.0 | nearest text line for classification hints |
| `pdf_parser._attach_neighbors` | 120.0 | text/word k-NN |
| `graph_builder.build_graph` nearest_label/nearest_geometry | 160.0 | 1-NN label↔geometry |

None of these four grids are shared, none share code, and none carry over into `structural_graph.py`'s own pairwise pass (see next question).

## 10. Are any association steps performing O(n²) comparisons?

Yes, in the geometry-adjacent layer:
- `duplicate_detector.merge_duplicate_predictions` — genuine nested-loop O(n²), no index (§7).
- `graph_builder.py`'s pairwise PARALLEL/PERPENDICULAR/INTERSECTS/CONTAINMENT/TOUCHING/CONNECTED/SUPPORTS pass is **not grid-indexed** — it takes `page_geom[:60]` (hard cap, drops everything past index 60 on a page) and compares each item only to the next 11 items **in extraction-order**, not spatial order (`graph_builder.py:281-283`). Two spatially adjacent lines that happen to be far apart in PyMuPDF's `get_drawings()` output order are simply never compared — their PARALLEL/INTERSECTS relationship is silently never detected, regardless of true proximity.
- `structural_graph.py` repeats the identical pattern at larger scale (`candidates[:350]`, window of 44) for beam/column/connection semantic edges.
- `graph_builder.py`'s `REFERENCE` edge pass (shared `drawing_references` between text nodes) is **fully unbounded O(n²)** with no windowing at all (`graph_builder.py:346-363`).

These are documented in detail in `04_graph_audit.md §5`, but are listed here because they directly determine which geometric relationships (parallel members, intersecting members, containment in a detail box) actually get computed — dense pages silently lose coverage.

## 11. Are geometric operations numerically robust?

Mostly yes for the simple cases (division-by-zero guards exist: `1e-6` epsilon in `_classify_path`, `aspect_ratio` falls back to `width` alone when `height==0`, `orientation` defaults to `0.0` when `len(points)<2`). But several operations are **systematically biased, not just imprecise**:
- **Curve length is a control-polygon chord sum, not true arc length** — Bezier control points are added to `points` and summed via `hypot`, which is always ≥ true arc length (worse for tightly curved arcs). No arc-length integration exists anywhere.
- **Orientation uses only the first and last point of the entire path** (`orientation = _orientation_deg(points[0], points[-1])`), even for multi-segment polylines — a zig-zag polyline gets a single chord angle, not a per-segment or best-fit orientation.
- **Area = bounding-box area, not true polygon area** — a rotated or thin diagonal shape has its footprint systematically overstated.

## 12. Behavior around edge cases

| Case | Behavior |
|---|---|
| Very short segments | No minimum-length filter; only affects LEADER/DIMENSION reclassification thresholds, not exclusion |
| Nearly parallel lines | Only evaluated inside the 8°-tolerance check in `graph_builder.py`, itself gated by the 60-item/window-12 truncation — many near-parallel pairs on dense pages are never compared at all |
| Curved members | Length overestimated (chord vs arc), orientation ignores curvature entirely |
| Rotated details | No evidence page rotation is compensated for; axis-aligned `"re"` rects are always parsed as axis-aligned bboxes |
| Multiple details on one page | No per-detail/viewport segmentation exists; all objects on a page are one flat pool related only by distance/bbox topology |
| Broken polylines / missing endpoints | Silently dropped if both `rect is None` and `points` is empty (`geometry_extractor.py:348-353`) — no warning, no count recorded in `page_summaries` |
| Coordinates with large magnitudes | Not specifically tested; no explicit bounds-checking found |

## 13. Which geometry decisions create the most downstream ambiguity?

1. **No geometry-native beam/grid/border/hatch distinction** (§8) — every downstream consumer (graph, matching, ranking) inherits this ambiguity and has to compensate with text-proximity heuristics instead of trusting geometry.
2. **The 250-drawing cap's zero-area sort bias** (§7) — actively removes the cleanest structural signal (orthogonal lines) on exactly the dense CAD-exported pages where automation matters most.
3. **The 60-item/window-12 (and 350/window-44) list-order pairwise caps** — geometric relationship coverage depends on incidental PDF-drawing-command order, not spatial layout; this is invisible in `graph.json` (no "coverage" flag is emitted) so downstream consumers cannot tell a missing PARALLEL/CONTAINMENT edge from "the geometries truly aren't related" vs. "they were never compared."
4. **No coordinate/unit/scale normalization** — every tolerance is a raw-point magic number, so behavior silently degrades on drawings plotted at a different scale or DPI than whatever the constants were tuned against.

---

## Geometry weaknesses table

| Problem | Current implementation | Failure example | Business impact | Severity | Frequency | Recommended fix | Est. effort |
|---|---|---|---|---|---|---|---|
| No scale/unit normalization | Raw PDF points everywhere, `units="pdf_points"` field unused downstream | A drawing plotted at 1/8"=1'-0" vs 1/4"=1'-0" gets identical raw-pt thresholds applied, causing under/over-merging | Silent accuracy drift across projects with different plot scales | High | Every document | Detect/derive scale from title block or `UserUnit`; carry a `scale_factor` alongside geometry; convert thresholds to real-world units | 3–5 days |
| 250-drawing cap drops orthogonal lines first | Sorts by raw bbox area descending, keeps top 250 (`geometry_extractor.py:292-305`) | Dense CAD-exported page with 400 drawings: every axis-aligned beam/column/grid line (bbox area=0) is dropped before large hatch fills | Missing structural members on complex sheets, silently | High | Any page >250 raw drawings (common on CAD-exported PDFs) | Sort by a "structural significance" proxy that doesn't penalize axis-aligned lines (e.g. length, or exclude zero-area bias) | 0.5–1 day |
| No collinear/fragmented line merging | None — each PyMuPDF path is one object | A member split into 3 path fragments by the CAD export becomes 3 unrelated `GeometryObject`s | Duplicate/fragmented candidates reach the graph and ranking layer | High | Common on DWG→PDF exports | Add a post-extraction merge pass (collinearity + endpoint proximity) before graph construction | 3–5 days |
| No beam-vs-grid/border/hatch distinction | Pure path-syntax classification, no layer/length/context awareness | A drawing border (`RECTANGLE`) and a hatch stroke (`LINE`) are graph nodes on equal footing with true member lines | Downstream graph/ranking noise, more false associations | High | Every document | Add geometry-native heuristics (aspect ratio + page-edge proximity for borders; density clustering for hatch) before node creation | 1–2 weeks |
| Pairwise relation windowing is list-order, not spatial | `page_geom[:60]`, window of next 11 (`graph_builder.py:281-283`); `page_nodes[:350]`, window 44 (`structural_graph.py:119-121`) | Two adjacent, genuinely parallel beams 15 positions apart in extraction order are never compared | Missing PARALLEL/CONTAINMENT/CONNECTED edges on dense pages, with no visible signal that coverage was incomplete | High | Any page near/above the caps | Replace with a real spatial index (grid or R-tree) so windowing is by proximity, not list position | 2–4 days |
| Curve length/orientation approximated | Chord-sum length, first/last-point orientation | An arc brace reports a shorter length than true, and an orientation that ignores its curvature | Wrong length/orientation features feed ranking for curved members | Medium | Rare (curved members uncommon in steel drawings) | Arc-length integration; per-segment or best-fit orientation for polylines | 2–3 days |
| Duplicate-merge is O(n²) | `duplicate_detector.py` nested loop, no index | Documents with very high token counts slow down at the merge step | Latency risk on large sheet sets, not yet a correctness bug | Low–Medium | Large documents only | Bucket by page+label before the distance check | 0.5 day |
| Silent drop of degenerate paths | `continue` with no counter when both `rect` and `points` are empty (`geometry_extractor.py:348-353`) | A malformed/degenerate path just vanishes with no diagnostic | Hard to debug missing members; no observability | Medium | Occasional | Record a `dropped_degenerate_count` in `page_summaries` | 0.5 day |
| No rotation compensation verified | Page `rotation` captured for document metadata, not demonstrably applied to geometry coords | A rotated detail view could have systematically wrong orientation/PARALLEL classification | Unverified — needs empirical test against a rotated-page PDF | Unknown (untested) | Rotated pages only | Add a rotated-page fixture test; explicitly transform coordinates by `page.rotation` if not already handled by PyMuPDF | 1–2 days incl. test |

Full per-function citations (formulas, thresholds, dead-code flags) are in `02_logic_inventory.md §C` and `algorithm_registry.csv`.
