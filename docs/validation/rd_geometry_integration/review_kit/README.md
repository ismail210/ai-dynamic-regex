# Human gold review kit (G3)

Open `index.html` in a browser (`file://`).

1. Decide **before** revealing the production pick.
2. Leaders are support, not members (`leader_support_not_target` is a note that a candidate is a leader, not the member).
3. If unsure, use `ambiguous_requires_adjudication`.
4. If a member is visible but none of the listed candidates is that member, use `no_valid_target`.
5. If the crop/drawing cannot be judged, use `unavailable`. Do not guess from JSON alone.
6. Do not invent thickness or beam/column roles.
7. Save decision JSON into this folder’s `decisions/` and append a line to `gold_outcomes.jsonl`.

Kit fields (required):

```json
{"token_id":"token_p8_348","review_label":"direct_target","reviewed_target_geometry_ids":["geom_..."],"reviewer_id":"initials","page":8,"text":"W30X90"}
```

`review_label` values:

| Value | Human decision |
|-------|----------------|
| `direct_target` | Associated; list the member geometry (not the leader) |
| `no_valid_target` | Label is real but no listed candidate is the member, or there is no member |
| `ambiguous_requires_adjudication` | Multiple members remain plausible |
| `unavailable` | Evidence/crop insufficient |
| `leader_support_not_target` / `not_target` | Candidate-level notes; not used as gold-associated |

The first Burrville pass (75/75) is in `gold_outcomes.jsonl` with extra R&D fields (`decision`, `reason`, `error_bucket`, `candidate_geometry_ids`, `production_geometry_id`). Report: [`../HUMAN_GOLD_REVIEW_REPORT.md`](../HUMAN_GOLD_REVIEW_REPORT.md). Regenerating the kit HTML **must not** wipe that file.
