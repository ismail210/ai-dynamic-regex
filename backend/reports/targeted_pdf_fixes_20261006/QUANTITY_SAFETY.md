# Quantity safety

`QuantityEngine`, `services/prediction/orchestrator.py`, and the prediction contract were not edited.

Compared the pre-fix snapshots in `backend/reports/manual_pdf_validation_20261006/extract_*.json` with the re-extract in this directory.

| PDF | Mark map before | Mark map after | Endpoints before | Endpoints after |
| --- | --- | --- | --- | --- |
| Struct.pdf | 12 sections, listed below | identical 12 | none | none |
| Springhill | 0 | 0 | none | none |
| Brandywine | 0 | 0 | 96 complete, 1 gap | 96 complete, 1 gap |
| Burrville | 0 | 0 | 54 complete | 54 complete |

Struct.pdf map, both runs: C1 `HSS6X6X1/2`, C2 `HSS7X7X3/8`, C3 `HSS8X8X1/2`, C4 `W10X49`, C5 `HSS12.750X0.375`, C6 `HSS12X8X5/8`, L1 `W8X21`, L1A `W8X21`, L2 `W8X28`, L2A `W8X28`, L3 `W16X36`, L4 `W24X62`.

## What changed in the extracted rows

Springhill M-20, N-20, and N.2-12: plate status `unresolved` with the garbage string → `present` with the printed `1"x18"x18"` and notes `**`. They are `grid_location` rows. They are not in the mark map. No member length was taken from the level elevation `14' - 0"`.

Furley BP4–BP6 lost the inspection sentences and kept the printed plate sizes. BP7 gained remarks `SEE S/S502`. CL rows lost inspection sentences. CL5, CL7, and CL9 stay `unresolved`. None of those marks entered the map. C1 plate `14"x14"x3/4"` is still a combined plate with no thickness assigned by position. L4 plate remains `-` / not applicable. L5 is still not a steel section.

Brandywine BP1–BP9 on page 43 are unchanged, including washer and anchor columns staying out of the plate size. Example: BP1 `1 1/4" 1'-6" 1'-6"`, BP6 `1 3/4" 2'-0" 2'-0"`, BP8 `3/4" 1'-6" 1'-6"`.

## Invariants checked

- Schedule rows did not add mark-map entries. The three maps that were empty stayed empty. The Struct.pdf map did not gain BP, CL, or grid locations.
- The malformed Springhill string does not match the plate pattern and stays unresolved if the duplicate-span evidence is absent. The test covers that.
- Brandywine washer, anchor, bolt, and weld columns are still excluded from BP1–BP9 plate text. The existing headed-plate test passed inside the full suite.
- Combined plates still leave thickness null. The existing `1"x18"x18"` test passed.
- Incomplete section labels were not completed. L5 and the CL N/A rows are not in the mark map.
- Exact section strings in the Struct.pdf map are unchanged.
- Endpoint counts are unchanged, so repeated views did not add column runs.
- Grid locations such as M-20 stay `mark_role` grid locations.
- Level pairing did not become a physical length. `level` is null on the unpaired bands. The trace’s `logical_stack_only` flag is true, and the bottom end of A.3'-19 stays unresolved.
- Tracing was not written into the mark map or the endpoint counts.
