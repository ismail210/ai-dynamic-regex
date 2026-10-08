# Takeoff value matrix

Scores run 1–5. **Takeoff** is direct help to a correct count or section. **Location** is where the item is. **Review** is how much it speeds up a reviewer. **Nav** is drawing-set navigation. **Safe auto** is whether it can be extracted without judgment. **Risk if wrong** is the worst case.

| Capability | Takeoff | Location | Review | Nav | Safe auto | Level | Qty | Risk if wrong |
| --- | --: | --: | --: | --: | --: | --- | --- | --- |
| Exact printed sections (exists) | 5 | 1 | 4 | 1 | 5 | A | Yes, gated | Wrong size in takeoff |
| Incomplete-label abstention (exists) | 5 | 1 | 4 | 1 | 5 | A | Excl | Invented thickness |
| Schedule mark map (exists) | 5 | 1 | 4 | 2 | 4 | A/B | Yes, gated | Wrong section propagated to every occurrence |
| Mark occurrence ledger | 5 | 4 | 5 | 3 | 4 | B | No (exposes misses and duplicates) | Hides a missing occurrence; ledger only |
| Sheet index (number, title, scale, page) | 3 | 3 | 5 | 5 | 4 | A | No | Wrong sheet label on evidence |
| View index (title, number, scale, extent) | 4 | 4 | 4 | 5 | 3 | A/B | Excl (scope) | A plan label treated as a detail, or the reverse |
| Reference objects + resolution | 3 | 2 | 5 | 5 | 4 | A/B | No | Wrong navigation link |
| Grid registry per view | 3 | 5 | 4 | 3 | 3 | A/B | No | Wrong location string |
| Label → grid location string | 3 | 5 | 4 | 2 | 3 | B | No | Wrong location shown |
| Level per counted occurrence (plan title ↔ level) | 3 | 4 | 4 | 3 | 3 | B | No | Wrong floor assignment |
| Scope tags (existing, demo, alternate) per view or member | 4 | 1 | 4 | 1 | 2 | B/C | Excl, with review | Existing steel counted as new |
| Revision / issue metadata | 2 | 1 | 4 | 3 | 4 | A | Excl, with review | Superseded sheet counted |
| Plate and accessory lines (BP, anchor rods) as a separate takeoff | 4 | 2 | 3 | 1 | 3 | A/B | Future, separate gate | Plate double count |
| Column tier length between levels | 4 | 3 | 3 | 1 | 2 | B/C | Future | Wrong length |
| Dimension → member attachment | 3 | 3 | 2 | 1 | 1 | B/C | No | Wrong length or spacing |
| Geometry member box (BBX) | 1 | 3 | 4 | 2 | 2 | B | Never | Misleading highlight |
| Detail governs member (connection) | 2 | 1 | 4 | 3 | 1 | B/C | No | Wrong connection assumption |
| Steel grade / material notes | 2 | 1 | 3 | 1 | 4 | A | No (attribute) | Wrong grade on export |
| Joist / deck schedules | 3 | 1 | 2 | 1 | 4 | A | Future, separate family | Mixed families |
| LLM narrative polish | 0 | 0 | 2 | 1 | n/a | — | Never | Misleading prose |

Reading: the highest takeoff value with high safety is the occurrence ledger plus the sheet, view, and reference indexes. They make existing counts explainable and expose misses and duplicates, without new quantity paths. Scope tags are high value but need human review before they exclude anything.
