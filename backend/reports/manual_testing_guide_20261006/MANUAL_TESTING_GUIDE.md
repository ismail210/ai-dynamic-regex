# Manual testing guide

Use this on your own machine. Do not upload these PDFs to a hosted or production site.

## What changed

Two extraction defects on Furley `Struct.pdf`, page 2:

1. Masonry pier rows MP16, MP24, MP24A, MP32, and MP32A. The sheet prints a pier **width** and **vertical bars**. The width is kept as the raw cell. It is no longer treated as a finished steel plate. Length and thickness are not printed, so they stay empty. The bars stay in their own field. These marks are not steel section marks.
2. Wrapped second lines on the ICF lintel schedule. CL6A, CL8, and CL9 now keep `#4 STIRRUPS AT 12"o.c.` with the same mark. CL2, CL4, and CL6 also keep the printed `WELDED TO PLATE` line that sits in the same cell. The next mark does not inherit that line. `LINTEL SCHEDULE` and note lines are not pulled into the row above.

## What did not change

- Springhill plate cells M-20, N-20, and N.2-12 still read `1"x18"x18" **`. A repeated word is dropped only when the two copies overlap on the page. Two separate copies of the same word both stay.
- Brandywine `14'-0" LEVEL 1` still splits into elevation `14'-0"` and name `LEVEL 1`. They are not paired into one level. The drawn lines put `14'-0"` with LEVEL 2 and the name LEVEL 1 with the level below.
- Brandywine location `A.3'-19` stays an ambiguous trace. It is not confirmed as grid `A.3'`.
- OSSE LEVEL 2 stays a conflict: the schedule prints `55' - 10"` and plan S122 prints `55'-2"`. Neither value replaces the other. LEVEL 1 stays `38'-0"` on both the schedule and plan S121.
- The Furley steel mark list is still the same 12 sections: C1 through C6 and L1, L1A, L2, L2A, L3, L4.
- Quantity calculation code was not edited. A schedule row is still a definition, not a counted piece.

## What this test can and cannot prove

A pass means the printed cell and the extracted text agree, and that an unresolved or conflicting value was not turned into a quantity.

A pass does not mean the whole project is validated. One level check does not validate every sheet. The historical 383/414 figure could not be reproduced; do not treat a green screen as that baseline.

## Which environment

Local only.

- App: `http://localhost:5173`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

Do not use a deployed URL. Do not change deployment settings.

## Start the local app

From the repository root `/Users/hibareda/Desktop/ai-dynamic-regex`.

1. Stop any old backend window so it reloads this extraction change.
2. In one terminal:

```bash
cd backend
./venv/bin/uvicorn app:app --reload
```

3. Wait until the terminal shows the server on port 8000. Open `http://localhost:8000/docs` and confirm the page loads.
4. In a second terminal:

```bash
cd frontend
npm run dev
```

5. Open `http://localhost:5173`. The sidebar must show **Upload & Extract**, **Drawing Summary**, **Analysis & Results**, and **Takeoff**.
6. If a banner says the backend is unreachable or belongs to another copy of the project, stop and fix that before uploading. Leave `VITE_API_BASE` empty.

## How to open a PDF

1. Sidebar: **Upload & Extract**.
2. **Choose PDF**, or drop the file on **Drop a PDF here**.
3. Wait for **Upload complete**.
4. Click **Extract drawing**. Wait until the progress line finishes.
5. Click **Continue to Drawing Summary**.

Excel is not required for these checks. Do not upload a spreadsheet as if it were a drawing.

## Where to look

| What you are checking | Where |
| --- | --- |
| ICF lintel text, bearing plates, column sections | Drawing Summary. Open the row and **Show source details**. The line under the mark is the extracted source text. The caption says the row is not an installed member and not a quantity. |
| Level names and elevations | Drawing Summary, section **Levels and elevations**. |
| A printed label that joins an elevation and a name | Same page, **How the schedule's printed level labels read**. |
| Counted members | Sidebar **Takeoff**, and only after **Analyze Steel Takeoff** on Drawing Summary. The page says the total is labeled-callout members, not true physical quantity. |
| Masonry pier width versus bars | Not listed as a steel definition. Compare the sheet with `furley_page2_checked_rows.json` in this folder. Then confirm Takeoff has no MP plate row. |

## First test

PDF: `backend/uploads/Struct.pdf` (Furley). Page **2**. Table **MASONRY PIER SCHEDULE**, row **MP16**.

Printed cells: MARK `MP16`, WIDTH `16"`, VERTICAL REINFORCEMENT `1-#5`, REMARKS empty.

Pass: the width and the bars stay separate, `16"` is not a plate quantity, and MP16 is not a steel section. Details are in `MANUAL_TEST_CASES.csv` row MT-01 and `EXPECTED_RESULTS.md`.

## Pass, fail, unresolved

- **PASS** — the printed value and the extracted value match, and the row does not create a quantity it should not create.
- **FAIL** — a dimension was added, dropped, or moved onto the wrong mark, or a conflict was silently replaced by one number.
- **UNRESOLVED** — the sheet itself does not decide. Record it. Do not pick a value to make the test look finished. OSSE LEVEL 2 and Brandywine `A.3'-19` are supposed to stay unresolved.

Write the result in the **Actual Result** and **Status** columns of `MANUAL_TEST_CASES.csv`. Save screenshots with `EVIDENCE_CHECKLIST.md`. Do not put passwords or access keys in the screenshots.
