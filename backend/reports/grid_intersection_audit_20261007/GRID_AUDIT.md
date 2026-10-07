# Grid extraction and intersection ground-truth audit

Date: 2026-10-07. Extractor: `legend_extractor_v6s-grid-bubbles`.

Machine-readable scores: `grid_ground_truth.json` in this folder.
Margin renders: `renders/`.

This audit scores printed grid bubbles and the drawn crossings of those lines.
It does not score object-to-grid allocation. Allocation was not redesigned.

A match is a confirmed label whose text, orientation, and bubble center agree
with an expected bubble within 55px. A left or right bubble expects a
horizontal line. A top or bottom bubble expects a vertical line.
An intersection counts only when the two drawn lines actually overlap.
The product of the two axes is not the expected set.

On this audit a confirmed grid is one label plus its line, so grid-line
precision and recall equal label precision and recall. A missing bubble is a
missing line. A confirmed label on the wrong orientation is a false line.

## 1. Executive summary

The detector is precise on the bubbles it confirms and incomplete on the
bubbles it does not.

| Project | Sheets | Grid precision | Grid recall | Line precision | Line recall | Intersection precision | Intersection recall |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Burrville | S-101A, S-101B, S-102A | 1.00 | 0.267 | 1.00 | 0.267 | 1.00 | 1.00 on 3 drawn crossings |
| OSSE | S-101-O, S-122-O | 0.981 | 0.964 | 0.981 | 0.964 | 0.970 | not hand-counted past the false `N` |
| Struct / Furley | S101A, S102C | 0.915 | 0.377 | 0.915 | 0.377 | 0.975 | not hand-counted |
| Brandywine | S-110, S-111 | 0.864 | 0.345 | 0.864 | 0.345 | 1.00 | not hand-counted |

Burrville prints A–E and 1–5 on all three sheets. Eight of those thirty
bubbles were confirmed, all of them real, and none of the confirmed
intersections is false. The other twenty-two bubbles are in the text layer
and were kept as candidates, or the page has no chain inside the current
rules. OSSE's high intersection count is mostly real overlap on S-101-O
(345 crossings, all between matched bubbles). Eleven of the twenty-two
intersections on S-122-O are false because a title-block `N` took a long
vertical line. Struct and Brandywine miss large sets of printed bubbles:
opposite-end copies, the right-hand grids past the title-column cut, and
Brandywine's top number row, which sits just outside the margin band.

Two deterministic fixes were made, both from a measured failure. A second
copy of the same letter no longer deletes the outer grid, which restored
Burrville `A`. An inward digit whose line does not end at that digit is no
longer confirmed, which removed the false horizontal `1` on S-101A.
Thresholds were not lowered.

## 2. Ground-truth sheets

All nine sheets are rotation 0, about 3024×2160.

| Project | Sheet | PDF page | Why it was chosen |
| --- | --- | ---: | --- |
| Burrville | S-101A | 4 | Foundation plan. Clear left letters and top numbers. |
| Burrville | S-101B | 5 | Same bubble layout. The detector previously confirmed nothing. |
| Burrville | S-102A | 7 | Same bubble layout on the next area plan. |
| OSSE | S-101-O | 5 | Parking plan with fractional grids. Source of most of the 740 intersections. |
| OSSE | S-122-O | 10 | Area plan with the same fractional series, plus a suspicious `N`. |
| Struct / Furley | S101A | 3 | Foundation plan. Letters A–M on the left, numbers 1–18 on both edges. |
| Struct / Furley | S102C | 9 | Same main grid plus a fractional grid along the lower plan. |
| Brandywine | S-110 | 6 | Inner column contains `E.4`, `B.2`, `D.1`. |
| Brandywine | S-111 | 7 | Two left columns on one sheet. |

`view_id` is null on every grid record. `view_status = unknown`.
The view index stores title lines, not plan extents, so no view was invented.

## 3. Expected grids

Expected bubbles are PDF text tokens in a column or row that was checked
against the margin render. Opposite-end copies on Struct are separate
expected bubbles of the same axis. Brandywine's top number row and its
bottom number row are different grids even when the text matches.

Not expected, and not scored as misses: interior notes, dimensions,
member marks, and the repeated bubbles inside the right title block
(OSSE's second copy of A–E at x≈2467, Struct's second letter column at
x≈2964).

## 4. Detected grids

Confirmed means a margin label plus one long axis-aligned chain.
Candidates are margin labels with no such chain. Review means the chain
was already claimed, or the same box sits on both a horizontal and a
vertical line.

| Sheet | Confirmed | Review | Candidates of the expected set |
| --- | ---: | ---: | --- |
| Burrville S-101A | 4 | 0 | D, E, 1, 2, 3, 5 |
| Burrville S-101B | 0 | 0 | A–E and 1–5 |
| Burrville S-102A | 4 | 0 | D, E, 1, 2, 3, 5 |
| OSSE S-101-O | 40 | C.8 | none of the scored bubbles left as candidates |
| OSSE S-122-O | 14 | 0 | vertical 3 |
| Struct S101A | 15 | 9 | the unscored ends, plus letters with no chain |
| Struct S102C | 32 | 21 | same pattern, plus `G` and `G.2` |
| Brandywine S-110 | 11 | 1 | outer column A–E; top row 1–21 was not searched |
| Brandywine S-111 | 11 | 2 | outer E and A; inner C.6 and D.2; bottom 2, 3, 4 |

## 5. Grid precision and recall

### Burrville S-101A

```text
Expected horizontal: A, B, C, D, E
Expected vertical:   1, 2, 3, 4, 5
Detected:            A, B, C horizontal; 4 vertical
Missing:             D, E, 1, 2, 3, 5
False positives:     none
Precision: 1.00
Recall:    0.40
```

### Burrville S-101B

```text
Expected horizontal: A, B, C, D, E
Expected vertical:   1, 2, 3, 4, 5
Detected:            none
Missing:             A, B, C, D, E, 1, 2, 3, 4, 5
False positives:     none
Precision: n/a (nothing confirmed)
Recall:    0.00
```

The same ten bubbles are present in the text layer, at the same coordinates
as S-101A. All ten stay candidates.

### Burrville S-102A

```text
Expected horizontal: A, B, C, D, E
Expected vertical:   1, 2, 3, 4, 5
Detected:            A, B, C horizontal; 4 vertical
Missing:             D, E, 1, 2, 3, 5
False positives:     none
Precision: 1.00
Recall:    0.40
```

### OSSE S-101-O

```text
Expected horizontal: A, B, B.1, B.5, B.9, C, C.1–C.5, C.45, C.7, C.8, D, D.3, D.6, D.8, E, and a left-edge 1
Expected vertical:   1 through 21 along the top
Detected:            40 of those 41
Missing:             C.8 (review: a nearer label already uses the line)
False positives:     none
Precision: 1.00
Recall:    0.976
```

The right-edge repeat of A–E is the same axes, not a second expected set.
Numbers 22 and higher in the text sit in the title area and were not part
of the top bubble row.

### OSSE S-122-O

```text
Expected horizontal: C, C.1, C.2, C.3, C.4, C.45, C.5, C.7, C.8, D, D.2, and a left-edge 1
Expected vertical:   7 and 3
Detected:            all of those except vertical 3, plus N
Missing:             3
False positives:     N vertical at (2160, 1945)
Precision: 0.929
Recall:    0.929
```

`N` sits at the same sheet corner on S-101-O, where it was only a candidate.
On S-122-O it claimed a vertical line from y=192.6 to y=1777.6.

### Struct S101A

```text
Expected horizontal: A B C D E F G H J K L M (no I)
Expected vertical:   1–18 on the top edge and again on the bottom edge (36 bubbles)
Detected correct:    C, F, H, J, L horizontal; 4, 6, 10, 11, 12, 16 vertical
                     (4, 6, and 11 also on the top edge)
Missing bubbles:     34, including both ends of the numbers that were not confirmed
False positives:     B vertical at the left edge (71, 1924). B is a horizontal grid.
Precision: 0.933
Recall:    0.292 of printed bubbles, 0.367 of unique axes (11 of 30)
```

Numbers 1, 2, and 3 are printed at x=2498, 2649, and 2800. The title-column
cut is x≥0.82×width (≈2480), so those three bubbles are never searched.

### Struct S102C

```text
Expected:            the same A–M and 1–18 bubbles, plus a lower fractional row
                     A.5 B C C.2 D E F G G.2 G.5 H J J.2 J.5 J.8 K K.8 L
Detected correct:    29 bubbles, including 16 of the 18 fractional labels
Missing:             37 bubbles. Unique-axis recall is 28/48 = 0.583
False positives:     T vertical (2200, 215), 0 vertical (2167, 2084),
                     and the same left-edge B read as vertical
Precision: 0.906
Recall:    0.439 of printed bubbles
```

`G.2` is review because a nearer fractional label already uses that chain.
`0` sits between grids 5 and 6. It is not one of them. `T` is not in either
bubble row.

### Brandywine S-110

```text
Expected horizontal: outer column E D C B A, and inner column A B.2 C D D.1 E E.4
Expected vertical:   top row 1–21 at y≈329, and bottom row 5 4 3 2 1 at y≈2131
Detected correct:    inner A, B.2, C, D, D.1, E, E.4; bottom 4 and 3 as vertical
Missing:             all five outer letters; the whole top row; bottom 5, 2, and 1
False positives:     5 horizontal at the bottom bubble (the line is the sheet border),
                     and 1 horizontal at (333, 1976), which is not either number row
Precision: 0.818
Recall:    0.237
```

`E.4`, `B.2`, and `D.1` are genuine. They sit in the same inner column as
A, C, D, and E, and each has its own horizontal chain.

The top row is real text at y≈329. The margin band is 14% of the page
(≈302px), so that row is outside the search. It was not dropped by the
label grammar.

### Brandywine S-111

```text
Expected horizontal: outer E D C B A, and inner A B.2 C C.6 D.1 D.2 E.4
Expected vertical:   bottom 5 4 3 2 1
Detected correct:    outer B, C, D; inner A, B.2, C, D.1, E.4; bottom 5 and 1
Missing:             outer E and A; inner C.6 and D.2; bottom 4, 3, 2
False positives:     1 horizontal at (402, 1923)
Precision: 0.909
Recall:    0.588
```

A further column B C D E E.2 F G at x≈2602 is printed and was excluded by
the title-column cut. It is not in the scored expected set. It is a real
printed series the search did not see.

## 6. Grid-line precision and recall

Line scores equal the label scores above.

Confirmed lines that matched a bubble are `confirmed_grid_line`.
Confirmed lines that did not match are `false_grid_line`:

- Struct S101A and S102C: left-edge `B` on a vertical line.
- Struct S102C: `T` and `0`.
- OSSE S-122-O: `N`.
- Brandywine S-110: bottom `5` on the horizontal border at y=2107.1, from x=124.4 to x=2950.4, and the extra horizontal `1`.
- Brandywine S-111: the extra horizontal `1` at y=1929.5.

Missing lines are the missing bubbles. Burrville D, E, 1, 2, 3, and 5 do
not have an axis-aligned chain within 32px that is at least 360px long.
Grid 5's aligned dashes on S-101A total about 225px, which stays under that
minimum. Those dashes were not merged into a neighboring grid.

## 7. Intersection precision and recall

### Burrville, hand-scored

Only pairs whose lines overlap are expected.

```text
S-101A
Expected: 4/C
Detected: 4/C
Missing:  none
False:    none
Precision: 1.00
Recall:    1.00

A's line is y=271.2, x=1098.8–1973.6. Grid 4 runs y=635.5–1410.2, so A does not reach it.
B's line ends at x=808.0. Grid 4 is at x=1942.3, so B does not reach it.
C's line is y=1071.9, x=1675.0–2084.8, which contains x=1942.3.

S-102A
Expected: 4/B, 4/C
Detected: 4/B, 4/C
Missing:  none
False:    none
Precision: 1.00
Recall:    1.00

A's line ends at x=1911.4, short of grid 4 at x=1942.3, so 4/A is not expected.

S-101B
Expected drawn crossings: none
Detected: none
Label recall is 0. The empty intersection list does not mean the grid was recovered.
```

### OSSE

```text
S-101-O
Detected: 345
True:     345 (both lines matched an expected bubble and overlap)
False:    none
Precision: 1.00
Recall:    not hand-counted bubble by bubble.
           C.8 was not given its own line, so it adds no separate crossing.
           The 345 crossings are one parking plan, not six sheets counted twice.

S-122-O
Detected: 22
True:     7/C, 7/C.1, 7/C.2, 7/C.3, 7/C.4, 7/C.45, 7/C.5, 7/C.7, 7/C.8, 7/D, 7/D.2
False:    the same eleven horizontals crossed with N
Precision: 0.50
Recall:    not hand-counted beyond that split
```

### Struct

```text
S101A:  13 detected, 13 true under the bubble test, 0 false. Precision 1.00.
S102C:  68 detected, 66 true, 2 false (T/H and 0/H). Precision 0.971.
```

Recall was not hand-counted. Many printed axes have no confirmed line, so
their crossings are absent. The crossings that were emitted are overlaps of
partial lines, not the full letter-by-number product. On S102C a fractional
vertical such as `A.5` crosses the main horizontal letters `C`, `F`, and `K`
because both systems were treated as one page.

### Brandywine

```text
S-110: 4/A, 4/E, 4/E.4, 4/C, 4/D, 3/E, 3/E.4, 3/D. Precision 1.00.
       The false border line under grid 5 does not reach these verticals, so it creates no intersection.
S-111: 5/A, 5/E.4, 5/C, 5/D.1, 5/B.2, 5/C, 1/C. Precision 1.00.
       5/C is emitted twice: once for each C column. See view isolation.
```

## 8. Missing grids

The misses fall into six groups. Examples:

| Group | Example |
| --- | --- |
| A. Not a printed grid | Burrville interior `1` at (324, 1316), and `8` at (304, 1576). Text in the plan, not a bubble. |
| B. Printed, never searched | Struct grids 1, 2, 3 at x>2480. Brandywine S-110 top row 1–21 at y≈329, outside the 14% margin. Brandywine S-111's right column at x≈2602. |
| C. Found, then not confirmed | Burrville D, E, 1, 2, 3, 5 on S-101A, and all ten bubbles on S-101B, stored as candidates. OSSE `C.8` is review because another label owns the line. Struct top copies of 10, 12, 16 are review for the same reason. |
| D. Wrong view | No grid was given a wrong `view_id`, because every `view_id` is null. S-111 mixes two columns. See section 10. |
| E. Merged onto the wrong chain | Struct `G.2` on S102C is review: a nearer fractional label already uses that chain. Burrville's short dashes on grid 5 were not merged into grid 4. |
| F. Geometry the rules do not accept | Burrville 1, 2, and 5. The close crops show the bubble above the border, with no vertical line through it, or a line offset from the bubble. Grid 5's aligned ink is about 225px. |

## 9. False grids

| Sheet | False confirmed label | Why it is false |
| --- | --- | --- |
| OSSE S-122-O | `N` vertical | Same corner token on S-101-O, where it has no grid line. It then crosses eleven real horizontals. |
| Struct S101A, S102C | `B` vertical at x≈71 | `B` is in the left letter column. The column's grids are horizontal. |
| Struct S102C | `0` vertical | Sits between bubbles 5 and 6, not on a bubble. |
| Struct S102C | `T` vertical | Not in the top number row or the letter column. |
| Brandywine S-110 | `5` horizontal | The bottom bubble was tied to the sheet border at y=2107. |
| Brandywine S-110, S-111 | extra `1` horizontal | A long line near the bottom, not the bottom number bubble. |

The interior Burrville `1` that used to confirm at (324, 1316) is now a
candidate. It is no longer a false grid.

## 10. View-isolation issues

`view_status = unknown` on every audited sheet. Key-plan text inside the
right title block was excluded by the 0.82 width cut, and those repeats were
not confirmed as a second grid.

S-111 is the sheet that shows the limit. It has two left columns:

- outer `C` at x≈99, line y=1074.2, x=318.6–1153.7
- inner `C` at x≈294, line y=1004.0, x=318.6–2583.8
- vertical `5` at x=379.3, y=656.9–1478.9

Grid 5 crosses both lines, so the sheet emits `5/C` twice. The two records
have no `view_id`, so a later allocation step cannot tell the plans apart.
S102C has the same shape: the lower fractional row and the main letter
column are crossed as one page (`A.5/C`, `B/C`, and the rest).

No fix was applied. The view index does not yet have plan extents, and this
audit does not invent them.

## 11. Rotated-page results

Every audited sheet has `page_rotation = 0`. Display coordinates and PDF
coordinates are the same on these pages, and the confirmed lines sit on the
bubbles listed above.

Rotation is covered by `test_dashed_segments_merge_and_rotation_follows_display`.
A horizontal PDF segment on a page rotated 90 degrees becomes a vertical
display segment. None of the four project PDFs used here contains a rotated
plan sheet, so this audit does not prove a rotated construction drawing.
Yellow Spring was not part of this set.

## 12. Burrville analysis

Project-wide counts before this audit (14 confirmed, 11 intersections) were
low because most printed bubbles have no usable line, and because a second
`A` was cancelling the real left-edge `A`.

After the two fixes, S-101A and S-102A each confirm A, B, C, and 4.
Precision is 1. The recall stays 0.40 on those sheets and 0 on S-101B.

What the close crops and the vector probe show:

- `A`, `B`, `C`, and `4` have a chain longer than 360px within 32px of the bubble.
- `D` and `E` are printed in the same left column (x=124) and have no such chain.
- `1`, `2`, and `3` are printed on the top row. The crops show the number above the border, without a vertical grid line in the first few hundred pixels.
- `5` has short dashes near x=2441, about 225px merged, under the minimum.
- S-101B has the same ten bubbles and no chain inside the rules. They stay candidates. Confirming them would mean attaching unrelated lines.

The only clean crossings are `4/C` on S-101A and `4/C`, `4/B` on S-102A.

## 13. OSSE analysis

S-101-O explains the project intersection count. Forty matched bubbles,
most of them full-width horizontals (x≈238–2476) and full-height verticals
(y≈245–1743), overlap 345 times. That is one plan. The fractional labels
`B.1`, `C.45`, `D.8`, and the rest are printed in the left bubble column
and were confirmed with their own lines. Detail and schedule text in the
title block was not confirmed as a grid.

S-122-O is the sheet that makes the count unsafe to trust project-wide.
Half of its intersections are `N` crossed with the real horizontals.
`N` is not a grid on that plan.

## 14. Struct / Furley analysis

The underlying intersections of the lines that were confirmed are mostly
real overlaps. Precision is 0.975. The ambiguity downstream comes from the
extraction, not from a bad crossing test:

- Letters and numbers are printed twice, once on each end. One chain confirms one label, so the other end becomes review.
- Fractional labels on S102C sit close together. `G.2` loses its chain to a neighbor.
- `B` on the left edge is confirmed vertical, so any later allocation sees the wrong axis.
- Lines are partial. A vertical number often crosses only some of the letters, which is why 15 confirmed grids on S101A produce 13 intersections rather than a full product.
- Two grid systems on S102C are not separated by view.
- Grids 1, 2, and 3 fall in the title-column cut.

Those are the conditions that produce ambiguous allocations. Allocation
was not changed.

## 15. Brandywine analysis

`E.4`, `B.2`, and `D.1` are genuine grid labels on S-110 and S-111.
They are in the inner bubble column with the whole letters, and the
detector kept them.

The same sheet also prints a second system. On S-110 the outer column
A–E is present and unconfirmed. On S-111 both columns are partly confirmed,
and grid 5 crosses both `C` lines. The top number row on S-110 is a third
printed series, and it sits outside the margin band, so it contributes
nothing. The grid is being read once per sheet, not once per view.

## 16. Deterministic fixes made

Both fixes are in `backend/services/engineering/grid_intelligence.py`.
The cache key is now `legend_extractor_v6s-grid-bubbles`.

1. Two different boxes with the same text no longer cancel each other.
   Before this, the left-edge `A` on S-101A and S-102A was confirmed and
   then deleted because another `A` was vertical. The left-edge `A` is
   confirmed horizontal again. Test: `test_a_second_copy_does_not_erase_the_outer_grid`.

2. A label that is not in the outer bubble band (within 72px of the
   outermost token on that side) must sit within 100px of a chain end.
   This removed the false horizontal `1` at (324, 1316) on S-101A, which
   was inside the 14% margin but about 200px inward of the real bubble
   column, on a line that starts at x=1675. Test: `test_an_inward_digit_on_a_distant_line_is_not_a_grid`.

Not changed, because the audit did not show a safe rule:

- minimum chain length 360px
- association tolerance 32px
- 14% margin band
- 0.82 title-column cut
- the label grammar

Lowering those would confirm Burrville `5` from a 225px dash, or pull the
title block into the grid.

## 17. Remaining limitations

- Burrville recall stays at 0.267 until D, E, 1, 2, 3, 5, and all of S-101B have a line rule that does not grab unrelated ink.
- Struct unique-axis recall is about 0.37 on S101A and 0.58 on S102C. Opposite-end bubbles, the title-column cut, and the wrong orientation of `B` are still open.
- Brandywine's top number row is outside the margin band.
- `view_id` is unknown, so multi-column sheets mix intersections.
- OSSE S-122-O's `N` is a false axis and produces 11 false intersections.
- No rotated plan from these four projects was in the audited set.
- Intersection recall was hand-listed only for Burrville. OSSE's 345 crossings were checked by label identity and line overlap, not by eye one at a time.

## 18. Recommendation

Grid extraction is not trustworthy enough to drive a better allocation.
OSSE S-101-O is in good shape. Burrville, Struct, and Brandywine still miss
printed grids, and two sheets still emit false axes (`N`, `B` vertical,
`0`, `T`, the Brandywine border). Allocation should wait until those
extraction failures have a measured fix.

NOT READY — GRID EXTRACTION STILL NEEDS WORK

## 19. After logical-axis extraction

Extractor: `legend_extractor_v6t-grid-axes`. Same nine sheets, same expected bubbles, same 55px match. Allocation was not changed. Numbers below replace the section 1 scores for extraction only. The section 1 table is the v6s baseline.

| Project | Precision | Recall | Matched | False positives | Missing | Confirmed grids | Logical merged axes | Fragmented axes recovered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Burrville | 1.00 | 0.333 | 10 | 0 | 20 | 10 | 12 | 1 |
| OSSE | 1.00 | 0.964 | 53 | 0 | 2 | 53 | 85 | 1 |
| Struct / Furley | 0.970 | 0.561 | 64 | 2 | 50 | 66 | 39 | 7 |
| Brandywine | 1.00 | 0.618 | 34 | 0 | 21 | 34 | 120 | 4 |

Recovered against the v6s missing set: Burrville S-101A `5` and S-102A `2`. Struct S101A `A`, `17` (both ends), `16`, `9`, `8`, `1` (both ends). Struct S102C `M`, `J`, `G`, `A`, `17`, `11`, `9` (both ends), `5` (bottom), `3` (both ends), `1` (both ends). Brandywine S-110 `C`, `B`, and top-row `1`–`5`, `7`–`9`, `11`–`13`. Brandywine S-111 `A` and `D.2`. Every v6s true positive is still matched, including S102C `F`.

False positives removed: OSSE `N`, Struct `B` vertical on both sheets, Struct `T`, Brandywine horizontal `5` and both horizontal `1`s. Still false against this expected set: Struct S101A `F` at (371, 686) and S102C `0` at (2167, 2084). `0` was already false before this change.

Decision after this pass: NOT READY — GRID EXTRACTION STILL NEEDS WORK. Burrville S-101B is still 0 of 10, and most remaining misses have no aligned run long enough to confirm without accepting a single short line.

## 20. After callout and closest-label pass

Extractor: `legend_extractor_v6u-grid-context`. Same expected bubbles and 55px match. Compared with section 19.

| Project | Precision | Recall | Matched | False positives | Missing | Confirmed grids |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Burrville | 1.00 | 0.333 | 10 | 0 | 20 | 10 |
| OSSE | 1.00 | 0.964 | 53 | 0 | 2 | 53 |
| Struct / Furley | 1.00 | 0.570 | 65 | 0 | 49 | 65 |
| Brandywine | 1.00 | 0.618 | 34 | 0 | 21 | 34 |

S-101B is still 0 of 10. Its plan has no axis-aligned line at A, B, E, 1, 2, or 5. C, D, 3, and 4 have only scraps under 80px. Those bubbles stay unresolved.

Recovered since section 19: Brandywine S-110 top `6` (the dashed line at x=880) and Struct S102C top `5`. Struct false `F` at (371, 686) is a letter stacked on `S401`. Struct false `0` is a digit on the same baseline as `4'`, `8'`, and `16'`. Both are rejected. Brandywine bottom `4` had been confirmed on that same x=880 line, 42px off the bubble and 1334px from the line end. The line now stays with top `6`, so bottom `4` is no longer confirmed.

Decision after this pass: NOT READY — GRID EXTRACTION STILL NEEDS WORK. The remaining misses are bubbles with no supported line.

## Evidence sample

```text
Sheet: S-101A
View: unknown (view_status = unknown)
page_rotation: 0

GRID LABEL AUDIT
Expected: A, B, C, D, E and 1, 2, 3, 4, 5
Detected: A, B, C and 4
Missing:  D, E, 1, 2, 3, 5
False positives: none
Precision: 1.00
Recall:    0.40

INTERSECTION AUDIT
Expected: 4/C
Detected: 4/C
Missing:  none
False:    none
Precision: 1.00
Recall:    1.00

EVIDENCE
Grid A: label bbox [118.3, 256.5, 129.4, 276.6], line y=271.2 x=1098.8–1973.6, horizontal, confirmed
Grid B: label bbox [118.3, 667.3, 129.4, 687.5], line y=701.8 x=331.1–808.0, horizontal, confirmed
Grid C: label bbox [118.3, 1066.6, 130.3, 1086.7], line y=1071.9 x=1675.0–2084.8, horizontal, confirmed
Grid 4: label bbox [1933.0, 25.7, 1942.2, 45.8], line x=1942.3 y=635.5–1410.2, vertical, confirmed
Intersection 4/C: point (1942.3, 1071.9)
  vertical evidence: grid 4, x=1942.3, y=635.5–1410.2
  horizontal evidence: grid C, y=1071.9, x=1675.0–2084.8
```
