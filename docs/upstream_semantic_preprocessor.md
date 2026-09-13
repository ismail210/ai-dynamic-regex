# Upstream Structural Drawing Semantic Preprocessor

Implementation status: **Phase 1 foundation landed this session** (see
"What's implemented" below). This is a design + as-built reference for
`backend/services/semantic_preprocessor/`, not a forward-looking proposal --
where it says a module exists, it exists and is tested.

## Product boundary

This system does **not** compute takeoff quantities, classify members into
fabrication/cost buckets, or duplicate the existing Rhino/Grasshopper
geometry workflow. It owns exactly one thing: **turning a noisy structural
PDF into a semantically clean, geometry-aware record** --
`drawing_semantics.json` -- for the existing Grasshopper/Rhino takeoff
system to consume. See CLAUDE.md's own architecture invariants for the
adjacent (and separate) internal takeoff-prediction system this shares a
repo with; `semantic_preprocessor` does not import from, or get imported
by, `services.prediction.orchestrator` or any router -- it is a new,
additive service reachable only through its own entry points
(`pipeline.process_pdf` / `pipeline.process_primitives`).

| This system owns | Grasshopper/Rhino owns |
|---|---|
| PDF text extraction, semantic grouping, bounding boxes | Mature beam curve extraction (`MAIN_PlanPurging`) |
| Structural label parsing, normalization, repair, completion | Existing curve classification where reliable |
| Drawing-specific relation resolution (Drawing Language Profile) | Takeoff, quantity calculation, connections, fabrication |
| Confidence / abstention / human review | Downstream Rhino operations |
| `drawing_semantics.json` | Final takeoff output |
| Text <-> geometry-candidate ID mapping | -- |

## The four operations stay structurally separate

| Operation | Example | Authority | Module |
|---|---|---|---|
| **Normalization** | `HSS8X8X0.375` -> `HSS8X8X3/8` | Deterministic grammar + catalog | `normalization.py` |
| **Repair** | `W8XI0` -> `W8X10` | Catalog-constrained candidate, never auto-applied | `normalization._try_repair` |
| **Completion** | `W8` -> `W8X10` | Drawing evidence only (`source_verified`) | `drawing_language_profile.py` |
| **Association** | `W8X10` -> Beam geometry #291 | Spatial/topological evidence fusion | `association.py` |

Grasshopper geometry evidence is only ever allowed to influence
**association**. This is enforced in code, not just by convention: nothing
in `pipeline.py` ever assigns `GeometryEvidence`-derived text to
`Correction.canonical`. A GHX-paired beam's own label (if the capture
supplies one) is surfaced only as a `diagnostics.ghx_text_discrepancies`
entry -- see `test_semantic_preprocessor_pipeline.py::GhxNeverCompletesALabelTests`
for the regression test that would fail if this boundary were ever crossed.

## What's implemented (`backend/services/semantic_preprocessor/`)

| Module | Responsibility |
|---|---|
| `models.py` | Canonical dataclasses: `TextPrimitive`, `SemanticAnnotation`, `Modifier`, `StructuralParse`, `Correction`, `GeometryEvidence`, `AssociationCandidate`, `CoordinateTransform`, `SemanticDocument`. Confidence is `Optional[float]`; `None` means "not calibrated," never a fabricated `0.5`. |
| `extraction.py` | Thin adapter over the existing `services.pdf_parser.extract_document_structure` (PyMuPDF-backed, already captures bbox/font/rotation) into `TextPrimitive`s, plus a page classifier (`NATIVE_TEXT_HEALTHY` / `NATIVE_TEXT_GARBLED` / `NO_NATIVE_TEXT` / `IMAGE_DOMINANT` / `UNKNOWN`). No OCR wired in -- every project in this system's benchmark corpus is natively vector/text (verified this session); OCR stays out of the critical path until a page actually needs it. |
| `grouping.py` | Conservative, reason-coded semantic annotation grouping: same-baseline chain merge, bracket-modifier attachment (`W8X10` + `[24]`), and a narrowly-scoped cross-line HSS continuation merge (`HSS8X8` over `3/8` -> `HSS8X8X3/8`, with the implicit `X` separator inserted). Original per-fragment bboxes are always preserved in `source_fragment_ids`; `semantic_bbox` is a union, never a replacement. |
| `structural_parser.py` | Family/grammar detection only (W/M/S/HP/C/MC/L/2L, rectangular vs. round HSS, Pipe, PL, BP). Explicitly rejects architectural dimensions (`3'4"`). Grammar `"incomplete"` marks a bare `W8`-style shorthand as a completion case, never a normalization target. Catalog validation delegates to the existing `services.label_reconstruction.structural_parser.compatible_catalog_labels` when available (optional import, fails soft). |
| `normalization.py` | Deterministic canonicalization. The one highest-risk rule: rectangular/square HSS thickness converts decimal<->fraction (`0.375` -> `3/8`, tolerance-gated to standard 1/16" mill increments); round HSS/Pipe (`HSS5.563X0.258`) is a *different grammar* and is never touched, even though it shares the `HSS` prefix. Also contains a minimal, conservative repair layer (single-character OCR-confusion substitution, gated to an exact catalog-valid match, `auto_accept` always `False`) -- explicitly not a replacement for the existing ranking-based repair engine in `services.exact_section_predictor`. |
| `drawing_language_profile.py` | Consumer-side resolver for the real Drawing Language Profile schema (see "Protecting the DLP prototype" below). Only `source_verified` rules can authorize a completion; a page-scoped rule wins over a project-wide one; two `source_verified` rules disagreeing for the same scope is a conflict -> abstain, never guess. |
| `coordinate_transform.py` | 2D similarity (scale + rotation + translation + optional Y-flip) fit from point correspondences, with measured mean/median/P95/max residuals and a hard `valid` gate. `apply_transform`/`invert_transform` both refuse to run on an invalid transform. |
| `geometry_evidence.py` | `GeometryEvidenceProvider` ABC + `NullGeometryEvidenceProvider` (the default -- the pipeline runs to completion with zero geometry evidence) + `GrasshopperGeometryEvidenceProvider` (wraps an already-captured RH_OUT-shaped payload; no live Rhino.Compute call exists anywhere in this repo to wrap -- see `docs/ghx_geometry_audit.md`). Geometry identity is never list position: a `BeamElementID` (if the capture provides one) is preserved as `source_geometry_id`; otherwise a SHA1 fingerprint over rounded geometry attributes is used. |
| `association.py` | Evidence fusion. GHX's own text<->curve pairing is tried first (`associate_via_ghx_pairing`); a deterministic nearest-structural-geometry fallback runs independently (`associate_via_nearest_geometry`, refuses to run without a valid coordinate transform); `fuse_candidates` merges agreement, flags disagreement `needs_review` (`GHX_PDF_DISAGREEMENT`), and abstains (`AMBIGUOUS_MULTIPLE_BEAMS`) on a near-tie. |
| `pipeline.py` | `process_primitives` (core, directly testable) and `process_pdf` (real entry point). Enforces the completion boundary described above and computes each annotation's `review_status` from the worst of {correction, geometry association}. |
| `serialization.py` | `to_dict` / `to_json` for the `drawing_semantics.json` sidecar. Round-trip-tested. |

## GHX audit summary

Full forensic detail: `docs/ghx_geometry_audit.md` (SHA-256
`35d5bb064f30ad82c7364485f4a53ee15971581aed9d7b117e382e95c75fab0e`,
6,798,022 bytes, verified unchanged throughout this session). Headline
findings:

- **No existing Rhino.Compute integration anywhere in this codebase** --
  confirmed by repository-wide search across every worktree. The C#
  `i3dmBase64 -> GeometryBase` bridge exists inside the GHX itself, fully
  decoded, but nothing in the backend calls it. `GrasshopperGeometryEvidenceProvider`
  was built as a pure adapter with no live-call implementation as a result
  (Section 32/33's explicit fallback).
- **`MAIN_PlanPurging`, `MAIN_FilterBeamText`, `MAIN_BeamProcessing&Selection`,
  `MAIN_BeamsMomentConnection` are real Cluster components** (verified via
  their `ClusterDocument` payload, not their `Name` field, which holds the
  user's custom cluster name instead of the literal word "Cluster").
- **42 `RH_OUT:*` outputs found, each resolved to its real producing
  component** via the GH Group's own `ID`/`ID_Count` member list (not
  guessed).
- **The `BeamTxt` <-> `BeamCrv` pairing contract is explicitly unresolved**,
  not assumed. This is why `association.py` never assumes list/tree
  alignment between two separate RH_OUT outputs and only trusts a pairing a
  capture states explicitly.
- **Catalog contract divergence documented, not silently fixed**: the
  GHX's own AISC-lookup script references
  `backend/integrations/steel/section_catalog.py`, which does not exist
  anywhere in this repository. The actual current implementation is
  `services.normalization` / `services.label_reconstruction.structural_parser`.

## Protecting the DLP (Drawing Language Profile) prototype

The real legend/notes/table extraction implementation for Section 6/29 of
the original research brief already exists -- **uncommitted**, in the
sibling worktree `C:\Users\Bassam\git\ai-dynamic-regex-dlp`, branch
`bassam/drawing-language-profile`
(`backend/services/engineering/drawing_language_profile.py`, 714 lines).
It is materially more complete than what this session should rebuild: four
rule statuses (`source_verified` / `proposed_inference` / `conflicted` /
`rejected`, not just two), per-page rule scoping, per-rule source evidence
(page + quote), automatic conflict detection when two extracted rules
disagree, and a hallucination-grounding check for LLM-proposed rules.

This session's `drawing_language_profile.py` is the **consumer-side half**
of that same schema -- it performs only the lookup/precedence/conflict
policy (Section 29) against already-built rule dicts, and does not
duplicate the extraction step. **This is a protection strategy, not a
rebuild**: nothing in the DLP worktree's uncommitted files was read-write
touched this session. Recommended next step (not done this session, since
it touches someone else's uncommitted work in a different worktree):
commit that branch, then swap this module's rule-dict input for a direct
call to `extract_designation_rules` / `build_drawing_language_profile`.

## Coordinate systems

PDF page points and Rhino model units are never assumed interchangeable.
`coordinate_transform.fit_similarity_transform` requires >=3 real point
correspondences and reports `valid=False` outright when residuals exceed
threshold -- callers (`association.associate_via_nearest_geometry`) refuse
to run rather than silently comparing frames. **No real PDF<->Rhino
correspondence data was available this session** (no live Rhino.Compute
call, no captured `.3dm` for a real project) -- the coordinate module is
tested against synthetic correspondences with known ground truth (scale,
rotation, translation, Y-flip) and passes exactly. The live calibration
experiment (Top-5 Experiment 2 in the original research brief) remains a
pending real-data validation step.

## Validation strategy actually run this session

- 52 new unit/integration tests, all passing (`pytest backend/tests/test_semantic_preprocessor_*.py`).
- Full existing backend suite re-run: 325 passed, 5 pre-existing failures
  unrelated to this work (Excel-engine environment issue on `.xlsm` files
  and two multimodal-fusion database tests) -- confirmed unrelated by `git
  status` showing zero modifications to any file these tests touch.
- No production PDF was rewritten. No existing file was modified (this
  session is purely additive: one new package, nine new test files, one
  new script, two new docs).
- The source GHX file's SHA-256 was verified identical before and after
  this session.

## What's explicitly NOT done this session (by design, not oversight)

- **PDF rewriting.** Deferred per Section 39 -- text semantics, grouping,
  normalization, drawing-local completion, and the GHX bridge contract had
  to be proven first. The schema (`Correction`, `rendered_bbox`) already
  has the fields a future writer needs.
- **Live Rhino.Compute execution.** No client exists anywhere in this repo
  to build on; a fixture-based provider was built instead, with the exact
  capture payload shape documented in `geometry_evidence.py`.
- **A real coordinate calibration.** No real PDF+`.3dm` pair was available;
  the transform math is proven against synthetic data only.
- **Extending the DLP prototype's own extraction logic.** Deliberately
  left in its home worktree, uncommitted work, not touched.

## Recommended next implementation objective

**Run Top-5 Experiment 1 from the original research brief for real**: get
one representative project's PDF *and* its `.3dm`/Rhino.Compute output for
the same sheet, capture the real `RH_OUT:BeamTxt` / `RH_OUT:BeamCrv` /
`RH_OUT:BeamElementID` payloads, and answer the pairing-contract question
this audit could only leave open. Everything else in this package
(`GrasshopperGeometryEvidenceProvider`'s capture contract, `association.py`'s
fusion logic, the coordinate transform's validity gate) was built
specifically so that this experiment is a matter of writing one capture
adapter and running the existing test fixtures against real data, not a
redesign.
