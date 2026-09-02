# Phase 3A Human Review Audit

## Existing human-review sources

1. **Drawing Review**
   - UI: `frontend/src/pages/DrawingReviewPage.jsx`
   - Section selector: `frontend/src/components/SectionReviewSelector.jsx`
   - API: `POST /engineering/corrections`
   - Append-only log: `backend/training/engineering_corrections.jsonl`
   - Optional latest section overlay: `backend/training/human_selections.json`

2. **Unknown-token review**
   - Persistence: `unknown_tokens.csv`, `approved_dataset.csv`, and `history.csv`
   - This is token-to-class review. It has no page, bbox, geometry target, role, scale, or length truth.

3. **Offline association review**
   - Implementation: `backend/services/ml_association/`
   - Review kit: `backend/scripts/build_ml_association_review_kit.py`
   - Importer: `backend/scripts/import_review_decisions.py`
   - Outcome schema: append-only `ReviewedOutcome` records with document/page/text entity, selected geometry IDs, no-valid-target, ambiguity, reviewer, timestamp, and history.
   - No current decision files or outcome JSONL were found under `backend/training/ml_association/`.
   - The tracked 108-case manifest describes a historical review batch, not completed human outcomes.

## Human decision persistence

`engineering_corrections.jsonl` stores:

- `document_id`, `object_id`, timestamp
- the full prediction snapshot when supplied, including page and label bbox
- `correct_label`
- optional `correct_geometry`
- `user_decision` and free-text notes

Drawing Review actions are `approve`, `correct`, `mark_unreadable`, and
`mark_unsupported`. The separate section selector supports model candidates and
free-text **Other**, but its latest-value store only contains
`document_id -> object_id -> {section, selected_at, notes, semantic_type?}`.

## What can be reused

- An explicit Drawing Review `approve` or `correct` can support section truth
  when the prediction snapshot contains a stable page and label bbox.
- `mark_unreadable` and `mark_unsupported` can support annotation status.
- Offline association outcomes, if present, would support target/no-target and
  ambiguity truth. None are currently present.

## Fields missing for Gold Set association truth

The current Drawing Review flow does **not** require or persist:

- a selected member/geometry ID
- an explicit “correct orphan / no valid target” decision
- association failure vs geometry-recall failure
- member role confirmation
- region confirmation
- scale confirmation
- member length confirmation

`correct_geometry` exists in the backend correction schema but Drawing Review
does not populate it.

Therefore a section approval must not be treated as association approval.

## Burrville audit

- Unknown-token records contain Burrville human approvals, but they are
  token-to-class decisions without page, bbox, or geometry identity.
- Structured inspection found eight Burrville correction rows, including five
  `drawing_review:*` events.
- Those five events collapse to two unique explicitly reviewed drawing objects:
  `token_p7_176` (`HSS10X6X3/8`) and `token_p7_205` (`W16X26`), both on page 7.
  Repeated writes for `token_p7_176` are review history, not four cases.
- Neither unique Drawing Review object stores `correct_geometry`.
- Their object IDs are stale relative to the current artifacts
  (`token_p7_176` no longer identifies the current occurrence), so they are not
  safe occurrence-level Gold records.
- No explicit Burrville page-8 orphan/no-target decisions were found.

## Audit conclusion

Existing token reviews can support a separate global lexicon dataset, but the
stale occurrence IDs mean no inspected Burrville record is safe to seed this
spatial Gold Set. The records cannot supply a 30–50-case association Gold Set
or classify the 50 Burrville page-8 orphans. The existing offline
association-review workflow is the appropriate reusable mechanism because it
already records selected geometry, no-valid-target, ambiguity, reviewer
identity, and append-only history. Human review must occur before association
metrics or a Burrville orphan diagnosis can be reported.
