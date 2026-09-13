# Estima3D R&D Synthesis: Cross-Check and Final Conclusion

**Companion document** to `legend_aware_extraction_audit.md` (the evidence base) and `estima3d_rd_roadmap.md` (our 20-section external research roadmap), both in this folder. This document cross-checks our roadmap against a second, independently-produced research report (a ChatGPT-authored document, provided by the user, saved at the user's local `Downloads` folder — not copied into this repo) that was evidently also built on the internal audit, and records where the two converge, where they differ, and what should be adopted from the second report into our own recommendations.

---

## 1. Verdict

The two research passes — ours and the second report's — independently reach the same architecture. Two differently-steered research efforts landing in the same place is stronger evidence than either alone. **No change to the core recommendation in `estima3d_rd_roadmap.md` §A/§Q is warranted.** Three specific refinements from the second report are adopted below.

Two of the second report's most load-bearing new claims (Tekla's bent-plate/end-plate connection components deriving dimensions from picked points and bolt-group edge distances; SDS2 modeling a pour stop as either a bent-plate shape with separately-given thickness or a rolled angle) were independently spot-checked against Tekla's and SDS2's own documentation and confirmed accurate.

---

## 2. Where the two reports agree (independently)

- **Root cause is deterministic, not AI.** Both reports identify the same mechanism — the plate-detection regex requires a width×length pair most real thickness-only callouts (`BENT PL`, `CAP PL`, `CONN PL`) don't have — as the dominant, fixable cause of the audit's confirmed losses.
- **The Drawing Language Profile must be validated, not trusted.** Both reject "ask an LLM to read the legend and trust its output" in favor of "LLM proposes a structured rule with a source quote, deterministic code checks it against the rest of the document before it's allowed to influence anything."
- **Page/legend suppression needs a region-role signal, not a binary keyword filter.** Both independently point at the same failure pair from the audit (a legend-caption `W27X84` example is correctly suppressed today; the GCDC abbreviation-table row is not) as proof the current local-keyword check is too crude.
- **A document/detail-relationship graph is real, valuable, second-priority work** — sequenced after the grammar fix and the profile, not instead of them.
- **VLM is not justified now.** Neither report found a genuine pixel-dependent problem in this corpus; both independently flag the partner's 4-crop Moondream pilot as confounded by literal text-in-crop, and both propose a masked-text ablation design to actually test this before spending more on VLM work.
- **Two of the same open questions, found independently:** whether GCDC's `"W8"=W8x10` rule is actually used elsewhere on that project (never checked in the audit), and where the "TEXT_NOTE" label the user's partner referenced actually comes from, given it doesn't exist anywhere in the audited codebase.

## 3. Where they differ, and the call made

- **Framing of the contextual ranker.** The second report's architecture-comparison table labels "profile + relationship graph + contextual ranker" as one bundled tier and calls it the recommended core target. Its own week-by-week roadmap, however, states the ranker should be trained "only after" the graph exists and works — i.e., functionally the same gating our own `§S` go/no-go gates impose. **Call: keep our framing** (ranker explicitly gated behind a measured gap after the graph is built) — it's more conservative, and it's what both reports' actual implementation sequences agree on regardless of the table label.

## 4. Three refinements adopted from the second report

1. **Explicit rules vs. inferred patterns need different validation bars.** Our `§I.2` validation logic (in `estima3d_rd_roadmap.md`) required ≥1 corpus-corroborating occurrence before a proposed rule counts as `validated`. This conflates two different questions. An explicit declarative sentence (`"W8" = W8x10`) should be trusted as a real rule on source-grounding + catalog-validity alone — zero occurrences elsewhere means the rule is *unused on this document*, not *false*. Only a rule *inferred from repeated co-occurrence* (no explicit sentence — e.g. "we saw `BP` near bent plates 3 times, so `BP` probably means bent plate") needs statistical support before being trusted. **Revise `DrawingLanguageProfile` rule status to: `SOURCE_VERIFIED` (explicit sentence, grounded, catalog-valid — usable immediately, independent of corpus occurrence count) vs. `PROPOSED_INFERENCE` (no explicit sentence — needs supporting occurrences before promotion).** Track "observed applications elsewhere" as a separate, informational field on `SOURCE_VERIFIED` rules — useful for review, not a gate.
2. **A richer dimension-provenance enum.** Adopt: `EXPLICIT_TEXT`, `EXPLICIT_DETAIL_DIMENSION`, `SCHEDULE_VALUE`, `PROJECT_DEFAULT`, `GEOMETRY_DERIVED`, `CONNECTION_DERIVED`, `DELEGATED_DESIGN`, `NOT_APPLICABLE`, `UNKNOWN` in place of our simpler `dimension_source` field (`estima3d_rd_roadmap.md` §D.2/§H.8). This is more complete and maps directly onto real cases in the audit (`CONNECTION_DERIVED` in particular has no equivalent in our original schema, and real Tekla connection components confirm it's a real category, not a hypothetical one).
3. **New corroborating evidence for the "information is distributed, not one string" thesis.** Tekla's End Plate and Bent Plate connection components derive width/height from bolt-group edge distances and connection geometry when the user supplies only thickness (confirmed against Tekla's own docs); SDS2 models a pour stop as either a bent-plate shape (thickness given separately) or a rolled angle (confirmed against SDS2's own docs). This is concrete proof that commercial detailing software already treats a fabricated plate's full definition as something assembled from text + geometry + connection logic, not something that must arrive complete in one label — strengthening (not changing) the case already made in `estima3d_rd_roadmap.md` §C/§D.

## 5. What stays unchanged

Everything else in `estima3d_rd_roadmap.md` — the executive conclusion (§A), the six-way architecture comparison (§P), the recommended architecture (§Q), the phased roadmap (§R), the go/no-go gates (§S), and the ranked open engineering questions (§T) — stands as written. The second report is corroborating evidence, not a correction.
