# app/image_extractor/route.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from .claude import extract_structured_info
from .google_vision import extract_text_from_image
import traceback
from typing import List
from pdf2image import convert_from_bytes
import io
from PIL import Image

router = APIRouter()

@router.post("/extract-from-image")
async def extract_from_image(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()

        # Handle PDF files
        if file.content_type == "application/pdf":
            images: List[Image.Image] = convert_from_bytes(
                file_bytes,
                poppler_path=r"C:/poppler/Library/bin"
)

            full_text = ""
            for img in images:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format="PNG")
                img_bytes = img_byte_arr.getvalue()
                text = await extract_text_from_image(img_bytes)
                full_text += text + "\n\n"
            ocr_text = full_text.strip()

        # Handle image files
        elif file.content_type and file.content_type.startswith("image/"):
            ocr_text = await extract_text_from_image(file_bytes)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Please upload an image or PDF.",
            )

        # Debugging
        print("\n===== OCR TEXT START =====")
        print(ocr_text)
        print("===== OCR TEXT END =====\n")

        # Call Claude for structured extraction
        structured_data = await extract_structured_info(ocr_text)

        return {
            "ocr_text": ocr_text,
            "structured_data": structured_data,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
