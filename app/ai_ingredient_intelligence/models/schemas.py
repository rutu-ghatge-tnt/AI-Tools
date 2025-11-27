from typing import List, Optional, Union, Dict
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
    bis_cautions: Optional[Dict[str, List[str]]] = Field(None, description="BIS cautions for ingredients")

                        # how many branded ingredients matched

class ExtractIngredientsResponse(BaseModel):
    """Response schema for ingredient extraction from URL"""
    ingredients: List[str] = Field(..., description="List of extracted INCI ingredient names")
    extracted_text: str = Field(..., description="Full text scraped from the product page")
    platform: str = Field(..., description="Detected e-commerce platform (amazon, nykaa, flipkart, generic)")
    url: str = Field(..., description="The URL that was scraped")
    processing_time: float = Field(..., description="Time taken to extract ingredients (in seconds)")
    is_estimated: bool = Field(False, description="Whether ingredients are estimated from AI search (true) or directly extracted (false)")
    source: str = Field("url_extraction", description="Source of ingredients: 'url_extraction' or 'ai_search'")
    product_name: Optional[str] = Field(None, description="Detected product name (used for AI search fallback)")
    message: Optional[str] = Field(None, description="Optional message about the extraction method")