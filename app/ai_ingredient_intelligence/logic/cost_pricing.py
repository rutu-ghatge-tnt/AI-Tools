"""
Cost Pricing Logic
==================

Calculate pricing scenarios and recommendations.
Pure mathematical calculations - no AI required.

HOW IT WORKS:
1. Calculate different pricing multipliers (2x, 2.5x, 3x, 4x)
2. Calculate profit margins for each scenario
3. Recommend optimal pricing based on industry standards
"""

from typing import List, Optional
from app.ai_ingredient_intelligence.models.cost_calculator_schemas import (
    PricingScenario,
    PricingResponse
)


def calculate_pricing_scenarios(
    cost_per_unit: float,
    batch_size: int,
    multipliers: Optional[List[float]] = None
) -> PricingResponse:
    """
    Calculate pricing scenarios for different multipliers
    
    HOW IT WORKS:
    - For each multiplier: MRP = cost_per_unit * multiplier
    - Profit = MRP - cost_per_unit
    - Margin = (Profit / MRP) * 100
    
    RETURNS:
    Pricing response with scenarios and recommendations
    """
    if multipliers is None:
        multipliers = [2.0, 2.5, 3.0, 4.0]
    
    scenarios = []
    for multiplier in multipliers:
        mrp = cost_per_unit * multiplier
        profit_per_unit = mrp - cost_per_unit
        profit_margin_percent = (profit_per_unit / mrp * 100.0) if mrp > 0 else 0.0
        total_profit = profit_per_unit * batch_size
        
        scenarios.append(
            PricingScenario(
                multiplier=multiplier,
                mrp=round(mrp, 2),
                profit_per_unit=round(profit_per_unit, 2),
                profit_margin_percent=round(profit_margin_percent, 2),
                total_profit=round(total_profit, 2)
            )
        )
    
    # Recommend pricing (typically 3x for cosmetics, but can adjust)
    # Recommendation: Use 3x multiplier (67% margin) as standard
    recommended_multiplier = 3.0
    recommended_mrp = cost_per_unit * recommended_multiplier
    
    return PricingResponse(
        cost_per_unit=round(cost_per_unit, 2),
        scenarios=scenarios,
        recommended_mrp=round(recommended_mrp, 2),
        recommended_multiplier=recommended_multiplier
    )

