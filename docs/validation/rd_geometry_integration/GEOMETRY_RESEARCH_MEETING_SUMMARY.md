# Geometry R&D — Team Meeting Summary

**Document:** Burrville `doc_0d910a43b4a021e3` (R&D shadow path)  
**Final gate:** `PRODUCTION_NO_GO`  
**Historical gold SHA (immutable):** `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155`

---

## Meeting paragraph (speak this)

We started this geometry work because Drawing Review often shows a correct red text box but a missing or questionable green Member box, and we needed to know whether that was a representation problem, an association problem, or both—without changing production. G7 was a bbox/representation audit: it showed that PDF strokes frequently arrive as giant or compound paths that are not member-scale, so the candidate pool itself was unreliable. G8 was a shadow representation-repair experiment on that pool; it reached `REPRESENTATION_READY_FOR_ASSOCIATION` by recovering better member-scale candidates, including short strokes and segmented compounds, still without touching production extraction. G9 then tried deterministic text-to-geometry association only on that frozen G8 candidate universe, as a shadow; its gate was `ASSOCIATION_STILL_NOT_READY`. We audited 27 G9 “false associations” and found they were mostly not scorer bugs: B = 21 were stale pre-G8 gold cases, C = 5 were parallel-bay ambiguity, and D = 1 was a genuine ranking failure (`token_p24_1359`, long LINE preferred over short SEGMENT at the leader tip). A separate G8-era human ownership review covered those 27 cases: 22 `VALID_MEMBER`, 5 `AMBIGUOUS`, and 0 unresolved or `NO_VALID_MEMBER`. G10 was correctly not run—its justification gate was `NOT_JUSTIFIED` because one isolated ranking failure does not establish a repeatable pattern. `PRODUCTION_NO_GO` means we do not wire G8/G9 into production, do not rewrite historical gold, and do not ship a new association policy on this evidence alone; production stays on the live `member_geometry` path—PDF geometry extraction, current candidate merging, current text-to-member association, and ambiguity abstention when there is no unique confident link—while G8/G9 remain shadow-only. Research showed that candidate representation can potentially be improved, but it did not prove that a new association policy is safe or better for production; it also did not prove generalization beyond Burrville. The next logical validation step is to run G8-class candidate repair plus ownership review on at least one non-Burrville package before any association-policy experiment.

---

## Quick reference

| Item | Status |
| --- | --- |
| G7 | COMPLETE — bbox/representation audit |
| G8 | COMPLETE — `REPRESENTATION_READY_FOR_ASSOCIATION` |
| G9 | COMPLETE — `ASSOCIATION_STILL_NOT_READY` |
| False-assoc audit | B=21, C=5, D=1 |
| G8-era human review | 27 reviewed; 22 VALID_MEMBER; 5 AMBIGUOUS |
| G10 | `NOT_JUSTIFIED` — not run |
| Final | `PRODUCTION_NO_GO` |
| Production | Untouched; G8/G9 not wired |
| Historical gold | Immutable |
| Generalization | Not established beyond Burrville |

---

## Source artifacts

- `GEOMETRY_BBOX_AUDIT_G7_REPORT.md`
- `GEOMETRY_REPRESENTATION_REPAIR_G8_REPORT.md`
- `GEOMETRY_ASSOCIATION_G9_REPORT.md`
- `g9_false_association_audit/G9_FALSE_ASSOCIATION_AUDIT_REPORT.md`
- `g8_era_human_validation/G10_JUSTIFICATION.md`
- `FINAL_ASSOCIATION_GATE_REPORT.md`
