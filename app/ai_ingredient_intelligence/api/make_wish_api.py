"""
Make a Wish API Endpoint
========================

This module provides the API endpoint for the "Make a Wish" feature.

ENDPOINT: POST /api/make-wish/generate

WHAT IT DOES:
- Accepts wish data from frontend
- Runs complete 5-stage AI pipeline
- Returns comprehensive formula with all analysis

STAGES:
1. Ingredient Selection
2. Formula Optimization
3. Manufacturing Process
4. Cost Analysis
5. Compliance Check
"""

from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import time

# Import authentication - Using JWT tokens
from app.ai_ingredient_intelligence.auth import verify_jwt_token

from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    generate_formula_from_wish
)
from app.ai_ingredient_intelligence.models.schemas import (
    MakeWishRequest,
    MakeWishResponse
)

router = APIRouter(prefix="/make-wish", tags=["Make a Wish"])


@router.post("/generate", response_model=MakeWishResponse)
async def generate_make_wish_formula(
    request: MakeWishRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate a cosmetic formulation using the complete 5-stage "Make a Wish" AI pipeline.
    
    REQUEST BODY:
    {
        "category": "skincare" or "haircare",
        "productType": "serum",
        "benefits": ["Brightening", "Hydration"],
        "exclusions": ["Silicone-free", "Paraben-free"],
        "heroIngredients": ["Niacinamide", "Hyaluronic Acid"],
        "costMin": 30,
        "costMax": 60,
        "texture": "lightweight",
        "claims": ["Vegan", "Dermatologist-tested"],
        "targetAudience": ["oily-skin", "young-adults"],
        "additionalNotes": "Additional requirements"
    }
    
    RESPONSE:
    Complete formula with:
    - Ingredient selection
    - Optimized percentages
    - Manufacturing process
    - Cost analysis
    - Compliance check
    """
    start_time = time.time()
    
    try:
        # Convert Pydantic model to dict
        wish_data = request.model_dump()
        
        # Validate required fields
        if not wish_data.get("productType"):
            raise HTTPException(
                status_code=400,
                detail="productType is required"
            )
        
        if not wish_data.get("benefits") or len(wish_data.get("benefits", [])) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one benefit is required"
            )
        
        # Set defaults
        wish_data.setdefault("category", "skincare")
        wish_data.setdefault("texture", "lightweight")
        wish_data.setdefault("exclusions", [])
        wish_data.setdefault("heroIngredients", [])
        wish_data.setdefault("claims", [])
        wish_data.setdefault("targetAudience", [])
        wish_data.setdefault("additionalNotes", "")
        
        if wish_data.get("costMin") is None:
            wish_data["costMin"] = 30
        if wish_data.get("costMax") is None:
            wish_data["costMax"] = 60
        
        # Validate cost range
        if wish_data["costMin"] >= wish_data["costMax"]:
            raise HTTPException(
                status_code=400,
                detail="costMax must be greater than costMin"
            )
        if wish_data["costMin"] < 0 or wish_data["costMax"] < 0:
            raise HTTPException(
                status_code=400,
                detail="Cost values must be positive"
            )
        
        print(f"📝 Generating Make a Wish formula...")
        print(f"   Category: {wish_data['category']}")
        print(f"   Product Type: {wish_data['productType']}")
        print(f"   Benefits: {', '.join(wish_data['benefits'])}")
        print(f"   Exclusions: {', '.join(wish_data.get('exclusions', []))}")
        print(f"   Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
        print(f"   Cost Range: ₹{wish_data['costMin']} - ₹{wish_data['costMax']}/100g")
        
        # Generate formula using 5-stage pipeline
        try:
            result = await generate_formula_from_wish(wish_data)
        except ValueError as ve:
            raise HTTPException(
                status_code=400,
                detail=f"Formula generation validation error: {str(ve)}"
            )
        except Exception as gen_error:
            print(f"❌ Error in generate_formula_from_wish: {gen_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error during formula generation: {str(gen_error)}"
            )
        
        # Validate response structure
        if not result or not isinstance(result, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid formula structure returned"
            )
        
        processing_time = time.time() - start_time
        print(f"✅ Make a Wish formula generated in {processing_time:.2f}s")
        
        # Extract key metrics
        optimized = result.get("optimized_formula", {})
        cost_analysis = result.get("cost_analysis", {})
        compliance = result.get("compliance", {})
        
        print(f"   Formula Cost: ₹{cost_analysis.get('raw_material_cost', {}).get('total_per_100g', 0)}/100g")
        print(f"   Compliance: {compliance.get('overall_status', 'UNKNOWN')}")
        print(f"   Ingredients: {len(optimized.get('ingredients', []))}")
        
        # Return response
        return MakeWishResponse(**result)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error generating Make a Wish formula: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

