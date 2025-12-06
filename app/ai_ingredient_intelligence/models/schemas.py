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
    ingredient_id: Optional[str] = Field(None, description="Ingredient ID from branded ingredients collection (for distributor mapping)")
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
    tag: Optional[str] = Field(None, description="Tag: 'B' for branded, 'G' for general INCI")
    match_method: Optional[str] = Field(None, description="Match method: 'exact', 'fuzzy', or 'synonym'")

class InciGroup(BaseModel):
    inci_list: List[str]                  # the set of INCI names matched
    items: List[AnalyzeInciItem]          # all branded ingredients that matched this INCI set
    count: int    
    
class AnalyzeInciResponse(BaseModel):
    grouped: List[InciGroup] = Field(default_factory=list, description="All matched ingredients (branded + general) - for backward compatibility")
    branded_ingredients: List[AnalyzeInciItem] = Field(default_factory=list, description="Branded ingredients only (tag='B') - flat list")
    branded_grouped: List[InciGroup] = Field(default_factory=list, description="Branded ingredients grouped by INCI - shows all branded options for each INCI")
    general_ingredients_list: List[AnalyzeInciItem] = Field(default_factory=list, description="General INCI ingredients only (tag='G') - shown at end in Matched Ingredients tab")
    unable_to_decode: List[str] = Field(default_factory=list, description="Ingredients that couldn't be decoded - for 'Unable to Decode' tab")
    unmatched: List[str] = Field(default_factory=list, description="DEPRECATED: Use unable_to_decode instead")
    overall_confidence: float
    processing_time: float
    extracted_text: Optional[str] = Field(None, description="Text extracted from input")
    input_type: str = Field(..., description="Type of input processed")
    bis_cautions: Optional[Dict[str, List[str]]] = Field(None, description="BIS cautions for ingredients")
    ingredient_tags: Optional[Dict[str, str]] = Field(None, description="Mapping of ingredient names to tags: 'B' for branded, 'G' for general")

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


class ProductComparisonItem(BaseModel):
    """Schema for a single product in comparison"""
    product_name: Optional[str] = Field(None, description="Product name")
    brand_name: Optional[str] = Field(None, description="Brand name")
    inci: List[str] = Field(default_factory=list, description="List of INCI ingredients")
    benefits: List[str] = Field(default_factory=list, description="List of product benefits")
    claims: List[str] = Field(default_factory=list, description="List of product claims")
    price: Optional[str] = Field(None, description="Product price")
    cruelty_free: Optional[bool] = Field(None, description="Whether product is cruelty-free")
    sulphate_free: Optional[bool] = Field(None, description="Whether product is sulphate-free")
    paraben_free: Optional[bool] = Field(None, description="Whether product is paraben-free")
    vegan: Optional[bool] = Field(None, description="Whether product is vegan")
    organic: Optional[bool] = Field(None, description="Whether product is organic")
    fragrance_free: Optional[bool] = Field(None, description="Whether product is fragrance-free")
    non_comedogenic: Optional[bool] = Field(None, description="Whether product is non-comedogenic")
    hypoallergenic: Optional[bool] = Field(None, description="Whether product is hypoallergenic")
    extracted_text: Optional[str] = Field(None, description="Raw extracted text from URL or INCI input")


class CompareProductsRequest(BaseModel):
    """Request schema for product comparison"""
    input1: str = Field(..., description="First input: URL or INCI string")
    input2: str = Field(..., description="Second input: URL or INCI string")
    input1_type: str = Field(..., description="Type of input1: 'url' or 'inci'")
    input2_type: str = Field(..., description="Type of input2: 'url' or 'inci'")


class CompareProductsResponse(BaseModel):
    """Response schema for product comparison"""
    product1: ProductComparisonItem = Field(..., description="First product data")
    product2: ProductComparisonItem = Field(..., description="Second product data")
    processing_time: float = Field(..., description="Time taken for comparison (in seconds)")


class DecodeHistoryItem(BaseModel):
    """Schema for decode history item"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this decode")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    analysis_result: Dict = Field(..., description="Full analysis result")
    report_data: Optional[str] = Field(None, description="Generated report HTML (if available)")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class ReportTableRow(BaseModel):
    """Schema for a single table row"""
    cells: List[str] = Field(..., description="Array of cell values for this row")

class ReportSection(BaseModel):
    """Schema for a report section"""
    title: str = Field(..., description="Section title (e.g., '1) Submitted INCI List')")
    type: str = Field(..., description="Section type: 'list', 'table', or 'text'")
    content: Union[List[str], List[ReportTableRow], str] = Field(..., description="Section content - list of strings for lists, list of rows for tables, or string for text")

class FormulationReportResponse(BaseModel):
    """Response schema for formulation report as JSON"""
    inci_list: List[str] = Field(..., description="List of submitted INCI ingredients")
    analysis_table: List[ReportTableRow] = Field(..., description="Analysis table with columns: Ingredient | Category | Functions/Notes | BIS Cautions")
    compliance_panel: List[ReportTableRow] = Field(default_factory=list, description="Compliance panel table")
    preservative_efficacy: List[ReportTableRow] = Field(default_factory=list, description="Preservative efficacy check table")
    risk_panel: List[ReportTableRow] = Field(default_factory=list, description="Risk panel table")
    cumulative_benefit: List[ReportTableRow] = Field(default_factory=list, description="Cumulative benefit panel table")
    claim_panel: List[ReportTableRow] = Field(default_factory=list, description="Claim panel table")
    recommended_ph_range: Optional[str] = Field(None, description="Recommended pH range text")
    expected_benefits_analysis: List[ReportTableRow] = Field(default_factory=list, description="Expected benefits analysis table (if provided)")
    raw_text: Optional[str] = Field(None, description="Raw report text for reference")

class SaveDecodeHistoryRequest(BaseModel):
    """Request schema for saving decode history"""
    name: str = Field(..., description="Name for this decode")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    analysis_result: Dict = Field(..., description="Full analysis result")
    report_data: Optional[str] = Field(None, description="Generated report HTML (optional)")


class GetDecodeHistoryResponse(BaseModel):
    """Response schema for getting decode history"""
    items: List[DecodeHistoryItem] = Field(..., description="List of history items")
    total: int = Field(..., description="Total number of items")


class CompareHistoryItem(BaseModel):
    """Schema for compare history item"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this comparison")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input1: str = Field(..., description="First input (URL or INCI)")
    input2: str = Field(..., description="Second input (URL or INCI)")
    input1_type: str = Field(..., description="Type of input1: 'url' or 'inci'")
    input2_type: str = Field(..., description="Type of input2: 'url' or 'inci'")
    comparison_result: Dict = Field(..., description="Full comparison result")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class SaveCompareHistoryRequest(BaseModel):
    """Request schema for saving compare history"""
    name: str = Field(..., description="Name for this comparison")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input1: str = Field(..., description="First input (URL or INCI)")
    input2: str = Field(..., description="Second input (URL or INCI)")
    input1_type: str = Field(..., description="Type of input1: 'url' or 'inci'")
    input2_type: str = Field(..., description="Type of input2: 'url' or 'inci'")
    comparison_result: Dict = Field(..., description="Full comparison result")


class GetCompareHistoryResponse(BaseModel):
    """Response schema for getting compare history"""
    items: List[CompareHistoryItem] = Field(..., description="List of history items")
    total: int = Field(..., description="Total number of items")