# Project-rule benchmark — project-rules-synthetic-v1

Harness 1.0 · versions `{"extraction_version": "3.12-schedule-marks", "schedule_grid_enabled": true, "schedule_mark_map_enabled": true, "legend_profile_llm_enabled": false, "schedule_evidence_version": "1.0"}`

| metric | baseline | shadow |
|---|---|---|
| rule_bearing_page_recall | 0.5 | 0.8333 |
| rule_bearing_region_recall | 0.5 | 0.875 |
| rule_bearing_region_recall_ci95 | [0.2152, 0.7848] | [0.5291, 0.9776] |
| gold_rows | 14 | 14 |
| row_found_rate | 0.5 | 0.9286 |
| cell_relationship_accuracy | 0.5 | 1.0 |
| mark_to_section_precision | 0.6667 | 1.0 |
| mark_to_section_recall | 0.5 | 1.0 |
| mark_to_section_recall_ci95 | [0.2152, 0.7848] | [0.6756, 1.0] |
| correct_abstention_rate | 0.6667 | 1.0 |
| component_role_accuracy | 0.5 | 0.9286 |
| component_dimension_accuracy | 0.6667 | 1.0 |
| quantity_per_assembly_accuracy | None | None |
| provenance_completeness | 0.0 | 1.0 |
| catalog_valid_output_rate | 1.0 | 1.0 |
| latency_ms_total | 0.45 | 0.73 |

## Safety gates

| gate | baseline | shadow |
|---|---|---|
| invalid_catalog_auto_accept | 0 | 0 |
| schedule_rows_marked_countable | 0 | 0 |
| resolved_rows_missing_provenance | 6 | 0 |
| fabricated_rows_on_vision_pages | 0 | 0 |
| cross_project_leaks | 0 | 0 |

Token cases: `{"semantic_lock_violations": 0, "wrong_auto_accepts": 1, "outcomes": {"expected_known_defect": 1, "pass": 13}, "latency_ms_total": 664.99}`

## Row outcomes

- **baseline** rows `{'expected_unsupported': 6, 'pass': 8}` regions `{'expected_unsupported': 4, 'pass': 4}`
- **shadow** rows `{'pass': 14}` regions `{'expected_unsupported': 1, 'pass': 7}`

## Non-passing rows

| pipeline | row | expected | predicted | outcome | note |
|---|---|---|---|---|---|
| baseline | B-LB1 | resolved:W8X21 | None | expected_unsupported | case 3: LB-1 is a non-current convention |
| baseline | B-LB2 | resolved:L4X4X1/4 | None | expected_unsupported |  |
| baseline | B-C1 | resolved:W8X24 | None | expected_unsupported | real H5 convention; C-1 is not a channel |
| baseline | B-C2 | resolved:W8X24 | None | expected_unsupported |  |
| baseline | D-L1-p1 | review:None | W8X21 | expected_unsupported | case 14: conflicting duplicate mark; baseline silently keeps first row |
| baseline | D-L1-p2 | review:None | W8X21 | expected_unsupported |  |

## Token cases

| case | text | expect | section | status | review | outcome |
|---|---|---|---|---|---|---|
| T01 | `W10X33` | locked:W10X33 | W10X33 | exact_match | False | pass |
| T02 | `HSS8X4` | not_auto_accepted:None | HSS8X4X1/2 | missing_dimension_field | True | pass |
| T03 | `L4X4X1/4` | locked:L4X4X1/4 | L4X4X1/4 | exact_match | False | pass |
| T04 | `L1` | rule_resolved:W8X21 | W8X21 | project_rule_resolved | False | pass |
| T05 | `L1` | not_auto_accepted:None | L1 | exact_match | True | pass |
| T06 | `ANGLE 4X4X1/4` | not_auto_accepted:None | L4X4X3/8 | corrected_prediction | True | pass |
| T07 | `4X4X1/4 ANGLE` | locked:L4X4X1/4 | L4X4X1/4 | normalized_match | False | pass |
| T08 | `4X4X1/4` | not_auto_accepted:None | L4X4X1/4 | corrected_prediction | True | pass |
| T09 | `CHANNEL` | not_auto_accepted:None | C8X11.5 | corrected_prediction | True | pass |
| T10 | `BENT PLATE 12X4X3/8` | component_not_rolled:None |  | confirmed_annotation | True | pass |
| T11 | `2L4X4X1/2` | locked:2L4X4X1/2 | 2L4X4X1/2 | exact_match | False | pass |
| T12 | `2 L4X4X1/2` | locked:L4X4X1/2 | 2L4X4X1/2 | normalized_match | False | expected_known_defect |
| T13 | `L1` | not_auto_accepted:None | L1 | exact_match | True | pass |
| T14 | `LB-1` | not_auto_accepted:None | W8X21 | corrected_prediction | True | pass |
