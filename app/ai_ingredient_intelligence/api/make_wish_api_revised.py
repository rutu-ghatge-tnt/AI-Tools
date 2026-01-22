"""
Revised Make A Wish API Endpoints (January 2025)
================================================

This module implements the new API endpoints for the revised Make A Wish flow:
- POST /parse-wish (Stage 1)
- POST /generate (Stage 2 - revised) 
- POST /get-alternatives (Stage 3)
- POST /edit-formula (Stage 4)
- POST /request-quote (Stage 5)
- POST /get-this-made (Stage 6)

The new flow features natural language parsing, complexity selection, 
ingredient alternatives, formula editing, and commercialization.
"""

from fastapi import APIRouter, HTTPException, Header, Depends, Query, BackgroundTasks
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time
import json
import uuid

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token

# Import revised schemas
from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import (
    ParseWishRequest, ParseWishResponse,
    MakeWishRequestRevised, MakeWishResponseRevised,
    GetAlternativesRequest, GetAlternativesResponse,
    EditFormulaRequest, EditFormulaResponse,
    RequestQuoteRequest, RequestQuoteResponse,
    GetThisMadeRequest, GetThisMadeResponse
)

# Import original schemas for backward compatibility
from app.ai_ingredient_intelligence.models.schemas import (
    MakeWishRequest, MakeWishResponse
)

# Import configuration
from app.ai_ingredient_intelligence.logic.make_wish_config import (
    get_complexity_config, get_texture_for_product_type, 
    get_alternatives_for_ingredient, check_compatibility,
    generate_queue_number, EDIT_RULES
)

# Import AI prompts
from app.ai_ingredient_intelligence.logic.make_wish_prompts_revised import (
    PARSE_WISH_PROMPT, INGREDIENT_SELECTION_COMPLEXITY_PROMPT,
    INSIGHTS_GENERATION_PROMPT, ALTERNATIVES_ANALYSIS_PROMPT,
    format_ingredients_list, format_alternatives_list
)

# Import existing generator for backward compatibility
from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    call_ai_with_claude, generate_formula_from_wish
)

# Import database collections
from app.ai_ingredient_intelligence.db.collections import (
    wish_history_col, commercialization_requests_col, 
    formula_versions_col, quotes_col, ingredient_alternatives_cache_col
)

router = APIRouter(prefix="/make-wish", tags=["Make a Wish - Revised"])


# ============================================================================
# STAGE 1: PARSE WISH ENDPOINT
# ============================================================================

@router.post("/parse-wish", response_model=ParseWishResponse)
async def parse_natural_language_wish(
    request: ParseWishRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Parse natural language wish into structured data.
    
    This endpoint analyzes user's natural language description and extracts:
    - Category (skincare/haircare)
    - Product type with confidence
    - Detected ingredients
    - Benefits and exclusions
    - Auto-detected texture
    - Compatibility issues
    - Clarification questions if needed
    """
    start_time = time.time()
    
    try:
        # Validate minimum length
        if len(request.wish_text.strip()) < 30:
            raise HTTPException(
                status_code=400,
                detail="Wish text must be at least 30 characters long"
            )
        
        print(f"🔍 Parsing natural language wish...")
        print(f"   Wish: {request.wish_text[:100]}...")
        
        # Call AI to parse the wish
        try:
            parsed_result = await call_ai_with_claude(
                system_prompt="You are a cosmetic formulation expert AI. Analyze natural language wishes and extract structured information.",
                user_prompt=PARSE_WISH_PROMPT.format(wish_text=request.wish_text),
                prompt_type="parse_wish"
            )
            
            # Debug: Log the AI response
            print(f"🤖 AI Response received:")
            print(f"   Type: {type(parsed_result)}")
            if isinstance(parsed_result, dict):
                print(f"   Keys: {list(parsed_result.keys())}")
                if 'compatibility_issues' in parsed_result:
                    print(f"   Compatibility Issues: {len(parsed_result['compatibility_issues'])}")
                    if parsed_result['compatibility_issues']:
                        first_issue = parsed_result['compatibility_issues'][0]
                        print(f"   First Issue Keys: {list(first_issue.keys())}")
            
        except Exception as ai_error:
            print(f"❌ AI parsing error: {ai_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Error parsing wish: {str(ai_error)}"
            )
        
        # Validate AI response structure
        if not parsed_result or not isinstance(parsed_result, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid parsing result from AI"
            )
        
        # Auto-detect texture if not provided
        product_type_id = parsed_result.get("product_type", {}).get("id", "serum")
        auto_texture = get_texture_for_product_type(product_type_id)
        
        # Update parsed data with auto-detected texture
        if "auto_texture" not in parsed_result:
            parsed_result["auto_texture"] = auto_texture
        
        # Check for additional compatibility issues
        detected_ingredients = [ing.get("name", "") for ing in parsed_result.get("detected_ingredients", [])]
        compatibility_issues = parsed_result.get("compatibility_issues", [])
        
        # Add any additional compatibility checks
        additional_issues = check_compatibility(detected_ingredients)
        for issue in additional_issues:
            if issue not in compatibility_issues:
                compatibility_issues.append(issue)
        
        parsed_result["compatibility_issues"] = compatibility_issues
        
        # Transform needs_clarification to ensure proper format
        needs_clarification = parsed_result.get("needs_clarification", [])
        if needs_clarification:
            transformed_clarifications = []
            for item in needs_clarification:
                if isinstance(item, str):
                    # Convert string to dictionary format
                    transformed_clarifications.append({
                        "question": item,
                        "reason": f"Clarification needed for: {item}"
                    })
                elif isinstance(item, dict):
                    # Already in correct format
                    transformed_clarifications.append(item)
                else:
                    # Skip invalid items
                    continue
            
            parsed_result["needs_clarification"] = transformed_clarifications
        
        processing_time = time.time() - start_time
        print(f"✅ Wish parsed in {processing_time:.2f}s")
        print(f"   Category: {parsed_result.get('category', 'unknown')}")
        print(f"   Product Type: {parsed_result.get('product_type', {}).get('name', 'unknown')}")
        print(f"   Ingredients Detected: {len(parsed_result.get('detected_ingredients', []))}")
        print(f"   Compatibility Issues: {len(compatibility_issues)}")
        
        return ParseWishResponse(
            success=True,
            parsed_data=parsed_result,
            compatibility_issues=compatibility_issues
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error parsing wish: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# STAGE 2: REVISED GENERATE ENDPOINT
# ============================================================================

@router.post("/generate-revised", response_model=MakeWishResponseRevised)
async def generate_formula_revised(
    request: MakeWishRequestRevised,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Generate formula using revised flow with complexity selection.
    
    This endpoint creates a formula based on:
    - Parsed natural language wish
    - Selected complexity level (minimalist/classic/luxe)
    - Auto-detected texture
    - Enhanced insights generation
    """
    start_time = time.time()
    
    # Extract user info for auto-save
    user_id = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip()
    history_id = None
    
    # Validate required fields
    if not name:
        raise HTTPException(
            status_code=400,
            detail="name is required for formula generation"
        )
    
    if request.complexity not in ["minimalist", "classic", "luxe"]:
        raise HTTPException(
            status_code=400,
            detail="complexity must be one of: minimalist, classic, luxe"
        )
    
    try:
        print(f"🚀 Generating revised formula...")
        print(f"   Complexity: {request.complexity}")
        print(f"   Product Type: {request.parsed_data.product_type.name}")
        
        # Get complexity configuration
        complexity_config = get_complexity_config(request.complexity)
        if not complexity_config:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid complexity level: {request.complexity}"
            )
        
        # Stage 1: Ingredient Selection with Complexity
        print("📋 Stage 1: Ingredient Selection with Complexity...")
        
        # Prepare ingredients list for prompt
        detected_ingredients = request.parsed_data.detected_ingredients
        
        # Generate ingredient selection prompt
        selection_prompt = INGREDIENT_SELECTION_COMPLEXITY_PROMPT.format(
            wish_text=request.wish_text,
            category=request.parsed_data.category,
            product_type=request.parsed_data.product_type.name,
            benefits=", ".join(request.parsed_data.detected_benefits),
            exclusions=", ".join(request.parsed_data.detected_exclusions),
            skin_type=", ".join(request.parsed_data.detected_skin_types),
            detected_ingredients=[ing.name for ing in detected_ingredients],
            texture=request.parsed_data.auto_texture.label,
            complexity=request.complexity,
            max_ingredients=complexity_config["max_ingredients"],
            active_slots=complexity_config["active_slots"],
            include_sensorials=complexity_config["include_sensorials"],
            base_ingredients=", ".join(complexity_config["base_ingredients"]),
            cost_multiplier=complexity_config["cost_target_multiplier"]
        )
        
        # Call AI for ingredient selection
        selected_ingredients = await call_ai_with_claude(
            system_prompt="You are a cosmetic formulation expert. Select ingredients based on user requirements and complexity constraints.",
            user_prompt=selection_prompt,
            prompt_type="ingredient_selection_complexity"
        )
        
        if not selected_ingredients or "selected_ingredients" not in selected_ingredients:
            raise HTTPException(
                status_code=500,
                detail="Failed to select ingredients"
            )
        
        print(f"✅ Selected {len(selected_ingredients['selected_ingredients'])} ingredients")
        
        # Stage 2: Formula Optimization
        print("🔧 Stage 2: Formula Optimization...")
        
        # Simplified optimization prompt
        optimization_prompt = f"""You are a cosmetic formulation expert. Optimize ingredient percentages for a balanced formula.

## FORMULA REQUIREMENTS
- Product: {request.parsed_data.product_type.name} ({request.parsed_data.category})
- Texture Target: {request.parsed_data.auto_texture.label}
- Complexity: {request.complexity}
- Total Must Equal: 100.00%

## SELECTED INGREDIENTS
{format_ingredients_list(selected_ingredients['selected_ingredients'])}

## OPTIMIZATION RULES

1. **PERCENTAGE ALLOCATION**
   - Total MUST equal exactly 100.00%
   - Water/Aqua typically makes up 60-80% for water-based products
   - Round all percentages to 2 decimal places

2. **ACTIVE OPTIMIZATION**
   - Hero ingredients at efficacious levels within their ranges
   - Consider synergy between multiple actives
   - Stay within safe usage limits

3. **TEXTURE ACHIEVEMENT**
   - "{request.parsed_data.auto_texture.label}" texture requires appropriate thickener levels
   - Adjust emollients for cream vs gel textures
   - Consider sensory modifiers for luxe products

4. **STABILITY & SAFETY**
   - Preservative at effective level (usually 0.8-1.2%)
   - pH adjusters as needed (usually 0.1-0.5%)
   - Antioxidants for oxidation protection

5. **COST BALANCING**
   - Higher percentages of expensive ingredients increase cost
   - Balance efficacy with cost targets for {request.complexity} complexity

## PHASE ORGANIZATION
- Phase A: Water phase (water-soluble ingredients)
- Phase B: Oil phase (oil-soluble ingredients)  
- Phase C: Cool down phase (heat-sensitive ingredients)

## RESPONSE FORMAT (JSON):
{{
    "optimized_formula": {{
        "name": "Formula Name",
        "complexity": "{request.complexity}",
        "total_percentage": 100.0,
        "target_ph": {{"min": 5.0, "max": 6.0}},
        "texture_achieved": "texture_description"
    }},
    "ingredients": [
        {{
            "id": "ingredient_id",
            "name": "Ingredient Name",
            "inci": "INCI Name",
            "percentage": "X.XX%",
            "phase": "A|B|C",
            "function": "Purpose",
            "is_hero": true|false,
            "is_base": true|false,
            "cost_contribution": "₹X.XX per 100g"
        }}
    ],
    "phase_summary": [
        {{
            "phase": "A",
            "name": "Water Phase",
            "total_percent": X.XX,
            "temperature": "70-75°C"
        }}
    ],
    "optimization_notes": [
        "Key decisions made during optimization"
    ],
    "cost_estimate": {{
        "raw_material_cost_per_100g": ₹XXX,
        "cost_category": "low|medium|high",
        "meets_complexity_target": true|false
    }}
}}

Ensure percentages are realistic and formula is manufacturable. Return ONLY the JSON object above, no markdown formatting."""
        
        optimized_formula = await call_ai_with_claude(
            system_prompt="You are a cosmetic formulation expert. Optimize ingredient percentages for balanced, stable formulas.",
            user_prompt=optimization_prompt,
            prompt_type="formula_optimization_revised"
        )
        
        # Debug: Log the actual structure returned
        print(f"🔍 Optimized formula structure: {type(optimized_formula)}")
        if isinstance(optimized_formula, dict):
            print(f"   Keys: {list(optimized_formula.keys())}")
        
        if not optimized_formula:
            raise HTTPException(
                status_code=500,
                detail="Failed to optimize formula - empty response"
            )
        
        # Check for multiple possible response formats
        has_ingredients = "ingredients" in optimized_formula
        has_optimized_formula = "optimized_formula" in optimized_formula
        has_formula = "formula" in optimized_formula
        
        if not has_ingredients and not has_optimized_formula and not has_formula:
            print(f"❌ Missing expected keys. Available keys: {list(optimized_formula.keys())}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to optimize formula - unexpected response format. Expected 'ingredients', 'optimized_formula', or 'formula' keys"
            )
        
        print(f"✅ Optimized formula: {optimized_formula['optimized_formula']['total_percentage']}%")
        
        # Stage 3: Manufacturing Process (reuse existing)
        print("🏭 Stage 3: Manufacturing Process...")
        from app.ai_ingredient_intelligence.logic.make_wish_generator import generate_manufacturing_prompt
        manufacturing_prompt = generate_manufacturing_prompt(optimized_formula)
        manufacturing = await call_ai_with_claude(
            system_prompt="Generate detailed manufacturing instructions for cosmetic formulations.",
            user_prompt=manufacturing_prompt,
            prompt_type="manufacturing_process"
        )
        
        # Stage 4: Compliance Check (reuse existing)
        print("✅ Stage 4: Compliance Check...")
        from app.ai_ingredient_intelligence.logic.make_wish_generator import generate_compliance_prompt
        compliance_prompt = generate_compliance_prompt(optimized_formula)
        compliance = await call_ai_with_claude(
            system_prompt="Check regulatory compliance for cosmetic formulations.",
            user_prompt=compliance_prompt,
            prompt_type="compliance_check"
        )
        
        # Stage 5: Insights Generation (NEW)
        print("💡 Stage 5: Insights Generation...")
        
        # Get ingredients from the correct nested structure
        ingredients_list = []
        if "ingredients" in optimized_formula:
            ingredients_list = optimized_formula["ingredients"]
        elif "formula" in optimized_formula and "ingredients" in optimized_formula["formula"]:
            ingredients_list = optimized_formula["formula"]["ingredients"]
        
        key_ingredients = [ing for ing in ingredients_list if ing.get("is_hero", False)]
        
        insights_prompt = INSIGHTS_GENERATION_PROMPT.format(
            formula_name=optimized_formula["optimized_formula"]["name"],
            product_type=request.parsed_data.product_type.name,
            complexity=request.complexity,
            key_ingredients=", ".join([ing["name"] for ing in key_ingredients]),
            benefits=", ".join(request.parsed_data.detected_benefits),
            target_audience=", ".join(request.parsed_data.detected_skin_types) or "General"
        )
        
        insights = await call_ai_with_claude(
            system_prompt="You are a cosmetic formulation expert and marketing strategist. Generate comprehensive insights for cosmetic formulas.",
            user_prompt=insights_prompt,
            prompt_type="insights_generation"
        )
        
        # Generate unique IDs
        formula_id = str(uuid.uuid4())
        if not history_id:
            optimized_formula["insights"] = insights
            optimized_formula["manufacturing"] = manufacturing
            optimized_formula["compliance"] = compliance
            # optimized_formula["complexity_config"] = complexity_config

            # Create new history record
            try:
                history_doc = {
                    "user_id": user_id,
                    "name": name,
                    "tag": request.tag,
                    "notes": request.notes,
                    "wish_text": request.wish_text,
                    "parsed_data": request.parsed_data.model_dump(),
                    "complexity": request.complexity,
                    "formula_id": formula_id,
                    "formula_data": optimized_formula,
                    # "insights": insights,
                    "status": "completed",
                    "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                result = await wish_history_col.insert_one(history_doc)
                history_id = str(result.inserted_id)
                print(f"[AUTO-SAVE] Created history record: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save history: {e}")
        
        # Build response
        response_data = {
            "success": True,
            "formula_id": formula_id,
            "history_id": history_id,
            "formula": {
                "name": optimized_formula["optimized_formula"]["name"],
                "complexity": request.complexity,
                "complexity_info": {
                    "id": request.complexity,
                    "name": complexity_config["name"],
                    "emoji": complexity_config["emoji"],
                    "description": complexity_config["description"],
                    "highlights": complexity_config["highlights"],
                    "marketing_angle": complexity_config["marketing_angle"]
                },
                "product_type": request.parsed_data.product_type.model_dump(),
                "texture": request.parsed_data.auto_texture.model_dump(),
                "phases": [],  # TODO: Convert from optimized format
                "hero_ingredients": [],  # TODO: Convert from optimized format
                "total_ingredients": len(ingredients_list),
                "total_hero_actives": len(key_ingredients),
                "available_claims": request.claims or [],
                "exclusions_met": request.parsed_data.detected_exclusions
            },
            "insights": insights,
            "manufacturing": manufacturing,
            "compliance": compliance
        }
        
        processing_time = time.time() - start_time
        print(f"✅ Revised formula generated in {processing_time:.2f}s")
        
        return MakeWishResponseRevised(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error generating revised formula: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# STAGE 3: GET ALTERNATIVES ENDPOINT
# ============================================================================

@router.post("/get-alternatives", response_model=GetAlternativesResponse)
async def get_ingredient_alternatives(
    request: GetAlternativesRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get alternative ingredients for a specific hero ingredient.
    
    This endpoint provides alternatives for ingredients with:
    - Detailed descriptions and benefits
    - Cost impact analysis
    - Complexity compatibility
    - Usage considerations
    """
    try:
        print(f"🔄 Getting alternatives for: {request.ingredient_name}")
        
        # Get alternatives from database
        alternatives_data = get_alternatives_for_ingredient(request.ingredient_name)
        
        if not alternatives_data:
            raise HTTPException(
                status_code=404,
                detail=f"No alternatives found for {request.ingredient_name}"
            )
        
        # Filter alternatives by complexity
        all_alternatives = alternatives_data.get("variants", [])
        compatible_alternatives = [
            alt for alt in all_alternatives 
            if request.complexity in alt.get("complexity", [])
        ]
        
        # Find current variant
        current_variant = None
        if request.current_variant:
            for alt in all_alternatives:
                if alt.get("name") == request.current_variant or alt.get("inci") == request.current_variant:
                    current_variant = alt
                    break
        
        # Default to first variant if current not found
        if not current_variant and all_alternatives:
            current_variant = all_alternatives[0]
        
        # Format response
        response_data = {
            "success": True,
            "ingredient_name": request.ingredient_name,
            "current": {
                "name": current_variant.get("name", "Unknown"),
                "inci_name": current_variant.get("inci", "Unknown"),
                "emoji": current_variant.get("emoji", "🧪"),
                "description": current_variant.get("description", ""),
                "benefit_tag": current_variant.get("benefit", ""),
                "suggested_percentage": current_variant.get("percentage", ""),
                "cost_impact": "similar",
                "complexity_fit": current_variant.get("complexity", []),
                "considerations": current_variant.get("considerations", "")
            },
            "alternatives": [
                {
                    "name": alt.get("name", "Unknown"),
                    "inci_name": alt.get("inci", "Unknown"),
                    "emoji": alt.get("emoji", "🌿"),
                    "description": alt.get("description", ""),
                    "benefit_tag": alt.get("benefit", ""),
                    "suggested_percentage": alt.get("percentage", ""),
                    "cost_impact": alt.get("cost_tier", "similar"),
                    "complexity_fit": alt.get("complexity", []),
                    "considerations": alt.get("considerations", "")
                }
                for alt in compatible_alternatives
                if alt != current_variant  # Exclude current from alternatives
            ]
        }
        
        print(f"✅ Found {len(response_data['alternatives'])} alternatives")
        
        return GetAlternativesResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting alternatives: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting alternatives: {str(e)}"
        )

# STAGE 4.5: EDIT METADATA ENDPOINT
# ============================================================================

@router.patch("/{wishId}", response_model=dict)
async def edit_formula_metadata(
    wishId: str,
    request: dict,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Edit formula metadata (name, tag, notes) without changing formula itself.
    
    This endpoint allows users to:
    - Update formula name
    - Update tag for categorization  
    - Update notes
    - Preserve all formula data unchanged
    """
    try:
        print(f"📝 Editing formula metadata: {wishId}")
        
        obj_id = ObjectId(wishId)
        # Extract user info
        user_id = current_user.get("user_id") or current_user.get("_id")
        
       # Allowed fields whitelist (defense-in-depth)
        ALLOWED_FIELDS = {"name", "tag", "notes"}

          # Filter allowed fields only
        data = {k: v for k, v in request.items() if k in ALLOWED_FIELDS and v is not None}

        # Trim name
        if "name" in data and isinstance(data["name"], str):
            data["name"] = data["name"].strip()

        # No valid fields
        if not data:
            raise HTTPException(400, "No valid fields provided")

        # Build update document
        update_doc = {
            **data,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Atomic update (ownership enforced)
        result = await wish_history_col.update_one(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_doc}
        )

        # Not found or unauthorized
        if result.matched_count == 0:
            raise HTTPException(404, "Formula not found or access denied")

        return {
            "success": True,
            "message": "Updated successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error editing metadata: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# STAGE 4: EDIT FORMULA ENDPOINT
# ============================================================================

@router.post("/edit-formula", response_model=EditFormulaResponse)
async def edit_formula(
    request: EditFormulaRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Edit a generated formula by adding, removing, or swapping ingredients.
    
    This endpoint allows users to:
    - Add new ingredients
    - Remove existing ingredients (with restrictions)
    - Swap ingredients for alternatives
    - Adjust ingredient percentages
    - Auto-rebalance formula after edits
    """
    try:
        print(f"✏️ Editing formula: {request.formula_id}")
        
        # Retrieve current formula from history
        user_id = current_user.get("user_id") or current_user.get("_id")
        history_item = await wish_history_col.find_one({
            "_id": ObjectId(request.history_id),
            "user_id": user_id,
            "formula_id": request.formula_id
        })
        
        if not history_item:
            raise HTTPException(
                status_code=404,
                detail="Formula not found or access denied"
            )
        
        current_formula = history_item.get("formula_data", {})
        current_complexity = history_item.get("complexity", "classic")
        
        # Validate operations
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Get complexity limits
        complexity_config = get_complexity_config(current_complexity)
        max_total = complexity_config["max_ingredients"]
        max_actives = complexity_config["active_slots"]
        
        # Track changes
        updated_ingredients = []
        removed_count = 0
        added_count = 0
        
        # Process operations
        for i, operation in enumerate(request.operations):
            op_type = operation.type
            
            if op_type == "remove":
                ingredient_id = operation.ingredient_id
                
                # Check if ingredient can be removed
                if ingredient_id in EDIT_RULES["cannot_remove"]:
                    validation_result["errors"].append({
                        "operation_index": i,
                        "message": f"Cannot remove {ingredient_id} - required for safety"
                    })
                    validation_result["is_valid"] = False
                elif ingredient_id in EDIT_RULES["warn_on_remove"]:
                    validation_result["warnings"].append({
                        "operation_index": i,
                        "message": f"Removing {ingredient_id} may affect stability"
                    })
                
                removed_count += 1
                
            elif op_type == "add":
                new_ingredient = operation.new_ingredient
                
                # Check complexity limits
                current_count = len(current_formula.get("ingredients", []))
                if current_count + added_count - removed_count >= max_total:
                    validation_result["errors"].append({
                        "operation_index": i,
                        "message": f"Cannot add ingredient - exceeds {current_complexity} complexity limit of {max_total}"
                    })
                    validation_result["is_valid"] = False
                
                added_count += 1
                
            elif op_type == "swap":
                # Swapping is essentially remove + add
                added_count += 1
                
            elif op_type == "adjust_percentage":
                # Percentage adjustments are generally valid
                pass
            else:
                validation_result["errors"].append({
                    "operation_index": i,
                    "message": f"Unknown operation type: {op_type}"
                })
                validation_result["is_valid"] = False
        
        if not validation_result["is_valid"]:
            return EditFormulaResponse(
                success=False,
                formula_id=request.formula_id,
                validation=validation_result,
                updated_formula=None,
                warnings=[w["message"] for w in validation_result["warnings"]]
            )
        
        # Apply operations (simplified for demo)
        # In production, this would be more sophisticated with actual ingredient database
        updated_formula = current_formula.copy()
        
        # Add operation notes
        operation_summary = f"Applied {len(request.operations)} operations: {', '.join([op.type for op in request.operations])}"
        
        print(f"✅ Formula edited successfully")
        print(f"   Operations: {len(request.operations)}")
        print(f"   Warnings: {len(validation_result['warnings'])}")
        
        return EditFormulaResponse(
            success=True,
            formula_id=request.formula_id,
            validation=validation_result,
            updated_formula=None,  # Would return actual updated formula
            warnings=[w["message"] for w in validation_result["warnings"]] + [operation_summary]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error editing formula: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error editing formula: {str(e)}"
        )


# ============================================================================
# STAGE 5: REQUEST QUOTE ENDPOINT
# ============================================================================

@router.post("/request-quote", response_model=RequestQuoteResponse)
async def request_manufacturing_quote(
    request: RequestQuoteRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get manufacturing cost quote for a formula.
    
    This endpoint provides:
    - Cost analysis for different quantities
    - Pricing guidance and MRP recommendations
    - Packaging cost estimates
    - Investment breakdown
    """
    try:
        print(f"💰 Generating quote for formula: {request.formula_id}")
        
        # Retrieve formula from history
        user_id = current_user.get("user_id") or current_user.get("_id")
        history_item = await wish_history_col.find_one({
            "_id": ObjectId(request.history_id),
            "user_id": user_id,
            "formula_id": request.formula_id
        })
        
        if not history_item:
            raise HTTPException(
                status_code=404,
                detail="Formula not found or access denied"
            )
        
        # Generate quote ID
        quote_id = str(uuid.uuid4())
        generated_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        valid_until = generated_at + timedelta(days=7)  # Valid for 7 days
        
        # Calculate costs (simplified for demo)
        base_cost_per_100g = 45.50  # Base formula cost
        
        quotes = []
        for quantity in request.quantity_options:
            # Cost calculations
            raw_material_cost = base_cost_per_100g * (quantity / 100)
            packaging_cost_per_unit = 5.0 if request.include_packaging else 0
            total_cost_per_unit = raw_material_cost + packaging_cost_per_unit
            
            # Pricing guidance
            suggested_mrp = int(total_cost_per_unit * 4.5)  # 4.5x margin
            suggested_mrp_range = f"₹{int(suggested_mrp * 0.8)} - ₹{int(suggested_mrp * 1.2)}"
            estimated_margin = f"{int((suggested_mrp / total_cost_per_unit - 1) * 100)}%"
            
            total_investment = total_cost_per_unit * quantity
            total_investment_breakdown = {
                "raw_materials": raw_material_cost * quantity,
                "packaging": packaging_cost_per_unit * quantity,
                "total": total_investment
            }
            
            quotes.append({
                "quantity": quantity,
                "raw_material_cost_per_unit": raw_material_cost,
                "packaging_cost_per_unit": packaging_cost_per_unit,
                "total_cost_per_unit": total_cost_per_unit,
                "suggested_mrp": f"₹{suggested_mrp}",
                "suggested_mrp_range": suggested_mrp_range,
                "estimated_margin": estimated_margin,
                "total_investment": f"₹{int(total_investment):,}",
                "total_investment_breakdown": total_investment_breakdown
            })
        
        # Pricing guidance
        pricing_guidance = {
            "positioning": "Premium but accessible",
            "competitor_range": "₹399 - ₹799 for similar products",
            "recommended_mrp": f"₹{quotes[0]['suggested_mrp']}",
            "margin_explanation": f"At {quotes[0]['suggested_mrp']}, you'll have a healthy {quotes[0]['estimated_margin']} margin after accounting for manufacturing, packaging, and marketing costs."
        }
        
        print(f"✅ Quote generated successfully")
        print(f"   Quote ID: {quote_id}")
        print(f"   Quantities: {request.quantity_options}")
        print(f"   Valid until: {valid_until.strftime('%Y-%m-%d')}")
        
        # Save quote to database
        quote_doc = {
            "quote_id": quote_id,
            "formula_id": request.formula_id,
            "history_id": request.history_id,
            "user_id": user_id,
            "quantity_options": request.quantity_options,
            "include_packaging": request.include_packaging,
            "packaging_type": request.packaging_type,
            "quotes": quotes,
            "pricing_guidance": pricing_guidance,
            "generated_at": generated_at.isoformat(),
            "valid_until": valid_until.isoformat(),
            "status": "active",
            "created_at": generated_at.isoformat()
        }
        
        try:
            result = await quotes_col.insert_one(quote_doc)
            print(f"💾 Saved quote: {quote_id}")
        except Exception as db_error:
            print(f"⚠️ Warning: Failed to save quote: {db_error}")
            # Continue without failing the response
        
        return RequestQuoteResponse(
            success=True,
            formula_id=request.formula_id,
            quote_id=quote_id,
            generated_at=generated_at,
            valid_until=valid_until,
            quotes=quotes,
            pricing_guidance=pricing_guidance
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating quote: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quote: {str(e)}"
        )


# ============================================================================
# STAGE 6: GET THIS MADE ENDPOINT
# ============================================================================

@router.post("/get-this-made", response_model=GetThisMadeResponse)
async def submit_commercialization_request(
    request: GetThisMadeRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Submit commercialization request for a formula.
    
    This endpoint:
    - Assigns queue number
    - Creates commercialization profile
    - Provides next steps
    - Sets up commitment information
    """
    try:
        print(f"🚀 Submitting commercialization request...")
        
        # Validate formula exists
        user_id = current_user.get("user_id") or current_user.get("_id")
        history_item = await wish_history_col.find_one({
            "_id": ObjectId(request.history_id),
            "user_id": user_id,
            "formula_id": request.formula_id
        })
        
        if not history_item:
            raise HTTPException(
                status_code=404,
                detail="Formula not found or access denied"
            )
        
        # Generate queue number and request ID
        queue_number = generate_queue_number()
        request_id = str(uuid.uuid4())
        submitted_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        
        # Determine queue position (simplified)
        queue_position = None  # Would be calculated from database
        
        # Define next steps based on experience level
        next_steps = []
        if request.user_profile.experience_level == "dreaming":
            next_steps = [
                {
                    "order": 1,
                    "emoji": "💬",
                    "title": "Consultation Call",
                    "description": "Our formulation expert will call you to understand your vision and requirements",
                    "estimated_timeline": "1-2 business days"
                },
                {
                    "order": 2,
                    "emoji": "🧪",
                    "title": "Sample Development",
                    "description": "We'll create and test samples based on your formula",
                    "estimated_timeline": "2-3 weeks"
                },
                {
                    "order": 3,
                    "emoji": "📋",
                    "title": "Regulatory Review",
                    "description": "Complete compliance and documentation review",
                    "estimated_timeline": "1 week"
                },
                {
                    "order": 4,
                    "emoji": "🏭",
                    "title": "Production Planning",
                    "description": "Finalize manufacturing specifications and schedule",
                    "estimated_timeline": "1 week"
                }
            ]
        elif request.user_profile.experience_level == "ready":
            next_steps = [
                {
                    "order": 1,
                    "emoji": "🧪",
                    "title": "Sample Batch",
                    "description": "Create production samples for your approval",
                    "estimated_timeline": "1-2 weeks"
                },
                {
                    "order": 2,
                    "emoji": "📋",
                    "title": "Final Documentation",
                    "description": "Prepare all manufacturing and compliance documents",
                    "estimated_timeline": "3-5 days"
                },
                {
                    "order": 3,
                    "emoji": "🏭",
                    "title": "Production Start",
                    "description": "Begin manufacturing your product",
                    "estimated_timeline": "2-3 weeks"
                }
            ]
        else:
            next_steps = [
                {
                    "order": 1,
                    "emoji": "💬",
                    "title": "Discovery Call",
                    "description": "Let's discuss your product goals and timeline",
                    "estimated_timeline": "1-2 business days"
                },
                {
                    "order": 2,
                    "emoji": "📊",
                    "title": "Feasibility Analysis",
                    "description": "Technical and commercial viability assessment",
                    "estimated_timeline": "1 week"
                }
            ]
        
        # Commitment information
        commitment_info = {
            "amount": 5000,
            "currency": "INR",
            "refundable": True,
            "refund_policy": "100% refundable if you decide not to proceed after consultation",
            "platform_charges": "No platform charges",
            "purpose": "To ensure dedicated time and resources for your project"
        }
        
        # Save commercialization request to database
        commercialization_doc = {
            "request_id": request_id,
            "queue_number": queue_number,
            "user_id": user_id,
            "formula_id": request.formula_id,
            "history_id": request.history_id,
            "user_profile": request.user_profile.model_dump(),
            "formula_snapshot": request.formula_snapshot,
            "status": "submitted",
            "submitted_at": submitted_at.isoformat(),
            "next_steps": next_steps,
            "commitment_info": commitment_info,
            "updated_at": submitted_at.isoformat()
        }
        
        try:
            result = await commercialization_requests_col.insert_one(commercialization_doc)
            print(f"💾 Saved commercialization request: {request_id}")
        except Exception as db_error:
            print(f"⚠️ Warning: Failed to save commercialization request: {db_error}")
            # Continue without failing the response
        
        print(f"✅ Commercialization request submitted")
        print(f"   Queue Number: {queue_number}")
        print(f"   Experience Level: {request.user_profile.experience_level}")
        print(f"   Timeline: {request.user_profile.timeline}")
        
        return GetThisMadeResponse(
            success=True,
            queue_number=queue_number,
            queue_position=queue_position,
            request_id=request_id,
            submitted_at=submitted_at,
            next_steps=next_steps,
            commitment_info=commitment_info
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error submitting commercialization request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error submitting request: {str(e)}"
        )


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-inspiration-board")
async def export_make_wish_revised_to_board(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token)
):
    """Export revised make a wish formulations to inspiration board"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
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
        
        # Create export request
        export_request = ExportToBoardRequest(
            board_id=board_id,
            exports=[
                ExportItemRequest(
                    feature_type="make_wish_revised",
                    history_ids=history_ids
                )
            ]
        )
        
        # Call the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.api.inspiration_boards import export_to_board_endpoint
        result = await export_to_board_endpoint(export_request, background_tasks, current_user)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR exporting revised make a wish to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BACKWARD COMPATIBILITY: ORIGINAL GENERATE ENDPOINT
# ============================================================================

@router.post("/generate", response_model=MakeWishResponse)
async def generate_make_wish_formula_legacy(
    request: MakeWishRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Legacy Make a Wish endpoint for backward compatibility.
    
    This endpoint maintains the original API structure while 
    internally using the revised system. Maps old request format
    to new flow.
    """
    try:
        print(f"🔄 Converting legacy request to revised flow...")
        
        # Convert legacy request to natural language
        legacy_wish_text = f"""
        I want to create a {request.category} {request.productType} with the following benefits: {', '.join(request.benefits)}.
        """
        
        if request.heroIngredients:
            legacy_wish_text += f" Please include these ingredients: {', '.join(request.heroIngredients)}."
        
        if request.exclusions:
            legacy_wish_text += f" Make it {', '.join(request.exclusions)}."
        
        if request.additionalNotes:
            legacy_wish_text += f" Additional notes: {request.additionalNotes}"
        
        # Create ParseWishRequest
        from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import ParseWishRequest
        parse_request = ParseWishRequest(wish_text=legacy_wish_text.strip())
        
        # Parse the wish
        parse_response = await parse_natural_language_wish(parse_request, current_user)
        
        # Default to classic complexity for legacy requests
        complexity = "classic"
        
        # Create revised request
        from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import MakeWishRequestRevised
        revised_request = MakeWishRequestRevised(
            wish_text=legacy_wish_text.strip(),
            parsed_data=parse_response.parsed_data,
            complexity=complexity,
            claims=request.claims,
            additional_notes=request.additionalNotes,
            name=request.name or "Legacy Formula",
            tag=request.tag,
            notes=request.notes,
            history_id=request.history_id
        )
        
        # Generate using revised flow
        revised_response = await generate_formula_revised(revised_request, current_user)
        
        # Convert back to legacy format
        legacy_response = {
            "wish_data": request.model_dump(),
            "ingredient_selection": {"status": "completed"},
            "optimized_formula": revised_response.formula.model_dump(),
            "manufacturing": revised_response.manufacturing,
            "cost_analysis": {"status": "moved_to_separate_endpoint"},
            "compliance": revised_response.compliance,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "formula_version": "2.0 (revised)",
                "legacy_mode": True
            },
            "history_id": revised_response.history_id
        }
        
        return MakeWishResponse(**legacy_response)
    
    except Exception as e:
        print(f"❌ Error in legacy conversion: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error in legacy endpoint: {str(e)}"
        )
