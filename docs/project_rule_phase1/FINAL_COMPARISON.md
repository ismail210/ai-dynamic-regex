# Project-rule Phase 1 — Baseline vs Shadow Comparison

Recorded 2026-09-23. Companion to `BASELINE_STATE.md` (Gate 0 audit). Nothing committed or pushed.

## Start / end state

| | Value |
|---|---|
| Start SHA | `77f0ea03692358e0718f3975156f23bd4808c31c` (`main` = `origin/main`) |
| End SHA | unchanged (working-tree changes only, uncommitted) |
| Pre-existing drift | untouched — 3 modified + 5 untracked `backend/training/**` files, `docs/deep_research_project_rule_intelligence/`, 17 `docs/validation/phase_{c,d1,d2}_*` files |

## How to read this report — four evidence classes

| Class | Meaning here | Where |
|---|---|---|
| Code-wired behaviour | Traced statically from source (call sites, flags) | "Verified architecture", BASELINE_STATE.md |
| Synthetic regression performance | Scores on author-written fixtures; a regression guard, **not accuracy evidence** | "Synthetic results" |
| Unlabelled real-document discovery | What each pipeline emits on 7 real PDFs with **no gold**; counts, not correctness | "Real-corpus discovery" |
| Measured accuracy | Scores against reviewer-approved gold | **None exists yet.** No number in this report is a real-document accuracy figure. |

## Files changed

| File | Why |
|---|---|
| `backend/scripts/evaluate_project_rules.py` (new) | Read-only benchmark harness: manifest loader (synthetic words or local PDFs via env var), baseline + shadow pipelines, row/region/token scoring, safety gates, per-project/template/source/family slices, JSON/CSV/MD + annotation queue. |
| `backend/tests/fixtures/project_rules/synthetic_manifest.json` (new) | 5 synthetic documents (4 template families) + 14 token cases covering plan cases 1–14. Unsupported baseline behaviour is labelled `unsupported` / `known_defect`, never passed. |
| `backend/tests/test_project_rule_benchmark.py` (new) | CI: no unlabelled baseline regressions, hard safety gates, semantic-lock token cases, tracked known defect. |
| `backend/tests/test_schedule_evidence_shadow.py` (new) | Current-mode map == legacy map; plate evidence + provenance; hyphen marks only when widened; mark letter never sets family; conflict → review; reinforcing schedule rejected; flags default off; no production reader of the shadow artifact. |
| `backend/services/engineering/schedule_grid.py` | Shadow `build_schedule_evidence` (+ `schedule_mark_map_from_evidence`). Legacy and shadow share one row splitter (`_split_row`); `_schedule_kind` gained an optional x-span and returns the title blob. Legacy output unchanged (all legacy tests green). |
| `backend/config.py` | `SCHEDULE_EVIDENCE_SHADOW_ENABLED` (default false), `SCHEDULE_EVIDENCE_SHADOW_WIDENED` (default false). |
| `docs/project_rule_phase1/{BASELINE_STATE,FINAL_COMPARISON}.md`, `synthetic_results/` | Reports. Real-corpus outputs stay outside git (scratchpad). |

Production behaviour with default flags: identical. The shadow artifact is written only when the flag is on and nothing in `services/` or `routers/` reads it (guard test).

## Verified architecture (short; see BASELINE_STATE.md)

- `schedule_grid` reads **all** pages; the only page filter is literal `MARK` + `SIZE` words. Page role is not a gate.
- Mark grammar `^(L|C)\d+[A-Z]?$`; duplicate marks resolve first-wins.
- Schedule-mark hits get `protected_exact_section` strength → `PROJECT_RULE_RESOLVED`, which is in the takeoff-trusted status set (derived eligibility changes; the resolver never writes the field).
- Plate roles/text never leave `document["schedule_grid"]`.
- The 9 non-LABEL_SUBSTITUTION rule types have no consumer; `project_rule_resolver` is fed `page_role="UNKNOWN"`.

## Test commands and results

Interpreter `backend/venv/Scripts/python.exe`, run from `backend/`.

| Command | Before | After |
|---|---|---|
| Targeted project-rule / legend / schedule / exact-lock suites (8 files) | 204 passed, 1 skipped | — |
| Same 8 files + 2 new files | — | 222 passed, 1 skipped |
| `python -m pytest -q` | 1324 passed, 9 failed, 4 skipped | 1342 passed, 9 failed (same 9), 4 skipped |

The 9 pre-existing failures (8 × `test_a2_a7_human_review`, 1 × `test_repeated_detail_linker`) predate every edit here.

## Benchmark composition

| Set | Documents | Template families | Gold |
|---|---|---|---|
| Synthetic (CI) | 5 docs, 7 pages, 14 gold rows, 8 gold regions (6 rule-bearing + 2 non) | T1 conventional, T2 embedded-in-plan, T3 scanned | Written by me from the plan's case list and from real H5/Ketcham patterns. **Not reviewer-approved; same author as the shadow code → overfit risk.** |
| Real (local only) | 7 PDFs: 1200 K, Burrville, GCDC, H5 Herndon, Ketcham, Sidwell, Springhill | Unknown / not verified (no drafter metadata) | **None.** Unlabelled discovery only. No real-project metric below is an accuracy claim. |

## Synthetic results (baseline = frozen path, shadow = widened evidence)

| Metric | Baseline | Shadow |
|---|---|---|
| Rule-bearing page recall | 0.50 | 0.83 |
| Rule-bearing region recall (95% Wilson) | 0.50 [0.22, 0.78] | 0.88 [0.53, 0.98] |
| Row found | 0.50 | 0.93 |
| Cell relationship accuracy | 0.50 | 1.00 |
| Mark→section precision / recall | 0.67 / 0.50 | 1.00 / 1.00 |
| Correct abstention (incl. conflict→review) | 0.67 | 1.00 |
| Component role / dimension accuracy | 0.50 / 0.67 | 0.93 / 1.00 |
| Quantity-per-assembly accuracy | n/a (no gold quantity; no pipeline emits it) | n/a |
| Provenance completeness | 0.00 | 1.00 |
| Catalog-valid output rate | 1.00 | 1.00 |

Baseline non-passes are all declared: LB-1/LB-2/C-1/C-2 (mark grammar), duplicate `L1` resolved first-wins instead of review. The one shadow region miss is the scanned `VISION_REQUIRED` page (expected, nothing fabricated).

Token cases (production orchestrator, adversarial fusion decoy): 13 pass, 1 known defect, **0 semantic-lock violations**.

## Safety gates

| Gate | Baseline | Shadow |
|---|---|---|
| Exact semantic-lock overrides (token cases) | 0 | n/a (shadow does not touch prediction) |
| Invalid catalog auto-accepts | 0 | 0 |
| Schedule rows marked countable | 0 (not represented) | 0 (`countable_occurrence=false` on every record) |
| Resolved rows missing provenance | 6 | 0 |
| Fabricated rows on vision pages | 0 | 0 |
| Cross-project leaks | 0 | 0 (synthetic and real) |
| Project-rule writes to takeoff/quantity | 0 (static: overlay never writes; shadow is not read) | 0 |
| Legacy L/C regressions | — | 0 (current-mode map equals legacy map; legacy tests green) |

Known defect outside the gates (not fixed, out of scope): `"2 L4X4X1/2"` as one raw string is auto-accepted as `2L4X4X1/2` (`resolve_trusted_explicit_section` whole-string path). Token extraction alone yields `L4X4X1/2`; whether real tokens ever carry the spaced form is unmeasured.

## Real-corpus discovery (unlabelled)

| | Baseline | Shadow |
|---|---|---|
| Schedule rows resolved (7 projects) | **0** | 22 (all H5; 11 unique marks × 2 sheets) |
| Conflicts | 0 | 0 |
| Rows rejected with reason | — | 10 (H5 p.23 `RI-*`/`RE-*`, `host_member_schedule`) |
| Grid time, 7 docs | 153 ms | 151 ms (PDF parse ≈ 27 s total; grid < 1%) |
| Deterministic across 2 runs | yes | yes |

H5 pp. 7–8 `EXISTING COLUMN SCHEDULE`: `C-1…C-11 → W8X24/W8X31/W8X28/W8X35/W8X40/W8X58/W8X48`. All 11 rows match the verbatim PDF text row for row (checked against extracted words), but no steel reviewer has approved them. **These 11 mappings are shadow evidence about existing/renovation conditions. They are not takeoff members, they do not feed any prediction or quantity, and they must not be counted.** Caveats:

- **No consumer.** The `C-n` marks appear ~58 more times on H5 plan pages, but `extract_engineering_tokens` yields **zero** `C-n` tokens, so even a promoted widened map would change nothing downstream.
- **Scope.** These are *existing* `(E)` columns in a renovation — likely not new-steel takeoff.
- **Exposure.** 71 engineering tokens sit inside those schedule regions on non-context pages, i.e. definition text that `context_scope` leaves takeoff-eligible today (upper bound; detail demotion not modelled). Pre-existing behaviour, not changed.

### Failure taxonomy (title-text survey of every page containing "SCHEDULE"; reviewer-unconfirmed)

| Class | Pages | Current | Shadow | Needed mechanism |
|---|---|---|---|---|
| Steel column schedules as level × location matrices (no MARK/SIZE header) | Burrville 28–29, GCDC 77–79, Ketcham 4, Sidwell 43, Springhill 26–27 (≈9) | miss | miss | Matrix parser; the output is **member count by location**, not mark→section |
| Hyphen-mark MARK/SIZE schedule embedded in a plan | H5 7–8 (2) | miss | found | Done in shadow; blocked on token extraction + scope decision |
| Plate / reinforcing component schedules | 1200 K 32 (base plate), Ketcham 10 (bearing plate, multi-row header), H5 23 (reinforcing) | miss | H5 23 correctly rejected; others miss | Multi-row header support + component contract (none exists downstream) |
| L/C bare-mark lintel schedule (the supported case) | **0 pages** | — | — | — |
| Scanned / `VISION_REQUIRED` rule pages | **0 pages** | — | — | — |
| Concrete schedules, drawing indexes, "SEE … SCHEDULE" references | remainder | correct abstain | correct abstain | — |

Estimated steel-schedule page coverage (≈14 candidate pages): baseline 0/14, shadow 3/14. This is an **estimate from title text**, not gold.

## Answers to the four questions

1. **How much does the current engine solve?** On this corpus, nothing: the supported `L1/C1` convention does not occur in 7 real projects. It is correct and safe on its fixtures.
2. **Does it find schedules embedded in drawing pages?** Yes when headers are literally `MARK`+`SIZE` (page role is not a gate); it failed H5 only on the hyphenated mark grammar. The shadow path fixes that case and keeps side-by-side tables apart.
3. **Primary section only, or components too?** Primary section only. Plate roles/text stop at the side artifact; no contract carries component dimensions or quantities.
4. **What justifies deterministic rules vs vision vs LLM?** The measured residual is deterministic-shaped: vector-text column matrices and multi-row plate headers. No vision-required rule page exists in the corpus, and no free-text rule was observed that the tables could not express. **Nothing here justifies a vision or LLM bake-off yet.**

## Remaining unknowns

- No steel-reviewer gold for any real page; synthetic gold shares an author with the code.
- Drafter/template families of the 7 projects are unknown (so no family split was possible).
- Whether `(E)` schedule columns belong in takeoff scope.
- Whether real tokens ever arrive as `"2 L…"` single strings.
- Quantity-per-assembly is unmeasured (no gold, no emitter).

## Recommendation — next single change

Build a **shadow, deterministic column-schedule matrix parser** (level × location grid → section per location, with provenance), measured with this harness against reviewer-approved gold for 3–5 real column schedules (Burrville 28, GCDC 77, Springhill 26 first). It targets the largest real residual (≈9 pages across 5 projects) and feeds member *count*, which prior audits identified as the main takeoff loss. Do **not** promote the widened mark map (no consuming tokens, unresolved `(E)` scope) and do **not** start a vision/LLM bake-off.

## Rollback (preserves unrelated work)

```
git checkout -- backend/config.py backend/services/engineering/schedule_grid.py
rm backend/scripts/evaluate_project_rules.py backend/tests/test_project_rule_benchmark.py \
   backend/tests/test_schedule_evidence_shadow.py
rm -r backend/tests/fixtures/project_rules docs/project_rule_phase1
```

These paths are the only ones this work touched; `backend/training/**`, `docs/deep_research_project_rule_intelligence/` and `docs/validation/` are left alone.
