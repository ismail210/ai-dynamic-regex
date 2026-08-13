# Double-Review Subset (Phase 2.6)

37 of the 108-group human-review batch (34.3%) are selected for **independent double review** — reviewed separately by two different reviewers, without either seeing the other's decision beforehand (`human_review_protocol.md` §6) — so inter-rater agreement can be measured once real reviews exist. This exceeds the phase spec's "20-25%+" requirement.

Selection is produced by `backend/scripts/select_double_review_subset.py`, a deterministic, tracked script (no `random` module, no wall-clock input — same run always produces the same 37 group IDs). Source data: `training/ml_association/real_project_pilot/working_notes/batch_audit_rows.json` (git-ignored, per-group metadata only, no drawing content). Full machine-readable output: `training/ml_association/real_project_pilot/working_notes/double_review_subset.json` (git-ignored).

## Selection rule

A deterministic integer priority score per group, ranked highest-first (ties broken by a SHA-1 hash of `group_id`, not row order):

| Signal | Points | Why |
|---|---|---|
| `has_leader_evidence=True` | +2 | Directly targets the pilot's headline finding — production selected a leader stroke itself as the final target in 28.8% of its selections (`real_project_pilot_results.md`) — agreement specifically on leader-involving groups is the most decision-relevant number this phase can produce. |
| Belongs to a repeated `(project, page, label_raw_text)` combination | +2 | Flagged in `annotation_guidelines.md` as having an open scope-boundary question (`repeated` vs. independent instances) — worth a second independent judgment. |
| `page_type` in {leaders or arrows, repeated steel labels, no valid geometry target likely, several adjacent candidate members, incomplete or damaged labels} | +1 | These page types were deliberately selected during pilot page selection (`real_project_pilot_manifest.json`) to stress-test the harder parts of the pipeline. |
| `candidate_count <= 3` | +1 | Sparse-candidate groups are both rarer and higher-stakes to get right. |

Then a floor guarantee, applied by walking the same deterministic order: **every one of the 7 projects gets at least 2 groups**, and **every one of the 11 `page_type` categories gets at least 2 groups**, so no project or page-type category is entirely absent from the double-reviewed set even if it scored low on the signals above.

## What this subset deliberately does NOT try to select on

- **Cross-detail/cross-region contamination**: not used as a signal because no data field for it exists anywhere in this repository — `region_id` is `None` on every one of the 1,253 real label groups built in Phase 2.5 (no region/detail-segmentation layer exists; `docs/geometry_graph_audit/08_prioritized_roadmap.md` P1.4 is still open). Selecting on this would require fabricating a signal that isn't there.
- **Multi-target and candidate-generation-miss outcomes**: these are properties of a *review decision*, which doesn't exist before any review happens — they cannot be used as a pre-review selection signal without effectively guessing the outcome in advance. `page_type == "no valid geometry target likely"` is used as the closest available a priori proxy (2 groups guaranteed via the page-type floor).

## Observed result: 100% of selected groups are repeated-combo groups

All 37 selected groups happen to belong to a repeated `(project, page, label)` combination. This is not a selection-code bug — 78 of the full batch's 108 groups (72%) already belong to a repeated combination (the same label text recurring on the same page for different real members is common on framing plans), so "repeated" is the dominant class, not a rare edge case, and it stacks with the leader-evidence signal (31 of 37 selected groups, 83.8%, also have leader evidence — versus 63% in the full batch). **No genuinely single-instance, non-leader "easy case" group is present in the double-review subset.** This is a deliberate consequence of prioritizing difficulty per the phase spec, not an oversight — but it means agreement statistics computed from this subset will describe agreement on the *harder* end of the batch, not the batch as a whole. `real_ground_truth_metrics.md` (pending real review data) must state this explicitly rather than generalize double-review agreement to the full 108-group batch.

## Resulting distribution

| | |
|---|---|
| Selected | 37 / 108 (34.3%) |
| Leader evidence | 31 / 37 (83.8%) |
| Repeated-combo | 37 / 37 (100%) |

By project: project_001: 4, project_002: 2, project_003: 2, project_004: 7, project_005: 3, project_006: 10, project_007: 9.

By page type: dense vector page: 3, detail page #1: 3, detail page #2: 2, incomplete or damaged labels: 2, leaders or arrows: 2, no valid geometry target likely: 2, repeated steel labels: 8, schedule or table page: 2, several adjacent candidate members: 9, structural framing plan #1: 2, structural framing plan #2: 2.

## Selected groups

Referenced by `group_id` — open each via the review kit's `index.html` (search or scan for the label text below) or navigate directly to `<group_id>.html` in the review kit directory.

| group_id | pilot | project | page | label | page_type | candidates | leader |
|---|---|---|---|---|---|---|---|
| group_1368ee2f9d59defe | pilot_08 | project_006 | 22 | W14X34 | repeated steel labels | 10 | yes |
| group_16fea683a4647cdd | pilot_05 | project_004 | 8 | W24x55 | dense vector page | 8 | yes |
| group_17edf9fbad025503 | pilot_08 | project_006 | 22 | W14X34 | repeated steel labels | 10 | yes |
| group_1c44540275556d0b | pilot_08 | project_006 | 22 | W24X62 | repeated steel labels | 6 | yes |
| group_2090bcc3e4b64b0a | pilot_02 | project_003 | 39 | W27x84 | structural framing plan #2 | 10 | yes |
| group_2212c07e504f1566 | pilot_07 | project_006 | 43 | W8X31 | leaders or arrows | 4 | no |
| group_3697c2e6ab2343c2 | pilot_10 | project_007 | 7 | W18X35 | several adjacent candidate members | 10 | yes |
| group_3dcb0645febb6c6a | pilot_03 | project_005 | 8 | L2x2x1 | detail page #1 | 10 | yes |
| group_46c918f79c9fb03f | pilot_10 | project_007 | 7 | W18X60 | several adjacent candidate members | 10 | yes |
| group_4d8db4ae608398d9 | pilot_05 | project_004 | 8 | W24x55 | dense vector page | 9 | yes |
| group_52c809980b4bea30 | pilot_07 | project_006 | 43 | W8X31 | leaders or arrows | 3 | no |
| group_547b49fcd61cff36 | pilot_11 | project_001 | 30 | L4 x 4 x 1/4 | no valid geometry target likely | 7 | no |
| group_569e830f8ddb1d61 | pilot_10 | project_007 | 7 | W18X35 | several adjacent candidate members | 10 | yes |
| group_5e95f6153cbe3b39 | pilot_08 | project_006 | 22 | W12X40 | repeated steel labels | 10 | yes |
| group_640eee4e144f2a0d | pilot_01 | project_002 | 10 | W10X19 | structural framing plan #1 | 10 | yes |
| group_683dbcdb567930eb | pilot_08 | project_006 | 22 | W14X34 | repeated steel labels | 9 | yes |
| group_6a98b7031ee45aee | pilot_10 | project_007 | 7 | W18X40 | several adjacent candidate members | 10 | yes |
| group_6abacd6e6e608215 | pilot_08 | project_006 | 22 | W12X40 | repeated steel labels | 10 | yes |
| group_6e34d504eefdd119 | pilot_03 | project_005 | 8 | L2x2x1 | detail page #1 | 10 | yes |
| group_71e5ce030b415861 | pilot_10 | project_007 | 7 | W18X40 | several adjacent candidate members | 10 | yes |
| group_76834c9cca5c5752 | pilot_10 | project_007 | 7 | W18X50 | several adjacent candidate members | 10 | yes |
| group_815e83fede3a1864 | pilot_01 | project_002 | 10 | W18X40 | structural framing plan #1 | 10 | yes |
| group_88a62395c2299f1c | pilot_02 | project_003 | 39 | W18x50 | structural framing plan #2 | 10 | yes |
| group_95859deb2eea7dbe | pilot_04 | project_004 | 19 | HSS8x8x1/2 | detail page #2 | 10 | no |
| group_999f7b3bda115615 | pilot_05 | project_004 | 8 | W24x55 | dense vector page | 4 | yes |
| group_a4109becbbf320e9 | pilot_10 | project_007 | 7 | W18X40 | several adjacent candidate members | 10 | yes |
| group_a9ad30bfe3d29e99 | pilot_09 | project_001 | 22 | W14X26 | incomplete or damaged labels | 10 | yes |
| group_add9d5346289471d | pilot_11 | project_001 | 30 | L4 x 4 | no valid geometry target likely | 6 | no |
| group_b4139acbde4e7e9b | pilot_12 | project_004 | 3 | W16x26 | schedule or table page | 10 | yes |
| group_ba1e35d259000c64 | pilot_10 | project_007 | 7 | W18X50 | several adjacent candidate members | 10 | yes |
| group_bed7620b78fe0563 | pilot_04 | project_004 | 19 | HSS8x8x1/2 | detail page #2 | 10 | no |
| group_c08f3a22bfc27c50 | pilot_08 | project_006 | 22 | W12X40 | repeated steel labels | 10 | yes |
| group_d5188594198c0953 | pilot_12 | project_004 | 3 | W16x26 | schedule or table page | 8 | yes |
| group_d9e7bbd8be9d93d5 | pilot_09 | project_001 | 22 | W14X26 | incomplete or damaged labels | 4 | yes |
| group_ef7d8f9e331f60ae | pilot_08 | project_006 | 22 | W24X62 | repeated steel labels | 7 | yes |
| group_f4e5ec4f99b2a4b6 | pilot_03 | project_005 | 8 | W8x10 | detail page #1 | 10 | yes |
| group_f54509f91e3e34c6 | pilot_10 | project_007 | 7 | W18X40 | several adjacent candidate members | 10 | yes |

## Reproducing this selection

```
cd backend
python scripts/select_double_review_subset.py
```

Regression-tested with synthetic fixtures in `backend/tests/test_select_double_review_subset.py` (determinism across repeated runs, stability under input row reordering, minimum-floor guarantees, repeated-combo prioritization).
