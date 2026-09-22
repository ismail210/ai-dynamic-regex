# Documentation and Report Organization Plan

Baseline: `main` @ `5261ee1f1c4ccc428e28ce6c739dc145fd080b8a`. Scope: all tracked Markdown/JSON/CSV/image files
under `docs/`, `validation/semantic_test_pdfs/`, and the backend-root status docs identified during the file
inventory. **The untracked `docs/validation/phase_c_*`/`phase_d1_*`/`phase_d2_*` files remain completely
untouched** — they were never read, listed, or classified in this audit; only the ~123 pre-existing tracked
files under `docs/validation/` were inventoried. This document is a proposal; nothing has been moved.

## Canonical vs. point-in-time docs

**8 authoritative docs** named in CLAUDE.md: `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/FOLDERS.md`,
`docs/SERVICES.md`, `docs/TRAINING.md`, `docs/FRONTEND.md`, `docs/ENGINEERING_VALIDATION.md`,
`docs/DEPLOYMENT.md`. All 8 untouched since the 2026-07-31 "Initial commit" despite substantial subsequent
work — worth a maintainer review for staleness even though no code change is proposed here.

**Gap found**: 7 of the 8 are linked from README's "Documentation" section; `docs/ENGINEERING_VALIDATION.md` is
named authoritative in CLAUDE.md but is an orphan from README's own nav. Recommend adding the link (a doc-only
change, not part of this audit's scope to perform).

**A 9th de-facto canonical doc, not in either list**: `docs/architecture/unified_semantic_contract.md`
(2026-09-13, "Status: implemented"). It documents `backend/services/semantic/` as the canonical
semantic-contract module — verified live in code (matches the module CLAUDE.md's explainability-contract
invariant actually points at today), not just prose. **Recommend adding it to CLAUDE.md's authoritative list
and README's nav** as a documentation fix, tracked in the roadmap, not performed here.

**A discoverability gap, not a staleness one**: `backend/SEMANTIC_CONTRACT.md` (211 LOC) documents the same
live v2 contract module but sits at `backend/` root, outside `docs/` and outside every nav list. Proposed
destination: `docs/architecture/SEMANTIC_CONTRACT.md`, with a content diff against
`unified_semantic_contract.md` performed *before* any merge decision (they may already overlap).

**~150 of 173 tracked `docs/**` files are point-in-time reports/audits, not living docs**: `docs/accuracy_work/`,
`docs/audits/`, `docs/final_rnd_audit/`, `docs/geometry_graph_audit/` (10 files + CSV),
`docs/ml_association_phase/` (20 files — documents the `ml_association` shadow module CLAUDE.md forbids wiring
into production), `docs/ml_integration/` (3 files), and all of the tracked `docs/validation/` tree (gold-set
JSON, phase1-3 reports + measurement JSONs + 116 paired sample json/png files). None of these are referenced
*by* any of the 8 canonical docs (checked via `git grep` — zero cross-references found from
ARCHITECTURE/FOLDERS/SERVICES/TRAINING/API/FRONTEND/ENGINEERING_VALIDATION/README into any of these report
folders).

## Stale or conflicting documentation found (not rewritten — flagged only)

1. **`docs/geometry_graph_audit/06_research_findings.md`** explicitly states `docs/ARCHITECTURE.md` is
   "broadly consistent... but treat `docs/` as aspirational, not authoritative" because 4 of 10
   engineering/graph modules it found are dead code the architecture doc doesn't mention. This is the single
   most important conflict surfaced by this audit — it is a prior, independent audit already flagging the
   living docs as partially stale.
2. **`docs/final_rnd_audit/executive_summary.md`** found 2 of partner Ismail's neural components run
   unconditionally in production based only on file-existence, with accuracy never measured — this motivated
   `docs/ml_integration/partner_dl_governance_plan.md`'s 7-item checklist. **Whether that checklist is actually
   enforced in `model_registry.py` today was not verified in this audit pass** — flagged as a live risk
   requiring follow-up, not a documentation-organization issue per se.
3. **`docs/validation/phase3_gold_set_report.md` / `gold_set_v1.json`**: gold set has 0 records,
   "awaiting_human_association_review" — may still be true today (perpetually incomplete based on tracked
   evidence, not necessarily stale).
4. **Naming collision risk**: three unrelated "Phase 1/2/3..." numbering schemes coexist —
   `docs/ml_association_phase/`, `docs/validation/phase1-3*`, `docs/accuracy_work/phase1*`, and
   `backend/scripts/phase1..phase14*` ML-training scripts. These are genuinely different efforts sharing a
   generic numbering convention — high confusion risk for anyone reading `git log`/`git grep` results without
   this context. The proposed structure below groups each under its own subject folder specifically to defuse
   this.
5. **`docs/ESTIMA3D_MANAGER_DEMO_FLOW.md` / `_PRESENTATION_SCRIPTS.md`** (newest docs, 2026-09-16) are
   completely orphaned from README/CLAUDE.md nav despite being current, actively-relevant demo material.

## `validation/semantic_test_pdfs/` — confirmed active test fixture, not documentation

Referenced by `backend/tests/test_semantic_damage_manifests.py`,
`backend/tests/test_semantic_precedence_task_regression.py`, and 2 scripts
(`build_semantic_damage_test_pdfs.py`, `validate_demo_correction_flow.py`). **Should** conventionally move to
`backend/tests/fixtures/semantic_test_pdfs/`, but this is explicitly **not a plain doc move** — it requires
updating `REPO_ROOT`-relative paths in all 4 referencing files, or the test suite and those scripts break.
Tracked as a coordinated code+fixture move in the roadmap (Phase 6/7), not a documentation-only change.

## Proposed canonical documentation structure

```
docs/
  API.md, ARCHITECTURE.md, FOLDERS.md, SERVICES.md, TRAINING.md,
  FRONTEND.md, ENGINEERING_VALIDATION.md, DEPLOYMENT.md        <- canonical, linked from README (unchanged location)
  architecture/
    unified_semantic_contract.md                                <- already here; add to canonical list
    SEMANTIC_CONTRACT.md                                         <- moved from backend/ root (after content-diff review)
  demos/
    ESTIMA3D_MANAGER_DEMO_FLOW.md
    ESTIMA3D_MANAGER_PRESENTATION_SCRIPTS.md
  history/
    MIGRATION_NOTES_v5.2.md
  reports/                                                       <- archived, dated, read-only historical record
    accuracy-track/            (from backend/ root: A1_CONTEXT_SCOPE_AUDIT.md, A6_COMPLETION_EVIDENCE_DESIGN.md,
                                 ACCURACY_TRACK_A1_A8_STATUS.md)
    june-validation/           (from backend/ root: JUNE_STEEL_PAGE_INDEX.md, JUNE_PHASE3_VALIDATION_MANIFEST.json)
    ghx/                       (from backend/ root: GHX_REAL_DRAWINGS_EXPERIMENT.md,
                                 ghx_real_drawings_phase0d_evidence.json)
    backend/                   (backend/reports/broadened_xgb_ranker_benchmark.md)
    accuracy_work/             (current docs/accuracy_work/* — path unchanged, grouped under reports/ conceptually)
    audits/                    (current docs/audits/* — path unchanged; this codebase-refactor audit's own
                                 output lives here too, one level down)
    final_rnd_audit/           (current docs/final_rnd_audit/* — path unchanged)
    geometry_graph_audit/      (current docs/geometry_graph_audit/* — path unchanged)
    ml_association_phase/      (current docs/ml_association_phase/* — path unchanged)
    ml_integration/            (current docs/ml_integration/* — path unchanged)
  validation/                                                    <- current tracked docs/validation/* — path
                                                                     unchanged (phase1-3 reports + samples);
                                                                     the untracked phase_c/d1/d2 files layer into
                                                                     this same directory and are NOT part of this
                                                                     proposal (separate authorized review later)
validation/
  semantic_test_pdfs/  -> backend/tests/fixtures/semantic_test_pdfs/   <- coordinated move, update 4 referencing files
```

This intentionally does **not** move every `docs/` subfolder into a deep new hierarchy — most of the
already-organized `docs/accuracy_work/`, `docs/audits/`, `docs/final_rnd_audit/`, `docs/geometry_graph_audit/`,
`docs/ml_association_phase/`, `docs/ml_integration/`, and `docs/validation/` trees are left at their current
paths (they are already topically grouped and nothing references them by a path that would need to change) —
only the **backend-root loose status docs** (which have no consistent home today) get a real move, into new
`docs/reports/*` subfolders.

## Per-file disposition (representative sample; full detail in `file-inventory.csv`)

| Current path | Purpose | Relevance | Superseded? | Proposed destination | Referenced by tooling? | Keep/Archive/Merge/Delete |
|---|---|---|---|---|---|---|
| `docs/API.md` | Canonical API reference | Living | No | unchanged | README, CLAUDE.md | Keep |
| `docs/ENGINEERING_VALIDATION.md` | Canonical validation reference | Living | No | unchanged | CLAUDE.md only (README gap) | Keep + fix README link |
| `docs/architecture/unified_semantic_contract.md` | De-facto canonical contract doc | Living | No | unchanged | none yet (gap) | Keep + add to canonical list |
| `backend/SEMANTIC_CONTRACT.md` | Same subject as above, wrong location | Live but undiscoverable | Possibly overlaps unified_semantic_contract.md | `docs/architecture/SEMANTIC_CONTRACT.md` | 1 inbound ref | Move (after content diff) |
| `backend/ACCURACY_TRACK_A1_A8_STATUS.md` | A1-A8 sprint status snapshot | Historical | Completed checklist | `docs/reports/accuracy-track/` | 0 inbound refs | Archive |
| `docs/geometry_graph_audit/06_research_findings.md` | Independent prior audit | Historical, but flags ARCHITECTURE.md as stale | N/A | unchanged | 0 refs from canonical docs | Keep (high-value conflict flag) |
| `docs/ml_integration/partner_dl_governance_plan.md` | Live-risk governance checklist | Must-stay-canonical, enforcement unverified | N/A | unchanged | referenced by final_rnd_audit | Keep but document (verify enforcement) |
| `validation/semantic_test_pdfs/*` | Active test fixture (7 files) | Active | No | `backend/tests/fixtures/semantic_test_pdfs/` | 4 code/test files | Move (coordinated) |
| `docs/database/aisc_v16_parser_fix_before_after.md` (backend/database/reports/) | Point-in-time fix note | Historical | Possibly | `docs/reports/backend/` | 0 inbound refs | Archive |

The complete row-by-row disposition for all ~180 documentation/report/fixture files is in
`file-inventory.csv` (filter `classification` in `documentation`, `report/audit`, `research/reference`, or
`fixture/sample` and `subsystem` under the docs/validation scopes).

## Explicitly preserved, not touched

`docs/validation/`'s untracked `phase_c_*`/`phase_d1_*`/`phase_d2_*` files exist alongside the tracked
`docs/validation/` tree at the same path. They were **not** read, opened, or classified anywhere in this audit.
Any future integration of that untracked content into the canonical structure above requires a separate,
explicitly authorized review — this plan only accounts for what was already tracked at the audited baseline.
