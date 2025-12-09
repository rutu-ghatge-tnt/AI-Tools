"""
Cost Calculator API Endpoint
============================

API endpoints for cost calculator with 4 tabs:
1. Cost Analysis - Detailed cost breakdown
2. Optimize - Cost optimization using linear programming
3. Pricing - Pricing scenarios and recommendations
4. Cost Sheet - Export-ready cost sheet

ENDPOINTS:
- POST /api/cost-calculator/analyze - Cost analysis
- POST /api/cost-calculator/optimize - Cost optimization
- POST /api/cost-calculator/pricing - Pricing scenarios
- POST /api/cost-calculator/cost-sheet - Cost sheet generation
- GET /api/cost-calculator/lookup-ingredient - Lookup ingredient by INCI

NO AI REQUIRED - Pure mathematical calculations
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
import time
from app.ai_ingredient_intelligence.models.cost_calculator_schemas import (
    CostCalculatorRequest,
    CostAnalysisResponse,
    OptimizationRequest,
    OptimizationResponse,
    PricingResponse,
    CostSheetResponse
)
from app.ai_ingredient_intelligence.logic.cost_calculator import calculate_cost_analysis
from app.ai_ingredient_intelligence.logic.cost_optimizer import optimize_cost
from app.ai_ingredient_intelligence.logic.cost_pricing import calculate_pricing_scenarios
from app.ai_ingredient_intelligence.logic.cost_sheet import generate_cost_sheet
from app.ai_ingredient_intelligence.db.collections import (
    branded_ingredients_col,
    inci_col,
    functional_categories_col,
    distributor_col
)
from bson import ObjectId

router = APIRouter(prefix="/cost-calculator", tags=["Cost Calculator"])


@router.get("/lookup-ingredient")
async def lookup_ingredient(inci: str):
    """
    Lookup ingredient details by INCI name
    
    Returns cost per kg and function from database.
    If not found in branded ingredients, checks general INCI collection.
    
    QUERY PARAMS:
    - inci: INCI name to lookup
    
    RESPONSE:
    {
        "name": "Ingredient name",
        "inci": "INCI name",
        "cost_per_kg": 1200.0,
        "function": "Brightening",
        "found": true
    }
    """
    if not inci or not inci.strip():
        raise HTTPException(status_code=400, detail="INCI name is required")
    
    try:
        inci_normalized = inci.strip().lower()
        
        # First, try to find in branded ingredients collection
        # Look for ingredients where INCI matches
        inci_doc = await inci_col.find_one(
            {"inciName_normalized": inci_normalized}
        )
        
        cost_per_kg = None
        function = None
        name = None
        found = False
        
        if inci_doc:
            inci_id = inci_doc.get("_id")
            # Get category/function from INCI collection
            category = inci_doc.get("category", "")
            if category:
                function = category
            
            # Try to find branded ingredient with this INCI to get cost
            async for branded_ing in branded_ingredients_col.find(
                {"inci_ids": inci_id}
            ).limit(1):
                ing_id = str(branded_ing.get("_id"))
                name = branded_ing.get("ingredient_name", inci)
                
                # Try to get cost from distributor collection
                distributor_doc = await distributor_col.find_one(
                    {"ingredientIds": ing_id},
                    sort=[("createdAt", -1)]  # Get most recent
                )
                
                if distributor_doc and distributor_doc.get("pricePerKg"):
                    cost_per_kg = float(distributor_doc.get("pricePerKg", 0))
                elif branded_ing.get("estimated_cost_per_kg"):
                    cost_per_kg = float(branded_ing.get("estimated_cost_per_kg", 0))
                else:
                    # Use default estimates based on category
                    if category == "Active":
                        cost_per_kg = 5000  # Default for actives
                    else:
                        cost_per_kg = 500  # Default for excipients
                
                found = True
                break
            
            # If no branded ingredient found, use INCI data
            if not found:
                name = inci_doc.get("inciName", inci)
                if category == "Active":
                    cost_per_kg = 5000
                else:
                    cost_per_kg = 500
                found = True
        
        # If still not found, return defaults
        if not found:
            name = inci
            cost_per_kg = 1000  # Default cost
            function = "Other"
        
        return {
            "name": name,
            "inci": inci,
            "cost_per_kg": cost_per_kg,
            "function": function or "Other",
            "found": found
        }
    
    except Exception as e:
        print(f"Error looking up ingredient: {e}")
        import traceback
        traceback.print_exc()
        # Return defaults on error
        return {
            "name": inci,
            "inci": inci,
            "cost_per_kg": 1000,
            "function": "Other",
            "found": False
        }


@router.post("/analyze", response_model=CostAnalysisResponse)
async def analyze_cost(request: CostCalculatorRequest):
    """
    Calculate detailed cost analysis
    
    REQUEST BODY:
    {
        "batch_settings": {
            "batch_size": 1000,
            "unit_size": 30,
            "packaging_cost_per_unit": 18,
            "labeling_cost_per_unit": 3,
            "manufacturing_overhead_percent": 15
        },
        "phases": [
            {
                "id": "A",
                "name": "Water Phase",
                "ingredients": [
                    {
                        "id": 1,
                        "name": "Purified Water",
                        "inci": "Aqua",
                        "percent": 74.30,
                        "cost_per_kg": 0.15,
                        "function": "Solvent"
                    }
                ]
            }
        ],
        "formula_name": "Brightening Serum"
    }
    
    RESPONSE:
    Complete cost analysis with breakdowns, totals, and statistics
    
    HOW IT WORKS:
    - Calculates ingredient costs based on percentages and batch size
    - Calculates phase costs
    - Calculates totals (raw materials, packaging, labeling, manufacturing)
    - Identifies top cost contributors
    - Groups costs by category
    """
    start_time = time.time()
    
    try:
        # Validate request
        if not request.phases:
            raise HTTPException(
                status_code=400,
                detail="At least one phase is required"
            )
        
        if not any(phase.ingredients for phase in request.phases):
            raise HTTPException(
                status_code=400,
                detail="At least one ingredient is required"
            )
        
        # Calculate cost analysis
        analysis = calculate_cost_analysis(
            batch_settings=request.batch_settings,
            phases=request.phases,
            formula_name=request.formula_name
        )
        
        processing_time = time.time() - start_time
        print(f"✅ Cost analysis completed in {processing_time:.2f}s")
        print(f"   Cost per unit: ₹{analysis.cost_per_unit:.2f}")
        print(f"   Total batch cost: ₹{analysis.total_batch_cost:.2f}")
        
        return analysis
    
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Error calculating cost analysis: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating cost analysis: {str(e)}"
        )


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_cost_endpoint(request: OptimizationRequest):
    """
    Optimize formulation cost using linear programming
    
    REQUEST BODY:
    {
        "batch_settings": {...},
        "phases": [...],
        "target_cost_per_unit": 25.0,  // Optional
        "target_cost_reduction_percent": 10.0,  // Optional
        "constraints": [  // Optional
            {
                "ingredient_id": 1,
                "min_percent": 5.0,
                "max_percent": 10.0
            }
        ],
        "preserve_hero_ingredients": true,
        "preserve_phase_totals": false
    }
    
    RESPONSE:
    Optimization results with new percentages and cost savings
    
    ALGORITHM: Linear Programming (scipy.optimize.linprog)
    - Minimizes total cost
    - Respects min/max percentage constraints
    - Maintains total percentage = 100%
    - Can preserve hero ingredients
    """
    start_time = time.time()
    
    try:
        # Validate request
        if not request.phases:
            raise HTTPException(
                status_code=400,
                detail="At least one phase is required"
            )
        
        # Optimize cost
        optimization = optimize_cost(
            batch_settings=request.batch_settings,
            phases=request.phases,
            target_cost_per_unit=request.target_cost_per_unit,
            target_cost_reduction_percent=request.target_cost_reduction_percent,
            constraints=request.constraints,
            preserve_hero_ingredients=request.preserve_hero_ingredients,
            preserve_phase_totals=request.preserve_phase_totals
        )
        
        processing_time = time.time() - start_time
        print(f"✅ Cost optimization completed in {processing_time:.2f}s")
        print(f"   Original cost: ₹{optimization.original_cost_per_unit:.2f}")
        print(f"   Optimized cost: ₹{optimization.optimized_cost_per_unit:.2f}")
        print(f"   Cost reduction: {optimization.cost_reduction_percent:.2f}%")
        
        return optimization
    
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Error optimizing cost: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error optimizing cost: {str(e)}"
        )


@router.post("/pricing", response_model=PricingResponse)
async def calculate_pricing(request: CostCalculatorRequest):
    """
    Calculate pricing scenarios for different multipliers
    
    REQUEST BODY:
    Same as /analyze endpoint
    
    RESPONSE:
    Pricing scenarios with different multipliers (2x, 2.5x, 3x, 4x)
    and recommended pricing
    
    HOW IT WORKS:
    - Calculates MRP for different multipliers
    - Calculates profit margins
    - Recommends optimal pricing (typically 3x for cosmetics)
    """
    start_time = time.time()
    
    try:
        # Calculate cost analysis first
        analysis = calculate_cost_analysis(
            batch_settings=request.batch_settings,
            phases=request.phases,
            formula_name=request.formula_name
        )
        
        # Calculate pricing scenarios
        pricing = calculate_pricing_scenarios(
            cost_per_unit=analysis.cost_per_unit,
            batch_size=request.batch_settings.batch_size
        )
        
        processing_time = time.time() - start_time
        print(f"✅ Pricing calculation completed in {processing_time:.2f}s")
        print(f"   Recommended MRP: ₹{pricing.recommended_mrp:.2f}")
        
        return pricing
    
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Error calculating pricing: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating pricing: {str(e)}"
        )


@router.post("/cost-sheet", response_model=CostSheetResponse)
async def generate_cost_sheet_endpoint(request: CostCalculatorRequest):
    """
    Generate detailed cost sheet for export
    
    REQUEST BODY:
    Same as /analyze endpoint
    
    RESPONSE:
    Cost sheet with all ingredients, costs, and summaries
    Ready for export to JSON, CSV, or Excel
    
    HOW IT WORKS:
    - Flattens all ingredients from phases
    - Formats data for export
    - Creates summary sections
    """
    start_time = time.time()
    
    try:
        # Validate request
        if not request.phases:
            raise HTTPException(
                status_code=400,
                detail="At least one phase is required"
            )
        
        # Generate cost sheet
        cost_sheet = generate_cost_sheet(
            batch_settings=request.batch_settings,
            phases=request.phases,
            formula_name=request.formula_name
        )
        
        processing_time = time.time() - start_time
        print(f"✅ Cost sheet generated in {processing_time:.2f}s")
        print(f"   Items: {len(cost_sheet.items)}")
        
        return cost_sheet
    
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        print(f"❌ Error generating cost sheet: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error generating cost sheet: {str(e)}"
        )
