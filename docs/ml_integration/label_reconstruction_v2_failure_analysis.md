# v2 failure analysis & recoverable-vs-ambiguous distribution (Parts 1-2)

Source data: `backend/training/datasets/label_reconstruction/frozen_test_analysis.jsonl`
(2,772 rows, the exact frozen pointwise test split from dataset version
`label_reconstruction_20260807_125937` -- untouched by this analysis).
Every row in that file carries the full per-example record this document's
Part 1 requirement asks for (query, true label, deterministic/learned
top-10, rank, family, corruption type(s), severity, whether the true label
entered the candidate set, candidate-generation-vs-ranking classification,
and `compatible_catalog_count`) -- this document summarizes and groups it;
it does not re-print all 2,772 rows.

## Headline numbers

- v2 deterministic generator top-1 accuracy: **79.33%**
- v2 learned ranker top-1 accuracy: **79.58%**
- Of the 2,772 test rows: **2,206 correct** (`failure_kind: none`), **369
  ranking failures** (true label was generated but not ranked #1), **197
  candidate-generation failures** (true label never appeared in the top-25
  candidates at all).

**Ranking failures (369) still outnumber candidate-generation failures
(197)**, though by a smaller margin than first measured. *(Correction: an
earlier version of this analysis passed the ranker a normalized query
string instead of the raw corrupted text it was actually trained on -- an
inference/training preprocessing mismatch that undercounted v2's true
ranking accuracy, especially for `separator`-corruption rows, whose raw
text contains spaces that normalization strips. That bug lived only in this
offline analysis script, not in the evaluation numbers reported elsewhere
or in production code -- except that the same bug was also found and fixed
in `services/label_reconstruction/shadow.py` itself, see the v3 evaluation
report's "bugs found" section. Numbers below are post-fix.)* This still
answers Part 1's "is the failure candidate generation or candidate ranking"
question in aggregate: there is more headroom in improving the RANKER than
in improving what gets generated -- which argues for investing in Part 7's
learning-to-rank model, not just Part 3's structural candidate fix (though
that fix still matters, see below).

## 1. Failures grouped by family

| Family group | n | top-1 acc | candidate-gen failures | ranking failures |
|---|---|---|---|---|
| C/MC | 97 | 0.856 | 6 | 8 |
| HSS | 868 | 0.772 | 61 | 137 |
| L/2L | 930 | 0.835 | 51 | 102 |
| PIPE | 60 | 0.717 | 9 | 8 |
| W | 347 | 0.767 | 25 | 56 |
| WT/MT/ST | 380 | 0.755 | 40 | 53 |
| other | 90 | 0.889 | 5 | 5 |

PIPE has the worst raw candidate-generation coverage (9 generation failures
out of 60, the highest failure RATE of any family) -- its distinctive
no-`X`-delimiter grammar (`PIPE<size><STD|XS|XXS>`) makes several corruption
types (especially `added_noise` wrapping the whole token in parens, e.g.
`(?4STD)`) harder to recover positionally than the `X`-delimited families.

## 2. Failures grouped by corruption type

| Corruption family | n | top-1 acc | candidate-gen failures | ranking failures |
|---|---|---|---|---|
| separator | 527 | 0.915 | 12 | 33 |
| ocr_substitution | 470 | 0.862 | 18 | 47 |
| added_noise | 505 | 0.848 | 56 | 21 |
| char_deletion | 473 | 0.740 | 25 | 98 |
| unknown_char (wildcard) | 503 | 0.690 | 37 | 119 |
| missing_prefix | 294 | 0.660 | 49 | 51 |

`unknown_char` (wildcard masking) has the most ranking failures in absolute
terms (121) -- this is the exact failure mode Part 3/4 targeted, and is
addressed by the family-aware structural fix (see below), NOT yet reflected
in these v2 numbers. `missing_prefix` has the worst top-1 accuracy overall
(66.3%) -- losing the family letter is a genuinely hard problem: without a
family, `family_of()` cannot disambiguate `18X35` as W-vs-other-family at
all, and the corruption is irrecoverable from text alone in the
`NO_EXACT_STRUCTURAL_MATCH` sense described below.

## 3. Representative failure examples

**Candidate-generation failures** (true label never generated):

| Query | True label | Corruption(s) | v2 top-10 |
|---|---|---|---|
| `WHSS3.000X0.216` | `HSS3.000X0.216` | added_prefix_letter | *(empty)* |
| `W2L8X4X1/2SLBB` | `2L8X4X1/2SLBB` | added_prefix_letter | `W24X162, W24X192` |
| `W**XZ*` | `W40X277` | char_deletion + OCR + wildcard (sev. 3) | *(empty)* |

The first two rows reveal a real, un-fixed limitation: `added_prefix_letter`
corruption sometimes prepends the letter **"W"**, and `family_of()` (in
`corruption.py`, shared by both v2 and v3, not modified this session) checks
family prefixes longest-first but still matches the single-letter `"W"`
prefix on `"WHSS..."`/`"W2L8..."` before any structural-parser code even
runs -- the corrupted text is misidentified as a completely wrong family at
the very first parsing step. This is a corruption-vs-parser interaction bug
worth fixing in a future phase (e.g. by trying every valid family prefix
anywhere the string could plausibly start, not just the literal start), not
something Part 3's field-grammar fix could address since it operates
downstream of `family_of()`.

**Ranking failures** (true label generated, but not ranked #1):

| Query | True label | v2 rank | What outranked it |
|---|---|---|---|
| `WTSX3*` | `WT5X30` | 2 | `WT5X13` (same depth, different weight) |
| `18XBX3/4` | `L8X8X3/4` | 7 | Multiple HSS/2L candidates (family prefix `L` was lost) |
| `HSS4.000X0.3` | `HSS4.000X0.313` | 2 | `HSS4.000X0.237` (same diameter, different truncated thickness) |
| `(?4STD)` | `PIPE24STD` | 3 | `PIPE4STD`, `PIPE14STD` (added-noise parens plus a masked leading digit) |

These illustrate two genuinely different situations: `WTSX3*` and
`HSS4.000X0.3` are close, structurally-plausible near-misses (the kind Part
6's hard-negative mining targets); `18XBX3/4` is the `missing_prefix`
problem again -- once the family letter is gone, "8X8" could plausibly be
an HSS/2L/L dimension pair, and text alone genuinely underdetermines the
family.

## 4. Recoverable vs. ambiguous distribution (Part 2)

`compatible_catalog_count` = number of catalog labels whose fields match
every literal, non-wildcard character of the query exactly (see
`services.structural_parser`). This is intentionally
STRICT: an OCR-substituted digit is a literal character mismatch, not a
wildcard, so most non-wildcard corruptions correctly fall into
`NO_EXACT_STRUCTURAL_MATCH` -- that category means "needs OCR/fuzzy
recovery," not "unrecoverable."

| Ambiguity category | n | % of test set | compatible-set recall | top-1 | top-3 | top-5 |
|---|---|---|---|---|---|---|
| UNIQUE (exactly 1 compatible label) | 137 | 4.9% | 98.5% | **99.3%** | 99.3% | 100.0% |
| SMALL_AMBIGUOUS_SET (2-5) | 71 | 2.6% | 97.2% | 45.1% | 91.5% | 97.2% |
| LARGE_AMBIGUOUS_SET (>5) | 12 | 0.4% | 83.3% | **0.0%** | 33.3% | 58.3% |
| NO_EXACT_STRUCTURAL_MATCH | 2,552 | 92.1% | n/a (0 by definition) | 79.9% | 87.9% | 89.5% |

**This is the single clearest result in the whole v2/v3 analysis.** When a
corrupted query's surviving structure genuinely determines a UNIQUE catalog
label, the system gets it right 99.3% of the time -- there is essentially
nothing left to fix there. When 2-5 labels are equally compatible
(`SMALL_AMBIGUOUS_SET`), top-1 accuracy collapses to 45.1% not because the
model is bad, but because **the query itself does not contain enough
information to pick one of 2-5 equally-valid answers** -- yet top-5 recall
stays high (97.2%), meaning the system correctly narrows to the right
neighborhood even when it cannot commit to one label. At `LARGE_AMBIGUOUS_SET`
(>5 compatible labels, e.g. `W18X**`), top-1 accuracy is **zero** -- this is
expected and should never be reported as a model failure; it should be
reported as "this query is inherently ambiguous, present the top-K set to
a human reviewer rather than auto-selecting."

**Practical implication for any future UI/API surface**: `ambiguity_category`
should be exposed alongside any prediction. A `UNIQUE` prediction can
reasonably be auto-applied; a `SMALL_AMBIGUOUS_SET` or `LARGE_AMBIGUOUS_SET`
prediction should default to showing the top-K list for confirmation rather
than silently picking #1, regardless of how good the ranker gets -- no
ranker can out-perform the information actually present in the text.

## 6. Candidate-generation recall: v2 vs v3 generator (Part 5)

Measured separately from ranking accuracy -- "was the correct label even
generated" vs. "was it ranked #1" are two different questions, and hiding
generation failures inside a single top-1 number (as most ML reporting
does) obscures which one to fix.

| k | v2 recall@k | v3 recall@k |
|---|---|---|
| 1 | 0.7933 | 0.7929 |
| 3 | 0.8892 | 0.8874 |
| 5 | 0.9087 | 0.9069 |
| 10 | 0.9232 | 0.9217 |
| 20 | 0.9278 | 0.9275 |
| any rank (up to 25) | 0.9289 | 0.9286 |

**v3's raw candidate-generation recall is statistically at parity with v2 --
not better.** This is an honest, slightly counter-intuitive result worth
stating plainly: the family-aware structural fix (Part 3/4) does not expand
how often the true label is *somewhere* in the candidate list; both
generators find it ~92.9% of the time. What the structural fix changes is
***where in the list*** a correct-but-previously-buried candidate appears --
concretely, for `HSS8X8X?`, v2 and v3 both eventually include every real
`HSS8X8Xn` entry, but v2 ranks `HSS18X18X1` (wrong depth entirely) **first**
among them via fuzzy string similarity, while v3's `structural_field_match`
strategy ranks all seven real `HSS8X8Xn` candidates ahead of it (see
`tests/test_structural_parser.py::V3CandidateOrderingFixesHssBugTests` for
the exact before/after). So: **Part 3/4's value is a ranking-quality fix
disguised as a candidate-generation fix** -- consistent with the "Headline numbers" section above's
finding that ranking failures (446) already outnumber candidate-generation
failures (197) in v2. Combined with a learned ranker that can make full use
of the new `structural_field_match`/field-distance features (Part 7-9), this
is expected to matter more than these raw recall numbers suggest on their
own.

## 7. `compatible_catalog_count` distribution (raw)

```
0 -> 2552 rows (NO_EXACT_STRUCTURAL_MATCH)
1 -> 137 rows (UNIQUE)
2 -> 49, 3 -> 9, 4 -> 9, 5 -> 4   (SMALL_AMBIGUOUS_SET, sums to 71)
6 -> 3, 7 -> 4, 9 -> 1, 10 -> 2, 15 -> 1, 21 -> 1   (LARGE_AMBIGUOUS_SET, sums to 12)
```
