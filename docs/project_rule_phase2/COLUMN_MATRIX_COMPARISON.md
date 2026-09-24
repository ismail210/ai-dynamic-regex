# Column-Schedule Matrix — Shadow Parser Comparison

**Status: NOT RUN. Gate 3 is blocked on reviewer approval.**

Gate 3 (matrix-to-member candidate generation and comparison against gold) starts only after the extraction layer for the three development pages (Burrville p.28, GCDC p.77, Springhill p.26) is reviewer-approved or corrected in `gold_annotation/`. Physical interpretation may remain `UNSURE`. As of 2026-09-23 all 262 records have both `extraction_review_status` and `physical_review_status` set to `PENDING_REVIEW`. So this report contains no parser metrics, no held-out (Ketcham, Sidwell) results, and no H5 exclusion results from a matrix parser.

The separate schedule-region quarantine is only a classification of already-extracted definition labels. It does not generate matrix members or make schedules authoritative quantity sources, so it may be measured in shadow mode while this gate remains closed.

The current-system baseline is in `COLUMN_MATRIX_BASELINE.md`.
