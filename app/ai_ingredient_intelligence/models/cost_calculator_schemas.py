"""
Cost Calculator API Schemas
============================

Schemas for the cost calculator backend API.
Handles batch settings, phases, ingredients, and cost calculations.
"""

from typing import List, Optional, Dict, Union, Any
from pydantic import BaseModel, Field


class BatchSettings(BaseModel):
    """Batch settings for cost calculation"""
    batch_size: int = Field(..., description="Number of units in batch", gt=0)
    unit_size: float = Field(..., description="Size of each unit in ml/g", gt=0)
    packaging_cost_per_unit: float = Field(0, description="Packaging cost per unit (₹)", ge=0)
    labeling_cost_per_unit: float = Field(0, description="Labeling cost per unit (₹)", ge=0)
    manufacturing_overhead_percent: float = Field(0, description="Manufacturing overhead as percentage", ge=0, le=100)


class IngredientInput(BaseModel):
    """Input schema for a single ingredient"""
    id: Union[str, int] = Field(..., description="Unique ingredient identifier")
    name: str = Field(..., description="Ingredient name")
    inci: str = Field(..., description="INCI name")
    percent: float = Field(..., description="Percentage in formulation", ge=0, le=100)
    cost_per_kg: float = Field(..., description="Cost per kilogram (₹)", ge=0)
    function: Optional[str] = Field(None, description="Functional category")
    phase_id: Optional[str] = Field(None, description="Phase identifier this ingredient belongs to")
    is_hero: Optional[bool] = Field(False, description="Whether this is a hero ingredient")
    min_percent: Optional[float] = Field(None, description="Minimum allowed percentage (for optimization)", ge=0)
    max_percent: Optional[float] = Field(None, description="Maximum allowed percentage (for optimization)", ge=0)


class PhaseInput(BaseModel):
    """Input schema for a formulation phase"""
    id: str = Field(..., description="Phase identifier (e.g., 'A', 'B', 'C')")
    name: str = Field(..., description="Phase name (e.g., 'Water Phase')")
    ingredients: List[IngredientInput] = Field(..., description="List of ingredients in this phase")


class CostCalculatorRequest(BaseModel):
    """Request schema for cost calculation"""
    batch_settings: BatchSettings = Field(..., description="Batch configuration")
    phases: List[PhaseInput] = Field(..., description="List of phases with ingredients")
    formula_name: Optional[str] = Field(None, description="Name of the formula")


class IngredientCostDetail(BaseModel):
    """Detailed cost breakdown for a single ingredient"""
    id: Union[str, int]
    name: str
    inci: str
    percent: float
    cost_per_kg: float
    grams_needed: float
    cost_for_batch: float
    cost_per_unit: float
    cost_per_gram: float
    function: Optional[str] = None
    phase_id: Optional[str] = None
    is_hero: Optional[bool] = False
    contribution_percent: float = Field(..., description="Percentage contribution to total raw material cost")


class PhaseCostDetail(BaseModel):
    """Cost breakdown for a phase"""
    id: str
    name: str
    total_cost: float
    total_percent: float
    ingredients: List[IngredientCostDetail]


class CostAnalysisResponse(BaseModel):
    """Response schema for cost analysis tab"""
    formula_name: Optional[str] = None
    batch_size: int
    unit_size: float
    batch_grams: float
    
    # Cost breakdowns
    phases: List[PhaseCostDetail]
    all_ingredients: List[IngredientCostDetail]
    
    # Totals
    raw_material_cost: float
    raw_material_cost_per_unit: float
    packaging_cost_total: float
    labeling_cost_total: float
    manufacturing_cost: float
    total_batch_cost: float
    cost_per_unit: float
    
    # Statistics
    total_percentage: float
    top_cost_contributors: List[IngredientCostDetail]
    cost_by_category: Dict[str, float]


class OptimizationConstraint(BaseModel):
    """Constraint for optimization"""
    ingredient_id: Union[str, int]
    min_percent: Optional[float] = None
    max_percent: Optional[float] = None
    fixed_percent: Optional[float] = None  # If set, ingredient percentage is fixed


class OptimizationRequest(BaseModel):
    """Request schema for cost optimization"""
    batch_settings: BatchSettings
    phases: List[PhaseInput]
    target_cost_per_unit: Optional[float] = Field(None, description="Target cost per unit (₹)")
    target_cost_reduction_percent: Optional[float] = Field(None, description="Target cost reduction percentage", ge=0, le=100)
    constraints: Optional[List[OptimizationConstraint]] = Field(None, description="Additional optimization constraints")
    preserve_hero_ingredients: bool = Field(True, description="Keep hero ingredient percentages fixed")
    preserve_phase_totals: bool = Field(False, description="Keep phase total percentages fixed")


class OptimizedIngredient(BaseModel):
    """Optimized ingredient with new percentage"""
    id: Union[str, int]
    original_percent: float
    optimized_percent: float
    cost_savings: float
    percent_change: float


class OptimizationResponse(BaseModel):
    """Response schema for optimization tab"""
    original_cost_per_unit: float
    optimized_cost_per_unit: float
    cost_reduction: float
    cost_reduction_percent: float
    optimized_ingredients: List[OptimizedIngredient]
    optimization_summary: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class PricingScenario(BaseModel):
    """Pricing scenario calculation"""
    multiplier: float
    mrp: float
    profit_per_unit: float
    profit_margin_percent: float
    total_profit: float


class PricingResponse(BaseModel):
    """Response schema for pricing tab"""
    cost_per_unit: float
    scenarios: List[PricingScenario]
    recommended_mrp: float
    recommended_multiplier: float


class CostSheetItem(BaseModel):
    """Item in cost sheet export"""
    phase_id: str
    phase_name: str
    ingredient_name: str
    inci_name: str
    percentage: float
    grams_per_batch: float
    cost_per_kg: float
    cost_per_batch: float
    cost_per_unit: float
    function: Optional[str] = None


class CostSheetResponse(BaseModel):
    """Response schema for cost sheet tab"""
    formula_name: Optional[str] = None
    batch_settings: BatchSettings
    cost_summary: Dict[str, float]
    items: List[CostSheetItem]
    phases_summary: List[Dict[str, Any]]
    export_formats: List[str] = Field(default_factory=lambda: ["json", "csv", "excel"])

