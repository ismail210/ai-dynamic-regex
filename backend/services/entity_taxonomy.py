"""
Entity Taxonomy
===============

Two-stage classification for engineering tokens / takeoff entities.

Runtime categories remain backward-compatible. Takeoff-facing entity classes
extend the vocabulary for plates, fasteners, joists, deck, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from services.family_codes import MODERN_FAMILY_CODES

CATEGORY_STRUCTURAL = "structural_section"
CATEGORY_MATERIAL = "material"
CATEGORY_BOLT = "bolt"
CATEGORY_PLATE = "plate"
CATEGORY_PIPE = "pipe"
CATEGORY_MISC = "miscellaneous"
CATEGORY_ANCHOR = "anchor_bolt"
CATEGORY_NUT = "nut"
CATEGORY_WASHER = "washer"
CATEGORY_GRATING = "grating"
CATEGORY_JOIST = "joist"
CATEGORY_DECK = "deck"
CATEGORY_CONNECTION_PLATE = "connection_plate"
CATEGORY_STIFFENER = "stiffener"
CATEGORY_UNKNOWN = "unknown"

CATEGORIES: List[str] = [
    CATEGORY_STRUCTURAL,
    CATEGORY_PLATE,
    CATEGORY_MATERIAL,
    CATEGORY_BOLT,
    CATEGORY_ANCHOR,
    CATEGORY_NUT,
    CATEGORY_WASHER,
    CATEGORY_GRATING,
    CATEGORY_JOIST,
    CATEGORY_DECK,
    CATEGORY_CONNECTION_PLATE,
    CATEGORY_STIFFENER,
    CATEGORY_PIPE,
    CATEGORY_MISC,
    CATEGORY_UNKNOWN,
]

CATEGORY_LABELS: Dict[str, str] = {
    CATEGORY_STRUCTURAL: "Steel Section",
    CATEGORY_MATERIAL: "Material",
    CATEGORY_BOLT: "Bolt",
    CATEGORY_PLATE: "Plate",
    CATEGORY_PIPE: "Pipe",
    CATEGORY_MISC: "Miscellaneous",
    CATEGORY_ANCHOR: "Anchor Bolt",
    CATEGORY_NUT: "Nut",
    CATEGORY_WASHER: "Washer",
    CATEGORY_GRATING: "Grating",
    CATEGORY_JOIST: "Joist",
    CATEGORY_DECK: "Deck",
    CATEGORY_CONNECTION_PLATE: "Connection Plate",
    CATEGORY_STIFFENER: "Stiffener",
    CATEGORY_UNKNOWN: "Unknown",
}

AISC_TYPE_TO_CATEGORY: Dict[str, str] = {
    "W": CATEGORY_STRUCTURAL,
    "WT": CATEGORY_STRUCTURAL,
    "M": CATEGORY_STRUCTURAL,
    "S": CATEGORY_STRUCTURAL,
    "HP": CATEGORY_STRUCTURAL,
    "C": CATEGORY_STRUCTURAL,
    "MC": CATEGORY_STRUCTURAL,
    "L": CATEGORY_STRUCTURAL,
    "2L": CATEGORY_STRUCTURAL,
    "HSS": CATEGORY_STRUCTURAL,
    "MT": CATEGORY_STRUCTURAL,
    "ST": CATEGORY_STRUCTURAL,
    "PIPE": CATEGORY_PIPE,
}

MATERIAL_GRADES: Set[str] = {
    "A36", "A53", "A106", "A500", "A501", "A529", "A572", "A588",
    "A709", "A913", "A992", "A1085", "A514", "A242",
}

BOLT_GRADES: Set[str] = {
    "A307", "A325", "A490", "A449", "F1852", "F2280", "A563", "F436",
}

ANCHOR_HINTS = ("AB", "ANCHOR", "HAS", "ROD")
NUT_HINTS = ("NUT", "HEXNUT")
WASHER_HINTS = ("WASHER", "FLATWASHER")
JOIST_HINTS = ("KJOIST", "JOIST", "LH", "DLH")
DECK_HINTS = ("DECK", "BDECK", "NDECK", "FORMDECK")
GRATING_HINTS = ("GRATING", "GRATE")
STIFFENER_HINTS = ("STIFFENER", "STIF")


@dataclass
class EntityClassification:
    category: str
    category_label: str
    class_name: Optional[str]
    source: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "category_label": self.category_label,
            "class": self.class_name,
            "source": self.source,
            "confidence": round(self.confidence, 4),
        }


def category_for_aisc_type(shape_type: Optional[str]) -> str:
    if not shape_type:
        return CATEGORY_MISC
    return AISC_TYPE_TO_CATEGORY.get(str(shape_type).strip().upper(), CATEGORY_STRUCTURAL)


def classify_category(token: str) -> EntityClassification:
    t = str(token).strip().upper().replace(" ", "")

    if any(h in t for h in ANCHOR_HINTS) and re.search(r"\d", t):
        return EntityClassification(CATEGORY_ANCHOR, CATEGORY_LABELS[CATEGORY_ANCHOR], t, "heuristic", 0.8)
    if any(t.startswith(h) or h in t for h in NUT_HINTS):
        return EntityClassification(CATEGORY_NUT, CATEGORY_LABELS[CATEGORY_NUT], t, "heuristic", 0.8)
    if any(h in t for h in WASHER_HINTS):
        return EntityClassification(CATEGORY_WASHER, CATEGORY_LABELS[CATEGORY_WASHER], t, "heuristic", 0.8)
    if any(h in t for h in GRATING_HINTS):
        return EntityClassification(CATEGORY_GRATING, CATEGORY_LABELS[CATEGORY_GRATING], t, "heuristic", 0.8)
    if any(h in t for h in JOIST_HINTS):
        return EntityClassification(CATEGORY_JOIST, CATEGORY_LABELS[CATEGORY_JOIST], t, "heuristic", 0.8)
    if any(h in t for h in DECK_HINTS):
        return EntityClassification(CATEGORY_DECK, CATEGORY_LABELS[CATEGORY_DECK], t, "heuristic", 0.8)
    if "CONNECTION" in t and "PLATE" in t:
        return EntityClassification(CATEGORY_CONNECTION_PLATE, CATEGORY_LABELS[CATEGORY_CONNECTION_PLATE], t, "heuristic", 0.85)
    if any(h in t for h in STIFFENER_HINTS):
        return EntityClassification(CATEGORY_STIFFENER, CATEGORY_LABELS[CATEGORY_STIFFENER], t, "heuristic", 0.8)

    if t in BOLT_GRADES:
        return EntityClassification(CATEGORY_BOLT, CATEGORY_LABELS[CATEGORY_BOLT], t, "heuristic", 0.95)
    if t in MATERIAL_GRADES:
        return EntityClassification(CATEGORY_MATERIAL, CATEGORY_LABELS[CATEGORY_MATERIAL], t, "heuristic", 0.95)
    if t.startswith("PLATE") or re.fullmatch(r"PL\d.*", t) or "BASEPLATE" in t:
        return EntityClassification(CATEGORY_PLATE, CATEGORY_LABELS[CATEGORY_PLATE], "PL", "heuristic", 0.85)
    if t.startswith("PIPE"):
        return EntityClassification(CATEGORY_PIPE, CATEGORY_LABELS[CATEGORY_PIPE], "PIPE", "heuristic", 0.95)
    if re.fullmatch(r"S-\d+", t):
        return EntityClassification(CATEGORY_MISC, CATEGORY_LABELS[CATEGORY_MISC], "SHEET", "heuristic", 0.70)
    if re.fullmatch(r"A\d{2,4}(?:M)?", t):
        if t in BOLT_GRADES or t[:4] in {"A307", "A325", "A490", "A449"}:
            return EntityClassification(CATEGORY_BOLT, CATEGORY_LABELS[CATEGORY_BOLT], t, "heuristic", 0.90)
        return EntityClassification(CATEGORY_MATERIAL, CATEGORY_LABELS[CATEGORY_MATERIAL], t, "heuristic", 0.80)

    for prefix, cls in (
        ("HSS", "HSS"), ("WT", "WT"), ("HP", "HP"), ("MC", "MC"),
        ("MT", "MT"), ("ST", "ST"), ("2L", "2L"), ("WF", "W"),
    ):
        if t.startswith(prefix) and re.search(r"\d", t):
            return EntityClassification(CATEGORY_STRUCTURAL, CATEGORY_LABELS[CATEGORY_STRUCTURAL], cls, "heuristic", 0.85)

    if re.fullmatch(r"[WCSML]\d.*X.*", t):
        return EntityClassification(CATEGORY_STRUCTURAL, CATEGORY_LABELS[CATEGORY_STRUCTURAL], t[0], "heuristic", 0.80)

    return EntityClassification(CATEGORY_UNKNOWN, CATEGORY_LABELS[CATEGORY_UNKNOWN], None, "heuristic", 0.35)


def resolve_entity(
    token: str,
    aisc_type: Optional[str] = None,
    model_class: Optional[str] = None,
    database_type: Optional[str] = None,
) -> EntityClassification:
    """
    Resolve entity category / family metadata.

    AI ``model_class`` (family) and heuristic token analysis decide ``class_name``.
    ``aisc_type`` / ``database_type`` may enrich category only — they never become
    the predicted class when an AI family is available.
    """

    heuristic = classify_category(token)
    if heuristic.category in (
        CATEGORY_MATERIAL, CATEGORY_BOLT, CATEGORY_PLATE, CATEGORY_ANCHOR, CATEGORY_NUT,
        CATEGORY_WASHER, CATEGORY_GRATING, CATEGORY_JOIST, CATEGORY_DECK,
        CATEGORY_CONNECTION_PLATE, CATEGORY_STIFFENER,
    ):
        return heuristic

    db_type = database_type or aisc_type

    if model_class:
        model_cat = category_for_aisc_type(model_class)
        # Prefer AI family; optionally confirm category via DB type metadata.
        if db_type:
            db_cat = category_for_aisc_type(db_type)
            if heuristic.category in (CATEGORY_STRUCTURAL, CATEGORY_PIPE, CATEGORY_MISC, CATEGORY_UNKNOWN):
                return EntityClassification(
                    category=db_cat if db_cat != CATEGORY_MISC else model_cat,
                    category_label=CATEGORY_LABELS[
                        db_cat if db_cat != CATEGORY_MISC else model_cat
                    ],
                    class_name=str(model_class).strip().upper(),
                    source="model+database_metadata",
                    confidence=0.9,
                )
        if heuristic.category in (CATEGORY_MISC, CATEGORY_UNKNOWN):
            return EntityClassification(
                category=model_cat,
                category_label=CATEGORY_LABELS[model_cat],
                class_name=str(model_class).strip().upper(),
                source="model",
                confidence=0.75,
            )
        if heuristic.category in (CATEGORY_STRUCTURAL, CATEGORY_PIPE):
            return EntityClassification(
                category=heuristic.category,
                category_label=CATEGORY_LABELS[heuristic.category],
                class_name=str(model_class).strip().upper(),
                source="model+heuristic",
                confidence=0.85,
            )

    # No AI family — category metadata from DB is allowed, but class remains heuristic.
    if db_type and heuristic.category in (CATEGORY_MISC, CATEGORY_UNKNOWN, CATEGORY_STRUCTURAL, CATEGORY_PIPE):
        cat = category_for_aisc_type(db_type)
        return EntityClassification(
            category=cat,
            category_label=CATEGORY_LABELS[cat],
            class_name=heuristic.class_name,
            source="database_metadata",
            confidence=0.6,
        )
    return heuristic


def list_categories() -> List[dict]:
    return [{"id": c, "label": CATEGORY_LABELS[c]} for c in CATEGORIES]


MODEL_PAGE_TAB_ORDER: List[str] = [CATEGORY_STRUCTURAL, CATEGORY_MATERIAL, CATEGORY_BOLT, CATEGORY_PLATE, CATEGORY_MISC]
MODEL_PAGE_TAB_LABELS: Dict[str, str] = {
    CATEGORY_STRUCTURAL: "Steel Sections",
    CATEGORY_MATERIAL: "Materials",
    CATEGORY_BOLT: "Bolts",
    CATEGORY_PLATE: "Plates",
    CATEGORY_MISC: "Other",
}
MODEL_PAGE_TABS: List[dict] = [{"id": "all", "label": "All"}, *[{"id": t, "label": MODEL_PAGE_TAB_LABELS[t]} for t in MODEL_PAGE_TAB_ORDER]]
_STRUCTURAL_MODEL_CLASSES: Set[str] = MODERN_FAMILY_CODES
_BOLT_PREFIXES = {"A307", "A325", "A490", "A449", "A228", "F185", "F228", "F436"}


def category_label_for_model_page(category_id: str) -> str:
    return MODEL_PAGE_TAB_LABELS.get(category_id, CATEGORY_LABELS.get(category_id, category_id))


def category_for_model_class(class_label: str) -> str:
    t = str(class_label or "").strip().upper()
    if not t:
        return CATEGORY_MISC
    if t in {"PL", "PLATE"} or re.fullmatch(r"PL\d.*", t):
        return CATEGORY_PLATE
    if t in BOLT_GRADES or t[:4] in _BOLT_PREFIXES:
        return CATEGORY_BOLT
    if re.fullmatch(r"F\d{3,4}", t):
        return CATEGORY_BOLT
    if t in MATERIAL_GRADES:
        return CATEGORY_MATERIAL
    if re.fullmatch(r"A\d{2,4}(?:M)?", t):
        return CATEGORY_MATERIAL
    if t in _STRUCTURAL_MODEL_CLASSES:
        return CATEGORY_STRUCTURAL
    return CATEGORY_MISC


def map_model_classes(class_labels: List[str]) -> Dict[str, dict]:
    mapping: Dict[str, dict] = {}
    for label in class_labels:
        name = str(label).strip()
        if not name:
            continue
        entity_type = category_for_model_class(name)
        mapping[name] = {
            "entity_type": entity_type,
            "entity_type_label": category_label_for_model_page(entity_type),
            "tab_id": entity_type,
        }
    return mapping
