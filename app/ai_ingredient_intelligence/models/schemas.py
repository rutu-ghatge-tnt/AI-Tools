from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_serializer
from fastapi import UploadFile

class AnalyzeInciRequest(BaseModel):
    inci_names: List[str] = Field(..., description="Raw INCI names from product label (array of strings)")
    # New fields for different input types
    pdf_file: Optional[UploadFile] = Field(None, description="PDF file containing ingredient list")
    image_file: Optional[UploadFile] = Field(None, description="Image file containing ingredient list")
    camera_image: Optional[str] = Field(None, description="Base64 encoded camera image")
    input_type: str = Field(..., description="Type of input: 'text', 'pdf', 'image', or 'camera'")

class AnalyzeInciItem(BaseModel):
    ingredient_name: str
    ingredient_id: Optional[str] = Field(None, description="Ingredient ID from branded ingredients collection (for distributor mapping)", exclude=False)
    supplier_id: Optional[str] = Field(None, description="Supplier ID from suppliers collection", exclude=False)
    supplier_name: Optional[str] = Field(None, description="Supplier name for branded ingredients", exclude=False)
    description: Optional[str] = Field(None, description="Description (uses enhanced_description from MongoDB for branded ingredients)")
    category_decided: Optional[str] = Field(None, description="Category from MongoDB for branded ingredients: 'Active' or 'Excipient'")
    category: Optional[str] = Field(None, description="Computed category for general INCI and combinations: 'Active' or 'Excipient' (handles combinations automatically)")
    functionality_category_tree: Optional[List[List[str]]] = []
    chemical_class_category_tree: Optional[List[List[str]]] = []
    match_score: float
    matched_inci: List[str]
    tag: Optional[str] = Field(None, description="Tag: 'B' for branded, 'G' for general INCI")
    match_method: Optional[str] = Field(None, description="Match method: 'exact', 'fuzzy', 'synonym', or 'combination'")
    
    # Pydantic v2: Use model_config to ensure supplier_name, supplier_id and ingredient_id are always included even when None
    # This ensures these fields are always serialized, even when None
    model_config = ConfigDict(exclude_none=False)
    
    def model_dump(self, **kwargs):
        """Override model_dump to always include supplier_name, supplier_id and ingredient_id even when None"""
        # Get the default dump
        data = super().model_dump(**kwargs)
        # Force include supplier_name, supplier_id and ingredient_id even if they were excluded
        if 'supplier_name' not in data:
            data['supplier_name'] = getattr(self, 'supplier_name', None)
        if 'supplier_id' not in data:
            data['supplier_id'] = getattr(self, 'supplier_id', None)
        if 'ingredient_id' not in data:
            data['ingredient_id'] = getattr(self, 'ingredient_id', None)
        return data

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
    distributor_info: Optional[Dict[str, List[Dict]]] = Field(None, description="Distributor information for branded ingredients: { 'ingredient_name': [distributor1, distributor2, ...] }")
    history_id: Optional[str] = Field(None, description="History item ID (MongoDB ObjectId) - returned when history is auto-saved")
    
    # Pydantic v2: Use model_config - exclude_none=True for top-level, but nested models use their own settings
    model_config = ConfigDict(exclude_none=True)
    

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
    selected_method: Optional[str] = Field(None, description="Input method used: 'url' or 'inci'")
    url: Optional[str] = Field(None, description="URL of the product (if input_type was 'url')")


class ProductInput(BaseModel):
    """Schema for a single product input"""
    input: Union[str, List[str]] = Field(..., description="URL (str) or INCI list (List[str])")
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")


class CompareProductsRequest(BaseModel):
    """Request schema for product comparison - supports multiple products"""
    products: List[ProductInput] = Field(..., description="List of products to compare (minimum 2)")


class CompareProductsResponse(BaseModel):
    """Response schema for product comparison - supports multiple products"""
    products: List[ProductComparisonItem] = Field(..., description="List of compared products")
    processing_time: float = Field(..., description="Time taken for comparison (in seconds)")
    id: Optional[str] = Field(None, description="History ID if the comparison was saved")


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
    # Auto-save fields (optional)
    name: Optional[str] = Field(None, description="Name for saving to history (required for auto-save)")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    history_id: Optional[str] = Field(None, description="Existing history ID to update (optional)")


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
    history_id: Optional[str] = Field(None, description="History item ID (MongoDB ObjectId) - returned when history is auto-saved")


class DecodeHistoryItemSummary(BaseModel):
    """Summary schema for decode history item (used in list endpoints - excludes large fields)"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this decode")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: Optional[str] = Field(None, description="Input data preview (truncated for list view)")
    status: str = Field(..., description="Status: 'pending' (analysis in progress), 'analyzed' (completed), or 'failed'")
    notes: Optional[str] = Field(None, description="User notes for this decode")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    # Summary fields from analysis_result (if available)
    has_analysis: bool = Field(False, description="Whether analysis_result exists")
    has_report: bool = Field(False, description="Whether report_data exists")


class DecodeHistoryItem(BaseModel):
    """Full schema for decode history item (used in detail endpoints - includes all fields)"""
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


class MergedAnalyzeAndReportResponse(BaseModel):
    """Merged response schema combining analyze-inci and formulation-report results"""
    # Analysis results from analyze-inci
    analysis: AnalyzeInciResponse = Field(..., description="Ingredient analysis results")
    # Report results from formulation-report
    report: FormulationReportResponse = Field(..., description="Formulation report results")
    # Combined processing time
    total_processing_time: float = Field(..., description="Total time taken for both analysis and report generation (in seconds)")
    # History ID (auto-saved)
    history_id: Optional[str] = Field(None, description="History item ID (MongoDB ObjectId) - returned when history is auto-saved")

class SaveDecodeHistoryRequest(BaseModel):
    """Request schema for saving decode history"""
    name: str = Field(..., description="Name for this decode")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    analysis_result: Dict = Field(..., description="Full analysis result")
    report_data: Optional[str] = Field(None, description="Generated report HTML (optional)")


class GetDecodeHistoryResponse(BaseModel):
    """Response schema for getting decode history (returns summaries only)"""
    items: List[DecodeHistoryItemSummary] = Field(..., description="List of history item summaries")
    total: int = Field(..., description="Total number of items")


class DecodeHistoryDetailResponse(BaseModel):
    """Response schema for getting decode history detail (returns full data)"""
    item: DecodeHistoryItem = Field(..., description="Full history item with all data")


class CompareHistoryItemSummary(BaseModel):
    """Summary schema for compare history item (used in list endpoints - excludes large fields)"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this comparison")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    # Products array - unified format for all comparisons (2-product or multi-product)
    products: List[Dict[str, str]] = Field(..., description="List of products with 'input' and 'input_type' (inputs truncated for preview)")
    status: str = Field(..., description="Status: 'pending' (comparison in progress), 'analyzed' (completed), or 'failed'")
    notes: Optional[str] = Field(None, description="User notes for this comparison")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    # Summary fields
    has_comparison: bool = Field(False, description="Whether comparison_result exists")
    product_count: int = Field(..., description="Number of products being compared")


class CompareHistoryItem(BaseModel):
    """Full schema for compare history item (used in detail endpoints - includes all fields)"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this comparison")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    # Products array - unified format for all comparisons (2-product or multi-product)
    products: List[Dict[str, str]] = Field(..., description="List of products with 'input' and 'input_type' - unified format for all comparisons")
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
    """Response schema for getting compare history (returns summaries only)"""
    items: List[CompareHistoryItemSummary] = Field(..., description="List of history item summaries")
    total: int = Field(..., description="Total number of items")


class CompareHistoryDetailResponse(BaseModel):
    """Response schema for getting compare history detail (returns full data)"""
    item: CompareHistoryItem = Field(..., description="Full history item with all data")


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
    inci: Optional[List[str]] = Field(None, description="INCI ingredient list (array of strings)")
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")


class MarketResearchResponse(BaseModel):
    """Response schema for market research"""
    products: List[MarketResearchProduct] = Field(default_factory=list, description="List of matched products")
    extracted_ingredients: List[str] = Field(default_factory=list, description="List of extracted ingredients from input")
    total_matched: int = Field(0, description="Total number of matched products")
    processing_time: float = Field(0.0, description="Time taken for processing (in seconds)")
    input_type: str = Field(..., description="Type of input processed")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message when no actives found (e.g., 'This formulation contains no defined active ingredient...')")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning for ingredient selection and matching strategy")
    # New fields for enhanced market research
    ai_interpretation: Optional[str] = Field(None, description="AI interpretation of the input URL/INCI explaining category determination")
    primary_category: Optional[str] = Field(None, description="Primary category identified by AI (haircare, skincare, lipcare, bodycare, etc.)")
    subcategory: Optional[str] = Field(None, description="Subcategory/product type identified by AI (serum, cleanser, shampoo, etc.)")
    category_confidence: Optional[str] = Field(None, description="Confidence level of category determination (high, medium, low)")
    market_research_overview: str = Field(..., description="Comprehensive AI-generated overview of market research findings (always provided)")
    # Pagination fields
    page: int = Field(1, description="Current page number")
    page_size: int = Field(10, description="Number of products per page")
    total_pages: int = Field(0, description="Total number of pages")


class MarketResearchProductsResponse(BaseModel):
    """Response schema for market research products endpoint (fast, no overview)"""
    products: List[MarketResearchProduct] = Field(default_factory=list, description="List of matched products")
    extracted_ingredients: List[str] = Field(default_factory=list, description="List of extracted ingredients from input")
    total_matched: int = Field(0, description="Total number of matched products")
    processing_time: float = Field(0.0, description="Time taken for processing (in seconds)")
    input_type: str = Field(..., description="Type of input processed")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message when no actives found")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning for ingredient selection and matching strategy")
    # Category info (always included)
    ai_interpretation: Optional[str] = Field(None, description="AI interpretation of the input URL/INCI explaining category determination")
    primary_category: Optional[str] = Field(None, description="Primary category identified by AI (haircare, skincare, lipcare, bodycare, etc.)")
    subcategory: Optional[str] = Field(None, description="Subcategory/product type identified by AI (serum, cleanser, shampoo, etc.)")
    category_confidence: Optional[str] = Field(None, description="Confidence level of category determination (high, medium, low)")
    # Pagination fields
    page: int = Field(1, description="Current page number")
    page_size: int = Field(10, description="Number of products per page")
    total_pages: int = Field(0, description="Total number of pages")


class MarketResearchOverviewRequest(BaseModel):
    """Request schema for market research overview endpoint"""
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")
    url: Optional[str] = Field(None, description="Product URL (required if input_type is 'url')")
    inci: Optional[List[str]] = Field(None, description="INCI ingredient list (required if input_type is 'inci', array of strings)")
    # Optional: provide category info if already known (to avoid re-analysis)
    primary_category: Optional[str] = Field(None, description="Primary category (if already known)")
    subcategory: Optional[str] = Field(None, description="Subcategory (if already known)")
    category_confidence: Optional[str] = Field(None, description="Category confidence (if already known)")


class MarketResearchOverviewResponse(BaseModel):
    """Response schema for market research overview endpoint"""
    market_research_overview: str = Field(..., description="Comprehensive AI-generated overview of market research findings")
    processing_time: float = Field(0.0, description="Time taken for processing (in seconds)")
    history_id: Optional[str] = Field(None, description="History item ID if the overview was saved to history")


class MarketResearchHistoryItemSummary(BaseModel):
    """Summary schema for market research history item (used in list endpoints - excludes large fields)"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this market research")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: Optional[str] = Field(None, description="Input data preview (truncated for list view)")
    notes: Optional[str] = Field(None, description="User notes for this research")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    # Summary fields from research_result (if available)
    has_research: bool = Field(False, description="Whether research_result exists")
    total_products: Optional[int] = Field(None, description="Total number of products found (if available)")


class MarketResearchHistoryItem(BaseModel):
    """Full schema for market research history item (used in detail endpoints - includes all fields)"""
    id: Optional[str] = Field(None, description="History item ID")
    user_id: Optional[str] = Field(None, description="User ID who created this history")
    name: str = Field(..., description="Name for this market research")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    research_result: Optional[Dict] = Field(None, description="Full market research result")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message (when no actives found)")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning (when no actives found)")
    ai_interpretation: Optional[str] = Field(None, description="AI interpretation of input explaining category determination")
    primary_category: Optional[str] = Field(None, description="Primary category identified by AI (haircare, skincare, lipcare, bodycare, etc.)")
    subcategory: Optional[str] = Field(None, description="Subcategory/product type identified by AI (serum, cleanser, shampoo, etc.)")
    category_confidence: Optional[str] = Field(None, description="Confidence level of category determination (high, medium, low)")
    notes: Optional[str] = Field(None, description="User notes for this research")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    # New fields for enhanced flow
    structured_analysis: Optional[Dict] = Field(None, description="Structured analysis data (ProductStructuredAnalysis as dict)")
    selected_keywords: Optional[Dict] = Field(None, description="Selected keywords (ProductKeywords as dict)")
    available_keywords: Optional[Dict] = Field(None, description="Available keywords (ProductKeywords as dict)")


class SaveMarketResearchHistoryRequest(BaseModel):
    """Request schema for saving market research history"""
    name: str = Field(..., description="Name for this market research")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    input_type: str = Field(..., description="Input type: 'inci' or 'url'")
    input_data: str = Field(..., description="Input data (INCI list or URL)")
    research_result: Optional[Dict] = Field(None, description="Full market research result")
    ai_analysis: Optional[str] = Field(None, description="AI analysis message (when no actives found)")
    ai_reasoning: Optional[str] = Field(None, description="AI reasoning (when no actives found)")
    ai_interpretation: Optional[str] = Field(None, description="AI interpretation of input explaining category determination")
    primary_category: Optional[str] = Field(None, description="Primary category identified by AI (haircare, skincare, lipcare, bodycare, etc.)")
    subcategory: Optional[str] = Field(None, description="Subcategory/product type identified by AI (serum, cleanser, shampoo, etc.)")
    category_confidence: Optional[str] = Field(None, description="Confidence level of category determination (high, medium, low)")
    notes: Optional[str] = Field(None, description="User notes")


class GetMarketResearchHistoryResponse(BaseModel):
    """Response schema for getting market research history (returns summaries only)"""
    items: List[MarketResearchHistoryItemSummary] = Field(..., description="List of history item summaries")
    total: int = Field(..., description="Total number of items")


class MarketResearchHistoryDetailResponse(BaseModel):
    """Response schema for getting market research history detail (returns full data)"""
    item: MarketResearchHistoryItem = Field(..., description="Full history item with all data")


# ============================================================================
# NEW MARKET RESEARCH SCHEMAS (Enhanced Flow)
# ============================================================================

class ActiveIngredient(BaseModel):
    """Schema for active ingredient with percentage"""
    name: str = Field(..., description="Active ingredient name")
    percentage: Optional[str] = Field(None, description="Percentage if available (e.g., '5%', '2-3%')")


class ProductKeywords(BaseModel):
    """Schema for keywords organized by feature category - includes all Formulynx taxonomy fields"""
    # Form-related keywords
    product_formulation: List[str] = Field(default_factory=list, description="Product form keywords - uses Formulynx taxonomy form IDs (e.g., 'serum', 'cream', 'gel')")
    form: Optional[str] = Field(None, description="Primary product form - Formulynx taxonomy form ID (e.g., 'serum', 'cream', 'gel')")
    
    # Price tier
    mrp: List[str] = Field(default_factory=list, description="Price range keywords - uses Formulynx taxonomy price_tier IDs (e.g., 'premium', 'masstige')")
    price_tier: Optional[str] = Field(None, description="Price tier - Formulynx taxonomy price_tier ID: 'mass_market', 'masstige', 'premium', 'prestige'")
    
    # Application/Use case keywords
    application: List[str] = Field(default_factory=list, description="Use case keywords (e.g., 'night_cream', 'brightening', 'sun_protection')")
    
    # Functional benefit keywords
    functionality: List[str] = Field(default_factory=list, description="Functional benefit keywords - uses Formulynx taxonomy benefit IDs (e.g., 'brightening', 'hydrating', 'anti_aging')")
    benefits: List[str] = Field(default_factory=list, description="Formulynx benefit IDs (e.g., 'brightening', 'hydrating', 'anti_aging')")
    
    # Formulynx Taxonomy Fields
    target_area: Optional[str] = Field(None, description="Formulynx target area ID (e.g., 'face', 'hair', 'body', 'lips', 'undereye', 'neck', 'hands', 'feet', 'scalp')")
    product_type_id: Optional[str] = Field(None, description="Formulynx product type ID (e.g., 'cleanser', 'serum', 'moisturizer', 'shampoo')")
    concerns: List[str] = Field(default_factory=list, description="Formulynx concern IDs (e.g., 'acne', 'dark_spots', 'dryness')")
    market_positioning: List[str] = Field(default_factory=list, description="Formulynx market positioning IDs (e.g., 'natural', 'organic', 'clinical', 'korean')")
    
    # Legacy fields (for backward compatibility)
    functional_categories: List[str] = Field(default_factory=list, description="Functional categories as keywords (legacy)")
    main_category: Optional[str] = Field(None, description="Main category: skincare, haircare, lipcare, bodycare (legacy)")
    subcategory: Optional[str] = Field(None, description="Subcategory/product type (legacy)")
    
    @model_serializer
    def serialize_model(self):
        """Custom serializer that excludes empty arrays and None values"""
        # Access fields directly to avoid recursion
        result = {}
        for field_name, field_value in self.__dict__.items():
            # Skip None values
            if field_value is None:
                continue
            # Skip empty lists
            if isinstance(field_value, list) and len(field_value) == 0:
                continue
            result[field_name] = field_value
        return result
    
    def model_dump_exclude_empty(self) -> dict:
        """Return model dict with empty arrays and None values excluded"""
        return self.serialize_model()


class ProductStructuredAnalysis(BaseModel):
    """Schema for structured product analysis - only contains non-keyword data"""
    active_ingredients: List[ActiveIngredient] = Field(default_factory=list, description="Active ingredients with percentages")
    mrp: Optional[float] = Field(None, description="MRP of the product")
    mrp_per_ml: Optional[float] = Field(None, description="MRP per ml")
    mrp_source: Optional[str] = Field(None, description="Source of MRP: 'scraped' or 'ai_estimated'")
    # Note: All taxonomy fields (form, target_area, product_type_id, concerns, benefits, price_tier, market_positioning) 
    # are now in the keywords object, not here


class ProductAnalysisRequest(BaseModel):
    """Request schema for product analysis endpoint"""
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")
    url: Optional[str] = Field(None, description="Product URL (required if input_type is 'url')")
    inci: Optional[List[str]] = Field(None, description="INCI ingredient list (required if input_type is 'inci', array of strings)")
    name: Optional[str] = Field(None, description="Name for history (optional)")
    tag: Optional[str] = Field(None, description="Tag for categorization (optional)")


class ProductAnalysisResponse(BaseModel):
    """Response schema for product analysis endpoint"""
    structured_analysis: ProductStructuredAnalysis = Field(..., description="Structured analysis data")
    available_keywords: ProductKeywords = Field(..., description="All available keywords organized by feature category")
    extracted_ingredients: List[str] = Field(default_factory=list, description="Extracted ingredients list")
    processing_time: float = Field(..., description="Time taken for processing")
    history_id: Optional[str] = Field(None, description="History item ID if saved")


class UpdateKeywordsRequest(BaseModel):
    """Request schema for updating selected keywords"""
    history_id: str = Field(..., description="History item ID")
    selected_keywords: ProductKeywords = Field(..., description="Selected keywords organized by feature category")


class UpdateKeywordsResponse(BaseModel):
    """Response schema for updating keywords"""
    success: bool = Field(..., description="Success status")
    message: str = Field(..., description="Response message")
    selected_keywords: ProductKeywords = Field(..., description="Updated selected keywords")
    history_id: str = Field(..., description="History item ID")


class MarketResearchWithKeywordsRequest(BaseModel):
    """Request schema for market research with keywords"""
    input_type: str = Field(..., description="Type of input: 'url' or 'inci'")
    url: Optional[str] = Field(None, description="Product URL (required if input_type is 'url')")
    inci: Optional[List[str]] = Field(None, description="INCI ingredient list (required if input_type is 'inci', array of strings)")
    selected_keywords: Optional[ProductKeywords] = Field(None, description="Selected keywords for filtering")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters (price_range, brand, etc.)")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(10, ge=1, le=100, description="Items per page")
    sort_by: str = Field("match_score", description="Sort by: 'price_low', 'price_high', 'match_score'")
    name: Optional[str] = Field(None, description="Name for auto-saving to history")
    tag: Optional[str] = Field(None, description="Tag for categorization")


class MarketResearchPaginatedResponse(BaseModel):
    """Response schema for paginated market research"""
    products: List[MarketResearchProduct] = Field(default_factory=list, description="List of matched products")
    total_matched: int = Field(0, description="Total number of matched products")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(10, description="Items per page")
    total_pages: int = Field(0, description="Total number of pages")
    sort_by: str = Field(..., description="Current sort method")
    filters_applied: Dict[str, Any] = Field(default_factory=dict, description="Applied filters")
    processing_time: float = Field(..., description="Time taken for processing")
    extracted_ingredients: List[str] = Field(default_factory=list, description="Extracted ingredients list")
    input_type: str = Field(..., description="Type of input processed")
    ai_interpretation: Optional[str] = Field(None, description="AI interpretation")
    primary_category: Optional[str] = Field(None, description="Primary category")
    subcategory: Optional[str] = Field(None, description="Subcategory")
    category_confidence: Optional[str] = Field(None, description="Category confidence")
    history_id: Optional[str] = Field(None, description="History item ID if saved")


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
    # Auto-save fields (optional)
    name: Optional[str] = Field(None, description="Name for saving to history (required for auto-save)")
    tag: Optional[str] = Field(None, description="Tag for categorization")
    notes: Optional[str] = Field(None, description="User notes for this wish")
    history_id: Optional[str] = Field(None, description="Existing history ID to update (optional)")


class MakeWishResponse(BaseModel):
    """Response schema for Make a Wish formula generation"""
    wish_data: Dict[str, Any]
    ingredient_selection: Dict[str, Any] = Field(..., description="Stage 1: Ingredient selection results")
    optimized_formula: Dict[str, Any] = Field(..., description="Stage 2: Optimized formula with percentages")
    manufacturing: Dict[str, Any] = Field(..., description="Stage 3: Manufacturing process instructions")
    cost_analysis: Dict[str, Any] = Field(..., description="Stage 4: Cost analysis and pricing recommendations")
    compliance: Dict[str, Any] = Field(..., description="Stage 5: Regulatory compliance check")
    metadata: Dict[str, Any] = Field(..., description="Metadata about the generation process")
    history_id: Optional[str] = Field(None, description="History item ID (MongoDB ObjectId) - returned when history is auto-saved")


# ============================================================================
# FORMULYNX TAXONOMY SCHEMAS
# ============================================================================

class TaxonomyForm(BaseModel):
    """Schema for a form in the taxonomy"""
    id: str = Field(..., description="Form ID (e.g., 'serum', 'cream', 'gel')")
    label: str = Field(..., description="Form label")
    icon: Optional[str] = Field(None, description="Form icon")
    description: Optional[str] = Field(None, description="Form description")
    texture_feel: Optional[str] = Field(None, description="Texture feel category")


class TaxonomyProductType(BaseModel):
    """Schema for a product type in the taxonomy"""
    id: str = Field(..., description="Product type ID")
    label: str = Field(..., description="Product type label")
    description: Optional[str] = Field(None, description="Product type description")
    forms: List[str] = Field(default_factory=list, description="Valid form IDs for this product type")
    sub_types: List[str] = Field(default_factory=list, description="Sub-type IDs")


class TaxonomyConcern(BaseModel):
    """Schema for a concern in the taxonomy"""
    id: str = Field(..., description="Concern ID")
    label: str = Field(..., description="Concern label")
    parent: Optional[str] = Field(None, description="Parent concern category")


class TaxonomyBenefit(BaseModel):
    """Schema for a benefit in the taxonomy"""
    id: str = Field(..., description="Benefit ID")
    label: str = Field(..., description="Benefit label")
    description: Optional[str] = Field(None, description="Benefit description")


class TaxonomyTargetArea(BaseModel):
    """Schema for a target area in the taxonomy"""
    id: str = Field(..., description="Target area ID")
    icon: Optional[str] = Field(None, description="Target area icon")
    label: str = Field(..., description="Target area label")
    category: Optional[str] = Field(None, description="Category (skin, hair, etc.)")
    sub_areas: Optional[List[str]] = Field(None, description="Sub-area IDs")
    product_types: List[TaxonomyProductType] = Field(default_factory=list, description="Product types for this target area")
    concerns: List[TaxonomyConcern] = Field(default_factory=list, description="Concerns for this target area")
    benefits: List[TaxonomyBenefit] = Field(default_factory=list, description="Benefits for this target area")


class TaxonomyPriceTier(BaseModel):
    """Schema for a price tier in the taxonomy"""
    id: str = Field(..., description="Price tier ID")
    label: str = Field(..., description="Price tier label")
    range: str = Field(..., description="Price range")
    icon: Optional[str] = Field(None, description="Price tier icon")
    color: Optional[str] = Field(None, description="Price tier color")


class TaxonomyMarketPositioning(BaseModel):
    """Schema for market positioning in the taxonomy"""
    id: str = Field(..., description="Market positioning ID")
    label: str = Field(..., description="Market positioning label")


class TaxonomyResponse(BaseModel):
    """Response schema for complete taxonomy"""
    forms: Dict[str, TaxonomyForm] = Field(..., description="All available forms")
    target_areas: Dict[str, TaxonomyTargetArea] = Field(..., description="All target areas with their product types, concerns, and benefits")
    price_tiers: List[TaxonomyPriceTier] = Field(..., description="All price tiers")
    market_positioning: List[TaxonomyMarketPositioning] = Field(..., description="All market positioning options")


class TaxonomyTargetAreaResponse(BaseModel):
    """Response schema for a specific target area"""
    target_area: TaxonomyTargetArea = Field(..., description="Target area details")


class TaxonomyFormsResponse(BaseModel):
    """Response schema for all forms"""
    forms: Dict[str, TaxonomyForm] = Field(..., description="All available forms")


class TaxonomyPriceTiersResponse(BaseModel):
    """Response schema for price tiers"""
    price_tiers: List[TaxonomyPriceTier] = Field(..., description="All price tiers")


class TaxonomyMarketPositioningResponse(BaseModel):
    """Response schema for market positioning"""
    market_positioning: List[TaxonomyMarketPositioning] = Field(..., description="All market positioning options")


# ============================================================================
# PLATFORM FETCHER SCHEMAS
# ============================================================================

class FetchPlatformsRequest(BaseModel):
    """Request schema for fetching product platforms"""
    product_name: str = Field(..., description="Name of the product to search")


class PlatformInfo(BaseModel):
    """Schema for a single platform result"""
    platform: str = Field(..., description="Normalized platform name (e.g., 'amazon', 'nykaa')")
    platform_display_name: str = Field(..., description="Human-readable platform name (e.g., 'Amazon', 'Nykaa')")
    url: str = Field(..., description="Product URL on the platform")
    logo_url: Optional[str] = Field(None, description="S3 URL of platform logo")
    title: str = Field(..., description="Product title from search result")
    price: Optional[str] = Field(None, description="Product price if available")
    position: int = Field(..., description="Original search position (lower is better)")


class FetchPlatformsResponse(BaseModel):
    """Response schema for fetching product platforms"""
    platforms: List[PlatformInfo] = Field(..., description="List of platform links for the product")
    total_platforms: int = Field(..., description="Total number of unique platforms found")
    product_name: str = Field(..., description="The product name that was searched")