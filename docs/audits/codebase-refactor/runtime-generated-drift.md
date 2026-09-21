# Runtime-Generated Training-File Drift

This report classifies working-tree changes that existed **before** this task began and are **unrelated** to
the codebase-refactor audit. They were caused by a backend dev server (`uvicorn app:app`) that was started in
an earlier session turn (to let the user test the UI) and left running for several minutes before being
stopped. **Nothing in this report was staged, reverted, deleted, or modified as part of producing it.** No
private document content is reproduced below — only structural metadata (field names, counts, timestamps).

## Root-cause timeline

All drift-file modification timestamps fall in a single ~2.5-minute window: **2026-09-18 14:42:29 →
14:44:57** (local time; the dev server was started and later stopped within that same session turn). No
process for this repository is currently running — confirmed via process list (only two unrelated Serena MCP
server processes matched the repo path, neither touches `backend/training/`) and via port check (nothing
listening on 8000/5173). The drift is **historical, one-time, and not ongoing** — 3 days old as of this task.

`backend/training/upload_log.csv` (append-only) recorded exactly two processing events in that window:

```
a5ae21ca-...,Burrville ES - ST.pdf,29,864,863,1,0,2026-09-18T11:42:29Z
8b7a9b0c-...,burrville_SEMANTIC_DAMAGE_TEST.pdf,29,863,862,1,0,2026-09-18T11:44:57Z
```
(timestamps here in UTC, as stored; local time above is UTC+3)

These correspond exactly to the tracked/untracked file changes below.

## Classified changes

| Path | Tracked? | File type | Modified | Likely generating process |
|---|---|---|---|---|
| `backend/training/documents/doc_0d910a43b4a021e3.json` | tracked | JSON, document registry record | 2026-09-18 14:42:29 | Re-analysis of an already-tracked upload, "Burrville ES - ST.pdf" |
| `backend/training/multimodal_review_index.json` | tracked | JSON, per-section prediction/review index (31.5 MB) | 2026-09-18 14:44:54 | Same two re-analysis events, writing per-token review-index entries |
| `backend/training/upload_log.csv` | tracked | CSV, append-only upload log | 2026-09-18 14:44:57 | Both processing events (2 new rows appended) |
| `backend/training/documents/doc_06009aaef05256fa.json` | **untracked (new)** | JSON, document registry record | 2026-09-18 14:44:57 | Processing of `burrville_SEMANTIC_DAMAGE_TEST.pdf` |
| `backend/training/documents/doc_71b87553b617833f.json` | untracked, **pre-existing** | JSON, document registry record | 2026-09-14 00:18 | Unrelated, predates this task by 4 days; not touched |
| `backend/training/documents/doc_8c6dfa0d820abb35.json` | untracked, **pre-existing** | JSON, document registry record | 2026-09-13 23:58 | Unrelated, predates this task; not touched |
| `backend/training/documents/doc_fba71e49fb20a89e.json` | untracked, **pre-existing** | JSON, document registry record | 2026-09-14 01:55 | Unrelated, predates this task; not touched |
| `backend/training/label_reconstruction_tmp/broadened_ranker_eval.json` | untracked, **pre-existing** | JSON, eval scratch output | 2026-09-14 02:06 | Unrelated, predates this task; not touched |

Only the **first 4 rows** are drift from this session's dev-server run. The last 4 rows predate this entire
engagement (by 4+ days, before the audit's own baseline commit `5261ee1` even existed) and are included here
only for completeness of the preserved-directory inventory, per this task's instruction to record their
existence at a high level — **their contents were not opened in this task**.

## Per-file detail

### `backend/training/documents/doc_0d910a43b4a021e3.json` (tracked, modified)

- **Diff summary**: 4 of 15 top-level fields changed: `source_path`, `updated_at`
  (`2026-09-09T11:53:39Z` → `2026-09-18T11:42:29Z`), `engineering_object_count` (1127 → 1132),
  `prediction_count` (863 → 864).
- **Contains human-review/training information?** No — this is a document-processing-stage registry record
  (filename, page count, hash, counts, timestamps). No extracted text, no predictions, no human-review
  decisions are stored in this file.
- **Reproducible?** Yes — re-running the same PDF through Upload/Extract → Analyze would regenerate an
  equivalent record (counts may vary slightly run-to-run depending on pipeline state).
- **May contain private uploaded-document data?** The `source_file`/`source_path`/`sha256` fields reference a
  previously-uploaded document ("Burrville ES - ST.pdf") that is not part of this repository's own tracked
  fixtures — this record's *existence* predates this session (it was already in `HEAD`); only its counters
  were refreshed by this session's re-analysis. Treat the underlying document as potentially private; this
  registry record itself contains only metadata, not document content.
- **Recommended action**: **preserve** (do not revert without explicit approval — the counter refresh reflects
  a real re-analysis event, not corruption).

### `backend/training/multimodal_review_index.json` (tracked, modified, 31.5 MB)

- **Diff summary**: two clusters of change. (1) ~50 existing per-section entries for
  `"burrville es - st__0d910a43b4a0.pdf::<SECTION>"` had their list contents refreshed (list length unchanged
  at 25 entries per section — values updated, not counts). (2) ~74 **new** entries appeared for
  `"burrville_semantic_damage_test__06009aaef052.pdf::<SECTION>"` — i.e., a first-time processing of the
  semantic-damage-test fixture.
- **Contains human-review/training information?** Yes — each entry is a dict with keys including
  `original_token`, `corrected_token`, `prediction`, `why_selected`, `why_rejected`, `explanation`,
  `reasoning`, `evidence`, `multimodal_confidence`, `multimodal_review_status`. This is exactly the
  continuous-learning review-index data CLAUDE.md and the earlier audit both describe as normal-to-edit at
  runtime — confirmed structurally, not by content inspection.
- **Reproducible?** Only partially — the `_burrville_semantic_damage_test__06009aaef052_` entries are fully
  reproducible (re-processing the repo's own bundled fixture `burrville_SEMANTIC_DAMAGE_TEST.pdf`). The
  refreshed Burrville-ES entries reflect a real re-analysis of a real prior upload and may not reproduce
  byte-identically on a second run.
- **May contain private uploaded-document data?** The Burrville-ES-linked entries reference a
  previously-uploaded, non-fixture document (structured prediction data only, not raw document content). The
  semantic-damage-test entries reference the repo's own tracked fixture
  (`validation/semantic_test_pdfs/burrville_SEMANTIC_DAMAGE_TEST.pdf`) — not private.
- **Recommended action**: **preserve** (do not revert without explicit approval).

### `backend/training/upload_log.csv` (tracked, modified)

- **Diff summary**: 2 rows appended (shown verbatim above — this file's content is already a log of
  filenames/counts/timestamps, not sensitive beyond what's already tracked in the file's prior 124 rows).
- **Contains human-review/training information?** No — upload/processing metadata only (UUID, filename, page
  count, prediction counts, timestamp).
- **Reproducible?** Yes, in shape (two new log rows would be appended again by re-running the same two
  processing events); exact UUIDs would differ.
- **May contain private uploaded-document data?** Row 1 references the same prior "Burrville ES - ST.pdf"
  upload (filename only, no content). Row 2 references the repo's own semantic-damage-test fixture.
- **Recommended action**: **preserve** (append-only log; reverting would falsify the historical record of
  what actually happened).

### `backend/training/documents/doc_06009aaef05256fa.json` (untracked, newly generated)

- **Content** (structural fields only): `document_id: doc_06009aaef05256fa`,
  `source_file: burrville_SEMANTIC_DAMAGE_TEST.pdf`, `stage: analyzed`, `page_count: 29`,
  `prediction_count: 863`, `engineering_object_count: 1141`, `created_at`/`updated_at` both
  2026-09-18T11:4x.
- **Contains human-review/training information?** No — same registry-record shape as the tracked document
  records above.
- **Reproducible?** Yes, fully — `source_file` is the repository's own bundled test fixture
  (`validation/semantic_test_pdfs/burrville_SEMANTIC_DAMAGE_TEST.pdf`), not user-private data. Re-running that
  fixture through Upload/Extract would regenerate an equivalent record.
- **May contain private uploaded-document data?** **No** — confirmed by `source_file` matching the repo's own
  tracked fixture, not a private upload.
- **Recommended action**: **preserve for now**; this is the one file in the drift set that could reasonably be
  **regenerated** on demand rather than preserved indefinitely, but per this task's explicit instruction it
  was not decided to be disposable and was not staged, reverted, or deleted.

## Recommended future action summary

| Path | Recommended action |
|---|---|
| `backend/training/documents/doc_0d910a43b4a021e3.json` | preserve |
| `backend/training/multimodal_review_index.json` | preserve |
| `backend/training/upload_log.csv` | preserve |
| `backend/training/documents/doc_06009aaef05256fa.json` | preserve (reproducible from the repo's own fixture, but not deleted without explicit approval) |
| 4 pre-existing untracked files (dated 2026-09-13/14) | preserve, out of scope, not opened |

**None of the 4 drift files were staged, committed, reverted, archived, or deleted in this task.** They remain
exactly as found. Any decision to commit, revert, or discard them requires your explicit, separate approval —
not implied by this classification.
