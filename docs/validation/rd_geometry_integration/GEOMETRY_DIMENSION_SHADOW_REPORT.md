# E3 — Member-vs-Callout Dimension Shadow Experiment

**Status: shadow measurement only.** Production `_looks_like_dimension` / `_looks_like_leader`
were not modified. CAP_450 unchanged. Human gold immutable.

- Document: `doc_0d910a43b4a021e3`
- Population: same 21 audited targets as E1/E2
- Script: `backend/scripts/rd_geometry_integration/dimension_shadow_experiment.py`
- Artifacts: `dimension_shadow_results.jsonl`, `dimension_shadow_summary.json`
- Renders: `dimension_shadow_renders/`

---

## 1. Executive conclusion

**Own-label numeric contamination is confirmed for 4 of the 6 E2 dimension losses.**

| Question | Answer |
| --- | --- |
| Does own-label numeric contamination explain observed dimension losses? | **Yes, for 4/6** (`W14X22 [25]`, `W21X44 [30]`, `W18X35 [35]`, `W18X35 [28]`) |
| How many recovered by V1/V2/V3? | **4 MEMBER_RECOVERED** among E2 dimension losses |
| Which variant? | V1, V2, and V3 all recover the same 4 own-label cases |
| W30X90 / `17K`? | **Not own-label.** Trigger text is unrelated nearby `17K`. All variants leave it `dimension` |
| Genuine dimensions preserved? | **Yes for the only available control** (`token_p18_1143`, nearby `7/8`) |
| Enough evidence for a production change? | **No.** False-flip safety is only weakly measurable (n=1 genuine-dimension control in this gold set) |

Verdict: own-label digit stripping is a **strongly supported** shadow remedy for a
specific subclass of losses, but **not** a complete fix for dimension misclassification,
and **not** yet justified as a production change.

---

## 2. Scope

- 21 audited targets (E1 fingerprints + E2 attributions)
- Primary: CAP_450 survivors (12)
- CAP losses (9): marked `NOT_APPLICABLE_CAP_LOSS`
- Gold has **no** `source_word_ids`; own-label ownership uses text containment of the gold
  label token inside document lines (bare `nK` load callouts excluded)
- Production helpers reused for baseline: `_nearby_text`, `_looks_like_leader`,
  `_looks_like_dimension`, `_classify_path`

---

## 3. Baseline funnel

```
21 raw
 ↓
12 CAP_450 survivors
 ↓
 5 member-eligible (V0)
 7 classified dimension (includes 1 ambiguous)
 0 classified leader
```

Matches E2.

---

## 4. Variant definitions

| Variant | Rule |
| --- | --- |
| **V0** | Production baseline (unchanged helpers) |
| **V1** | If the production nearby-text line is own-label, **strip digits** from that text before `_looks_like_dimension` |
| **V2** | **Exclude entire own-label lines** from nearby candidates; use next nearest non-own line |
| **V3** | Digit-bearing lines count only if their bbox **does not intersect** the own-label annotation bbox union. No invented distance threshold |

---

## 5. Results table (CAP_450 survivors, n=12)

| Metric | V0 | V1 | V2 | V3 |
| --- | ---: | ---: | ---: | ---: |
| Dimension | 7 | 2 | 2 | 2 |
| Leader | 0 | 0 | 0 | 0 |
| Member-eligible | 5 | **10** | **10** | **10** |
| MEMBER_RECOVERED | — | **4** | **4** | **4** |
| DIMENSION_PRESERVED | — | 2 | 2 | 2 |
| AMBIGUOUS_CHANGE | — | 1 | 1 | 1 |
| FALSE_MEMBER_RECOVERY | — | **0** | **0** | **0** |
| Member→dimension flips | — | 0 | 0 | 0 |

### E2 dimension-loss population (n=6)

| Variant | Recovered | Still dimension |
| --- | ---: | ---: |
| V1 | **4** | 2 (`p8_348` 17K, `p18_1143` 7/8) |
| V2 | 4 | 2 |
| V3 | 4 | 2 |

---

## 6. Per-target change matrix (V1)

| Token | Cap | V0 | Trigger | Attribution | V1 | Change |
| --- | ---: | --- | --- | --- | --- | --- |
| token_p8_332 | ✓ | dimension | `W14X22  [25]` | OWN_LABEL | line | MEMBER_RECOVERED |
| token_p8_337 | ✓ | dimension | `W21X44  [30]` | OWN_LABEL | line | MEMBER_RECOVERED |
| token_p8_340 | ✓ | line | *(empty)* | — | line | NO_CHANGE |
| token_p8_346 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p8_348 | ✓ | dimension | `17K` | UNRELATED_NEARBY | dimension | DIMENSION_PRESERVED |
| token_p8_351 | ✓ | line | *(empty)* | — | line | NO_CHANGE |
| token_p8_355 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p8_359 | ✓ | line | *(empty)* | RETRIEVAL_STAGE | line | NO_CHANGE |
| token_p8_367 | ✓ | dimension | `21KW14X22  [14]` | AMBIGUOUS | line | AMBIGUOUS_CHANGE |
| token_p8_381 | ✓ | dimension | `W18X35  [35]` | OWN_LABEL | line | MEMBER_RECOVERED |
| token_p8_430 | ✓ | dimension | `W18X35  [28]` | OWN_LABEL | line | MEMBER_RECOVERED |
| token_p18_1143 | ✓ | dimension | `7/8` | GENUINE | dimension | DIMENSION_PRESERVED |
| token_p18_1162 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p18_1169 | ✓ | rectangle | `(Fy = 50 ksi)` | RETRIEVAL_STAGE | rectangle | NO_CHANGE |
| token_p18_1178 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p18_1186 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p24_1359 | ✓ | line | `DWGS` | — | line | NO_CHANGE |
| token_p24_1360 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p24_1361 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p24_1377 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |
| token_p24_1385 | ✗ | — | — | — | — | NOT_APPLICABLE_CAP_LOSS |

---

## 7. W30X90 case study (`token_p8_348`)

Independently traced from PDF + `document.json` + production helpers:

| Field | Value |
| --- | --- |
| Own annotation line | `W30X90  [42]  c = 3/4"` |
| Production nearby text | **`17K`** |
| Nearby distance | 20.92 pt |
| Nearby bbox | `[1496.18, 1238.11, 1512.99, 1257.6]` |
| Trigger belongs to W30X90 annotation? | **No** |
| V0 | dimension (`looks_like_dimension`) |
| V1 | dimension (unchanged — `17K` is not own-label) |
| V2 | dimension (next non-own nearby remains `17K`) |
| V3 | dimension (`17K` bbox does not intersect own-label union) |
| Interpretation | **DIMENSION_UNRELATED_NEARBY_TEXT** — own-label variants cannot recover this case |

---

## 8. Own-label contamination cases

| Token | Trigger | Own-label line demonstrated? | V1 effect |
| --- | --- | --- | --- |
| token_p8_337 | `W21X44  [30]` | yes (contains `W21X44`) | digits stripped → member-eligible |
| token_p8_381 | `W18X35  [35]` | yes | recovered |
| token_p8_430 | `W18X35  [28]` | yes | recovered |
| token_p8_332 | `W14X22  [25]` | yes | recovered |

Mechanism: production `_nearby_text` returns the member’s own designation (which contains
digits). `_looks_like_dimension` only checks `length≥12` and “any digit in nearby text”,
so the annotation that *names* the member reclassifies the member stroke as a dimension.

---

## 9. Genuine dimension controls

Available in the audited CAP_450 survivors:

| Token | Trigger | Why treated as genuine control | Shadow result |
| --- | --- | --- | --- |
| token_p18_1143 | `7/8` | Fraction-like numeric text, not the `W10X33` label; schedule/table rule | DIMENSION_PRESERVED under V1/V2/V3 |

**The current gold population is insufficient to establish false-flip safety** for a
production change. n=1 preserved control is directionally reassuring (no
`FALSE_MEMBER_RECOVERY` observed) but not a safety proof.

---

## 10. Visual QA

Crops in `dimension_shadow_renders/` (blue=label, green=geometry, orange dashed=own-label
annotation, red=trigger text):

- `token_p8_348` — W30X90 vs red `17K`
- `token_p8_337`, `token_p8_381`, `token_p8_430`, `token_p8_332` — own-label contamination
- `token_p18_1143` — genuine `7/8` control
- `token_p8_367` — ambiguous

---

## 11. Interpretation

**Proven**

- 4/6 E2 dimension losses are own-label digit contamination under CAP_450.
- V1/V2/V3 recover those 4 without flipping the `7/8` control or the `17K` case.
- W30X90’s trigger is independently `17K`, not the W30X90 annotation.

**Strongly supported**

- Ignoring own-label numbers is the right *first* shadow remedy for the own-label subclass.
- Own-label stripping alone cannot fix unrelated nearby digits (`17K`).

**Uncertain / not measured**

- False-flip rate on a broad set of true dimension lines (only n=1 control here).
- Whether recovering these 4 members improves association accuracy (not tested).
- NO_LIMIT short-stroke leader problem (out of E3 scope; E2 already measured it).

---

## 12. Recommendation

**B. Run another deterministic diagnostic — do not productionize yet.**

Smallest next experiment:

> **E4 (diagnostic only): genuine-dimension control expansion on p8/p18/p24**
> Sample strokes that production already classifies as `dimension` whose nearby text is
> fraction/length-like and **not** an engineering-token designation; measure V1 false-flip
> rate on that control set. Gate: zero false member recoveries on that set + associated-8
> unchanged.

Only after that control set is large enough would a gated production-shadow change for
own-label digit exclusion be warranted.

Do **not** implement that production change in E3.
Do **not** start Retrieval V3.
Do **not** treat V1’s 4/6 recovery as general accuracy.

---

## Safety

| Check | Result |
| --- | --- |
| Gold SHA-256 | `0fad4291ff06ffa4e61c46f4ac923d7187455dd6b2f9b088481ab5e6b976b155` unchanged |
| `geometry_extractor.py` | unchanged |
| `retrieval.py` / `retrieval_v2.py` | unchanged |
| Tests | `test_rd_geometry_dimension_shadow.py` + phase + v2: **27 passed** |
