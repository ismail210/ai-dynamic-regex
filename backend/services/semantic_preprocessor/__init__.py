"""Structural drawing semantic preprocessor.

Upstream of the existing Rhino/Grasshopper takeoff system, not a replacement
for it. This package owns text semantics (extraction primitives, semantic
grouping, structural label parsing, normalization/repair/completion,
drawing-specific relation resolution) and the evidence-fusion bridge to
optional Grasshopper geometry evidence. It never computes quantities, never
classifies members into fabrication/cost buckets, and never rewrites a
production PDF -- see docs/upstream_semantic_preprocessor.md.

This module is intentionally NOT imported by any existing router or the
production prediction orchestrator. It is a new, additive service reached
only through its own entry points, so existing takeoff behavior is
unaffected by its presence (see backend/services/prediction/orchestrator.py
architecture invariant in CLAUDE.md).
"""
