# Phase 3 Readiness Decision (Phase 2.5)

## Recommendation: **B — Conditionally ready, after a defined set of small fixes and additional annotations**

Not **A** (ready now): there is zero reviewed real-project ground truth (`real_project_annotation_status.md`), and Phase 3's core purpose — reproducing the current heuristic and a repaired baseline on real, project-grouped, *reviewed* data — cannot proceed without it. Reporting frozen-baseline accuracy numbers today would mean reporting them against nothing.

Not **C** (not ready / fundamentally unreliable): extraction is reliable (zero failures across 262 real pages), the dataset schema held up against 1,253 real label groups with zero validation errors, reviewer exports are deterministic and visually correct where inspected, and candidate generation finds a real target within top-10 for 96.5% of real labels. The pipeline mechanism works. What's missing is data and two known, well-scoped defects — not a redesign.

## Against the stated Phase 3 readiness criteria

| Criterion | Status |
|---|---|
| Reproducible real-project extraction | **Met** — zero failures, deterministic IDs confirmed on real data (byte-identical exports across repeated runs) |
| Usable reviewer exports | **Mostly met** — coordinate-correct, deterministic; file-size and extreme-crop-aspect-ratio issues documented, not yet blocking for a bounded batch |
| No critical coordinate mismatch | **Met** — no misalignment observed in manual inspection |
| No silent ID mismatch | **Met** — deterministic IDs, schema validation passed on all real data |
| Candidate sets containing the correct target often enough to make ranking meaningful | **Plausible but unverified** — 96.5% of real labels get at least one candidate within top-10, and the leader-resolution mechanism demonstrably surfaces better alternatives than production's pick in the specific 28.8% leader-contaminated case; but "contains the correct target" cannot be confirmed without reviewed truth |
| At least a small reviewed real-project batch | **Not met** — 108 groups are prepared and prioritized; zero are reviewed |
| Project-level identifiers suitable for leakage-safe splitting | **Met** — `project_id` is a required, caller-supplied field; all 7 real projects have distinct sanitized IDs ready for group-based splitting |
| Explicit separation between confirmed truth and inferred spreadsheet references | **Met** — `real_project_excel_assessment.md` classifies every possible Excel linkage and confirms none is used as truth |

## The defined set of small fixes/annotations needed to reach "A"

1. **Get the 108-group prioritized batch (or a similar batch) reviewed by a human** (internal estimator or structural engineer) using the existing export/import workflow — this alone is the largest blocker. No code change required, only reviewer time.
2. **Decide what to do about the 28.8% leader-as-target production defect** before treating current-heuristic accuracy as a fair baseline — either fix it (production change, needs separate approval per this phase's guardrails) or explicitly account for it as a known-bad baseline characteristic in Phase 3's comparison design.
3. **Decide whether the fraction-suffix label-splitting extraction defect** needs a fix before Phase 3, since it silently duplicates/corrupts a subset of real labels (both forms get separately counted as if genuine).
4. **Optional but recommended**: address the reviewer-export file-size/crop-aspect-ratio issues before scaling review beyond this pilot's bounded batch, so reviewer time isn't spent fighting the tool.

None of these require new research or a design overhaul — items 1 and 4 are process/tooling work, items 2-3 are small, well-isolated production bug fixes with a clear, already-quantified real-data justification.

## Exact next recommended implementation phase

**Not Phase 3 model/frozen-baseline work yet.** Recommended immediate next step: **a short "Phase 2.6" human-review pass** — get the existing 108-group batch (or an expanded one) reviewed by an actual person with domain knowledge, using the workflow already built and validated in Phase 2/2.5. Once even a modest reviewed batch exists (the pilot spec's own "50-100 label groups" target is already prepared), Phase 3's frozen-baseline evaluation becomes meaningful rather than vacuous, and the leader-as-target and label-splitting defects can be assessed for fix-before-baseline vs. fix-after-baseline with real accuracy numbers in hand rather than a guess.

Do not begin Phase 3 frozen-baseline evaluation, Phase 4 model training, or any XGBoost work until a reviewed batch exists and this decision is revisited.
