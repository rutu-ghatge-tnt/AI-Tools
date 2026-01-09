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
from bson import ObjectId
import time

# Import authentication - Using JWT tokens
from app.ai_ingredient_intelligence.auth import verify_jwt_token

from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    generate_formula_from_wish
)
from app.ai_ingredient_intelligence.logic.make_wish_rules_engine import (
    get_rules_engine,
    ValidationSeverity
)
from app.ai_ingredient_intelligence.models.schemas import (
    MakeWishRequest,
    MakeWishResponse
)
from app.ai_ingredient_intelligence.db.collections import wish_history_col

router = APIRouter(prefix="/make-wish", tags=["Make a Wish"])


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-inspiration-board")
async def export_make_wish_to_board(
    request: dict,
    user_id: str = Query(..., description="User ID"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Export make a wish formulations to inspiration board"""
    try:
        board_id = request.get("board_id")
        history_ids = request.get("history_ids", [])
        
        if not board_id:
            raise HTTPException(status_code=400, detail="Board ID is required")
        
        if not history_ids:
            raise HTTPException(status_code=400, detail="At least one history ID is required")
        
        # Use the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
            ExportToBoardRequest, ExportItemRequest
        )
        from app.ai_ingredient_intelligence.logic.board_manager import get_board_detail
        
        # Verify board exists and belongs to user
        board_detail = await get_board_detail(user_id, board_id)
        if not board_detail:
            raise HTTPException(status_code=404, detail="Board not found or access denied")
        
        # Create export request
        export_request = ExportToBoardRequest(
            board_id=board_id,
            exports=[
                ExportItemRequest(
                    feature_type="make_wish",
                    history_ids=history_ids
                )
            ]
        )
        
        # Call the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.api.inspiration_boards import export_to_board_endpoint
        result = await export_to_board_endpoint(export_request, user_id, current_user)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR exporting make a wish to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MAIN ENDPOINTS
# ============================================================================


@router.post("/generate", response_model=MakeWishResponse)
async def generate_make_wish_formula(
    request: MakeWishRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate a cosmetic formulation using the complete 5-stage "Make a Wish" AI pipeline.
    
    AUTO-SAVE: Results are automatically saved to wish history if user is authenticated.
    Provide optional "name" and "tag" in request to customize the saved history item.
    
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
        "additionalNotes": "Additional requirements",
        "name": "Formula Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "history_id": "existing_history_id" (optional, to update existing history)
    }
    
    RESPONSE:
    Complete formula with:
    - Ingredient selection
    - Optimized percentages
    - Manufacturing process
    - Cost analysis
    - Compliance check
    - history_id (if auto-saved)
    """
    start_time = time.time()
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip() if request.name else ""
    tag = request.tag
    notes = request.notes  # This is the notes field from MakeWishRequest (for history)
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
        wish_data = request.model_dump(exclude={"name", "tag", "notes", "history_id"})
        
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
        
        # Validate using rules engine
        rules_engine = get_rules_engine()
        can_proceed, validation_results, fixed_wish_data = rules_engine.validate_wish_data(wish_data)
        
        if not can_proceed:
            blocking_errors = [r for r in validation_results if r.severity == ValidationSeverity.BLOCK]
            error_messages = [r.message for r in blocking_errors]
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed: {'; '.join(error_messages)}"
            )
        
        # Use fixed wish data (with auto-selections applied)
        wish_data = fixed_wish_data
        
        # Log validation warnings
        warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARN]
        if warnings:
            print(f"⚠️ Validation warnings: {len(warnings)}")
            for warning in warnings:
                print(f"   - {warning.message}")
        
        print(f"📝 Generating Make a Wish formula...")
        print(f"   Category: {wish_data['category']}")
        print(f"   Product Type: {wish_data['productType']}")
        print(f"   Benefits: {', '.join(wish_data['benefits'])}")
        print(f"   Exclusions: {', '.join(wish_data.get('exclusions', []))}")
        print(f"   Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
        print(f"   Cost Range: ₹{wish_data['costMin']} - ₹{wish_data['costMax']}/100g")
        
        # Create a unique identifier for the wish data to check for duplicates
        # Use a combination of key fields to identify similar wishes
        import json
        wish_data_for_comparison = {
            "category": wish_data.get("category"),
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
        
        # 🔹 Auto-save: Update history with "completed" status and formula_result
        if user_id_value and history_id:
            try:
                update_doc = {
                    "formula_result": result,
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
                    "formula_result": result,
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
        
        # Add history_id to result if available
        if history_id:
            result["history_id"] = history_id
        
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

