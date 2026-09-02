"""Project Drawing-Language Rule taxonomy, validation and compiler.

Checkpoint 4, objective #3. The legend / general-notes pages of a structural
set are not just a list of notes -- they define a *project-specific drawing
language*: what abbreviated labels expand to, how bracketed / prefixed /
parenthesised annotations encode camber, studs, reactions and elevations,
which member attributes inherit from a neighbour, and which project
defaults apply. The LLM (``legend_llm_provider``) discovers and states these
rules; this module is the deterministic layer that decides:

1. is the rule real (evidence-grounded, a known type)?
2. what kind of thing is it -- mapped onto a controlled taxonomy;
3. what is Estima3D allowed to DO with it (``application_policy``).

Nothing here executes free-form model output. A ``NOTATION_GRAMMAR`` rule is
mapped to one of a fixed set of ``grammar_type`` constants; an unrecognised
grammar stays informational. Only ``LABEL_SUBSTITUTION`` is ever
auto-applicable, and even then only through
``services.engineering.project_rule_resolver`` behind its own gates.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# --- rule types -----------------------------------------------------------

LABEL_SUBSTITUTION = "LABEL_SUBSTITUTION"
NOTATION_GRAMMAR = "NOTATION_GRAMMAR"
INHERITANCE_RULE = "INHERITANCE_RULE"
ATTRIBUTE_DEFAULT = "ATTRIBUTE_DEFAULT"
ORIENTATION_RULE = "ORIENTATION_RULE"
CONNECTION_DEFAULT = "CONNECTION_DEFAULT"
SCOPE_RULE = "SCOPE_RULE"
DOCUMENT_PRECEDENCE = "DOCUMENT_PRECEDENCE"
CONFLICT_WARNING = "CONFLICT_WARNING"
DERIVED_INSIGHT = "DERIVED_INSIGHT"

RULE_TYPES = frozenset(
    {
        LABEL_SUBSTITUTION,
        NOTATION_GRAMMAR,
        INHERITANCE_RULE,
        ATTRIBUTE_DEFAULT,
        ORIENTATION_RULE,
        CONNECTION_DEFAULT,
        SCOPE_RULE,
        DOCUMENT_PRECEDENCE,
        CONFLICT_WARNING,
        DERIVED_INSIGHT,
    }
)

# --- what Estima3D may do with a validated rule -------------------------

POLICY_AUTO_ELIGIBLE = "AUTO_ELIGIBLE"           # may change a predicted section (resolver + gates)
POLICY_CORROBORATION_REQUIRED = "CORROBORATION_REQUIRED"  # needs geometry/association proof first
POLICY_PARSER_ASSIST = "PARSER_ASSIST"           # may guide annotation parsing (not this checkpoint)
POLICY_ATTRIBUTE_ONLY = "ATTRIBUTE_ONLY"         # may populate a material/finish/orientation attribute
POLICY_INFORMATION_ONLY = "INFORMATION_ONLY"     # surfaced to the estimator, never acted on
POLICY_NEVER_AUTO = "NEVER_AUTO"                 # inference / conflict -- display only

_APPLICATION_POLICY = {
    LABEL_SUBSTITUTION: POLICY_AUTO_ELIGIBLE,
    NOTATION_GRAMMAR: POLICY_PARSER_ASSIST,
    INHERITANCE_RULE: POLICY_CORROBORATION_REQUIRED,
    ORIENTATION_RULE: POLICY_CORROBORATION_REQUIRED,
    ATTRIBUTE_DEFAULT: POLICY_ATTRIBUTE_ONLY,
    CONNECTION_DEFAULT: POLICY_INFORMATION_ONLY,
    SCOPE_RULE: POLICY_INFORMATION_ONLY,
    DOCUMENT_PRECEDENCE: POLICY_INFORMATION_ONLY,
    CONFLICT_WARNING: POLICY_NEVER_AUTO,
    DERIVED_INSIGHT: POLICY_NEVER_AUTO,
}


def application_policy(rule_type: str, grammar_type: Optional[str] = None) -> str:
    """A NOTATION_GRAMMAR rule whose grammar we could not map to a known
    type is downgraded to INFORMATION_ONLY -- we will not let an
    unrecognised syntax hint drive a parser."""

    if rule_type == NOTATION_GRAMMAR and (grammar_type in (None, GRAMMAR_UNKNOWN)):
        return POLICY_INFORMATION_ONLY
    return _APPLICATION_POLICY.get(rule_type, POLICY_INFORMATION_ONLY)


# --- controlled annotation-grammar vocabulary --------------------------

GRAMMAR_CAMBER_PREFIX = "CAMBER_PREFIX"
GRAMMAR_STUD_COUNT_SINGLE = "STUD_COUNT_SINGLE"
GRAMMAR_STUD_COUNT_SEGMENTED = "STUD_COUNT_SEGMENTED"
GRAMMAR_REACTION_VALUE = "REACTION_VALUE"
GRAMMAR_TOP_OF_STEEL_ELEVATION = "TOP_OF_STEEL_ELEVATION"
GRAMMAR_COLUMN_POSTING_LOAD = "COLUMN_POSTING_LOAD"
GRAMMAR_FRAME_MARK = "FRAME_MARK"           # generic braced/moment/drag frame mark
GRAMMAR_DRAG_STRUT_MARK = "DRAG_STRUT_MARK"
GRAMMAR_MOMENT_FRAME_MARK = "MOMENT_FRAME_MARK"
GRAMMAR_BRACED_FRAME_MARK = "BRACED_FRAME_MARK"
GRAMMAR_CANTILEVER_MARK = "CANTILEVER_MARK"
GRAMMAR_UNKNOWN = "UNKNOWN_GRAMMAR"

GRAMMAR_TYPES = frozenset(
    {
        GRAMMAR_CAMBER_PREFIX,
        GRAMMAR_STUD_COUNT_SINGLE,
        GRAMMAR_STUD_COUNT_SEGMENTED,
        GRAMMAR_REACTION_VALUE,
        GRAMMAR_TOP_OF_STEEL_ELEVATION,
        GRAMMAR_COLUMN_POSTING_LOAD,
        GRAMMAR_FRAME_MARK,
        GRAMMAR_DRAG_STRUT_MARK,
        GRAMMAR_MOMENT_FRAME_MARK,
        GRAMMAR_BRACED_FRAME_MARK,
        GRAMMAR_CANTILEVER_MARK,
        GRAMMAR_UNKNOWN,
    }
)

# Ordered (specific first): (grammar_type, keyword regex over the model's
# `field` + `grammar` + `statement`, blended and lower-cased).
_GRAMMAR_SIGNALS = (
    (GRAMMAR_STUD_COUNT_SEGMENTED, re.compile(r"stud.*(segment|girder segment|;|semicolon)|by (girder )?segment")),
    (GRAMMAR_STUD_COUNT_SINGLE, re.compile(r"\b(shear )?stud")),
    (GRAMMAR_CAMBER_PREFIX, re.compile(r"\bcamber\b|(^|[^a-z])c\s*=")),
    (GRAMMAR_TOP_OF_STEEL_ELEVATION, re.compile(r"top[- ]of[- ]steel|top of steel|\bt\.?o\.?s\.?\b|elevation")),
    (GRAMMAR_COLUMN_POSTING_LOAD, re.compile(r"column post|col\s*up|posting load|column .*load above")),
    (GRAMMAR_REACTION_VALUE, re.compile(r"reaction|\br\d|\bkip\b|kips\b|factored .*(load|force)|end (load|force)")),
    (GRAMMAR_DRAG_STRUT_MARK, re.compile(r"drag strut|\bds\b")),
    (GRAMMAR_MOMENT_FRAME_MARK, re.compile(r"moment frame|\bmf\b")),
    (GRAMMAR_BRACED_FRAME_MARK, re.compile(r"braced frame|\bbf\b")),
    (GRAMMAR_CANTILEVER_MARK, re.compile(r"cantilever|\bcant\b")),
    (GRAMMAR_FRAME_MARK, re.compile(r"frame mark|frame (identifier|designation)")),
)


def classify_grammar(*, field: str, grammar: str, statement: str) -> str:
    blob = " ".join(str(x or "") for x in (field, grammar, statement)).lower()
    for grammar_type, pattern in _GRAMMAR_SIGNALS:
        if pattern.search(blob):
            return grammar_type
    return GRAMMAR_UNKNOWN


# --- validation ---------------------------------------------------------

VALIDATION_STATUS_VALIDATED = "VALIDATED"
VALIDATION_STATUS_PROPOSED_INFERENCE = "PROPOSED_INFERENCE"

_RELEVANCE = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
_MAX_STR = 320
_MAX_QUOTE = 400

# Every executable/attribute rule type must be grounded by a verbatim quote;
# a DERIVED_INSIGHT reasons across rules and instead needs evidence_refs.
_QUOTE_REQUIRED = RULE_TYPES - {DERIVED_INSIGHT}


def _clean(value: Any, limit: int = _MAX_STR) -> str:
    return str(value or "").strip()[:limit]


def _scope(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"page_roles": [], "uno_applies": False}
    roles = raw.get("page_roles")
    roles = [str(r).strip().upper() for r in roles if str(r).strip()] if isinstance(roles, list) else []
    return {"page_roles": roles, "uno_applies": bool(raw.get("uno_applies"))}


# Rules the 8B model keeps emitting that are not project drawing-language:
# administrative sheet-status notes, and generic non-steel scope.
_ADMIN_NOISE = re.compile(
    r"issued for (bid|construction|permit|review)|not for construction|"
    r"copyright|these documents were prepared|shall be responsible for obtaining|"
    r"\bslab[- ]on[- ]grade\b|reinforc\w* with .*wwf|vapor barrier",
    re.I,
)
# An ATTRIBUTE_DEFAULT is only meaningful if it actually names a
# grade / material / finish.
_MATERIAL_SIGNAL = re.compile(
    r"\bA(?:36|53|500|513|572|588|992|1085|1554|325|490|307)\b|astm|grade [a-z0-9]|"
    r"fy\s*=|\bksi\b|galvani[sz]|hot[- ]dip|\bhdg\b|coating|primer|paint|shop coat|"
    r"weathering|unpainted|metallic|fireproof",
    re.I,
)


def _is_circular(statement: str, quote: str) -> bool:
    """'W12x53 indicates a W12x53 steel shape' / '295k indicates a load of
    295 kips' with a bare-token quote -- the model restating a fragment, not
    a rule."""

    q = quote.strip().strip('"').strip()
    if len(q) >= 12 and " " in q:
        return False
    token = re.sub(r"[^A-Za-z0-9]", "", q).lower()
    return bool(token) and statement.lower().count(token) >= 2


def validate_rule(
    raw: Any,
    *,
    source_text: str,
    verify_quote,
    statement_supported_by_quote,
    next_id: int,
) -> Optional[Dict[str, Any]]:
    """Validate one LLM-proposed rule (not a DERIVED_INSIGHT -- see
    ``validate_insight``). Returns the compiled rule dict or None."""

    if not isinstance(raw, dict):
        return None
    rule_type = str(raw.get("type") or "").strip().upper()
    if rule_type not in RULE_TYPES or rule_type == DERIVED_INSIGHT:
        return None
    statement = _clean(raw.get("statement"))
    if not statement:
        return None

    quote = _clean(raw.get("source_quote"), _MAX_QUOTE)
    if rule_type in _QUOTE_REQUIRED:
        if not quote or not verify_quote(source_text, quote):
            return None
        if not statement_supported_by_quote(statement, quote):
            return None
        if _is_circular(statement, quote):
            return None

    if _ADMIN_NOISE.search(statement) or _ADMIN_NOISE.search(quote):
        return None
    if rule_type == ATTRIBUTE_DEFAULT and not _MATERIAL_SIGNAL.search(f"{statement} {quote}"):
        return None

    try:
        source_page = int(raw.get("source_page"))
    except (TypeError, ValueError):
        source_page = None
    relevance = str(raw.get("relevance") or "MEDIUM").strip().upper()
    if relevance not in _RELEVANCE:
        relevance = "MEDIUM"

    grammar_type: Optional[str] = None
    if rule_type == NOTATION_GRAMMAR:
        grammar_type = classify_grammar(
            field=_clean(raw.get("field")),
            grammar=_clean(raw.get("grammar")),
            statement=statement,
        )

    benefits = raw.get("system_benefit")
    benefits = (
        sorted({str(b).strip().upper()[:1] for b in benefits if str(b).strip()})
        if isinstance(benefits, list)
        else []
    )

    return {
        "id": f"RULE_{next_id:03d}",
        "type": rule_type,
        "statement": statement,
        "trigger": _clean(raw.get("trigger"), 60) or None,
        "result": _clean(raw.get("result"), 60) or None,
        "field": _clean(raw.get("field"), 60) or None,
        "grammar": _clean(raw.get("grammar"), 80) or None,
        "grammar_type": grammar_type,
        "relation": _clean(raw.get("relation"), 60) or None,
        "inherited_field": _clean(raw.get("inherited_field"), 60) or None,
        "condition": _clean(raw.get("condition")) or None,
        "scope": _scope(raw.get("scope")),
        "relevance": relevance,
        "system_benefit": benefits,
        "source_page": source_page,
        "source_quote": quote or None,
        "application_policy": application_policy(rule_type, grammar_type),
        "validation_status": VALIDATION_STATUS_VALIDATED,
        "extraction_method": "llm_proposed",
    }


def validate_insight(
    raw: Any, *, validated_rule_ids: set, phrase_overlap
) -> Optional[Dict[str, Any]]:
    """A derived insight must cite validated rule ids (RULE_003 ...) or the
    close text of a validated rule's statement. Never executable."""

    if not isinstance(raw, dict):
        return None
    statement = _clean(raw.get("statement")) or _clean(raw.get("inference"))
    if not statement:
        return None
    raw_refs = raw.get("evidence_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        return None
    refs = [str(r).strip() for r in raw_refs if str(r).strip()]
    grounded = [r for r in refs if r.upper() in validated_rule_ids or phrase_overlap(r)]
    if not grounded:
        return None
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "id": _clean(raw.get("id"), 20) or None,
        "statement": statement,
        "evidence_refs": grounded[:8],
        "reasoning_summary": _clean(raw.get("reasoning_summary")),
        "impact": _clean(raw.get("impact")),
        "confidence": confidence,
        "application_policy": POLICY_NEVER_AUTO,
        "validation_status": VALIDATION_STATUS_PROPOSED_INFERENCE,
    }


# --- human-readable "drawing language" -------------------------------

def _label_substitution_bullet(abbreviation_rules: List[Dict[str, Any]]) -> Optional[str]:
    if not abbreviation_rules:
        return None
    families = sorted({str(r.get("lhs_family") or "").upper() for r in abbreviation_rules if r.get("lhs_family")})
    fam_text = "/".join(families) if families else "W/C/HSS"
    return (
        f"Shortened {fam_text} member labels on the framing plans map to project-specific "
        f"complete AISC sections (see the legend / abbreviations page)."
    )


_GRAMMAR_BULLET = {
    GRAMMAR_CAMBER_PREFIX: "`c=<dimension>` denotes beam camber.",
    GRAMMAR_STUD_COUNT_SINGLE: "A bracketed value is a shear-stud quantity for the associated beam.",
    GRAMMAR_STUD_COUNT_SEGMENTED: "Semicolon-separated bracketed values divide the shear-stud count by girder segment.",
    GRAMMAR_REACTION_VALUE: "A `…k` value at a beam end is a factored connection reaction.",
    GRAMMAR_TOP_OF_STEEL_ELEVATION: "A parenthesised elevation gives top-of-steel.",
    GRAMMAR_COLUMN_POSTING_LOAD: "`COL UP …K` is a factored column posting (axial) load from above.",
    GRAMMAR_DRAG_STRUT_MARK: "`DS` marks a drag-strut member.",
    GRAMMAR_MOMENT_FRAME_MARK: "`MF` marks a moment-frame condition.",
    GRAMMAR_BRACED_FRAME_MARK: "`BF…` marks a braced-frame member.",
    GRAMMAR_FRAME_MARK: "Frame marks identify braced-frame / moment-frame / drag-strut conditions.",
    GRAMMAR_CANTILEVER_MARK: "`CANT` marks a cantilevered member.",
}


def build_drawing_language(
    *, rules: List[Dict[str, Any]], abbreviation_rules: List[Dict[str, Any]]
) -> List[str]:
    """A short bullet list -- 'how does this project's framing notation
    work' -- derived only from validated rules. Never hard-coded doc text."""

    bullets: List[str] = []
    seen: set = set()

    def add(text: Optional[str]) -> None:
        if text and text not in seen:
            seen.add(text)
            bullets.append(text)

    add(_label_substitution_bullet(abbreviation_rules))

    _frame_grammars = {GRAMMAR_DRAG_STRUT_MARK, GRAMMAR_MOMENT_FRAME_MARK, GRAMMAR_BRACED_FRAME_MARK}
    frame_marks = {
        r.get("grammar_type")
        for r in rules
        if r.get("type") == NOTATION_GRAMMAR and r.get("grammar_type") in _frame_grammars
    }
    for rule in rules:
        if rule.get("type") == NOTATION_GRAMMAR:
            add(_GRAMMAR_BULLET.get(rule.get("grammar_type") or GRAMMAR_UNKNOWN))
        elif rule.get("type") == INHERITANCE_RULE:
            trig = rule.get("trigger") or "an omitted-size member"
            rel = (rule.get("relation") or "adjacent member").replace("_", " ")
            add(f"`{trig}`: where the steel section is omitted, it inherits the {rel}, UNO.")
        elif rule.get("type") == ORIENTATION_RULE:
            add(rule.get("statement"))

    if len(frame_marks) >= 2:
        add("`DS`, `MF` and `BF` marks identify drag-strut, moment-frame and braced-frame conditions.")

    return bullets[:8]
