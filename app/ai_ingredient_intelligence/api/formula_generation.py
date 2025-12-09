"""
Formula Generation API Endpoint
================================

This module provides the API endpoint for the "Create A Wish" feature.

ENDPOINT: POST /api/generate-formula

WHAT IT DOES:
- Accepts wish data from frontend
- Generates complete cosmetic formulation
- Returns structured formula with phases, ingredients, insights

HOW IT WORKS:
1. Receives CreateWishRequest
2. Calls formula_generator.generate_formula()
3. Returns GenerateFormulaResponse

WHAT WE USE:
- formula_generator.py: Core generation logic
- MongoDB: Ingredient database
- Claude (Anthropic): AI optimization
- BIS RAG: Compliance checking
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import time
from app.ai_ingredient_intelligence.models.schemas import (
    CreateWishRequest,
    GenerateFormulaResponse
)
from app.ai_ingredient_intelligence.logic.formula_generator import (
    generate_formula,
    get_texture_description
)

router = APIRouter(prefix="/formula", tags=["Formula Generation"])


@router.post("/generate", response_model=GenerateFormulaResponse)
async def generate_formula_endpoint(request: CreateWishRequest):
    """
    Generate a cosmetic formulation based on user wish data
    
    REQUEST BODY:
    {
        "productType": "serum",
        "benefits": ["Brightening", "Hydration"],
        "exclusions": ["Silicone-free", "Paraben-free"],
        "heroIngredients": ["Vitamin C", "Hyaluronic Acid"],
        "costMin": 30,
        "costMax": 60,
        "texture": "gel",
        "fragrance": "none",
        "notes": "Additional requirements"
    }
    
    RESPONSE:
    {
        "name": "Brightening Serum",
        "version": "v1",
        "cost": 48.5,
        "ph": {"min": 5.0, "max": 5.5},
        "texture": "Lightweight gel",
        "shelfLife": "12 months",
        "phases": [...],
        "insights": [...],
        "warnings": [...],
        "compliance": {...}
    }
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
        
        # Set defaults only if not provided
        if wish_data.get("costMin") is None:
            wish_data["costMin"] = 30
        if wish_data.get("costMax") is None:
            wish_data["costMax"] = 60
        
        # Validate cost range
        if wish_data.get("costMin") is not None and wish_data.get("costMax") is not None:
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
        
        wish_data.setdefault("texture", wish_data.get("productType", "serum"))
        wish_data.setdefault("fragrance", "none")
        wish_data.setdefault("exclusions", [])
        wish_data.setdefault("heroIngredients", [])
        wish_data.setdefault("notes", "")
        
        print(f"📝 Generating formula for product type: {wish_data['productType']}")
        print(f"   Benefits: {', '.join(wish_data['benefits'])}")
        print(f"   Exclusions: {', '.join(wish_data.get('exclusions', []))}")
        print(f"   Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
        
        # Generate formula using hybrid approach
        try:
            formula = await generate_formula(wish_data)
        except ValueError as ve:
            # Handle specific validation errors
            raise HTTPException(
                status_code=400,
                detail=f"Formula generation validation error: {str(ve)}"
            )
        except Exception as gen_error:
            print(f"❌ Error in generate_formula: {gen_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error during formula generation: {str(gen_error)}"
            )
        
        # Validate response structure
        if not formula or not isinstance(formula, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid formula structure returned"
            )
        
        if "phases" not in formula or not formula["phases"]:
            raise HTTPException(
                status_code=500,
                detail="No phases generated in formula"
            )
        
        processing_time = time.time() - start_time
        print(f"✅ Formula generated in {processing_time:.2f}s")
        print(f"   Cost: ₹{formula.get('cost', 0)}/100g")
        print(f"   Phases: {len(formula.get('phases', []))}")
        print(f"   Ingredients: {sum(len(p.get('ingredients', [])) for p in formula.get('phases', []))}")
        
        # Ensure all required fields are present
        formula.setdefault("name", f"{wish_data['productType'].title()} Formula")
        formula.setdefault("version", "v1")
        formula.setdefault("cost", 0)
        formula.setdefault("costTarget", {"min": wish_data.get("costMin", 30), "max": wish_data.get("costMax", 60)})
        formula.setdefault("ph", {"min": 5.0, "max": 6.5})
        # Import here to avoid circular dependency
        from app.ai_ingredient_intelligence.logic.formula_generator import get_texture_description
        formula.setdefault("texture", get_texture_description(wish_data.get("texture", "serum")))
        formula.setdefault("shelfLife", "12 months")
        formula.setdefault("insights", [])
        formula.setdefault("warnings", [])
        
        # Compliance is set by validate_formula, but set default if not present
        # Compliance logic: False = free (good), True = contains (bad for silicone/paraben)
        # For vegan: True = vegan (good)
        if "compliance" not in formula:
            exclusions = wish_data.get("exclusions", [])
            # Check if formula actually contains these ingredients (will be validated properly in validate_formula)
            formula["compliance"] = {
                "silicone": True,  # Default, will be checked against actual ingredients
                "paraben": True,   # Default, will be checked against actual ingredients
                "vegan": "vegan" in [exc.lower() for exc in exclusions] if exclusions else False
            }
        
        return GenerateFormulaResponse(**formula)
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error generating formula: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

