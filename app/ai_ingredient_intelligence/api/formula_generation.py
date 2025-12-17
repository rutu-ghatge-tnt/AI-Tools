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

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.models.schemas import (
    CreateWishRequest,
    GenerateFormulaResponse
)
from app.ai_ingredient_intelligence.logic.formula_generator import (
    generate_formula,
    get_texture_description
)
from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    generate_formula_from_wish as generate_make_wish_formula
)
from app.ai_ingredient_intelligence.db.collections import wish_history_col

router = APIRouter(prefix="/formula", tags=["Formula Generation"])


def transform_make_wish_to_frontend_format(make_wish_result: dict, original_wish_data: dict) -> dict:
    """
    Transform 5-stage Make a Wish response to frontend-expected format.
    
    Frontend expects:
    {
        "name": str,
        "version": str,
        "cost": float,
        "costTarget": {"min": float, "max": float},
        "ph": {"min": float, "max": float},
        "texture": str,
        "shelfLife": str,
        "phases": [...],
        "insights": [...],
        "warnings": [...],
        "compliance": {...}
    }
    """
    try:
        # Extract data from 5-stage result
        optimized = make_wish_result.get("optimized_formula", {})
        ingredient_selection = make_wish_result.get("ingredient_selection", {})
        cost_analysis = make_wish_result.get("cost_analysis", {})
        compliance = make_wish_result.get("compliance", {})
        
        # Get formula name
        formula_name = ingredient_selection.get("formula_name") or optimized.get("optimized_formula", {}).get("name") or f"{original_wish_data.get('productType', 'Formula').title()}"
        
        # Get cost
        total_cost = cost_analysis.get("raw_material_cost", {}).get("total_per_100g", 0) or optimized.get("optimized_formula", {}).get("estimated_cost_per_100g", 0)
        
        # Get pH
        target_ph = ingredient_selection.get("target_ph") or optimized.get("optimized_formula", {}).get("target_ph") or {"min": 5.0, "max": 6.0}
        
        # Get ingredients from optimized formula
        optimized_ingredients = optimized.get("ingredients", [])
        
        # Organize ingredients into phases
        phases_data = ingredient_selection.get("phases", [])
        phases = []
        used_ingredients = set()  # Track which ingredients have been assigned
        
        # First, try to match ingredients to phases from phases_data
        for phase_info in phases_data:
            phase_id = phase_info.get("id", "A")
            phase_name = phase_info.get("name", "Phase")
            
            # Get ingredients for this phase
            phase_ingredient_names = phase_info.get("ingredient_names", [])
            phase_ingredients = []
            
            for ing in optimized_ingredients:
                ing_name = ing.get("name", "")
                ing_inci = ing.get("inci", "")
                ing_key = f"{ing_name}|{ing_inci}"
                
                # Skip if already used
                if ing_key in used_ingredients:
                    continue
                
                # Match ingredient to phase by name or INCI
                if (ing_name in phase_ingredient_names or 
                    ing_inci in phase_ingredient_names or
                    any(name.lower() in ing_name.lower() or name.lower() in ing_inci.lower() 
                        for name in phase_ingredient_names)):
                    
                    phase_ingredients.append({
                        "name": ing_name,
                        "inci": ing_inci,
                        "percent": ing.get("percent", 0),
                        "cost": ing.get("cost_contribution", 0),
                        "function": ing.get("function", "Other"),
                        "hero": ing.get("is_hero", False)
                    })
                    used_ingredients.add(ing_key)
            
            # If no ingredients matched by name, try to find by phase ID
            if not phase_ingredients:
                for ing in optimized_ingredients:
                    ing_key = f"{ing.get('name', '')}|{ing.get('inci', '')}"
                    if ing_key in used_ingredients:
                        continue
                    if ing.get("phase") == phase_id:
                        phase_ingredients.append({
                            "name": ing.get("name", ""),
                            "inci": ing.get("inci", ""),
                            "percent": ing.get("percent", 0),
                            "cost": ing.get("cost_contribution", 0),
                            "function": ing.get("function", "Other"),
                            "hero": ing.get("is_hero", False)
                        })
                        used_ingredients.add(ing_key)
            
            if phase_ingredients:
                phases.append({
                    "id": phase_id,
                    "name": phase_name,
                    "temp": phase_info.get("process_temp", "room"),
                    "color": get_phase_color(phase_id),
                    "ingredients": phase_ingredients
                })
        
        # Add any remaining ingredients to appropriate phases
        for ing in optimized_ingredients:
            ing_key = f"{ing.get('name', '')}|{ing.get('inci', '')}"
            if ing_key not in used_ingredients:
                phase_id = ing.get("phase", "A")
                # Find existing phase or create new one
                phase_found = False
                for phase in phases:
                    if phase["id"] == phase_id:
                        phase["ingredients"].append({
                            "name": ing.get("name", ""),
                            "inci": ing.get("inci", ""),
                            "percent": ing.get("percent", 0),
                            "cost": ing.get("cost_contribution", 0),
                            "function": ing.get("function", "Other"),
                            "hero": ing.get("is_hero", False)
                        })
                        phase_found = True
                        used_ingredients.add(ing_key)
                        break
                
                if not phase_found:
                    # Create new phase for this ingredient
                    phases.append({
                        "id": phase_id,
                        "name": f"Phase {phase_id}",
                        "temp": "room",
                        "color": get_phase_color(phase_id),
                        "ingredients": [{
                            "name": ing.get("name", ""),
                            "inci": ing.get("inci", ""),
                            "percent": ing.get("percent", 0),
                            "cost": ing.get("cost_contribution", 0),
                            "function": ing.get("function", "Other"),
                            "hero": ing.get("is_hero", False)
                        }]
                    })
                    used_ingredients.add(ing_key)
        
        # If no phases created, create default phases from ingredients
        if not phases:
            # Group by phase from optimized ingredients
            phase_groups = {}
            for ing in optimized_ingredients:
                phase_id = ing.get("phase", "A")
                if phase_id not in phase_groups:
                    phase_groups[phase_id] = []
                phase_groups[phase_id].append({
                    "name": ing.get("name", ""),
                    "inci": ing.get("inci", ""),
                    "percent": ing.get("percent", 0),
                    "cost": ing.get("cost_contribution", 0),
                    "function": ing.get("function", "Other"),
                    "hero": ing.get("is_hero", False)
                })
            
            for phase_id, ingredients in phase_groups.items():
                phases.append({
                    "id": phase_id,
                    "name": f"Phase {phase_id}",
                    "temp": "room",
                    "color": get_phase_color(phase_id),
                    "ingredients": ingredients
                })
        
        # Get insights
        insights = []
        for insight in ingredient_selection.get("insights", []):
            insights.append({
                "icon": insight.get("icon", "💡"),
                "title": insight.get("title", ""),
                "text": insight.get("text", "")
            })
        for insight in optimized.get("insights", []):
            insights.append({
                "icon": insight.get("icon", "💡"),
                "title": insight.get("title", ""),
                "text": insight.get("text", "")
            })
        
        # Get warnings
        warnings = []
        for warning in ingredient_selection.get("warnings", []):
            warnings.append({
                "type": warning.get("severity", "info"),
                "text": warning.get("text", "")
            })
        for warning in optimized.get("warnings", []):
            warnings.append({
                "type": warning.get("severity", "info"),
                "text": warning.get("text", "")
            })
        
        # Get compliance
        compliance_data = {
            "silicone": True,  # Default
            "paraben": True,   # Default
            "vegan": False     # Default
        }
        
        # Check exclusions
        exclusions = original_wish_data.get("exclusions", [])
        exclusion_lower = [exc.lower() for exc in exclusions]
        
        if "silicone-free" in exclusion_lower:
            compliance_data["silicone"] = False
        if "paraben-free" in exclusion_lower:
            compliance_data["paraben"] = False
        if "vegan" in exclusion_lower:
            compliance_data["vegan"] = True
        
        # Override with compliance check results if available
        if compliance.get("overall_status"):
            bis_compliance = compliance.get("bis_compliance", {})
            # Check ingredient status for actual compliance
            ingredient_status = compliance.get("ingredient_status", [])
            for ing_status in ingredient_status:
                ing_name = ing_status.get("ingredient", "").lower()
                if "silicone" in ing_name or "dimethicone" in ing_name:
                    compliance_data["silicone"] = True
                if "paraben" in ing_name:
                    compliance_data["paraben"] = True
        
        # Get texture
        texture = original_wish_data.get("texture", "lightweight")
        from app.ai_ingredient_intelligence.logic.formula_generator import get_texture_description
        texture_desc = get_texture_description(texture)
        
        return {
            "name": formula_name,
            "version": "v1",
            "cost": total_cost,
            "costTarget": {
                "min": original_wish_data.get("costMin", 30),
                "max": original_wish_data.get("costMax", 60)
            },
            "ph": target_ph,
            "texture": texture_desc,
            "shelfLife": "12 months",
            "phases": phases,
            "insights": insights,
            "warnings": warnings,
            "compliance": compliance_data
        }
    
    except Exception as e:
        print(f"⚠️ Error transforming Make a Wish response: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to old method
        raise


def get_phase_color(phase_id: str) -> str:
    """Get color gradient for phase based on ID"""
    colors = {
        "A": "from-blue-500 to-blue-600",
        "B": "from-green-500 to-green-600",
        "C": "from-purple-500 to-purple-600",
        "D": "from-orange-500 to-orange-600",
        "E": "from-pink-500 to-pink-600"
    }
    return colors.get(phase_id, "from-slate-500 to-slate-600")


@router.post("/generate", response_model=GenerateFormulaResponse)
async def generate_formula_endpoint(
    request: CreateWishRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
        
        # Generate formula using 5-stage Make a Wish pipeline
        formula = None
        try:
            # Transform wish_data to match Make a Wish format
            make_wish_data = {
                "category": wish_data.get("category", "skincare"),
                "productType": wish_data.get("productType", "serum"),
                "benefits": wish_data.get("benefits", []),
                "exclusions": wish_data.get("exclusions", []),
                "heroIngredients": wish_data.get("heroIngredients", []),
                "costMin": wish_data.get("costMin", 30),
                "costMax": wish_data.get("costMax", 60),
                "texture": wish_data.get("texture", "lightweight"),
                "claims": wish_data.get("preferences", {}).get("claims", []),
                "targetAudience": wish_data.get("targetAudience", []),
                "additionalNotes": wish_data.get("notes", "")
            }
            
            # Generate using 5-stage pipeline
            make_wish_result = await generate_make_wish_formula(make_wish_data)
            
            # Transform 5-stage response to frontend format
            formula = transform_make_wish_to_frontend_format(make_wish_result, wish_data)
            print("✅ Used 5-stage Make a Wish pipeline")
        
        except Exception as make_wish_error:
            print(f"⚠️ 5-stage pipeline failed, falling back to hybrid approach: {make_wish_error}")
            import traceback
            traceback.print_exc()
            # Fallback to old hybrid approach
            formula = await generate_formula(wish_data)
            print("✅ Used hybrid approach (fallback)")
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
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Save wish history with formula data (user-specific)
    
    HISTORY FUNCTIONALITY:
    - All formula generation operations are automatically saved to user's history
    - History is user-specific and isolated by user_id
    - Stores both the original wish data and the generated formula result
    - Name and notes can be used for organization and categorization
    - History items can be searched by name or notes
    - History persists across sessions and page refreshes
    - Users can revisit previously generated formulas
    
    Request body:
    {
        "name": "Formula Name",
        "wish_data": {...},  # Original wish data
        "formula_result": {...},  # Generated formula
        "notes": "Optional notes"
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        print(f"📝 Save wish history request received")
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
        
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
        if not user_id_value:
            print("❌ User ID not found in JWT token")
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
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
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get wish history for a user
    
    HISTORY FUNCTIONALITY:
    - Returns all formula generation history items for the authenticated user
    - Each item contains the original wish data and the generated formula result
    - Supports pagination with limit and skip parameters
    - Search works across name and notes fields
    - History items are sorted by creation date (newest first)
    - Users can access previously generated formulas and their original requirements
    
    Query params:
    - search: Optional search term (searches name and notes)
    - limit: Number of results (default 50)
    - skip: Number of results to skip (default 0)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
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
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Delete a wish history item
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
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

