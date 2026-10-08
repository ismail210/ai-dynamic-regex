# Metrics

These counts are the rows in `PAGE_RESULTS.csv`. They are not a percentage of every column on every PDF.

| Result | Rows | What that row is |
| --- | --- | --- |
| PASS | 12 | A checked sheet feature matched the drawing, or a non-steel / non-quantity rule held |
| PARTIAL | 4 | Brandywine band split, Brandywine uncertain locations, Burrville page 28 level_span, Furley pier-as-plate |
| FAIL | 2 | Furley BP4–BP6 note bleed; Springhill 3 corrupted plate strings |
| UNRESOLVED-AS-EXPECTED | 1 | Furley CL5 and CL9 |
| NOT-TESTABLE | 5 | 383/414 baseline, OSSE, Yellow Spring, Washington Latin, Fort Davis |

24 scored rows. Denominator is this checklist, not the number of schedule cells in the PDFs.

## Field checks that support the PASS rows

| Check | Numerator | Denominator | Definition |
| --- | --- | --- | --- |
| Brandywine base-plate size rows | 9 | 9 | Extracted thickness, width, and length equal the rendered BASE PLATE SIZE cells |
| Brandywine washer pairs kept off the plate | 9 | 9 | Cropped PLATE WASHER diameter and thickness equal `plate_accessories` |
| Brandywine level lines | 5 | 5 | Name and elevation equal the lines drawn on S-601 |
| Burrville level lines | 4 | 4 | Same, against S-501 and the reference fixture |
| Springhill level lines | 3 | 3 | Same, against S-501 |
| Springhill first-floor band rows with split printed parts and pairing `unpaired` | 118 | 118 transposed rows | Every transposed row on pages 26–27 |
| Furley mark-map entries that are BP or CL | 0 | 12 | Map is C1–C6 and L1–L4 only |
| Brandywine and Burrville and Springhill mark-map size | 0 | 0 | Grid-location and plate rows produced no map entries |

## Quantity-impacting errors

0 of the 2 FAIL rows put a plate, a corrupted string, or a grid location into `schedule_mark_map`.

Sections that did enter the map (Furley C1–C6, L1–L4) matched the printed steel marks on the rendered column and lintel schedules. L5 did not enter.

## What these numbers are not

- Not a count of every column on Brandywine. 99 catalog-section rows were extracted. A hand count of all printed columns was not made, so "105 columns" was not verified.
- Not a live trace score. `trace_column` was not called.
- Not the 383/414 Struct.pdf baseline. That evaluation was not rerun.
- Not a result for OSSE, Yellow Spring, Washington Latin, Fort Davis, or the large multi-discipline sets (Winchester, SOME, River Road, GCDC, 1200 K, SFSLS). Those were inventoried only.
