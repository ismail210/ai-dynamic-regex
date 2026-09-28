# R&D — Geometry Retrieval & Detail Extents (isolated)

Controlled prototype for the Geometry Integration phase (Steps 2–3 plus G1–G6 evidence pack).

- **Does not** modify production GHX, association, Semantic Review, takeoff, or ML flags.
- **Reuses** existing `geometry.json` / `graph.json` / `document.json` artifacts.
- **Treats** retrieval as **evidence only** — never invents section sizes or beam/column roles.

Run from `backend/`:

```bash
venv/bin/python scripts/rd_geometry_integration/run_prototype.py
```

Team-facing outputs in `docs/validation/rd_geometry_integration/`:

| File | Phase |
|------|--------|
| `comparison.html` | G6 dedicated comparison page (not Semantic Review) |
| `g1_summary.json` / `g1_rows.jsonl` | Leader-aware candidates vs production |
| `g2_frames.json` | Title-seeded detail frames + IoU |
| `review_kit/` | G3 human gold kit (`gold_outcomes.jsonl` + `decisions/`) |
| `HUMAN_GOLD_REVIEW_REPORT.md` | First Burrville human-gold review (75/75) |
| `GEOMETRY_RETRIEVAL_V2_REPORT.md` | Isolated retrieval v2 vs frozen gold (not production) |
| `v2_rows.jsonl` / `v2_summary.json` / `v2_renders/` | V2 candidate lists, coverage metrics, QA crops |
| `GEOMETRY_EXTRACTION_AUDIT.md` | Stage-by-stage extraction audit, p8/p18/p24 (investigation only) |
| `extraction_audit.jsonl` / `extraction_audit_summary.json` / `extraction_audit_renders/` | Per-case stage trace, aggregates, QA crops |
| `GEOMETRY_CAP_COST_REPORT.md` | E1 dense-page cap cost measurement (450/900/1800/no-limit) |
| `cap_cost_results.jsonl` / `cap_cost_summary.json` | Per-case cap survival + page aggregates |
| `GEOMETRY_CLASSIFICATION_COST_REPORT.md` | E2 classification cost (`_looks_like_dimension` / leader) |
| `classification_cost_results.jsonl` / `classification_cost_summary.json` | Per-case classification stage trace |
| `GEOMETRY_DIMENSION_SHADOW_REPORT.md` | E3 own-label vs callout dimension shadow |
| `dimension_shadow_results.jsonl` / `dimension_shadow_summary.json` / `dimension_shadow_renders/` | E3 per-target matrix, aggregates, QA crops |
| `GEOMETRY_DIMENSION_CONTROL_E4_REPORT.md` | E4 genuine-dimension control expansion + V1 false-flip diagnostic |
| `dimension_control_set.jsonl` / `dimension_control_results.jsonl` / `dimension_control_summary.json` / `dimension_control_renders/` | E4 controls, V0/V1 results, QA crops |
| `GEOMETRY_DIMENSION_HOLDOUT_E5_REPORT.md` | E5 multi-document holdout + implementation gate |
| `dimension_holdout_e5_results.jsonl` / `dimension_holdout_e5_summary.json` / `dimension_holdout_e5_renders/` / `dimension_holdout_e5_review.html` | E5 holdout matrix, aggregates, QA |
| `GEOMETRY_OWNERSHIP_E5_1_REPORT.md` | E5.1 ownership evidence audit + ownership gate |
| `ownership_evidence_e5_1_results.jsonl` / `ownership_evidence_e5_1_summary.json` / `ownership_e5_1_renders/` / `ownership_e5_1_review.html` | E5.1 per-case ownership matrix |
| `GEOMETRY_BBOX_AUDIT_G7_REPORT.md` | G7 geometry/bbox representation readiness gate |
| `geometry_bbox_audit_g7_results.jsonl` / `geometry_bbox_audit_g7_summary.json` / `geometry_bbox_audit_g7_renders/` / `geometry_bbox_audit_g7_review.html` | G7 per-case matrix, aggregates, QA |
| `GEOMETRY_REPRESENTATION_REPAIR_G8_REPORT.md` | G8 R&D candidate population / representation repair gate |
| `representation_repair_g8_results.jsonl` / `representation_repair_g8_summary.json` / `representation_repair_g8_renders/` / `representation_repair_g8_review.html` | G8 A/B representation matrix |
| `GEOMETRY_ASSOCIATION_G9_REPORT.md` | G9 deterministic association shadow gate |
| `association_shadow_g9_results.jsonl` / `association_shadow_g9_summary.json` / `association_shadow_g9_renders/` / `association_shadow_g9_review.html` | G9 rankings + decisions |
| `g4_shadow_metrics.json` | Shadow scorer vs production |
| `g5_workflow_verify.json` | Sidecar must not rewrite text |
| `renders/` | Region + association overlays |

V2 (shadow only, does not write gold):

```bash
venv/bin/python scripts/rd_geometry_integration/run_retrieval_v2.py
python -m pytest tests/test_rd_geometry_phase.py tests/test_rd_geometry_retrieval_v2.py -q
```

Extraction audit (read-only; replays production extraction stages and verifies the replay
reproduces `geometry.json` byte-for-byte before attributing any loss to a stage):

```bash
venv/bin/python scripts/rd_geometry_integration/extraction_audit.py --renders
```

Cap-cost experiment E1 (measurement only; production cap unchanged):

```bash
venv/bin/python scripts/rd_geometry_integration/cap_cost_experiment.py
```

Classification-cost experiment E2 (measurement only; classifiers unchanged):

```bash
venv/bin/python scripts/rd_geometry_integration/classification_cost_experiment.py
```

Dimension-shadow experiment E3 (measurement only; classifiers unchanged):

```bash
venv/bin/python scripts/rd_geometry_integration/dimension_shadow_experiment.py --renders
python -m pytest tests/test_rd_geometry_dimension_shadow.py tests/test_rd_geometry_phase.py tests/test_rd_geometry_retrieval_v2.py -q
```

Genuine-dimension control expansion E4 (V1 false-flip diagnostic; classifiers unchanged;
reuses E3 V1; does **not** promote V1 to production):

```bash
venv/bin/python scripts/rd_geometry_integration/dimension_control_expansion.py --renders
python -m pytest \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_dimension_shadow.py \
  tests/test_rd_geometry_dimension_control_e4.py \
  -q
```

Multi-document holdout E5 (final Phase-E gate for own-label digit stripping;
shadow only; does **not** implement production V1):

```bash
venv/bin/python scripts/rd_geometry_integration/multi_document_dimension_holdout.py --renders
python -m pytest \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_dimension_shadow.py \
  tests/test_rd_geometry_dimension_control_e4.py \
  tests/test_rd_geometry_dimension_holdout_e5.py \
  -q
```

Ownership evidence audit E5.1 (final ownership gate before any production
implementation; does **not** implement V1):

```bash
venv/bin/python scripts/rd_geometry_integration/ownership_evidence_audit_e5_1.py --renders
python -m pytest \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_dimension_shadow.py \
  tests/test_rd_geometry_dimension_control_e4.py \
  tests/test_rd_geometry_dimension_holdout_e5.py \
  tests/test_rd_geometry_ownership_e5_1.py \
  -q
```

Geometry / bbox representation audit G7 (read-only; does **not** implement
association; does not modify production extraction or gold):

```bash
venv/bin/python scripts/rd_geometry_integration/geometry_bbox_audit_g7.py --renders
python -m pytest \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_dimension_shadow.py \
  tests/test_rd_geometry_dimension_control_e4.py \
  tests/test_rd_geometry_dimension_holdout_e5.py \
  tests/test_rd_geometry_ownership_e5_1.py \
  tests/test_rd_geometry_bbox_audit_g7.py \
  -q
```

| File | Phase |
|------|--------|
| `GEOMETRY_BBOX_AUDIT_G7_REPORT.md` | G7 representation / bbox readiness gate |
| `geometry_bbox_audit_g7_results.jsonl` / `geometry_bbox_audit_g7_summary.json` | Per-case matrix + aggregates |
| `geometry_bbox_audit_g7_renders/` / `geometry_bbox_audit_g7_review.html` | QA crops + review page |

Representation repair G8 (R&D candidate population only; does **not** implement
association; does not modify production extraction, CAP, retrieval, or gold):

```bash
venv/bin/python scripts/rd_geometry_integration/representation_repair_g8.py --renders
python -m pytest \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_bbox_audit_g7.py \
  tests/test_rd_geometry_representation_g8.py \
  -q
```

| File | Phase |
|------|--------|
| `GEOMETRY_REPRESENTATION_REPAIR_G8_REPORT.md` | G8 representation-ready-for-association gate |
| `representation_repair_g8_results.jsonl` / `representation_repair_g8_summary.json` | Per-case A/B matrix + aggregates |
| `representation_repair_g8_renders/` / `representation_repair_g8_review.html` | QA crops + review page |

Association shadow G9 (deterministic multi-signal ranking over G8 candidates;
R&D only; does **not** wire production association):

```bash
venv/bin/python scripts/rd_geometry_integration/association_shadow_g9.py --renders
python -m pytest \
  tests/test_rd_geometry_phase.py \
  tests/test_rd_geometry_retrieval_v2.py \
  tests/test_rd_geometry_representation_g8.py \
  tests/test_rd_geometry_association_g9.py \
  -q
```

| File | Phase |
|------|--------|
| `GEOMETRY_ASSOCIATION_G9_REPORT.md` | G9 association evidence gate |
| `association_shadow_g9_results.jsonl` / `association_shadow_g9_summary.json` | Per-case rankings + decisions |
| `association_shadow_g9_renders/` / `association_shadow_g9_review.html` | QA crops + review page |

Reports: `docs/GEOMETRY_PHASE_CHARTER.md`, `docs/GEOMETRY_PHASE_G1_RESULTS.md`,
`docs/GEOMETRY_RETRIEVAL_COMPARISON.md`, `docs/DETAIL_PAGE_EXTENTS_PROTOTYPE.md`.
