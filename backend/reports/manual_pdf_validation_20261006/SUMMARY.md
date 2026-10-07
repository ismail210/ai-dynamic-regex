# Manual PDF validation — 2026-10-06

Working tree on `main` at `9522744`, extraction constant `3.25-level-bands-locations` (uncommitted). Five structural PDFs were run through `extract_document_structure` and `attach_schedule_grid` in memory. Schedule sheets were rendered and compared. No code, baseline, or training file was changed.

## Result

The schedules that were opened match the drawings on plate size, washer separation, level-line names, and the Revit band rule (elevation of the line above, name of the line below), except for two confirmed defects. Neither defect entered `schedule_mark_map`.

## Confirmed defects

1. **Furley `Struct.pdf` page 2.** Bearing-plate cells BP4–BP6, and several CL rows, include text from the inspection tables beside the schedule. The crop shows BP4 is only `6"x8"x3/4"`. BP and CL marks are not in the mark map.
2. **Springhill pages 26–27.** Three plate cells are the garbage string `11"x"1x188"x"1x188" "**`. The mark map is empty.

## Correct on the sheets that were opened

- Brandywine S-601 BP1–BP9 sizes match the table. Washer diameters stay in `plate_accessories`. BP8 thickness is `3/4"`, not the washer `2 3/4"`.
- Brandywine, Burrville, and Springhill level lines match the printed names and elevations.
- Burrville `29' - 0" UPPER LEVEL` and Springhill `14' - 0" FIRST FLOOR` stay `pairing: unpaired`.
- Offsets such as `C-8(-4'-4")` keep the printed offset and `direction: null`.
- Furley combined plates such as `14"x14"x3/4"` do not get an assigned thickness. CL5 and CL9 stay unresolved. L5 precast is not a steel section.
- Springhill `W10X45` matches a high-zoom crop.

## Blockers

OSSE, Yellow Spring, Washington Latin, and the Fort Davis file named in `reference_levels.json` are not on this machine. Column traces were not run. The 383/414 Struct.pdf baseline was not rerun; this file's schedule map has 12 sections, which is a different measurement.

Brandywine band labels without spaces (`14'-0" LEVEL 1`) do not fill `printed_elevation`. Pairing stays `unpaired`.

## Next steps

1. Put the OSSE, Yellow Spring, Washington Latin, and Fort Davis PDFs on disk and repeat this comparison, including one trace per building.
2. Fix the Furley table bleed and the Springhill garbage plate string before using those plate texts in review.
3. Split tight feet-inch band labels on Brandywine without pairing the elevation to the name in the same cell.
4. Identify the original 383/414 script and rerun it without writing baselines.
