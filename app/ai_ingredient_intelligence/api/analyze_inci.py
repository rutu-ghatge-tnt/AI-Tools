# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException, Form
import time
from typing import List, Optional
from collections import defaultdict

from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.models.schemas import (
    AnalyzeInciRequest,
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup,   # ⬅️ new schema for grouping
)

router = APIRouter(tags=["INCI Analysis"])


@router.post("/analyze-inci-form", response_model=AnalyzeInciResponse)
async def analyze_inci_form(
    inci_names: List[str] = Form(..., description="Raw INCI names from product label")
):
    start = time.time()
    
    try:
        if not inci_names:
            raise HTTPException(status_code=400, detail="inci_names is required")
        
        # Process text input
        ingredients = inci_names
        extracted_text = ", ".join(ingredients)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients provided")
        
        # Match ingredients using existing logic
        matched_raw, unmatched = await match_inci_names(ingredients)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_inci: {e}")
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
        extracted_text=extracted_text,
        input_type="text"
    )


# Simple JSON endpoint for frontend compatibility
@router.post("/analyze-inci", response_model=AnalyzeInciResponse)
async def analyze_inci(payload: dict):
    start = time.time()
    
    try:
        # Validate payload format: { inci_names: ["ingredient1", "ingredient2", ...] }
        if "inci_names" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: inci_names")
        
        if not isinstance(payload["inci_names"], list):
            raise HTTPException(status_code=400, detail="inci_names must be a list of strings")
        
        ingredients = payload["inci_names"]
        extracted_text = ", ".join(ingredients)
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients provided")
        
        # Match ingredients using existing logic
        matched_raw, unmatched = await match_inci_names(ingredients)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_inci_json: {e}")
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
        extracted_text=extracted_text,
        input_type="text"
    )
