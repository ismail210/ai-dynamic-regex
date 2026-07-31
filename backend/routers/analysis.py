"""
Analysis router
===============

Exposes the AI Dynamic Regex engine directly (without a PDF), plus read access
to the self-learning knowledge base and aggregate statistics.

Endpoints
---------
POST /analyze          : analyze a single token
POST /analyze/batch    : analyze a list of tokens
GET  /knowledge-base   : full learned-regex knowledge base
GET  /knowledge-base/{cls} : a single class record
GET  /stats            : knowledge-base statistics
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.dynamic_regex_service import analyze_token, analyze_tokens
from services.regex_knowledge_base import knowledge_base

router = APIRouter()


class TokenRequest(BaseModel):
    token: str = Field(..., min_length=1, examples=["WF18X40"])


class BatchRequest(BaseModel):
    tokens: List[str] = Field(..., examples=[["W18X40", "HSS8X8X1/2", "WF18X40"]])


@router.post("/analyze")
def analyze_single(payload: TokenRequest):
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token must not be empty.")
    return analyze_token(token)


@router.post("/analyze/batch")
def analyze_batch(payload: BatchRequest):
    tokens = [t.strip() for t in payload.tokens if t and t.strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail="No valid tokens provided.")
    results = analyze_tokens(tokens)
    return {"token_count": len(results), "results": results}


@router.get("/knowledge-base")
def get_knowledge_base():
    return {
        "classes": knowledge_base.all(),
        "stats": knowledge_base.stats(),
    }


@router.get("/knowledge-base/{cls}")
def get_knowledge_base_class(cls: str):
    record = knowledge_base.get(cls.upper())
    if record is None:
        raise HTTPException(status_code=404, detail=f"Class '{cls}' not found.")
    return {"class": cls.upper(), "record": record}


@router.get("/stats")
def get_stats():
    return knowledge_base.stats()
