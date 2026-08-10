# 04 — Deep Graph Audit

Primary files: `backend/services/engineering/graph_builder.py` (383 lines, base spatial pass), `structural_graph.py` (301 lines, semantic enrichment), `matching_engine.py`, `rule_engine.py`, `suggestion_engine.py`, `object_confidence.py`, `validation_engine.py` (the `engineering/` one), `services/component_tracker.py`, `services/engineering_object_filter.py`, `services/entity_diagnostics.py`.

## Headline finding

**The graph is real (a genuine node/edge structure with spatial relations), but its influence on the final prediction is reduced to five scalar aggregates** (`degree`, `geometry_links`, `structural_links`, `min_distance`, `graph_consistency`), fed through a fixed attention prior (`weight=0.17`) into the fusion score. The graph's actual topology — which specific geometry a label is linked to, whether that link is a leader, whether it sits inside a detail box — is **never read back out** for prediction purposes in the live code path. Four of the ten audited files (`matching_engine.py`, `suggestion_engine.py`, `validation_engine.py` [the `engineering/` one], `object_confidence.py`) are **fully-built but not imported by any router or by the live pipeline** — exercised only by tests. This is stated plainly, not to imply the code is worthless — it is feature-complete and internally consistent — but it means roughly 40% of the "graph logic" inventory described below has zero effect on production predictions today.

## 1. Node schema

Nodes are plain Python `dict`s — **not** class instances, **not** networkx nodes (confirmed: no `networkx` import or dependency anywhere in `backend/`). Two construction sites, both in `graph_builder.build_graph` (`graph_builder.py:99-161`):

**Text/label node** (`graph_builder.py:112-139`), one per `document_structure["engineering_tokens"]` entry:
```python
{
  "node_id": "txt_<uuid4[:10]>", "source_id": token["token_id"],
  "kind": <NodeKind>, "page_number": ..., "text": ..., "bbox": ..., "center": [...],
  "font_size": ..., "rotation": ..., "drawing_references": [...],
  "engineering_object_type": ...,
}
```
`kind` resolves via `_OBJECT_NODE_KIND` dict lookup, falling back to `_classify_text_node()` regex (`LABEL_RE`, `COLUMN_HINT_RE`, `BEAM_RE`).

**Geometry node** (`graph_builder.py:142-161`), one per `geometry["objects"]` entry:
```python
{
  "node_id": "geo_<uuid4[:10]>", "source_id": geom["geometry_id"],
  "kind": <DIMENSION|GEOMETRY|CONNECTION(if leader)>, "page_number": ..., "text": geom["nearby_text"],
  "bbox": ..., "center": ..., "geometry_kind": ..., "length": ..., "width": ..., "area": ..., "orientation": ...,
}
```
`NodeKind` enum (`models.py:27-39`): `TEXT, GEOMETRY, DIMENSION, LABEL, BEAM, COLUMN, PLATE, BRACE, BOLT, WELD, CONNECTION, OTHER`. **`OTHER` is never assigned** — dead enum member at this layer.

**Node IDs are non-deterministic**: `_nid() = f"{prefix}_{uuid.uuid4().hex[:10]}"` — a fresh, unseeded UUID4 per call. Running the same document twice produces different `node_id`/`edge_id` strings even when the underlying topology is identical, which breaks byte-for-byte diffing/caching of `graph.json` and means any downstream code keying off `node_id` directly is implicitly fragile (most code correctly keys off the stable `source_id` instead).

**Enrichment overwrite**: `structural_graph.build_structural_graph` (`structural_graph.py:80-93`) mutates every node in place — `node["base_kind"] = node["kind"]`, then `node["kind"] = _semantic_kind(node)` **overwrites** the original classification with a second, independently-written regex classifier (`_ENTITY_RULES`, `structural_graph.py:19-27`: bolt/weld/plate/brace/column/beam/connection). Any code reading `node["kind"]` after this point cannot tell, from the key alone, which of the two classifiers produced the value.

## 2. Edge schema

Edges are `dict`s: `{edge_id, source, target, relationship, distance, weight, page_number, meta}`. All edges carry directional `source`→`target` fields, but directionality is **inconsistently enforced per relation type** — some relations emit both directions as separate edge dicts (`CONTAINMENT`+reverse `INSIDE`), others only one (`PARALLEL`, `PERPENDICULAR`).

`RelationKind` enum (`models.py:42-61`), all 19 members emitted somewhere: `NEAREST_LABEL, NEAREST_GEOMETRY, DISTANCE, INTERSECTION, CONTAINMENT, TOUCHING, CONNECTED, CONNECTED_TO, SUPPORTS, INTERSECTS, INSIDE, ADJACENT, PARALLEL, PERPENDICULAR, ABOVE, BELOW, LEFT_OF, RIGHT_OF, REFERENCE`.

| Relation | Trigger | Citation |
|---|---|---|
| `nearest_label` / `nearest_geometry` | greedy arg-min distance within grid buckets, one edge per source node | `graph_builder.py:256-278` |
| `distance` + `adjacent` | any geometry pair within `max_edge_distance` (windowed) — **both names emitted for the same fact** | `graph_builder.py:286-289` |
| `left_of`/`right_of`, `above`/`below` | `dx≥dy` vs `dy>dx` branch of the same pair | `graph_builder.py:292-309` |
| `parallel` / `perpendicular` | orientation delta ≤8° / \|Δ-90\|≤8° | `graph_builder.py:310-318` |
| `intersection` + `intersects` | bbox `_intersects(pad=1.0)` — **both names, one fact** | `graph_builder.py:319-321` |
| `containment` (+ reverse `inside`) | bbox `_contains(tol=1.0)` | `graph_builder.py:322-327` |
| `touching` | ring-band test, `tol=2.5` | `graph_builder.py:328-329` |
| `connected` + `connected_to` | bbox `_intersects(pad=3.0)` — **both names, one fact** | `graph_builder.py:331-333` |
| `supports` | horizontal overlap + vertical stacking | `graph_builder.py:334-344` |
| `reference` | shared `drawing_references` value, full O(n²) | `graph_builder.py:346-363` |

`structural_graph.py` layers a **second pass of the same relation names** on top, with different thresholds/confidences, gated by an order-sensitive dedup set:

| Relation | Trigger | Confidence |
|---|---|---|
| `near` | distance ≤ 180.0 | `max(0.1, 1-d/180)` |
| `above`/`below` | vertical gap > 8px | fixed `0.72` |
| `supported_by`/`supports` | beam↔column pair, distance <90 | fixed `0.82` |
| `connected_to` | either node kind = `connection`, distance <70 | fixed `0.78` |
| `inside` | bolt + (plate\|connection), distance <55 | fixed `0.75` |

**Same-fact duplication is deliberate but costly**: `intersection`+`intersects`, `containment`+`inside`, `connected`+`connected_to` are each emitted together for one geometric predicate. Any consumer checking only one name gets a partial picture — e.g. the (dead) `validation_engine.py`'s "disconnected geometry" check only tests `{connected, touching, intersection, nearest_label}`, silently missing `intersects`/`connected_to`/`containment`/`inside` and over-counting disconnection.

**Cross-file duplicate relation strings, different formulas**: `structural_graph.py` re-emits `"above"`, `"below"`, `"connected_to"`, `"inside"` with its own thresholds, distinct from `graph_builder.py`'s versions of the same string values. The dedup guard (`(source, target, relationship)` tuple set) does **not** canonicalize node order, so `above(a,b)` from the base pass and `above(b,a)` from the semantic pass are not recognized as duplicates — both survive.

## 3. Graph data structure

Pure Python `{"nodes": [...], "edges": [...], "stats": {...}}` — no networkx, no adjacency index materialized anywhere. Every consumer that needs "edges touching node X" **linearly re-scans the full edge list** (`graph_features_for_source`, `matching_engine._geometry_linked_labels`, `suggestion_engine._graph_features_for_node`). The module docstring (`structural_graph.py:4-7`) explicitly frames this as "framework-neutral for future NetworkX/GraphSAGE/GCN adapters" — i.e., it is deliberately a serialization-friendly staging format today, not a real graph library structure.

## 4. Association logic

**Search radius/bucket**: `max_edge_distance=160.0` doubles as both the grid cell size and the hard cutoff — a real (if coarse) spatial index for nearest-neighbor edges only.

**Greedy single-best, not bipartite matching**: nearest_label/nearest_geometry pick one best match per source node via simple arg-min — **not** Hungarian assignment, not a global bipartite optimum. Ties break on iteration order (grid scan order, then list-append order) — incidental, not a documented policy.

**One-to-one vs. one-to-many (direct answer)**: because each source node picks its own single nearest neighbor independently, one label can have at most one `nearest_geometry` edge, and one geometry object can have at most one `nearest_label` edge — **but nothing prevents many different labels from each independently choosing the same geometry object as their nearest**, producing unconstrained many-to-one fan-in with no conflict detection at the graph layer. True one-to-many association only happens through the unconstrained pairwise relations (`near`, `distance`, `connected_to`, ...), which impose no per-node cap.

**Leaders are not resolved through**: a leader/arrow is just another `CONNECTION`-kind node competing on raw centroid distance in the nearest-neighbor search — there is no "follow the leader from label to its far endpoint, then associate with what's at the far end" logic anywhere. If a leader stroke happens to be closer to a label's bbox center than the true target member, the label's one `nearest_geometry` edge points at the leader, not the member.

**Conflict resolution / alternative hypotheses**: none at the graph layer. `nearest` is overwritten in place during the search loop; no ranked candidate list is retained on the node or edge. (Alternatives *are* retained later, in the AI candidate-ranking layer — see §6.)

## 5. Spatial index vs. O(n²) — three regimes in the same codebase

1. **Grid-indexed** (bounded, real index): nearest_label/nearest_geometry.
2. **List-order windowed** (looks bounded, but not spatially complete):
   ```python
   candidates = page_geom[:60]
   for i, a in enumerate(candidates):
       for b in candidates[i+1 : i+12]:
   ```
   (`graph_builder.py:281-283`), and `structural_graph.py`'s equivalent (`candidates[:350]`, window 44, `structural_graph.py:119-121`). The list order is PDF-drawing-extraction order, **not** a spatial sort — two geometrically adjacent objects far apart in extraction order are never compared, silently, for PARALLEL/INTERSECTS/CONTAINMENT/CONNECTED/SUPPORTS/PERPENDICULAR alike.
3. **True unbounded O(n²)**: the `REFERENCE` edge pass — full nested loop over all `page_text` nodes, no cap, no windowing (`graph_builder.py:347-363`).

No R-tree/KD-tree/quadtree/STRtree exists anywhere in the graph-construction code.

## 6. Alternative hypotheses

**At the graph layer**: none survive — single-best collapse, as above.
**Downstream, in prediction**: yes — `UnifiedMultimodalFusion.predict` keeps up to 8 scored candidates, and `orchestrator.predict_from_context` exposes an `AlternativePrediction` list. So multiplicity survives in the *section-label* candidate list, but never in the *spatial-association* graph itself — once the graph picks a nearest neighbor, that decision is final within `graph.json` and is not re-examined by the ranking layer (see the worked example, §11).

## 7. Determinism

- **Node/edge IDs are non-deterministic** (UUID4, §1) — topology-equivalent runs produce byte-different `graph.json`.
- **Windowed pairwise loops are order-dependent** on upstream extraction order (§5) — reproducible per PyMuPDF version, but silently different if that version changes drawing-enumeration order, with no error or logged change.
- No other randomness/time-based nondeterminism found.

## 8. Persistence

Rebuilt by default (`graph = graph_document or build_structural_graph(document, geometry)`, `multimodal/pipeline.py:90`), serialized to `graph.json` via `artifact_store.write_artifact`, and reloadable to skip recompute (`staged_pipeline.py:43,136,145`, gated by a `force` flag and cache presence). Also independently reloaded, raw, by `training_pipeline/source_ingestion.py:305`.

## 9. Does the graph actually influence final predictions?

**Yes, but only through five scalar aggregates, not through graph structure or traversal.**

1. `structural_graph.build_structural_graph` computes, per node with a `source_id`: `degree, geometry_links, structural_links, min_distance, graph_consistency = min(1.0, 0.35 + structural_links*0.09)` (`structural_graph.py:209-238`), cached in `graph["source_features"]`.
2. `GraphFeatureProvider.extract` (`multimodal/feature_providers.py:110-120`) fetches this dict per token.
3. `orchestrator.predict_from_context` folds `graph_consistency/degree/structural_links` into rule-engine input, encoder input, `signals["graph"]`, and a `"graph_conflict"` issue flag (`degree>0 and graph_consistency<0.45`).
4. `modular_fusion.ATTENTION_PRIORS["graph"] = 0.17` (second-highest prior after text=0.32, geometry=0.30) — a softmax-attention-weighted linear blend that **directly moves which AISC section wins** among competing candidates, and also feeds the reported overall confidence.
5. `rule_engine.evaluate_engineering_rules` separately consumes `{degree, structural_links}` to gate `member_connectivity`/`column_supports`/`bolt_belongs_to_connection` findings, which further feed a `rules.score` fusion input.

**Crucially, the specific geometry object a label is graph-linked to is never read back for prediction.** `GeometryFeatureProvider.extract` (the thing that actually supplies "which geometry evidence supports this label") re-scans `context["geometry"]["objects"]` directly with its **own independent** nearest-neighbor search (`math.hypot`, proximity formula `max(0.1, 1-d/180)`) — bypassing `graph["edges"]` entirely. So there are, in effect, **three independent nearest-neighbor routines** in the pipeline (`geometry_extractor._nearby_text`, `graph_builder`'s nearest_label/nearest_geometry, and `GeometryFeatureProvider`'s own search) that can each pick a *different* "closest" geometry object for the same label, and nothing reconciles them.

**Dead in the live path** (confirmed by import grep, excluding tests): `matching_engine.py`, `suggestion_engine.py`, `validation_engine.py` (the `engineering/` one — distinct from the *live* `multimodal/validation_engine.py`), `object_confidence.py`. None are imported by any router or by `multimodal/pipeline.py`/`prediction/orchestrator.py`/`staged_pipeline.py` — only by `test_engineering_pipeline.py` and `test_prediction_orchestrator.py`.

## 10. Hard-coded thresholds (consolidated — see `algorithm_registry.csv` for the full list)

Distinct "how far is nearby" constants that all mean roughly the same thing but were tuned independently: `graph_builder.max_edge_distance=160.0`, `structural_graph.max_near_distance=180.0`, `validation_engine.far_label_distance=140.0` (dead code). No comment anywhere explains the discrepancy. Semantic-edge distance gates: beam↔column `<90` (conf 0.82), connection `<70` (conf 0.78), bolt↔plate `<55` (conf 0.75) — all fixed confidences, not derived from any distribution.

## 11. Rule/heuristic inventory — `rule_engine.py`, `suggestion_engine.py`

**`evaluate_engineering_rules`** (per-token, live): 10 rules (`notation_valid`, `beam_orientation`, `column_orientation`, `depth_geometry_agreement`, `geometry_available`, `member_connectivity`, `column_supports`, `bolt_belongs_to_connection`, `plate_attached`, `material_prior`), each pass/warning/fail with a fixed weight (0.4–1.3); final score = `weighted/total`, warning contributes 0.45× its weight. Role inference (`_infer_role`) is itself a small rule chain (text keyword match, else orientation-based fallback).

**`evaluate_document_rules`** (document-level, live, only 2 checks): `beams_without_columns`, `missing_support_edges`.

**`suggestion_engine.suggest_for_text_node`** (dead code, not imported outside tests): AI-first suggestion generator that calls `orchestrator.predict_token`, nudges confidence using Excel-count priors and graph proximity (`+0.05`/`-0.08`), with hardcoded fallback confidences (0.25 no-signal, 0.7 missing-label-from-Excel).

## 12. Graph-specific problems (explosion, connectivity, cycles)

- **Edge explosion risk**: real. A single geometry pair in `structural_graph.py`'s windowed loop can fire up to 3 relations simultaneously; `graph_builder.py`'s base pass can fire up to 10 edge-dict appends per pair, several of which are deliberately-duplicated names for one fact (§2) — inflating edge count without adding information.
- **Isolated-node handling**: none. Every extracted token and geometry object becomes a node unconditionally regardless of resulting edge count. The only place isolation is *detected* is the dead `validation_engine.py` (`>50%` disconnected-geometry threshold) — no isolated-node handling exists for text/label nodes anywhere, live or dead.
- **Duplicate-edge handling**: `graph_builder.py`'s own loop is safe by construction (each unordered pair visited once within its own windowed loop). `structural_graph.py` dedups via a set, but the set key is not order-invariant (§2) — reordered-pair duplicates across the two passes are not caught.
- **Cycle handling**: none anywhere; not detected, not broken. `_contains(tol=1.0)` could in principle satisfy both directions for two near-identical bboxes, only partially guarded by an `if/elif` — the general possibility of 2-cycles across containment/inside combined with the independent semantic layer is not prevented.
- **Under-connected geometry (e.g. a detail box spanning many members) can end up with zero `nearest_label` edge** if its centroid is far from any single label within 160pt, even though it visually "contains" several labeled members via `CONTAINMENT`/`INSIDE` edges — the containment relation exists, but nothing promotes "region membership" into a first-class grouping for downstream ranking to use directly.

## 13. Evaluating whether the graph represents the right *concepts*

Per the audit's requested taxonomy:

**1. Drawing entities** (text, lines, curves, leaders, dimensions, blocks, detail regions, grid lines): text and geometry are separate node types; leaders are folded into `CONNECTION` kind; dimensions get their own `NodeKind.DIMENSION`; **detail regions and grid lines have no dedicated representation** — a detail box is just a `RECTANGLE`-kind geometry node related to its contents only via generic bbox `CONTAINMENT`, and grid lines are indistinguishable from any other `LINE`.

**2. Structural elements** (beam, column, brace, plate, connection, assembly): represented, but via **two independently-written text-regex classifiers stacked in sequence** (`_classify_text_node` then `_semantic_kind`), not via geometric reasoning. No `ASSEMBLY` concept exists at all — a beam-to-column moment connection with multiple bolts/plates is a set of same-page nodes linked by generic `near`/`connected_to`/`inside` edges, not a first-class grouped entity.

**3. Evidence relationships** (near, parallel, intersects, contained-in, leader-points-to, same-detail, same-level, same-grid-bay, possible-label-for, confirmed-label-for, connected-structurally): near/parallel/intersects/contained-in/connected exist (with the duplication caveats in §2). **Leader-points-to is not modeled as its own relation** (a leader is just another node with `nearest_*` edges like anything else). **Same-detail, same-level, same-grid-bay have no representation whatsoever** — there is no grid/level/detail-region concept anywhere in the schema. **Possible-label-for vs. confirmed-label-for is not distinguished at the graph layer** — `nearest_label`/`nearest_geometry` are single, unweighted-by-confidence-tier edges; confirmation only happens later, out-of-graph, in the AI ranking layer.

**Mixing of different meanings into one edge type**: `connected_to` alone means at least three different things depending on which pass emitted it — a raw bbox-intersection-with-padding fact from `graph_builder.py`, or a kind-gated distance-threshold fact from `structural_graph.py`. A consumer reading `relationship == "connected_to"` cannot tell which without also checking `meta`/confidence fields that aren't consistently populated across both emitters.

---

## Pseudocode — how the graph is actually built

```
function build_structural_graph(document, geometry):
    graph = build_graph(document, geometry)          # base spatial pass
    for node in graph.nodes:
        node.base_kind = node.kind
        node.kind = semantic_kind(node)               # 2nd independent classifier, OVERWRITES kind
        node.features = {length, width, area, orientation, font_size}
    existing = set of (src,tgt,rel) from graph.edges   # dedup guard, NOT order-invariant
    for page in group_by_page(graph.nodes):
        candidates = page[:350]                        # hard cap, not spatially sorted
        for i, a in enumerate(candidates):
            for b in candidates[i+1 : i+45]:            # WINDOW, list-order not spatial
                d = euclid(a.center, b.center)
                if d <= 180: add_if_new(a, b, "near", conf=1-d/180)
                if |a.y - b.y| > 8: add_if_new(above/below pair, conf=0.72)
                if {a.kind,b.kind} == {beam,column} and d < 90: add supports/supported_by, 0.82
                if "connection" in kinds and d < 70: add connected_to, 0.78
                if "bolt" in kinds and ("plate"/"connection" in kinds) and d < 55: add inside, 0.75
    graph.source_features = { source_id: aggregate(degree, geometry_links, structural_links,
                                                     min_distance,
                                                     consistency = min(1.0, 0.35 + 0.09*structural_links)) }
    return graph

function build_graph(document, geometry):              # base pass
    nodes = [text_node(t) for t in document.engineering_tokens]
          + [geometry_node(g) for g in geometry.objects]     # leader -> CONNECTION kind
    bucket nodes into grid[page][floor(x/160), floor(y/160)]
    for each geometry node g:
        nearest_label = argmin(dist) over nearby(label_grid, g.center) within 160
        if found: add_edge(g, nearest_label, "nearest_label", weight=1/(1+d))
    for each label node l:
        nearest_geom = argmin(dist) over nearby(geometry_grid, l.center) within 160
        if found: add_edge(l, nearest_geom, "nearest_geometry", weight=1/(1+d))
    for page_geom[:60] windowed pairs (i, i+1..i+12):        # NOT spatially sorted
        if d <= 160: add distance, adjacent, left/right_of or above/below, parallel/perpendicular
        if bbox intersects: add intersection + intersects (duplicate names, one fact)
        if bbox contains:   add containment + inside (duplicate names, one fact)
        if touches (ring band): add touching
        if intersects(pad=3): add connected + connected_to; maybe supports
    for page_text (full O(n^2), unbounded): add "reference" edges on shared drawing_references
    return {nodes, edges, stats}
```

## Worked example (traced through real code, not hypothetical)

**Scenario**: text token `"W12X26"`; nearby candidates are a straight beam-line geometry object, a short leader stroke, and a large rectangular detail box that spans the beam line.

1. **Before the graph exists** (`geometry_extractor.py`): the beam line already gets `nearby_text = "W12X26"` stamped on it by `_nearby_text` (its *own*, separate 48pt-radius search — independent of anything the graph will later compute). The short stroke gets reclassified `LEADER` if it's 8–180pt long with a small bbox. The rectangle stays `RECTANGLE` (assumed area ≥ 400).
2. **Node construction**: the token → text node, `_classify_text_node("W12X26")` matches `BEAM_RE` → `kind="beam"`. The beam line → `GEOMETRY` node. The leader → forced `CONNECTION` kind because `geom["kind"]=="leader"`. The rectangle → `GEOMETRY` node with a large bbox.
3. **Bucketing**: all four land in the same/adjacent 160pt grid cells.
4. **`nearest_geometry` for the label**: candidates are the beam line, the leader, and the rectangle — **unfiltered by semantic kind**, purely closest-centroid wins. If the leader (drawn from the label toward the member) happens to be centroid-closer than the beam line itself, the label's single `nearest_geometry` edge points at the **leader**, not the beam — there is no "resolve through the leader to its far endpoint" step anywhere.
5. **`nearest_label` for the geometry**: symmetric, independent search per geometry node — the beam line and the leader may **both** end up pointing `nearest_label` back at the same `"W12X26"` node (unconstrained many-to-one). The large rectangle, if its centroid is far from any single label, may get no `nearest_label` edge at all.
6. **Pairwise relations** (subject to the 60/window-12 cap): for (beam line, rectangle), `_contains` fires → `CONTAINMENT(rectangle, beam)` **and** `INSIDE(beam, rectangle)` — this is the *only* mechanism modeling a "detail box" relationship; there is no dedicated region/detail concept. For (beam line, leader), bbox proximity may fire `TOUCHING`/`CONNECTED`/`CONNECTED_TO`, and angle proximity may independently fire `PARALLEL`/`PERPENDICULAR`.
7. **Semantic enrichment**: `_semantic_kind` reclassifies the label node — `"W12X26"` doesn't match bolt/weld/plate/brace/column/connection regexes, stays `"beam"`. The leader node: `geometry_kind=="leader"` → forced `"connection"` again (redundant here, but independently re-derived). The semantic pairwise pass may add a *second*, differently-thresholded `connected_to(connection, member)` edge for the same beam↔leader adjacency already captured by the base pass.
8. **What "wins"**: nothing filters or ranks these coexisting edges — the beam-line edge, the leader edge, and the containment edges all persist in `graph["edges"]`. Downstream, `GraphFeatureProvider` only pulls the **cached aggregate** (`degree, structural_links, graph_consistency, min_distance`) for the label's `source_id` — it never asks "which geometry object is this label's `nearest_geometry`?" The geometry object that actually informs the AI prediction's `geometry` evidence comes from `GeometryFeatureProvider`'s **own, third, independent** nearest-neighbor search over `context["geometry"]["objects"]`, bypassing `graph["edges"]` entirely. **The specific identity of what the label was linked to in the graph (beam vs. leader vs. detail box) is never read back out for prediction** — only the five scalar aggregates matter downstream.

---

## Dead code / duplication / raw-normalized-inferred mixing (flagged per guardrails)

**Dead code** (import-grep confirmed, non-test callers = zero):
- `matching_engine.py`, `suggestion_engine.py`, `validation_engine.py` (`engineering/`, not `multimodal/`), `object_confidence.py` — all four feature-complete, none reachable from any router or the live pipeline.
- `NodeKind.OTHER` — never assigned.
- `object_confidence.score_matching_for_object` contains a logically vestigial double-check (`if object_id not in ids: if object_id not in set(ids): continue`) — the inner condition is always true when reached, moot since the whole module is unreferenced.

**Duplicated logic**:
1. Euclidean distance reimplemented independently 3×: `graph_builder._dist`, `structural_graph._distance`, inline `math.hypot` in `feature_providers.GeometryFeatureProvider`.
2. Text-to-line nearest-neighbor search exists twice, different radii, different candidate pools, can disagree: `geometry_extractor._nearby_text` (48pt, pre-graph) vs. `graph_builder` nearest_label/nearest_geometry (160pt, graph edges) — nothing reconciles a mismatch between `geom["nearby_text"]` and the graph's `nearest_label` edge target.
3. `TOKEN_RE` (steel-shape regex) duplicated verbatim between `matching_engine.py` and `suggestion_engine.py`.
4. Two independent node-kind classifiers stacked in sequence (`_classify_text_node`, `_semantic_kind`), each with its own regex set.

**Raw/normalized/inferred/resolved values mixed without separation**:
1. `node["kind"]` means one thing from `graph_builder` and a different, overwritten thing after `structural_graph` runs — the original is preserved only under a separately-named key (`base_kind`), and any single reader of `kind` can't tell which classifier produced the current value.
2. `node["text"]` means the raw extracted string for text nodes, but for geometry nodes it holds `nearby_text` — the *output* of a separate inferred-association step, not anything intrinsic to the geometry. Same key, two different provenance levels.
3. `matching_engine._labels_from_graph` manufactures synthetic "label" records by spreading a node and overwriting only `text` with a regex-extracted substring, while **keeping the original node's `bbox`/`center` unchanged** — if the source text run contains more than the token (e.g. `"SEE W12X26 NOTE 3"`), the synthesized label's geometry doesn't actually correspond to what its `text` now claims.
4. `geometry["objects"]` entries mix raw PDF-drawing measurements with an inferred field (`nearby_text`) and a possibly-overwritten classification (`kind`, which may have been reclassified from its original `_classify_path` output to `LEADER`/`DIMENSION`/`SYMBOL`) — no field distinguishes "as-drawn" from "as-classified."

## Open questions

See `09_open_questions.md` for the consolidated list; graph-specific items include: why three different "nearby" distance constants (160/180/140) exist without a shared source of truth; whether the four dead-code engineering-graph modules are intentionally staged for future wiring or genuinely orphaned; and what real-world node-count-per-page distribution the 60/350 windowing caps were sized against.
