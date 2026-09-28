# Extraction-Only Gold Evaluation Report

Evaluation-only. No production code, flags, models, prediction, takeoff, geometry, or OCR changes.
Artifacts: `extraction_gold.json`, `eval_report.json`, `tokens_*.json`.

## Documents (STEP 1)

| Document | Pages | Text | Project/source | Why selected |
| --- | ---: | --- | --- | --- |
| Struct.pdf | 24 | native | Estima 3D Struct | High-density ST; W/HSS + BP/CL |
| Burrville ES - ST.pdf | 29 | native | uploads / 51 Burrville | Requested ST package |
| ST.pdf | 23 | native | uploads/ST.pdf | Additional ST; hyphenated C-# |
| ST-Spring Garden ES.pdf | 8 | native | Estima 3D | Smaller ST; C1–C5 / L1 marks |

Gold pages (stratified): Struct 8/10/14; Burrville 7/10/18/29; ST 8/9/19; Spring Garden 3/8.
Unit: unique `(document, page, normalized)` presence. Bare C/L rejected when area/grid/camber/sheet-callout.

## Metrics (STEP 6)

Primary = post-filter `engineering_tokens` (extraction success), not takeoff quantity.

- Gold 207 · TP 174 · FN 33 · FP 157
- Recall **84.1%** · Precision **52.6%** · F1 **64.7%**
- Steel-conditioned precision (exclude anon dimension FPs): **94.1%** (11 residual FPs)
- Usable (takeoff_eligible) recall **80.2%** with **8** context demotions of otherwise-extracted tokens

## Document table

| Document | Pages | Gold | TP | FN | FP | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Burrville ES - ST.pdf | 29 | 63 | 52 | 11 | 45 | 53.6% | 82.5% | 65.0% |
| ST-Spring Garden ES.pdf | 8 | 19 | 17 | 2 | 52 | 24.6% | 89.5% | 38.6% |
| ST.pdf | 23 | 47 | 29 | 18 | 8 | 78.4% | 61.7% | 69.0% |
| Struct.pdf | 24 | 78 | 76 | 2 | 52 | 59.4% | 97.4% | 73.8% |

## FN stages (usable view)

| Failure Type | Count | % of FN (41) | Examples |
| --- | ---: | ---: | --- |
| TOKENIZATION_MISS | 20 | 48.8% | Burrville p18 W12X106…; ST p8 W8X24…; Struct HSS6X4X3/8, C8X11.5 |
| RAW_EXTRACTION_MISS | 13 | 31.7% | ST.pdf C-1…C-11; Burrville L-13/L-14 |
| CONTEXT_DEMOTION | 8 | 19.5% | Burrville p18 detail_reference W10X112, WT7X19, … |
| FILTER_MISS | 0 | 0% | — |
| SCHEDULE_EXTRACTION_MISS | 0 | 0% | — |
| NORMALIZATION_MISMATCH | 0 | 0% | — |
| UNKNOWN | 0 | 0% | — |

TOKENIZATION_MISS evidence: tokens exist in `extract_document_structure` engineering_tokens, then disappear in `group_annotation_fragments` (before filter).

## C/L/CL/BP

| Family | Raw extraction | Notes |
| --- | --- | --- |
| BP# | 11/11 (100%) | Extracted as marks; scope takeoff on Struct gold pages |
| CL# | 18/18 (100%) | Same |
| C# / C-# | 6/17 | Unhyphenated C1… OK; hyphenated C-1… miss |
| L# / L-# | 6/8 | L-13/L-14 miss (hyphen) |
| Bare C/L/CL/BP | Out of gold after curation | Product patterns require digits; bare letters are not in TOKEN_PATTERNS |

Resolution (BP→plate / CL→angle) is downstream of raw extraction and was not scored as extraction TP/FN.

## Incomplete L/2L

No incomplete `L4X4` / `2L4X4` forms on selected ST gold pages (native words or spaced). Complete `L4X4X1/4` (Burrville p18) and `L6X6X3/4` (ST p9) extracted and preserved (`takeoff_eligible=True`). Unsafe completion: not observed on this set. River Road incomplete cases exist in june gold but that PDF is Arch-mixed and was not primary gold here.
