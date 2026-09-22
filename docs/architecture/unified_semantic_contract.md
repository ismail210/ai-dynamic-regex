# Unified Semantic Contract (schema v2.0)

**Status:** implemented. Canonical model lives in `backend/services/semantic/`.
**Supersedes:** `services.prediction.semantic_contract` (Pydantic) and
`services.semantic_preprocessor.models` (dataclasses) — both now re-export
from the one canonical module; neither defines its own domain classes anymore.

## 1. Why two models existed

They were built for different purposes and never reconciled:

- **`services.prediction.semantic_contract`** (partner, Hiba) is a **read-only
  projection schema**. It never runs extraction/grouping/normalization/repair
  itself — it maps the existing dict-shaped production prediction payload
  (`orchestrator.py` / `canonical_contract.py` output) into a typed,
  validated shape, purely for the A8 `drawing_semantics.json` sidecar and
  offline audit scripts. Strengths: Pydantic validation, a typed
  `OperationRecord[]` history with per-operation evidence, a typed geometry
  provider (`grasshopper` / `pdf` / `unavailable`).
- **`services.semantic_preprocessor.models`** (this branch, `98d8955`) is the
  **live data model for a self-contained pipeline** (extraction → grouping →
  normalization → repair → completion → geometry association), driving the
  actual "Semantic Review" demo end to end on real PDFs. Strengths:
  multi-fragment source provenance (`source_fragments`), semantic spatial
  representation (`semantic_bbox` / `original_anchor` / `original_axis`,
  never destroying per-fragment geometry), multiple ranked geometry
  candidates per annotation, and the KEEP/NORMALIZE/REPAIR/COMPLETE pipeline
  orientation.

Both independently modeled "what is a semantic annotation," with different
field names for overlapping concepts (`raw_text` vs `original_text`,
`geometry_evidence` (singular, one slot) vs `geometry_associations` (list)),
which is exactly the duplicate-domain-model problem this consolidation
removes.

## 2. Non-negotiable outcome

One class definition each for `SemanticDocument`, `SemanticAnnotation`,
`OperationRecord`, `GeometryAssociation`, in `services/semantic/models.py`.
Both old import paths (`services.prediction.semantic_contract`,
`services.semantic_preprocessor.models`) are thin re-export shims — old code
that imports from either path gets the *same* class object, not a copy.

## 3. Design decisions

| Decision | Chosen | From | Why |
|---|---|---|---|
| Container type | Plain `@dataclass` + hand-written `to_dict()` | preprocessor model | Benchmarked two ways: (1) a generic proxy shape at 27,099 instances — dataclass construct+`to_dict()` ~0.16s vs an equivalent Pydantic model's construct+`model_dump()` ~0.52s (~3x), using this repo's existing hand-rolled-`to_dict` convention rather than `dataclasses.asdict()` (itself ~2x slower than hand-written `to_dict`); (2) the real `SemanticAnnotation` class at the same 27,099 scale (nested `StructuralParse`/`OperationRecord`/`EvidenceRecord`/`ScoreValue`): construct 0.20s + `to_dict()` 0.37s + `json.dumps()` 0.28s = **0.85s end to end**, 45MB of JSON. Pydantic stays for thin API request/response bodies, not the domain model. |
| Closed vocabularies | `str, Enum` (`OperationKind`, `ReviewStatus`, `GeometryProvider`, `EvidenceType`) | partner model | Keeps partner's typing strength; an enum member IS a plain string at runtime/in JSON, so it costs nothing at the dataclass layer. |
| Text history | Append-only `operations: List[OperationRecord]`, never a single mutable `correction` field | partner model, generalized | A `Correction` field that gets reassigned per pipeline stage cannot represent "proposed then rejected," "grouped, normalized, then human-edited," etc. (Sections 12/45/75). |
| Association vs operation | `GeometryAssociation` is **not** an `OperationRecord` at all | preprocessor model (association was already never text-mutating) + partner's runtime validator, now made structural | Old partner code enforced "association must not change text" with a Pydantic validator on a generic operation. The unified model makes this a *type-level* guarantee: `GeometryAssociation` has no `output_text` field, so there is no way to construct a text-changing association. |
| KEEP | Explicit `OperationKind.KEEP` record | new (partner had no KEEP; preprocessor's `OP_NONE` was closest) | Auditability requirement (Section 14): the system must say "`W18X40` was evaluated and deliberately left unchanged," which is different from "never evaluated" (empty `operations`). |
| Source fidelity | `source_fragments: List[SourceFragment]` (each with its own bbox/font/rotation), `semantic_bbox` as a derived union, never a replacement | preprocessor model | Partner's model only carried one `source_bbox`; multi-fragment reconstruction (`"W18X40" + "[11;3;11]"`) needs every contributing fragment kept. |
| Geometry | `GeometryEvidence` (an object from a provider) + `GeometryAssociation` (a candidate link, evidence not truth), multiple per annotation, each with its own `provider`/`score`/`review_status` | preprocessor model's multi-candidate list + partner's typed provider | Neither alone was enough: partner had one typed-provider slot; preprocessor had a list but with `source: str` instead of a closed provider vocabulary. |
| Score | One `ScoreValue{value, kind, calibrated, model_name, model_version}` used everywhere a confidence-shaped number appears | new | Section 27: a raw LightGBM ranker score, a deterministic-rule confidence, and a calibrated probability must never be interchangeable floats. `kind`/`calibrated` make the distinction explicit at every use site (operation score, evidence score, association score). |
| Annotation identity | `derive_annotation_id(document_id, page, sorted(source_fragment_ids))` — a stable hash | new (fixes a real bug) | The old preprocessor grouping stage used `f"ann_{page}_{i}"` — a loop-position ID that would silently shift if upstream extraction ever reordered primitives. Never derived from corrected/canonical text either way (Section 24 requirement was already met on that axis). |
| Review | `ReviewState{status, resolved_text, reason, comment, history}` on the annotation; each `GeometryAssociation` carries its *own* independent `review_status` | both, unified | Section 73: a text repair can be human-accepted while its geometry association stays ambiguous. One global status can't represent that; per-association status can coexist with the annotation-level `ReviewState`. |
| Location | `services/semantic/` (new package) | — | Neither `services/prediction/` (too narrow — semantics are used far beyond prediction compilation) nor `services/semantic_preprocessor/` (too narrow — the model is now shared infrastructure, not preprocessing-only) was the right home (Section 53). |

## 4. Final schema (shape)

```
SemanticDocument
├─ document_id, schema_version="2.0", input_pdf_sha256, pipeline_version, catalog_version
├─ annotations: [SemanticAnnotation]
├─ drawing_language_rules: [DrawingLanguageRule]
├─ geometry_evidence: [GeometryEvidence]        # renamed from grasshopper_geometry (provider-neutral)
├─ coordinate_frames: [CoordinateTransform]
├─ diagnostics: {}                              # internal / not a stable contract
└─ metrics: {}

SemanticAnnotation
├─ annotation_id                                 # derive_annotation_id(...) — stable, position/text independent
├─ original_text                                 # WHAT WAS OBSERVED. Never overwritten.
├─ source_fragment_ids, source_fragments: [SourceFragment]   # WHERE IT CAME FROM
├─ semantic_bbox, original_anchor, original_axis  # WHERE IT IS ON THE DRAWING
├─ primary_label, modifiers, grouping_reasons     # WHAT IT MEANS (reconstruction)
├─ structural_parse: StructuralParse              # first-class typed interpretation
├─ operations: [OperationRecord]                  # WHAT CHANGED / WHY (full, immutable history)
├─ evidence: [EvidenceRecord]                     # annotation-level (not tied to one operation)
├─ takeoff_eligible: bool|None                    # WHETHER SAFE FOR TAKEOFF (independent axis)
├─ geometry_associations: [GeometryAssociation]    # WHAT GEOMETRY MAY BE ASSOCIATED (evidence, not truth)
├─ review: ReviewState                            # WHETHER A HUMAN HAS REVIEWED IT
├─ pipeline_version, created_by
└─ computed: effective_text, review_status, current_operation, is_complete, primary_geometry_association

OperationRecord: operation(KEEP|NORMALIZATION|REPAIR|COMPLETION), input_text, output_text,
                 reason_codes, evidence: [EvidenceRecord], score: ScoreValue|None,
                 deterministic, semantic_information_added, provenance, accepted, notes

EvidenceRecord: evidence_id, evidence_type(enum), source, strength(explicit|inferred|unknown),
                reference, score: ScoreValue|None, page, bbox, notes, details{}

GeometryAssociation: geometry_id, provider(pdf_vector|grasshopper|human|unavailable), rank,
                     score: ScoreValue|None, evidence, reason_codes, coordinate_frame,
                     verified, review_status

StructuralParse: is_structural, family, grammar, fields{}, complete, catalog_status, parser_reason
ScoreValue: value, kind, calibrated, model_name, model_version
ReviewState: status(pending|auto_accepted|human_accepted|human_rejected|needs_review|unresolved),
             resolved_text, reason, comment, reviewed_at, reviewed_by, history: []
DrawingLanguageRule: rule_id, trigger, result, status, scope{}, source_evidence, confidence
```

## 5. Operation semantics (Section 12/13/15-17)

- **KEEP** — evaluated, deliberately unchanged. `deterministic=True`,
  `semantic_information_added=False`.
- **NORMALIZATION** — same structural meaning, different representation
  (`HSS 8X8X0.375` → `HSS8X8X3/8`). `semantic_information_added=False`.
  Never called "repair."
- **REPAIR** — observed text appears corrupted (`W18X4O` → `W18X40`).
  Carries `score` (or `None` if uncalibrated — never fabricated),
  `provenance` (e.g. `"lightgbm_repair_ranker_v2"`), and starts life with
  `accepted=True` (matching the pre-existing UI contract: a proposed repair
  is shown as the effective text pending review, not hidden until accepted)
  — human rejection later sets `accepted=False` on that *same* record
  rather than deleting it.
- **COMPLETION** — information absent from the annotation was supplied from
  SOURCE_VERIFIED drawing evidence only (`W8` → `W8X10`).
  `semantic_information_added=True`. Evidence must reference a
  `DrawingLanguageRule`; Grasshopper occurrence, catalog frequency, and
  Excel quantity can never produce a COMPLETION record.
- **Association is not an operation.** It cannot appear in `operations` at
  all — it lives in `geometry_associations`, which has no `output_text`
  field. This is a type-level guarantee, not a runtime check.
- **Grouping is not an operation.** It is reconstruction provenance
  (`grouping_reasons`), because it produces the annotation, it doesn't
  transform an existing one.
- **Review actions are not operations.** They live in `ReviewState.history`.

## 6. Takeoff eligibility vs semantic validity (Section 10/11/40)

Independent axes, deliberately:

```
L4X4  →  is_structural=True, family="L", complete=False,
         takeoff_eligible=False, review.status=NEEDS_REVIEW
```

`takeoff_eligible=False` never means "not a semantic annotation" — the
annotation stays fully present in `annotations`, in the sidecar, and in the
review queue. `services/prediction/context_scope.py`'s
`partition_takeoff`/restore logic (Accuracy Track A1, unaffected by this
consolidation) is the enforcement point on the production prediction path;
`SemanticAnnotation.takeoff_eligible` is the same boolean surfaced through
the unified model for the standalone pipeline and the sidecar.

## 7. Geometry semantics (Section 19-22, 63)

Geometry is evidence, never truth. An annotation may have zero, one, or many
`GeometryAssociation` candidates, each independently tagged with `provider`
(`pdf_vector` | `grasshopper` | `human` | `unavailable`), its own
`review_status`, and a `verified` flag that only a human (or future
ground-truth import) ever sets `True` — never inferred from a provider's own
confidence. `score` may be `None`; association precision stays unclaimed
until real ground truth exists (A2/A7 human review), consistent with the
recent partner-integration audit. A future Grasshopper `RH_OUT` evidence
provider fits without a schema change — it is just another
`GeometryEvidence.provider=GRASSHOPPER` entry.

## 8. Review semantics (Section 23, 73)

`ReviewState.status` covers the annotation's text-level review; each
`GeometryAssociation.review_status` is independent, so a repaired label can
be `human_accepted` while its geometry candidate stays `needs_review`. This
matches how `apply_review_action` (`services/semantic_document_service.py`)
now works: "reject" preserves the rejected `OperationRecord` (sets
`accepted=False`, never deletes it or resets `operation` back to KEEP) and
records `ReviewState.status=HUMAN_REJECTED`, which is a more precise signal
than the old code's `needs_review` (nobody-has-looked-yet) after a human
explicitly *did* look.

## 9. Legacy compatibility (Section 31-32)

`services/semantic/serialization.load_semantic_document(data)` reads three
shapes and always returns today's `SemanticDocument`:

1. current (`schema_version` starts with `"2."`)
2. old preprocessor sidecar (single `correction` object per annotation)
3. old A8 `drawing_semantics_v1` row list

Nothing downstream ever sees the old shapes — conversion happens once, on
load. `services/prediction/semantic_contract.py` and
`services/semantic_preprocessor/models.py` each still re-export a subset of
this module's symbols for a few remaining callers, but neither is a pure
shim: `semantic_contract.py` also holds the `example_*` schema-demonstration
functions, and `semantic_preprocessor/models.py` also holds `TextPrimitive`,
an extraction-stage type this module never had an equivalent for.
`services/semantic_preprocessor/serialization.py` **was** a pure re-export
delegating to `services/semantic/serialization.py` — it has been removed
(2026-09-22 codebase-refactor cleanup); import `to_dict`/`to_json` from
`services/semantic/serialization.py` directly.

`services/prediction/drawing_semantics.py`'s sidecar schema bumped
`drawing_semantics_v1` → `drawing_semantics_v2` (field names changed:
`raw_text`→`original_text`, `normalized_text`→`primary_label`,
`geometry_evidence` singular slot → `geometry_associations` list, plus the
new `operations`/`review` structure). `TextPrimitive` (an extraction-stage
working type with no partner equivalent) was never part of the duplication
and stays where it was.

## 10. Public vs internal fields (Section 57-58)

**Stable contract** (the sidecar/API surface): `annotation_id`,
`original_text`, `effective_text`, `structural_parse`, `operations`,
`takeoff_eligible`, `geometry_associations`, `review`/`review_status`,
`source_fragments`.
**Internal/diagnostic**: `SemanticDocument.diagnostics`, per-operation
`notes`, `EvidenceRecord.details` (a free-form bag for provider-specific
data — deliberately not typed further per-provider, per Section 18's
"tagged record, not a dict dumping ground, but not a dozen subclasses
either").

## 11. Worked examples

**Clean** (`W18X40`):
```json
{"original_text": "W18X40", "operations": [{"operation": "keep", "input_text": "W18X40", "output_text": "W18X40"}],
 "effective_text": "W18X40", "takeoff_eligible": true, "review_status": "auto_accepted"}
```

**Normalized** (`HSS 8X8X0.375` → `HSS8X8X3/8`):
```json
{"original_text": "HSS 8X8X0.375",
 "operations": [{"operation": "normalization", "input_text": "HSS 8X8X0.375", "output_text": "HSS8X8X3/8",
                  "deterministic": true, "semantic_information_added": false,
                  "reason_codes": ["deterministic_grammar_equivalence"]}],
 "effective_text": "HSS8X8X3/8", "review_status": "auto_accepted"}
```

**Repaired** (`W18X4O` → `W18X40`):
```json
{"original_text": "W18X4O",
 "operations": [{"operation": "repair", "input_text": "W18X4O", "output_text": "W18X40",
                  "deterministic": true, "score": null,
                  "reason_codes": ["single_char_ocr_confusion_candidate"], "accepted": true}],
 "effective_text": "W18X40", "review_status": "needs_review"}
```

**Completed** (`W8` → `W8X10`, source-verified):
```json
{"original_text": "W8",
 "operations": [{"operation": "keep", "input_text": "W8", "output_text": "W8"},
                {"operation": "completion", "input_text": "W8", "output_text": "W8X10",
                 "semantic_information_added": true, "provenance": "drawing_language_rule",
                 "reason_codes": ["note_W8"],
                 "evidence": [{"evidence_type": "drawing_rule", "reference": "note_W8"}]}],
 "effective_text": "W8X10", "review_status": "auto_accepted"}
```

**Incomplete angle** (`L4X4` — mandatory case):
```json
{"original_text": "L4X4,",
 "structural_parse": {"is_structural": true, "family": "L", "grammar": "incomplete", "complete": false},
 "operations": [{"operation": "keep", "input_text": "L4X4,", "output_text": "L4X4"}],
 "effective_text": "L4X4", "takeoff_eligible": false, "review_status": "needs_review"}
```
No invented thickness. Fully visible in `annotations`, in the sidecar, and
in the review queue.

**Multi-fragment** (`W18X40 [11;3;11]`):
```json
{"original_text": "W18X40 [11;3;11]", "primary_label": "W18X40",
 "source_fragments": [{"primitive_id": "p1", "text": "W18X40", "bbox": [...]},
                       {"primitive_id": "p2", "text": "[11;3;11]", "bbox": [...]}],
 "modifiers": [{"type": "bracket_tag", "raw_text": "[11;3;11]", "value": "11;3;11"}],
 "grouping_reasons": ["same_baseline_merge", "bracket_modifier_attachment"]}
```

**Multiple geometry candidates**:
```json
{"geometry_associations": [
   {"geometry_id": "geom_pdf_1", "provider": "pdf_vector", "score": {"value": 0.7, "kind": "association_distance"}, "verified": false},
   {"geometry_id": "geom_ghx_1", "provider": "grasshopper", "score": null, "verified": false}
 ]}
```
Neither is truth until a human sets `verified=true` on one.

## 12. Final comparison

| Feature | Old partner model | Old preprocessor model | Unified model |
|---|---|---|---|
| Typing/validation | Pydantic, runtime validators | plain dataclass, no validation | dataclass + targeted `__post_init__` invariants (raw-text preserved, structural completeness) |
| Source fragments | one `source_bbox` | full `source_fragments[]` | full `source_fragments[]` (kept) |
| Operation history | typed `OperationRecord[]` | single mutable `Correction` | typed `OperationRecord[]`, immutable, `accepted` flag for rejection (kept + fixed) |
| Evidence | typed `SemanticEvidence` | untyped `EvidenceItem(type,value)` | typed `EvidenceRecord` with `EvidenceType` enum, `ScoreValue`, `details{}` |
| Structural parse | none (only `structural_family` string) | typed `StructuralParse` | typed `StructuralParse` + explicit `complete`/`catalog_status` |
| Completion | schema field only, no rule linkage | rule evidence via `evidence_ids` | rule evidence via `EvidenceRecord.reference`, `semantic_information_added` flag |
| Geometry providers | typed (`grasshopper`/`pdf`/`unavailable`) string | untyped `source: str` | typed `GeometryProvider` enum (kept from partner) |
| Multi-candidate geometry | one `geometry_evidence` slot | `geometry_associations[]` | `geometry_associations[]` (kept from preprocessor), each with its own provider/review |
| Review | `review_required`/`review_status` strings | `review_status` string only | `ReviewState` (6 states) + per-association review, rejection preserves history |
| Takeoff eligibility | field present, not enforced here | absent | present, independent axis, documented boundary with `context_scope.partition_takeoff` |
| Sidecar | `drawing_semantics_v1` (ad hoc rows) | separate `semantic.json` artifact shape | one `drawing_semantics_v2` path (`services/semantic/serialization.py`) |
| Performance @ 27k annotations | not benchmarked (never ran at that scale — projection only) | not separately benchmarked (dataclass-based like the unified model) | 0.85s end to end (construct 0.20s + `to_dict` 0.37s + `json.dumps` 0.28s), 45MB JSON |
