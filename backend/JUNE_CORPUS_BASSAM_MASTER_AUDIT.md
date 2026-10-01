# JUNE CORPUS + BASSAM RESEARCH — MASTER AUDIT (PHASE 0)

**Date:** 2026-09-12  
**Scope:** Read-only investigation. No production code changes, flag flips, training, OCR/ML installs, commits, or pushes.  
**Sources:** Estima3D repo (`estima3d-integration` @ `af743be` + dirty working tree), Bassam reports (Downloads), local structural PDFs used only as a **proxy** after Drive access failed.

---

## 1. Executive verdict

**OVERALL VERDICT: NOT READY — June Google Drive folder `testing projects` is not accessible from this environment.**

| Check | Result |
|---|---|
| Google Drive / connected-file API | **Unavailable** (no Drive MCP; `~/Library/CloudStorage` empty; no DriveFS mount; Spotlight finds no `testing projects`) |
| Claimed 40+ June PDFs inventoried | **0** |
| Defensible proxy inspected | **7** structural PDFs under `Desktop/PDF & Excel` (same family as the existing 8-doc eval set) |
| Bassam reports readable | **Yes** — both deep-research reports |
| Repo call-path audit | **Yes** |
| Safety policy (incomplete L/2L, Excel ≠ predictor, experimental flags off) | **Must keep** — proxy evidence **strengthens**, does not weaken |

**Implication:** Parts 4–7 and 9 cannot be finalized against the real June corpus. Priorities below use **proxy + prior Burrville/GCDC investigations** and must be re-validated when Drive access exists.

**What is still clear without June Drive:**

1. Bassam’s four-operation split (**normalization / repair / completion / association**) matches how this repo should evolve — not as a second takeoff engine.
2. Native PDF text is already the right default; OCR/GNN/VLM are not first work.
3. Incomplete-L/2L abstention and format≠completion must stay; catalog / Excel must not complete thickness.
4. Dense-page geometry caps + leader-dominated retention are the real member-bbox blockers — not “draw a box.”
5. First engineering work after corpus access should be **contract + inventory + grouping/normalization**, not corrected PDF or LambdaMART.

---

## 2. June corpus inventory

### 2.1 Access attempt (required source)

| Attempt | Outcome |
|---|---|
| Cursor Google Drive / connected files | No Drive tools in available MCP namespaces |
| `~/Library/CloudStorage` | Empty |
| Google DriveFS / File Provider mounts | Not present |
| Spotlight / filesystem search for `testing projects` | No matches |
| Agent instruction: do not ask user to copy **if** connected access works | Connected access **does not** work → corpus blocked |

**Accessible June corpus PDFs: 0.**  
**Claimed “40+” cannot be verified.**

### 2.2 Sampling strategy (proxy only — labeled as such)

Because the official folder is unreachable, a **proxy corpus** was used for technical evidence. This is **not** June’s `testing projects` set.

| Metric | Value |
|---|---|
| Official June files available | **0** |
| Proxy files fully page-counted | **7** |
| Proxy files text/shape inspected | **7** |
| Pages in proxy | **262** total (17–81 per file) |
| Pages with deep text+drawing sampling | ~11 pages/file (first, early, mid, late) |
| Shape/family scan | Full PDF when ≤50 pages; GCDC (81p) = sample + early/late bands |
| Sampling method | Prefer diversity (notes, framing, details, large sheets); not “easiest first” |

**Proxy paths (local):**

| # | Project | File | Bytes | Pages | Native text | Vector drawings |
|---|---|---|---:|---:|---|---|
| 1 | 1200 K | `1200 K_Permit_Bid_Dwgs - Structural.pdf` | 18.4 MB | 39 | Yes | Yes (dense) |
| 2 | Burrville | `Burrville ES - ST.pdf` | 1.8 MB | 29 | Yes | Yes |
| 3 | GCDC | `GCDC Building 4 - ST1.pdf` | 44.9 MB | 81 | Yes | Yes |
| 4 | H5 Herndon | `ST.pdf` | 3.3 MB | 23 | Yes | Yes (very dense) |
| 5 | Ketcham | `Structure - Copy.pdf` | 5.5 MB | 17 | Yes | Yes |
| 6 | Sidwell | `03 - SFSLS_…_STRUCTURAL….pdf` | 13.3 MB | 45 | Yes | Yes |
| 7 | Springhill ES | `ST - Springhill Lake.pdf` | 2.4 MB | 28 | Yes | Yes |

These align with uploads / 8-doc eval IDs already in-repo (`doc_0d910a…` Burrville, `doc_47dc7e…` GCDC, `doc_f6ddc4…` Springhill, etc.).

### 2.3 Proxy inventory highlights (only fields reliably observed)

| Signal | Observation |
|---|---|
| Discipline | Structural (ST / S-sheets / notes) |
| Drawing types | Notes/legends, schedules, framing plans, details, sections — present across set |
| Native PDF text | **All 7** have substantial extractable text (tens of thousands of chars on sampled pages) |
| OCR-like corruption (`U+FFFD`, `W8XI0`) | **Not observed** as a dominant pattern in raw native text |
| Rotated text | **All 7** — hundreds of non-horizontal lines on sampled pages |
| Fractions | Heavy (hundreds–1000+ fraction hits per set) |
| Decimal dims / HSS | Common; 1200 K explicitly labels **HSS (ROUND)** vs **HSS (RECT.)** |
| W / HSS / L / PL | Dominant families; 2L present (GCDC, Burrville, Sidwell) |
| Incomplete angles (regex legs-only) | Springhill **L4X4**×7 on p9; GCDC **L4X4** / **2L4X4**; Sidwell/Burrville **L4X3**/`L5X3` (many are schedule false-positives for `L5X3-1/2X…`) |
| Legend / schedule / TYP language | Strong across set |
| Brackets / callout suffixes | Common (esp. H5, 1200 K) |
| Dense vector pages | Nearly every framing/detail page ≫ `_DENSE_PAGE_CAP` (450); peaks **~35k–41k** drawings/page |

**Do not treat proxy counts as June corpus frequencies.**

---

## 3. Current architecture (repository call-path audit)

**Inference owner:** `backend/services/prediction/orchestrator.py` only.  
**HEAD:** `af743be`. Dirty tree includes incomplete-L abstention, `member_geometry`, first-run eval scripts (not all on HEAD).

### 3.1 Capability status

| Capability | Status | Notes |
|---|---|---|
| PDF / native text extraction | **PRODUCTION** | `pdf_parser.py` / `extraction_engine.py` (PyMuPDF) |
| Text coordinates / bbox | **PRODUCTION** | words/spans/lines → prediction `bounding_box` |
| Text quads | **NOT PRESENT** | Axis-aligned boxes only |
| Token extraction | **PRODUCTION** | `document_intelligence` → `engineering_tokens` |
| Token grouping | **PRODUCTION** | `annotation/fragment_grouper.py` (same-line; not full Bassam graph) |
| Engineering parser/filter | **PRODUCTION** | `engineering_object_filter.py` |
| `structural_parser` | **PRODUCTION** | Plausibility + parse helpers |
| Normalization | **PRODUCTION** | Format/compact normalize — **not** semantic completion |
| Catalog / `catalog_form` | **PRODUCTION** | Verify/spell only |
| TF-IDF candidates | **PRODUCTION** | Candidate retrieval; incomplete-L path skips |
| ML label reconstruction | **SHADOW** | Package + hook; `ML_LABEL_RANKER_*` default **false** |
| Document prior / legend | **PRODUCTION** | `DOCUMENT_PRIOR_ENABLED` default true |
| Drawing Language Profile | **PRODUCTION** (read-only attach) | `legend_profile` / `build_drawing_language`; LLM slice **off** |
| Geometry extraction | **PRODUCTION** | `geometry_extractor.py` via PDF adapter |
| Geometry filtering | **PRODUCTION** | Dense cap **450**, structural-first sort |
| Geometry normalization | **PRODUCTION** | Collinear merge |
| Leader detection | **PRODUCTION** | Heuristic `kind=leader` |
| Spatial association | **PRODUCTION** | Default on; STRtree / leader-aware |
| Graph construction | **PRODUCTION** | Topology; GraphSAGE scoring separate |
| Member resolution | **PRODUCTION** | Gating for takeoff eligibility |
| `member_geometry` bbox | **UNCOMMITTED** | Dirty tree; evidence-only; null when unresolved |
| First-run evaluation | **UNCOMMITTED** | `evaluate_first_run.py` + guide; artifacts already persist |
| Review / explainability | **PRODUCTION** | Explanation contract + Drawing Review |
| PDF rewriting | **NOT PRESENT** | |
| `drawing_semantics.json` | **NOT PRESENT** | |
| Rhino / Grasshopper | **DEFERRED** | 3DM stub; no GH contract |
| Graph v2 scorer | **ORPHANED / UNCOMMITTED** | Eval scripts/tests; not wired |
| Learned fusion / GraphSAGE / geom-missing / VLM / prod LLM | **EXPERIMENTAL / OFF** | Defaults false / absent |

### 3.2 Flag defaults (must stay)

| Flag | Default |
|---|---|
| `LEARNED_FUSION_ENABLED` | false |
| `GRAPHSAGE_SECTION_SCORING_ENABLED` | false |
| `GEOMETRY_MISSING_LABEL_INFERENCE_ENABLED` | false |
| `ML_LABEL_RANKER_ENABLED` | false |
| `ML_LABEL_RANKER_SHADOW` | false |
| `LEGEND_PROFILE_LLM_ENABLED` | false |

### 3.3 Production flow (simplified)

```text
PDF → extract (text+bbox+tokens) → fragment group → engineering filter
    → legend_profile / document_prior
    → geometry extract/filter/normalize (+ leaders)
    → graph + spatial association
    → fusion → orchestrator.predict (normalize → catalog/TF-IDF → prior → review)
         [dirty: incomplete L/2L abstain]
    → [dirty: member_geometry attach, evidence only]
    → member_resolution → takeoff partition → review artifacts
```

Excel remains **post-prediction comparison only**, never a prediction input.

---

## 4. Bassam research summary

**Reports read:**

1. *Semantic Repair Pipeline for Structural Steel PDFs* (`deep-research-report (1).md`)  
2. *Upstream Structural Drawing Semantic Correction System* — Bassam Tarshishi, 2026-09-11 (`deep-research-report (3).md`)

### 4.1 Product boundary (agree)

> Upstream **semantic preprocessor** for imperfect structural PDFs → existing Rhino/Grasshopper takeoff.  
> **Not** a second quantity / takeoff engine.

Deliverables: authoritative **`drawing_semantics.json`**, optional **corrected PDF** later.

### 4.2 Four operations (preserve terminology)

| Operation | Example | Authority |
|---|---|---|
| **Normalization** | `HSS8X8X0.375` → `HSS8X8X3/8` | Deterministic grammar + catalog |
| **Repair** | `W8XI0` → `W8X10` | Corruption model + candidates |
| **Completion** | `W8` → `W8X10` | Drawing-local evidence only |
| **Association** | Label → member geometry | Leaders / paths / spatial |

Mixing these into one LLM “fix” step is explicitly rejected.

### 4.3 Architecture recommendations (condensed)

- Native PDF before OCR; page classifier; selective OCR only  
- Oriented geometry (**quads**), not bbox-only; synthetic stable IDs  
- Rotation-aware semantic grouping (proximity graph / union-find; brackets)  
- Deterministic structural grammar; **round HSS ≠ rectangular fraction rules**  
- Catalog-constrained candidates; TF-IDF baseline → optional LambdaMART  
- Confidence / abstention / risk-coverage; SOURCE_VERIFIED vs PROPOSED_INFERENCE  
- Drawing Language Profile as evidence registry for completion  
- Leader tracing + geometry role filtering before GNN  
- JSON sidecar first; corrected PDF via careful redact+reinsert (preserve vectors)  
- Human review overlay; Grasshopper consumes semantics  
- GNN / VLM / heavy OCR **after** measured ceilings  

### 4.4 Bassam’s suggested early experiments

1. Grouping benchmark (~250 annotations)  
2. Normalizer false-correction audit  
3. Protect DLP + source-verified relations  
4. 50–100 human label↔geometry links  
5. JSON contract with GH; rewrite A/B later  

---

## 5. Corpus-derived problem taxonomy

**Frequency labels:** High / Medium / Low / Unknown — from **proxy + prior 8-doc work**, not June Drive.

| # | Problem | Frequency (proxy) | Severity | Current handling | Failure | Proposed direction | Det / Ctx / ML | Safety |
|---|---|---|---|---|---|---|---|---|
| 1 | Formatting / normalization | High | Med | `catalog_form`, compact normalize | Spacing/`×`/case still vary | Strengthen grammar canonicalize | Det | Low if format-only |
| 2 | OCR-like corruption | Low (native) | Med | TF-IDF / ranker shadow | Rare on this CAD-export set | Defer OCR engines | Det→Repair later | — |
| 3 | Character substitutions | Low–Med | Med | Ranker shadow | `I`/`1` etc. when present | Repair ranking later | Det+ML later | Abstain if ambiguous |
| 4 | Spacing | High | Low | Normalize | Still fragments | Grouping + normalize | Det | Low |
| 5 | Separator errors | Med | Med | Normalize | `x`/`×`/`*` | Grammar | Det | Low |
| 6 | Split tokens | High | High | Fragment grouper | Brackets/rotated splits miss | Rotation-aware grouping | Det | Low |
| 7 | Fractions | High | Med | Partial | Mixed unicode/ASCII | Family-aware fraction rules | Det | Avoid arch dims |
| 8 | Decimal dimensions | High (HSS) | High if wrong | Partial HSS rules | Round vs rect confusion risk | Grammar by HSS class | Det | High if global fractionize |
| 9 | Wrong field order | Unknown | High | Limited | Rare? | Grammar reject | Det | Abstain |
| 10 | Abbreviations | High | Med | Legend profile / notes | Incomplete maps | DLP SOURCE_VERIFIED | Ctx | High if auto-apply |
| 11 | HSS naming variants | High | High | Catalog form | `HSS8x4"` / incomplete HSS | Grammar + incomplete abstain | Det | High |
| 12 | Missing dimensions | Med | High | Incomplete-L abstain (dirty) | TF-IDF used to complete (pre-gate) | Keep abstain; evidence completion later | Ctx only | **Critical** |
| 13 | Incomplete L | Med (Springhill/GCDC) | Critical | Dirty abstain | HEAD lacks gate | Commit + keep | Ctx for complete | **Critical** |
| 14 | Incomplete 2L | Low (GCDC) | Critical | Dirty abstain | Must not invent from single L | Keep | Ctx | **Critical** |
| 15 | Plausible-but-wrong | Med | Critical | Review / abstain | Catalog nearest neighbor | Never auto | Abstain | **Critical** |
| 16 | Legend relationships | High | High | Legend profile attach | Not full SOURCE_VERIFIED completion | Promote evidence registry | Ctx | High |
| 17 | Schedule relationships | High | High | Partial | Lintels etc. need scope | Table+scope evidence | Ctx | High |
| 18 | Detail relationships | High | High | Weak | TYP/detail chains | Explicit links | Ctx | High |
| 19 | Label↔geometry association | High | High | Spatial + graph | Wrong nearest stroke | Leader-aware + filter | Det→rank | Med |
| 20 | Leader association | High | High | Heuristic leaders | Leaders dominate retained set | Trace tip → member | Det | Med |
| 21 | Geometry coverage | High | Critical | Cap 450 | Drop most strokes on dense pages | Role-aware retention | Det | Perf risk |
| 22 | Member identification | Med | High | `member_geometry` WT | ~low resolve rate historically | Better filter+trace | Det | Don’t fake bbox |
| 23 | Member bbox | Med | High | Null if unresolved | Cap/leaders/ambiguity | Prerequisite #21–22 | Det | **No fake boxes** |
| 24 | Text bbox | High | Med | Present | No quads; rotation inflate | Quads later | Det | Low |
| 25 | Repeated annotations | High | Med | Dedupe / resolution | Over-count risk | Keep gating | Det | Med |
| 26 | Duplicate labels | Med | Med | Duplicate audit | — | Metrics | Det | Low |
| 27 | Missing extracted labels | Unknown | High | First-run metrics partial | Need human recall set | Annotation subset | — | — |
| 28 | Table extraction | Med | Med | Limited | Schedules underused | Native tables first | Det | Low |
| 29 | Review requirements | High | High | Review queue exists | Semantics ops not typed | Tag norm/repair/complete/assoc | — | — |
| 30 | Corrected PDF | Stakeholder ask | High risk | Absent | Vector wipe risk | After JSON proven | Det write | High |
| 31 | JSON semantic output | Stakeholder ask | High | Absent | GH needs contract | Schema first | Contract | Low |

---

## 6. Bassam recommendation validation

Classifications use: **SUPPORTED BY JUNE CORPUS** | **PARTIALLY SUPPORTED** | **NOT OBSERVED** | **NOT TESTABLE** | **ALREADY SOLVED** | **DEFER** | **REJECT / UNSAFE**

Because June Drive = 0 files, “June corpus” below means **proxy + prior investigations**, and **NOT TESTABLE on official June set** applies everywhere until access is restored.

| ID | Recommendation | Class | Evidence / notes |
|---|---|---|---|
| A | Native PDF before OCR | **SUPPORTED** (proxy) / **ALREADY SOLVED** path | All 7 proxy PDFs are born-digital with rich native text; OCR not required first |
| B | Rotation-aware grouping | **SUPPORTED** | Hundreds of rotated lines/file; current grouper is same-line-centric |
| C | Split annotation grouping | **PARTIALLY SUPPORTED** | Brackets common; fragment grouper exists but incomplete vs Bassam graph |
| D | Bracket suffix grouping | **SUPPORTED** | High bracket counts (e.g. H5, 1200 K) |
| E | Deterministic structural grammar | **SUPPORTED** | Diverse W/HSS/L/PL; format noise |
| F | Fraction normalization | **SUPPORTED** | Heavy fractions; must stay family-aware |
| G | HSS round vs rect/square | **SUPPORTED** | 1200 K literal “HSS (ROUND)” / “HSS (RECT.)”; Sidwell `HSS6X0.500` vs fractional walls |
| H | Normalization vs repair separation | **SUPPORTED** (policy) | Repo already mixes candidate repair with prediction; ops should be typed |
| I | Evidence-based completion | **SUPPORTED** + **REJECT/UNSAFE** if fuzzy | Burrville: both `L4X4X1/4` and `L4X4X3/8`; no global map; Springhill bare `L4X4` |
| J | Drawing Language Profile | **PARTIALLY SUPPORTED** / **ALREADY SOLVED** attach | Legend profile exists; not Bassam’s full SOURCE_VERIFIED completion engine |
| K | Confidence / abstention | **SUPPORTED** / partial | Incomplete-L abstain (dirty); risk-coverage metrics incomplete |
| L | Leader-aware geometry association | **SUPPORTED** | Leaders dominate retained geometry; association exists but weak |
| M | Geometry filtering | **SUPPORTED** | Cap 450; pages with 10k–40k drawings |
| N | Member-level geometry bbox | **PARTIALLY SUPPORTED** | Useful vectors exist; trustworthy bbox **not** yet; leave unavailable when unresolved |
| O | JSON semantic sidecar | **NOT OBSERVED** as product / **SUPPORTED** as need | Meeting + Bassam; not in repo |
| P | Corrected PDF | **DEFER** | Stakeholder desire; unsafe before semantics+review |
| Q | Human review | **ALREADY SOLVED** base / extend | Review UI exists; needs operation typing |
| R | LambdaMART / XGBoost | **DEFER** | TF-IDF production; ML ranker shadow only; no June-proven need to enable |
| S | OCR | **DEFER** | Not needed on proxy CAD exports; revisit if June scans appear |
| T | GNN / GraphSAGE | **DEFER** / keep **REJECT** for production enable now | Measure leader rules first; flag stays false |
| U | VLM | **DEFER** / **REJECT** for now | No production path; not justified by proxy |

### Per-recommendation detail (minimum set)

**A — Native first:** Proxy shows native text + vectors. Component: `pdf_parser`. Failure: none systemic. Det sufficient. Risk: low. Validate: page classifier on June when available.

**B–D — Grouping:** Rotated + brackets everywhere. Component: `fragment_grouper`. Failure: split/rotated compounds. Det graph likely enough before ML. Gate: grouping F1 on annotated subset.

**E–G — Grammar / HSS:** High. Component: `structural_parser` + `catalog_form`. Failure: round HSS fractionized incorrectly if naive. Det required. Gate: round vs rect fixtures from 1200 K / Sidwell.

**H–I — Norm vs completion:** Incomplete L on Springhill/GCDC; Burrville multi-thickness. Component: dirty abstain + prior. Failure if TF-IDF completes. **Ctx required for completion; ML not justified to auto-complete.** Risk: critical. Gate: zero unsafe L/2L completions.

**J — DLP:** Legends/schedules dense. Component: `legend_profile`. Gap: SOURCE_VERIFIED scoped maps. Ctx. Gate: conflict injection tests.

**K — Abstention:** Already policy. Extend risk-coverage. Gate: first-run unsafe_completion = 0 on incomplete set.

**L–N — Geometry:** Cap drops most strokes; leaders ≫ members in retention (Burrville framing QA: tens of thousands leaders). `member_geometry` correctly returns unavailable. Prerequisites: role-aware retention + tip tracing. **Do not invent bbox.**

**O–Q — Sidecar / PDF / review:** Contract + review before rewrite.

**R–U — ML/OCR/GNN/VLM:** Defer until grouping/normalize/geometry baselines measured on real June set.

---

## 7. Safety audit

### 7.1 Explicit checks (unchanged)

| Rule | Status |
|---|---|
| `L4X4` ↛ `L4X4X1/4` without explicit drawing evidence | **KEEP** — Burrville proves both 1/4 and 3/8 exist; Springhill has bare `L4X4` needing abstain |
| Catalog existence ≠ thickness evidence | **KEEP** |
| `2L4X4` not inferred from single-L | **KEEP** — GCDC has explicit `2L4X4` incomplete; must not invent |
| Excel = comparison/reference only | **KEEP** |
| Unlabeled geometry ≠ takeoff truth | **KEEP** |
| Experimental flags remain off | **KEEP** (verified defaults) |

### 7.2 Additional risks observed (document only)

1. **Schedule false-positive incomplete angles** (`L5X3` from `L5X3-1/2X5/16`) — detection must not strip thickness that is present on the same glyph run.  
2. **GCDC note `HSS8x4" = HSS8x4x1/4`** — looks like completion evidence; still requires scoped SOURCE_VERIFIED application, not global TF-IDF.  
3. **Dense-cap performance** — raising cap without role filter previously caused Analyze timeouts; unsafe to “just keep everything.”  
4. **Corrected-PDF redaction** — Bassam warns default redaction can delete vectors; treat as high-risk.  
5. **Incomplete-L gate not on HEAD** — operational risk if dirty tree is lost.

---

## 8. Geometry audit (proxy + prior Burrville framing QA)

Answers to required questions:

| # | Question | Answer |
|---|---|---|
| 1 | Useful structural vectors retained? | **Partial** — long strokes exist, but dense pages retain a thin slice after cap |
| 2 | Loss from dense-page filtering/caps? | **Severe on framing/details** — sampled pages often 2k–40k drawings vs cap **450** (earlier QA used 1200; still dropped thousands) |
| 3 | Leaders dominating retained geometry? | **Yes** — Burrville framing QA: leaders ~23k vs lines+polylines ~5k in aggregate object counts; retained kinds still leader-heavy |
| 4 | Leaders deterministically traceable to members? | **Not proven at scale** — tip/proximity heuristics exist in WT `member_geometry`; not validated as trustworthy production association |
| 5 | Member strokes sufficiently available? | **Often after cap: insufficient / mixed with junk** |
| 6 | Multiple primitives → one member? | **Partially** — collinear merge + multi-id union in WT; incomplete |
| 7 | One member, multiple labels? | **Possible on drawings**; resolution/dedupe exists; association still weak |
| 8 | One primitive shared by multiple labels? | **Yes risk** — WT uses claim/ambiguity → unavailable |
| 9 | Stable member-level ID? | **Hash ID when resolved**; unstable if primitives churn under cap |
| 10 | Trustworthy member bbox? | **NO for general production** — leave `geometry_bbox` / member bbox **unavailable** when unresolved |

**Exact blocker for trustworthy member bbox:**

1. Dense-page cap drops most candidate member strokes.  
2. Retained set is leader-dominated → nearest-stroke association is biased.  
3. No validated leader-tip → member-stroke tracer with gold associations.  
4. No stable primitive identity across cap strategy changes.

**Prerequisite before claiming member bbox:** role-aware retention (prefer long structural strokes; keep leaders as relation primitives separately) + measured leader association precision on a human-labeled subset ≥50–100 links.

---

## 9. Priority matrix

| Priority | Problem | June evidence | Current capability | Gap | Recommended implementation | Expected impact | Risk | Dependencies | Validation gate |
|---|---|---|---|---|---|---|---|---|---|
| **P0** | Official corpus inaccessible | Drive folder not mounted | — | Cannot validate roadmap | Restore Drive access + frozen manifest (hashes, pages) | Unblocks Phase 0→1 | Ops | User/Drive | `testing projects` listed; N PDFs hashed |
| **P0** | Incomplete L/2L safety not on HEAD | Proxy Springhill/GCDC incomplete L/2L | Dirty abstain | Commit/protect | Land abstention + tests on branch | Stops unsafe completion | Low | Dirty tree | 0 unsafe completions on incomplete set |
| **P0** | Ops typing: norm ≠ repair ≠ completion ≠ association | Bassam + meeting | Mixed in prediction | Contract | Define semantic operation fields (no behavior change yet) | Clarifies product | Low | None | Schema review with partners |
| **P1** | Rotation/bracket grouping | Proxy rotated+brackets | Same-line grouper | Graph grouping | Improve `fragment_grouper` | Fewer split labels | Med | Contract IDs | Grouping F1 on ≥250 labels |
| **P1** | HSS / fraction canonicalization | 1200 K round vs rect | Partial | Grammar by family | Deterministic canonicalizer | Catalog match ↑ | Med if wrong | Catalog fixtures | 0 round-HSS false fractionize |
| **P1** | First-run / multi-metric eval | Stakeholder ask | Partial scripts | June harness | Freeze proxy+June eval protocol | Measurable progress | Low | Corpus | Per-subsystem metrics reported |
| **P1** | Geometry retention quality | Dense pages | Cap 450 | Role-aware keep | Filter leaders vs members for retention | Assoc recall ↑ | Perf | Cap strategy tests | Cap applied ⇒ member stroke recall vs gold sample |
| **P2** | SOURCE_VERIFIED DLP completion | Legends/schedules | Legend attach | Scoped maps | Evidence registry only | Safe completion later | High if auto | Grouping+grammar | Conflict → abstain tests |
| **P2** | Leader association | Leader-heavy pages | Heuristics | Tip trace gold | Deterministic tracer | Assoc precision ↑ | Med | Retention | Precision@1 on labeled links |
| **P2** | `drawing_semantics.json` | Stakeholder/GH | Absent | Schema+writer | Sidecar export (read model) | GH path | Med | Contract | Schema validates; no takeoff change |
| **P2** | Member bbox | Partial WT | Unresolved often | Trust | Only after assoc gate | Review UX | High if fake | L+M | Availability only when precision gate met |
| **DEFER** | LambdaMART enable | Not proven needed | TF-IDF + shadow | — | Keep shadow | — | High | Gold repair set | Shadow beats TF-IDF |
| **DEFER** | OCR stack | Not seen on proxy | Native works | — | Page classifier only | — | Cost | June scans? | OCR only if native fails |
| **DEFER** | GNN / GraphSAGE | Research later | Flag off | — | Keep off | — | High | Assoc ceiling | Measured plateau |
| **DEFER** | Corrected PDF | Mike ask | Absent | Safe write | After JSON+review | Downstream pickup | **Very high** | Human accept | Round-trip text; vectors intact |
| **REJECT** | Fuzzy L thickness / Excel-as-GT / unlabeled geom takeoff | Burrville multi-thickness | Abstain | — | Do not build | Prevents wrong steel | — | — | Policy tests stay red if violated |

---

## 10. Recommended implementation roadmap (evidence-ordered)

Bassam’s phase list is **reordered** for this repo + proxy evidence:

### PHASE 0b — Corpus unlock (blocking)

- **Objective:** Access June `testing projects`; freeze inventory.  
- **Files:** Offline manifest under `training/eval_cache_backups/june_corpus/` (hashes only; no PDF commit).  
- **Prerequisite:** Drive sync or readable path.  
- **Gate:** Actual file count + SHA-256 list.  
- **Production impact:** None.

### PHASE 1 — Protect safety + semantic contract

- **Objective:** Commit incomplete-L/2L abstention; add operation-typed semantic contract (fields only).  
- **Components:** `label_ranker_hook.py`, `orchestrator.py`, `database_loader.catalog_form`, new contract module/docs; tests.  
- **Benefit:** Safety on HEAD; shared language with Bassam/GH.  
- **Risk:** Low if behavior-preserving for complete labels.  
- **Gate:** Incomplete abstention tests green; no experimental flags on.  
- **Production impact:** Safer predictions; no takeoff formula change.

### PHASE 2 — First-run validation harness on frozen corpus

- **Objective:** Multi-metric reports (extract/group/norm/repair/complete/abstain/bbox/assoc).  
- **Components:** `evaluate_first_run.py`, extend taxonomy; June subset.  
- **Gate:** Report generates without Excel-as-gold.

### PHASE 3 — Improved grouping (rotation + brackets)

- **Objective:** Semantic groups for split/rotated/bracketed labels.  
- **Components:** `fragment_grouper.py`, pdf span directions.  
- **Gate:** Grouping benchmark vs human labels.

### PHASE 4 — Deterministic canonicalization (grammar + HSS)

- **Objective:** Normalization only; round vs rect HSS.  
- **Components:** `structural_parser`, `catalog_form`, fixtures from 1200 K/Sidwell.  
- **Gate:** False-correction rate near-zero on held negatives (arch dims, round HSS).

### PHASE 5 — Repair (candidates) without auto-accept

- **Objective:** Rank repairs for review; TF-IDF baseline; LambdaMART **shadow only**.  
- **Gate:** Risk-coverage; no live enable without win.

### PHASE 6 — Evidence / DLP SOURCE_VERIFIED (completion)

- **Objective:** Scoped legend/schedule maps; abstain on conflict.  
- **Components:** `legend_profile`, `document_prior`, project rules.  
- **Gate:** Burrville-style conflict tests; no global L4X4→thickness.

### PHASE 7 — Geometry coverage + leader association

- **Objective:** Role-aware retention; leader tip tracing; measure assoc.  
- **Components:** `geometry_extractor.py`, `spatial_association.py`, `member_geometry.py`.  
- **Gate:** Labeled association precision; Analyze latency budget held.

### PHASE 8 — Member geometry bbox (conditional)

- **Objective:** Emit bbox **only** when association gate met; else unavailable.  
- **Gate:** Precision threshold; no fabricated boxes.

### PHASE 9 — `drawing_semantics.json`

- **Objective:** Authoritative sidecar for GH.  
- **Gate:** Schema validation; partner review.

### PHASE 10 — Review UX for four operations

- **Objective:** Accept/edit/abstain by operation type.  
- **Components:** existing review + explanation contract.

### PHASE 11 — Corrected PDF (optional)

- **Objective:** Accepted replacements only; preserve vectors.  
- **Gate:** Round-trip extract; visual/vector diff.

### PHASE 12 — Grasshopper contract

- **Objective:** Consume sidecar; A/B vs PDF rewrite.  
- **Prerequisite:** Mike GH access + schema agreement.

---

## 11. Phase gates (summary)

| Phase | Measurable gate |
|---|---|
| 0b | June PDFs listed + hashed |
| 1 | Incomplete unsafe completion = 0; contract reviewed |
| 2 | Multi-metric first-run report on ≥1 June + proxy |
| 3 | Grouping F1 improvement on annotated subset |
| 4 | Normalization false-correction ≤ agreed bound; round HSS OK |
| 5 | Repair shadow metrics only; ENABLED stays false |
| 6 | Completion only with SOURCE_VERIFIED; conflicts abstain |
| 7 | Assoc precision on gold links; latency OK |
| 8 | Member bbox available iff gate; else null |
| 9 | Sidecar schema stable |
| 10 | Reviewers can mark ops |
| 11 | Rewrite safe on accepted set |
| 12 | GH reads sidecar successfully |

---

## 12. Validation strategy (June 40+ → fixed corpus)

1. **When accessible:** copy-free read from Drive; build **manifest** (path, size, pages, SHA-256, project name). Do **not** commit PDFs.  
2. **Do not** treat PDFs or Excel as automatic semantic GT.  
3. **Representative subset first** (~8–12 sheets / ~10 projects): notes+legend, framing, detail, schedule, dense page, rotated labels, incomplete L if present, HSS round+rect.  
4. **Smallest useful human annotation** (per Bassam-ish record):  
   - source fragments + group id  
   - operation type (norm/repair/complete/none)  
   - canonical label or abstain  
   - evidence cite for completion  
   - optional geometry link (50–100 total to start)  
5. **Metrics separate:** extraction recall, grouping F1, norm accuracy, repair top-k, completion precision, abstention risk-coverage, text bbox/quad coverage, geometry assoc, member bbox availability+precision, duplicates, missing labels, review decisions.  
6. Keep existing **8-doc proxy-gold** as internal regression; June is stakeholder validation corpus.

---

## 13. Open blockers

1. **CRITICAL:** Google Drive `testing projects` inaccessible → official inventory/frequencies unknown.  
2. Incomplete-L/2L safety + first-run tooling largely **uncommitted**.  
3. Trustworthy **member bbox** blocked by dense-cap + leader dominance (see §8).  
4. No `drawing_semantics.json` / GH contract yet.  
5. Bassam “commit DLP prototype” is partly stale — legend profile is in-tree; still need SOURCE_VERIFIED completion semantics.  
6. Partner GH access (Mike) still external.

---

## 14. Exact FIRST implementation task

**Task:** Restore agent-readable access to June’s Google Drive folder `testing projects`, then produce a frozen corpus manifest (filename, bytes, page count, SHA-256, project name) and re-run Part 1 inventory — **before** any Bassam pipeline feature work.

**Why first:** Every PART 4–7 priority claim is provisional without the real 40+ set. Building grouping/JSON/PDF rewrite against the 7-file proxy alone would bake in selection bias.

**Repository area:** Ops + `backend/training/eval_cache_backups/june_corpus/MANIFEST.json` (manifest only; no PDF ingestion into git).  

**Dependency:** Drive mount, shared link path, or Cursor connected-files that actually resolve.  

**Validation gate:** Manifest lists all accessible PDFs; page counts succeed via PyMuPDF; document states actual N (not assumed 40).

---

## What we should NOT build yet

| Item | Why |
|---|---|
| OCR engine install / OCRmyPDF pipeline | Proxy PDFs are native-text CAD exports; cost ≫ benefit until June shows scans |
| Enable LambdaMART / `ML_LABEL_RANKER_ENABLED` | Shadow only until repair gold + risk-coverage win |
| Enable GraphSAGE / learned fusion / geometry-missing inference | Flags off; association ceiling not measured |
| VLM / production LLM completion | Violates evidence rules; Burrville multi-thickness |
| Automatic L/2L thickness completion | Explicitly unsafe |
| Excel-as-semantic-GT or predictor | Meeting + repo invariants |
| Corrected PDF writer | Vector wipe risk; no accepted decision stream yet |
| Fake member bboxes | Cap/leader blockers; null is correct |
| GNN line classifier | Premature before leader-rule baseline |
| Second takeoff / quantity engine | Out of product boundary |
| Blind copy of Bassam’s full stack in one phase | June evidence missing; sequencing must stay gated |

---

## FINAL DECISION

### OVERALL VERDICT

**NOT READY — June Google Drive folder `testing projects` is not accessible (0 official PDFs inventoried).**

Proxy work (7 PDFs + prior Burrville/GCDC/Springhill analyses + Bassam reports + repo audit) is sufficient to **draft** the roadmap above, not to close Phase 0 against the real corpus.

### TOP 5 IMPLEMENTATION TASKS

1. **Unlock June corpus + freeze MANIFEST**  
   - Area: ops / `training/eval_cache_backups/june_corpus/`  
   - Why: Official evidence for all priorities  
   - Evidence: Drive access failed this session  
   - Dependency: Connected Drive  
   - Gate: N PDFs hashed + page-counted  

2. **Land incomplete L/2L abstention + catalog punct safety on the integration branch**  
   - Area: `label_ranker_hook.py`, `orchestrator.py`, `database_loader.py`, tests  
   - Why: Prevents catalog/TF-IDF inventing thickness  
   - Evidence: Springhill bare `L4X4`; GCDC `2L4X4`; Burrville dual thicknesses  
   - Dependency: Preserve dirty tree  
   - Gate: Abstention tests; 0 unsafe completions on incomplete set  

3. **Define `drawing_semantics` / four-operation contract (schema only)**  
   - Area: new contract module + docs; no production rewrite  
   - Why: Aligns repo with Bassam/GH without enabling unsafe completion  
   - Evidence: Meeting + both research reports  
   - Dependency: Task 1 preferred for examples  
   - Gate: Partner-readable schema; maps to existing prediction fields  

4. **Rotation- and bracket-aware grouping upgrade**  
   - Area: `fragment_grouper.py` / extraction path  
   - Why: Highest-frequency deterministic win on proxy  
   - Evidence: Rotated lines + brackets on all 7 proxy PDFs  
   - Dependency: Stable span IDs from contract  
   - Gate: Grouping benchmark on annotated subset  

5. **Role-aware dense-page geometry retention + leader association measurement**  
   - Area: `geometry_extractor.py`, `member_geometry.py`, eval script  
   - Why: Unblocks honest member bbox later  
   - Evidence: Pages with 10k–40k drawings; leader-dominated retention  
   - Dependency: Human assoc labels (small set)  
   - Gate: Assoc precision + latency; bbox remains null below threshold  

### RECOMMENDED FIRST IMPLEMENTATION TASK

**Restore access to June’s `testing projects` Drive folder and publish a frozen corpus MANIFEST (hashes + page counts) — no production behavior changes.**

Once that lands, the first *code* implementation task should be **#2 (incomplete L/2L abstention on HEAD)**, then **#3 (semantic contract)**.

---

*End of Phase 0 audit. No production code modified. No commit. No push.*
