# Real-Project Page Profile (Phase 2.5)

Full per-page diagnostics for all 262 pages across the 7 real projects, produced by running the **unmodified production extraction path** (`pdf_parser.extract_document_structure` → `geometry_extractor.extract_geometry` → `graph_builder.build_graph`, all Phase 1 code, default settings) against every page. Raw detail (all fields, including `scale_text_candidates`) lives in the git-ignored `backend/training/ml_association/real_project_pilot/working_notes/page_profile_full.json`; this document is the sanitized, committed summary.

**Page classification is heuristic** (keyword search over each page's extracted text against a fixed category list — see the script referenced in `working_notes/`), explicitly labeled as such. It is a rough sort for pilot-selection purposes, not a validated taxonomy.

## Headline findings (all real data, not synthetic)

1. **The 250-drawing cap triggers on 229/262 pages (87.4%)** of this real corpus — not a rare edge case. Raw per-page drawing counts range up to **53,146** on a single page (median 4,970), so the cap is the *normal* operating condition for these real structural sheets, not an exception.
2. **The 60-object pairwise window triggers on 233/262 pages (89.0%)**. On a typical capped page with the geometry-node count sitting at the retained cap (~250 nodes), the window's own arithmetic means only **642 of the 31,125 possible geometry pairs are ever compared for PARALLEL/PERPENDICULAR/INTERSECTS/CONTAINS/CONNECTED relationships — 2.06% coverage.** This is not an estimate; it is the exact, repeated `candidate_pairs_considered=642` / `candidate_pairs_pruned=30483` figures below, which fall out of the window's fixed `page_geom[:60]` × 12-item-lookahead arithmetic once a page has ≥72 geometry nodes (any capped page does). This sharpens Phase 1's synthetic-fixture estimate (10.8%–19% recall) with a real, worse number for real dense pages.
3. **The 350-node semantic window never triggers (0/262 pages)** — `structural_graph.py`'s larger cap is generous enough relative to real per-page node counts (max observed: 517) that it is not the bottleneck; the 60-object window is.
4. **8,356 steel labels detected across 177/262 pages** (67.6% of pages have at least one) — real content exists in real volume for candidate-generation testing.
5. **248/262 pages (94.7%) contain the literal word "SCALE"**, and 205/262 (78.2%) contain a scale-ratio-shaped text pattern (e.g. `1/4"=1'-0"`) — confirming Phase 1's finding that scale information is present in real drawings but never extracted or propagated (`docs/geometry_graph_audit/09_open_questions.md` Q4) is a real, common gap, not a hypothetical one.
6. **All 262 pages report `rotation=0`** at the PDF-page level — the rotation-handling code path (Phase 1) was not exercised by page-level rotation in this corpus (see `real_project_pilot_results.md` for how the pilot still covers rotation via a synthetic fixture).
7. **Zero extraction failures or exceptions** across all 262 pages — the production extraction pipeline ran to completion on every page of every one of the 7 real PDFs without crashing.

## Page category distribution (heuristic)

| Category | Count |
|---|---|
| structural framing plan | 77 |
| general notes | 64 |
| detail sheet | 38 |
| unknown | 25 |
| member schedule | 23 |
| section or elevation | 17 |
| connection schedule | 9 |
| architectural or non-structural | 6 |
| title or cover | 3 |

("unknown" pages are typically ones with sparse or ambiguous text that didn't match any keyword rule — several are pages where `engineering_token_count=0`, i.e., no steel labels were detected at all, often true blank-ish or purely-graphical pages.)

## Per-page diagnostics (all 262 pages)

Columns: rotation | raw text tokens | detected engineering tokens | detected steel labels (regex-matched subset of engineering tokens) | raw drawing paths | retained drawing paths | zero-area paths | 250-cap triggered | graph node count | graph edge count | 60-object window triggered | candidate pairs considered | candidate pairs pruned | heuristic category.

| project | page | rot | text_tok | eng_tok | steel_lbl | raw_draw | retained | zero_area | cap? | graph_nodes | edges | 60win? | pairs_considered | pairs_pruned | category |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| project_001 | 1 | 0 | 1262 | 1 | 1 | 1734 | 250 | 447 | Y | 251 | 965 | Y | 642 | 30483 | title or cover |
| project_001 | 2 | 0 | 3680 | 4 | 0 | 906 | 250 | 324 | Y | 254 | 2076 | Y | 642 | 30483 | general notes |
| project_001 | 3 | 0 | 2877 | 23 | 0 | 884 | 250 | 307 | Y | 273 | 2376 | Y | 642 | 30483 | general notes |
| project_001 | 4 | 0 | 483 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_001 | 5 | 0 | 516 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_001 | 6 | 0 | 86 | 0 | 0 | None | None | None | N | None | None | N | None | None | general notes |
| project_001 | 7 | 0 | 315 | 0 | 0 | None | None | None | N | None | None | N | None | None | general notes |
| project_001 | 8 | 0 | 313 | 0 | 0 | None | None | None | N | None | None | N | None | None | general notes |
| project_001 | 9 | 0 | 320 | 0 | 0 | None | None | None | N | None | None | N | None | None | general notes |
| project_001 | 10 | 0 | 338 | 4 | 4 | 14594 | 250 | 7363 | Y | 254 | 615 | Y | 642 | 30483 | general notes |
| project_001 | 11 | 0 | 412 | 2 | 1 | 16538 | 250 | 10130 | Y | 252 | 539 | Y | 642 | 30483 | general notes |
| project_001 | 12 | 0 | 435 | 13 | 12 | 16952 | 250 | 10612 | Y | 263 | 2467 | Y | 642 | 30483 | general notes |
| project_001 | 13 | 0 | 290 | 30 | 29 | 14779 | 250 | 9528 | Y | 280 | 1095 | Y | 642 | 30483 | structural framing plan |
| project_001 | 14 | 0 | 330 | 1 | 0 | 11036 | 250 | 7553 | Y | 251 | 722 | Y | 642 | 30483 | general notes |
| project_001 | 15 | 0 | 332 | 1 | 0 | 10043 | 250 | 7076 | Y | 251 | 830 | Y | 642 | 30483 | general notes |
| project_001 | 16 | 0 | 331 | 1 | 0 | 9959 | 250 | 7011 | Y | 251 | 759 | Y | 642 | 30483 | general notes |
| project_001 | 17 | 0 | 315 | 1 | 0 | 9457 | 250 | 6520 | Y | 251 | 750 | Y | 642 | 30483 | general notes |
| project_001 | 18 | 0 | 337 | 1 | 0 | 9519 | 250 | 6575 | Y | 251 | 758 | Y | 642 | 30483 | general notes |
| project_001 | 19 | 0 | 376 | 9 | 8 | 11917 | 250 | 9339 | Y | 259 | 2379 | Y | 642 | 30483 | general notes |
| project_001 | 20 | 0 | 420 | 25 | 20 | 11549 | 250 | 9193 | Y | 275 | 933 | Y | 642 | 30483 | general notes |
| project_001 | 21 | 0 | 652 | 80 | 75 | 18019 | 250 | 13022 | Y | 330 | 4462 | Y | 642 | 30483 | general notes |
| project_001 | 22 | 0 | 1248 | 197 | 195 | 11260 | 250 | 8592 | Y | 447 | 844 | Y | 642 | 30483 | general notes |
| project_001 | 23 | 0 | 467 | 74 | 74 | 7251 | 250 | 5909 | Y | 324 | 806 | Y | 642 | 30483 | general notes |
| project_001 | 24 | 0 | 401 | 73 | 73 | 5738 | 250 | 3677 | Y | 323 | 629 | Y | 642 | 30483 | structural framing plan |
| project_001 | 25 | 0 | 1664 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_001 | 26 | 0 | 999 | 10 | 10 | 14190 | 250 | 2606 | Y | 260 | 257 | Y | 642 | 30483 | detail sheet |
| project_001 | 27 | 0 | 1324 | 0 | 0 | None | None | None | N | None | None | N | None | None | detail sheet |
| project_001 | 28 | 0 | 1237 | 30 | 16 | 13351 | 250 | 3857 | Y | 280 | 652 | Y | 642 | 30483 | unknown |
| project_001 | 29 | 0 | 949 | 1 | 0 | 7415 | 250 | 3142 | Y | 251 | 213 | Y | 642 | 30483 | connection schedule |
| project_001 | 30 | 0 | 997 | 24 | 9 | 5738 | 250 | 2802 | Y | 274 | 970 | Y | 642 | 30483 | architectural or non-structural |
| project_001 | 31 | 0 | 784 | 28 | 16 | 6393 | 250 | 3308 | Y | 278 | 376 | Y | 642 | 30483 | detail sheet |
| project_001 | 32 | 0 | 423 | 0 | 0 | None | None | None | N | None | None | N | None | None | member schedule |
| project_001 | 33 | 0 | 994 | 5 | 5 | 19947 | 250 | 3708 | Y | 255 | 268 | Y | 642 | 30483 | detail sheet |
| project_001 | 34 | 0 | 781 | 0 | 0 | None | None | None | N | None | None | N | None | None | section or elevation |
| project_001 | 35 | 0 | 385 | 0 | 0 | None | None | None | N | None | None | N | None | None | section or elevation |
| project_001 | 36 | 0 | 888 | 12 | 11 | 11584 | 250 | 4826 | Y | 262 | 119 | Y | 642 | 30483 | section or elevation |
| project_001 | 37 | 0 | 625 | 45 | 45 | 10061 | 250 | 4518 | Y | 295 | 539 | Y | 642 | 30483 | section or elevation |
| project_001 | 38 | 0 | 695 | 24 | 24 | 35297 | 250 | 11283 | Y | 274 | 396 | Y | 642 | 30483 | structural framing plan |
| project_001 | 39 | 0 | 532 | 14 | 13 | 7177 | 250 | 2677 | Y | 264 | 495 | Y | 642 | 30483 | detail sheet |
| project_002 | 1 | 0 | 4555 | 17 | 0 | 464 | 250 | 302 | Y | 267 | 1212 | Y | 642 | 30483 | general notes |
| project_002 | 2 | 0 | 3308 | 7 | 6 | 1546 | 250 | 568 | Y | 257 | 540 | Y | 642 | 30483 | general notes |
| project_002 | 3 | 0 | 1680 | 2 | 0 | 1398 | 250 | 1256 | Y | 252 | 280 | Y | 642 | 30483 | general notes |
| project_002 | 4 | 0 | 1019 | 20 | 0 | 4353 | 250 | 1787 | Y | 270 | 728 | Y | 642 | 30483 | member schedule |
| project_002 | 5 | 0 | 442 | 11 | 0 | 3267 | 250 | 238 | Y | 261 | 1488 | Y | 642 | 30483 | structural framing plan |
| project_002 | 6 | 0 | 434 | 19 | 0 | 2888 | 250 | 80 | Y | 269 | 599 | Y | 642 | 30483 | structural framing plan |
| project_002 | 7 | 0 | 1091 | 162 | 154 | 2400 | 250 | 1066 | Y | 412 | 991 | Y | 642 | 30483 | general notes |
| project_002 | 8 | 0 | 779 | 98 | 81 | 3586 | 250 | 207 | Y | 348 | 1073 | Y | 642 | 30483 | structural framing plan |
| project_002 | 9 | 0 | 671 | 101 | 89 | 1576 | 250 | 56 | Y | 351 | 973 | Y | 642 | 30483 | structural framing plan |
| project_002 | 10 | 0 | 764 | 160 | 140 | 3037 | 250 | 1358 | Y | 410 | 1088 | Y | 642 | 30483 | structural framing plan |
| project_002 | 11 | 0 | 597 | 130 | 123 | 2423 | 250 | 163 | Y | 380 | 1055 | Y | 642 | 30483 | structural framing plan |
| project_002 | 12 | 0 | 495 | 93 | 77 | 1817 | 250 | 63 | Y | 343 | 1368 | Y | 642 | 30483 | structural framing plan |
| project_002 | 13 | 0 | 538 | 58 | 43 | 1919 | 250 | 66 | Y | 308 | 1456 | Y | 642 | 30483 | structural framing plan |
| project_002 | 14 | 0 | 1300 | 1 | 0 | 9770 | 250 | 2586 | Y | 251 | 597 | Y | 642 | 30483 | general notes |
| project_002 | 15 | 0 | 1222 | 4 | 0 | 11561 | 250 | 3440 | Y | 254 | 405 | Y | 642 | 30483 | member schedule |
| project_002 | 16 | 0 | 1619 | 25 | 19 | 5890 | 250 | 2846 | Y | 275 | 736 | Y | 642 | 30483 | structural framing plan |
| project_002 | 17 | 0 | 1149 | 13 | 6 | 10876 | 250 | 4661 | Y | 263 | 377 | Y | 642 | 30483 | general notes |
| project_002 | 18 | 0 | 886 | 36 | 23 | 5300 | 250 | 2317 | Y | 286 | 488 | Y | 642 | 30483 | member schedule |
| project_002 | 19 | 0 | 1021 | 12 | 4 | 3303 | 250 | 1432 | Y | 262 | 629 | Y | 642 | 30483 | detail sheet |
| project_002 | 20 | 0 | 1436 | 27 | 20 | 14950 | 250 | 8729 | Y | 277 | 619 | Y | 642 | 30483 | detail sheet |
| project_002 | 21 | 0 | 1050 | 1 | 0 | 4920 | 250 | 1447 | Y | 251 | 511 | Y | 642 | 30483 | detail sheet |
| project_002 | 22 | 0 | 754 | 12 | 0 | 22620 | 250 | 7375 | Y | 262 | 301 | Y | 642 | 30483 | detail sheet |
| project_002 | 23 | 0 | 450 | 11 | 1 | 4970 | 250 | 2061 | Y | 261 | 329 | Y | 642 | 30483 | detail sheet |
| project_002 | 24 | 0 | 614 | 36 | 21 | 4749 | 250 | 2191 | Y | 286 | 568 | Y | 642 | 30483 | general notes |
| project_002 | 25 | 0 | 311 | 9 | 5 | 2531 | 250 | 1361 | Y | 259 | 1579 | Y | 642 | 30483 | section or elevation |
| project_002 | 26 | 0 | 481 | 33 | 25 | 3255 | 250 | 2422 | Y | 283 | 303 | Y | 642 | 30483 | section or elevation |
| project_002 | 27 | 0 | 524 | 37 | 27 | 3182 | 250 | 2313 | Y | 287 | 265 | Y | 642 | 30483 | section or elevation |
| project_002 | 28 | 0 | 629 | 62 | 61 | 1923 | 250 | 1751 | Y | 312 | 414 | Y | 642 | 30483 | member schedule |
| project_002 | 29 | 0 | 584 | 55 | 54 | 1563 | 250 | 1409 | Y | 305 | 460 | Y | 642 | 30483 | member schedule |
| project_003 | 1 | 0 | 1140 | 0 | 0 | None | None | None | N | None | None | N | None | None | title or cover |
| project_003 | 2 | 0 | 80 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_003 | 3 | 0 | 3114 | 23 | 0 | 850 | 250 | 174 | Y | 273 | 1424 | Y | 642 | 30483 | general notes |
| project_003 | 4 | 0 | 4986 | 4 | 0 | 772 | 250 | 98 | Y | 254 | 1436 | Y | 642 | 30483 | general notes |
| project_003 | 5 | 0 | 3296 | 19 | 12 | 1541 | 250 | 281 | Y | 269 | 685 | Y | 642 | 30483 | general notes |
| project_003 | 6 | 0 | 162 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_003 | 7 | 0 | 162 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_003 | 8 | 0 | 202 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_003 | 9 | 0 | 424 | 5 | 5 | 4655 | 250 | 3459 | Y | 255 | 227 | Y | 642 | 30483 | structural framing plan |
| project_003 | 10 | 0 | 431 | 19 | 4 | 5234 | 250 | 4024 | Y | 269 | 290 | Y | 642 | 30483 | structural framing plan |
| project_003 | 11 | 0 | 398 | 16 | 0 | 5225 | 250 | 4065 | Y | 266 | 200 | Y | 642 | 30483 | structural framing plan |
| project_003 | 12 | 0 | 523 | 17 | 3 | 7509 | 250 | 6004 | Y | 267 | 232 | Y | 642 | 30483 | structural framing plan |
| project_003 | 13 | 0 | 545 | 21 | 5 | 6567 | 250 | 5149 | Y | 271 | 244 | Y | 642 | 30483 | structural framing plan |
| project_003 | 14 | 0 | 483 | 19 | 0 | 5778 | 250 | 4546 | Y | 269 | 220 | Y | 642 | 30483 | structural framing plan |
| project_003 | 15 | 0 | 524 | 24 | 5 | 5984 | 250 | 4655 | Y | 274 | 255 | Y | 642 | 30483 | structural framing plan |
| project_003 | 16 | 0 | 508 | 12 | 12 | 5629 | 250 | 3990 | Y | 262 | 211 | Y | 642 | 30483 | structural framing plan |
| project_003 | 17 | 0 | 562 | 135 | 135 | 3451 | 250 | 2346 | Y | 385 | 454 | Y | 642 | 30483 | unknown |
| project_003 | 18 | 0 | 565 | 38 | 22 | 6189 | 250 | 4694 | Y | 288 | 300 | Y | 642 | 30483 | structural framing plan |
| project_003 | 19 | 0 | 589 | 148 | 148 | 3664 | 250 | 2525 | Y | 398 | 481 | Y | 642 | 30483 | unknown |
| project_003 | 20 | 0 | 526 | 29 | 12 | 6394 | 250 | 4923 | Y | 279 | 290 | Y | 642 | 30483 | structural framing plan |
| project_003 | 21 | 0 | 611 | 160 | 160 | 4016 | 250 | 2853 | Y | 410 | 576 | Y | 642 | 30483 | unknown |
| project_003 | 22 | 0 | 585 | 40 | 22 | 7088 | 250 | 5578 | Y | 290 | 329 | Y | 642 | 30483 | structural framing plan |
| project_003 | 23 | 0 | 559 | 141 | 141 | 3499 | 250 | 2399 | Y | 391 | 513 | Y | 642 | 30483 | unknown |
| project_003 | 24 | 0 | 547 | 38 | 21 | 6198 | 250 | 4758 | Y | 288 | 331 | Y | 642 | 30483 | structural framing plan |
| project_003 | 25 | 0 | 569 | 147 | 147 | 3601 | 250 | 2485 | Y | 397 | 468 | Y | 642 | 30483 | unknown |
| project_003 | 26 | 0 | 531 | 27 | 11 | 6258 | 250 | 4841 | Y | 277 | 218 | Y | 642 | 30483 | structural framing plan |
| project_003 | 27 | 0 | 564 | 131 | 131 | 3623 | 250 | 2519 | Y | 381 | 435 | Y | 642 | 30483 | unknown |
| project_003 | 28 | 0 | 574 | 33 | 17 | 6483 | 250 | 4994 | Y | 283 | 310 | Y | 642 | 30483 | structural framing plan |
| project_003 | 29 | 0 | 204 | 0 | 0 | None | None | None | N | None | None | N | None | None | structural framing plan |
| project_003 | 30 | 0 | 710 | 111 | 109 | 3429 | 250 | 1848 | Y | 361 | 501 | Y | 642 | 30483 | structural framing plan |
| project_003 | 31 | 0 | 640 | 69 | 69 | 2975 | 250 | 1639 | Y | 319 | 387 | Y | 642 | 30483 | structural framing plan |
| project_003 | 32 | 0 | 589 | 53 | 53 | 3139 | 250 | 1883 | Y | 303 | 333 | Y | 642 | 30483 | structural framing plan |
| project_003 | 33 | 0 | 745 | 104 | 103 | 4484 | 250 | 2631 | Y | 354 | 416 | Y | 642 | 30483 | structural framing plan |
| project_003 | 34 | 0 | 564 | 71 | 71 | 2662 | 250 | 1400 | Y | 321 | 359 | Y | 642 | 30483 | structural framing plan |
| project_003 | 35 | 0 | 565 | 69 | 69 | 2759 | 250 | 1578 | Y | 319 | 347 | Y | 642 | 30483 | structural framing plan |
| project_003 | 36 | 0 | 590 | 69 | 69 | 2796 | 250 | 1445 | Y | 319 | 381 | Y | 642 | 30483 | structural framing plan |
| project_003 | 37 | 0 | 626 | 115 | 115 | 2443 | 250 | 1161 | Y | 365 | 471 | Y | 642 | 30483 | structural framing plan |
| project_003 | 38 | 0 | 203 | 0 | 0 | None | None | None | N | None | None | N | None | None | structural framing plan |
| project_003 | 39 | 0 | 642 | 118 | 118 | 3167 | 250 | 1807 | Y | 368 | 433 | Y | 642 | 30483 | structural framing plan |
| project_003 | 40 | 0 | 669 | 74 | 74 | 3405 | 250 | 1996 | Y | 324 | 384 | Y | 642 | 30483 | structural framing plan |
| project_003 | 41 | 0 | 633 | 60 | 60 | 3353 | 250 | 1992 | Y | 310 | 345 | Y | 642 | 30483 | structural framing plan |
| project_003 | 42 | 0 | 664 | 84 | 80 | 3429 | 250 | 1887 | Y | 334 | 368 | Y | 642 | 30483 | structural framing plan |
| project_003 | 43 | 0 | 566 | 57 | 57 | 3025 | 250 | 1732 | Y | 307 | 364 | Y | 642 | 30483 | structural framing plan |
| project_003 | 44 | 0 | 537 | 38 | 38 | 3016 | 250 | 1783 | Y | 288 | 336 | Y | 642 | 30483 | structural framing plan |
| project_003 | 45 | 0 | 544 | 47 | 47 | 2870 | 250 | 1611 | Y | 297 | 345 | Y | 642 | 30483 | structural framing plan |
| project_003 | 46 | 0 | 585 | 89 | 89 | 2448 | 250 | 1292 | Y | 339 | 435 | Y | 642 | 30483 | structural framing plan |
| project_003 | 47 | 0 | 200 | 0 | 0 | None | None | None | N | None | None | N | None | None | architectural or non-structural |
| project_003 | 48 | 0 | 410 | 41 | 41 | 1496 | 250 | 1157 | Y | 291 | 476 | Y | 642 | 30483 | structural framing plan |
| project_003 | 49 | 0 | 512 | 47 | 47 | 4662 | 250 | 3377 | Y | 297 | 404 | Y | 642 | 30483 | structural framing plan |
| project_003 | 50 | 0 | 496 | 40 | 40 | 4502 | 250 | 3257 | Y | 290 | 386 | Y | 642 | 30483 | structural framing plan |
| project_003 | 51 | 0 | 703 | 108 | 106 | 4719 | 250 | 3017 | Y | 358 | 469 | Y | 642 | 30483 | structural framing plan |
| project_003 | 52 | 0 | 488 | 60 | 60 | 1937 | 250 | 1470 | Y | 310 | 416 | Y | 642 | 30483 | structural framing plan |
| project_003 | 53 | 0 | 516 | 67 | 67 | 2661 | 250 | 1494 | Y | 317 | 423 | Y | 642 | 30483 | structural framing plan |
| project_003 | 54 | 0 | 515 | 72 | 72 | 2697 | 250 | 1501 | Y | 322 | 424 | Y | 642 | 30483 | structural framing plan |
| project_003 | 55 | 0 | 351 | 39 | 39 | 1602 | 250 | 666 | Y | 289 | 647 | Y | 642 | 30483 | structural framing plan |
| project_003 | 56 | 0 | 762 | 8 | 0 | 5938 | 250 | 2337 | Y | 258 | 471 | Y | 642 | 30483 | detail sheet |
| project_003 | 57 | 0 | 663 | 12 | 6 | 7641 | 250 | 4731 | Y | 262 | 372 | Y | 642 | 30483 | detail sheet |
| project_003 | 58 | 0 | 1100 | 10 | 8 | 14096 | 250 | 9910 | Y | 260 | 469 | Y | 642 | 30483 | general notes |
| project_003 | 59 | 0 | 901 | 15 | 8 | 11400 | 250 | 7889 | Y | 265 | 404 | Y | 642 | 30483 | detail sheet |
| project_003 | 60 | 0 | 976 | 7 | 6 | 5250 | 250 | 3014 | Y | 257 | 408 | Y | 642 | 30483 | detail sheet |
| project_003 | 61 | 0 | 1064 | 23 | 18 | 5609 | 250 | 3016 | Y | 273 | 527 | Y | 642 | 30483 | structural framing plan |
| project_003 | 62 | 0 | 823 | 3 | 2 | 19590 | 250 | 11764 | Y | 253 | 348 | Y | 642 | 30483 | connection schedule |
| project_003 | 63 | 0 | 1096 | 9 | 9 | 3853 | 250 | 1893 | Y | 259 | 438 | Y | 642 | 30483 | general notes |
| project_003 | 64 | 0 | 1426 | 29 | 15 | 6578 | 250 | 3621 | Y | 279 | 905 | Y | 642 | 30483 | structural framing plan |
| project_003 | 65 | 0 | 420 | 16 | 16 | 6386 | 250 | 3594 | Y | 266 | 365 | Y | 642 | 30483 | structural framing plan |
| project_003 | 66 | 0 | 275 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_003 | 67 | 0 | 275 | 0 | 0 | None | None | None | N | None | None | N | None | None | unknown |
| project_003 | 68 | 0 | 290 | 2 | 1 | 8733 | 250 | 4243 | Y | 252 | 328 | Y | 642 | 30483 | unknown |
| project_003 | 69 | 0 | 400 | 8 | 1 | 11978 | 250 | 5705 | Y | 258 | 186 | Y | 642 | 30483 | unknown |
| project_003 | 70 | 0 | 413 | 8 | 8 | 18568 | 250 | 7355 | Y | 258 | 33 | Y | 642 | 30483 | unknown |
| project_003 | 71 | 0 | 318 | 2 | 0 | 5773 | 250 | 2564 | Y | 252 | 241 | Y | 642 | 30483 | section or elevation |
| project_003 | 72 | 0 | 419 | 7 | 6 | 4984 | 250 | 2888 | Y | 257 | 558 | Y | 642 | 30483 | unknown |
| project_003 | 73 | 0 | 400 | 5 | 5 | 5941 | 250 | 3789 | Y | 255 | 288 | Y | 642 | 30483 | unknown |
| project_003 | 74 | 0 | 303 | 14 | 10 | 6852 | 250 | 4516 | Y | 264 | 327 | Y | 642 | 30483 | unknown |
| project_003 | 75 | 0 | 493 | 16 | 16 | 5340 | 250 | 2978 | Y | 266 | 411 | Y | 642 | 30483 | unknown |
| project_003 | 76 | 0 | 477 | 21 | 16 | 7197 | 250 | 4088 | Y | 271 | 398 | Y | 642 | 30483 | structural framing plan |
| project_003 | 77 | 0 | 898 | 207 | 153 | 1398 | 250 | 359 | Y | 457 | 546 | Y | 642 | 30483 | member schedule |
| project_003 | 78 | 0 | 696 | 203 | 151 | 1139 | 250 | 315 | Y | 453 | 629 | Y | 642 | 30483 | member schedule |
| project_003 | 79 | 0 | 690 | 176 | 129 | 1115 | 250 | 297 | Y | 426 | 553 | Y | 642 | 30483 | member schedule |
| project_003 | 80 | 0 | 495 | 107 | 101 | 3178 | 250 | 2033 | Y | 357 | 365 | Y | 642 | 30483 | section or elevation |
| project_003 | 81 | 0 | 370 | 21 | 19 | 7352 | 250 | 5402 | Y | 271 | 445 | Y | 642 | 30483 | section or elevation |
| project_004 | 1 | 0 | 4965 | 24 | 0 | 141 | 141 | 138 | N | 165 | 802 | Y | 642 | 9228 | general notes |
| project_004 | 2 | 0 | 1529 | 4 | 0 | 101 | 101 | 98 | N | 105 | 814 | Y | 642 | 4408 | general notes |
| project_004 | 3 | 0 | 2125 | 16 | 7 | 5381 | 250 | 2491 | Y | 266 | 621 | Y | 642 | 30483 | connection schedule |
| project_004 | 4 | 0 | 118 | 4 | 0 | 84 | 84 | 81 | N | 88 | 954 | Y | 642 | 2844 | general notes |
| project_004 | 5 | 0 | 353 | 4 | 0 | 29703 | 250 | 20345 | Y | 254 | 318 | Y | 642 | 30483 | unknown |
| project_004 | 6 | 0 | 351 | 4 | 0 | 53146 | 250 | 38233 | Y | 254 | 996 | Y | 642 | 30483 | unknown |
| project_004 | 7 | 0 | 911 | 46 | 32 | 6890 | 250 | 5270 | Y | 296 | 562 | Y | 642 | 30483 | member schedule |
| project_004 | 8 | 0 | 1461 | 267 | 243 | 41501 | 250 | 33844 | Y | 517 | 1244 | Y | 642 | 30483 | member schedule |
| project_004 | 9 | 0 | 662 | 58 | 50 | 12641 | 250 | 9854 | Y | 308 | 1205 | Y | 642 | 30483 | section or elevation |
| project_004 | 10 | 0 | 1065 | 205 | 189 | 8211 | 250 | 5231 | Y | 455 | 491 | Y | 642 | 30483 | structural framing plan |
| project_004 | 11 | 0 | 1368 | 128 | 112 | 18348 | 250 | 14873 | Y | 378 | 2434 | Y | 642 | 30483 | general notes |
| project_004 | 12 | 0 | 974 | 263 | 247 | 29676 | 250 | 15530 | Y | 513 | 1120 | Y | 642 | 30483 | connection schedule |
| project_004 | 13 | 0 | 155 | 8 | 1 | 1735 | 250 | 1415 | Y | 258 | 965 | Y | 642 | 30483 | section or elevation |
| project_004 | 14 | 0 | 717 | 9 | 0 | 9907 | 250 | 4368 | Y | 259 | 693 | Y | 642 | 30483 | structural framing plan |
| project_004 | 15 | 0 | 573 | 5 | 0 | 8293 | 250 | 3946 | Y | 255 | 1255 | Y | 642 | 30483 | member schedule |
| project_004 | 16 | 0 | 361 | 6 | 0 | 6346 | 250 | 2381 | Y | 256 | 1040 | Y | 642 | 30483 | detail sheet |
| project_004 | 17 | 0 | 592 | 20 | 12 | 2445 | 250 | 1363 | Y | 270 | 695 | Y | 642 | 30483 | connection schedule |
| project_004 | 18 | 0 | 656 | 16 | 0 | 8365 | 250 | 4681 | Y | 266 | 746 | Y | 642 | 30483 | detail sheet |
| project_004 | 19 | 0 | 585 | 102 | 68 | 11501 | 250 | 5959 | Y | 352 | 1386 | Y | 642 | 30483 | detail sheet |
| project_004 | 20 | 0 | 302 | 36 | 21 | 4219 | 250 | 2445 | Y | 286 | 998 | Y | 642 | 30483 | detail sheet |
| project_004 | 21 | 0 | 679 | 7 | 0 | 5987 | 250 | 2712 | Y | 257 | 322 | Y | 642 | 30483 | connection schedule |
| project_004 | 22 | 0 | 2271 | 18 | 8 | 6621 | 250 | 2514 | Y | 268 | 576 | Y | 642 | 30483 | member schedule |
| project_004 | 23 | 0 | 531 | 36 | 13 | 7798 | 250 | 3607 | Y | 286 | 1081 | Y | 642 | 30483 | detail sheet |
| project_005 | 1 | 0 | 8477 | 50 | 14 | 157 | 157 | 83 | N | 207 | 222 | Y | 642 | 11604 | general notes |
| project_005 | 2 | 0 | 958 | 0 | 0 | None | None | None | N | None | None | N | None | None | general notes |
| project_005 | 3 | 0 | 1331 | 3 | 1 | 17869 | 250 | 3271 | Y | 253 | 275 | Y | 642 | 30483 | structural framing plan |
| project_005 | 4 | 0 | 889 | 6 | 6 | 15602 | 250 | 2455 | Y | 256 | 473 | Y | 642 | 30483 | member schedule |
| project_005 | 5 | 0 | 997 | 7 | 5 | 4835 | 250 | 1809 | Y | 257 | 749 | Y | 642 | 30483 | general notes |
| project_005 | 6 | 0 | 1424 | 13 | 13 | 6782 | 250 | 2252 | Y | 263 | 240 | Y | 642 | 30483 | connection schedule |
| project_005 | 7 | 0 | 1355 | 32 | 32 | 8104 | 250 | 4242 | Y | 282 | 397 | Y | 642 | 30483 | connection schedule |
| project_005 | 8 | 0 | 1018 | 16 | 15 | 3996 | 250 | 1845 | Y | 266 | 486 | Y | 642 | 30483 | detail sheet |
| project_005 | 9 | 0 | 548 | 8 | 5 | 7365 | 250 | 3096 | Y | 258 | 410 | Y | 642 | 30483 | detail sheet |
| project_005 | 10 | 0 | 1246 | 24 | 24 | 8133 | 250 | 5202 | Y | 274 | 1463 | Y | 642 | 30483 | detail sheet |
| project_005 | 11 | 0 | 352 | 0 | 0 | None | None | None | N | None | None | N | None | None | general notes |
| project_005 | 12 | 0 | 925 | 9 | 9 | 19834 | 250 | 18446 | Y | 259 | 415 | Y | 642 | 30483 | general notes |
| project_005 | 13 | 0 | 750 | 193 | 193 | 9820 | 250 | 8758 | Y | 443 | 380 | Y | 642 | 30483 | general notes |
| project_005 | 14 | 0 | 412 | 186 | 186 | 9140 | 250 | 8211 | Y | 436 | 352 | Y | 642 | 30483 | structural framing plan |
| project_005 | 15 | 0 | 358 | 89 | 89 | 6068 | 250 | 5777 | Y | 339 | 344 | Y | 642 | 30483 | structural framing plan |
| project_005 | 16 | 0 | 346 | 3 | 0 | 7047 | 250 | 2359 | Y | 253 | 286 | Y | 642 | 30483 | detail sheet |
| project_005 | 17 | 0 | 399 | 0 | 0 | None | None | None | N | None | None | N | None | None | detail sheet |
| project_006 | 1 | 0 | 2709 | 39 | 0 | 3299 | 250 | 2846 | Y | 289 | 1153 | Y | 642 | 30483 | title or cover |
| project_006 | 2 | 0 | 493 | 0 | 0 | None | None | None | N | None | None | N | None | None | structural framing plan |
| project_006 | 3 | 0 | 518 | 0 | 0 | None | None | None | N | None | None | N | None | None | section or elevation |
| project_006 | 4 | 0 | 394 | 0 | 0 | None | None | None | N | None | None | N | None | None | architectural or non-structural |
| project_006 | 5 | 0 | 419 | 0 | 0 | None | None | None | N | None | None | N | None | None | architectural or non-structural |
| project_006 | 6 | 0 | 382 | 0 | 0 | None | None | None | N | None | None | N | None | None | structural framing plan |
| project_006 | 7 | 0 | 4655 | 17 | 0 | 1376 | 250 | 849 | Y | 267 | 1097 | Y | 642 | 30483 | general notes |
| project_006 | 8 | 0 | 3652 | 6 | 5 | 2533 | 250 | 1165 | Y | 256 | 545 | Y | 642 | 30483 | general notes |
| project_006 | 9 | 0 | 1755 | 2 | 0 | 2493 | 250 | 1897 | Y | 252 | 285 | Y | 642 | 30483 | general notes |
| project_006 | 10 | 0 | 505 | 1 | 0 | 1625 | 250 | 988 | Y | 251 | 817 | Y | 642 | 30483 | architectural or non-structural |
| project_006 | 11 | 0 | 464 | 2 | 0 | 1654 | 250 | 1003 | Y | 252 | 962 | Y | 642 | 30483 | general notes |
| project_006 | 12 | 0 | 815 | 24 | 4 | 5070 | 250 | 3854 | Y | 274 | 435 | Y | 642 | 30483 | member schedule |
| project_006 | 13 | 0 | 1247 | 27 | 1 | 6457 | 250 | 4697 | Y | 277 | 540 | Y | 642 | 30483 | member schedule |
| project_006 | 14 | 0 | 720 | 18 | 0 | 7509 | 250 | 2381 | Y | 268 | 822 | Y | 642 | 30483 | structural framing plan |
| project_006 | 15 | 0 | 825 | 73 | 44 | 4273 | 250 | 3047 | Y | 323 | 854 | Y | 642 | 30483 | general notes |
| project_006 | 16 | 0 | 901 | 179 | 145 | 4808 | 250 | 3224 | Y | 429 | 802 | Y | 642 | 30483 | structural framing plan |
| project_006 | 17 | 0 | 765 | 63 | 46 | 13315 | 250 | 3173 | Y | 313 | 924 | Y | 642 | 30483 | structural framing plan |
| project_006 | 18 | 0 | 615 | 5 | 0 | 5049 | 250 | 715 | Y | 255 | 520 | Y | 642 | 30483 | structural framing plan |
| project_006 | 19 | 0 | 600 | 40 | 24 | 3676 | 250 | 2774 | Y | 290 | 642 | Y | 642 | 30483 | general notes |
| project_006 | 20 | 0 | 550 | 65 | 52 | 3337 | 250 | 2298 | Y | 315 | 757 | Y | 642 | 30483 | structural framing plan |
| project_006 | 21 | 0 | 625 | 50 | 37 | 3856 | 250 | 2968 | Y | 300 | 725 | Y | 642 | 30483 | structural framing plan |
| project_006 | 22 | 0 | 1044 | 190 | 164 | 5365 | 250 | 3770 | Y | 440 | 757 | Y | 642 | 30483 | structural framing plan |
| project_006 | 23 | 0 | 1356 | 1 | 0 | 9735 | 250 | 2904 | Y | 251 | 350 | Y | 642 | 30483 | general notes |
| project_006 | 24 | 0 | 1024 | 5 | 0 | 10103 | 250 | 3657 | Y | 255 | 410 | Y | 642 | 30483 | member schedule |
| project_006 | 25 | 0 | 1636 | 25 | 19 | 7524 | 250 | 3776 | Y | 275 | 705 | Y | 642 | 30483 | structural framing plan |
| project_006 | 26 | 0 | 1188 | 35 | 19 | 12001 | 250 | 5355 | Y | 285 | 390 | Y | 642 | 30483 | general notes |
| project_006 | 27 | 0 | 1115 | 16 | 7 | 5553 | 250 | 2509 | Y | 266 | 671 | Y | 642 | 30483 | detail sheet |
| project_006 | 28 | 0 | 1143 | 20 | 15 | 12513 | 250 | 6853 | Y | 270 | 454 | Y | 642 | 30483 | general notes |
| project_006 | 29 | 0 | 1666 | 1 | 0 | 9402 | 250 | 3165 | Y | 251 | 234 | Y | 642 | 30483 | structural framing plan |
| project_006 | 30 | 0 | 1106 | 1 | 0 | 7251 | 250 | 2677 | Y | 251 | 1374 | Y | 642 | 30483 | member schedule |
| project_006 | 31 | 0 | 707 | 10 | 4 | 7897 | 250 | 2845 | Y | 260 | 449 | Y | 642 | 30483 | structural framing plan |
| project_006 | 32 | 0 | 873 | 20 | 4 | 21216 | 250 | 10276 | Y | 270 | 400 | Y | 642 | 30483 | detail sheet |
| project_006 | 33 | 0 | 388 | 5 | 0 | 5787 | 250 | 2766 | Y | 255 | 841 | Y | 642 | 30483 | detail sheet |
| project_006 | 34 | 0 | 877 | 31 | 5 | 8908 | 250 | 4455 | Y | 281 | 434 | Y | 642 | 30483 | section or elevation |
| project_006 | 35 | 0 | 1024 | 38 | 11 | 16289 | 250 | 8162 | Y | 288 | 595 | Y | 642 | 30483 | general notes |
| project_006 | 36 | 0 | 899 | 21 | 0 | 21931 | 250 | 9244 | Y | 271 | 415 | Y | 642 | 30483 | general notes |
| project_006 | 37 | 0 | 637 | 15 | 1 | 8074 | 250 | 4301 | Y | 265 | 522 | Y | 642 | 30483 | general notes |
| project_006 | 38 | 0 | 405 | 12 | 3 | 3063 | 250 | 1525 | Y | 262 | 445 | Y | 642 | 30483 | section or elevation |
| project_006 | 39 | 0 | 408 | 33 | 27 | 8490 | 250 | 4748 | Y | 283 | 1160 | Y | 642 | 30483 | detail sheet |
| project_006 | 40 | 0 | 344 | 15 | 10 | 2764 | 250 | 1779 | Y | 265 | 627 | Y | 642 | 30483 | detail sheet |
| project_006 | 41 | 0 | 396 | 31 | 25 | 3807 | 250 | 2836 | Y | 281 | 446 | Y | 642 | 30483 | section or elevation |
| project_006 | 42 | 0 | 343 | 1 | 0 | 2070 | 250 | 926 | Y | 251 | 1120 | Y | 642 | 30483 | detail sheet |
| project_006 | 43 | 0 | 799 | 83 | 82 | 3465 | 250 | 2755 | Y | 333 | 1017 | Y | 642 | 30483 | member schedule |
| project_006 | 44 | 0 | 507 | 1 | 0 | 4373 | 250 | 3078 | Y | 251 | 1253 | Y | 642 | 30483 | detail sheet |
| project_006 | 45 | 0 | 1096 | 31 | 8 | 18817 | 250 | 6362 | Y | 281 | 534 | Y | 642 | 30483 | member schedule |
| project_007 | 1 | 0 | 4613 | 36 | 1 | 963 | 250 | 536 | Y | 286 | 1276 | Y | 642 | 30483 | general notes |
| project_007 | 2 | 0 | 3178 | 5 | 4 | 1970 | 250 | 775 | Y | 255 | 545 | Y | 642 | 30483 | general notes |
| project_007 | 3 | 0 | 772 | 1 | 0 | 1377 | 250 | 799 | Y | 251 | 181 | Y | 642 | 30483 | architectural or non-structural |
| project_007 | 4 | 0 | 1653 | 2 | 0 | 1707 | 250 | 1323 | Y | 252 | 271 | Y | 642 | 30483 | general notes |
| project_007 | 5 | 0 | 1756 | 41 | 4 | 8723 | 250 | 5199 | Y | 291 | 624 | Y | 642 | 30483 | member schedule |
| project_007 | 6 | 0 | 858 | 29 | 0 | 6163 | 250 | 3694 | Y | 279 | 693 | Y | 642 | 30483 | structural framing plan |
| project_007 | 7 | 0 | 1646 | 257 | 210 | 5229 | 250 | 3132 | Y | 507 | 4484 | Y | 642 | 30483 | general notes |
| project_007 | 8 | 0 | 1177 | 182 | 142 | 4319 | 250 | 2469 | Y | 432 | 979 | Y | 642 | 30483 | general notes |
| project_007 | 9 | 0 | 1172 | 201 | 166 | 4145 | 250 | 2697 | Y | 451 | 672 | Y | 642 | 30483 | structural framing plan |
| project_007 | 10 | 0 | 1230 | 227 | 187 | 4505 | 250 | 2838 | Y | 477 | 1068 | Y | 642 | 30483 | structural framing plan |
| project_007 | 11 | 0 | 1261 | 1 | 0 | 10390 | 250 | 2699 | Y | 251 | 667 | Y | 642 | 30483 | general notes |
| project_007 | 12 | 0 | 1889 | 5 | 0 | 11079 | 250 | 3517 | Y | 255 | 236 | Y | 642 | 30483 | detail sheet |
| project_007 | 13 | 0 | 1686 | 27 | 23 | 4673 | 250 | 2251 | Y | 277 | 593 | Y | 642 | 30483 | detail sheet |
| project_007 | 14 | 0 | 1080 | 2 | 0 | 7380 | 250 | 3402 | Y | 252 | 281 | Y | 642 | 30483 | general notes |
| project_007 | 15 | 0 | 1178 | 17 | 7 | 6713 | 250 | 3379 | Y | 267 | 688 | Y | 642 | 30483 | structural framing plan |
| project_007 | 16 | 0 | 1465 | 31 | 27 | 12659 | 250 | 6440 | Y | 281 | 433 | Y | 642 | 30483 | connection schedule |
| project_007 | 17 | 0 | 1200 | 26 | 1 | 18809 | 250 | 7820 | Y | 276 | 306 | Y | 642 | 30483 | general notes |
| project_007 | 18 | 0 | 1150 | 30 | 9 | 12960 | 250 | 6681 | Y | 280 | 606 | Y | 642 | 30483 | section or elevation |
| project_007 | 19 | 0 | 1018 | 40 | 13 | 9637 | 250 | 4895 | Y | 290 | 415 | Y | 642 | 30483 | detail sheet |
| project_007 | 20 | 0 | 1051 | 23 | 7 | 9859 | 250 | 5217 | Y | 273 | 453 | Y | 642 | 30483 | general notes |
| project_007 | 21 | 0 | 829 | 17 | 3 | 6650 | 250 | 2958 | Y | 267 | 629 | Y | 642 | 30483 | detail sheet |
| project_007 | 22 | 0 | 625 | 11 | 4 | 9623 | 250 | 8156 | Y | 261 | 179 | Y | 642 | 30483 | detail sheet |
| project_007 | 23 | 0 | 673 | 31 | 22 | 3742 | 250 | 2421 | Y | 281 | 147 | Y | 642 | 30483 | detail sheet |
| project_007 | 24 | 0 | 557 | 20 | 14 | 3114 | 250 | 2096 | Y | 270 | 173 | Y | 642 | 30483 | detail sheet |
| project_007 | 25 | 0 | 685 | 1 | 0 | 2406 | 250 | 1173 | Y | 251 | 855 | Y | 642 | 30483 | general notes |
| project_007 | 26 | 0 | 753 | 65 | 64 | 2117 | 250 | 1678 | Y | 315 | 248 | Y | 642 | 30483 | member schedule |
| project_007 | 27 | 0 | 723 | 57 | 56 | 1970 | 250 | 1546 | Y | 307 | 231 | Y | 642 | 30483 | member schedule |
| project_007 | 28 | 0 | 659 | 22 | 5 | 5304 | 250 | 2369 | Y | 272 | 881 | Y | 642 | 30483 | general notes |

Note: pages with `None` in the drawing/graph columns are pages where `engineering_token_count=0`, so `extract_geometry`'s `active_pages` filter (Phase 1, unchanged) skipped geometry extraction for that page entirely — this is existing, intentional production behavior (skip geometry work on pages with no engineering tokens to associate it with), not a pilot defect.
