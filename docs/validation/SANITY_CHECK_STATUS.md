# Sanity-check status (Sep 23)

One-paragraph team checkpoint for the Sep 22 meeting items plus P0 quantity safety.

**A — Read Tables:** Proven on Estima3D `Struct.pdf` (`schedule_grid` → `schedule_mark_map`; C1/L1 resolve). Second-PDF census of 21 candidates under `Testing Projects/` + Estima3D found **no other** structural MARK|SIZE schedule that yields grids + C/L mark map (`ST.pdf` has MARK/SIZE text but 0 grids). **P1-1 = BLOCKED** until another structural schedule PDF is available. Cross-doc isolation: mark maps remain document-local.

**B — Filter Steel Pages:** `shadow_context_page_gate_enabled` stays **OFF** (default / env). Do not retune `legend_profile.context_pages` (Struct already mis-tags schedule page 2 as SPECIFICATIONS). Mixed-package Current vs Shadow metrics remain **BLOCKED** without multimodal artifacts.

**C — Evaluate LLM:** **DEFERRED** — no measurable value case yet; out of scope until A/B is justified.

**D — Sanity / P0:** Schedule-only `METHOD_SCHEDULE_CELL` → `physical_quantity=0` (`excluded_schedule_only`) **PASS** on Struct export; mark/angle regression suite green. QuantityEngine still does **not** count labeled plan sources (`Explicit catalog match` / mark map) — separate product decision.

Checkout: `main` @ `77f0ea0` + uncommitted P0 quantity-safety fix (commit when asked). Geometry G8/G9 remain `PRODUCTION_NO_GO` — not wired.
