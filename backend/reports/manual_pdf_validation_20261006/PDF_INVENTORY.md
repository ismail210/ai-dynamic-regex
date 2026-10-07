# PDF inventory

58 unique PDF paths were opened. Many are hash-suffixed duplicates of the same upload. Damage-test, smoke, and phase-extract PDFs are not project drawings. Page counts are from PyMuPDF.

## Priority sets that were extracted and visually checked

| PDF | Path used | Pages | What was checked |
| --- | --- | --- | --- |
| Brandywine Structural4 | `backend/uploads/Structural4__3aa51f661bdf.pdf` | 43, no rotation | Column schedules pp. 42–43, base-plate schedule p. 43. Same file as the attachment copy (4.4 MB). |
| Burrville ES structural | `backend/uploads/Burrville ES - ST.pdf` | 29, no rotation | Column schedule pp. 28–29. This is not `ST-Burrville.pdf` from the reference fixture, but the sheet is Burrville S-501. |
| Springhill Lake structural | `backend/uploads/ST - Springhill Lake__f6ddc4a7e233.pdf` | 28, no rotation | Column schedule pp. 26–27. |
| Furley Struct.pdf | `backend/uploads/Struct.pdf` | 24, no rotation | Inspection/schedule sheet p. 2 (S002). Title block is Furley Elementary School Replacement. |
| Ketcham / Structure - Copy | `backend/uploads/Structure - Copy.pdf` | 17, no rotation | Page 9 is typical details, not a column schedule. Not the Fort Davis file named in the fixture. |

## Named sets that are not on disk

| Expected by the reference fixture | Status |
| --- | --- |
| `07 - FEMS & OSSE/OSSE - ST.pdf` | Not found |
| `00 - Yellow Spring/ST1.pdf` | Not found |
| `01 - Washington Latin/New bldg - St.pdf` | Not found |
| `08 - Fort Davis Community Center/Structure - Copy1 - edit.pdf` | Not found. `Structure - Copy.pdf` is Ketcham Elementary, a different set |
| `36 - Furley ES/Struct.pdf` as a separate path | The content is present as `backend/uploads/Struct.pdf` |

## Other structural PDFs found but not cell-compared

Keyword hits only (`COLUMN SCHEDULE` / `BASE PLATE` / `COLUMN LOCATIONS`). Not manually compared to extraction.

| File | Pages | Rotated pages | Schedule-like pages |
| --- | --- | --- | --- |
| William Winchester bid set | 88 | 46 | 33–35, 56, 58, 60 |
| SOME DD set | 99 | 39 | 22, 24, 26, 61, 62, 65 |
| River Road addendum | 215 | 34 | 15, 22, 119, 133 |
| Burrville DD pricing set | 248 | 76 | Not in the scanned upload list as a separate extract; the small ST set above was used |
| GCDC Building 4 ST1 | 81 | 0 | 1, 5, 56, 58, 59, 63, 77–79 |
| 1200 K structural | 39 | 0 | 29, 32, 36, 38 |
| SFSLS structural addendum | 45 | 0 | 1, 7, 24, 26, 32, 33, 43 |
| ST.pdf (23 pages, separate from Springhill and Furley) | 23 | 0 | 3, 7, 8, 11, 12, 15, 22 |
| ST-Elmer Wolfe, Robert Moton, Runnymede, Spring Garden | 8–11 | 0 | foundation/schedule sheets; not opened visually |
| Arch Springhill Lake | 120 | 0 | Architectural; not used as a structural schedule source |
| Crystal Drive architectural / interior sets | 181 / 120 | 0 | Not structural schedules |

Full page counts for every opened path are in `inventory_raw.json`.
