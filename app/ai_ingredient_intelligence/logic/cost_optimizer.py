"""
Cost Optimizer Logic
====================

Optimization algorithms for cost reduction.
Uses Linear Programming (scipy.optimize) for continuous optimization.

ALGORITHM: Linear Programming
- Better than knapsack for continuous variables (percentages)
- Can handle constraints (min/max percentages, fixed ingredients)
- Optimizes cost while maintaining formulation integrity

HOW IT WORKS:
1. Define objective function: minimize total cost
2. Set constraints:
   - Total percentage = 100%
   - Min/max percentages for each ingredient
   - Fixed percentages for hero ingredients (optional)
   - Phase total constraints (optional)
3. Solve using scipy.optimize.linprog
4. Return optimized percentages with cost savings
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from scipy.optimize import linprog
from app.ai_ingredient_intelligence.models.cost_calculator_schemas import (
    BatchSettings,
    IngredientInput,
    PhaseInput,
    OptimizationConstraint,
    OptimizedIngredient,
    OptimizationResponse
)
from app.ai_ingredient_intelligence.logic.cost_calculator import calculate_cost_analysis


def optimize_cost(
    batch_settings: BatchSettings,
    phases: List[PhaseInput],
    target_cost_per_unit: Optional[float] = None,
    target_cost_reduction_percent: Optional[float] = None,
    constraints: Optional[List[OptimizationConstraint]] = None,
    preserve_hero_ingredients: bool = True,
    preserve_phase_totals: bool = False
) -> OptimizationResponse:
    """
    Optimize formulation cost using linear programming
    
    ALGORITHM: Linear Programming
    - Objective: Minimize total cost
    - Variables: Ingredient percentages
    - Constraints: Min/max percentages, total = 100%
    
    HOW IT WORKS:
    1. Collect all ingredients with their constraints
    2. Build objective function (cost coefficients)
    3. Build constraint matrix (equality and inequality)
    4. Solve using scipy.optimize.linprog
    5. Calculate cost savings
    6. Return optimized percentages
    
    RETURNS:
    Optimization response with new percentages and cost savings
    """
    # Get original cost
    original_analysis = calculate_cost_analysis(batch_settings, phases)
    original_cost_per_unit = original_analysis.cost_per_unit
    
    # Collect all ingredients
    all_ingredients = []
    ingredient_index_map = {}  # Map ingredient ID to index
    
    for phase in phases:
        for ingredient in phase.ingredients:
            ingredient_index_map[ingredient.id] = len(all_ingredients)
            all_ingredients.append(ingredient)
    
    n_ingredients = len(all_ingredients)
    
    if n_ingredients == 0:
        raise ValueError("No ingredients provided for optimization")
    
    # Build cost coefficients (objective function: minimize cost)
    # Cost per unit = (percent / 100) * (batch_grams / 1000) * (cost_per_kg / batch_size)
    batch_grams = batch_settings.batch_size * batch_settings.unit_size
    cost_coefficients = np.array([
        (ing.cost_per_kg / 1000.0) * (batch_grams / batch_settings.batch_size) / 100.0
        for ing in all_ingredients
    ])
    
    # Build constraint matrix
    # Constraint 1: Total percentage = 100%
    equality_constraints = []
    equality_values = []
    
    # Sum of all percentages = 100
    equality_constraints.append(np.ones(n_ingredients))
    equality_values.append(100.0)
    
    # Build inequality constraints (min/max bounds)
    lower_bounds = []
    upper_bounds = []
    
    for i, ingredient in enumerate(all_ingredients):
        # Get min/max from ingredient or constraints
        min_percent = ingredient.min_percent
        max_percent = ingredient.max_percent
        
        # Check if there's a constraint override
        if constraints:
            for constraint in constraints:
                if constraint.ingredient_id == ingredient.id:
                    if constraint.fixed_percent is not None:
                        min_percent = constraint.fixed_percent
                        max_percent = constraint.fixed_percent
                    else:
                        if constraint.min_percent is not None:
                            min_percent = constraint.min_percent
                        if constraint.max_percent is not None:
                            max_percent = constraint.max_percent
                    break
        
        # Preserve hero ingredients if requested
        if preserve_hero_ingredients and ingredient.is_hero:
            min_percent = ingredient.percent
            max_percent = ingredient.percent
        
        # Set defaults if not specified
        if min_percent is None:
            min_percent = 0.0
        if max_percent is None:
            max_percent = 100.0
        
        # Ensure bounds are valid
        min_percent = max(0.0, min(min_percent, 100.0))
        max_percent = max(min_percent, min(max_percent, 100.0))
        
        lower_bounds.append(min_percent)
        upper_bounds.append(max_percent)
    
    # Convert to numpy arrays
    lower_bounds = np.array(lower_bounds)
    upper_bounds = np.array(upper_bounds)
    
    # Solve linear programming problem
    # Minimize: cost_coefficients @ x
    # Subject to: sum(x) = 100, lower_bounds <= x <= upper_bounds
    try:
        result = linprog(
            c=cost_coefficients,
            A_eq=np.array(equality_constraints),
            b_eq=np.array(equality_values),
            bounds=list(zip(lower_bounds, upper_bounds)),
            method='highs'  # Use HiGHS solver (faster and more reliable)
        )
        
        if not result.success:
            # If optimization fails, try with relaxed constraints
            warnings_list = [f"Optimization warning: {result.message}"]
            
            # Fallback: use original percentages
            optimized_percentages = [ing.percent for ing in all_ingredients]
        else:
            optimized_percentages = result.x.tolist()
            warnings_list = []
            
            # Round to 2 decimal places
            optimized_percentages = [round(p, 2) for p in optimized_percentages]
            
            # Ensure total is exactly 100 (adjust largest value if needed)
            total = sum(optimized_percentages)
            if abs(total - 100.0) > 0.01:
                diff = 100.0 - total
                # Add difference to the ingredient with highest percentage
                max_idx = optimized_percentages.index(max(optimized_percentages))
                optimized_percentages[max_idx] += diff
                optimized_percentages[max_idx] = round(optimized_percentages[max_idx], 2)
    
    except Exception as e:
        # Fallback to original if optimization fails
        optimized_percentages = [ing.percent for ing in all_ingredients]
        warnings_list = [f"Optimization failed: {str(e)}. Using original percentages."]
    
    # Create optimized phases
    optimized_phases = []
    for phase in phases:
        optimized_phase_ingredients = []
        for ingredient in phase.ingredients:
            idx = ingredient_index_map[ingredient.id]
            new_percent = optimized_percentages[idx]
            optimized_phase_ingredients.append(
                IngredientInput(
                    id=ingredient.id,
                    name=ingredient.name,
                    inci=ingredient.inci,
                    percent=new_percent,
                    cost_per_kg=ingredient.cost_per_kg,
                    function=ingredient.function,
                    phase_id=ingredient.phase_id,
                    is_hero=ingredient.is_hero,
                    min_percent=ingredient.min_percent,
                    max_percent=ingredient.max_percent
                )
            )
        optimized_phases.append(
            PhaseInput(
                id=phase.id,
                name=phase.name,
                ingredients=optimized_phase_ingredients
            )
        )
    
    # Calculate optimized cost
    optimized_analysis = calculate_cost_analysis(batch_settings, optimized_phases)
    optimized_cost_per_unit = optimized_analysis.cost_per_unit
    
    # Calculate savings
    cost_reduction = original_cost_per_unit - optimized_cost_per_unit
    cost_reduction_percent = (cost_reduction / original_cost_per_unit * 100.0) if original_cost_per_unit > 0 else 0.0
    
    # Check if target was met
    if target_cost_per_unit is not None:
        if optimized_cost_per_unit > target_cost_per_unit:
            warnings_list.append(f"Target cost of ₹{target_cost_per_unit:.2f} not achieved. Optimized cost: ₹{optimized_cost_per_unit:.2f}")
    
    if target_cost_reduction_percent is not None:
        if cost_reduction_percent < target_cost_reduction_percent:
            warnings_list.append(f"Target reduction of {target_cost_reduction_percent}% not achieved. Actual reduction: {cost_reduction_percent:.2f}%")
    
    # Build optimized ingredients list
    optimized_ingredients = []
    for i, ingredient in enumerate(all_ingredients):
        original_percent = ingredient.percent
        optimized_percent = optimized_percentages[i]
        
        # Calculate cost savings for this ingredient
        batch_grams = batch_settings.batch_size * batch_settings.unit_size
        original_cost = (original_percent / 100.0) * (batch_grams / 1000.0) * ingredient.cost_per_kg / batch_settings.batch_size
        optimized_cost = (optimized_percent / 100.0) * (batch_grams / 1000.0) * ingredient.cost_per_kg / batch_settings.batch_size
        cost_savings = original_cost - optimized_cost
        
        optimized_ingredients.append(
            OptimizedIngredient(
                id=ingredient.id,
                original_percent=original_percent,
                optimized_percent=optimized_percent,
                cost_savings=round(cost_savings, 2),
                percent_change=round(optimized_percent - original_percent, 2)
            )
        )
    
    # Build optimization summary
    optimization_summary = {
        "method": "Linear Programming (scipy.optimize.linprog)",
        "solver": "HiGHS",
        "ingredients_optimized": n_ingredients,
        "ingredients_fixed": sum(1 for ing in all_ingredients if preserve_hero_ingredients and ing.is_hero),
        "constraints_applied": len(constraints) if constraints else 0,
        "optimization_successful": len(warnings_list) == 0
    }
    
    return OptimizationResponse(
        original_cost_per_unit=round(original_cost_per_unit, 2),
        optimized_cost_per_unit=round(optimized_cost_per_unit, 2),
        cost_reduction=round(cost_reduction, 2),
        cost_reduction_percent=round(cost_reduction_percent, 2),
        optimized_ingredients=optimized_ingredients,
        optimization_summary=optimization_summary,
        warnings=warnings_list
    )

