# Human Review Protocol (Phase 2.6)

Operational instructions for reviewing the 108-group real-project batch (`human_review_batch_manifest.json`) using the local, offline review kit. This document covers **mechanics** — how to run the tool, what to click, how to submit. For **what to decide** (which `review_label`/`callout_scope` value applies to a given candidate), see `annotation_guidelines.md`; this document does not repeat those rules.

**Scope note**: this protocol governs review of real, confidential project drawings. Everything below runs entirely on the reviewer's local machine — no network calls, no uploads, no server.

## Who can review

Anyone with enough structural-drawing literacy to read a framing plan and identify which line is a beam/column/brace vs. a grid line, dimension, or leader — the review kit surfaces the raw drawing and label but makes no engineering judgment for the reviewer. Per this phase's top-level constraint, **no structural ground truth may be inferred or fabricated by an AI assistant**; every one of the 108 (and the double-reviewed subset within it) must be a genuine human decision.

## 1. Build (or rebuild) the review kit

```
cd backend
python scripts/build_ml_association_review_kit.py
```

Reads the JSON+SVG exports already produced under the git-ignored `training/ml_association/real_project_pilot/exports/` directory and writes one static HTML page per label group, plus `index.html`, into the git-ignored `training/ml_association/real_project_pilot/review_kit/` directory. Re-running this script is always safe — output filenames are derived from the deterministic `group_id`, so it overwrites in place rather than accumulating stale copies.

## 2. Open the kit

Open `training/ml_association/real_project_pilot/review_kit/index.html` directly in a browser (`file://` — no server needed). The index lists all 108 groups with project, page, raw label text, candidate count, and whether leader evidence is present, each linking to its own review page.

## 3. Review one group

Each group page shows:
- The page-local SVG crop: the label (blue box), every real candidate (green boxes, numbered), and — where leader evidence exists — a dashed line approximating the leader path (violet).
- **Candidates are shown in a randomized, hash-based order, not production rank order.** This is deliberate: the order carries no signal about what the current heuristic picked, so it cannot bias your decision.
- A form: pick a `review_label` for the group's overall decision, check which candidate(s) (if any) are the real target(s), pick a `callout_scope`, optionally flag `candidate_generation_miss` and type an external geometry ID, and add free-text notes.
- A **"Reveal current system's pick"** button. It is collapsed by default and must be clicked explicitly. **Decide first, reveal second.** Revealing before deciding defeats the purpose of the randomized ordering (bias reduction against anchoring on the current, known-imperfect heuristic — see `real_project_pilot_results.md`'s 28.8% leader-mis-selection finding, which is exactly the kind of bias this ordering exists to avoid re-introducing into human judgment).
- Enter your reviewer ID (a stable identifier — e.g. a first name or initials — consistent across your own sessions; used only to identify the double-review subset and never leaves your machine) and click **"Save decision"**. This downloads one `<group_id>.decision.json` file — pure client-side JavaScript, no network request.

## 4. Collect decision files

Move (or point your browser's download folder at) every downloaded `*.decision.json` file into one local input folder, e.g.:
```
training/ml_association/real_project_pilot/working_notes/decisions/
```
(already covered by the `.gitignore` block for `real_project_pilot/`).

## 5. Import

```
cd backend
ML_ASSOCIATION_DATASET_ENABLED=true python scripts/import_review_decisions.py \
    --decisions-dir training/ml_association/real_project_pilot/working_notes/decisions
```

Each file is validated against the matching group export (`services/ml_association/validation.py` — the same strict rules documented in `schema.md`'s "Reject an imported review when..." list) and, if valid, appended to `training/ml_association/real_project_pilot/working_notes/outcomes.jsonl` via the normal `service.submit_review` path. The script prints `[OK]`/`[FAIL]`/`[SKIP]` per file and exits non-zero if anything was rejected — check stderr for the exact `ValidationErrorCode` and fix-and-resubmit rather than editing the JSONL by hand (it is append-only by design; see `outcome_store.py`).

A rejected decision is never silently dropped — re-run the import after fixing the offending field; a corrected resubmission with a new `reviewed_at` is accepted as a fresh outcome (or, to formally supersede a specific prior mistake, set `supersedes_outcome_id`; the review kit's UI does not currently expose this field, so a correction after the fact requires hand-editing the downloaded JSON before re-import).

**Known limitation**: the importer does not cross-check `candidate_generation_miss=true` corrections against a full page-level geometry index (none exists in this phase — only each group's own top-K candidate set is available). Such corrections are accepted at face value. This does not affect ordinary `direct_target`/`not_target`/`no_valid_target` decisions, which are always checked against the real exported candidate set.

## 6. Double review

A subset of groups (selection rule and list: `double_review_subset.md`) is reviewed independently by two different reviewers. Review that subset **without** looking at the first reviewer's notes or decision file — the point is an independent second judgment, not a check of the first reviewer's arithmetic. Both reviewers' outcomes are retained (distinct `outcome_id`s, since `outcome_id` is derived from `(group_id, reviewer_id, reviewed_at)` — see `identifiers.py`); neither supersedes the other. Agreement/disagreement is computed afterward from `outcome_store.history_for_group()`, not decided by either reviewer in the moment.

## 7. Session hygiene

- No fixed time limit per group — reviewing real structural drawings carefully takes as long as it takes. If a group is genuinely ambiguous, use `ambiguous_requires_adjudication` (`annotation_guidelines.md`) rather than guessing to finish faster.
- It's fine to review in multiple sessions; decision files simply accumulate in the decisions folder until imported.
- Do not rename or hand-edit a `*.decision.json` file's `group_id`, `project_id`, `document_id`, or `page_id` fields — those are cross-checked against the immutable export and any mismatch is rejected (`ValidationErrorCode.PROJECT_MISMATCH` etc.).

## Confidentiality (carried over from Phase 2.5's pilot guardrails)

- Everything under `training/ml_association/real_project_pilot/` (exports, review kit, decisions, outcomes) is git-ignored — verified with `git check-ignore -v` before this phase's data was ever written there. Never `git add -f` anything under that tree.
- Do not copy SVGs, decision files, or outcome JSONL out of the repository (e.g. into chat, email, or a shared drive) without separately clearing that with the project owner — the drawings are real customer content, sanitized only at the `project_id` level (`project_001`...`project_007`), not de-identified in their visual content.
- Reviewer IDs should be short and non-identifying-beyond-necessary (a first name or initials, not a full name/email) since they land in the outcome JSONL.
