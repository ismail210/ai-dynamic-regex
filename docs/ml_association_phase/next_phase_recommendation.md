# Next Phase Recommendation

## Is the repository ready for Phase 3 (frozen-baseline evaluation)?

**Not yet — one real gap, clearly scoped.** Phase 2's own acceptance criteria (deterministic dataset construction, exportable candidate context, validated reviewer import, append-only outcomes, no project/page mismatch able to enter reviewed truth, explicit candidate-generation-miss representation, reproducible output, unchanged production behavior) are **all met on synthetic fixtures** — see the test results in the final report and `docs/ml_association_phase/unresolved_questions.md` items 6-10 for known, contained design limitations (not correctness bugs).

What's missing is exposure to **real project PDFs**. None were available in this environment (confirmed again in this phase — same finding as Phase 0/1). Every one of the 78 new tests uses either hand-built extraction dicts or small synthetic PyMuPDF fixtures. This matters specifically for Phase 3 because:

- Phase 3's whole purpose is to reproduce the *current production heuristic* and a *repaired deterministic baseline* on **project-grouped real data** and measure their actual accuracy — that requires real projects to group by, by definition.
- Candidate-generation recall (the release gate the deep-research report emphasizes most) can only be measured meaningfully against pages with genuine density, genuine leader/dimension/grid ambiguity, and genuine multi-detail layouts — none of which a handful of synthetic fixtures can represent at realistic scale or variety.

## Recommended next action

**Two things in parallel, not strictly sequential:**

1. **Source real project PDFs** (and, ideally, a small first batch of human-reviewed label groups using this phase's export/import workflow) before starting Phase 3's frozen-baseline work in earnest. This was already the standing recommendation at the end of Phase 1 (`docs/ml_association_phase/baseline_results.md`) and remains the single highest-leverage next step — nothing else in this roadmap can be honestly validated without it.
2. **Run a small pilot review batch** using this phase's tools against whatever real PDFs become available: `service.build_dataset` → `service.export_groups` → have 1-2 people actually review a few dozen label groups → `service.submit_review` → `service.latest_outcomes`. This will surface real usability problems in the export/import workflow (annotation guideline gaps, awkward SVG overlays, missing evidence fields) far faster than more synthetic-fixture testing would, and produces the first genuine reviewed data Phase 3 needs.

Do **not** proceed to Phase 3's frozen-baseline comparisons, Phase 4's ranker training, or any further phase until at least a first real-project pilot batch exists — running the frozen-baseline evaluation exclusively against synthetic fixtures would produce numbers that look precise but measure nothing about real-world performance, which is exactly the kind of overclaiming this entire audit-and-roadmap effort has been careful to avoid.

## What Phase 2 quietly de-risked for later phases

- The append-only outcome store and its supersession semantics are fully built and tested now, before any real reviewer touches it — a schema mistake here would be far more expensive to fix after real review data has accumulated.
- The validation rule set (18 distinct rejection codes) was designed and tested against edge cases (leader-support-as-target, single/multi-target scope mismatches, candidate-generation misses) before a human reviewer could develop bad submission habits around a looser system.
- The feature-flag/production-isolation discipline (`ML_ASSOCIATION_DATASET_ENABLED`, the structural not-wired-into-production test) means real-project experimentation in Phase 3 can proceed without any risk to current users, by construction rather than by careful operator discipline alone.
