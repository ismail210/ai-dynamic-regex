# Retest — OSSE, Yellow Spring, Washington Latin, Fort Davis

The four PDFs are in `/Users/hibareda/Desktop/Testing Projects/`, downloaded 2026-10-06. They are not inside the fixture subfolders, so the test root used symlinks and did not move the files.

| Project | File | Pages | Identity check |
| --- | --- | --- | --- |
| OSSE | `OSSE - ST.pdf` | 26 | Sheet text contains OSSE |
| Yellow Spring | `ST1.pdf` | 40 | Sheet text contains YELLOW |
| Washington Latin | `New bldg - St.pdf` | 23 | Sheet text contains WASHINGTON LATIN |
| Fort Davis | `Structure - Copy1 - edit.pdf` | 20 | Sheet text contains FORT DAVIS |

Command, from `backend/`:

```text
ESTIMA3D_TESTING_PROJECTS=reports/targeted_pdf_fixes_20261006/retest_pdf_root \
  ./venv/bin/python -m pytest tests/test_level_reference_set.py -q --tb=short
```

Result: **4 passed, 4 skipped**, 176 seconds. The skips are Furley, Brandywine, Burrville, and Springhill, whose fixture paths were not in this root. Expected answers in `reference_levels.json` were not changed.

What passed:

- OSSE: building and parking schedule levels, the LEVEL 2 plan conflict (`55'-2"` vs schedule `55' - 10"`), LEVEL 1 agreement, CBP-2 plate `12" 18" 3/4"`, and the `C.8-8.9` trace (symbols on roof, level 2, and level 1; bottom at level 1; parking sheet S101 kept out of the building scope).
- Yellow Spring: rotated column schedule, second-floor agreement `15'-4"`, no production rows on pages 13–14, flagged note counts, and the `P-21` trace with bottom `POST UP` on S2.01.
- Washington Latin: schedule names stay `SEE PLAN`; SECOND FLOOR `330'-0"`, FIRST FLOOR `314'-0"`, ROOF LEVEL `372'-9"` resolve from the plans; THIRD FLOOR and FOURTH FLOOR stay unresolved; masked elevations `314' - 0"` and `372' - 6"` are not used as schedule levels.
- Fort Davis: HIGH ROOF, LOW ROOF, 2ND, and FOUNDATION are read with no printed elevation, and no level difference is computed.
