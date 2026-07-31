"""
Dynamic Regex Orchestrator (internal module)
============================================

Routes token analysis through the AI-primary prediction orchestrator, then
applies Dynamic Regex learning / validation around the AI section decision.

The AISC database never decides the predicted class.
"""

from __future__ import annotations

from typing import List

from services.prediction.orchestrator import predict_token
from services.regex_knowledge_base import knowledge_base


def analyze_token(
    token: str, source_file: str = "", queue_unknown: bool = True, persist: bool = True,
) -> dict:
    """Run the AI-first prediction + regex pipeline for one token."""

    return predict_token(
        token,
        source_file=source_file,
        queue_unknown=queue_unknown,
        persist_learning=persist,
    )


def analyze_tokens(
    tokens: List[str], source_file: str = "", queue_unknown: bool = True,
) -> List[dict]:
    """Analyze a batch of tokens, persisting the KB once at the end."""

    results = [
        analyze_token(t, source_file=source_file, queue_unknown=queue_unknown, persist=False)
        for t in tokens
    ]
    knowledge_base._write()  # noqa: SLF001 - intentional single batch flush
    return results
