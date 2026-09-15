# Semantic damage test PDFs (in-place)

Controlled copies of **real** structural drawings for Estima3D Semantic Review validation.

Mutations are applied **on the actual drawing callouts** in their original locations. There is no test table, legend panel, or synthetic summary page.

## Safety

- **Original project PDFs are never modified.**
- Controlled corruptions are **synthetic test mutations** applied to copies of real drawing pages.
- Not training data. Not production gold. Not customer documents.
- Production inference flags / incomplete L–2L safety / Excel policy are unchanged by this corpus.

## Source PDFs

Located under `backend/uploads/` (never edited by the generator):

| Project | Source file |
|---------|-------------|
| Burrville | `Burrville ES - ST__0d910a43b4a0.pdf` |
| ST | `ST__0bfc2d61245d.pdf` |
| Structure | `Structure - Copy__9414716bffc6.pdf` |

## Generated files

| PDF | Manifest |
|-----|----------|
| `burrville_SEMANTIC_DAMAGE_TEST.pdf` | `burrville_SEMANTIC_DAMAGE_TEST.manifest.json` |
| `st_SEMANTIC_DAMAGE_TEST.pdf` | `st_SEMANTIC_DAMAGE_TEST.manifest.json` |
| `structure_SEMANTIC_DAMAGE_TEST.pdf` | `structure_SEMANTIC_DAMAGE_TEST.manifest.json` |

Frontend mirrors of the manifests (for Semantic Review case nav / expected-vs-actual UI):

`frontend/src/fixtures/semanticDamage/`

## Categories

| Category | Purpose |
|----------|---------|
| `char_corruption` | OCR-like glyph swaps → repair / needs review |
| `deletion` / `insertion` | Character edits → repair / needs review |
| `decimal_fraction` | Fraction thickness rewritten as decimal → **normalization** (not ML repair) |
| `spacing` | Spaced / × fields → grouping + normalization |
| `incomplete` | Angle thickness stripped → **abstain** (never invent thickness) |
| `clean_control` | Untouched labels → must not rewrite |

## Manifest format

Each case includes: `test_case_id`, `source_page`, `original_text`, `test_text`, `category`, `corruption_type`, `intended_semantic_result`, `expected_operation`, `expected_status`, `expected_normalized`, `expected_abstention`, `original_bbox`, `modified_bbox`.

**Expected fields are test metadata only.** The UI must show them separately from actual backend results. They are never fed into the semantic pipeline.

## How to regenerate

```bash
cd backend
./venv/bin/python scripts/build_semantic_damage_test_pdfs.py \
  --output-dir ../validation/semantic_test_pdfs \
  --seed 20260914
```

Optional: `--source-dir` to point at an alternate uploads root.

## How to upload / process / review

1. Upload one `*_SEMANTIC_DAMAGE_TEST.pdf` via **Upload & Extract**.
2. Open **Semantic Review**.
3. Confirm the PDF drawing is visible (paper frame, not a black page).
4. Click **Process drawing**.
5. Use the controlled-damage bar:
   - filters (All / Damaged / Normalization / Incomplete / Clean / Needs review / Reviewed)
   - **Case N / M** with Previous / Next (jumps page + bbox + inspector)
6. Click a damaged annotation on the drawing:
   - text `semantic_bbox` highlights on the real page
   - inspector shows RAW / NORMALIZED / FAMILY / OPERATION / candidates / scores / evidence
   - **Expected vs actual** compares test metadata to live backend output (PASS / REVIEW / UNMATCHED)
7. Accept / Reject repairs through the existing Bassam Semantic Review flow (no automatic production rewrite).

## Evaluation rule

Do **not** claim “all damaged labels repaired” unless live backend results show that. Failed or abstaining cases are valuable — this corpus measures the pipeline.

## Modification method

Full-page-count `copy` of the source PDF, then targeted white cover + replacement text at the original callout bbox (PyMuPDF). Page size, orientation, linework, title blocks, and page count are preserved. Only selected annotation glyphs change.
