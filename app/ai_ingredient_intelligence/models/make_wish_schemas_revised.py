"""
Revised Make A Wish Schemas (January 2025)
==========================================

This module contains all the new Pydantic schemas for the revised Make A Wish flow.
The new flow introduces natural language parsing, complexity selection, ingredient alternatives,
formula editing, quote requests, and commercialization features.
"""

from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ============================================================================
# STAGE 1: PARSE WISH SCHEMAS
# ============================================================================

class ParseWishRequest(BaseModel):
    """Request schema for parsing natural language wish"""
    wish_text: str = Field(..., min_length=30, description="Natural language wish description (minimum 30 characters)")


class ProductTypeInfo(BaseModel):
    """Detected product type information"""
    id: str = Field(..., description="Product type ID (e.g., 'serum', 'moisturizer')")
    name: str = Field(..., description="Display name for product type")
    emoji: str = Field(..., description="Emoji representing product type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")


class DetectedIngredient(BaseModel):
    """Ingredient detected in natural language wish"""
    name: str = Field(..., description="Ingredient name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    has_alternatives: bool = Field(..., description="Whether alternatives exist in database")


class TextureInfo(BaseModel):
    """Auto-detected texture information"""
    id: str = Field(..., description="Texture ID (e.g., 'watery', 'gel', 'cream')")
    label: str = Field(..., description="Display label for texture")
    auto_selected: bool = Field(True, description="Always True for auto-detection")


class ClarificationQuestion(BaseModel):
    """Question to clarify ambiguous wish details"""
    id: str = Field(..., description="Question ID")
    question: str = Field(..., description="Question text")
    options: List[Dict[str, str]] = Field(..., description="Available options")
    required: bool = Field(..., description="Whether this question is required")
    input_type: Optional[Dict[str, Any]] = Field(None, description="Raw input from AI")


class CompatibilityIssue(BaseModel):
    """Ingredient compatibility issue detected"""
    severity: str = Field(..., description="Severity: 'critical' or 'warning'")
    title: Optional[str] = Field(None, description="Issue title")
    problem: Optional[str] = Field(None, description="User-friendly problem description")
    solution: Optional[str] = Field(None, description="Suggested solution")
    ingredients_involved: Optional[List[str]] = Field(None, description="Ingredients involved in the issue")
    input_type: Optional[Dict[str, Any]] = Field(None, description="Raw input from AI")


class ParsedWishData(BaseModel):
    """Parsed data from natural language wish"""
    category: str = Field(..., description="Auto-detected category: 'skincare' or 'haircare'")
    product_type: ProductTypeInfo = Field(..., description="Detected product type")
    detected_ingredients: List[DetectedIngredient] = Field(..., description="Ingredients detected in wish")
    detected_benefits: List[str] = Field(..., description="Benefits detected from wish")
    detected_exclusions: List[str] = Field(..., description="Exclusions detected from wish")
    detected_skin_types: List[str] = Field(default_factory=list, description="Skin types mentioned")
    detected_hair_concerns: List[str] = Field(default_factory=list, description="Hair concerns mentioned")
    auto_texture: TextureInfo = Field(..., description="Auto-detected texture")
    needs_clarification: List[Dict[str, Any]] = Field(default_factory=list, description="Simple clarification questions from AI")


class ParseWishResponse(BaseModel):
    """Response schema for parsing natural language wish"""
    success: bool = Field(..., description="Whether parsing was successful")
    parsed_data: ParsedWishData = Field(..., description="Parsed wish data")
    compatibility_issues: List[CompatibilityIssue] = Field(default_factory=list, description="Any compatibility issues detected")


# ============================================================================
# STAGE 2: REVISED GENERATE SCHEMAS
# ============================================================================

class MakeWishRequestRevised(BaseModel):
    """Revised request schema for Make a Wish formula generation"""
    # Core inputs
    wish_text: str = Field(..., description="Original natural language wish")
    parsed_data: ParsedWishData = Field(..., description="Parsed wish data from /parse-wish endpoint")
    
    # New: Complexity selection
    complexity: str = Field(..., description="Formula complexity: 'minimalist', 'classic', or 'luxe'")
    
    # Optional overrides from clarification questions
    product_type_override: Optional[str] = Field(None, description="Override product type if user selected different")
    skin_type_override: Optional[List[str]] = Field(None, description="Override skin types if user selected")
    
    # Existing fields (kept)
    claims: Optional[List[str]] = Field(default_factory=list, description="Product claims to support")
    additional_notes: Optional[str] = Field(None, description="Additional notes or requirements")
    name: str = Field(..., description="Required name for auto-save")
    tag: Optional[str] = Field(None, description="Optional tag for categorization")
    notes: Optional[str] = Field(None, description="Optional user notes")
    history_id: Optional[str] = Field(None, description="Existing history ID to update")


class ComplexityInfo(BaseModel):
    """Information about formula complexity"""
    id: str = Field(..., description="Complexity ID")
    name: str = Field(..., description="Complexity name")
    emoji: str = Field(..., description="Emoji representing complexity")
    description: str = Field(..., description="Description of this complexity level")
    highlights: List[str] = Field(..., description="Key highlights of this complexity")
    marketing_angle: str = Field(..., description="Marketing angle for this complexity")


class FormulaIngredientRevised(BaseModel):
    """Revised schema for formula ingredient"""
    id: str = Field(..., description="Ingredient ID")
    inci_name: str = Field(..., description="INCI name")
    display_name: str = Field(..., description="Display name")
    emoji: str = Field(..., description="Emoji representing ingredient")
    percentage: str = Field(..., description="Percentage (e.g., '5%' or 'q.s.')")
    percentage_range: Optional[str] = Field(None, description="Percentage range (e.g., '3-5%')")
    phase: str = Field(..., description="Phase assignment")
    purpose: str = Field(..., description="Purpose in formula")
    is_hero: bool = Field(..., description="Whether this is a hero ingredient")
    is_base: bool = Field(..., description="Whether this is a base ingredient (cannot be removed)")
    has_alternatives: bool = Field(..., description="Whether alternatives exist")
    complexity_note: Optional[str] = Field(None, description="Why chosen for this complexity")


class FormulaPhase(BaseModel):
    """Formula phase with ingredients"""
    name: str = Field(..., description="Phase name")
    order: int = Field(..., description="Phase order")
    ingredients: List[FormulaIngredientRevised] = Field(..., description="Ingredients in this phase")


class HeroIngredient(BaseModel):
    """Hero ingredient information"""
    id: str = Field(..., description="Hero ingredient ID")
    name: str = Field(..., description="Ingredient name")
    emoji: str = Field(..., description="Ingredient emoji")
    percentage: str = Field(..., description="Percentage used")
    why_included: str = Field(..., description="Why this ingredient was included")
    complexity_variant: str = Field(..., description="Variant used for this complexity")
    alternatives_available: int = Field(..., description="Number of alternatives available")


class FormulaOutput(BaseModel):
    """Complete formula output"""
    name: str = Field(..., description="Formula name")
    complexity: str = Field(..., description="Formula complexity")
    complexity_info: ComplexityInfo = Field(..., description="Complexity information")
    product_type: ProductTypeInfo = Field(..., description="Product type")
    texture: TextureInfo = Field(..., description="Texture information")
    
    phases: List[FormulaPhase] = Field(..., description="Formula phases")
    hero_ingredients: List[HeroIngredient] = Field(..., description="Hero ingredients")
    
    total_ingredients: int = Field(..., description="Total number of ingredients")
    total_hero_actives: int = Field(..., description="Number of hero active ingredients")
    
    available_claims: List[str] = Field(..., description="Available claims")
    exclusions_met: List[str] = Field(..., description="Exclusions that were met")


class WhyIngredient(BaseModel):
    """Explanation for why an ingredient was chosen"""
    ingredient_name: str = Field(..., description="Ingredient name")
    emoji: str = Field(..., description="Ingredient emoji")
    explanation: str = Field(..., description="User-friendly explanation")
    complexity_reason: Optional[str] = Field(None, description="Why this variant for this complexity")


class Challenge(BaseModel):
    """Potential challenge with the formula"""
    title: str = Field(..., description="Challenge title")
    emoji: str = Field(..., description="Emoji representing challenge")
    description: str = Field(..., description="What to expect")
    tip: str = Field(..., description="How to handle it")
    severity: str = Field(..., description="Severity: 'info' or 'attention'")


class MarketingTip(BaseModel):
    """Marketing tip for the formula"""
    title: str = Field(..., description="Tip title")
    emoji: str = Field(..., description="Emoji representing tip")
    content: str = Field(..., description="The actual tip content")
    category: str = Field(..., description="Tip category: 'positioning', 'pricing', or 'targeting'")


class FAQItem(BaseModel):
    """Frequently asked question"""
    question: str = Field(..., description="Question")
    answer: str = Field(..., description="Answer")


class FormulaInsights(BaseModel):
    """Insights about the formula"""
    why_these_ingredients: List[WhyIngredient] = Field(..., description="Why each ingredient was chosen")
    challenges: List[Challenge] = Field(..., description="Potential challenges")
    marketing_tips: List[MarketingTip] = Field(..., description="Marketing tips")
    faq: List[FAQItem] = Field(..., description="Frequently asked questions")


class MakeWishResponseRevised(BaseModel):
    """Revised response schema for Make a Wish formula generation"""
    success: bool = Field(..., description="Whether generation was successful")
    formula_id: str = Field(..., description="Unique ID for this formula")
    history_id: str = Field(..., description="History tracking ID")
    
    # Formula core
    formula: FormulaOutput = Field(..., description="Complete formula")
    
    # New: Insights
    insights: FormulaInsights = Field(..., description="Formula insights")
    
    # Existing (kept)
    manufacturing: Dict[str, Any] = Field(..., description="Manufacturing process")
    compliance: Dict[str, Any] = Field(..., description="Compliance information")
    
    # Note: cost_analysis moved to separate /request-quote endpoint


# ============================================================================
# STAGE 3: GET ALTERNATIVES SCHEMAS
# ============================================================================

class GetAlternativesRequest(BaseModel):
    """Request schema for getting ingredient alternatives"""
    ingredient_name: str = Field(..., description="Ingredient name to get alternatives for")
    current_variant: Optional[str] = Field(None, description="Current variant being used")
    complexity: str = Field(..., description="Current formula complexity")
    product_type: str = Field(..., description="Product type for context")


class AlternativeOption(BaseModel):
    """Alternative ingredient option"""
    name: str = Field(..., description="Alternative name")
    inci_name: str = Field(..., description="INCI name")
    emoji: str = Field(..., description="Emoji")
    description: str = Field(..., description="Description")
    benefit_tag: str = Field(..., description="Benefit tag")
    suggested_percentage: str = Field(..., description="Suggested percentage")
    cost_impact: str = Field(..., description="Cost impact: 'higher', 'similar', or 'lower'")
    complexity_fit: List[str] = Field(..., description="Which complexities this fits")
    considerations: Optional[str] = Field(None, description="Usage considerations")


class GetAlternativesResponse(BaseModel):
    """Response schema for ingredient alternatives"""
    success: bool = Field(..., description="Whether request was successful")
    ingredient_name: str = Field(..., description="Ingredient name")
    current: AlternativeOption = Field(..., description="Current variant")
    alternatives: List[AlternativeOption] = Field(..., description="Available alternatives")


# ============================================================================
# STAGE 4: EDIT FORMULA SCHEMAS
# ============================================================================

class NewIngredientInput(BaseModel):
    """Input for adding new ingredient"""
    name: str = Field(..., description="Ingredient name")
    suggested_percentage: Optional[str] = Field(None, description="Suggested percentage")


class FormulaOperation(BaseModel):
    """Operation to perform on formula"""
    type: str = Field(..., description="Operation type: 'add', 'remove', 'swap', or 'adjust_percentage'")
    ingredient_id: Optional[str] = Field(None, description="Ingredient ID for remove/swap/adjust")
    new_ingredient: Optional[NewIngredientInput] = Field(None, description="New ingredient for add/swap")
    new_percentage: Optional[str] = Field(None, description="New percentage for adjust_percentage")


class EditFormulaRequest(BaseModel):
    """Request schema for editing formula"""
    formula_id: str = Field(..., description="Formula ID to edit")
    history_id: str = Field(..., description="History ID")
    operations: List[FormulaOperation] = Field(..., description="Operations to perform")


class ValidationError(BaseModel):
    """Validation error for formula edit"""
    operation_index: int = Field(..., description="Index of operation that failed")
    message: str = Field(..., description="Error message")


class ValidationWarning(BaseModel):
    """Validation warning for formula edit"""
    operation_index: int = Field(..., description="Index of operation with warning")
    message: str = Field(..., description="Warning message")


class EditValidation(BaseModel):
    """Validation results for formula edit"""
    is_valid: bool = Field(..., description="Whether edit is valid")
    errors: List[ValidationError] = Field(default_factory=list, description="Blocking errors")
    warnings: List[ValidationWarning] = Field(default_factory=list, description="Non-blocking warnings")


class EditFormulaResponse(BaseModel):
    """Response schema for formula edit"""
    success: bool = Field(..., description="Whether edit was successful")
    formula_id: str = Field(..., description="Formula ID")
    validation: EditValidation = Field(..., description="Validation results")
    updated_formula: Optional[FormulaOutput] = Field(None, description="Updated formula if valid")
    warnings: List[str] = Field(default_factory=list, description="Additional warnings")


# ============================================================================
# STAGE 5: REQUEST QUOTE SCHEMAS
# ============================================================================

class RequestQuoteRequest(BaseModel):
    """Request schema for manufacturing quote"""
    formula_id: str = Field(..., description="Formula ID")
    history_id: str = Field(..., description="History ID")
    quantity_options: List[int] = Field(..., description="Quantity options to quote")
    include_packaging: bool = Field(..., description="Include packaging costs")
    packaging_type: Optional[str] = Field(None, description="Packaging type: 'basic', 'premium', or 'custom'")


class QuantityQuote(BaseModel):
    """Quote for specific quantity"""
    quantity: int = Field(..., description="Quantity")
    
    # Per-unit costs (internal)
    raw_material_cost_per_unit: float = Field(..., description="Raw material cost per unit")
    packaging_cost_per_unit: float = Field(..., description="Packaging cost per unit")
    total_cost_per_unit: float = Field(..., description="Total cost per unit")
    
    # What user sees
    suggested_mrp: str = Field(..., description="Suggested MRP")
    suggested_mrp_range: str = Field(..., description="Suggested MRP range")
    estimated_margin: str = Field(..., description="Estimated margin")
    
    # Total investment
    total_investment: str = Field(..., description="Total investment amount")
    total_investment_breakdown: Dict[str, Any] = Field(..., description="Investment breakdown")


class PricingGuidance(BaseModel):
    """Pricing guidance for the formula"""
    positioning: str = Field(..., description="Product positioning")
    competitor_range: str = Field(..., description="Competitor price range")
    recommended_mrp: str = Field(..., description="Recommended MRP")
    margin_explanation: str = Field(..., description="Margin explanation")


class RequestQuoteResponse(BaseModel):
    """Response schema for manufacturing quote"""
    success: bool = Field(..., description="Whether quote was generated")
    formula_id: str = Field(..., description="Formula ID")
    quote_id: str = Field(..., description="Quote ID for reference")
    generated_at: datetime = Field(..., description="When quote was generated")
    valid_until: datetime = Field(..., description="Quote expiry date")
    
    quotes: List[QuantityQuote] = Field(..., description="Quotes for different quantities")
    pricing_guidance: PricingGuidance = Field(..., description="Pricing guidance")


# ============================================================================
# STAGE 6: GET THIS MADE SCHEMAS
# ============================================================================

class CommercializationProfile(BaseModel):
    """User profile for commercialization"""
    name: str = Field(..., description="User name")
    phone: str = Field(..., description="WhatsApp phone number")
    city: str = Field(..., description="City")
    
    experience_level: str = Field(..., description="Experience: 'dreaming', 'researching', 'ready', or 'existing'")
    timeline: str = Field(..., description="Timeline: 'asap', '3months', '6months', or 'exploring'")
    
    # Optional
    brand_name: Optional[str] = Field(None, description="Brand name if they have one")
    quantity_interest: Optional[str] = Field(None, description="Quantity interest")
    additional_notes: Optional[str] = Field(None, description="Additional notes")


class GetThisMadeRequest(BaseModel):
    """Request schema for commercialization"""
    formula_id: str = Field(..., description="Formula ID")
    history_id: str = Field(..., description="History ID")
    user_profile: CommercializationProfile = Field(..., description="User commercialization profile")
    formula_snapshot: Dict[str, Any] = Field(..., description="Current formula state")


class NextStep(BaseModel):
    """Next step in commercialization process"""
    order: int = Field(..., description="Step order")
    emoji: str = Field(..., description="Step emoji")
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="Step description")
    estimated_timeline: Optional[str] = Field(None, description="Estimated timeline")


class CommitmentInfo(BaseModel):
    """Commitment information for commercialization"""
    amount: int = Field(..., description="Commitment amount")
    currency: str = Field(..., description="Currency")
    refundable: bool = Field(..., description="Whether refundable")
    refund_policy: str = Field(..., description="Refund policy")
    platform_charges: str = Field(..., description="Platform charges")
    purpose: str = Field(..., description="Purpose of commitment")


class GetThisMadeResponse(BaseModel):
    """Response schema for commercialization request"""
    success: bool = Field(..., description="Whether request was submitted")
    queue_number: str = Field(..., description="Queue number assigned")
    queue_position: Optional[int] = Field(None, description="Position in queue")
    request_id: str = Field(..., description="Request tracking ID")
    submitted_at: datetime = Field(..., description="Submission timestamp")
    next_steps: List[NextStep] = Field(..., description="Next steps")
    commitment_info: CommitmentInfo = Field(..., description="Commitment information")
