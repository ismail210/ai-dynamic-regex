# Schedule-region quarantine — full-corpus validation (Phase 3)

Measurement only. Production ran at committed defaults (`SCHEDULE_REGION_QUARANTINE_ENABLED`
off). The quarantine was called directly on a side path in each worker, and its output was
projected onto the baseline; it was never enabled. Code under test: `700c72f` (before the
partner's `f47bda1` was integrated) plus the harness `backend/scripts/benchmark_full_corpus_quarantine.py`
as it stood then. Raw run directories stay local and are not committed. Everything in this
folder is sanitized: relative paths only. See the **Integration addendum** at the end for what
changed afterwards.

**Verdict: keep the quarantine shadow-only and disabled by default. Do not advance it, and do
not reject it.** Every safety gate holds, and the measurement layer is fully deterministic. But
no ground truth anywhere can score it. Also, 86% of what it removes is the *only* occurrence
of that section in the document, so enabling it before a matrix parser supplies replacement
counts would drop column sizes from the takeoff.

## 1. Corpus coverage

| | count |
|---|---:|
| PDF references (zip + attachments) | 205 |
| Unique PDFs after SHA-256 dedup | 202 |
| Excluded (encrypted / unreadable) | 0 |
| Projects (folder key) | 48 |
| Pages / pages with vector text / textless pages | 2,910 / 2,897 / 13 |
| Docs with textless pages / fully textless | 3 / 1 |
| Skipped pages (rich-page limit) | 0 |
| Docs with engineering tokens / with takeoff-eligible exact sections | 170 / 62 |
| Known development projects present (Burrville, GCDC, Springhill, H5 Herndon, Sidwell, …) | 11 docs |
| Workbooks / GT pairings (confident / ambiguous) | 18 / 11 / 5 |

Each run processed all 202 unique PDFs: 202 `ok`, 0 `failed`, 0 `resource_gap`, exit code 0.

## 2. Run integrity (`integrity_check.json`)

- Both run directories hold exactly 202 `DOC-*.json` files. Every `doc_id` matches its filename
  and every status is `ok`. The same 11 GT-paired docs carry a prediction projection in both
  runs.
- All four recorded flags are `false` in all 404 outputs, including
  `schedule_region_quarantine_enabled`.
- **Provenance caveat for run 1:** 145 outputs come from an earlier pass (~02:32), which used an
  earlier harness revision and an earlier manifest. The other 57 come from a resume that
  finished at 11:07. Run 2 is a single pass. Both manifests map every doc_id to the same
  SHA-256 and pair GT identically; only `local_path` differs. Every measurement field in the 145
  early outputs matches run 2 exactly (see §3), so the revision change did not alter any
  recorded measurement.

## 3. Determinism (`determinism_comparison.json`, `default_off_confirmation.json`)

The raw comparison from `report` shows 39 identical and 163 differing docs. **Every difference
is in exactly three fields:** `production.digest` (163 docs), and
`production.reference_check.equal` plus `gates.default_off_production_differences` (the same
40 docs). If those three fields are excluded, **202/202 docs are identical** across runs.
That covers token counts, eligible-by-section/family/page, page roles, schedule evidence, every
shadow region and bbox, every quarantined token, the projection, and served predictions.

**Root cause:** `production.digest` hashes the whole extracted document, including
`legend_profile.drawing_intelligence.narrative.*` and `.overview`. The Drawing Summary LLM
writes those fields, and `DRAWING_SUMMARY_LLM_ENABLED` defaults to `true`. Reproduced on
DOC-169: 3 extractions with the same code gave 2 distinct digests, and the only differing
paths were the 7 narrative/overview prose strings. The harness records `legend_profile_llm_enabled`
but not this flag.

## 4. Safety gates (`hard_gates.json`)

| gate | total |
|---|---:|
| live_token_mutations | 0 |
| unquarantined_token_changes | 0 |
| plan_labels_outside_regions_changed | 0 |
| ambiguous_regions_auto_quarantined | 0 |
| context_definitions_counted | 0 |
| definition_rows_counted_in_shadow | 0 |
| schedule_evidence_as_quantity | 0 |
| invalid_catalog_auto_accepts | 0 |
| cross_document_leaks | 0 |
| default_off_production_differences | 127 raw → **0 after confirmation** |

The raw 127 is the same LLM prose noise, not a production change. Here is why:

- By inspection, the only change to `services/` between the `30bc54d` reference and `700c72f` is
  a block guarded by `settings.schedule_region_quarantine_enabled`, plus the module-level import
  of `settings`.
- Confirmation run with `DRAWING_SUMMARY_LLM_ENABLED=false` on 60 docs. The sample was all 40
  docs whose reference check flipped between runs, the 15 smallest unequal in both runs, and the
  5 smallest equal in both runs. Results: the working-tree engine was deterministic on 60/60,
  and its output was byte-equal to the `30bc54d` engine on **60/60**.

## 5. Schedule regions and labels identified

| region class | count | exact labels inside | quarantined |
|---|---:|---:|---:|
| confident — `column_matrix_geometry` | 72 | 2,226 | 2,226 |
| confident — `structured_schedule_evidence` | 104 | 72 | 64 |
| ambiguous — `column_matrix_geometry` (never quarantined) | 72 | 423 | 0 |

- 48 docs have at least one region. 30 docs and 23 projects have at least one quarantine.
- Titles on structured regions: `schedule` 68, `lintel` 14, `column` 12, `bearing_plate` 10.
  87 confident regions quarantine nothing (mostly structured schedules with no steel labels).
- 52 of the 72 confident matrix regions have **no schedule title**. They were accepted on
  geometry evidence alone (column-locations header, regular vertical grid, level datum axis,
  catalog-label density).
- Structured schedule evidence: 104 regions, 687 rejections, and 1 conflict (1 doc).

## 6. Shadow-quarantine effect (`document_metrics.csv`, `section_deltas.csv`)

- Corpus baseline eligible exact-section tokens: 38,031. Quarantined: 2,288 eligible (+2
  non-eligible). Projected: 35,743, a **−6.02%** change.
- Per affected doc: 22 docs lose 10–25%, 7 lose 5–10%, and 1 loses 0 eligible tokens. The
  largest drop is 19.4% (Tempelton, William Winchester).
- Families: W 2,079 and HSS 211. W depth: W8 192, W10 1,188, W12 398, W14 269, W16 2, W18 30.
  So 98.5% of the W labels are W8–W14, the usual column profile.
- Every W16+ hit is either in the GCDC Bldg 4 column matrices (W18X311 columns, the same
  schedule Phase 2 found) or in two small lintel schedules.
- 11 GT-paired docs got served predictions. The quarantine removed predictions in 2 of them:
  Tempelton (150 of 772) and Wellness Center (32 of 232). The other 9 were unchanged.

## 7. False-positive / false-negative evidence

**No ground truth supports an FP/FN measurement.**

- All 11 confident pairings came back `ground_truth_evaluable = False`. The workbooks are
  estimator QTO books with sheets such as `ST`, `Main Frame`, `Structural`, and `MM`. The
  repository GT parser recognises only Revit-schedule sheet names, so it returned zero rows.
  The harness correctly declined to score against empty GT rather than report a fake 0%
  precision.
- The dev projects that do have Revit GT (Burrville, GCDC, Springhill, Sidwell) are not paired
  in this corpus. Phase 2 also found no page-scoped Revit GT.
- The 262-record column-schedule reviewer gold package (`30bc54d`) has not been reviewed yet.

Structural proxies (not accuracy metrics):

- *FP proxy (removing real plan labels):* 0 plan labels outside regions changed, 0 ambiguous
  regions quarantined, and 0 nearby outside labels changed. There are 9 exact labels near a
  region boundary (6 regions), and 81 tokens straddle a boundary (19 regions). All of them are
  queued for review.
- ***FN risk (the main finding):*** 1,969 of the 2,288 quarantined labels (86%, in 29 docs,
  225 doc×section pairs) are the **only** eligible occurrence of that section in the document.
  Those are mostly W≤14 and HSS column sizes. If the quarantine were enabled as-is, those sizes
  would vanish from the takeoff. Double counting is only removed correctly if the plans already
  count those columns, and column schedules are usually their sole source. The matrix parser
  has to supply mark×tier counts first.
- *Unverified templates:* 551 review-queue rows come from projects outside the development set.

## 8. Reviewer queue (`review_queue.csv`)

838 rows cover 202 regions in 40 docs. Up to 10 sample labels are listed per region, and rows
are sorted by priority. Reasons:

| reason | rows |
|---|---:|
| large_reduction_without_ground_truth | 582 |
| new_project_template_unverified | 551 |
| titleless_matrix_region | 520 |
| tokens_straddle_region_boundary | 107 |
| ambiguous_boundary_region | 72 |
| region_covers_large_page_area | 52 |
| exact_labels_near_region_outside_bounds | 6 |
| schedule_evidence_conflicts | 1 |

## 9. Limitations and coverage gaps

1. There is no evaluable GT, because the QTO workbook format is unsupported. FP/FN are
   unmeasured.
2. In these runs, `production.digest` and the default-off gate included LLM prose.
   Default-off equality was confirmed on a 60-doc sample, not all 202 docs. (Fixed in the
   harness afterwards; see the addendum.)
3. Run 1 mixes two harness revisions (145 + 57 docs). All measurement fields still match run 2
   exactly.
4. 13 textless pages (3 docs, 1 fully textless) are outside what vector-text extraction can see.
5. 72 ambiguous regions (423 labels) are deliberately left unquarantined, and their correct
   treatment is unknown. 52 confident matrix regions have no title.
6. The corpus contains no image-only schedules and no non-US / metric sections. Behaviour
   there is untested.

## 10. Recommendation

**Keep it shadow-only; do not advance, do not reject.**

- *Why not reject:* all safety gates are clean, the layer is fully deterministic across 202
  docs, and it hits the intended target (column-schedule matrices) in 23 projects, most of them
  new.
- *Why not advance:* there is no FP/FN evidence, and 86% of its removals would delete the only
  source of a section. Promotion is blocked on three things: (a) reviewer decisions on the
  262-record gold package and the priority ≥3 rows of this queue, (b) a matrix parser that
  supplies replacement column counts, and (c) GT support for the QTO workbook format, or a
  paired Revit-GT set, so FN can be measured.

## Files

`document_metrics.csv` · `section_deltas.csv` · `ground_truth_comparison.csv` · `review_queue.csv` ·
`hard_gates.json` · `determinism_comparison.json` (all generated by
`benchmark_full_corpus_quarantine.py report`) · `integrity_check.json` ·
`default_off_confirmation.json` (this validation pass).

`report` also writes `run1_summary.json` and `run2_summary.json`, per-document raw dumps of about
900 KB each. They are intentionally not committed: they can be regenerated from the local run
directories, and `determinism_comparison.json` plus `document_metrics.csv` already carry the
evidence. The raw persistent benchmark data (corpus copy, manifest with local paths,
`run1/`, `run2/`, A/B outputs) stays local and is not committed.

## Integration addendum (2026-09-24)

This report was produced **before** the partner commit `f47bda1` (BP/CL/C/L schedule-mark
resolution) was integrated. **The 202-document corpus was not rerun against the final merged
commit.**

- **What the numbers above describe:** two full passes on the pre-partner local code (`700c72f`).
  Both finished 202/202 `ok` with exit code 0. Every structural field was identical across runs
  for all 202 documents. Raw-digest differences came only from the free-form Drawing Summary
  LLM narrative.
- **Partner A/B (16 documents, Drawing Summary LLM disabled in the subprocess environment only):**
  - Documents: Struct.pdf; lintel/BP schedule sets; H5 Herndon; column-matrix, ambiguous-only
    and textless documents; controls. Compared base `77f0ea0` with partner `f47bda1`.
  - Eligible exact-section tokens were identical in 15/16 documents (Struct.pdf +4 newly kept
    labels), and no exact label lost eligibility. So partner mark resolution did not materially
    change the quarantine's inputs.
  - QuantityEngine: `Schedule mark map` plan callouts now count. Schedule cells, including
    schedule-only sections, count 0 (`excluded_schedule_only`). That is the partner's intended
    policy, and it is kept.
- **Regression found and fixed:** the A/B found one exact label destroyed on DOC-187 (H5
  Herndon) page 3. The newly extracted `BP3` sat directly under `W14x90`, and the fragment
  grouper merged them into `"W14x90 BP3"`, which the filter then dropped. After integration,
  the grouper never joins a catalog-exact section with a BP/CL/C/L schedule mark (regression
  tests included).
- **Harness digest:** the harness now records `drawing_summary_llm_enabled`. It keeps the raw
  `digest` and adds `structural_digest`, which leaves out only
  `legend_profile.drawing_intelligence.narrative` and `.overview`. The default-off gate now uses
  the structural comparison. This was not applied retroactively to the runs above.
- **Unchanged:** the quarantine remains shadow-only and disabled by default
  (`SCHEDULE_REGION_QUARANTINE_ENABLED=false`), and nothing in the production quantity path
  reads it.
- **Still missing:** scoreable ground truth. The paired QTO workbooks are not supported by the
  current Revit-schedule parser.
- **Future work:** the matrix/count parser and a QTO ground-truth parser.
