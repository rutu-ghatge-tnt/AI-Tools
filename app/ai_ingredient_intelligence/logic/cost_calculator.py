"""
Cost Calculator Logic
====================

Mathematical calculations for cost analysis.
No AI required - pure mathematical operations.

HOW IT WORKS:
1. Calculate ingredient costs based on percentages and batch size
2. Calculate phase costs
3. Calculate total batch costs including overhead
4. Calculate per-unit costs
5. Identify top cost contributors
"""

from typing import List, Dict, Any, Optional
from app.ai_ingredient_intelligence.models.cost_calculator_schemas import (
    BatchSettings,
    IngredientInput,
    PhaseInput,
    IngredientCostDetail,
    PhaseCostDetail,
    CostAnalysisResponse
)


def calculate_ingredient_cost(
    ingredient: IngredientInput,
    batch_grams: float
) -> Dict[str, float]:
    """
    Calculate cost details for a single ingredient
    
    FORMULAS:
    - grams_needed = (percent / 100) * batch_grams
    - cost_for_batch = (grams_needed / 1000) * cost_per_kg
    - cost_per_unit = cost_for_batch / batch_size
    - cost_per_gram = cost_per_kg / 1000
    
    RETURNS:
    Dictionary with all calculated cost values
    """
    grams_needed = (ingredient.percent / 100.0) * batch_grams
    cost_for_batch = (grams_needed / 1000.0) * ingredient.cost_per_kg
    cost_per_gram = ingredient.cost_per_kg / 1000.0
    
    return {
        "grams_needed": round(grams_needed, 2),
        "cost_for_batch": round(cost_for_batch, 2),
        "cost_per_gram": round(cost_per_gram, 4)
    }


def calculate_cost_analysis(
    batch_settings: BatchSettings,
    phases: List[PhaseInput],
    formula_name: Optional[str] = None
) -> CostAnalysisResponse:
    """
    Calculate complete cost analysis for a formulation
    
    HOW IT WORKS:
    1. Calculate batch size in grams
    2. Calculate cost for each ingredient
    3. Calculate phase costs
    4. Calculate totals (raw materials, packaging, labeling, manufacturing)
    5. Calculate per-unit costs
    6. Identify top cost contributors
    7. Group costs by category
    
    RETURNS:
    Complete cost analysis response
    """
    # Calculate batch size in grams
    batch_grams = batch_settings.batch_size * batch_settings.unit_size
    
    # Process all ingredients
    all_ingredients_detail = []
    total_percentage = 0.0
    
    for phase in phases:
        for ingredient in phase.ingredients:
            # Calculate ingredient costs
            cost_details = calculate_ingredient_cost(ingredient, batch_grams)
            
            # Create detailed ingredient cost object
            ingredient_detail = IngredientCostDetail(
                id=ingredient.id,
                name=ingredient.name,
                inci=ingredient.inci,
                percent=ingredient.percent,
                cost_per_kg=ingredient.cost_per_kg,
                grams_needed=cost_details["grams_needed"],
                cost_for_batch=cost_details["cost_for_batch"],
                cost_per_unit=cost_details["cost_for_batch"] / batch_settings.batch_size,
                cost_per_gram=cost_details["cost_per_gram"],
                function=ingredient.function,
                phase_id=phase.id,
                is_hero=ingredient.is_hero,
                contribution_percent=0.0  # Will calculate after we have total
            )
            
            all_ingredients_detail.append(ingredient_detail)
            total_percentage += ingredient.percent
    
    # Calculate raw material cost
    raw_material_cost = sum(ing.cost_for_batch for ing in all_ingredients_detail)
    
    # Calculate contribution percentages
    for ingredient_detail in all_ingredients_detail:
        if raw_material_cost > 0:
            ingredient_detail.contribution_percent = (
                (ingredient_detail.cost_for_batch / raw_material_cost) * 100.0
            )
        else:
            ingredient_detail.contribution_percent = 0.0
    
    # Calculate phase costs
    phase_details = []
    for phase in phases:
        phase_ingredients = [
            ing for ing in all_ingredients_detail
            if ing.phase_id == phase.id
        ]
        phase_total_cost = sum(ing.cost_for_batch for ing in phase_ingredients)
        phase_total_percent = sum(ing.percent for ing in phase_ingredients)
        
        phase_detail = PhaseCostDetail(
            id=phase.id,
            name=phase.name,
            total_cost=round(phase_total_cost, 2),
            total_percent=round(phase_total_percent, 2),
            ingredients=phase_ingredients
        )
        phase_details.append(phase_detail)
    
    # Calculate other costs
    packaging_cost_total = batch_settings.packaging_cost_per_unit * batch_settings.batch_size
    labeling_cost_total = batch_settings.labeling_cost_per_unit * batch_settings.batch_size
    raw_material_cost_per_unit = raw_material_cost / batch_settings.batch_size
    
    # Calculate subtotal before manufacturing overhead
    subtotal = raw_material_cost + packaging_cost_total + labeling_cost_total
    
    # Calculate manufacturing overhead
    manufacturing_cost = subtotal * (batch_settings.manufacturing_overhead_percent / 100.0)
    
    # Calculate total batch cost
    total_batch_cost = subtotal + manufacturing_cost
    
    # Calculate cost per unit
    cost_per_unit = total_batch_cost / batch_settings.batch_size
    
    # Identify top cost contributors
    top_contributors = sorted(
        all_ingredients_detail,
        key=lambda x: x.cost_for_batch,
        reverse=True
    )[:5]
    
    # Group costs by category/function
    cost_by_category: Dict[str, float] = {}
    for ing in all_ingredients_detail:
        category = ing.function or "Other"
        if category not in cost_by_category:
            cost_by_category[category] = 0.0
        cost_by_category[category] += ing.cost_for_batch
    
    # Round category costs
    cost_by_category = {k: round(v, 2) for k, v in cost_by_category.items()}
    
    return CostAnalysisResponse(
        formula_name=formula_name,
        batch_size=batch_settings.batch_size,
        unit_size=batch_settings.unit_size,
        batch_grams=round(batch_grams, 2),
        phases=phase_details,
        all_ingredients=all_ingredients_detail,
        raw_material_cost=round(raw_material_cost, 2),
        raw_material_cost_per_unit=round(raw_material_cost_per_unit, 2),
        packaging_cost_total=round(packaging_cost_total, 2),
        labeling_cost_total=round(labeling_cost_total, 2),
        manufacturing_cost=round(manufacturing_cost, 2),
        total_batch_cost=round(total_batch_cost, 2),
        cost_per_unit=round(cost_per_unit, 2),
        total_percentage=round(total_percentage, 2),
        top_cost_contributors=top_contributors,
        cost_by_category=cost_by_category
    )

