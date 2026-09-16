"""Safe, gated LABEL_SUBSTITUTION resolution (checkpoint 4, objective #1).

The project legend can state that an abbreviated member label expands to a
complete AISC section ("``\"HSS8x4\" = HSS8x4x1/4``"). When a real drawing-page
token IS that abbreviated label, and every deterministic gate below passes,
Estima3D may resolve it to the stated complete designation instead of
routing it to "Missing Dimension -- Select Section".

This is NOT the removed ``reliable_family`` mechanism. ``reliable_family``
attached a family to a token whose own text carried none. Here the token
must ALREADY establish the family: ``HSS8X4`` (family HSS, established by the
token) + rule ``HSS8X4 -> HSS8X4X1/4`` (same family) = allowed; a bare
``8X4`` (no family in the token) + the same rule = REJECTED at gate 6.

The primary, preferred source is the deterministic ``abbreviation_rules``
from ``legend_profile.extract_abbreviation_rules`` (regex-only, requires a
quoted trigger -- never a hallucination risk). Only a DERIVED_INSIGHT or an
INHERITANCE_RULE is never eligible here (those need geometric corroboration,
not identity substitution).

The LLM's typed ``project_rules`` (``services.engineering.project_rules``,
``validation_status == "VALIDATED"`` LABEL_SUBSTITUTION entries only -- i.e.
already quote-grounded and statement/quote-coherence checked at extraction
time) serve two roles:

1. Whenever a deterministic rule already matched, they are consulted only to
   tighten scope (``page_roles``) and to detect a conflicting result --
   never to resolve independently (gates 10/11).
2. Whenever NO deterministic rule matches (e.g. the drawing states the
   substitution without the quoted-trigger syntax the regex requires), a
   validated LLM rule MAY resolve independently -- but only after passing
   the full re-verification in ``_llm_assisted_candidate`` below (Section 8
   safeguards: source snippet + page present, raw key and resolved value
   both grounded in that exact quote, catalog-valid destination, family
   match, and a unique, non-conflicting mapping). The LLM is never trusted
   to invent a section; every LLM-sourced resolution is re-checked against
   the AISC catalog and the verbatim source text by this module, exactly
   like the deterministic path -- it never has additional trust that the
   deterministic path lacks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.database_loader import catalog_form
from services.structural_parser import parse_section
from services.token_extractor import normalize_engineering_token

DECISION_PROJECT_RULE_RESOLVED = "PROJECT_RULE_RESOLVED"
DECISION_SOURCE = "verified_project_rule"

# Distinguishes HOW the winning rule was sourced -- surfaced on the decision
# dict as `extraction_method` so downstream provenance/status-tag
# classification can tell "Project rule" (deterministic legend read) apart
# from "LLM-assisted - Project rule" (validated model extraction) instead of
# mislabeling every project-rule resolution as LLM-assisted.
RESOLUTION_METHOD_DETERMINISTIC = "deterministic"
RESOLUTION_METHOD_LLM_ASSISTED = "llm_assisted"

# Page roles a LABEL_SUBSTITUTION rule may resolve a token on. A context /
# legend page never produces a takeoff token (context_scope), so this is a
# second, explicit line of defence.
_RESOLVABLE_PAGE_ROLES = frozenset({"FRAMING_PLAN", "PLAN", "DETAIL", "SECTION", "SCHEDULE", "UNKNOWN"})
_CONTEXT_PAGE_ROLES = frozenset(
    {"GENERAL_NOTES", "STRUCTURAL_NOTES", "LEGEND", "ABBREVIATIONS", "SPECIFICATIONS"}
)


class ResolutionRejected(Exception):
    """Internal control-flow: a gate failed. Carries the gate name."""

    def __init__(self, gate: str) -> None:
        super().__init__(gate)
        self.gate = gate


def _project_label_rules_for(trigger: str, project_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    norm = normalize_engineering_token(trigger)
    out = []
    for rule in project_rules or []:
        if rule.get("type") != "LABEL_SUBSTITUTION":
            continue
        if normalize_engineering_token(str(rule.get("trigger") or "")) == norm:
            out.append(rule)
    return out


def _quote_grounds_both(quote: str, trigger_norm: str, result_norm: str) -> bool:
    """Section 8 safeguard: the resolved value must appear in the source, or
    be explicitly derivable from it -- not just the trigger. Requires the
    quote (already verified verbatim-in-document by ``project_rules.
    validate_rule``) to contain both the trigger and the result once
    whitespace/punctuation is stripped, so a quote about something else
    entirely that merely happens to share the trigger text cannot ground an
    invented result."""

    import re

    def _squash(text: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", text.upper())

    squashed_quote = _squash(quote)
    trigger_sq = _squash(trigger_norm)
    result_sq = _squash(result_norm)
    return bool(trigger_sq) and bool(result_sq) and trigger_sq in squashed_quote and result_sq in squashed_quote


def _llm_assisted_candidate(
    *,
    token_norm: str,
    token_parsed: Any,
    project_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Re-verify a validated LLM LABEL_SUBSTITUTION rule against every
    safeguard the task's Section 8 requires, independently of whatever
    ``project_rules.validate_rule`` already checked at extraction time (that
    check only proved the STATEMENT is grounded -- this proves the SPECIFIC
    trigger->result mapping is catalog-valid, family-consistent and unique).
    Raises ``ResolutionRejected`` on the first failing safeguard; never
    raises for any other reason."""

    candidates = _project_label_rules_for(token_norm, project_rules)
    if not candidates:
        raise ResolutionRejected("no_matching_rule")

    verified: List[Dict[str, Any]] = []
    for rule in candidates:
        if rule.get("validation_status") != "VALIDATED":
            continue
        quote = str(rule.get("source_quote") or "").strip()
        page = rule.get("source_page")
        if not quote or page is None:
            continue
        result_raw = str(rule.get("result") or "").strip()
        if not result_raw:
            continue
        result_norm = normalize_engineering_token(result_raw)
        if not _quote_grounds_both(quote, token_norm, result_norm):
            continue
        result_parsed = parse_section(result_norm)
        if result_parsed is None or not result_parsed.catalog_valid:
            continue
        if result_parsed.family != token_parsed.family:
            continue
        verified.append({**rule, "_result_norm": result_norm})

    if not verified:
        raise ResolutionRejected("llm_rule_not_grounded")

    distinct_results = {catalog_form(r["_result_norm"]) or r["_result_norm"] for r in verified}
    if len(distinct_results) != 1:
        raise ResolutionRejected("conflicting_llm_rules")

    return verified[0]


def resolve_token(
    *,
    raw_token: str,
    normalized_token: Optional[str] = None,
    page_role: str = "UNKNOWN",
    takeoff_eligible: bool = True,
    abbreviation_rules: List[Dict[str, Any]],
    project_rules: Optional[List[Dict[str, Any]]] = None,
    human_reviewed: bool = False,
    diagnostics: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a ``PROJECT_RULE_RESOLVED`` decision, or ``None`` (= NO_RULE).

    Never raises. On a gate failure returns ``None`` and appends the gate
    name to ``diagnostics`` if a list was passed.
    """

    try:
        return _resolve(
            raw_token=raw_token,
            normalized_token=normalized_token,
            page_role=str(page_role or "UNKNOWN").strip().upper(),
            takeoff_eligible=takeoff_eligible,
            abbreviation_rules=abbreviation_rules or [],
            project_rules=project_rules or [],
            human_reviewed=human_reviewed,
        )
    except ResolutionRejected as rej:
        if diagnostics is not None:
            diagnostics.append(rej.gate)
        return None


def _resolve(
    *,
    raw_token: str,
    normalized_token: Optional[str],
    page_role: str,
    takeoff_eligible: bool,
    abbreviation_rules: List[Dict[str, Any]],
    project_rules: List[Dict[str, Any]],
    human_reviewed: bool,
) -> Optional[Dict[str, Any]]:
    token_norm = normalize_engineering_token(normalized_token or raw_token)
    if not token_norm:
        raise ResolutionRejected("token_empty")

    # Gate: a human decision on this occurrence always wins -- the resolver
    # refuses rather than overwrite it (the read-time overlay also enforces
    # ordering, this is belt-and-suspenders).
    if human_reviewed:
        raise ResolutionRejected("human_reviewed_precedence")

    # NOTE: `takeoff_eligible` is deliberately NOT gated here. Section-identity
    # resolution ("what does this label mean") and takeoff eligibility ("does
    # this occurrence count toward quantity") are orthogonal -- a legend/
    # schedule-definition occurrence can be correctly excluded from the
    # takeoff count while its label is still fully knowable from the project
    # rule. The caller (`staged_pipeline._apply_project_rule_resolution`)
    # never modifies `takeoff_eligible`, so resolving identity here can never
    # create a new physical member or change a quantity. Confirmed against
    # the real GCDC project: the only bare "HSS8X4" occurrence in that
    # document IS a `takeoff_eligible=False` schedule/legend-adjacent object,
    # and the task's own acceptance criterion for it names this exact page
    # (source page 5) as the expected resolved source -- so this gate must
    # not block it.
    if page_role in _CONTEXT_PAGE_ROLES:
        raise ResolutionRejected("context_page_occurrence")
    if page_role not in _RESOLVABLE_PAGE_ROLES:
        raise ResolutionRejected("unresolvable_page_role")

    # Gate 5: the token itself must parse to a real family.
    token_parsed = parse_section(token_norm)
    if token_parsed is None or not token_parsed.family:
        raise ResolutionRejected("token_unparsed_or_familyless")

    # Gate: a token that is ALREADY a complete catalog-valid designation is
    # never re-mapped ("full exact designation has precedence" -> W14X61
    # stays W14X61, HSS8X4X3/8 stays HSS8X4X3/8).
    if token_parsed.catalog_valid:
        raise ResolutionRejected("token_already_complete")

    # Find deterministic rules whose LHS the token matches EXACTLY. This is
    # the primary, preferred source -- see module docstring.
    matches = [
        r
        for r in abbreviation_rules
        if normalize_engineering_token(str(r.get("lhs") or "")) == token_norm
    ]

    if matches:
        # Gate 11: a single unambiguous rule. Two deterministic rules with the
        # same LHS but different RHS -> ambiguous, do not auto-apply.
        distinct_rhs = {catalog_form(str(r.get("rhs") or "")) or str(r.get("rhs") or "") for r in matches}
        if len(distinct_rhs) != 1:
            raise ResolutionRejected("conflicting_deterministic_rules")
        rule = matches[0]

        # Gate 12 + 3: explicit, deterministic, quote-verified.
        if rule.get("extraction_method") != "deterministic":
            raise ResolutionRejected("rule_not_deterministic")
        if rule.get("source_quote_verified") is not True:
            raise ResolutionRejected("quote_not_verified")
        if rule.get("status") and rule["status"] != "PROPOSED_INFERENCE":
            raise ResolutionRejected("unexpected_rule_status")

        lhs_norm = normalize_engineering_token(str(rule.get("lhs") or ""))
        rhs_norm = normalize_engineering_token(str(rule.get("rhs") or ""))

        # Gate 7: exact normalized LHS match (already true by construction of
        # `matches`, re-asserted).
        if token_norm != lhs_norm:
            raise ResolutionRejected("lhs_not_exact")

        # Gate 4: LHS and RHS both parse.
        lhs_parsed = parse_section(lhs_norm)
        rhs_parsed = parse_section(rhs_norm)
        if lhs_parsed is None or rhs_parsed is None:
            raise ResolutionRejected("rule_side_unparsed")

        # Gate 8: RHS is an exact, valid catalog designation.
        if not rhs_parsed.catalog_valid:
            raise ResolutionRejected("rhs_not_catalog_valid")

        # Gate 6: token family == LHS family == RHS family. This is the line
        # that distinguishes this from reliable_family.
        families = {token_parsed.family, lhs_parsed.family, rhs_parsed.family}
        if len(families) != 1:
            raise ResolutionRejected("family_mismatch")

        # Gate 10 + 11 (LLM-informed): if the model surfaced a LABEL_SUBSTITUTION
        # for this trigger, honour its scope and flag a conflicting result.
        for prule in _project_label_rules_for(lhs_norm, project_rules):
            p_result = normalize_engineering_token(str(prule.get("result") or ""))
            if p_result and p_result != rhs_norm:
                raise ResolutionRejected("llm_rule_result_conflict")
            roles = [str(x).strip().upper() for x in (prule.get("scope") or {}).get("page_roles") or []]
            if roles and "ALL" not in roles and page_role not in roles:
                raise ResolutionRejected("page_role_outside_rule_scope")

        resolved = catalog_form(rhs_norm) or rhs_norm
        return {
            "decision": DECISION_PROJECT_RULE_RESOLVED,
            "raw_token": raw_token,
            "normalized_token": token_norm,
            "resolved_designation": resolved,
            "rule_id": rule.get("rule_id") or rule.get("id"),
            "rule_type": "LABEL_SUBSTITUTION",
            "decision_source": DECISION_SOURCE,
            "extraction_method": RESOLUTION_METHOD_DETERMINISTIC,
            "application_policy": "AUTO_ELIGIBLE",
            "source_page": rule.get("source_page"),
            "source_quote": rule.get("source_quote"),
            "lhs": lhs_norm,
            "rhs": resolved,
            "family": token_parsed.family,
        }

    # No deterministic rule -- fall back to a validated, independently
    # re-verified LLM-sourced rule (Section 4/8 of the task). This is the
    # ONLY place an LLM-authored rule may resolve a token by itself; every
    # safeguard below is re-checked here regardless of what
    # ``project_rules.validate_rule`` already verified at extraction time.
    llm_rule = _llm_assisted_candidate(
        token_norm=token_norm, token_parsed=token_parsed, project_rules=project_rules
    )
    roles = [str(x).strip().upper() for x in (llm_rule.get("scope") or {}).get("page_roles") or []]
    if roles and "ALL" not in roles and page_role not in roles:
        raise ResolutionRejected("page_role_outside_rule_scope")

    resolved = catalog_form(llm_rule["_result_norm"]) or llm_rule["_result_norm"]
    return {
        "decision": DECISION_PROJECT_RULE_RESOLVED,
        "raw_token": raw_token,
        "normalized_token": token_norm,
        "resolved_designation": resolved,
        "rule_id": llm_rule.get("id"),
        "rule_type": "LABEL_SUBSTITUTION",
        "decision_source": DECISION_SOURCE,
        "extraction_method": RESOLUTION_METHOD_LLM_ASSISTED,
        "application_policy": "AUTO_ELIGIBLE",
        "source_page": llm_rule.get("source_page"),
        "source_quote": llm_rule.get("source_quote"),
        "lhs": token_norm,
        "rhs": resolved,
        "family": token_parsed.family,
    }
