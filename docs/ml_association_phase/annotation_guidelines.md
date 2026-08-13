# Annotation Guidelines

For reviewers using the export produced by `review_export.py` / `service.export_groups`. Every example below uses the actual enum values from `services/ml_association/enums.py` — use the exact string, not a paraphrase, when submitting a review.

**What this document does NOT do**: invent structural-engineering rules the repository and research don't already establish. Where a real judgment call needs a domain expert's input (e.g., "is this line a grid line or a member?"), that's flagged explicitly and logged in `unresolved_questions.md` instead of guessed at here. This mirrors the deep-research report's own domain questionnaire (`docs/geometry_graph_audit/06_research_findings.md`), which asked these same questions rather than answering them.

## The six `review_label` values

### `direct_target`
The geometry candidate **is** the physical member this label identifies — the ordinary case. Example: a `"W18X35"` label sits directly beside a straight line, and that line is the beam it's calling out. Select the candidate, mark `direct_target`, `callout_scope=single`.

### `valid_secondary_target`
The geometry candidate is **one of several** real members this one label legitimately applies to. Use this alongside `callout_scope` in `{multiple, typical, repeated}` (see below) — every additional correct target beyond the first gets its own `valid_secondary_target` entry (or, if your reviewer UI supports multi-select in one submission, list all target IDs together under one outcome with `callout_scope=multiple`; either shape is accepted by `validation.py` as long as `reviewed_target_geometry_ids` contains every real target).

### `leader_support_not_target`
The candidate is a **leader/arrow stroke** that helps a human (or `spatial_index.py`'s leader-endpoint resolution) find the real target — but the leader itself is not a structural member and must never be recorded as one. `validation.py` enforces this: submitting `leader_support_not_target` together with any `reviewed_target_geometry_ids` is rejected (`ValidationErrorCode.LEADER_SUPPORT_AS_FINAL_TARGET`) precisely to prevent a leader stroke from silently becoming "the answer" in training data.

Example: the label's nearest candidate (by raw distance) is a short diagonal leader stroke, and the export's overlay draws a dashed line from that leader toward the real target further away (see `review_export.py`'s `leader_support_evidence` overlay). Mark the leader candidate `leader_support_not_target`, and separately mark the real target `direct_target`.

### `not_target`
The candidate is a real geometry entity, but it is simply the wrong one for this label — not a leader, not a valid secondary target, just incorrect. Use this to explicitly reject a candidate (useful training signal: a *hard negative*) rather than leaving it unaddressed.

### `no_valid_target`
None of the exported candidates — and, if you looked at the source page directly, nothing else on the page either — is a valid target for this label. `reviewed_target_geometry_ids` must be empty (`validation.py` rejects the combination otherwise). Common causes: the label refers to a member on a different sheet (see "cross-detail mistakes" below, still an open question), the label is genuinely unresolvable from this drawing alone, or it's a note/callout that was never meant to resolve to one specific line.

### `ambiguous_requires_adjudication`
You cannot confidently decide among this label's own reasonable interpretation — record it as ambiguous rather than guessing, and set `adjudication_status=needs_second_review` on the resulting outcome (or leave it for a second reviewer pass) instead of picking arbitrarily. Ambiguous cases should not silently become training examples with a made-up "correct" answer.

## `callout_scope`

| Value | When to use |
|---|---|
| `single` | One label, one real target. Most common case. |
| `multiple` | One label genuinely applies to more than one specific, distinct member (not "typical of a group" — see below). |
| `typical` | A "TYP"/"typical" style callout meant to apply to a whole class of similar members, not enumerated individually. **How exactly to bound "typical" scope (which members count, where the scope ends) is an open domain question** — see `unresolved_questions.md`. Record what you can determine from the drawing; don't over-claim precision the drawing itself doesn't give you. |
| `repeated` | The same label text appears multiple times on the page/sheet, each instance pointing at its own distinct member. Whether repeated instances should be treated as separate label entities or one logical designation with several occurrences is **also an open question** (deep-research report's domain questionnaire, same source). |
| `detail_reference` | The label is a reference to a detail elsewhere (a bubble/callout), not a direct member designation on this page. |
| `schedule_reference` | The label's real meaning is resolved via a schedule table, not direct geometry association. |
| `unknown` | You cannot yet classify the scope. Prefer this over guessing. |

## Things that resemble members but (usually) are not

The geometry-extraction pipeline **does not** distinguish these from real structural lines by shape alone — see `docs/geometry_graph_audit/03_geometry_audit.md §8`: `GeometryKind` classification is purely path-syntax/size based, with no concept of "grid line," "border," or "hatch." This means candidates you're shown may legitimately include:

- **Grid lines** — long, straight, axis-aligned, often extending well beyond any actual framing. The pipeline cannot currently tell a grid line from a beam by its geometry alone (both are just `LINE`-kind paths). **Which visual cues reliably distinguish them is an open domain question** (grid bubbles, dash patterns, regular spacing — none of this is currently extracted or exposed to you as a reviewer signal). Use your own judgment from the source page; do not assume the tool has already screened these out.
- **Dimension lines / witness lines** — the pipeline has a narrow heuristic (`_looks_like_dimension`: stroke ≥12pt near numeric text) that sometimes reclassifies these, but it runs *after* an equally narrow leader heuristic and can misfire on short witness lines. If a candidate's `geometry_kind` shown in the export is `"dimension"`, treat that as a hint, not a guarantee.
- **Sheet/detail borders** — a large rectangle can be a real plate/profile or simply the drawing's border/match-line. The pipeline has no distinction between these (`docs/geometry_graph_audit/03_geometry_audit.md §8`). If a "candidate" is obviously the page border, mark it `not_target`.
- **Leaders that resemble short members** — see `leader_support_not_target` above.

None of this should be read as "the tool is broken" — it's an accurate description of where automated geometry classification currently stops and human judgment is still required, which is exactly the gap this review process exists to close.

## Cross-detail / cross-region mistakes

This repository has **no detail-region or drawing-area segmentation** yet (`docs/geometry_graph_audit/08_prioritized_roadmap.md` P1.4 is still open) — every candidate on a page is offered regardless of which visual "detail" or "area" it actually belongs to. If a candidate is spatially close to your label but visually in a *different* detail box/viewport, mark it `not_target` (or `candidate_generation_miss=true` if the true target was in a different detail and wasn't offered as a candidate at all because it was farther away). Every `LabelGroup`/`AssociationCandidateRow` in this phase has `region_id=None` — this is not a data-entry omission, it's an accurate reflection that no region layer exists yet. Do not infer or fabricate a region ID.

## Recording a candidate-generation miss

If the real target genuinely was not offered as a candidate at all (you have to look elsewhere on the page to find it), set `candidate_generation_miss=true` on your submission and put the real target's geometry ID in `reviewed_target_geometry_ids` anyway — `validation.py` specifically allows an out-of-candidate-set target only when this flag is set (`ValidationErrorCode.TARGET_OUTSIDE_CANDIDATE_SET` otherwise). This is valuable signal, not an error to avoid — it's exactly how candidate-generation recall gets measured (see `06_research_findings.md`'s recommended metric suite).
