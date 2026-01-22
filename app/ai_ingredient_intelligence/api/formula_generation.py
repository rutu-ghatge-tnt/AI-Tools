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
    GenerateFormulaResponse,
    UpdateWishHistoryRequest,
    UpdateWishHistoryResponse,
    DeleteWishHistoryResponse
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


def filter_original_formulation_references(items: list, text_fields: list = ["text", "title"]) -> list:
    """
    Filter out items that reference 'original formulation' or similar terms.
    
    Args:
        items: List of dicts (insights or warnings)
        text_fields: List of field names to check for references
        
    Returns:
        Filtered list without original formulation references
    """
    original_formulation_keywords = [
        "original formulation", "original formula", "previous formulation", 
        "previous formula", "provided formulation", "initial formulation"
    ]
    
    filtered = []
    for item in items:
        # Check all specified text fields
        item_text = " ".join([
            str(item.get(field, "")).lower() 
            for field in text_fields 
            if field in item
        ])
        
        # Skip if mentions original formulation
        if not any(keyword in item_text for keyword in original_formulation_keywords):
            filtered.append(item)
    
    return filtered


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
        
        # Get insights - filter out any that reference "original formulation"
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
        # Filter out original formulation references
        insights = filter_original_formulation_references(insights, ["text", "title"])
        
        # Get warnings - filter out any that reference "original formulation"
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
        # Filter out original formulation references
        warnings = filter_original_formulation_references(warnings, ["text"])
        
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
    
    AUTO-SAVE: Results are automatically saved to wish history if user is authenticated.
    Provide optional "name" and "tag" in request to customize the saved history item.
    
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
        "notes": "Additional requirements",
        "name": "Formula Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "history_id": "existing_history_id" (optional, to update existing history)
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
        "compliance": {...},
        "history_id": "..." (if auto-saved)
    }
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/generate")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"{'='*80}\n")
    
    start_time = time.time()
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip() if request.name else ""
    tag = request.tag
    notes = request.notes  # Already exists in CreateWishRequest
    provided_history_id = request.history_id
    history_id = None
    
    # Validate name is provided if auto-save is enabled (user_id is present) and no existing history_id
    if user_id_value and not provided_history_id and not name:
        raise HTTPException(status_code=400, detail="name is required for auto-save")
    
    # Validate history_id if provided
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await wish_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_item:
                    history_id = provided_history_id
                    print(f"[AUTO-SAVE] Using existing history_id: {history_id}")
                else:
                    print(f"[AUTO-SAVE] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, creating new one")
            else:
                print(f"[AUTO-SAVE] Warning: Invalid history_id format: {provided_history_id}, creating new one")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Error validating history_id: {e}, creating new one")
    
    try:
        # Convert Pydantic model to dict (exclude autosave fields from wish_data)
        wish_data = request.model_dump(exclude={"name", "tag", "history_id"})
        print(f"[DEBUG] Wish data keys: {list(wish_data.keys())}")
        print(f"[DEBUG] Product type: {wish_data.get('productType')}")
        print(f"[DEBUG] Benefits: {wish_data.get('benefits')}")
        print(f"[DEBUG] Exclusions: {wish_data.get('exclusions')}")
        print(f"[DEBUG] Hero ingredients: {wish_data.get('heroIngredients')}")
        print(f"[DEBUG] Cost range: {wish_data.get('costMin')} - {wish_data.get('costMax')}")
        
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
        
        # Create a unique identifier for the wish data to check for duplicates
        import json
        wish_data_for_comparison = {
            "category": wish_data.get("category", "skincare"),
            "productType": wish_data.get("productType"),
            "benefits": sorted(wish_data.get("benefits", [])),
            "exclusions": sorted(wish_data.get("exclusions", [])),
            "heroIngredients": sorted(wish_data.get("heroIngredients", [])),
            "costMin": wish_data.get("costMin"),
            "costMax": wish_data.get("costMax"),
            "texture": wish_data.get("texture")
        }
        wish_data_hash = json.dumps(wish_data_for_comparison, sort_keys=True)
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided and no existing history_id
        if user_id_value and not history_id:
            try:
                # Check if a history item with the same wish data already exists for this user
                existing_history_item = await wish_history_col.find_one({
                    "user_id": user_id_value,
                    "wish_data_hash": wish_data_hash
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same wish data, reusing history_id: {history_id}")
                else:
                    # Name is required - already validated above
                    # Truncate if too long
                    if len(name) > 100:
                        name = name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
                        "tag": tag,
                        "notes": notes,
                        "wish_data": wish_data,
                        "wish_data_hash": wish_data_hash,
                        "status": "in_progress",
                        "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                    }
                    result = await wish_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                # Continue with generation even if saving fails
        
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
        print(f"[DEBUG] ✅ Formula generated in {processing_time:.2f}s")
        print(f"[DEBUG]    Cost: ₹{formula.get('cost', 0)}/100g")
        print(f"[DEBUG]    Phases: {len(formula.get('phases', []))}")
        print(f"[DEBUG]    Ingredients: {sum(len(p.get('ingredients', [])) for p in formula.get('phases', []))}")
        
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
        
        # 🔹 Auto-save: Update history with "completed" status and formula_result
        if user_id_value and history_id:
            try:
                update_doc = {
                    "formula_result": formula,
                    "status": "completed",
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                
                await wish_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with completed status and formula result")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        elif user_id_value and name:
            # Create new history item if we didn't have history_id but have name
            try:
                if len(name) > 100:
                    name = name[:100]
                
                history_doc = {
                    "user_id": user_id_value,
                    "name": name,
                    "tag": tag,
                    "notes": notes,
                    "wish_data": wish_data,
                    "wish_data_hash": wish_data_hash,
                    "formula_result": formula,
                    "status": "completed",
                    "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                result_insert = await wish_history_col.insert_one(history_doc)
                history_id = str(result_insert.inserted_id)
                print(f"[AUTO-SAVE] Created new history {history_id} with completed status and formula result")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to create history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        # Add history_id to formula if available
        if history_id:
            formula["history_id"] = history_id
        
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
    ⚠️ DEPRECATED ENDPOINT - This endpoint is no longer needed.
    
    Wish history is now automatically saved by the /generate endpoints:
    - POST /api/formula/generate - Auto-saves when name is provided
    - POST /api/make-wish/generate - Auto-saves when name is provided
    
    The generate endpoints return a history_id in the response which can be used
    to retrieve the saved history later.
    
    This endpoint is kept for backward compatibility but returns an error.
    Please update your frontend to use the autosave feature instead.
    """
    print(f"\n{'='*80}")
    print(f"[DEPRECATED] 🚀 API CALL: /api/formula/save-wish-history")
    print(f"[DEPRECATED] This endpoint is deprecated. Use autosave in /generate endpoints instead.")
    print(f"{'='*80}\n")
    
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    print(f"[DEPRECATED] Called by user: {user_id_value}")
    
    raise HTTPException(
        status_code=410,  # 410 Gone - indicates the resource is no longer available
        detail={
            "error": "Endpoint deprecated",
            "message": "The /save-wish-history endpoint is deprecated. Wish history is now automatically saved by the /generate endpoints.",
            "migration_guide": {
                "old_way": "Call /generate, then call /save-wish-history with the result",
                "new_way": "Call /generate with 'name' field in request body. The endpoint will auto-save and return 'history_id' in the response.",
                "endpoints": [
                    "POST /api/formula/generate - Include 'name' field in CreateWishRequest",
                    "POST /api/make-wish/generate - Include 'name' field in MakeWishRequest"
                ],
                "example": {
                    "request": {
                        "productType": "serum",
                        "benefits": ["Brightening"],
                        "name": "My Formula Name"  # Required for autosave
                    },
                    "response": {
                        "...": "formula data",
                        "history_id": "507f1f77bcf86cd799439011"  # MongoDB ObjectId
                    }
                }
            }
        }
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
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Query params - search: {search}, limit: {limit}, skip: {skip}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
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
        
        # Get items - only get summary fields (exclude large fields)
        cursor = wish_history_col.find(
            query,
            {
                "_id": 1,
                "name": 1,
                "notes": 1,
                "created_at": 1,
                "tag": 1,
                "status": 1,
                "wish_text": 1,
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        items = []
        async for doc in cursor:
            # Create summary item (exclude large fields)
            # wish_data = doc.get("wish_data", {})
            # formula_result = doc.get("formula_result", {})
            
            items.append({
                "id": str(doc["_id"]),
                # "user_id": doc.get("user_id"),
                "name": doc.get("name", ""),
                "tag": doc.get("tag", ""),
                "wish_text": doc.get("wish_text", ""),
                "status": doc.get("status", ""),
                "notes": doc.get("notes", ""),
                "created_at": doc.get("created_at", ""),
                # "formula_data": doc.get("formula_data", None),
                # "has_wish_data": wish_data is not None and bool(wish_data),
                # "has_formula_result": formula_result is not None and bool(formula_result)
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


@router.get("/wish-history/{history_id}/details")
async def get_wish_history_detail(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get full details of a specific wish history item (includes all large fields)
    
    This endpoint returns the complete data including:
    - Full wish_data (large Dict)
    - Full formula_result (large Dict)
    - All other fields
    
    Use this endpoint when you need to display the full wish data or formula result.
    The list endpoint (/wish-history) only returns summaries.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history/{history_id}/details")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
            )
        
        # Validate ObjectId - check if it's a valid MongoDB ObjectId format
        # MongoDB ObjectIds are 24-character hex strings (no dashes)
        # UUIDs have dashes and are 36 characters, so we can detect them
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        if uuid_pattern.match(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format: UUID detected. The save-wish-history endpoint is disabled and returns dummy UUIDs. Please use the history_id returned from the /generate endpoint (which auto-saves and returns a MongoDB ObjectId). Received UUID: {history_id}"
            )
        
        if not ObjectId.is_valid(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format. Expected MongoDB ObjectId (24 hex characters), got: {history_id[:50]}"
            )
        
        # Fetch full item (including large fields)
        doc = await wish_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not doc:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Return full data - handle both old and new data gracefully
        return {
            "id": str(doc["_id"]),
            "user_id": doc.get("user_id"),
            "name": doc.get("name", ""),
            "notes": doc.get("notes", ""),
            "wish_text": doc.get("wish_text", ""),
            "tag": doc.get("tag", ""),
            "parsed_data": doc.get("parsed_data", None),
            "complexity": doc.get("complexity", ""),
            "formula_id": doc.get("formula_id", ""),
            "created_at": doc.get("created_at", ""),
            "formula_data": doc.get("formula_data", None),
            # Legacy fields - optional for backward compatibility
            "wish_data": doc.get("wish_data", None),  # Changed from {} to None to handle missing gracefully
            "formula_result": doc.get("formula_result", None)  # Changed from {} to None to handle missing gracefully
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting wish history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get wish history detail: {str(e)}"
        )


@router.patch("/wish-history/{history_id}", response_model=UpdateWishHistoryResponse)
async def update_wish_history(
    history_id: str,
    payload: UpdateWishHistoryRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update wish history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating formula results, wish data, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the wish history item
    - notes: Update user notes
    - tag: Update tag for categorization
    - wish_data: Update wish data (for regeneration)
    - formula_result: Update formula result (for regeneration)
    - status: Update status (e.g., 'in_progress', 'completed')
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history/{history_id} (PATCH)")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"[DEBUG] Payload: {payload.model_dump(exclude_none=True)}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
            )
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Build update document - only include fields that are provided (not None)
        update_doc = payload.model_dump(exclude_none=True)
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Only update if it belongs to the user
        result = await wish_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to update it"
            )
        
        return UpdateWishHistoryResponse(
            success=True,
            message="Wish history updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update wish history: {str(e)}"
        )


@router.delete("/wish-history/{history_id}", response_model=DeleteWishHistoryResponse)
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
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history/{history_id} (DELETE)")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
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
        
        return DeleteWishHistoryResponse(
            success=True,
            message="History item deleted successfully"
        )
        
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

