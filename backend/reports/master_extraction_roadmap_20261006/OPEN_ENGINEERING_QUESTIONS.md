# Open engineering questions (need a human / estimator decision)

1. **Conflicting elevations.** OSSE LEVEL 2: the schedule says `55' - 10"` and the plan says `55'-2"`. Which source governs for estimating — the plan, the schedule, or an RFI? Until decided, both are shown.
2. **SEE PLAN with two plan values.** Washington Latin THIRD and FOURTH FLOOR. Is the level a range, or is each plan view its own level?
3. **TYP / SIM without a printed count.** Should a `TYP` callout ever count more than its printed occurrence? Today, no; only `TYP x N` with a printed N counts.
4. **Definition-only marks.** A mark is in a schedule but never seen on a plan. Report only, or count as one? Today it is report only.
5. **Column counting across levels.** Is a column one piece per schedule tier, one per splice, or one per stack? This affects every column count and any future length.
6. **Plates per column.** `plate_count_per_member` is a hint. Should base and bearing plates become their own takeoff family, counted from column occurrences?
7. **Incomplete angles with a single schedule definition.** May a reviewer accept `L4x4` → schedule `L4X4X1/4` per occurrence, or per mark only?
8. **Scope.** Existing steel, demolition, and bid alternates (OSSE has 16 alternate mentions). Are they excluded, separated, or counted in a separate column?
9. **Revisions.** When a sheet appears in two issues, which issue wins? Is the newest issue automatic, or a human choice?
10. **Lintels with non-catalog text** (Furley CL5, CL7, CL9). Do these go to a misc-metals line with the printed text, or to review only?
11. **Downstream BBX / export target.** Which tool receives the takeoff (Tekla PowerFab / FabSuite, Tekla Structures, SDS2, StruM.I.S, Bluebeam, Excel only)? What fields and format does it require? No contract exists in the repo.
12. **Member box (BBX) expectation.** Should the green box mark the whole member stroke, the segment between grids, or only the label's beam line? This was a G9 ambiguity: parallel bays on Burrville.
13. **Fort Davis mark-based location plan (S301).** Should tag → nearest grid intersection be allowed as Level B review evidence?
14. **Brandywine `D-13(18'-2")`** appears in two schedule blocks with `W12X40` and `W12X50`. Are these two tiers or a drawing conflict?
