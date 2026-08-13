# Estima3D — Workflow Evolution Report (Last UI Demo → Now)

**Audit type:** reporting only. No code was implemented, trained, merged, committed, or pushed to produce this report.

---

## Baseline determination

There is no explicit "demo" tag, branch, or document anywhere in this repository. The baseline below is inferred from git history and is stated with its supporting evidence and its uncertainty, not presented as proven fact.

```
LAST_UI_DEMO_BASELINE_COMMIT = ef6f71b  "fix(ui): handle legacy analyses and remove MUI prop warnings"
                                        2026-08-04 14:11:52 +0300, author BassamTar99

CURRENT_LOCAL_BASE_COMMIT    = 2911a8a  "feat(backend): wire canonical prediction contract, wildcard matching, and calibration"
                                        2026-08-04 14:24:56 +0300, author BassamTar99
                                        + all of Bassam's local uncommitted work on top (Phase 0-2.6, damaged-label v2/v3)

ISMAIL_COMMIT                = e36fb1b  "feat: restore AI multimodal pipeline and training models"
                                        2026-08-06 12:19:58 +0300, author "Hiba Reda"
                                        (git commit author name; the GitHub account is "ismail210" — same person,
                                        referred to as "Ismail" throughout this report per the existing convention)
```

**Why `ef6f71b` was chosen:** it is a frontend-only commit (33 files, all under `frontend/`) whose message and diff are explicitly about making the UI presentable — fixing legacy-record display, removing console warnings, adding empty/error states, and adding UI regression tests. The very next commit, 13 minutes later (`2911a8a`), touches **zero** frontend files — it is 19 backend-only files. No frontend file changes occur again until Ismail's `e36fb1b`. This makes `ef6f71b` the last point in history where the UI was deliberately finished and touched before the codebase moved into backend-only work, which is the most defensible technical proxy for "what the UI looked like at the demo."

**Stated uncertainty:** no commit is explicitly tagged as a demo, and no presentation/demo document exists in the repository to confirm this independently. If the actual demo happened at a different point (e.g. mid-way through `ef6f71b`'s changes, or even earlier at the Initial commit `b9a9268`), the "before" state described below would need adjustment — but `ef6f71b` is the closest defensible inflection point the repository itself provides.

The repository's Initial commit (`b9a9268`, 2026-07-31, also authored by Ismail/Hiba Reda) already contained a working multimodal fusion architecture (see `docs/MIGRATION_NOTES_v5.2.md`, "v5.2.0 AI-First Platform" — AISC catalog demoted to "verification only," fusion of text/geometry/graph/rules already scoring predictions). That architecture is the actual starting point for everything described below; it predates both Bassam's and Ismail's post-Initial-commit work.

---

## Section 1 — Executive Summary

At the last UI demo, Estima3D's prediction pipeline worked like this: PyMuPDF pulled raw text and vector line-work out of a PDF, a regex pattern matched anything shaped like a steel designation (e.g. `W18X35`), a graph loosely connected text and geometry by "what's nearby," and a fusion step combined six evidence signals (text, OCR, layout, geometry, graph, engineering rules) with fixed weights to pick one final label. The AISC catalog only verified that pick — it never got to choose. Association between a label and the drawing member it named was a simple "pick whatever geometry is closest" rule, computed by scanning a list in whatever order PDF extraction happened to produce it, not by actual position on the page.

Since that demo, the work described in this report has NOT changed that headline picture in production. **Nearly everything described below as new is currently either a diagnostic, an experiment, or a not-yet-trained/not-yet-promoted candidate — not a change to what a user sees today.** The one exception is the backend contract/calibration work Bassam committed right after the demo (`2911a8a`), which is genuinely live.

What the work has focused on instead is making the *next* version of the architecture possible to build safely:

- **Reproducibility** — geometry and graph object IDs are no longer random; the same drawing now produces the same output every run (currently only in Bassam's uncommitted local work, not production).
- **Measurability** — for the first time, there are real numbers describing how often known bugs actually fire on real project drawings (e.g. a page-truncation bug triggers on 87.4% of real pages), rather than assertions.
- **Catalog-awareness** — a damaged/illegible steel label (e.g. `W18X3?`) is now parsed into its actual structural fields (family, depth, weight) and matched against the real 2,299-row AISC catalog, instead of relying on whole-string fuzzy text similarity that could confuse a completely different section for a superficially similar one.
- **Spatial awareness** — an experimental search structure looks up "what's near this point on the page" by actual page position, instead of by list order.
- **Candidate lists instead of one guess** — both for damaged labels and for label-to-geometry association, the system can now produce a ranked list of plausible answers instead of committing to a single, unreviewable pick.
- **Training-data generation and review infrastructure** — a full, tested pipeline exists to generate a damaged-label training set from the AISC catalog itself, and a full human-review workflow exists for the harder association problem, though no human has reviewed anything yet.
- **A first real trained model** — a machine-learning ranker for damaged steel labels was trained and shown, on a synthetic benchmark, to give a real, statistically-significant improvement over the existing rule-based approach.

Independently, Ismail's `e36fb1b` commit added a substantial new layer: additional PDF text/table/schedule extraction, and three neural-network components (a graph neural network, an image-feature encoder, and a learned fusion model) plus new training infrastructure. This is genuine new engineering, not placeholder code. However, the audit behind this report found that **two of those three neural checkpoints load automatically in the live prediction path today, based only on "does a file exist," with no real accuracy ever measured for either of them** — the model-governance system that is supposed to gate this is present but disconnected from what actually loads. This is explained in full in Step 13/14 below and is the single most important production-safety finding in this report.

---

## Section 2 — High-Level Workflow

```
PDF
 ↓
Page / document extraction
 ↓
Text extraction
 ↓
Steel-label parsing
 ↓
Damaged-label reconstruction
 ↓
Vector geometry extraction
 ↓
Geometry filtering / classification
 ↓
Graph / spatial relationships
 ↓
Label-to-geometry candidate generation
 ↓
Association / structural understanding
 ↓
Multimodal evidence fusion
 ↓
Catalog validation
 ↓
Final steel prediction
 ↓
Takeoff / pricing / UI
 ↓
Human review / learning feedback
```

Each stage is covered in detail below, using this legend throughout:

| Tag | Meaning |
|---|---|
| **[PRODUCTION]** | Actually used by the live workflow today |
| **[LOCAL-UNCOMMITTED]** | In Bassam's current working tree, not committed to any branch |
| **[ISMAIL]** | Introduced in Ismail's `e36fb1b` commit |
| **[EXPERIMENTAL]** | Implemented and tested, deliberately disconnected from production |
| **[RESEARCH/PLANNED]** | Not yet implemented |
| **[DEPRECATED/STALE]** | Exists in the codebase but should not be considered part of the intended architecture |

---

## Section 3 — Step-by-Step Evolution

### STEP 1 — PDF INPUT AND PAGE UNDERSTANDING

**At the last UI demo:** PyMuPDF opened each PDF and extracted pages one at a time. There was basic page extraction but essentially no reusable "profile" of a page — nothing recorded how many drawing objects a page had, whether it was rotated, or what kind of sheet it was.

**What I changed [LOCAL-UNCOMMITTED]:** Added page-level diagnostics (drawing counts before/after any filtering, rotation values, which internal "cap" or "window" limits fired) and ran a full profiling pass across a real 7-project, 262-page corpus to characterize what real pages actually look like (page-type mix, vector-vs-scanned ratio, rotation).

**What Ismail added [ISMAIL]:** New, separate text/table/schedule extraction modules (`pdf_parser.py`, `token_extractor.py`, `document_intelligence.py`) that read structured tables and title-block information the original extraction path did not attempt. These do not replace or fix the existing page/geometry extraction — they run alongside it, extracting different information.

**How it works now:** Page/document extraction itself is unchanged in production. The diagnostics and profiling are local-only measurement tools, not part of the live pipeline. Ismail's new extraction modules are new committed code but were not verified as wired into the live request path during this audit's code-reading (see Step 13 for what is and isn't confirmed wired).

**Algorithm explained simply:**
- **PyMuPDF** is a library that opens a PDF file and lets code read its text, page dimensions, rotation, and vector line-work directly — used because the PDFs here are "born-digital" (created by CAD software), not scans, so this is far more reliable than image-based reading.

**Evidence / results [REAL PROJECT]:** Across all 7 projects / 262 pages: **0 extraction failures or exceptions**; **100% of pages were vector/born-digital** (0 scanned pages found in this archive); page types split as 77 structural framing plans, 64 general notes, 38 detail sheets, 25 unknown, 23 member schedules, 17 section/elevation, 9 connection schedules, 6 architectural, 3 title/cover; total extraction runtime ~114 seconds for all 262 pages.

**Problems still remaining:** No drawing-scale detection exists anywhere — every geometric threshold in the codebase (leader length, symbol size, etc.) is a fixed number of raw PDF points, not a real-world distance, so behavior can silently drift across drawings plotted at different scales. No OCR strategy exists (not needed for this corpus, since it was 100% vector, but unverified for scanned input).

**Next planned improvement:** Determine whether Ismail's new extraction modules are actually reachable from a router before relying on them; add scale detection.

---

### STEP 2 — TEXT EXTRACTION

**At the last UI demo:** Raw PDF text extraction pulled text runs directly out of the PDF's internal text objects (born-digital text, not image/OCR text) and tokenized them for downstream matching.

**What I changed:** No changes to the text-extraction mechanism itself this phase.

**What Ismail added [ISMAIL]:** A `ClassicalTextEncoder` that takes the *existing*, already-fitted text-similarity index and projects its output into a fixed-size numeric vector via a hashing trick, so it can be combined mathematically with other signals in the new fusion model. This is a wrapper around existing logic, not a new language model, despite documentation elsewhere describing it more ambitiously.

**How it works now [PRODUCTION]:** All 262 real pages audited were born-digital vector PDFs with extractable text — **OCR is not currently exercised or verified by any evidence in this repository.** If a scanned PDF were uploaded, its behavior is unverified.

**Algorithm explained simply:**
- **TF-IDF** ("Term Frequency – Inverse Document Frequency") is a numerical way of representing which words/terms are important in a piece of text — common words score low, distinctive words score high. It is used here to turn text into numbers a similarity search can compare quickly.

**Evidence / results [REAL PROJECT]:** 8,356 regex-matched steel labels were detected across 177 of 262 real pages (67.6%).

**Problems still remaining:** No verified OCR path for scanned drawings.

**Next planned improvement:** If scanned-PDF support becomes a real requirement, this needs dedicated testing — it has not been exercised on any real data audited here.

---

### STEP 3 — STEEL LABEL DETECTION / REGEX

**At the last UI demo:** A regex pattern identified strings shaped like AISC designations (family letters followed by numbers, e.g. `W18X35`). There was some wildcard-matching logic and AISC catalog lookup already present from the Initial-commit "AI-first" architecture, but no separated raw/normalized/predicted text handling, and no conservative-normalization discipline (i.e. no guarantee the system wouldn't silently guess a digit while claiming to just be "cleaning up" text).

**Algorithm explained simply:**
- **Regex** ("regular expression") is a pattern matcher that looks for text with an expected shape — here, "letters then numbers then X then more numbers" — without needing to understand what the text means.

**What I changed [LOCAL-UNCOMMITTED / part committed in `2911a8a`]:** `2911a8a` (committed, right after the demo) added conservative, formatting-only text normalization and a wildcard matcher shared by exact/normalized comparison, plus isotonic confidence calibration that only turns on with enough held-out samples (otherwise it honestly reports a ranking score rather than inventing a probability). Later, uncommitted work added a stricter separation of `raw_text` / `normalized_text` / `predicted_label` / `reason` so raw drawing text is never silently overwritten, plus family-aware parsing that recognizes AISC's actual field structure (family, depth, weight, and family-specific fields for HSS/L/2L/PIPE) rather than treating a label as an opaque string.

**What Ismail added:** "Ismail's latest commit did not materially change this stage" beyond the text-encoder wrapper described in Step 2.

**How it works now [PRODUCTION for `2911a8a`'s pieces; LOCAL-UNCOMMITTED for the family-aware parser]:** A detected label goes through conservative normalization (case/whitespace only, never guessing characters), then wildcard matching if the text contains `*`/`?`, then exact AISC catalog lookup.

**Evidence / results:** See Step 4 for the full family-aware parsing evaluation, which is really where this stage's new capability gets tested.

**Problems still remaining:** A newly-discovered edge case (found during this audit's own work, not fixed): if noise corruption happens to prepend the letter "W" onto a different family's label (e.g. an HSS or double-angle label), the family-detection step matches the single-letter "W" prefix before any smarter logic runs, misidentifying the family at the very first step.

**Next planned improvement:** Fix the family-prefix collision above; it currently defeats every downstream improvement for the (rare but real) rows it affects.

---

### STEP 4 — DAMAGED / INCOMPLETE LABEL RECONSTRUCTION

This is the largest single body of new work covered by this report, so it's presented as its own progression.

**At the last UI demo:** A damaged or partially-illegible label (smudge, torn corner, OCR error) was handled, if at all, by generic fuzzy text-similarity against the catalog — comparing whole strings by character overlap, with no concept of "this is the depth field" vs. "this is the weight field."

**The progression since then, all [LOCAL-UNCOMMITTED]:**

1. **Catalog-aware candidate generation** — a deterministic module that only ever returns real rows from the actual AISC catalog (2,299 unique labels), never an invented label, using several strategies (exact match, wildcard-position matching, OCR-confusable-character matching, family-only fallback, fuzzy nearest-neighbor).
2. **A synthetic corruption dataset built from that catalog** — every one of the 2,299 real labels was deliberately corrupted in realistic ways (see below) to create a large set of (damaged text → correct answer) training pairs, since real damaged-label examples with confirmed answers don't exist yet.
3. **"v2": a first trained ranking model** — an XGBoost model (see below) that learned to re-order the deterministic candidate list, trained on that synthetic data.
4. **"v3": family-aware structural parsing + better training data + a proper ranking model** — the field-aware parser mentioned in Step 3, richer "hard negative" training examples (candidates that are genuinely easy to confuse with the right answer, not random wrong answers), and a true learning-to-rank model instead of v2's simpler approach.

**Corruption types used to build the training set:** character deletion (torn/cut-off text), unknown-character wildcards (smudges), OCR-style character substitutions (`0↔O`, `1↔I↔L`, `5↔S`, `8↔B`, `2↔Z`, `6↔G`), separator corruption (`X` turning into a space, multiply sign, or dash), added noise (stray characters, wrapping parentheses), missing family prefix, and combinations of 2-3 of the above at once.

**Algorithm explained simply:**
- **XGBoost** is a model made of many small decision trees that vote together; it learns which candidate characteristics (how close is the spelling, does the family match, etc.) usually correspond to the correct steel label.
- **LambdaMART / learning-to-rank** — instead of judging each candidate correct-or-wrong independently, the model learns how to order ALL the candidates for one damaged label from best to worst, which is a better match for how this problem is actually used (showing a ranked list).

**Evidence / results — [SYNTHETIC benchmark, frozen test set of 2,772 corrupted examples]:**

| Method | Top-1 accuracy | MRR |
|---|---|---|
| Deterministic (rule-based) baseline | **79.33%** | 0.844 |
| v2 (first trained model) | 79.58% | 0.843 |
| v3 (structural parsing + better training data) | **81.57%** | 0.860 |

v3's improvement over both the deterministic baseline and v2 was checked with a paired statistical test and found **statistically significant** (p < 0.01 both ways) — not noise.

Candidate-generation coverage (whether the right answer is even in the list of candidates, regardless of ranking) was measured separately: **92.9% recall@20** for both v2 and v3's candidate generators — i.e. v3's improvement comes from ranking the right answer higher when it's already found, not from finding more right answers.

Family-level results were mixed: HSS, W, and WT families improved meaningfully (e.g. HSS 77.0%→80.9%); a smaller family (single angles, "L") regressed (78.5%→74.6%) and needs attention before any production use.

**The most important, non-obvious finding from this work:** whether a damaged label is even *solvable from text alone* depends entirely on how much information survives. When the surviving characters point to exactly **one** possible catalog entry, the system gets it right **99.3%** of the time. When 2-5 catalog entries are equally consistent with what's visible (e.g. `W44X3**` could be several different W44 sections), top-1 accuracy is only **45.1%** — not because the model is bad, but because the text genuinely does not contain enough information to pick one — though the right answer is in the top-5 list **97.2%** of the time. This directly motivates Step 15 below: for these genuinely ambiguous cases, only geometry/context (not more text modeling) can help.

**Problems still remaining:** All of the above is measured on **synthetic** corrupted data, not real damaged labels from real drawings — real corruption patterns are unverified. The L-family regression is unresolved. The model has not been shadow-tested against real production traffic.

**Next planned improvement:** Shadow-deploy v3 (log its predictions alongside the current system's, without changing what users see) against real traffic to see whether the synthetic-benchmark improvement holds up on real damaged labels.

---

### STEP 5 — VECTOR GEOMETRY EXTRACTION

**At the last UI demo:** PyMuPDF's `get_drawings()` extracted lines, rectangles, and curves from each page. Every extracted object got a randomly-generated ID (`uuid4()`), meaning the same drawing produced different internal IDs every time it was processed. Classification of what kind of shape each object was relied on the raw path syntax.

**What I changed [LOCAL-UNCOMMITTED]:** Replaced random IDs with deterministic ones, and added diagnostics recording how many geometry objects survive each processing step.

**Algorithm explained simply:**
- **Deterministic (SHA-based) IDs**: the same object gets the same ID every time, because the ID is calculated from the object's own stable properties (position, shape) instead of being generated randomly. This matters because without it, re-running the same PDF twice produces two different-looking outputs even though nothing structural changed — making it impossible to reliably compare runs, debug, or build a stable training/review dataset.

**What Ismail added:** "Ismail's latest commit did not materially change this stage" — his commit does not touch `geometry_extractor.py`.

**How it works now:** Production still uses random IDs; deterministic IDs exist only in Bassam's uncommitted work.

**Problems still remaining:** No semantic understanding of what a shape *is* structurally (beam vs. grid line vs. border vs. hatch vs. dimension line) — classification is purely by shape syntax and size.

**Next planned improvement:** Land deterministic IDs in production; they are a prerequisite for reliable diagnostics and any future training-data collection from geometry.

---

### STEP 6 — DENSE PAGE FILTERING

**At the last UI demo:** When a page had more than 250 extracted drawing paths, the code kept only the 250 with the largest bounding-box area — intended to keep "the important stuff" and drop clutter. This has a real logic bug: perfectly straight horizontal/vertical lines (like clean structural beam and column lines) have a bounding-box area of exactly zero, so they are the *first* things dropped, which is the opposite of the intended effect.

**What I changed [LOCAL-UNCOMMITTED, not production]:** Measured how often this actually fires on real drawings, and built an alternative, experimental sorting strategy (by line length instead of bbox area) with a side-by-side comparison diagnostic.

**Evidence / results [REAL PROJECT]:** The 250-path cap triggered on **229 of 262 real pages (87.4%)** — this is the *normal* case for this corpus, not a rare edge case. Raw per-page drawing counts ranged up to 53,146 (median 4,970).

**Problems still remaining:** **This is still a live, unfixed production bug** — the length-aware alternative exists only as an experiment; production still uses the original bbox-area sort. This report explicitly avoids implying otherwise.

**Next planned improvement:** This is the single highest-priority, lowest-risk fix identified across the whole audit: swap the sort key in production, since it is a small, well-understood, well-tested change.

---

### STEP 7 — GRAPH CONSTRUCTION

**What a "graph" is here, explained simply:** drawing objects (text and geometry) become nodes; relationships between them, such as "these two are close together" or "these two overlap," become edges connecting the nodes.

**At the last UI demo:** Relationships were discovered by comparing pairs of objects within a fixed-size window of a list — a window of about 60 objects on a page, checked in whatever order PDF extraction happened to produce, not by actual page position. Object IDs were random (see Step 5), so results weren't reproducible. The graph's shape (topology) was built, but the final prediction step didn't actually read it — only a handful of summary numbers (like "how many connections does this node have") flowed into the final decision.

**What I changed [LOCAL-UNCOMMITTED]:** Deterministic graph IDs, per-page diagnostics recording how many relationship pairs were actually compared vs. how many *should* have been compared for a full check.

**Evidence / results [REAL PROJECT]:** The 60-object window triggered on **233 of 262 real pages (89.0%)**. On the 11 pages measured in detail, the old windowed approach found on average only **~7.4% (range 1.7%-17.2%)** of the spatially-complete relationship set — i.e. roughly 92.6% of genuinely nearby object pairs on a typical dense real page were never even compared for relationships.

**Important clarification, stated explicitly per this report's own accuracy rules:** that 7.4% is a measure of *how much relationship information the old method misses*, compared to a spatially-complete search — it is **not** a measure of final prediction accuracy. It says nothing about whether any specific prediction was right or wrong; it only shows that the old method is working with a small, position-blind fraction of the information that actually exists on the page.

**Problems still remaining:** Production still uses the old windowed approach. Even where relationships are found, the graph's actual topology still doesn't reach the final prediction (only summary numbers do) — that is a separate, unresolved architectural gap this phase's work did not attempt to close.

**Next planned improvement:** See Step 8 — a spatial index is the direct fix for the coverage problem measured here.

---

### STEP 8 — STRTREE / SPATIAL CANDIDATE SEARCH **[EXPERIMENTAL]**

**Algorithm explained simply:**
- **STRtree** is a spatial index — instead of scanning a plain list to find "what's near this point," it organizes objects by where they actually sit on the page, so a nearby-object search only has to look at a small relevant region instead of the whole page. This is exactly what fixes the coverage gap measured in Step 7.

**What I changed [LOCAL-UNCOMMITTED]:** Built a spatial-index-based candidate generator that finds geometry near a label by real page position, resolves leader/arrow lines through to what they actually point at (instead of treating the leader stroke itself as a candidate), and filters out page-spanning border rectangles that would otherwise look "close" to everything due to their huge size.

**This is explicitly experimental, not production.** It exists as a separate, isolated module, exercised only by tests and the diagnostic comparison in Step 7.

**Problems still remaining:** No decision has been made on whether/when to promote this to production. It has not been evaluated against human-confirmed correct answers (see Step 9).

**Next planned improvement:** Use this as the foundation for a repaired association mechanism (Step 9), once a decision is made to promote it.

---

### STEP 9 — LABEL-TO-GEOMETRY ASSOCIATION

**At the last UI demo / current production:** a label is linked to "whichever geometry object is nearest," picked greedily and independently for each label, with no global check for conflicts (multiple labels can point at the same geometry) and no alternative candidates retained.

**Real finding [REAL PROJECT, mechanism-level, not accuracy]:** across the 11 real pilot pages, the production heuristic's own final pick was the **leader/arrow stroke itself — not a real structural member — in 243 of 843 cases (28.8%)**. This is stated carefully: it means the production mechanism is picking a leader line as its answer nearly 3 times in 10, which is a strong warning sign — but because no human has reviewed these pages yet, **this is not a confirmed error rate**. It is possible (though considered unlikely by the audit) that some of those picks were coincidentally still correct. It is a mechanism-level finding, not a ground-truth accuracy number.

**What I changed [LOCAL-UNCOMMITTED, EXPERIMENTAL]:** Built a candidate-SET generator (instead of one greedy pick) that returns a ranked top-K list of geometry candidates per label, with explicit "leader evidence" flagging, support for a label having no valid target, and support for one label plausibly pointing at more than one member.

**What Ismail added:** No association-specific logic — Ismail's commit has no discrete "association" concept; geometry linkage in his multimodal path uses whatever the (unchanged) production geometry extractor already attaches.

**Why the association model has NOT been trained yet:** training a model on the current heuristic's own picks would teach the model to reproduce the heuristic's mistakes — including the 28.8% leader-selection problem — as if they were correct answers. This would be actively harmful, not neutral. **Real human-reviewed ground truth is required before this model can be legitimately trained**, and that does not exist yet.

**Evidence / results [REAL PROJECT]:** 1,253 label-geometry groups were built across the 11 pilot pages; average 7.84 candidates per group (median 10); 3.5% of groups have no real candidate at all.

**Problems still remaining:** No human-reviewed association ground truth exists anywhere in this repository yet.

**Next planned improvement:** Get the 108-group human review batch (Step 10) actually reviewed; that is the hard blocker for any real association model work.

---

### STEP 10 — REVIEW / TRAINING DATA FOUNDATION **[EXPERIMENTAL / infrastructure only]**

**What did not exist before:** any structured way to export a label-association case for human review, collect a decision, and store it durably.

**What I built [LOCAL-UNCOMMITTED]:** A full, tested pipeline — a candidate-row/label-group data model, deterministic (byte-identical, repeatable) JSON+SVG exports for review, an append-only outcome store, a validated import path for reviewer decisions, a rebalanced 108-group review batch (no project over-represented beyond 15.7%), a 37-group (34.3%) double-review subset for measuring reviewer agreement, and a frozen project-level train/test split (`project_007` held out as the untouchable test project; the other 6 projects form a training pool using leave-one-project-out cross-validation, never a project-blind row-level split).

**Explained simply:**
- **Append-only** means old reviewer decisions are never erased or overwritten — a correction creates a new entry, so the full history stays traceable and auditable.
- **Leave-one-project-out cross-validation** means the model is trained on 6 projects and tested on the 1 left out, rotating which project is left out — done because there are only 7 projects, too few for a normal 70/15/15 split to work meaningfully.

**Status:** infrastructure is complete and tested (100% deterministic export across repeated runs, verified). **Zero groups have actually been reviewed by a human.** Real review is explicitly planned to be performed by someone external to this engineering work, not fabricated or inferred by any automated process — this is a deliberate, stated constraint, not an oversight.

**Problems still remaining:** everything downstream of real review (recall@K against real truth, error-rate analysis, validating the 28.8% leader finding against confirmed answers) is blocked until review actually happens.

**Next planned improvement:** Get the 108-group batch in front of a human reviewer.

---

### STEP 11 — ISMAIL'S GRAPHSAGE **[ISMAIL, real code, unverified accuracy]**

**Algorithm explained simply:**
- **GraphSAGE** is a graph neural network — a model that learns from an object together with the objects connected around it in a graph, rather than looking at the object in isolation.

**What it actually is:** a genuine, small (~7.1 thousand parameters) PyTorch model, trained with real backpropagation (AdamW optimizer), that predicts a structural *role* for a graph node — beam, column, brace, plate, connection, or other — plus three additional yes/no signals (consistency, missing-label, incorrect-label). **It is not a damaged-label model and does not predict AISC designations.**

**What the audit found:** genuine, trained weights exist — but **no held-out accuracy has ever been computed for this model anywhere in the repository.** The model-registry entry that is supposed to track its accuracy contains hardcoded placeholder numbers (0.5/0.6) written by a separate, disconnected part of the codebase that doesn't actually run or evaluate this model, and that registry entry is explicitly marked "not production-promoted." Despite that, the model currently **loads automatically in the live prediction path whenever its checkpoint file exists on disk** — the rejection status is not checked.

**How it could complement Bassam's work (future, not current):**
```
Bassam's work: build a reliable, spatially-correct graph (Steps 7-8)
        ↓
GraphSAGE: learn structural meaning from that graph (beam/column/brace role)
        ↓
That role information becomes a useful signal for association/ranking
```
This is a real, sensible future direction — but it depends on first having a graph GraphSAGE can trust (Steps 7-8 are still experimental), and on GraphSAGE itself being properly evaluated first.

**Current production wiring:** loads and runs on every document analysis; its output can influence the final geometry evidence. **This should be considered unverified, not proven, despite running today.**

---

### STEP 12 — ISMAIL'S MOBILENETV3 GEOMETRY ENCODER **[ISMAIL, not trained on Estima3D data]**

**Algorithm explained simply:**
- **MobileNet** is a lightweight neural network originally trained to recognize everyday photo subjects (cats, cars, etc.); here it's used only to convert an image crop into a list of numbers ("features") that can be compared for similarity — not to recognize steel shapes.

**What it actually is:** the frozen, off-the-shelf ImageNet-pretrained backbone, with no fine-tuning of any kind performed on Estima3D drawings. It is used purely for nearest-neighbor visual lookup ("find geometry crops from past documents that look similar"), not as a trained classifier of steel geometry.

**Clarification:** this is genuinely useful as a similarity-search building block, but describing it as "AI that recognizes structural members visually" would overstate it — it has never seen a labeled Estima3D example.

**Possible future value:** a visual cue contributing to geometry classification, once (if) it is actually fine-tuned on labeled Estima3D crops.

**Current limitations:** no training on domain data; no accuracy measurement of any kind exists for it in this repository.

---

### STEP 13 — MULTIMODAL FUSION

**At the last UI demo:** a fixed, manually-weighted combination of text/OCR/layout/geometry/graph/engineering-rules scores picked the final label (the "AI-first" architecture already present at Initial commit).

**What Ismail added [ISMAIL]:** a genuine, trained **Fusion MLP** (small neural network) that can override the manually-weighted result entirely when its checkpoint is present.

**Algorithm explained simply:**
- **MLP** ("multi-layer perceptron") is a small neural network that learns how much weight/importance to give different input signals when combining them into one decision — instead of a human picking fixed weights by hand.

**Audited findings:**
- Real, trained model — genuine backpropagation occurred, and it is the highest-impact of Ismail's three neural components because it can directly change the final label, not just contribute a background feature.
- Its calibration step (the part that's supposed to turn raw scores into trustworthy confidence numbers) was fit on as few as ~20 samples in some cases, well under the 50-sample minimum this codebase's own existing calibration policy requires elsewhere, and those samples were not confirmed to be independent of its training data.
- **No held-out accuracy has been computed for it**, for the same registry-disconnection reason described for GraphSAGE in Step 11.
- **It loads and can change the final prediction on every document analysis today, based only on "does the checkpoint file exist."**

**The governance issue, stated professionally:** the architecture introduces genuine learned multimodal fusion, but the current model-governance path is not yet strong enough for production trust because checkpoint existence and model approval are not fully coupled — a model can be present, unevaluated, and even explicitly marked "rejected" in its own registry, and still be the thing that decides a user's final prediction.

---

### STEP 14 — MODEL REGISTRY / TRAINING INFRASTRUCTURE

**Bassam's work [LOCAL-UNCOMMITTED]:** explicit feature flags defaulting to "off" for every new experimental package (damaged-label ranker, association dataset), full isolation from production enforced by automated tests (not just code review), versioned experiment tracking for the damaged-label work, and a conservative confidence-reporting policy that refuses to fabricate a probability below a minimum sample count.

**Ismail's work [ISMAIL]:** genuine training/registry infrastructure and real model artifacts — but, per Steps 11/13, that registry is not what actually controls which checkpoint loads in production today.

**What should be unified (proposed, not yet done):** before any checkpoint is allowed to load in a real prediction, it should require ALL of: a registry entry, a specific model version, a recorded preprocessing version, a named held-out evaluation dataset, real (not hardcoded) recorded metrics, an explicit human approval status, and a compatibility check confirming the checkpoint still matches what the current code actually feeds it. **Checkpoint file existence alone should never again be treated as production approval.**

---

### STEP 15 — ASSOCIATING DAMAGED LABELS WITH GEOMETRY (future architecture)

Step 4 found that text-only reconstruction is very strong when a damaged label's surviving characters point to exactly one catalog entry (99.3% top-1) — but weak when several entries remain equally plausible (e.g. `W44X3**` could resolve to more than one real W44 section). This is where geometry/context becomes valuable, not before.

**Possible future evidence sources for resolving remaining ambiguity:**
- which physical member a callout's leader line actually points to;
- the member's structural role (beam/column/brace), potentially from GraphSAGE once properly evaluated;
- whether the same label text repeats on what looks like the same continuous member;
- a member mark cross-referenced against a schedule table (if Ismail's schedule extraction is verified working);
- neighboring labels and general graph relationships;
- which detail/region of the drawing a label sits in.

**An important caution stated explicitly, because it is easy to get wrong:** PDF vector geometry usually does **not** encode the true physical flange depth or weight of a member — a visually thick line in the PDF is a drawing/line-weight convention, not a measurement, and should never be treated as evidence that a heavier W-section is correct. Any future geometry-based disambiguation must be built on real structural/graph relationships, not on naive visual thickness.

**Proposed future flow:**
```
Damaged text
 ↓
AISC candidate generation (Step 4)
 ↓
Text ranker (v3, Step 4)
 ↓
Ambiguity detection (is this UNIQUE, or a small/large ambiguous set?)
 ↓
Geometry association (Steps 8-9, once trustworthy)
 ↓
Graph / structural role (Step 11, once evaluated)
 ↓
Schedule / repeated-member evidence (Ismail's extraction, once verified)
 ↓
Context reranking
 ↓
Final AISC candidate
```
This is presented as the most likely point where Bassam's deterministic/ranking work and Ismail's deep-learning work converge into one system — but every box after "Text ranker" above is currently either experimental or unproven, and this flow is not built yet.

---

### STEP 16 — FINAL PREDICTION / UI

**What the UI demo showed:** raw text, a predicted label, and basic provenance, with the multimodal fusion score (present since Initial commit) already driving the final pick.

**What has changed since, and is actually visible to a user today:** `2911a8a` (committed) added a proper separation between raw text, normalized text, predicted label, and reason, plus honest confidence reporting (reports a plain score rather than fabricating a probability when not enough samples exist). Ismail's commit added new frontend components for prediction detail/explainability display, plus elapsed-time and action-button UI pieces — whether these are exercising the new backend candidate/ranking work described in this report was not confirmed during this audit.

**What is NOT yet visible to users:** none of the v2/v3 damaged-label ranker's output, none of the experimental association candidate-set work, and — critically — the current settings for the new ML components are:

```
ML_LABEL_RANKER_ENABLED = false
ML_LABEL_RANKER_SHADOW  = false
ML_ASSOCIATION_DATASET_ENABLED = false
```

verified directly from `backend/config.py` at the time of this audit. None of Bassam's new ranking/association work is switched on in any capacity, including shadow logging.

---

## Section 4 — Bassam vs. Ismail

This is a comparison of complementary responsibilities, not a competition. Bassam's work primarily strengthened deterministic correctness, measurement, candidate generation, training-data foundations, and damaged-label ranking. Ismail's work primarily introduced additional multimodal extraction and neural components for graph, visual, and fusion reasoning.

| Area | Last UI Demo | Bassam's Work | Ismail's Work | Current Status | Best Combined Direction |
|---|---|---|---|---|---|
| PDF extraction | PyMuPDF, basic page extraction | Page diagnostics, real-corpus profiling | New text/table/schedule extraction modules | Diagnostics local-only; Ismail's extraction new, wiring unconfirmed | Verify Ismail's extraction is reachable, then land alongside Bassam's geometry fixes |
| Text extraction | Born-digital text extraction | No change | TF-IDF wrapper around existing index | Production unchanged; wrapper is low-risk | Merge freely once dependency issues resolved |
| Label parsing | Regex + basic AISC lookup | Conservative normalization, wildcard matcher, family-field parsing | No material change | `2911a8a` pieces in production; field parser local-only | Land family-field parser; fix prefix-collision bug |
| Damaged labels | Fuzzy whole-string matching | Corruption dataset, v2/v3 trained rankers | None | All experimental, flags off | Shadow-test v3 on real traffic |
| Geometry extraction | Random IDs, no diagnostics | Deterministic IDs, diagnostics | No change | Local-only | Land deterministic IDs first — low risk, high value |
| Dense-page handling | Buggy 250-cap (drops straight lines first) | Measured 87.4% real trigger rate; built alternative | No change | **Bug still live in production** | Fix the sort key — smallest, highest-value fix in this audit |
| Spatial indexing | List-order windowed loop | STRtree-based experimental candidate generator | No change | Experimental only | Promote once association model needs it |
| Graph | Non-deterministic, windowed, topology unused | Deterministic IDs, coverage diagnostics (7.4% measured) | GraphSAGE consumes graph output | Graph itself still production-legacy | Fix graph first, then let GraphSAGE consume a trustworthy graph |
| Geometry semantics | None | None | None | Missing on both sides | Open item for either side |
| GraphSAGE | N/A | N/A | Real trained model, unevaluated | Loads in production unconditionally | Requires held-out evaluation before trust |
| Visual encoder | N/A | N/A | Frozen MobileNet, not domain-trained | Loads in production unconditionally | Needs domain fine-tuning + evaluation |
| Association | Single greedy nearest-pick | Candidate-set generator, leader resolution | No discrete concept | Production unchanged; candidate-set experimental | Blocked on real human review |
| Candidate ranking | N/A | v2/v3 XGBoost/XGBRanker, statistically validated | N/A | Experimental, flags off | Shadow-test, then consider promotion |
| Fusion | Fixed manual weights | No change | Learned Fusion MLP | MLP loads in production unconditionally, unevaluated | Needs the same governance checklist as GraphSAGE |
| Confidence | Basic | Honest low-sample refusal policy | Temperature-scaling calibration, thin sample | `2911a8a` policy is production; Ismail's calibration unverified | Hold Ismail's calibration to Bassam's sample-size standard |
| Training infra | Ad hoc | Feature flags, isolation tests, experiment versioning | Registry + training scripts | Two disconnected systems exist | Unify per Step 14's checklist |
| Model registry | Basic | Extended for damaged-label experiments | Extended for multimodal models | Disconnected from what actually loads | Couple registry approval to actual loading, for both sides' models |
| Evaluation | Minimal | Synthetic benchmark with statistical testing | None for DL components | Real evaluation exists only for damaged-label work | Apply the same rigor to Ismail's DL components |
| Human review | None | Full infrastructure built, unused | N/A | Infrastructure ready, zero reviews done | Get the 108-group batch reviewed |
| UI | Demo state, some legacy-record bugs | Fixed in `ef6f71b`/`2911a8a` | New prediction/explainability components | Mostly production; new components' data source unconfirmed | Confirm new UI is actually fed by the new logic before relying on it |

---

## Section 5 — What Changed in Production?

| Change | Production now? | Experimental? | Tested? | Needs validation? |
|---|---|---|---|---|
| Conservative text normalization, wildcard matcher, calibration policy | Yes (`2911a8a`) | — | Yes | No |
| Deterministic geometry/graph IDs | No | Yes | Yes | Yes — needs to actually be merged |
| Page/graph diagnostics | No | Yes | Yes | N/A — diagnostic only |
| Dense-page length-aware cap | No | Yes | Yes | Yes — a real fix to a real production bug, not yet applied |
| STRtree spatial candidate search | No | Yes | Yes | Yes |
| Damaged-label candidate dataset + v2/v3 ranker | No (flags off) | Yes | Yes (statistically validated on synthetic data) | Yes — needs real-traffic shadow validation |
| Human-review workflow / candidate dataset (association) | No (flag off) | Yes | Yes (infrastructure) | Yes — needs actual human reviews |
| XGBRanker v3 (learning-to-rank) | No (flag off) | Yes | Yes | Yes |
| GraphSAGE | **Yes, loads unconditionally** | — | Partially (code exists, no held-out accuracy) | **Yes — urgent, currently unvalidated but live** |
| MobileNetV3 encoder | **Yes, loads unconditionally** | — | No domain evaluation | **Yes — not trained on Estima3D data** |
| Learned Fusion MLP | **Yes, loads unconditionally, can override final label** | — | No held-out accuracy | **Yes — highest-impact ungoverned component** |
| Ismail's text/table/schedule extraction | Unconfirmed wiring | Possibly | Not verified in this audit | Yes |
| Model registry (both sides) | Partially — tracks some things, not authoritative for what loads | — | Partially | Yes — needs unification |
| Association candidate ranking | No | Yes | Yes (mechanism-level) | Yes — needs real ground truth |

**The single most important line in this table:** GraphSAGE, the MobileNet encoder, and the Fusion MLP are all marked "production, loads unconditionally" despite none of them having a real, held-out accuracy number anywhere in the repository. This is stated as clearly as possible so it cannot be misread as "these are safe because they're experimental" — they are not experimental in terms of what actually runs; they are unevaluated in terms of what should be trusted.

---

## Section 6 — Results / Numbers

**REAL PROJECT (7 projects, 262 pages, all born-digital vector PDFs):**
- 0 extraction failures.
- Dense-page (250-drawing) cap triggered on 229/262 pages (**87.4%**).
- 60-object graph window triggered on 233/262 pages (**89.0%**).
- Old windowed relationship search recovered on average **~7.4%** (range 1.7%-17.2%) of the spatially-complete relationship set, on the 11 pages directly measured — a coverage/mechanism finding, not an accuracy finding.
- Production association mechanism selected a leader stroke itself (not a real member) as its final pick in **243/843 (28.8%)** of heuristic-selected label groups — a mechanism-level finding pending human review, not a confirmed error rate.
- 8,356 regex-matched labels detected across 177/262 pages (67.6%).
- 1,253 label-geometry groups built across the 11 pilot pages.
- 108-group human review batch built; 37 groups (34.3%) selected for double review; **zero groups reviewed to date.**

**SYNTHETIC (damaged-label reconstruction, AISC v16 catalog, 2,299 unique labels, frozen test set of 2,772 corrupted examples):**
- Deterministic baseline: Top-1 79.33%, MRR 0.844.
- v2 (first trained model): Top-1 79.58%, MRR 0.843.
- v3 (structural parsing + better training + true ranking model): Top-1 **81.57%**, MRR 0.860 — statistically significant improvement over both prior methods (paired test, p < 0.01).
- Candidate recall@20 (right answer somewhere in the list): 92.9% for both v2 and v3's generators.
- UNIQUE queries (only one catalog entry structurally possible): 99.3% Top-1.
- SMALL_AMBIGUOUS_SET queries (2-5 equally-possible entries): 45.1% Top-1, but 97.2% Top-5.
- HSS/W/WT families improved with v3; the single-angle ("L") family regressed (78.5%→74.6%) and is unresolved.

**TESTING (backend, current working tree, at time of this audit):** 264 tests passed; 3 pre-existing failures, confirmed unrelated to any of this session's or prior sessions' changes (they predate all local work and trace to the shared Initial commit).

---

## Section 7 — What Is Still Missing

### Deterministic / geometry
- The dense-page cap bug is still live in production (fix exists only as an experiment).
- No drawing-scale detection exists anywhere.
- No semantic geometry classification (beam/grid/border/dimension/hatch).
- No decision has been made on promoting the STRtree spatial index to production.

### Association
- No real human-reviewed association ground truth exists.
- No confirmed association accuracy number exists — the 28.8% figure is a mechanism finding, not an accuracy finding.
- No one-to-many label-to-member handling in production.
- No handling of "repeated/typical" callout semantics (the same label legitimately appearing on multiple identical members).
- No globally-optimal (conflict-free) assignment — the production heuristic can point multiple labels at the same geometry with no check.

### Damaged labels
- Candidate recall is capped at ~92.9% — roughly 1 in 14 damaged labels never gets the right answer generated at all, regardless of ranking quality.
- The L-family regression is unresolved.
- No production shadow validation has been run yet.
- Real corruption-pattern distribution (vs. the synthetic one used to train/test) is unverified.
- No geometry-context reranking exists for genuinely ambiguous cases (Step 15 is a proposal, not a build).

### Deep learning
- No held-out evaluation exists for GraphSAGE.
- No Estima3D-specific (domain) training exists for the visual encoder.
- No held-out evaluation exists for the learned fusion model.
- Checkpoint loading is not gated by approval status for any of the three.
- The model registry used for damaged-label work and the one used for the multimodal components are disconnected from each other and, for the multimodal side, disconnected from what actually loads.

### Confidence
- Ismail's fusion-model calibration does not yet meet the sample-size/independence standard already established elsewhere in this codebase.
- No uncertainty reporting exists for ambiguous damaged labels beyond the raw candidate-count signal described in Step 4.

### Integration
- `origin/main` (Ismail's commit) is not merged, and this audit does not recommend merging it yet.
- A dependency pin in Ismail's `requirements.txt` (`xgboost==3.3.0`) has no available wheel for Windows/Python 3.11 on this machine — a real, reproducible install failure, not a theoretical concern.
- The numpy/scipy version downgrade required by Ismail's `torch` pin is repository-wide, not scoped to his new code, and would affect every existing component that depends on numpy/scipy.
- Large model/data artifacts (tens of megabytes each, some duplicated 2-3 times) were committed directly into git history in Ismail's commit.
- No selective-merge has been performed; a plan exists (`docs/ml_integration/partner_vs_local_comparison.md` §5) but has not been executed.

---

## Section 8 — Recommended Combined Architecture

```
PDF
 ↓
Deterministic extraction                              [NOW: partially production, partially local fix]
 ↓
Raw text + vector geometry + tables/schedules          [NOW: text/geometry production; tables/schedules NEXT — verify Ismail's wiring]
 ↓
Steel label parser                                     [NOW: production for basics; family-field parsing NEXT]
 ↓
Catalog-constrained damaged-label candidates            [NEXT: shadow-test v3]
 ↓
LambdaMART text ranking                                [NEXT: shadow-test v3]
 ↓
Geometry candidate generation using spatial index       [FUTURE: promote STRtree once trusted]
 ↓
Graph construction                                     [NEXT: land deterministic IDs + fix dense-page cap]
 ↓
GraphSAGE / geometry-role classifier                    [FUTURE: requires real evaluation first]
 ↓
Label ↔ member association                             [FUTURE: blocked on real human review]
 ↓
Schedule / repeated-member / region context              [FUTURE: depends on Ismail's extraction being verified]
 ↓
Multimodal candidate reranking                          [FUTURE: depends on fusion model governance]
 ↓
AISC catalog validation                                 [NOW: already production]
 ↓
Calibrated confidence                                   [NOW: honest-refusal policy production; full calibration FUTURE]
 ↓
High confidence → automatic
Low confidence → review                                 [FUTURE: not built]
 ↓
Takeoff / pricing / UI                                  [NOW: production]
```

---

## Section 9 — Prioritized Roadmap

**P0 — Safely integrate only justified parts of Ismail's commit.**
*Problem:* 177 files, mixed value, real dependency/artifact problems. *Why it matters:* blocks everyone from building on a stable shared base. *Proposed solution:* selective port per `partner_vs_local_comparison.md` §5 — extraction code first, DL components last and flagged off. *Data needed:* none. *Success metric:* clean `pip install` on both platforms; no duplicate artifacts. *Human labels required:* no.

**P1 — Real shadow evaluation of the v3 damaged-label ranker.**
*Problem:* only synthetic-benchmark evidence exists. *Why it matters:* the 81.57% number means nothing for production until checked against real traffic. *Proposed solution:* enable `ML_LABEL_RANKER_SHADOW`, log disagreement vs. current system, review a sample. *Data needed:* real production traffic. *Success metric:* shadow accuracy consistent with synthetic benchmark, or a clear explanation of why not. *Human labels required:* for spot-checking, yes.

**P2 — Fix L-family regression, prefix-collision bug, and candidate-recall ceiling.**
*Problem:* three known, specific weaknesses in the damaged-label work. *Why it matters:* each has a concrete, traceable cause. *Proposed solution:* per-issue targeted fixes (documented in the audit that produced this report). *Data needed:* none beyond existing synthetic set. *Success metric:* L-family parity with other families; recall@20 above 92.9%. *Human labels required:* no.

**P3 — Fix the deterministic geometry/graph bottlenecks.**
*Problem:* dense-page cap bug and windowed relationship search are both live production issues with measured real-world trigger rates above 85%. *Why it matters:* highest-confidence, lowest-risk fix in this entire audit. *Proposed solution:* land deterministic IDs, fix the cap's sort key, evaluate promoting STRtree. *Data needed:* none. *Success metric:* cap no longer drops straight structural lines first; relationship coverage measurably improves. *Human labels required:* no.

**P4 — Obtain trustworthy association labels.**
*Problem:* no real ground truth exists; current heuristic cannot be trusted as a proxy. *Why it matters:* blocks all real association-model work. *Proposed solution:* get the 108-group batch reviewed by the designated external reviewer. *Data needed:* human review time. *Success metric:* at least the 37-group double-review subset completed, inter-rater agreement measurable. *Human labels required:* yes — this is the entire point.

**P5 — Evaluate GraphSAGE on real structural-role targets.**
*Problem:* zero held-out accuracy exists today despite the model running in production. *Why it matters:* production safety. *Proposed solution:* build a proper held-out, document-grouped evaluation set; compute real accuracy; gate loading on approval. *Data needed:* labeled structural-role examples. *Success metric:* a real accuracy number exists and is either good enough to keep running, or the model is gated off. *Human labels required:* likely yes, for role ground truth.

**P6 — Combine text ambiguity with geometry/graph/schedule context.**
*Problem:* Step 15's proposed flow does not exist yet. *Why it matters:* this is the one place text-only reconstruction is proven to hit a hard ceiling (45.1% on ambiguous cases). *Proposed solution:* build the reranking flow once P3-P5 are trustworthy. *Data needed:* everything above. *Success metric:* SMALL_AMBIGUOUS_SET top-1 measurably improves beyond 45.1%. *Human labels required:* eventually, for validation.

**P7 — Evaluate the learned multimodal fusion model.**
*Problem:* same governance gap as GraphSAGE, higher impact since it can override the final label. *Why it matters:* currently the least-checked, most-powerful component in the live system. *Proposed solution:* apply the governance checklist from Step 14. *Data needed:* independent, document-grouped held-out set. *Success metric:* real accuracy number; gated loading. *Human labels required:* yes.

**P8 — Calibrated confidence / production promotion.**
*Problem:* even a good ranker needs honest confidence to safely automate low-risk cases and route hard ones to review. *Why it matters:* this is the actual point of all the above — not just better predictions, but predictions the system knows when to trust. *Proposed solution:* extend the existing sample-size-honest calibration policy to every promoted component. *Data needed:* enough reviewed examples per component. *Success metric:* a defined automatic-vs-review threshold with measured precision at that threshold. *Human labels required:* yes.

---

## Section 10 — Supervisor-Friendly Conclusion

1. **What was the system doing at the last demo?** Extracting text and geometry from PDFs, finding steel-label-shaped text with a pattern matcher, loosely connecting labels to nearby drawing objects, and combining several signals with fixed weights to pick one final answer — with the AISC catalog only checking that answer, never choosing it.

2. **What did we improve since then?** Mostly the *foundations* for the next version: reproducible IDs, real measurements of known bugs on real drawings, catalog-aware damaged-label handling, a first trained ranking model with a statistically real improvement, and a complete (if not-yet-used) human-review pipeline.

3. **What has Bassam contributed?** Deterministic correctness and measurement (Steps 1, 5-8), the entire damaged-label reconstruction line of work (Step 4), the association candidate-set experiment and its review infrastructure (Steps 9-10), and production-safety discipline (feature flags, isolation tests, honest confidence reporting).

4. **What has Ismail contributed?** Additional PDF extraction breadth, and three real neural-network components — a graph model, a visual encoder, and a learned fusion model — plus training/registry infrastructure for them.

5. **What is actually running today?** The demo-era pipeline, plus Bassam's `2911a8a` normalization/calibration work, **plus, concerningly, two of Ismail's three neural components (GraphSAGE and the fusion MLP) already load and can influence predictions automatically, without ever having been measured for accuracy.**

6. **What have we learned from real projects?** Two known deterministic bugs (the dense-page cap and the association leader-selection issue) are not edge cases — they fire on the large majority of real pages (87.4% and, differently measured, a 28.8% mechanism rate respectively).

7. **Where has ML actually improved accuracy?** Only in one place, and only on synthetic data so far: the v3 damaged-label ranker, which showed a real, statistically significant improvement (79.33% → 81.57% top-1) over the rule-based approach.

8. **Where is deep learning still unproven?** GraphSAGE, the visual encoder, and the fusion MLP — all real code, none with a real accuracy number, two of the three already influencing production predictions today.

9. **What is the main blocker?** Two, at different layers: (a) no human has reviewed any association example yet, which blocks the entire association-model line of work; (b) the model-governance gap means production is currently trusting unevaluated models by default rather than by decision.

10. **What are the next 3 concrete actions?** (1) Fix the dense-page cap sort key — small, safe, high-value. (2) Shadow-test the v3 damaged-label ranker against real traffic. (3) Gate GraphSAGE and the fusion MLP behind the same approval checklist damaged-label work already follows, so production stops trusting unevaluated models by default.
