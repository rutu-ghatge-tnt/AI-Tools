# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException
import time
from typing import List
from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.models.schemas import AnalyzeInciRequest, AnalyzeInciResponse, AnalyzeInciItem

router = APIRouter(tags=["INCI Analysis"])

@router.post("/analyze-inci", response_model=AnalyzeInciResponse)
async def analyze_inci(payload: AnalyzeInciRequest):
    start = time.time()
    try:
        matched_raw, unmatched = await match_inci_names(payload.inci_names)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # 🔹 Calculate overall confidence: sum of match_score for each matched brand / total brands
    if matched_raw:
        confidence = round(sum(m.get("match_score", 0) for m in matched_raw) / len(matched_raw), 2)
    else:
        confidence = 0.0

    return AnalyzeInciResponse(
        matched=items,
        unmatched=unmatched,
        overall_confidence=confidence,
        processing_time=round(time.time() - start, 3),
    )
