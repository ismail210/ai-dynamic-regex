# AI / ML / LLM roadmap

Order of preference: native PDF text and vectors → deterministic grammar → measured ML ranking or classification → selective OCR or vision → LLM only for grounded wording or rule discovery behind gates.

What was already measured, and should not be repeated without new evidence:

| Item | Decision | Source |
| --- | --- | --- |
| XGB / ML label ranker | Do not enable | `FINAL_ACCURACY_GAP_AUDIT.md` |
| Graph v2 scoring | Do not enable; worse than text | same |
| Leader → target as a ranking signal | Stop; 0.7% reliable | same |
| GraphSAGE / learned fusion / geometry missing-label inference | Off | same |
| G8/G9 geometry association | `PRODUCTION_NO_GO`; Burrville only | geometry meeting summary |

## Candidates

| # | Problem | Baseline | ML / LLM idea | Input → output | Data needed | Failure mode | Cost / latency | Explainable | Safety risk | Fallback | Qty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Sheet title-block fields vary by firm | Keyword band | Learned title-block field locator (small layout model) or per-project template from the first pages | Page words + boxes → field boxes | 30–50 human-labelled title blocks across 8+ firms | Wrong field picked | Low; local | Yes (box shown) | Low | Deterministic band + "unresolved" | No |
| 2 | View / region extents | x-gap clustering | Vector-border detection first; small detector only if borders fail | Vectors + view titles → view boxes | Human-drawn view boxes on 10 sheets per project | Merged or split views | Medium | Yes | Medium (scope) | Page-level scope | Excl only |
| 3 | Page / view type | Regex categories | Text classifier over view title + content counts | View text → type | Labelled views from Phase 2 | Plan read as detail | Low | Yes, with features | Medium | Regex + review | Excl only |
| 4 | Stacked bubble vs other stacked text | Geometry + text rule | Not needed unless precision is below target | — | Phase 1 human sample | False reference | — | — | Low | Rule | No |
| 5 | Label → member geometry (BBX) | `member_geometry` | Ranker on G8 candidates | Label + candidates → choice or abstain | Ownership review on ≥ 2 non-Burrville packages | Wrong member highlighted | Medium | Partly | Medium | Abstain | Never |
| 6 | Rotated / raster pages | Native text | Conditional OCR only where the text layer is missing | Raster → words | Pages with no text layer (none in the current 8) | OCR digit errors | High | Yes (OCR conf) | High for sizes | Review | Only after review |
| 7 | Project drawing language rules | `legend_llm_provider` + `project_rules` gates | Keep as is; extend rule types only with gates | Legend text → typed rules | Rule-level gold | Hallucinated rule | Medium | Yes (quoted text) | Gated | Ignore rule | Only `LABEL_SUBSTITUTION`, gated |
| 8 | Summary prose | Deterministic narrative | `drawing_summary_llm`, grounded | Evidence packet → sentences | None; check quotes | Misstated fact | Low | Must quote | Low | Deterministic text | Never |
| 9 | Scope / alternate interpretation | Signals | LLM proposes scope per view from notes, quoting text | Notes + view titles → proposal | Human decisions on 3+ sets with alternates (OSSE) | Wrong exclusion | Medium | Quoted | High | Review | Never automatic |
| 10 | Vision model on whole pages | — | Not recommended | — | — | Plausible but unprinted sizes; not benchmarked in this repo | High | Low | High | — | Never |

## Where deterministic logic must stay

Section strings, thickness, plate dimensions, level elevations, grid names, reference labels and targets, mark-map membership, and every quantity gate.
