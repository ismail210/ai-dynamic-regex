# Extraction & Compilation Accuracy Track — A1–A8 status

**Date:** 2026-09-13  
**North star:** extract → normalize / repair / complete / associate → `drawing_semantics.json`  
**Not optimized here:** takeoff quantity / Excel matching / dense-page cap / auto L thickness

| ID | Deliverable | Status |
|---|---|---|
| A1 | Context-scope / compilation-surface fix | Done — `A1_CONTEXT_SCOPE_AUDIT.md`, legend v5b, pipeline restore |
| A2 | Extract/group gold (87 rows) | Done — `training/eval_cache_backups/accuracy_gold/june_16page_extract_group_gold.json` |
| A3 | Rotation/bracket grouping + F1 | Done — `fragment_grouper.py`, `scripts/measure_grouping_f1.py` |
| A4 | Deterministic canonicalize audit | Done — `section_canonicalize.py`, `scripts/audit_normalize_false_corrections.py` |
| A5 | Repair shadow metrics | Done — `scripts/measure_repair_shadow.py` (flags stay off) |
| A6 | SOURCE_VERIFIED completion design | Done — `A6_COMPLETION_EVIDENCE_DESIGN.md` + fixtures |
| A7 | Association gold + measure | Done — `june_association_gold.json`, `scripts/measure_association_precision.py` |
| A8 | `drawing_semantics.json` emitter | Done — `drawing_semantics.py`, `scripts/emit_drawing_semantics.py` |

Safety unchanged: incomplete L/2L abstain; catalog ≠ thickness evidence; Excel ≠ predictor; ML ranker off.
