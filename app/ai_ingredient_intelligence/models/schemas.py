from typing import List, Optional
from pydantic import BaseModel, Field

class AnalyzeInciRequest(BaseModel):
    inci_names: List[str] = Field(..., description="Raw INCI names from product label")

class AnalyzeInciItem(BaseModel):
    ingredient_name: str
    supplier_name: Optional[str] = None
    description: Optional[str] = None
    functionality_category_tree: Optional[List[List[str]]] = []
    chemical_class_category_tree: Optional[List[List[str]]] = []
    match_score: float
    matched_inci: List[str]
    matched_count: int
    total_brand_inci: int

class AnalyzeInciResponse(BaseModel):
    matched: List[AnalyzeInciItem]
    unmatched: List[str]
    overall_confidence: float
    processing_time: float
