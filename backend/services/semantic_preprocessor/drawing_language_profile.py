"""Drawing-specific relation resolver (Section 29).

This module deliberately does NOT re-implement legend/note extraction. The
real prototype for that already exists -- uncommitted, in the sibling
worktree ``C:\\Users\\Bassam\\git\\ai-dynamic-regex-dlp`` on branch
``bassam/drawing-language-profile``
(``backend/services/engineering/drawing_language_profile.py``) -- and it is
materially more complete than anything that should be rebuilt in this
session: it distinguishes ``source_verified`` / ``proposed_inference`` /
``conflicted`` / ``rejected`` rule statuses, scopes every rule to the pages
it was actually observed on, and stores per-rule source evidence (page +
quote). That module is at risk (uncommitted, single machine) and should be
committed and reused directly once available in this branch.

Until then, this resolver is the CONSUMER-side half of that same contract:
it accepts already-built rule dicts in the real prototype's schema and
performs only the lookup/precedence/conflict policy described in Section 29.
Wiring the actual extraction step (regex/LLM over legend and notes pages) is
out of scope for this module by design -- see
``docs/upstream_semantic_preprocessor.md`` for the promotion plan.

Rule dict shape expected (subset of the real prototype's schema):
    {
        "rule_id": str,
        "trigger": str,            # e.g. "W8"
        "result": str,             # e.g. "W8X10"
        "rule_status": "source_verified" | "proposed_inference" | "conflicted" | "rejected",
        "scope": {"pages": [int, ...]},
        "source_evidence": [{"page": int, "quote": str}, ...],
        "confidence": float,
    }
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

RULE_STATUS_SOURCE_VERIFIED = "source_verified"
RULE_STATUS_PROPOSED_INFERENCE = "proposed_inference"
RULE_STATUS_CONFLICTED = "conflicted"
RULE_STATUS_REJECTED = "rejected"


@dataclass
class CompletionResolution:
    canonical: Optional[str]
    allowed: bool
    reason: str
    evidence_ids: List[str]


def resolve_completion(
    trigger: str, page: int, rules: List[Dict[str, Any]]
) -> CompletionResolution:
    """Resolve a completion (e.g. ``W8`` -> ``W8X10``) against drawing evidence.

    Only ``source_verified`` rules can ever authorize a completion (Section
    28/29) -- a Grasshopper-derived guess, an LLM ``proposed_inference``, or
    a conflicted rule can never silently complete a label. Rule precedence
    when multiple source_verified rules apply: a rule scoped to this exact
    page wins over a rule with no page scope (project-wide); if two
    source_verified rules disagree for the SAME effective scope, that is a
    conflict -- abstain, do not guess.
    """
    matching = [r for r in rules if r.get("trigger") == trigger]
    if not matching:
        return CompletionResolution(None, False, "no_rule_found", [])

    verified = [r for r in matching if r.get("rule_status") == RULE_STATUS_SOURCE_VERIFIED]
    if not verified:
        # Only proposed/conflicted/rejected rules exist for this trigger.
        return CompletionResolution(None, False, "no_source_verified_rule", [])

    # A rule scoped to this exact page always wins. Failing that, fall back
    # to project-wide rules (empty scope) -- but a rule scoped to a
    # DIFFERENT specific page must never be pulled into scope here; it is
    # simply not applicable to this page and must not manufacture a
    # conflict against an unrelated page's lookup.
    page_scoped = [r for r in verified if page in (r.get("scope", {}).get("pages") or [])]
    project_wide = [r for r in verified if not (r.get("scope", {}).get("pages") or [])]
    pool = page_scoped or project_wide
    if not pool:
        return CompletionResolution(None, False, "no_source_verified_rule_in_scope", [])

    distinct_results = {r["result"] for r in pool}
    if len(distinct_results) > 1:
        return CompletionResolution(
            None, False, "conflicting_source_verified_rules",
            [r["rule_id"] for r in pool],
        )

    (canonical,) = distinct_results
    return CompletionResolution(
        canonical, True, "source_verified_match",
        [r["rule_id"] for r in pool],
    )
