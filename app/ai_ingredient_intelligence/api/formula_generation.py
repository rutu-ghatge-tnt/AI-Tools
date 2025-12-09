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

from fastapi import APIRouter, HTTPException, Header
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time
from app.ai_ingredient_intelligence.models.schemas import (
    CreateWishRequest,
    GenerateFormulaResponse
)
from app.ai_ingredient_intelligence.logic.formula_generator import (
    generate_formula,
    get_texture_description
)
from app.ai_ingredient_intelligence.db.collections import wish_history_col

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


@router.post("/save-wish-history")
async def save_wish_history(
    payload: dict,
    user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Save wish history with formula data (user-specific)
    
    Request body:
    {
        "name": "Formula Name",
        "wish_data": {...},  # Original wish data
        "formula_result": {...},  # Generated formula
        "notes": "Optional notes"
    }
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        print(f"📝 Save wish history request received")
        print(f"   User ID from header: {user_id}")
        print(f"   Payload keys: {list(payload.keys())}")
        
        # Validate payload
        if "name" not in payload:
            print("❌ Missing required field: name")
            raise HTTPException(status_code=400, detail="Missing required field: name")
        if "wish_data" not in payload:
            print("❌ Missing required field: wish_data")
            raise HTTPException(status_code=400, detail="Missing required field: wish_data")
        if "formula_result" not in payload:
            print("❌ Missing required field: formula_result")
            raise HTTPException(status_code=400, detail="Missing required field: formula_result")
        
        # Get user_id from header or payload
        user_id_value = user_id or payload.get("user_id")
        if not user_id_value:
            print("❌ User ID not provided")
            raise HTTPException(
                status_code=400,
                detail="User ID is required. Please provide X-User-Id header or user_id in payload"
            )
        
        print(f"✅ Validating data for user: {user_id_value}")
        
        # Create history document
        history_doc = {
            "user_id": user_id_value,
            "name": payload["name"],
            "wish_data": payload["wish_data"],
            "formula_result": payload["formula_result"],
            "notes": payload.get("notes", ""),
            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        
        print(f"📦 Inserting document into MongoDB collection: wish_history")
        print(f"   Document name: {history_doc['name']}")
        print(f"   Has wish_data: {bool(history_doc.get('wish_data'))}")
        print(f"   Has formula_result: {bool(history_doc.get('formula_result'))}")
        
        # Insert into MongoDB
        result = await wish_history_col.insert_one(history_doc)
        
        print(f"✅ Wish history saved successfully with ID: {result.inserted_id}")
        
        return {
            "success": True,
            "id": str(result.inserted_id),
            "message": "Wish history saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error saving wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save wish history: {str(e)}"
        )


@router.get("/wish-history")
async def get_wish_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Get wish history for a user
    
    Query params:
    - search: Optional search term
    - limit: Number of results (default 50)
    - skip: Number of results to skip (default 0)
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID is required. Please provide X-User-Id header"
            )
        
        # Build query
        query = {"user_id": user_id}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"notes": {"$regex": search, "$options": "i"}}
            ]
        
        # Get total count
        total = await wish_history_col.count_documents(query)
        
        # Get items
        cursor = wish_history_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = []
        async for doc in cursor:
            items.append({
                "id": str(doc["_id"]),
                "name": doc.get("name", ""),
                "wish_data": doc.get("wish_data", {}),
                "formula_result": doc.get("formula_result", {}),
                "notes": doc.get("notes", ""),
                "created_at": doc.get("created_at", "")
            })
        
        return {
            "items": items,
            "total": total
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get wish history: {str(e)}"
        )


@router.delete("/wish-history/{history_id}")
async def delete_wish_history(
    history_id: str,
    user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Delete a wish history item
    
    Headers:
    - X-User-Id: User ID (required)
    """
    try:
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID is required. Please provide X-User-Id header"
            )
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Delete only if it belongs to the user
        result = await wish_history_col.delete_one(
            {"_id": ObjectId(history_id), "user_id": user_id}
        )
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to delete it"
            )
        
        return {
            "success": True,
            "message": "History item deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete wish history: {str(e)}"
        )

