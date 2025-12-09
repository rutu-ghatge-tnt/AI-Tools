"""
Cost Sheet Logic
================

Generate detailed cost sheet for export.
Pure data formatting - no calculations needed.

HOW IT WORKS:
1. Flatten all ingredients from phases
2. Format data for export (JSON, CSV, Excel)
3. Create summary sections
"""

from typing import List, Dict, Any, Optional
from app.ai_ingredient_intelligence.models.cost_calculator_schemas import (
    BatchSettings,
    PhaseInput,
    CostSheetItem,
    CostSheetResponse,
    CostAnalysisResponse
)
from app.ai_ingredient_intelligence.logic.cost_calculator import calculate_cost_analysis


def generate_cost_sheet(
    batch_settings: BatchSettings,
    phases: List[PhaseInput],
    formula_name: Optional[str] = None
) -> CostSheetResponse:
    """
    Generate detailed cost sheet for export
    
    HOW IT WORKS:
    1. Calculate cost analysis
    2. Flatten ingredients into cost sheet items
    3. Create summary sections
    4. Format for export
    
    RETURNS:
    Cost sheet response ready for export
    """
    # Get cost analysis
    analysis = calculate_cost_analysis(batch_settings, phases, formula_name)
    
    # Flatten ingredients into cost sheet items
    items = []
    for phase in phases:
        for ingredient in phase.ingredients:
            # Find corresponding detail
            detail = next(
                (d for d in analysis.all_ingredients if d.id == ingredient.id),
                None
            )
            
            if detail:
                items.append(
                    CostSheetItem(
                        phase_id=phase.id,
                        phase_name=phase.name,
                        ingredient_name=ingredient.name,
                        inci_name=ingredient.inci,
                        percentage=ingredient.percent,
                        grams_per_batch=detail.grams_needed,
                        cost_per_kg=ingredient.cost_per_kg,
                        cost_per_batch=detail.cost_for_batch,
                        cost_per_unit=detail.cost_per_unit,
                        function=ingredient.function
                    )
                )
    
    # Create cost summary
    cost_summary = {
        "raw_material_cost": analysis.raw_material_cost,
        "raw_material_cost_per_unit": analysis.raw_material_cost_per_unit,
        "packaging_cost_total": analysis.packaging_cost_total,
        "labeling_cost_total": analysis.labeling_cost_total,
        "manufacturing_cost": analysis.manufacturing_cost,
        "total_batch_cost": analysis.total_batch_cost,
        "cost_per_unit": analysis.cost_per_unit,
        "batch_size": batch_settings.batch_size,
        "unit_size": batch_settings.unit_size,
        "batch_grams": analysis.batch_grams
    }
    
    # Create phases summary
    phases_summary = []
    for phase_detail in analysis.phases:
        phases_summary.append({
            "id": phase_detail.id,
            "name": phase_detail.name,
            "total_percent": phase_detail.total_percent,
            "total_cost": phase_detail.total_cost,
            "ingredient_count": len(phase_detail.ingredients)
        })
    
    return CostSheetResponse(
        formula_name=formula_name,
        batch_settings=batch_settings,
        cost_summary=cost_summary,
        items=items,
        phases_summary=phases_summary,
        export_formats=["json", "csv", "excel"]
    )

