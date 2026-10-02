# Graph Leader → Target Member Investigation

## A. Executive conclusion

**Recommendation: STOP — leader-target evidence is too weak/noisy**

Graph v2 remains **DO NOT ENABLE** in production. This investigation only asks whether existing leader→target associations contain family-level signal.

Key findings:
- Docs with `graph.json`: **3** / 8 (primary evidence subset; 5/8 eval docs lack graph.json → D)
- All-doc associations classified: **9396** (leader_resolved=2370)
- Graph-doc-only associations: **5031** (leader_resolved=2370)
- Reliability **graph docs only**: A=37 (0.7%), B=2101 (41.8%), C=776 (15.4%), D=2117 (42.1%)
- HSS-gold + leader_resolved (any candidate pool): n=149, prefers_W_only=52, prefers_HSS_only=0, both=97
- HSS-gold with HSS+W in candidate pool: n=3, prefers_HSS=0, prefers_W=0, neutral=2, missing=1
- Incomplete-L completion justification from leader evidence: **0** (must stay 0)

Reasons:
- On 149 HSS-gold rows with leader_resolved, orientation/role lean is prefers_W_only=52, prefers_HSS_only=0, both=97 (systematic HSS→W risk).
- Reliability A is only 37/5031 (0.7%) on docs that have graph.json; most resolved hops are ambiguous B (2101, often ≥3 leader sources).
- Targets are almost always unlabeled `kind=geometry` — no printed member section to ground family.
- Far-endpoint hop uses bbox corner; true polyline endpoints are not on graph nodes; leader id is not stored on the winning edge.

## B. How leader-target relationships are represented

### Construction

1. `geometry_extractor` marks thin short strokes as `kind=leader` and stores `leader_endpoints.near_endpoint` / `far_endpoint` on the geometry object.
2. `graph_builder.build_geometry_nodes` maps leaders to graph nodes with `geometry_kind=leader`, `kind=connection`. **Endpoints and polyline points are not copied onto graph nodes.**
3. `spatial_index.nearest_geometry_candidates` (used by `graph_builder.build_graph`):
   - finds geometries near the label
   - if a candidate is a leader, computes a **bbox far-corner** hop (`_leader_far_endpoint`) — not the geometry object's true far endpoint
   - queries again for a structural member near that point
   - ranks `leader_endpoint_resolved` ahead of `direct_distance`
4. Winning association is stored as one `nearest_geometry` edge:

```text
label (txt_*)  --nearest_geometry-->  member (geo_*)
meta.leader_resolved = true
meta.association_sources = [leader_endpoint_resolved, ...]
meta.candidate_count = N
distance / weight present
leader node id NOT stored on the edge
```

Separate `nearest_label` edges may link leader strokes → nearby labels (empty meta) — that is proximity to the leader, not the resolved target.

### Production usage

Leader meta (`leader_resolved`, `association_sources`) is used when **building** `nearest_geometry` edges (selects the associated member). Production fusion/ranking does **not** read leader fields as a feature; only indirect graph scalars (degree / min_distance / graph_consistency) reach ranking. GraphSAGE / learned fusion remain OFF.

### Docs analyzed

- `doc_0bfc2d61245dbce2`: graph=False geometry=False leader_nodes=0 diag.leader_resolved_associations=None
- `doc_0d910a43b4a021e3`: graph=True geometry=True leader_nodes=4263 diag.leader_resolved_associations=503
- `doc_240bd2541fbca147`: graph=False geometry=False leader_nodes=0 diag.leader_resolved_associations=None
- `doc_47dc7ef27f6e5d7e`: graph=True geometry=True leader_nodes=8297 diag.leader_resolved_associations=2272
- `doc_683e6eef0a945c9a`: graph=False geometry=False leader_nodes=0 diag.leader_resolved_associations=None
- `doc_6a9a9684bb19343b`: graph=False geometry=False leader_nodes=0 diag.leader_resolved_associations=None
- `doc_9414716bffc67596`: graph=True geometry=True leader_nodes=1961 diag.leader_resolved_associations=405
- `doc_f6ddc4a7e233ffb0`: graph=False geometry=False leader_nodes=0 diag.leader_resolved_associations=None

Docs **without** graph.json (prediction-only; associations → D/missing): `doc_0bfc2d61245dbce2`, `doc_240bd2541fbca147`, `doc_683e6eef0a945c9a`, `doc_6a9a9684bb19343b`, `doc_f6ddc4a7e233ffb0`

## C. Reliability counts

Buckets:
- **A** Explicitly resolved and reliable (leader hop → structural member, tight distance, low ambiguity)
- **B** Resolved but ambiguous (many leader sources / high candidate_count / farther distance)
- **C** Geometry-only / weak (direct nearest without leader, or non-structural target)
- **D** Missing or unresolved (no nearest_geometry edge / no graph)

### C1. All 8 eval docs (includes 5 without graph.json → mostly D)

| Bucket | Count | % |
|---|---:|---:|
| A | 37 | 0.4% |
| B | 2101 | 22.4% |
| C | 776 | 8.3% |
| D | 6482 | 69.0% |
| **Total** | **9396** | 100% |

Leader-resolved (all docs): **2370** (25.2%).

### C2. Graph-available docs only (primary evidence)

| Bucket | Count | % |
|---|---:|---:|
| A | 37 | 0.7% |
| B | 2101 | 41.8% |
| C | 776 | 15.4% |
| D | 2117 | 42.1% |
| **Total** | **5031** | 100% |

Leader-resolved (graph docs): **2370** (47.1%).

Among `leader_resolved` rows on graph docs:
- Target `kind` top: `{'geometry': 2309, 'brace': 22, 'beam': 14, 'column': 13, 'connection': 8, 'plate': 4}`
- Orientation bins: `{'vertical': 1144, 'horizontal': 1208, 'diagonal': 18}`
- Leader source multiplicity: <3 sources=801, ≥3 sources=1569 (66.2% of leader_resolved are multi-leader / ambiguous)

## D. Family-level separation results

Allowed families only: HSS / W / L / 2L / PIPE (plus related soft priors). No thickness, legs, or incomplete-L completion.

Multi-family gold association rows (graph docs): **31**

| Preference vs gold family | Count | % |
|---|---:|---:|
| prefers_gold_family | 16 | 51.6% |
| prefers_other_family | 12 | 38.7% |
| neutral | 1 | 3.2% |
| missing | 2 | 6.5% |

Interpretation: soft preference is derived from target **role/orientation** after leader association — not from reading a printed section on the member. Most targets are unlabeled `kind=geometry`, so family signal is weak and prior-driven. Multi-family gold preference is near coin-flip (16 gold vs 12 other).

## E. HSS vs W analysis

### E1. All HSS-gold rows with leader_resolved (family lean from target orientation/role)

n = **149**

| Lean | Count |
|---|---:|
| prefers_HSS_only | 0 |
| prefers_W_only | 52 |
| both_HSS_and_W | 97 |
| neither | 0 |

### E2. Gold family = HSS, candidates include HSS and W

n = **3** (leader_resolved on **2**)

| Lean | Count |
|---|---:|
| prefers_HSS | 0 |
| prefers_W | 0 |
| neutral | 2 |
| missing | 1 |

### E3. Gold family = W, candidates include HSS and W

n = **0**

| Lean | Count |
|---|---:|
| prefers_W | 0 |
| prefers_HSS | 0 |
| neutral | 0 |
| missing | 0 |

### E4. W-gold leader lean (all W-gold + leader_resolved)

n = **1868** → `{'both': 919, 'prefers_W_only': 931, 'prefers_HSS_only': 18}`

Examples where leader-target orientation/role lean prefers **W only** on HSS gold:

- `doc_0d910a43b4a021e3` raw=`HSS12X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=4.56 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS14X6X1/2` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=10.08 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS6X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=5.64 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS6X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=11.64 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS6X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=7.92 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS8X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=5.64 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS6X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=7.92 bucket=B
- `doc_0d910a43b4a021e3` raw=`HSS6X6X3/8` target_kind=geometry orient=horizontal preferred=['C', 'M', 'MC', 'S', 'W'] dist=7.92 bucket=B

## F. L analysis

Leader-target evidence is evaluated at **family** level only. It must not justify completing incomplete L or inventing thickness.

Completion-justification flags: **0** (analysis encodes family-only; must remain 0).

| L bucket | n | leader A | leader B | leader C | leader D | leader_resolved |
|---|---:|---:|---:|---:|---:|---:|
| explicit_complete_L | 187 | 1 | 8 | 1 | 177 | 10 |
| explicit_L_shop_cut | 60 | 0 | 4 | 1 | 55 | 5 |
| incomplete_L | 16 | 0 | 3 | 0 | 13 | 3 |
| unlabeled_L | 0 | 0 | 0 | 0 | 0 | 0 |
| other_L | 0 | 0 | 0 | 0 | 0 | 0 |

Verification:
- Incomplete L (`L4x4` style): leader evidence does **not** create a thickness/leg completion signal in this investigation.
- No path from leader-target → `L4X4X1/4` or `2L…` invention is supported by stored fields (no size fields on target geometry).
- Explicit complete / shop-cut L remain protected by existing production exact-section / core-section rules (unchanged).

## G. Examples of strong evidence

- `doc_0d910a43b4a021e3` `W16X26` gold=W16X26 → line/geometry orient=horizontal dist=9.72 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `W16X31` gold=W16X31 → line/geometry orient=horizontal dist=9.72 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `W14X22` gold=W14X22 → line/geometry orient=horizontal dist=9.72 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `3/4"` gold=None → line/geometry orient=horizontal dist=9.72 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `W12X16` gold=W12X16 → line/geometry orient=horizontal dist=9.72 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `W14X22` gold=W14X22 → line/geometry orient=horizontal dist=9.72 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `W21X44` gold=W21X44 → line/geometry orient=horizontal dist=9.96 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `W18X50` gold=W18X50 → polyline/geometry orient=horizontal dist=65.76 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `L3x3x3/16` gold=L3X3X3/16 → rectangle/column orient=vertical dist=80.28 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `1/2"` gold=None → line/brace orient=horizontal dist=99.48 leader_sources=1 cand_count=1
- `doc_0d910a43b4a021e3` `PL1/4x12"` gold=None → line/geometry orient=horizontal dist=35.88 leader_sources=2 cand_count=2
- `doc_0d910a43b4a021e3` `PL 5 5/16" 1/2"` gold=None → line/geometry orient=horizontal dist=78.96 leader_sources=1 cand_count=1

## H. Examples of ambiguous/unsafe evidence

- `doc_0d910a43b4a021e3` `W27X84` gold=W27X84 kind=symbol/beam dist=127.88 leader_sources=1 cand_count=1 issue= sources=['leader_endpoint_resolved', 'direct_distance']
- `doc_0d910a43b4a021e3` `1/2"` gold=None kind=line/geometry dist=0.0 leader_sources=8 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'direct_distance', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W18X35` gold=W18X35 kind=line/geometry dist=27.12 leader_sources=4 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W12X16` gold=W12X16 kind=line/geometry dist=0.0 leader_sources=13 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W16X26` gold=W16X26 kind=line/geometry dist=0.0 leader_sources=12 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W12X19` gold=W12X19 kind=line/geometry dist=0.0 leader_sources=11 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `HSS10X8X3/8` gold=HSS10X8X3/8 kind=line/geometry dist=0.0 leader_sources=15 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W16X31` gold=W16X31 kind=polyline/geometry dist=0.0 leader_sources=17 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W12X16` gold=W12X16 kind=polyline/geometry dist=0.0 leader_sources=17 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W12X16` gold=W12X16 kind=polyline/geometry dist=0.0 leader_sources=15 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W12X16` gold=W12X16 kind=polyline/geometry dist=0.0 leader_sources=14 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']
- `doc_0d910a43b4a021e3` `W12X16` gold=W12X16 kind=polyline/geometry dist=0.0 leader_sources=15 cand_count=3 issue= sources=['leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved', 'leader_endpoint_resolved']

## I. Missing evidence

- Reliability D count: **6482** (69.0%)
- Docs without graph.json: **5**
- Graph nodes omit true `leader_endpoints` / polyline points.
- Winning `nearest_geometry` edge does not store which leader was used.
- `predictions_view` explanations generally lack `leader_resolved` / far-endpoint fields (association provenance not surfaced to fusion).
- `source_features` has no leader flag.

Sample missing/unresolved rows:

- `doc_0bfc2d61245dbce2` `W14x90` gold=W14X90 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W16x26` gold=W16X26 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W14x22` gold=W14X22 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W16x26` gold=W16X26 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W16x26` gold=W16X26 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W16x26` gold=W16X26 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W16x26` gold=W16X26 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W8x31` gold=W8X31 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W8x40` gold=W8X40 (missing_or_unresolved)
- `doc_0bfc2d61245dbce2` `W8x40` gold=W8X40 (missing_or_unresolved)

## J. Recommendation

**STOP — leader-target evidence is too weak/noisy**

Constraints that remain in force:
- Do **not** wire Graph v2 into production.
- Do **not** add `GRAPH_V2_ENABLED` / GraphSAGE / learned fusion flags.
- Do **not** use leader-target evidence to invent thickness, complete incomplete L, or override explicit printed sections.
- Family-level research only, offline, if continued.

### Reasons

- On 149 HSS-gold rows with leader_resolved, orientation/role lean is prefers_W_only=52, prefers_HSS_only=0, both=97 (systematic HSS→W risk).
- Reliability A is only 37/5031 (0.7%) on docs that have graph.json; most resolved hops are ambiguous B (2101, often ≥3 leader sources).
- Targets are almost always unlabeled `kind=geometry` — no printed member section to ground family.
- Far-endpoint hop uses bbox corner; true polyline endpoints are not on graph nodes; leader id is not stored on the winning edge.

---

_Generated offline by `scripts/investigate_leader_target.py` from cached artifacts only. No production modules modified._
