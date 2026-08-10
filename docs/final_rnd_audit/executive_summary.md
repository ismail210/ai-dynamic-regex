# Estima3D — Executive Summary (Since Last UI Demo)

*Full detail: `estima3d_workflow_evolution_report.md` in this folder. This is a reporting/audit document only — nothing was built, trained, merged, or deployed to produce it.*

## Baseline used for this comparison

No commit is explicitly tagged as "the demo," so the closest defensible point in history was identified: **`ef6f71b`** (the last commit that touched the user interface before backend-only work resumed), dated 2026-08-04. Bassam's subsequent committed work sits on top of that at **`2911a8a`**, with further uncommitted local work beyond it. Ismail's independent contribution is **`e36fb1b`** ("feat: restore AI multimodal pipeline and training models"), dated 2026-08-06. This baseline choice is stated with its evidence and its uncertainty in the full report — it is an inference from git history, not a confirmed fact.

## What the system did at the demo

Estima3D read a PDF, pulled out text and drawing geometry, used a pattern matcher (regex) to find text shaped like a steel designation (e.g. `W18X35`), linked each label to whatever nearby drawing object happened to be closest, and combined several evidence signals with fixed weights to produce one final prediction. The official steel catalog only double-checked that answer — it never got to pick it.

## What has changed since

**Almost none of the new work described below is visible to users today.** It exists to make the *next* version of the system buildable safely, not to change what's on screen right now:

- Drawing and graph objects can now be given the same ID every time instead of a random one, which is a prerequisite for reliably comparing runs and building training data.
- Two long-suspected bugs were actually measured on real project drawings for the first time: a page-truncation rule that (on 87.4% of real pages) can drop clean structural lines first instead of last, and a "what's nearby" search that only checks a small, list-order-dependent slice of a page instead of everything actually close by.
- A damaged/illegible steel label (e.g. `W18X3?` from a smudge or tear) can now be matched against the real steel catalog's actual structure (its family, depth, and weight) instead of just comparing whole strings by rough similarity — this directly fixed a case where the system would have suggested a completely different, wrong-sized shape.
- A synthetic training set of realistically-damaged labels was built from the real catalog, and a first trained ranking model was shown, on that synthetic benchmark, to give a real and statistically meaningful improvement over the existing rule-based approach (about 79% correct → about 82% correct).
- A full pipeline for human review of the harder "which drawing object does this label belong to" problem was built and tested — but no human has used it yet, so it has not produced any real training data.

Separately, our partner Ismail added meaningful new capability in his own commit: additional extraction for text tables and schedules, and three real neural-network components — one that reasons about connected objects in a graph, one that converts image crops into comparable visual features, and one that learns how to combine all the evidence signals instead of using fixed weights.

**The most important finding of this audit:** two of those three new neural components already run automatically on every document today, based only on whether a model file exists on disk — and neither has ever had its accuracy actually measured. The system that is supposed to track and approve models exists, but it isn't the thing actually deciding what loads. This is not a criticism of the underlying work, which is real and competently built — it's a governance gap that should be closed before continuing to trust these components by default.

## What is proven vs. unproven

| | Proven | Status |
|---|---|---|
| Damaged-label ranking (new trained model) | Statistically real improvement, **on synthetic data only** | Off in production, ready for real-traffic testing |
| Graph neural network (Ismail) | Real trained model | **Running in production, accuracy unmeasured** |
| Visual feature encoder (Ismail) | Not trained on our data | **Running in production, no domain evaluation** |
| Learned fusion model (Ismail) | Real trained model, can override final prediction | **Running in production, accuracy unmeasured** |
| Label-to-geometry association | Real problem confirmed (28.8% mechanism-level warning sign on real pages) | No human-reviewed truth yet; not trained |

## What we've learned from real projects

Across 7 real projects and 262 real pages, with zero extraction failures: two deterministic (non-AI) bugs are not rare edge cases. The page-truncation bug fires on 87.4% of pages, and the "what's nearby" search only sees a small fraction of what it should on 89% of pages. Separately, the current geometry-matching rule picks the leader/arrow line itself — not the actual structural member — as its final answer in 28.8% of measured cases. That last number is a warning sign about the mechanism, not yet a confirmed error rate, because no human has checked these pages yet.

## Recommended next 3 actions

1. **Fix the page-truncation bug's sort order.** Small, well-tested, safe — the single highest-value, lowest-risk fix identified.
2. **Test the new damaged-label ranking model against real traffic**, in the background, without changing what users see, to confirm the synthetic-benchmark improvement holds up on real cases.
3. **Require the same approval checklist for Ismail's neural components that the damaged-label work already follows** — a real accuracy number and an explicit approval decision, not just "the file exists," before any model is trusted to change a user's result.

## Bottom line

The core prediction pipeline a user sees today has not fundamentally changed since the last demo. What has changed is our ability to trust and improve it: real measurements on real drawings, a genuinely better (if not-yet-deployed) way to handle damaged labels, and new deep-learning capability from Ismail that is promising but currently running ahead of its own evaluation. The main blocker going forward is not a lack of ideas — it's the missing human review data for association, and the missing accuracy numbers for the neural components already running in production.
