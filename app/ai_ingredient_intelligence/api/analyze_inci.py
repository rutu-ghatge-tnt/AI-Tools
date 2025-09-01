# app/api/analyze_inci.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
import time
from typing import List, Optional
from collections import defaultdict

from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.logic.ocr_processor import OCRProcessor
from app.ai_ingredient_intelligence.models.schemas import (
    AnalyzeInciRequest,
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup,   # ⬅️ new schema for grouping
)

router = APIRouter(tags=["INCI Analysis"])

# Initialize OCR processor
ocr_processor = OCRProcessor()


@router.post("/analyze-inci", response_model=AnalyzeInciResponse)
async def analyze_inci(
    input_type: str = Form(..., description="Type of input: 'text', 'pdf', 'image', or 'camera'"),
    inci_names: Optional[List[str]] = Form(None, description="Raw INCI names from product label"),
    pdf_file: Optional[UploadFile] = File(None, description="PDF file containing ingredient list"),
    image_file: Optional[UploadFile] = File(None, description="Image file containing ingredient list"),
    camera_image: Optional[str] = Form(None, description="Base64 encoded camera image")
):
    start = time.time()
    
    try:
        # Validate input type
        if input_type not in ['text', 'pdf', 'image', 'camera']:
            raise HTTPException(status_code=400, detail="Invalid input_type. Must be 'text', 'pdf', 'image', or 'camera'")
        
        # Validate required inputs based on type
        if input_type == 'text' and not inci_names:
            raise HTTPException(status_code=400, detail="inci_names is required for text input type")
        elif input_type == 'pdf' and not pdf_file:
            raise HTTPException(status_code=400, detail="pdf_file is required for PDF input type")
        elif input_type == 'image' and not image_file:
            raise HTTPException(status_code=400, detail="image_file is required for image input type")
        elif input_type == 'camera' and not camera_image:
            raise HTTPException(status_code=400, detail="camera_image is required for camera input type")
        
        # Process input and extract ingredients
        ingredients, extracted_text = await ocr_processor.process_input(
            input_type=input_type,
            inci_names=inci_names,
            pdf_file=pdf_file,
            image_file=image_file,
            camera_image=camera_image
        )
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients could be extracted from the input")
        
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
        input_type=input_type
    )


# Alternative endpoint for JSON-based requests (backward compatibility)
@router.post("/analyze-inci-json", response_model=AnalyzeInciResponse)
async def analyze_inci_json(payload: AnalyzeInciRequest):
    start = time.time()
    
    try:
        # Validate input type
        if payload.input_type not in ['text', 'pdf', 'image', 'camera']:
            raise HTTPException(status_code=400, detail="Invalid input_type. Must be 'text', 'pdf', 'image', or 'camera'")
        
        # Process input and extract ingredients
        ingredients, extracted_text = await ocr_processor.process_input(
            input_type=payload.input_type,
            inci_names=payload.inci_names,
            pdf_file=payload.pdf_file,
            image_file=payload.image_file,
            camera_image=payload.camera_image
        )
        
        if not ingredients:
            raise HTTPException(status_code=400, detail="No ingredients could be extracted from the input")
        
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
        input_type=payload.input_type
    )
