from typing import List, Optional, Union
from pydantic import BaseModel, Field
from fastapi import UploadFile

class AnalyzeInciRequest(BaseModel):
    inci_names: Optional[List[str]] = Field(None, description="Raw INCI names from product label")
    # New fields for different input types
    pdf_file: Optional[UploadFile] = Field(None, description="PDF file containing ingredient list")
    image_file: Optional[UploadFile] = Field(None, description="Image file containing ingredient list")
    camera_image: Optional[str] = Field(None, description="Base64 encoded camera image")
    input_type: str = Field(..., description="Type of input: 'text', 'pdf', 'image', or 'camera'")

class AnalyzeInciItem(BaseModel):
    ingredient_name: str
    supplier_name: Optional[str] = None
    description: Optional[str] = None
    rephrased_description: Optional[str] = None   # ✅ new
    category_decided: Optional[str] = None        # ✅ new
    functionality_category_tree: Optional[List[List[str]]] = []
    chemical_class_category_tree: Optional[List[List[str]]] = []
    match_score: float
    matched_inci: List[str]
    matched_count: int
    total_brand_inci: int

class InciGroup(BaseModel):
    inci_list: List[str]                  # the set of INCI names matched
    items: List[AnalyzeInciItem]          # all branded ingredients that matched this INCI set
    count: int    
    
class AnalyzeInciResponse(BaseModel):
    grouped: List[InciGroup]  
    unmatched: List[str]
    overall_confidence: float
    processing_time: float
    extracted_text: Optional[str] = Field(None, description="Text extracted from input")
    input_type: str = Field(..., description="Type of input processed")

                        # how many branded ingredients matched
