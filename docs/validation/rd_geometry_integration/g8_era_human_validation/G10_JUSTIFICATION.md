# G10 Justification Gate

**Gate: `NOT_JUSTIFIED`**

## Pattern
Long LINE preferred over short SEGMENT/plate tip target under leader mode (kind prior + segment penalty + retained provenance; near-tied tip distance).

## Counts
- Relevant cases in this review supporting the pattern: **1**
- Failures vs human ownership: **1**
- Token IDs: `['token_p24_1359']`

## Current G9 behavior
On token_p24_1359 G9 ASSOCIATED rnd_raw_p24_480 (405pt LINE) over raw_p24_10#seg1 (27pt SEGMENT). On all other VALID_MEMBER cases in this 27, G9 selected candidate equals human owned candidate.

## Why the current policy fails (on the isolated case)
Documented in d_case_forensics: tip roles unused; LINE/SEGMENT priors; length_score treats 405 as full member. Isolated to one leader tip case in frozen 75.

## Proposed policy change
Not proposed — insufficient multi-case evidence.

## Overfitting risk
HIGH if tuned on the single D case alone.

## Untouched evaluation / holdout
No independent holdout beyond Burrville exists for this association path. Even if G10 were attempted, generalization could not be established.

## Human-review support summary
```json
{
  "genuine_g9_ranking_disagreements": 1,
  "ambiguous_not_ranking_failures": 5,
  "g9_agrees_with_human_valid_member": 21,
  "repeatable_pattern_established": false
}
```

## Decision rule
A single isolated case is NOT sufficient. G10 requires a repeatable pattern supported by multiple independently reviewed cases.

## Conclusion
**NOT_JUSTIFIED — stop G10 path; do not modify production.**

G10 experiment was **not run**.
