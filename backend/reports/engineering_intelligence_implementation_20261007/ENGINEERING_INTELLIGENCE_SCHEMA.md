# Engineering intelligence schema — current

This is what the profile stores after this checkpoint. It is not the full navigation model. Fields already used by column schedules, levels, and mark definitions are unchanged and are not restated here.

## Sheet index

`drawing_intelligence.sheet_index` (version `sheet_index_v1`, plus `role_version` `sheet_role_v1`). Boxes are in display space. One record per PDF page.

| Field | Meaning | Safety |
| --- | --- | --- |
| `sheet_id`, `sheet_id_status`, `source_bbox` | Printed sheet number and where it was read | Level A when status is `read` |
| `sheet_title`, `title_status`, `title_bbox` | Printed title. `read_unlabeled` means the title is printed and the block has no “drawing title” label (Furley) | Level A |
| `issue`, `issue_date`, `issue_status` | Title-block issue phrase and its date | Level A |
| `scale`, `scale_status` | Title-block scale field. A graphic bar is not substituted when the field is absent | Level A |
| `revision.rows[]` | `number`, `description`, `date` from the revision table | Level A. Not an issue |
| `sheet_role`, `sheet_role_label` | Role derived only from `sheet_title` | Level A when `classification_status` is `read` |
| `classification_status` | `read`, `review`, or `unresolved` | |
| `classification_evidence` | Why that status was chosen | |
| `role_candidates` | Drawing-type words found when the title names more than one | Level B until a person picks one |

Roles in use: `general_notes`, `loading`, `foundation_plan`, `framing_plan`, `roof_plan`, `elevation`, `section`, `detail`, `foundation_details`, `concrete_details`, `steel_details`, `masonry_details`, `schedule`.

`foundation_plan` may be labeled “Foundation and framing plan” or “Foundation and floor plan” when those words are in the title. `framing_plan` may be labeled “Floor plan” when the title says floor plan and does not say framing.

## Orientation

`narrative.project_overview` starts with the page count and, when every sheet or a majority share one title-block issue, `(issue: …)`. Column-schedule sheet ids in that sentence come from the sheet index, not from the legacy id that strips hyphens.

## Engineering intelligence

`drawing_intelligence.engineering_intelligence`, version `engineering_intelligence_v1`. Added beside the sheet index. Existing keys are not removed.

| Key | Meaning | Status rule |
| --- | --- | --- |
| `views[]` | `sheet_id`, `pdf_page`, `view_id`, `view_number`, `view_title`, `view_type`, `scale`, `bbox`, `source_text`, `status`, `boundary_status`, `evidence` | `read` only for a whole-line title. `sheet_title` when the sheet title is reused. `boundary_status` `title_only` is not a view extent |
| `references[]`, `reference_count` | `reference_text`, `reference_type`, `source_sheet`, `target_sheet`, `target_number`, `status`, `bbox`, `evidence` | `target_view_found`, `target_sheet_only`, `target_sheet_found`, `target_missing`, `ambiguous`. Stored list is capped at 400; the count is the full set |
| `relationships[]` | `kind`, `status`, `evidence`, `source`, `confidence` | `resolved` only for a found view title or a `target_view_found` reference. These edges do not change quantities |
| `grids[]` | `grid_id`, `sheet_id`, `bbox`, `status`, `evidence` | Always `candidate` in this version. Cap 80 |
| `levels` | `building_levels`, `local_elevations` | A differing plan value is `conflict`. Both values stay |
| `occurrences[]` | `mark`, `sheet_id`, `status`, `quantity` | `quantity` is null. Status `defined_and_seen` or `defined_but_not_seen` |
| `objects[]`, `schedules[]` | Pointers to existing definitions and schedule readers | `read` of those readers. Not a new taxonomy parser |
| `dimensions[]`, `dimension_count` | Whole line with feet or inches, plus page and box | Stored list capped at 200 |
| `notes[]` | Numbered note text, category, sheet, box | Text is not rewritten |
| `incomplete_labels[]` | `printed_fact`, `candidate_cross_reference`, `resolved_definition`, `status` | `review_required`. The candidate and the resolved definition stay null |
| `scope_flags[]`, `scope_counts` | Printed existing / demolition / alternate / future / temporary | `review`. Not an exclusion |
| `warnings[]` | `type`, `severity`, `message`, `sheet_id`, `evidence`, `status` | `open`. Unresolved-reference warnings are capped at 30 |

`source_view` and `view_id` on a reference, a dimension, a note, and a grid are often empty. That empty field is the traceability gap, not a resolved link.

## Not measured yet

A geometric view boundary. A confirmed grid bubble. A mark tied to a grid or a level. A note that is not a numbered line. A schedule parser that replaces the existing column or plate readers.
