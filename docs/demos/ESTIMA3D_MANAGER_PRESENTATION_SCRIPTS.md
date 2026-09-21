# Estima3D Manager Presentation Scripts

Spoken scripts for a live manager demo. Keep claims aligned with current product behavior only.

Related reference: `docs/demos/ESTIMA3D_MANAGER_DEMO_FLOW.md`

---

## Part 1 — What Estima3D Is

**What I say:**

"Estima3D sits in front of our existing takeoff and geometry workflow.

Structural PDFs are messy. Labels get damaged in extraction. Some angles are incomplete. Notation is inconsistent. If that bad text goes straight into takeoff, the output is not trustworthy.

Estima3D’s job is to turn imperfect structural PDFs into cleaner, trusted semantic information — extract the text, interpret it, surface risk, and apply only human-approved corrections.

It does not replace the downstream takeoff or geometry system. It prepares better inputs so that system can work from information we trust."

---

## Part 2 — Upload

**What I say:**

"The user starts by uploading the structural PDF.

That upload becomes the source document, and we keep the original file unchanged. Estima3D works from that source.

Later corrections never overwrite it. They create a separate corrected PDF — a derived document."

---

## Part 3 — Extraction

**What I say:**

"Next is Extraction.

The system pulls text out of the PDF and keeps page and position information — including bounding boxes — so we know where each label sits on the drawing.

That location matters. On structural drawings, the same-looking text in the wrong place is the wrong member.

Extraction is the raw input layer. It is not yet the final engineering interpretation."

---

## Part 4 — Analyse

**What I say:**

"Analyse is where Estima3D interprets what was extracted.

It normalizes representation where that is safe. It detects damaged or incomplete labels. Where there is drawing-backed evidence, it can propose a repair. And when the information is not good enough, it abstains and sends the item for review instead of guessing.

A simple example: if the drawing only shows L4X4, Analyse does not invent a thickness just because a thicker size exists in a steel catalog."

---

## Part 5 — The Four Semantic Operations

**What I say:**

"We talk about four semantic operations.

**Normalization** — same steel designation, written more cleanly. For example, fixing case or separators without changing the member.

**Repair** — the original text looks corrupted, and the system proposes a valid structural designation for human approval.

**Completion** — a missing part is filled only when drawing-backed evidence allows it. Catalog presence alone is not enough.

**Association** — linking a label to nearby geometry or context as supporting evidence. That is evidence, not inventing a size."

---

## Part 6 — Safety / Why We Do Not Invent Information

**What I say:**

"This part matters for trust.

Estima3D is intentionally conservative. Knowing that a size exists in the AISC catalog is not enough to invent missing drawing information.

So L4X4 must not automatically become L4X4X1/4. If the thickness is not supported by the drawing evidence, we leave it incomplete and send it for review.

When the system is uncertain, it can abstain. For structural takeoff, inventing a member size is worse than asking a person to decide."

---

## Part 7 — Results

**What I say:**

"Results is the clean, takeoff-oriented output view.

It shows the structural results the system produced — sections, confidence, validation status.

Correction queues and debugging stay off this page on purpose. That keeps the main workflow simple: Results for the numbers, Semantic Review for trust and corrections."

---

## Part 8 — Semantic Review

**What I say:**

"Semantic Review is where uncertain, damaged, or correctable annotations are handled.

For each item, the reviewer can see the original text, the detected or effective text, the issue, any suggestion the backend already has, and the current status.

This is the human review layer. Normal Results stay clean; review work happens here."

---

## Part 9 — Accept / Reject / Manual Edit

**What I say:**

"There are three review actions.

**Accept** approves the proposed correction and applies it.

**Reject** keeps that correction from being applied.

**Manual Edit** lets the user type the correct text, then explicitly Accept it. The edit stays draft until Accept.

Nothing changes silently. Engineering information only moves when a person approves it."

---

## Part 10 — Corrected PDF

**What I say:**

"When a correction is accepted, we persist it and generate an actual corrected PDF.

That PDF is a derived artifact: original PDF plus approved text corrections. The original upload stays byte-for-byte unchanged.

The user can review and download the corrected PDF. This is not just a UI overlay — the file itself is rewritten in the annotation regions that were approved."

---

## Part 11 — Engineering Formatting

**What I say:**

"On write, corrected labels are formatted for engineering notation where applicable.

For example, a complete angle like L4X4X0.375 can be written as L4X4X3/8.

We also adjust placement so the replacement text fits the original drawing area, instead of dropping a fixed oversized blank over the sheet."

---

## Part 12 — Accept All

**What I say:**

"Accept All is for when several corrections are already eligible and the reviewer wants to approve them in one step.

The backend checks eligibility, skips items that are already accepted, rejected, or unsafe, persists each acceptance with history, and regenerates one corrected PDF.

Important for this demo: Accept All will accept every item the backend currently marks eligible. On large damage-test corpora, some repair candidates can attach to non-member note text. For a manager demo, prefer targeted Accept on known structural cases, or review the eligible queue before Accept All. Tightening that eligibility further is still an open safety improvement — not fully closed."

---

## Part 13 — History / Traceability

**What I say:**

"Every Accept, Reject, and Manual Edit is recorded.

We can track original text, corrected text, and the review action. That gives us an auditable correction workflow, while the original source PDF remains preserved."

---

## Part 14 — End-to-End Flow

**What I say:**

"Putting it together:

We upload the structural PDF.
We extract the text with page and position.
We analyse it — normalize, detect damage, propose repairs only when evidence allows, and abstain when it does not.
Results shows the clean takeoff-oriented output.
Semantic Review handles the uncertain items.
A person Accepts, Rejects, or Manual Edits.
Accepted corrections produce a real corrected PDF, without changing the original.
That cleaner semantic output is what can feed the downstream takeoff and geometry workflow.

Estima3D prepares trusted drawing semantics. The existing takeoff and geometry system still does the quantity and geometry work."

---

## Part 15 — Live Demo Script

Use a known semantic-damage test PDF when possible (for example Burrville or ST damage-test documents from the validation set). Prefer **targeted Accept** unless you have already reviewed the Accept All queue.

### Step 1 — Upload a real test PDF

**What I say:**
"I’ll upload a real structural test PDF. This becomes the source document."

**What I show:**
"Upload page / document registered. Note that we have not overwritten anything yet."

### Step 2 — Show Extraction

**What I say:**
"Extraction pulls the text and keeps where it sits on the page."

**What I show:**
"Extraction step completed for the document."

### Step 3 — Run Analyse

**What I say:**
"Analyse interprets the extracted text — normalization, damage detection, and safe proposals only."

**What I show:**
"Analyse running, then complete."

### Step 4 — Show clean Results

**What I say:**
"Results stays clean. This is the takeoff-oriented view, not the correction queue."

**What I show:**
"Results page — structural results table, no Accept / Reject panel."

### Step 5 — Open Semantic Review

**What I say:**
"Corrections live here, in Semantic Review."

**What I show:**
"Navigate to Semantic Review for the same document."

### Step 6 — Show a damaged / correctable label

**What I say:**
"Here is a damaged or correctable annotation on the drawing."

**What I show:**
"Select one known structural damage case. Point to original text and issue."

### Step 7 — Explain the suggested correction

**What I say:**
"The system is suggesting a correction only when the backend already has a candidate. We are not inventing one in the UI."

**What I show:**
"Original value, detected / effective value, issue, and suggestion if present."

### Step 8 — Accept one correction

**What I say:**
"I Accept this one. That is the human approval step."

**What I show:**
"Click Accept. Status updates. Save confirmation."

### Step 9 — Show that the actual corrected PDF updates

**What I say:**
"The corrected PDF regenerates. This is a real derived PDF, not just highlighting in the browser."

**What I show:**
"Viewer refresh / revision update, and optionally Download corrected PDF. Point to the rewritten label."

### Step 10 — Show that the original PDF remains unchanged

**What I say:**
"The original upload is still unchanged. Corrections only live in the derived file."

**What I show:**
"State clearly: original source preserved; corrected PDF is separate."

### Step 11 — Accept All (optional / careful)

**What I say:**
"Accept All can approve every currently eligible repair in one action and rebuild one PDF. On this corpus, I only use it after checking eligibility — some candidates may not be structural member labels."

**What I show:**
"Either skip, or briefly show Accept All after reviewing eligible items. Do not present broad eligibility as fully solved."

### Step 12 — Show correction history

**What I say:**
"The Accept is recorded in history, so we can audit what changed."

**What I show:**
"Correction history panel — Accept / Reject / Manual Edit events."

### Step 13 — Close to downstream workflow

**What I say:**
"From here, the cleaned semantic output and corrected PDF are what we can hand to the existing takeoff and geometry workflow. Estima3D prepared trusted inputs; it did not replace that downstream system."

**What I show:**
"Corrected PDF available; Results remain the clean takeoff-oriented view."

---

## Part 16 — Manager Q&A

### What problem are we solving?

Structural PDFs often contain damaged, incomplete, or inconsistently written steel labels. If we feed that straight into takeoff, we get unreliable results. Estima3D cleans and validates drawing semantics before the existing takeoff and geometry work continues.

### Why not just use the PDF directly?

Because extraction and OCR do not give takeoff-safe engineering text by themselves. Location, damage, incomplete angles, and notation issues all matter. We need interpretation, safety gates, and human approval on corrections.

### Why do we need Semantic Review?

Results is for clean takeoff-oriented output. Semantic Review is where uncertain or damaged items are reviewed without cluttering that main view. It is the trust and correction layer.

### Why don't we automatically fill missing dimensions?

Catalog existence is not drawing evidence. Completing L4X4 to L4X4X1/4 without support from the drawing would invent a member size. When evidence is insufficient, we abstain and ask for review.

### Is the original PDF changed?

No. The uploaded original remains immutable. Corrections produce a separate derived corrected PDF.

### Is the corrected PDF real or just a visual overlay?

It is a real derived PDF generated from the original plus accepted text corrections. The reviewer can download it. Viewer overlays may help inspection, but the authoritative proof is the corrected PDF file.

### What happens when the system is uncertain?

It can abstain and send the item to Semantic Review instead of guessing. Prefer review over inventing structural information.

### Where does the existing takeoff / geometry workflow fit?

After Estima3D. Estima3D prepares trusted semantic information and a corrected PDF. The existing takeoff and geometry pipeline still consumes that cleaner input for quantity and geometry work.

### Are we using ML / VLM here?

Production inference stays on the existing orchestrated prediction path. This demo is not presenting VLM or alternate model shortcuts as part of the validated Semantic Review correction flow. Excel and AISC are used to verify, not to invent missing sizes.

### How do we validate corrections?

Backend and API tests cover formatting, Accept, Accept All behavior, original-hash immutability, and corrected PDF generation. Burrville and ST damage corpora were run through controlled API validation. Frontend unit tests cover Semantic Review Accept / Accept All. Full browser click-through E2E is not fully verified.

### What is currently verified versus still pending?

Verified in controlled API and unit testing: original PDF immutability, corrected PDF generation, fraction formatting, Accept / Accept All persistence and history, and clean Results separation. Not fully verified: full browser E2E click-through, and spacing measured separately on Burrville / ST. Accept All eligibility is still broader than ideal on large damage corpora.

---

## Final Section — Current Validation Status

Based on `docs/demos/ESTIMA3D_MANAGER_DEMO_FLOW.md` and `backend/training/eval_cache_backups/final_demo_validation_report.json`.

| Area | Current Status | Evidence | Limitation |
|------|----------------|----------|------------|
| Angle grammar + `L4X4X0.375` → `L4X4X3/8` formatting | Verified | pytest: normalization + corrected PDF tests (27 passed) | Applies to complete designations with valid third-dimension decimals; incomplete `L4X4` is not completed by the formatter |
| Incomplete `L4X4` not auto-completed | Verified | pytest + controlled live PDF | Completion still requires drawing-backed evidence; catalog alone does not complete |
| Accept writes real corrected PDF; original hash unchanged | Verified | pytest + Burrville / ST / controlled API runs | Browser viewer click-through not fully verified |
| Accept All: one PDF, skips rejected, per-annotation history | Verified | pytest + controlled API (`HTTP 200` on Burrville / ST) | Eligibility can be broad; repair candidates may attach to non-member note text on damage corpora |
| Placement uses measured text width | Verified | pytest + controlled live spacing check (W18X40 vs neighbor overlap 0) | Spacing not separately measured on Burrville / ST sheets |
| Burrville API flow (Upload → Extract → Analyse → Semantic → Accept / Accept All → corrected PDF) | Verified (API) | `doc_06009aaef05256fa`; validation report + manager demo flow | Not full browser E2E |
| ST API flow (same sequence) | Verified (API) | `doc_4a167ac3d049e172`; validation report + manager demo flow | Not full browser E2E |
| Fraction text in corrected PDF (`HSS…3/8`, `L4X4X3/8`) | Verified | PDF text extract on Burrville / ST / controlled docs | Visual eyeball spacing in browser UI not verified |
| Original PDF immutable (hash) | Verified | API original hash matches source on Burrville / ST / controlled | — |
| Results page kept clean (no correction panel) | Verified (code) | `ResultsCorrectionsPanel` removed; ResultsBody clean; frontend unit coverage | Behavioral confirmation is code / unit-test based |
| Semantic Review Accept / Accept All UI unit tests | Verified | 34 vitest passed (`semanticContract` + `SemanticReviewPage`) | Not a substitute for full browser E2E |
| Controlled synthetic fraction / spacing PDF | Verified | `doc_cda64ab70c6b1dfd`; offline PNG under eval cache backups | Offline render, not browser |
| Full browser E2E (Upload → click Accept in UI) | Not fully verified | Explicitly marked not verified in manager demo flow | Do not present as completed |
| Burrville / ST visual spacing in UI | Not fully verified | Not separately measured on those corpora | Controlled synthetic spacing only |
| Accept All eligibility tightening | Pending / known limitation | Demo caution in manager demo flow; sample Accept All history includes some non-member note text on damage corpora | Prefer targeted Accept in live manager demos |

---

## Optional speaking note — What the LLM does here

**What I say:**

"In this project, the LLM is not the engine that decides steel sizes or silently corrects member labels. Prediction, normalization, repair proposals, abstention, and Semantic Review still follow our deterministic engineering and prediction path, with humans approving corrections. Where an LLM is used, it is optional and bounded: mainly to help polish a Drawing Summary from evidence we already extracted, and optionally to propose project drawing-language rules from legend/context text. Those outputs are grounded and re-checked against the evidence — the model is not allowed to invent families, sections, or quantities, and it does not change the original PDF or takeoff numbers by itself."

---

## Presenter notes

- Prefer targeted **Accept** on known structural damage cases for the live demo.
- Say “API-validated” or “unit-tested,” not “full browser E2E validated,” unless that changes.
- Do not claim Estima3D replaces GHX / geometry / takeoff.
- Do not claim VLM shortcuts as part of this validated demo path.
- If asked about Accept All breadth, acknowledge the known eligibility limitation instead of overselling it.
