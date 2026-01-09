"""
Pydantic schemas for Inspiration Boards API
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId


# ============================================================================
# HELPER MODELS
# ============================================================================

class ProductHistoryLink(BaseModel):
    """Link to feature history data"""
    feature_type: str = Field(..., description="Feature type: market_research, make_wish, formulation_decode, product_comparison")
    history_id: str = Field(..., description="History ID from the feature's collection")
    source_description: str = Field(..., description="Brief description of the source data")


class ProductTypeInfo(BaseModel):
    """Product type configuration"""
    type_name: str = Field(..., description="Product type: researched, decoded, compared, formulation")
    emoji: str = Field(..., description="Default emoji for this product type")
    label: str = Field(..., description="Display label for this product type")
    has_real_image: bool = Field(..., description="Whether this product type has real images")


class IngredientDetail(BaseModel):
    """Ingredient detail in decoded data"""
    name: str
    inci: str
    phase: str  # 'water', 'oil', 'active', 'preservative', 'other'
    concentration: float  # percentage
    cost: float
    function: str


class ComplianceDetail(BaseModel):
    """Compliance status for a region"""
    status: str  # 'compliant', 'warning', 'non-compliant'
    notes: str


class ComplianceInfo(BaseModel):
    """Compliance information"""
    bis: ComplianceDetail
    eu: ComplianceDetail
    fda: ComplianceDetail


class MarketPosition(BaseModel):
    """Market positioning information"""
    price_segment: str
    target_audience: str
    usp: str
    competitors: List[str]


class DecodedData(BaseModel):
    """Decoded product data"""
    ingredient_count: int
    hero_ingredients: List[str]
    estimated_cost: float  # per 100g
    ph_range: str
    formulation_type: str
    manufacturing_complexity: str
    shelf_life: str
    ingredients: List[IngredientDetail]
    compliance: ComplianceInfo
    market_position: MarketPosition


# ============================================================================
# BOARD SCHEMAS
# ============================================================================

class CreateBoardRequest(BaseModel):
    """Request to create a new board"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    icon: str = Field(default="🎯", max_length=10)
    color: str = Field(default="rose", max_length=20)
    template: Optional[str] = Field(None, description="Template name for quick start")


class UpdateBoardRequest(BaseModel):
    """Request to update a board"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, max_length=20)


class BoardResponse(BaseModel):
    """Board response model"""
    board_id: str
    user_id: str
    name: str
    description: Optional[str]
    icon: str
    color: str
    created_at: datetime
    updated_at: datetime
    product_count: int = 0
    decoded_count: int = 0

    class Config:
        from_attributes = True


class BoardListResponse(BaseModel):
    """List of boards response"""
    boards: List[BoardResponse]
    total: int
    limit: int
    offset: int


class BoardDetailResponse(BoardResponse):
    """Board detail with product summaries (excludes large decoded_data)"""
    products: List["ProductSummary"] = Field(default_factory=list, description="Product summaries (use /products/{product_id} for full data)")
    stats: Optional[Dict[str, Any]] = None


# ============================================================================
# PRODUCT SCHEMAS
# ============================================================================

class AddProductFromURLRequest(BaseModel):
    """Request to add product from URL - requires pre-fetched data from /fetch-product endpoint"""
    url: str = Field(..., description="Product URL from e-commerce site")
    notes: Optional[str] = Field(None, max_length=1000)
    tags: Optional[List[str]] = Field(default_factory=list)
    # REQUIRED: Pre-fetched product data from /fetch-product endpoint (no scraping in this endpoint)
    fetched_data: Dict[str, Any] = Field(..., description="Pre-fetched product data from /fetch-product endpoint. This endpoint does NOT scrape - you must fetch first.")


class AddProductManualRequest(BaseModel):
    """Request to add product manually"""
    name: str = Field(..., min_length=1, max_length=200)
    brand: str = Field(..., min_length=1, max_length=100)
    url: Optional[str] = None
    platform: str = Field(default="other", max_length=50)
    price: float = Field(..., gt=0)
    size: float = Field(..., gt=0)
    unit: str = Field(default="ml", max_length=10)
    category: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=1000)
    tags: Optional[List[str]] = Field(default_factory=list)
    image: Optional[str] = Field(None, max_length=200)


class UpdateProductRequest(BaseModel):
    """Request to update product"""
    notes: Optional[str] = Field(None, max_length=1000)
    tags: Optional[List[str]] = None
    my_rating: Optional[int] = Field(None, ge=1, le=5)


class ProductSummary(BaseModel):
    """Product summary (used in board detail - excludes large decoded_data)"""
    product_id: str
    board_id: str
    user_id: str
    name: str
    brand: str
    url: Optional[str]
    platform: str
    image: str
    price: float
    size: float
    unit: str
    price_per_ml: float
    category: Optional[str]
    date_added: datetime
    notes: Optional[str]
    tags: List[str]
    my_rating: Optional[int]
    decoded: bool
    created_at: datetime
    updated_at: datetime
    # Summary fields from decoded_data (if available)
    has_decoded_data: bool = Field(False, description="Whether decoded_data exists")
    hero_ingredients_preview: Optional[List[str]] = Field(None, description="First 3 hero ingredients if decoded")
    estimated_cost: Optional[float] = Field(None, description="Estimated cost if decoded")
    # New fields for feature integration
    product_type: Optional[str] = Field(None, description="Product type: researched, decoded, compared, formulation")
    history_link: Optional[ProductHistoryLink] = Field(None, description="Link to feature history data")
    # Platform links fetched from Serper API
    platforms: Optional[List[Dict[str, Any]]] = Field(None, description="Platform links fetched from Serper API (fetched in background)")
    platforms_fetched_at: Optional[str] = Field(None, description="Timestamp when platforms were fetched")

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    """Full product response model (includes all decoded_data)"""
    product_id: str
    board_id: str
    user_id: str
    name: str
    brand: str
    url: Optional[str]
    platform: str
    image: str
    price: float
    size: float
    unit: str
    price_per_ml: float
    category: Optional[str]
    date_added: datetime
    notes: Optional[str]
    tags: List[str]
    my_rating: Optional[int]
    decoded: bool
    decoded_data: Optional[DecodedData]
    created_at: datetime
    updated_at: datetime
    # New fields for feature integration
    product_type: Optional[str] = Field(None, description="Product type: researched, decoded, compared, formulation")
    history_link: Optional[ProductHistoryLink] = Field(None, description="Link to feature history data")
    feature_data: Optional[Dict[str, Any]] = Field(None, description="Full feature data fetched on demand")
    # Platform links fetched from Serper API
    platforms: Optional[List[Dict[str, Any]]] = Field(None, description="Platform links fetched from Serper API (fetched in background)")
    platforms_fetched_at: Optional[str] = Field(None, description="Timestamp when platforms were fetched")

    class Config:
        from_attributes = True


# ============================================================================
# URL FETCHING SCHEMAS
# ============================================================================

class FetchProductRequest(BaseModel):
    """Request to fetch product from URL"""
    url: str = Field(..., description="E-commerce product URL")


class FetchProductResponse(BaseModel):
    """Response from URL fetching"""
    name: Optional[str]
    brand: Optional[str]
    url: str
    platform: str
    price: Optional[float]
    size: Optional[float]
    unit: Optional[str]
    category: Optional[str]
    image: Optional[str]
    ingredients: Optional[List[str]] = Field(default_factory=list)
    benefits: Optional[List[str]] = Field(default_factory=list)
    tags: Optional[List[str]] = Field(default_factory=list)
    target_audience: Optional[List[str]] = Field(default_factory=list)
    success: bool
    message: Optional[str] = None


# ============================================================================
# COMPETITOR ANALYSIS SCHEMAS
# ============================================================================

class AnalysisRequest(BaseModel):
    """Request for competitor analysis"""
    product_ids: List[str] = Field(..., min_items=2, description="At least 2 product IDs required")
    analysis_type: str = Field(default="overview", description="'overview' or 'ingredients'")


class SideBySideRow(BaseModel):
    """Row in side-by-side comparison"""
    metric: str
    values: Dict[str, Any]  # product_id -> value


class PriceComparisonItem(BaseModel):
    """Item in price comparison"""
    product_id: str
    product_name: str
    brand: str
    price: float
    price_per_ml: float
    width_percentage: float  # For visualization


class CommonIngredientsAnalysis(BaseModel):
    """Common ingredients analysis"""
    common_ingredients: List[str]
    common_count: int
    total_unique_ingredients: int


class UniqueIngredientItem(BaseModel):
    """Unique ingredient for a product"""
    product_id: str
    product_name: str
    brand: str
    unique_ingredients: List[str]


class IngredientsAnalysis(BaseModel):
    """Ingredients analysis section"""
    common_ingredients: CommonIngredientsAnalysis
    unique_ingredients: List[UniqueIngredientItem]
    hero_ingredients_comparison: Dict[str, List[str]]  # product_id -> hero ingredients


class OverviewAnalysis(BaseModel):
    """Overview analysis section"""
    products_analyzed: int
    price_range: Dict[str, float]  # min, max, avg
    cost_range: Dict[str, float]  # min, max, avg
    common_ingredients_count: int
    total_unique_ingredients: int
    side_by_side: List[SideBySideRow]
    price_comparison: List[PriceComparisonItem]


class AnalysisResponse(BaseModel):
    """Competitor analysis response"""
    analysis_type: str
    products_analyzed: int
    overview: Optional[OverviewAnalysis] = None
    ingredients: Optional[IngredientsAnalysis] = None


# ============================================================================
# EXPORT SCHEMAS
# ============================================================================

class ExportItemRequest(BaseModel):
    """Single export item request"""
    feature_type: str = Field(..., description="Feature type: market_research, make_wish, formulation_decode, product_comparison")
    history_ids: List[str] = Field(..., description="History IDs to export from this feature")


class ExportToBoardRequest(BaseModel):
    """Request to export multiple items from multiple features to a board"""
    board_id: str = Field(..., description="Target board ID")
    exports: List[ExportItemRequest] = Field(..., description="List of export items from different features")


class ExportToBoardResponse(BaseModel):
    """Response from export operation"""
    success: bool
    exported_count: int
    skipped_count: int
    duplicates_count: int
    errors: List[str] = Field(default_factory=list)
    exported_products: List[ProductSummary] = Field(default_factory=list)


# ============================================================================
# TAG SCHEMAS
# ============================================================================

class TagCategory(BaseModel):
    """Tag category"""
    category_name: str
    description: str
    tags: List[Dict[str, str]]  # List of {tag: description}


class TagsResponse(BaseModel):
    """All available tags organized by category"""
    categories: List[TagCategory]

