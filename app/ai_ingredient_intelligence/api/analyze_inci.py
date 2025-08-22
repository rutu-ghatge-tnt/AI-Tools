# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException
import time
from typing import List
from collections import defaultdict

from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.models.schemas import (
    AnalyzeInciRequest,
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup,   # ⬅️ new schema for grouping
)

router = APIRouter(tags=["INCI Analysis"])


@router.post("/analyze-inci", response_model=AnalyzeInciResponse)
async def analyze_inci(payload: AnalyzeInciRequest):
    start = time.time()
    try:
        matched_raw, unmatched = await match_inci_names(payload.inci_names)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Group by matched_inci (tuple key so it's hashable)
    grouped_dict = defaultdict(list)
    for item in items:
        key = tuple(sorted(item.matched_inci))
        grouped_dict[key].append(item)

    grouped: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in grouped_dict.items()
    ]

    # 🔹 Confidence (average of match scores across all items)
    confidence = round(sum(i.match_score for i in items) / len(items), 2) if items else 0.0

    return AnalyzeInciResponse(
        grouped=grouped,
        unmatched=unmatched,
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
    )
