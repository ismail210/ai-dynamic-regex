"""Damaged/incomplete AISC steel-label reconstruction.

Given corrupted drawing text (OCR errors, torn/smudged labels, truncated
tokens), rank valid AISC catalog candidates. The catalog is the source of
truth for validity; nothing in this package invents a label that is not in
``services.database_loader.catalog_entries()``.

Pipeline: corrupted text -> conservative normalization -> family/partial
pattern extraction -> deterministic candidate generation -> learned
candidate scoring -> catalog-valid, ranked Top-K.
"""
