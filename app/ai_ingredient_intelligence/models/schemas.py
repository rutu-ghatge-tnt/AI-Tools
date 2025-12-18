from typing import List, Optional, Union, Dict, Any
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
    description: Optional[str] = Field(None, description="Description (uses enhanced_description from MongoDB for branded ingredients)")
    category_decided: Optional[str] = Field(None, description="Category from MongoDB for branded ingredients: 'Active' or 'Excipient'")
    category: Optional[str] = Field(None, description="Computed category for general INCI and combinations: 'Active' or 'Excipient' (handles combinations automatically)")
    functionality_category_tree: Optional[List[List[str]]] = []
    chemical_class_category_tree: Optional[List[List[str]]] = []
    match_score: float
    matched_inci: List[str]
    tag: Optional[str] = Field(None, description="Tag: 'B' for branded, 'G' for general INCI")
    match_method: Optional[str] = Field(None, description="Match method: 'exact', 'fuzzy', 'synonym', or 'combination'")

class InciGroup(BaseModel):
    inci_list: List[str]                  # the set of INCI names matched
    items: List[AnalyzeInciItem]          # all branded ingredients that matched this INCI set
    count: int = Field(..., description="Number of items (can be computed as len(items))")    
    
class AnalyzeInciResponse(BaseModel):
    detected: List[InciGroup] = Field(default_factory=list, description="All detected ingredients (branded + general) grouped by INCI")
    unable_to_decode: List[str] = Field(default_factory=list, description="Ingredients that couldn't be decoded - for 'Unable to Decode' tab")
    processing_time: float = Field(..., description="Time taken to process (in seconds)")
    bis_cautions: Optional[Dict[str, List[str]]] = Field(None, description="BIS cautions for ingredients")
    categories: Optional[Dict[str, str]] = Field(None, description="Individual INCI categories mapping for bifurcation: { 'inci_name': 'Active' | 'Excipient' }")
    
    class Config:
        # Exclude None values from JSON serialization to remove deprecated fields
        exclude_none = True

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


class ProductInput(BaseModel):
    """Schema for a single product input"""
    input: str = Field(..., description="URL or INCI string")
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")


class CompareProductsRequest(BaseModel):
    """Request schema for product comparison - supports multiple products"""
    products: List[ProductInput] = Field(..., description="List of products to compare (minimum 2)")


class CompareProductsResponse(BaseModel):
    """Response schema for product comparison - supports multiple products"""
    products: List[ProductComparisonItem] = Field(..., description="List of compared products")
    processing_time: float = Field(..., description="Time taken for comparison (in seconds)")


# ============================================================================
# FORMULA GENERATION SCHEMAS
# ============================================================================

class CreateWishRequest(BaseModel):
    """Request schema for Create A Wish formula generation"""
    category: Optional[str] = Field("skincare", description="Category: skincare or haircare")
    productType: str = Field(..., description="Product type: serum, cream, lotion, toner, etc.")
    benefits: List[str] = Field(default_factory=list, description="List of desired benefits")
    targetAudience: Optional[List[str]] = Field(default_factory=list, description="Target audience (e.g., oily-skin, young-adults)")
    pricePoint: Optional[str] = Field(None, description="Price point category")
    exclusions: List[str] = Field(default_factory=list, description="List of exclusions (e.g., Silicone-free)")
    heroIngredients: List[str] = Field(default_factory=list, description="Specific ingredients to include")
    costMin: Optional[float] = Field(None, description="Minimum cost target per 100g (₹)")
    costMax: Optional[float] = Field(None, description="Maximum cost target per 100g (₹)")
    texture: Optional[str] = Field(None, description="Texture preference: water, gel, serum, lotion, cream, balm")
    fragrance: Optional[str] = Field(None, description="Fragrance preference: none, light, moderate, any")
    notes: Optional[str] = Field(None, description="Additional notes or requirements")
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict, description="User preferences including keyIngredients, avoidIngredients, claims")


class FormulaIngredient(BaseModel):
    """Schema for a single ingredient in a formula"""
    name: str
    inci: str
    percent: Union[float, str]  # Can be number or "q.s."
    cost: float
    function: str
    hero: Optional[bool] = False


class FormulaPhase(BaseModel):
    """Schema for a formula phase"""
    id: str
    name: str
    temp: str
    color: str
    ingredients: List[FormulaIngredient]


class FormulaInsight(BaseModel):
    """Schema for formula insight"""
    icon: str
    title: str
    text: str


class FormulaWarning(BaseModel):
    """Schema for formula warning"""
    type: str  # "critical" or "info"
    text: str


class FormulaCompliance(BaseModel):
    """Schema for formula compliance"""
    silicone: bool
    paraben: bool
    vegan: bool


class GenerateFormulaResponse(BaseModel):
    """Response schema for formula generation"""
    name: str
    version: str
    cost: float
    costTarget: Dict[str, float]
    ph: Dict[str, float]
    texture: str
    shelfLife: str
    phases: List[FormulaPhase]
    insights: List[FormulaInsight]
    warnings: List[FormulaWarning]
    compliance: FormulaCompliance


class DecodeHistoryItem(BaseModel):
    """Schema for decode history item"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this decode")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    status: str = Field(..., description="Status: 'pending' (analysis in progress), 'analyzed' (completed), or 'failed'")
    analysis_result: Optional[Dict] = Field(None, description="Full analysis result (only present when status is 'analyzed')")
    report_data: Optional[str] = Field(None, description="Generated report HTML (if available)")
    notes: Optional[str] = Field(None, description="User notes for this decode")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class ReportTableRow(BaseModel):
    """Schema for a single table row"""
    cells: List[str] = Field(..., description="Array of cell values for this row")

class ReportSection(BaseModel):
    """Schema for a report section"""
    title: str = Field(..., description="Section title (e.g., '1) Submitted INCI List')")
    type: str = Field(..., description="Section type: 'list', 'table', or 'text'")
    content: Union[List[str], List[ReportTableRow], str] = Field(..., description="Section content - list of strings for lists, list of rows for tables, or string for text")

class FormulationSummary(BaseModel):
    """Summary fields for formulation report"""
    formulation_type: Optional[str] = Field(None, description="Overall formulation type (e.g., Water-based Serum)")
    key_active_ingredients: Optional[str] = Field(None, description="Comma-separated list of key active ingredients")
    primary_benefits: Optional[str] = Field(None, description="Comma-separated list of primary benefits")
    recommended_ph_range: Optional[str] = Field(None, description="Recommended pH range (e.g., 5.0-6.5)")
    compliance_status: Optional[str] = Field(None, description="Overall compliance status (e.g., Compliant, Review Needed)")
    critical_concerns: Optional[str] = Field(None, description="Comma-separated list of critical concerns or warnings")

class FormulationReportResponse(BaseModel):
    """Response schema for formulation report as JSON"""
    summary: Optional[FormulationSummary] = Field(None, description="Executive summary fields of the formulation analysis")
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
    status: str = Field(..., description="Status: 'pending' (comparison in progress), 'analyzed' (completed), or 'failed'")
    comparison_result: Optional[Dict] = Field(None, description="Full comparison result (only present when status is 'analyzed')")
    notes: Optional[str] = Field(None, description="User notes for this comparison")
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


class MarketResearchProduct(BaseModel):
    """Schema for a matched product in market research"""
    id: Optional[str] = Field(None, description="Product ID")
    productName: Optional[str] = Field(None, description="Product name")
    brand: Optional[str] = Field(None, description="Brand name")
    ingredients: Optional[List[str]] = Field(default_factory=list, description="List of ingredients")
    image: Optional[str] = Field(None, description="Product image URL")
    images: Optional[List[str]] = Field(default_factory=list, description="List of product image URLs")
    price: Optional[float] = Field(None, description="Product price")
    salePrice: Optional[float] = Field(None, description="Sale price")
    description: Optional[str] = Field(None, description="Product description")
    matched_ingredients: List[str] = Field(default_factory=list, description="List of ingredients that matched")
    match_count: int = Field(0, description="Number of matched ingredients")
    total_ingredients: int = Field(0, description="Total number of ingredients in product")
    match_percentage: float = Field(0.0, description="Percentage of input ingredients matched")
    match_score: float = Field(0.0, description="Weighted match score (0-100) considering actives, excipients, and overall match")
    active_match_count: int = Field(0, description="Number of active ingredients that matched")
    active_ingredients: List[str] = Field(default_factory=list, description="List of matched active ingredients")


class MarketResearchRequest(BaseModel):
    """Request schema for market research"""
    url: Optional[str] = Field(None, description="Product URL to extract ingredients from")
    inci: Optional[str] = Field(None, description="INCI ingredient list")
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")


class MarketResearchResponse(BaseModel):
    """Response schema for market research"""
    products: List[MarketResearchProduct] = Field(default_factory=list, description="List of matched products")
    extracted_ingredients: List[str] = Field(default_factory=list, description="List of extracted ingredients from input")
    total_matched: int = Field(0, description="Total number of matched products")
    processing_time: float = Field(0.0, description="Time taken for processing (in seconds)")
    input_type: str = Field(..., description="Type of input processed")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message when no actives found (e.g., 'This formulation contains no defined active ingredient...')")
    ai_product_type: Optional[str] = Field(None, description="Product type identified by AI (e.g., 'cleanser', 'lotion', 'cream')")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning for ingredient selection and matching strategy")


class MarketResearchHistoryItem(BaseModel):
    """Schema for market research history item"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this market research")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    research_result: Optional[Dict] = Field(None, description="Full market research result")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message")
    ai_product_type: Optional[str] = Field(None, description="Product type identified by AI")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning")
    notes: Optional[str] = Field(None, description="User notes for this research")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class SaveMarketResearchHistoryRequest(BaseModel):
    """Request schema for saving market research history"""
    name: str = Field(..., description="Name for this market research")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    research_result: Optional[Dict] = Field(None, description="Full market research result")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message")
    ai_product_type: Optional[str] = Field(None, description="Product type identified by AI")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning")
    notes: Optional[str] = Field(None, description="User notes")


class GetMarketResearchHistoryResponse(BaseModel):
    """Response schema for getting market research history"""
    items: List[MarketResearchHistoryItem] = Field(..., description="List of history items")
    total: int = Field(..., description="Total number of items")


# ============================================================================
# MAKE A WISH SCHEMAS
# ============================================================================

class MakeWishRequest(BaseModel):
    """Request schema for Make a Wish formula generation (5-stage AI pipeline)"""
    category: str = Field("skincare", description="Category: 'skincare' or 'haircare'")
    productType: str = Field(..., description="Product type: serum, cream, shampoo, conditioner, etc.")
    benefits: List[str] = Field(..., description="List of desired benefits")
    exclusions: List[str] = Field(default_factory=list, description="List of exclusions (e.g., Silicone-free, Paraben-free)")
    heroIngredients: List[str] = Field(default_factory=list, description="Specific ingredients to prioritize")
    costMin: Optional[float] = Field(30, description="Minimum cost target per 100g (₹)")
    costMax: Optional[float] = Field(60, description="Maximum cost target per 100g (₹)")
    texture: Optional[str] = Field("lightweight", description="Texture preference: lightweight, gel, cream, etc.")
    claims: List[str] = Field(default_factory=list, description="Product claims to support (e.g., Vegan, Dermatologist-tested)")
    targetAudience: List[str] = Field(default_factory=list, description="Target audience (e.g., oily-skin, young-adults)")
    additionalNotes: Optional[str] = Field(None, description="Additional notes or requirements")


class MakeWishResponse(BaseModel):
    """Response schema for Make a Wish formula generation"""
    wish_data: Dict[str, Any]
    ingredient_selection: Dict[str, Any] = Field(..., description="Stage 1: Ingredient selection results")
    optimized_formula: Dict[str, Any] = Field(..., description="Stage 2: Optimized formula with percentages")
    manufacturing: Dict[str, Any] = Field(..., description="Stage 3: Manufacturing process instructions")
    cost_analysis: Dict[str, Any] = Field(..., description="Stage 4: Cost analysis and pricing recommendations")
    compliance: Dict[str, Any] = Field(..., description="Stage 5: Regulatory compliance check")
    metadata: Dict[str, Any] = Field(..., description="Metadata about the generation process")