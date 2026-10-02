# Geometry sidecar vs corrected-PDF workflow (G5)

**Owner of live stream:** Mike (Step 1).  
**Owner of safety tests:** Estima3D.

## Invariant

Attaching geometry candidates must not change:

- original / primary label text
- completion status (e.g. `L4X4` stays missing thickness)
- `takeoff_eligible`

Implemented as `attach_geometry_sidecar` in `scripts/rd_geometry_integration/workflow_verify.py` and `tests/test_rd_geometry_phase.py::WorkflowSidecarTests`.

## Checklist when corrected PDF exists

1. Same document still produces `document.json` / `geometry.json` / `graph.json`.
2. Semantic Review still owns text.
3. Geometry evidence pack is additive JSON + overlays only.
4. Incomplete L/2L abstention tests still pass (`test_incomplete_angle_abstention` if run).

Latest harness write: `docs/validation/rd_geometry_integration/g5_workflow_verify.json`.
