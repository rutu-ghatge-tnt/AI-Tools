"""
Market Research API Endpoints
==============================

API endpoints for market research functionality including:
- Market research history management
- Product matching and comparison
- AI-powered category analysis and overview generation

Extracted from analyze_inci.py for better modularity.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
import time
import os
import json
import re
from typing import List, Dict, Optional
from bson import ObjectId
from datetime import datetime, timezone, timedelta

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper
from app.ai_ingredient_intelligence.logic.ai_analysis import (
    analyze_formulation_and_suggest_matching_with_ai,
    analyze_product_categories_with_ai,
    generate_market_research_overview_with_ai,
    enhance_product_ranking_with_ai,
    claude_client  # Import claude_client directly
)
import os  # For claude_api_key check

# Check if anthropic is available (for error messages)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

claude_api_key = os.getenv("CLAUDE_API_KEY")  # For error messages
from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import market_research_history_col, branded_ingredients_col, inci_col
from app.ai_ingredient_intelligence.models.schemas import (
    MarketResearchResponse,
    MarketResearchProductsResponse,
    MarketResearchOverviewResponse,
    GetMarketResearchHistoryResponse,
    MarketResearchHistoryDetailResponse,
    MarketResearchHistoryItem,
    MarketResearchHistoryItemSummary,
)

router = APIRouter(tags=["Market Research"])


# ============================================================================
# MARKET RESEARCH HISTORY ENDPOINTS
# ============================================================================

@router.post("/save-market-research-history")
async def save_market_research_history(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    [DISABLED] Save market research history (user-specific)
    
    ⚠️ THIS ENDPOINT IS CURRENTLY DISABLED ⚠️
    Market research results are now automatically saved by the market research endpoints.
    This endpoint returns success but does not save to prevent duplicates.
    
    AUTO-SAVE: Market research endpoints (/market-research, /market-research/products) 
    automatically save results to history when user is authenticated.
    
    Request body:
    {
        "name": "Product Name",
        "tag": "optional-tag",
        "input_type": "inci" or "url",
        "input_data": "ingredient list or URL",
        "research_result": {...} (optional),
        "ai_analysis": "AI analysis message",
        "ai_reasoning": "AI reasoning",
        "notes": "User notes"
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # ⚠️ ENDPOINT DISABLED - Return success without saving to prevent duplicates
        # Extract user_id and name for logging (do minimal validation to prevent crashes)
        user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
        name = payload.get("name", "Unknown")
        
        # Log that this endpoint was called but is disabled
        print(f"⚠️ [DISABLED] /save-market-research-history called for user {user_id_value}, name: {name}")
        print(f"   This endpoint is disabled to prevent duplicate saves.")
        
        # Return success response without actually saving
        # Generate a dummy ID for frontend compatibility
        import uuid
        dummy_id = str(uuid.uuid4())
        
        return {
            "success": True,
            "id": dummy_id,
            "message": "Market research history save endpoint disabled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in disabled save-market-research-history endpoint: {e}")
        # Still return success to prevent frontend crashes
        import uuid
        return {
            "success": True,
            "id": str(uuid.uuid4()),
            "message": "Market research history save endpoint disabled"
        }


@router.get("/market-research-history", response_model=GetMarketResearchHistoryResponse)
async def get_market_research_history(
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get market research history (user-specific)
    
    Query parameters:
    - search: Search term for name or tag (optional)
    - limit: Number of results (default: 50)
    - skip: Number of results to skip (default: 0)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        query = {"user_id": user_id}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"tag": {"$regex": search, "$options": "i"}}
            ]
        
        total = await market_research_history_col.count_documents(query)
        
        # Fetch items - only get summary fields (exclude large fields)
        cursor = market_research_history_col.find(
            query,
            {
                "_id": 1,
                "user_id": 1,
                "name": 1,
                "tag": 1,
                "input_type": 1,
                "input_data": 1,
                "notes": 1,
                "created_at": 1,
                "research_result": 1  # Check if exists, but don't return full data
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        
        # Convert to summary format (exclude large fields)
        summary_items = []
        for item in items:
            item_id = str(item["_id"])
            del item["_id"]
            
            # Truncate input_data for preview (max 100 chars)
            input_data = item.get("input_data", "")
            if input_data and len(input_data) > 100:
                input_data = input_data[:100] + "..."
            
            # Get total products count from research_result if available
            total_products = None
            research_result = item.get("research_result")
            if research_result and isinstance(research_result, dict):
                products = research_result.get("products", [])
                if isinstance(products, list):
                    total_products = len(products)
            
            summary_item = {
                "id": item_id,
                "user_id": item.get("user_id"),
                "name": item.get("name", ""),
                "tag": item.get("tag"),
                "input_type": item.get("input_type", ""),
                "input_data": input_data,
                "notes": item.get("notes"),
                "created_at": item.get("created_at"),
                "has_research": research_result is not None,
                "total_products": total_products
            }
            summary_items.append(summary_item)
        
        return GetMarketResearchHistoryResponse(
            items=[MarketResearchHistoryItemSummary(**item) for item in summary_items],
            total=total
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market research history: {str(e)}"
        )


@router.get("/market-research-history/{history_id}/details", response_model=MarketResearchHistoryDetailResponse)
async def get_market_research_history_detail(
    history_id: str,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of products per page (max 100)"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get full details of a specific market research history item (includes all large fields)
    
    This endpoint returns the complete data including:
    - Full research_result with PAGINATED products (products array is paginated)
    - All other fields remain constant (ai_interpretation, category info, etc.)
    
    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Number of products per page (default: 10, max: 100)
    
    Pagination:
    - Only the "products" array in research_result is paginated
    - All other fields (ai_interpretation, primary_category, subcategory, etc.) remain constant
    - Pagination metadata (page, page_size, total_pages, total_products) is included in research_result
    
    Use this endpoint when you need to display the full research results with paginated products.
    The list endpoint (/market-research-history) only returns summaries.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # 🔹 EFFICIENT DB-LEVEL PAGINATION: Use MongoDB aggregation with $slice
        # This reduces network transfer by only sending requested products
        # Note: MongoDB still loads full document, but only requested slice is transferred over network
        
        # First, get total count and other fields (lightweight query)
        item_meta = await market_research_history_col.find_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {
                "user_id": 1,
                "name": 1,
                "tag": 1,
                "input_type": 1,
                "input_data": 1,
                "ai_analysis": 1,
                "ai_reasoning": 1,
                "ai_interpretation": 1,
                "primary_category": 1,
                "subcategory": 1,
                "category_confidence": 1,
                "notes": 1,
                "created_at": 1,
                "research_result.total_matched": 1,  # Get total count
                "research_result.extracted_ingredients": 1,
                "research_result.processing_time": 1,
                "research_result.input_type": 1,
                "research_result.ai_analysis": 1,
                "research_result.ai_reasoning": 1,
                "research_result.ai_interpretation": 1,
                "research_result.primary_category": 1,
                "research_result.subcategory": 1,
                "research_result.category_confidence": 1
            }
        )
        
        if not item_meta:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Get total products count
        research_result = item_meta.get("research_result", {})
        total_products = research_result.get("total_matched", 0)
        
        # If no products, return early
        if total_products == 0:
            item_meta["id"] = str(item_meta["_id"])
            del item_meta["_id"]
            item_meta["research_result"] = {
                **research_result,
                "products": [],
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "total_matched": 0
            }
            # Ensure all fields
            for field in ["ai_analysis", "ai_reasoning", "ai_interpretation", "primary_category", "subcategory", "category_confidence"]:
                if field not in item_meta:
                    item_meta[field] = None
            return MarketResearchHistoryDetailResponse(
                item=MarketResearchHistoryItem(**item_meta)
            )
        
        # Use aggregation to slice products array at DB level
        pipeline = [
            {"$match": {"_id": ObjectId(history_id), "user_id": user_id}},
            {
                "$project": {
                    # Slice products array: skip (page-1)*page_size, take page_size
                    "products_slice": {
                        "$slice": [
                            {"$ifNull": ["$research_result.products", []]},
                            (page - 1) * page_size,
                            page_size
                        ]
                    }
                }
            }
        ]
        
        cursor = market_research_history_col.aggregate(pipeline)
        products_result = await cursor.to_list(length=1)
        paginated_products = products_result[0].get("products_slice", []) if products_result else []
        
        # Calculate pagination metadata
        total_pages = (total_products + page_size - 1) // page_size
        
        # Build complete item
        item = {
            "id": str(item_meta["_id"]),
            "user_id": item_meta.get("user_id"),
            "name": item_meta.get("name"),
            "tag": item_meta.get("tag"),
            "input_type": item_meta.get("input_type"),
            "input_data": item_meta.get("input_data"),
            "ai_analysis": item_meta.get("ai_analysis"),
            "ai_reasoning": item_meta.get("ai_reasoning"),
            "ai_interpretation": item_meta.get("ai_interpretation"),
            "primary_category": item_meta.get("primary_category"),
            "subcategory": item_meta.get("subcategory"),
            "category_confidence": item_meta.get("category_confidence"),
            "notes": item_meta.get("notes"),
            "created_at": item_meta.get("created_at"),
            "research_result": {
                **research_result,
                "products": paginated_products,  # Only paginated products
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_matched": total_products
            }
        }
        
        # Ensure all fields have defaults
        for field in ["ai_analysis", "ai_reasoning", "ai_interpretation", "primary_category", "subcategory", "category_confidence"]:
            if item.get(field) is None:
                item[field] = None
        
        print(f"[DB PAGINATION] History {history_id}: Page {page}/{total_pages}, Showing {len(paginated_products)}/{total_products} products (DB-level slice)")
        
        return MarketResearchHistoryDetailResponse(
            item=MarketResearchHistoryItem(**item)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching market research history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch market research history detail: {str(e)}"
        )


@router.patch("/market-research-history/{history_id}")
async def update_market_research_history(
    history_id: str, 
    payload: dict, 
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update market research history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating research results, AI analysis, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the market research history item
    - tag: Update or add a categorization tag
    - notes: Update user notes
    - input_data: Update input data (URL or INCI) (for regeneration)
    - input_type: Update input type (for regeneration)
    - research_result: Update research result (for regeneration)
    - ai_analysis: Update AI analysis (for regeneration)
    - ai_reasoning: Update AI reasoning (for regeneration)
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Build update document - allow all fields except user_id and created_at
        update_data = {}
        excluded_fields = ["user_id", "created_at", "_id"]  # These should never be updated
        
        for key, value in payload.items():
            if key not in excluded_fields:
                # Handle string fields with strip if they are strings
                if isinstance(value, str):
                    update_data[key] = value.strip() if value.strip() else None
                else:
                    update_data[key] = value
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = await market_research_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to update it")
        
        return {
            "success": True,
            "message": "Market research history updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update market research history: {str(e)}"
        )


@router.delete("/market-research-history/{history_id}")
async def delete_market_research_history(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Delete market research history item (user-specific)
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        result = await market_research_history_col.delete_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="History item not found or you don't have permission to delete it")
        
        return {
            "success": True,
            "message": "Market research history deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting market research history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete market research history: {str(e)}"
        )


# ============================================================================
# MARKET RESEARCH MAIN ENDPOINTS
# ============================================================================

# Market Research endpoint - matches ingredients with externalProducts collection
@router.post("/market-research", response_model=MarketResearchResponse)
async def market_research(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Market Research: Match products from URL or INCI list with externalProducts collection.
    
    AUTO-SAVE: Results are automatically saved to market research history if user is authenticated.
    Provide optional "name" and "tag" in payload to customize the saved history item.
    
    ENHANCED FEATURES:
    1. AI Category Analysis: Automatically analyzes input to determine product category (haircare, skincare, lipcare, etc.) and subcategory
    2. Category Filtering: Filters products by category to ensure relevance (e.g., face serum won't show hair products)
    3. Pagination: Shows all matched products with pagination instead of just top matches
    4. AI Interpretation: Provides AI interpretation of the input explaining category determination
    5. Market Research Overview: Generates comprehensive AI-powered overview of research findings
    
    IMPORTANT: Only matches ACTIVE ingredients. Shows all products that have at least one active ingredient match AND match the identified category.
    
    Request body:
    {
        "url": "https://example.com/product/..." (required if input_type is "url"),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci"),
        "input_type": "url" or "inci",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional)
    }
    
    Returns:
    {
        "products": [ALL matched products with images and full details, sorted by active match percentage],
        "extracted_ingredients": [list of ingredients extracted from input],
        "total_matched": total number of matched products,
        "processing_time": time taken,
        "input_type": "url" or "inci",
        "ai_interpretation": "AI interpretation of input explaining category determination",
        "primary_category": "haircare" | "skincare" | "lipcare" | "bodycare" | "other",
        "subcategory": "serum" | "cleanser" | "shampoo" | etc.,
        "category_confidence": "high" | "medium" | "low",
        "market_research_overview": "Comprehensive AI-generated overview of market research findings",
        "ai_analysis": "AI analysis message (if no actives found)",
        "ai_reasoning": "AI reasoning for ingredient selection"
    }
    
    Note: This POST endpoint returns ALL products. For pagination, use GET /market-research-history/{history_id}/details?page=1&page_size=10
    
    Note: Products are included if they:
    1. Match at least one active ingredient from the input
    2. Match the identified category (if category confidence is high or medium)
    
    Excipients and unknown ingredients are ignored for matching purposes.
    """
    start = time.time()
    scraper = None
    
    # 🔹 Auto-save: Extract user info and optional name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = payload.get("name")  # Optional: custom name for history
    tag = payload.get("tag")  # Optional: tag for history
    notes = payload.get("notes")  # Optional: notes for history
    provided_history_id = payload.get("history_id")  # Optional: reuse existing history item
    history_id = None
    
    # Validate history_id if provided
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await market_research_history_col.find_one({
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
        # Validate payload
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'")
        
        ingredients = []
        extracted_text = ""
        
        if input_type == "url":
            url = payload.get("url", "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="url is required when input_type is 'url'")
            
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
            
            # Initialize URL scraper and extract ingredients
            scraper = URLScraper()
            print(f"Scraping URL for market research: {url}")
            extraction_result = await scraper.extract_ingredients_from_url(url)
            
            # Get ingredients - could be list or string, ensure it's a list
            ingredients_raw = extraction_result.get("ingredients", [])
            extracted_text = extraction_result.get("extracted_text", "")
            # Store extraction result for later use in category analysis
            scraper_extraction_result = extraction_result
            
            # If ingredients is a string, parse it
            if isinstance(ingredients_raw, str):
                ingredients = parse_inci_string(ingredients_raw)
            elif isinstance(ingredients_raw, list):
                ingredients = ingredients_raw
            else:
                ingredients = []
            
            print(f"Extracted ingredients from URL: {ingredients}")
            
            if not ingredients:
                raise HTTPException(
                    status_code=404,
                    detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
                )
            
            input_data_value = url  # Store URL for auto-save
        elif input_type == "inci":
            # INCI input
            inci = payload.get("inci", "").strip()
            if not inci:
                raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'")
            
            # Parse INCI string
            ingredients = parse_inci_string(inci)
            extracted_text = inci
            input_data_value = inci  # Store INCI for auto-save
            
            if not ingredients:
                raise HTTPException(
                    status_code=400,
                    detail="No valid ingredients found after parsing. Please check your input format."
                )
        
        # Query externalproducts collection (lowercase - as shown in MongoDB Compass)
        external_products_col = db["externalproducts"]
        collection_name = "externalproducts"
        print(f"✅ Using collection: {collection_name}")
        
        # For ingredient-based matching (url, inci)
        print(f"Extracted {len(ingredients)} ingredients for market research")
        print(f"Ingredients list: {ingredients}")
        
        # Normalize ingredients for matching - use same normalization as database
        # Database uses: re.sub(r"\s+", " ", s).strip().lower()
        import re
        normalized_input_ingredients = []
        for ing in ingredients:
            if ing and ing.strip():
                # Use same normalization as database: normalize spaces, strip, lowercase
                normalized = re.sub(r"\s+", " ", ing.strip()).strip().lower()
                if normalized:
                    normalized_input_ingredients.append(normalized)
        
        # Remove duplicates while preserving order
        seen = set()
        normalized_input_ingredients = [x for x in normalized_input_ingredients if not (x in seen or seen.add(x))]
        
        print(f"Normalized {len(ingredients)} input ingredients to {len(normalized_input_ingredients)} unique normalized ingredients")
        
        print(f"Normalized ingredients for matching ({len(normalized_input_ingredients)}): {normalized_input_ingredients[:10]}{'...' if len(normalized_input_ingredients) > 10 else ''}")
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided and no existing history_id
        if user_id_value and not history_id and input_data_value:
            try:
                # Check if a history item with the same input_data already exists for this user
                existing_history_item = await market_research_history_col.find_one({
                    "user_id": user_id_value,
                    "input_type": input_type,
                    "input_data": input_data_value
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same input_data, reusing history_id: {history_id}")
                else:
                    # Generate default name if not provided
                    display_name = name
                    if not display_name:
                        if input_type == "url":
                            # Extract product name from URL
                            from urllib.parse import unquote
                            try:
                                url_decoded = unquote(input_data_value)
                                segments = url_decoded.split('/')
                                for segment in reversed(segments):
                                    segment = segment.split('?')[0].replace('-', ' ').replace('_', ' ')
                                    if segment and len(segment) > 5 and len(segment) < 100:
                                        if any(keyword in segment.lower() for keyword in ['cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner']):
                                            display_name = segment.title() + " Research"
                                            break
                            except:
                                pass
                        if not display_name:
                            # Use first ingredient or default
                            if ingredients and len(ingredients) > 0:
                                display_name = ingredients[0] + " Research"
                            else:
                                display_name = "Market Research"
                    
                    # Truncate if too long
                    if len(display_name) > 100:
                        display_name = display_name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": display_name,
                        "tag": tag,
                        "input_type": input_type,
                        "input_data": input_data_value,
                        "notes": notes,
                        "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
                    }
                    result = await market_research_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                # Continue with research even if saving fails
        
        # Initialize AI analysis variables (will be populated if AI is used)
        ai_analysis_message = None
        ai_reasoning = None
        
        # NEW: AI Category Analysis - Analyze input to determine categories
        print(f"\n{'='*60}")
        print("STEP 0: AI Category Analysis...")
        print(f"{'='*60}")
        category_info = {
            "primary_category": None,
            "subcategory": None,
            "interpretation": None,
            "confidence": "low"
        }
        
        if claude_client and ingredients:
            try:
                # Extract product name from URL if available
                product_name = ""
                if input_type == "url":
                    url = payload.get("url", "")
                    # First try to get product name from extraction result if available
                    if 'scraper_extraction_result' in locals() and scraper_extraction_result:
                        product_name = scraper_extraction_result.get("product_name", "")
                    
                    # If not found, try to extract from URL or extracted text
                    if not product_name:
                        if extracted_text:
                            # Look for product name patterns in extracted text
                            lines = extracted_text.split('\n')[:30]
                            for line in lines:
                                line_lower = line.lower()
                                # Look for product name indicators
                                if any(keyword in line_lower for keyword in ['product', 'name', 'title', 'cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner']):
                                    # Extract the line but clean it up
                                    cleaned = line.strip()[:150]
                                    # Remove common prefixes
                                    for prefix in ['product name:', 'product:', 'name:', 'title:']:
                                        if cleaned.lower().startswith(prefix):
                                            cleaned = cleaned[len(prefix):].strip()
                                    if cleaned and len(cleaned) > 3:
                                        product_name = cleaned
                                        break
                        
                        # Fallback: try to extract from URL path
                        if not product_name and url:
                            from urllib.parse import unquote
                            try:
                                url_decoded = unquote(url)
                                # Extract meaningful segments from URL
                                segments = url_decoded.split('/')
                                for segment in reversed(segments):
                                    segment = segment.split('?')[0].replace('-', ' ').replace('_', ' ')
                                    if segment and len(segment) > 5 and len(segment) < 100:
                                        # Check if it contains product-related keywords
                                        if any(keyword in segment.lower() for keyword in ['cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner', 'face', 'hair', 'lip']):
                                            product_name = segment.title()
                                            break
                            except:
                                pass
                
                print(f"  🤖 Calling AI for category analysis...")
                if product_name:
                    print(f"  📝 Product name/context: {product_name[:100]}")
                url_for_ai = payload.get("url", "") if input_type == "url" else ""
                if url_for_ai:
                    print(f"  🔗 Product URL: {url_for_ai[:100]}")
                category_info = await analyze_product_categories_with_ai(
                    ingredients,
                    normalized_input_ingredients,
                    extracted_text[:1000] if extracted_text else "",  # Limit text length
                    product_name,
                    url_for_ai
                )
                print(f"  ✓ Category analysis completed")
            except Exception as e:
                print(f"  ⚠️  Error in AI category analysis: {e}")
                import traceback
                traceback.print_exc()
        
        primary_category = category_info.get("primary_category")
        subcategory = category_info.get("subcategory")
        ai_interpretation = category_info.get("interpretation")
        category_confidence = category_info.get("confidence", "low")
        
        # Categorize input ingredients into actives and excipients
        print(f"\n{'='*60}")
        print("STEP 1.5: Categorizing input ingredients...")
        print(f"{'='*60}")
        input_actives = []  # List of normalized active ingredient names
        input_excipients = []  # List of normalized excipient ingredient names
        input_unknown = []  # Ingredients without category
        
        if normalized_input_ingredients:
            try:
                # Query INCI collection for categories (exact match only)
                inci_query = {
                    "inciName_normalized": {"$in": normalized_input_ingredients}
                }
                print(f"  Querying INCI collection with {len(normalized_input_ingredients)} normalized ingredients...")
                print(f"  Sample normalized ingredients being queried: {normalized_input_ingredients[:5]}")
                inci_cursor = inci_col.find(inci_query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                inci_results = await inci_cursor.to_list(length=None)
                print(f"  Found {len(inci_results)} INCI records in database")
                
                # Build mapping of normalized name -> category
                input_category_map = {}
                for inci_doc in inci_results:
                    normalized = inci_doc.get("inciName_normalized", "").strip().lower()
                    category = inci_doc.get("category", "")
                    inci_name = inci_doc.get("inciName", "")
                    if normalized and category:
                        input_category_map[normalized] = category
                        if len(input_category_map) <= 5:  # Log first 5 matches
                            print(f"    Matched: '{normalized}' -> category: '{category}' (INCI: {inci_name})")
                
                print(f"  Built category map with {len(input_category_map)} entries")
                if len(input_category_map) == 0 and len(normalized_input_ingredients) > 0:
                    print(f"  ⚠️  WARNING: No matches found in database!")
                    print(f"  This means the normalized names don't match what's in the database.")
                    print(f"  Sample query values: {normalized_input_ingredients[:3]}")
                    # Try to find a sample from database to compare
                    sample_doc = await inci_col.find_one({}, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                    if sample_doc:
                        print(f"  Sample DB doc: inciName='{sample_doc.get('inciName')}', inciName_normalized='{sample_doc.get('inciName_normalized')}'")
                
                # Categorize input ingredients
                for normalized_ing in normalized_input_ingredients:
                    category = input_category_map.get(normalized_ing)
                    if category == "Active":
                        input_actives.append(normalized_ing)
                    elif category == "Excipient":
                        input_excipients.append(normalized_ing)
                    else:
                        input_unknown.append(normalized_ing)
                
                print(f"  Input actives: {len(input_actives)}")
                print(f"  Input excipients: {len(input_excipients)}")
                print(f"  Input unknown (no category): {len(input_unknown)}")
                if input_actives:
                    print(f"  Sample actives: {input_actives[:5]}")
                else:
                    print(f"  ⚠️  WARNING: No active ingredients found!")
                    print(f"  This could mean:")
                    print(f"    1. Ingredients are not categorized in the database")
                    print(f"    2. Normalized names don't match")
                    print(f"    3. All ingredients are excipients")
                    print(f"  Sample normalized ingredients: {normalized_input_ingredients[:5]}")
                    print(f"  Sample category map entries: {list(input_category_map.items())[:5] if input_category_map else 'None'}")
                if input_excipients:
                    print(f"  Sample excipients: {input_excipients[:5]}")
            except Exception as e:
                print(f"  Warning: Error categorizing input ingredients: {e}")
                import traceback
                traceback.print_exc()
                # If categorization fails, treat all as unknown (will match all)
                input_unknown = normalized_input_ingredients.copy()
                print(f"  Fallback: Treating all {len(input_unknown)} ingredients as unknown")
        
        # If no actives found, use AI to analyze formulation and suggest what to match
        if len(input_actives) == 0:
            print(f"\n⚠️  No active ingredients found in database lookup!")
            print(f"  Using AI to analyze formulation and suggest matching strategy...")
            print(f"  Total input ingredients: {len(normalized_input_ingredients)}")
            
            # Use Claude AI to analyze formulation and suggest what to match
            if claude_client and normalized_input_ingredients:
                print(f"  🤖 Calling Claude AI to analyze formulation...")
                try:
                    ai_analysis = await analyze_formulation_and_suggest_matching_with_ai(
                        ingredients,
                        normalized_input_ingredients,
                        input_category_map
                    )
                    
                    # Store AI analysis for response (always store, even if no ingredients to match)
                    if ai_analysis:
                        # Get values, convert empty strings to None
                        analysis_val = ai_analysis.get("analysis")
                        ai_analysis_message = analysis_val if analysis_val and analysis_val.strip() else None
                        
                        reasoning_val = ai_analysis.get("reasoning")
                        ai_reasoning = reasoning_val if reasoning_val and reasoning_val.strip() else None
                        
                        print(f"  📊 AI Analysis stored: {ai_analysis_message}")
                        print(f"  💭 AI Reasoning stored: {ai_reasoning}")
                    
                    if ai_analysis and ai_analysis.get("ingredients_to_match"):
                        ai_identified_actives = ai_analysis.get("ingredients_to_match", [])
                        print(f"  ✓ AI suggested {len(ai_identified_actives)} ingredients to match: {ai_identified_actives[:5]}")
                        
                        # Add AI-identified actives to input_actives
                        input_actives.extend(ai_identified_actives)
                        print(f"  ✓ Total active ingredients after AI: {len(input_actives)}")
                    else:
                        print(f"  ⚠️  AI could not suggest ingredients to match. Will skip product matching.")
                        if ai_analysis_message:
                            print(f"  AI Message: {ai_analysis_message}")
                except Exception as e:
                    print(f"  ❌ Error using AI to analyze formulation: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                if not claude_client:
                    print(f"  ⚠️  Claude client not available. Cannot use AI matching.")
                    if not claude_api_key:
                        print(f"     Reason: CLAUDE_API_KEY environment variable not set")
                    elif not ANTHROPIC_AVAILABLE:
                        print(f"     Reason: anthropic package not installed")
                if not normalized_input_ingredients:
                    print(f"  ⚠️  No normalized ingredients available for AI analysis.")
                print(f"  Will skip product matching since no actives to match against.")
        
        # CRITICAL: Always fetch ALL products with ingredients - don't rely on regex query
        # The regex query might not work well with arrays, so we'll do matching in Python
        print(f"\n{'='*60}")
        print("STEP 1: Fetching products from database...")
        print(f"{'='*60}")
        all_products = []
        try:
            # First, check how many products exist
            print("Counting documents in collection...")
            total_count = await external_products_col.count_documents({})
            print(f"  Total documents: {total_count}")
            
            # Check for ingredients field in different ways
            has_ingredients_count_1 = await external_products_col.count_documents({
                "ingredients": {"$exists": True}
            })
            has_ingredients_count_2 = await external_products_col.count_documents({
                "ingredients": {"$exists": True, "$ne": None}
            })
            has_ingredients_count_3 = await external_products_col.count_documents({
                "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
            })
            
            print(f"  Products with ingredients field: {has_ingredients_count_1}")
            print(f"  Products with ingredients (not null): {has_ingredients_count_2}")
            print(f"  Products with ingredients (not null/empty): {has_ingredients_count_3}")
            
            # Try to get a sample product to see the structure
            sample_product = await external_products_col.find_one({})
            if sample_product:
                print(f"\n  Sample product structure:")
                print(f"    Keys: {list(sample_product.keys())[:10]}")
                if "ingredients" in sample_product:
                    sample_ing = sample_product["ingredients"]
                    print(f"    Ingredients type: {type(sample_ing).__name__}")
                    if isinstance(sample_ing, list):
                        print(f"    Ingredients array length: {len(sample_ing)}")
                        print(f"    First 3 ingredients: {sample_ing[:3]}")
                    elif isinstance(sample_ing, str):
                        print(f"    Ingredients string length: {len(sample_ing)}")
                        print(f"    First 200 chars: {sample_ing[:200]}")
            
            # Fetch ALL products that have ingredients (no limit - we need to check everything)
            print(f"\nFetching all products with ingredients...")
            all_products = await external_products_col.find({
                "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
            }).to_list(length=None)  # NO LIMIT - check all products
            
            print(f"✅ Fetched {len(all_products)} products to check")
            
            if len(all_products) == 0:
                print(f"\n⚠️ WARNING: No products found in {collection_name} collection!")
                print("   Possible reasons:")
                print("   1. The collection is empty")
                print("   2. Products don't have 'ingredients' field")
                print("   3. All ingredients fields are null or empty")
                print("   4. Collection name is incorrect")
                
                # Try fetching ANY products to see if collection has data
                any_products = await external_products_col.find({}).limit(5).to_list(length=None)
                if any_products:
                    print(f"   Found {len(any_products)} products in collection, but none have ingredients field")
                    print(f"   Sample product keys: {list(any_products[0].keys())[:10] if any_products else 'N/A'}")
                
                # Generate fallback overview for empty results
                fallback_overview = f"Market Research Overview\n\nNo products found in the database to match against. Please ensure the database contains product data with ingredient information."
                
                return MarketResearchResponse(
                    products=[],
                    extracted_ingredients=ingredients,
                    total_matched=0,
                    processing_time=round(time.time() - start, 2),
                    input_type=input_type,
                    ai_analysis=ai_analysis_message,
                    ai_reasoning=ai_reasoning,
                    market_research_overview=fallback_overview
                )
        except Exception as e:
            print(f"\n❌ ERROR fetching products: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch products from database: {str(e)}"
            )
        
        # Debug: Check a few sample products to see ingredient format
        if all_products and len(all_products) > 0:
            print(f"\n{'='*60}")
            print("DEBUG: Sample Product Analysis")
            print(f"{'='*60}")
            for i, sample_product in enumerate(all_products[:3]):  # Check first 3 products
                sample_ingredients = sample_product.get("ingredients", "")
                product_name = sample_product.get("name") or sample_product.get("productName") or "Unknown"
                print(f"\nSample Product {i+1}: {product_name[:50]}")
                print(f"  Ingredients type: {type(sample_ingredients).__name__}")
                if isinstance(sample_ingredients, str):
                    print(f"  Ingredients (first 300 chars): {sample_ingredients[:300]}")
                    # Try to parse it
                    parsed = parse_inci_string(sample_ingredients[:300])
                    print(f"  Parsed count: {len(parsed)} ingredients")
                    if parsed:
                        print(f"  First 3 parsed: {parsed[:3]}")
                elif isinstance(sample_ingredients, list):
                    print(f"  Ingredients array length: {len(sample_ingredients)}")
                    if sample_ingredients:
                        print(f"  First 5: {sample_ingredients[:5]}")
            print(f"{'='*60}\n")
        
        # Match products based on ingredient overlap
        matched_products = []
        print(f"\n{'='*60}")
        print(f"Starting ingredient matching:")
        print(f"  Input ingredients ({len(normalized_input_ingredients)}): {normalized_input_ingredients[:10]}{'...' if len(normalized_input_ingredients) > 10 else ''}")
        print(f"  Products to check: {len(all_products)}")
        print(f"{'='*60}\n")
        
        if len(all_products) == 0:
            print("⚠️ WARNING: No products found in database to check!")
            print("This might indicate:")
            print("  1. The externalProducts collection is empty")
            print("  2. No products have an 'ingredients' field")
            print("  3. Database connection issue")
            # Generate fallback overview for no active ingredients case
            fallback_overview = f"Market Research Overview\n\nNo active ingredients were identified in the input formulation. Market research requires active ingredients to match against products in the database."
            
            return MarketResearchResponse(
                products=[],
                extracted_ingredients=ingredients,
                total_matched=0,
                processing_time=round(time.time() - start, 2),
                input_type=input_type,
                market_research_overview=fallback_overview
            )
        
        print(f"🔍 Starting to check {len(all_products)} products for matches...")
        print(f"  Active ingredients to match against: {len(input_actives)}")
        if input_actives:
            print(f"  Active ingredients list: {input_actives[:10]}{'...' if len(input_actives) > 10 else ''}")
        else:
            print(f"  ⚠️  NO ACTIVE INGREDIENTS FOUND - will skip all products!")
        matches_found = 0
        
        for idx, product in enumerate(all_products):
            if (idx + 1) % 500 == 0:
                print(f"  Processed {idx + 1}/{len(all_products)} products... ({matches_found} matches so far)")
            
            product_ingredients_raw = product.get("ingredients", "")
            if not product_ingredients_raw:
                continue
            
            # Parse ingredients - handle both string and array formats
            product_ingredients = []
            
            if isinstance(product_ingredients_raw, list):
                # If it's already a list, use it directly (cleaned format)
                product_ingredients = [str(ing).strip() for ing in product_ingredients_raw if ing and str(ing).strip()]
            elif isinstance(product_ingredients_raw, str):
                # Extract ingredients from the string
                ingredients_text = product_ingredients_raw.strip()
                
                # Skip if empty
                if not ingredients_text:
                    continue
                
                # Try to find the actual ingredient list (after "Full Ingredients List:" or "Ingredients:")
                if "Full Ingredients List:" in ingredients_text:
                    ingredients_text = ingredients_text.split("Full Ingredients List:")[-1].strip()
                elif "Ingredients:" in ingredients_text:
                    ingredients_text = ingredients_text.split("Ingredients:")[-1].strip()
                
                # Clean up escaped backslashes (\\\\ becomes \)
                ingredients_text = ingredients_text.replace("\\\\", "\\")
                # Replace backslashes with commas for parsing (Water\\Aqua\\Eau -> Water, Aqua, Eau)
                ingredients_text = ingredients_text.replace("\\", ", ")
                
                # Parse the ingredients string using the same parser
                product_ingredients = parse_inci_string(ingredients_text)
            else:
                continue
            
            if not product_ingredients:
                continue
            
            # Normalize product ingredients (remove trailing punctuation for better matching)
            normalized_product_ingredients = []
            original_ingredient_map = {}  # Map normalized -> original for matching
            for ing in product_ingredients:
                if isinstance(ing, str):
                    # Clean: strip, remove trailing punctuation, lowercase
                    cleaned = ing.strip().rstrip('.,;!?').strip()
                    if cleaned:
                        normalized = cleaned.lower()
                        normalized_product_ingredients.append(normalized)
                        original_ingredient_map[normalized] = ing.strip()  # Keep original for display
                elif isinstance(ing, dict) and "name" in ing:
                    cleaned = str(ing["name"]).strip().rstrip('.,;!?').strip()
                    if cleaned:
                        normalized = cleaned.lower()
                        normalized_product_ingredients.append(normalized)
                        original_ingredient_map[normalized] = str(ing["name"]).strip()
            
            # MARKET RESEARCH: Only match active ingredients
            # Skip this product if no active ingredients in input
            if len(input_actives) == 0:
                # No active ingredients to match, skip this product
                continue
            
            # Find matching ingredients - ONLY match active ingredients
            matched_ingredients = []
            matched_active_indices = set()  # Track which active ingredients were matched
            import re
            
            # Create a mapping from normalized active ingredient to its index in normalized_input_ingredients
            active_to_index_map = {}
            for idx, input_ing in enumerate(normalized_input_ingredients):
                if input_ing in input_actives:
                    active_to_index_map[input_ing] = idx
            
            # Only match active ingredients
            for active_ing in input_actives:
                input_clean = active_ing.strip()
                if not input_clean:
                    continue
                
                # Try to match this active ingredient with any product ingredient
                matched_this_active = False
                
                for prod_ing in normalized_product_ingredients:
                    prod_clean = prod_ing.strip()
                    if not prod_clean:
                        continue
                    
                    is_match = False
                    
                    # Multiple matching strategies (in order of preference):
                    # 1. Exact match
                    if input_clean == prod_clean:
                        is_match = True
                    # 2. Word boundary match - check if input is a complete word in product (most reliable)
                    elif len(input_clean) > 3:
                        # Use word boundaries for better matching
                        word_boundary_pattern = r'\b' + re.escape(input_clean) + r'\b'
                        if re.search(word_boundary_pattern, prod_clean, re.IGNORECASE):
                            is_match = True
                    # 3. Contains match (handles cases like "Niacinamide" matching "Niacinamide (Vitamin B3)")
                    # But only if the input is substantial (at least 4 chars) to avoid false matches
                    elif len(input_clean) >= 4:
                        if input_clean in prod_clean or prod_clean in input_clean:
                            is_match = True
                    # 4. For short ingredients (3 chars or less), only exact match
                    # This prevents false matches on very short strings
                    
                    if is_match:
                        # Get original ingredient name from map
                        original_ing = original_ingredient_map.get(prod_ing)
                        if original_ing and original_ing not in matched_ingredients:
                            matched_ingredients.append(original_ing)
                            # Track the index of this active ingredient
                            if active_ing in active_to_index_map:
                                matched_active_indices.add(active_to_index_map[active_ing])
                            matched_this_active = True
                            if len(matched_products) < 10:  # Log for first 10 matches for debugging
                                print(f"  ✓ Matched active: '{active_ing}' -> '{original_ing}' (product: {product.get('name', 'Unknown')[:30]})")
                        break  # Found a match for this active ingredient, move to next
                
                # Debug: log if we couldn't match this active
                if not matched_this_active and idx < 3:  # Log for first 3 products
                    print(f"  ✗ Could not match active '{active_ing}' in product {product.get('name', 'Unknown')[:30]}")
                    if len(normalized_product_ingredients) > 0:
                        print(f"    Product has {len(normalized_product_ingredients)} ingredients, sample: {normalized_product_ingredients[:3]}")
            
            # Calculate match percentage based ONLY on active ingredients
            matched_actives = []
            for matched_idx in matched_active_indices:
                if matched_idx < len(normalized_input_ingredients):
                    matched_ing_normalized = normalized_input_ingredients[matched_idx]
                    if matched_ing_normalized in input_actives:
                        matched_actives.append(matched_ing_normalized)
            
            # Match percentage is based only on active ingredients
            active_match_count = len(matched_actives)
            total_active_ingredients = len(input_actives)
            active_match_percentage = (active_match_count / total_active_ingredients * 100) if total_active_ingredients > 0 else 0
            
            # For compatibility, also calculate overall match (but we won't use it for filtering)
            match_count = active_match_count
            total_input_ingredients = len(input_actives)  # Only count actives
            match_percentage = active_match_percentage  # Same as active match percentage
            
            # MARKET RESEARCH: Include any product that has at least one active ingredient match
            # No percentage threshold - show all products with active ingredient matches
            should_include = active_match_count > 0
            
            # NEW: Category filtering - filter products by category if category was identified
            if should_include and primary_category and category_confidence in ["high", "medium"]:
                product_category = product.get("category", "").lower() if product.get("category") else ""
                product_subcategory = product.get("subcategory", "").lower() if product.get("subcategory") else ""
                
                # Check if product category matches identified category
                category_match = False
                
                # Direct category match
                if product_category and primary_category in product_category:
                    category_match = True
                elif product_subcategory and primary_category in product_subcategory:
                    category_match = True
                
                # Subcategory matching (more specific)
                if not category_match and subcategory:
                    if product_subcategory and subcategory in product_subcategory:
                        category_match = True
                    elif product_category and subcategory in product_category:
                        category_match = True
                
                # If category doesn't match, exclude the product
                if not category_match:
                    should_include = False
                    if len(matched_products) < 5:  # Debug for first 5
                        print(f"  ✗ Category mismatch: Product category '{product_category}' doesn't match '{primary_category}'")
            
            if len(matched_products) < 5:  # Debug for first 5
                print(f"  Product match (active only): {active_match_percentage:.1f}% | Actives: {len(matched_actives)}/{len(input_actives)} | Include: {should_include}")
            
            # Include products that have at least one active ingredient match AND pass category filter
            if should_include:
                matches_found += 1
                
                # Get product image - prioritize s3Image/s3Images, fallback to image/images
                image = None
                images = []
                
                # Try S3 images first (preferred)
                if "s3Image" in product and product["s3Image"]:
                    image = product["s3Image"]
                    if isinstance(image, str):
                        images = [image]
                
                if "s3Images" in product and product["s3Images"]:
                    if isinstance(product["s3Images"], list) and len(product["s3Images"]) > 0:
                        images = product["s3Images"]
                        if not image and images:
                            image = images[0]
                
                # Fallback to regular images if S3 not available
                if not image and "image" in product and product["image"]:
                    image = product["image"]
                    if isinstance(image, str) and image not in images:
                        images.insert(0, image)
                
                if "images" in product and product["images"]:
                    if isinstance(product["images"], list):
                        for img in product["images"]:
                            if img and img not in images:
                                images.append(img)
                        if not image and images:
                            image = images[0]
                
                # Since we only match active ingredients, all matched ingredients should be active
                # But we verify by checking the INCI collection to get the actual active ingredient names
                matched_ingredients_normalized = [ing.strip().lower() for ing in matched_ingredients]
                active_ingredients = []
                
                if matched_ingredients_normalized:
                    try:
                        # Query INCI collection for categories to verify and get proper names
                        inci_query = {
                            "inciName_normalized": {"$in": matched_ingredients_normalized}
                        }
                        inci_cursor = inci_col.find(inci_query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                        inci_results = await inci_cursor.to_list(length=None)
                        
                        # Build mapping of normalized name -> category and INCI name
                        inci_category_map = {}
                        inci_name_map = {}
                        for inci_doc in inci_results:
                            normalized = inci_doc.get("inciName_normalized", "").strip().lower()
                            category = inci_doc.get("category", "")
                            inci_name = inci_doc.get("inciName", "")
                            if normalized and category:
                                inci_category_map[normalized] = category
                                inci_name_map[normalized] = inci_name
                        
                        # Collect active ingredients from matched ingredients
                        for matched_ing in matched_ingredients:
                            normalized = matched_ing.strip().lower()
                            if normalized in inci_category_map:
                                category = inci_category_map[normalized]
                                if category == "Active":
                                    # Use proper INCI name if available, otherwise use matched name
                                    active_name = inci_name_map.get(normalized, matched_ing)
                                    if active_name not in active_ingredients:
                                        active_ingredients.append(active_name)
                    except Exception as e:
                        print(f"  Warning: Error checking active ingredients: {e}")
                        # Fallback: use matched ingredients as active ingredients
                        active_ingredients = matched_ingredients.copy()
                else:
                    # No matched ingredients, so no active ingredients
                    active_ingredients = []
                
                # active_match_count is the number of input active ingredients that were matched
                active_match_count = len(matched_actives)
                
                # Build product data using correct field names from schema
                product_data = {
                    "id": str(product.get("_id", "")),  # Use 'id' instead of '_id' for Pydantic
                    "productName": product.get("name") or product.get("productName") or product.get("product_name"),
                    "brand": product.get("brand") or product.get("brandName") or product.get("brand_name"),
                    "ingredients": product_ingredients,  # Now it's a parsed list
                    "image": image,
                    "images": images,
                    "price": product.get("price"),
                    "salePrice": product.get("salePrice") or product.get("sale_price"),
                    "description": product.get("description"),
                    "matched_ingredients": matched_ingredients,  # All matched ingredients (should be active)
                    "match_count": active_match_count,  # Number of input active ingredients matched
                    "total_ingredients": len(product_ingredients),
                    "match_percentage": round(active_match_percentage, 2),  # Active match percentage
                    "match_score": round(active_match_percentage, 2),  # Use active match percentage as score
                    "active_match_count": active_match_count,  # Number of active ingredients matched
                    "active_ingredients": active_ingredients  # List of matched active ingredients (verified from INCI)
                }
                
                # Add any other fields from the product (excluding unwanted fields)
                # Exclude: countryOfOrigin, manufacturer, expiryDate, address, and similar fields
                excluded_fields = {
                    "countryOfOrigin", "manufacturer", "expiryDate", "expiry", 
                    "address", "Address", "Expiry Date", "Country of Origin", 
                    "Manufacturer", "Address:", "Expiry Date:", "Country of Origin:"
                }
                for key in ["category", "subcategory", "url"]:
                    if key in product and key not in excluded_fields:
                        product_data[key] = product[key]
                
                # Also filter out any unwanted fields that might be in the product dict
                # Clean description if it contains unwanted info
                if "description" in product_data and product_data["description"]:
                    desc = product_data["description"]
                    # Remove patterns like "Expiry Date: ...", "Country of Origin: ...", etc.
                    import re
                    patterns_to_remove = [
                        r"Expiry Date:\s*[^\n]*",
                        r"Country of Origin:\s*[^\n]*",
                        r"Manufacturer:\s*[^\n]*",
                        r"Address:\s*[^\n]*",
                        r"&nbsp;",
                    ]
                    for pattern in patterns_to_remove:
                        desc = re.sub(pattern, "", desc, flags=re.IGNORECASE)
                    # Clean up extra whitespace
                    desc = re.sub(r"\s+", " ", desc).strip()
                    if desc:
                        product_data["description"] = desc
                    else:
                        # If description becomes empty after cleaning, remove it
                        product_data.pop("description", None)
                
                matched_products.append(product_data)
        
        # AI-Powered Product Ranking (optional enhancement)
        # Use AI to re-rank products based on intelligent analysis
        if claude_client and len(matched_products) > 0 and len(input_actives) > 0:
            try:
                print(f"\n{'='*60}")
                print("AI-Powered Product Ranking...")
                print(f"{'='*60}")
                matched_products = await enhance_product_ranking_with_ai(
                    matched_products,
                    input_actives,
                    ingredients
                )
                print(f"  ✓ AI-enhanced ranking completed")
            except Exception as e:
                print(f"  ⚠️  Error in AI ranking (using default ranking): {e}")
        
        # Sort by: 1) match_percentage (descending - active match percentage), 2) active_match_count (descending)
        # This prioritizes products with highest active ingredient match percentage
        matched_products.sort(
            key=lambda x: (
                x.get("match_percentage", 0),  # Primary sort: active match percentage
                x.get("active_match_count", 0),  # Secondary: number of active matches
            ),
            reverse=True
        )
        
        # Return ALL matched products (no pagination in POST API - pagination is handled by GET detail endpoint)
        total_matched_count = len(matched_products)
        
        processing_time = time.time() - start
        
        # NEW: Generate market research overview using AI (always generate, never null)
        print(f"\n{'='*60}")
        print("Generating Market Research Overview...")
        print(f"{'='*60}")
        try:
            market_research_overview = await generate_market_research_overview_with_ai(
                ingredients,
                matched_products[:50],  # Use top 50 for overview generation
                category_info,
                total_matched_count
            )
            # Ensure overview is never None (function should always return a string)
            if not market_research_overview:
                market_research_overview = f"Market Research Overview\n\nFound {total_matched_count} matching products. Review the product list for detailed ingredient matches and formulations."
            print(f"  ✓ Market research overview generated ({len(market_research_overview)} characters)")
        except Exception as e:
            print(f"  ⚠️  Error generating market research overview: {e}")
            import traceback
            traceback.print_exc()
            # Fallback overview on error
            category = category_info.get('primary_category', 'product')
            subcategory = category_info.get('subcategory', 'product')
            market_research_overview = f"Market Research Overview\n\nFound {total_matched_count} matching {category} {subcategory} products. An error occurred while generating the detailed overview. Review the product list for specific ingredient matches and formulations."
        
        print(f"\n{'='*60}")
        print(f"Market Research Summary (Active Ingredients Only):")
        print(f"  Input type: {input_type}")
        print(f"  Extracted ingredients: {len(ingredients)}")
        print(f"  Active ingredients to match: {len(input_actives)}")
        print(f"  Sample active ingredients: {input_actives[:5] if input_actives else 'None'}")
        print(f"  Products in database: {len(all_products)}")
        print(f"  Total products matched: {total_matched_count}")
        if len(matched_products) > 0:
            top_match = matched_products[0]
            print(f"  Top match: {top_match.get('productName', 'Unknown')[:50]}")
            print(f"    - Active match count: {top_match.get('active_match_count', 0)}/{len(input_actives)}")
            print(f"    - Active match percentage: {top_match.get('match_percentage', 0)}%")
            print(f"    - Matched active ingredients: {top_match.get('active_ingredients', [])[:5]}")
        else:
            print(f"  ⚠️  WARNING: No products matched with active ingredients!")
            if len(all_products) > 0:
                print(f"  Debug: Checked {len(all_products)} products but found no matches")
                print(f"  Debug: Active ingredients searched: {input_actives[:5] if input_actives else 'None'}")
                if len(input_actives) == 0:
                    print(f"  Debug: No active ingredients found in input - market research requires active ingredients")
            else:
                print(f"  Debug: No products found in database to check")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"{'='*60}\n")
        
        # Debug: Log what we're returning
        print(f"\n📤 Returning response with enhanced AI analysis:")
        print(f"  ai_analysis: {ai_analysis_message}")
        print(f"  ai_reasoning: {ai_reasoning}")
        print(f"  ai_interpretation: {ai_interpretation}")
        print(f"  primary_category: {primary_category}")
        print(f"  subcategory: {subcategory}")
        print(f"  category_confidence: {category_confidence}")
        print(f"  market_research_overview: {'Generated' if market_research_overview else 'Not generated'}")
        print(f"  returning all {total_matched_count} products (pagination handled by GET detail endpoint)")
        
        response = MarketResearchResponse(
            products=matched_products,  # Return ALL products (no pagination in POST API)
            extracted_ingredients=ingredients,
            total_matched=total_matched_count,
            processing_time=round(processing_time, 2),
            input_type=input_type,
            ai_analysis=ai_analysis_message,  # AI analysis message
            ai_reasoning=ai_reasoning,  # AI reasoning for ingredient selection
            # New fields
            ai_interpretation=ai_interpretation,  # AI interpretation of input
            primary_category=primary_category,  # Primary category (haircare, skincare, etc.)
            subcategory=subcategory,  # Subcategory (serum, cleanser, etc.)
            category_confidence=category_confidence,  # Confidence level
            market_research_overview=market_research_overview,  # Comprehensive overview
            # Pagination fields (deprecated - kept for backward compatibility, but not used)
            page=1,
            page_size=total_matched_count,
            total_pages=1
        )
        
        # 🔹 Auto-save: Update history with completed status and research_result
        if history_id and user_id_value:
            try:
                # Convert response to dict for storage
                research_result_dict = response.dict()
                # ⚠️ IMPORTANT: Save ALL products, not just paginated ones for proper pagination later
                research_result_dict["products"] = matched_products  # Save all products, not paginated_products
                
                update_doc = {
                    "research_result": research_result_dict,
                    "ai_analysis": ai_analysis_message,
                    "ai_reasoning": ai_reasoning,
                    "ai_interpretation": ai_interpretation,
                    "primary_category": primary_category,
                    "subcategory": subcategory,
                    "category_confidence": category_confidence
                }
                
                await market_research_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with research results (saved {len(matched_products)} total products)")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in market research: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to perform market research: {str(e)}"
        )
    finally:
        if scraper:
            try:
                await scraper.close()
            except:
                pass


# API 1: Fast Products Endpoint (no overview generation)
@router.post("/market-research/products", response_model=MarketResearchProductsResponse)
async def market_research_products(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Market Research Products: Fast endpoint that returns matched products and category info.
    
    This is the optimized split API endpoint that returns products quickly without generating
    the comprehensive overview. Use this for fast product listing and pagination.
    
    For detailed market research overview, call /market-research/overview separately.
    
    Request body:
    {
        "url": "https://example.com/product/..." (required if input_type is "url"),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci"),
        "input_type": "url" or "inci",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional)
    }
    
    Returns:
    {
        "products": [ALL matched products],
        "extracted_ingredients": [list of ingredients],
        "total_matched": total number of matched products,
        "processing_time": time taken (typically 10-15s, no overview generation),
        "input_type": "url" or "inci",
        "ai_interpretation": "AI interpretation of category determination",
        "primary_category": "haircare" | "skincare" | etc.,
        "subcategory": "serum" | "cleanser" | etc.,
        "category_confidence": "high" | "medium" | "low",
        "ai_analysis": "AI analysis (only when no actives found)",
        "ai_reasoning": "AI reasoning (only when no actives found)"
    }
    
    Note: This endpoint does NOT include market_research_overview. 
    Call /market-research/overview separately if you need the comprehensive overview.
    
    Note: This POST endpoint returns ALL products. For pagination, use GET /market-research-history/{history_id}/details?page=1&page_size=10
    
    AUTO-SAVE: Results are automatically saved to market research history if user is authenticated.
    Provide optional "name" and "tag" in payload to customize the saved history item.
    """
    start = time.time()
    scraper = None
    
    # 🔹 Auto-save: Extract user info and optional name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = payload.get("name")  # Optional: custom name for history
    tag = payload.get("tag")  # Optional: tag for history
    notes = payload.get("notes")  # Optional: notes for history
    provided_history_id = payload.get("history_id")  # Optional: reuse existing history item
    history_id = None
    
    # Validate history_id if provided
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await market_research_history_col.find_one({
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
        # Validate payload
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'")
        
        ingredients = []
        extracted_text = ""
        input_data_value = ""  # For auto-save
        
        if input_type == "url":
            url = payload.get("url", "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="url is required when input_type is 'url'")
            
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
            
            # Initialize URL scraper and extract ingredients
            scraper = URLScraper()
            print(f"Scraping URL for market research products: {url}")
            extraction_result = await scraper.extract_ingredients_from_url(url)
            
            # Get ingredients - could be list or string, ensure it's a list
            ingredients_raw = extraction_result.get("ingredients", [])
            extracted_text = extraction_result.get("extracted_text", "")
            scraper_extraction_result = extraction_result
            
            # If ingredients is a string, parse it
            if isinstance(ingredients_raw, str):
                ingredients = parse_inci_string(ingredients_raw)
            elif isinstance(ingredients_raw, list):
                ingredients = ingredients_raw
            else:
                ingredients = []
            
            print(f"Extracted ingredients from URL: {ingredients}")
            
            if not ingredients:
                raise HTTPException(
                    status_code=404,
                    detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
                )
            
            input_data_value = url  # Store URL for auto-save
        elif input_type == "inci":
            # INCI input
            inci = payload.get("inci", "").strip()
            if not inci:
                raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'")
            
            # Parse INCI string
            ingredients = parse_inci_string(inci)
            extracted_text = inci
            input_data_value = inci  # Store INCI for auto-save
            
            if not ingredients:
                raise HTTPException(
                    status_code=400,
                    detail="No valid ingredients found after parsing. Please check your input format."
                )
        
        # Query externalproducts collection
        external_products_col = db["externalproducts"]
        collection_name = "externalproducts"
        print(f"✅ Using collection: {collection_name}")
        
        print(f"Extracted {len(ingredients)} ingredients for market research")
        print(f"Ingredients list: {ingredients}")
        
        # Normalize ingredients for matching
        import re
        normalized_input_ingredients = []
        for ing in ingredients:
            if ing and ing.strip():
                normalized = re.sub(r"\s+", " ", ing.strip()).strip().lower()
                if normalized:
                    normalized_input_ingredients.append(normalized)
        
        # Remove duplicates while preserving order
        seen = set()
        normalized_input_ingredients = [x for x in normalized_input_ingredients if not (x in seen or seen.add(x))]
        
        print(f"Normalized {len(ingredients)} input ingredients to {len(normalized_input_ingredients)} unique normalized ingredients")
        
        # 🔹 Auto-save: Save initial state if user_id provided and no existing history_id
        if user_id_value and not history_id and input_data_value:
            try:
                # Check if a history item with the same input_data already exists for this user
                existing_history_item = await market_research_history_col.find_one({
                    "user_id": user_id_value,
                    "input_type": input_type,
                    "input_data": input_data_value
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same input_data, reusing history_id: {history_id}")
                else:
                    # Generate default name if not provided
                    display_name = name
                    if not display_name:
                        if input_type == "url":
                            # Extract product name from URL
                            from urllib.parse import unquote
                            try:
                                url_decoded = unquote(input_data_value)
                                segments = url_decoded.split('/')
                                for segment in reversed(segments):
                                    segment = segment.split('?')[0].replace('-', ' ').replace('_', ' ')
                                    if segment and len(segment) > 5 and len(segment) < 100:
                                        if any(keyword in segment.lower() for keyword in ['cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner']):
                                            display_name = segment.title() + " Research"
                                            break
                            except:
                                pass
                        if not display_name:
                            # Use first ingredient or default
                            if ingredients and len(ingredients) > 0:
                                display_name = ingredients[0] + " Research"
                            else:
                                display_name = "Market Research"
                    
                    # Truncate if too long
                    if len(display_name) > 100:
                        display_name = display_name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": display_name,
                        "tag": tag,
                        "input_type": input_type,
                        "input_data": input_data_value,
                        "notes": notes,
                        "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
                    }
                    result = await market_research_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                # Continue with research even if saving fails
        
        # Initialize AI analysis variables
        ai_analysis_message = None
        ai_reasoning = None
        
        # AI Category Analysis - RUNS ONCE PER REQUEST
        # This analysis determines the product category and subcategory based on the input ingredients.
        print(f"\n{'='*60}")
        print("STEP 0: AI Category Analysis...")
        print(f"{'='*60}")
        category_info = {
            "primary_category": None,
            "subcategory": None,
            "interpretation": None,
            "confidence": "low"
        }
        
        if claude_client and ingredients:
            try:
                # Extract product name from URL if available
                product_name = ""
                if input_type == "url":
                    url = payload.get("url", "")
                    if 'scraper_extraction_result' in locals() and scraper_extraction_result:
                        product_name = scraper_extraction_result.get("product_name", "")
                    
                    if not product_name:
                        if extracted_text:
                            lines = extracted_text.split('\n')[:30]
                            for line in lines:
                                line_lower = line.lower()
                                if any(keyword in line_lower for keyword in ['product', 'name', 'title', 'cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner']):
                                    cleaned = line.strip()[:150]
                                    for prefix in ['product name:', 'product:', 'name:', 'title:']:
                                        if cleaned.lower().startswith(prefix):
                                            cleaned = cleaned[len(prefix):].strip()
                                    if cleaned and len(cleaned) > 3:
                                        product_name = cleaned
                                        break
                        
                        if not product_name and url:
                            from urllib.parse import unquote
                            try:
                                url_decoded = unquote(url)
                                segments = url_decoded.split('/')
                                for segment in reversed(segments):
                                    segment = segment.split('?')[0].replace('-', ' ').replace('_', ' ')
                                    if segment and len(segment) > 5 and len(segment) < 100:
                                        if any(keyword in segment.lower() for keyword in ['cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner', 'face', 'hair', 'lip']):
                                            product_name = segment.title()
                                            break
                            except:
                                pass
                
                print(f"  🤖 Calling AI for category analysis...")
                if product_name:
                    print(f"  📝 Product name/context: {product_name[:100]}")
                url_for_ai = url if input_type == "url" else ""
                if url_for_ai:
                    print(f"  🔗 Product URL: {url_for_ai[:100]}")
                category_info = await analyze_product_categories_with_ai(
                    ingredients,
                    normalized_input_ingredients,
                    extracted_text[:1000] if extracted_text else "",
                    product_name,
                    url_for_ai
                )
                print(f"  ✓ Category analysis completed")
            except Exception as e:
                print(f"  ⚠️  Error in AI category analysis: {e}")
                import traceback
                traceback.print_exc()
        
        primary_category = category_info.get("primary_category")
        subcategory = category_info.get("subcategory")
        ai_interpretation = category_info.get("interpretation")
        category_confidence = category_info.get("confidence", "low")
        
        # Categorize input ingredients into actives and excipients
        print(f"\n{'='*60}")
        print("STEP 1.5: Categorizing input ingredients...")
        print(f"{'='*60}")
        input_actives = []
        input_excipients = []
        input_unknown = []
        
        if normalized_input_ingredients:
            try:
                inci_query = {
                    "inciName_normalized": {"$in": normalized_input_ingredients}
                }
                print(f"  Querying INCI collection with {len(normalized_input_ingredients)} normalized ingredients...")
                inci_cursor = inci_col.find(inci_query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
                inci_results = await inci_cursor.to_list(length=None)
                print(f"  Found {len(inci_results)} INCI records in database")
                
                # Build category map
                input_category_map = {}
                for result in inci_results:
                    norm_name = result.get("inciName_normalized")
                    category = result.get("category", "").lower() if result.get("category") else ""
                    if norm_name:
                        input_category_map[norm_name] = category
                
                # Categorize ingredients
                for norm_ing in normalized_input_ingredients:
                    category = input_category_map.get(norm_ing, "").lower()
                    if category == "active":
                        input_actives.append(norm_ing)
                    elif category == "excipient":
                        input_excipients.append(norm_ing)
                    else:
                        input_unknown.append(norm_ing)
                
                print(f"  Categorized ingredients:")
                print(f"    - Actives: {len(input_actives)}")
                print(f"    - Excipients: {len(input_excipients)}")
                print(f"    - Unknown: {len(input_unknown)}")
                
            except Exception as e:
                print(f"  ⚠️  Error categorizing ingredients: {e}")
                input_unknown = normalized_input_ingredients.copy()
                print(f"  Fallback: Treating all {len(input_unknown)} ingredients as unknown")
        
        # If no actives found, use AI to analyze formulation
        if len(input_actives) == 0:
            print(f"\n⚠️  No active ingredients found in database lookup!")
            print(f"  Using AI to analyze formulation and suggest matching strategy...")
            
            if claude_client and normalized_input_ingredients:
                print(f"  🤖 Calling Claude AI to analyze formulation...")
                try:
                    ai_analysis = await analyze_formulation_and_suggest_matching_with_ai(
                        ingredients,
                        normalized_input_ingredients,
                        input_category_map
                    )
                    
                    if ai_analysis:
                        analysis_val = ai_analysis.get("analysis")
                        ai_analysis_message = analysis_val if analysis_val and analysis_val.strip() else None
                        
                        reasoning_val = ai_analysis.get("reasoning")
                        ai_reasoning = reasoning_val if reasoning_val and reasoning_val.strip() else None
                        
                        print(f"  📊 AI Analysis stored: {ai_analysis_message}")
                        print(f"  💭 AI Reasoning stored: {ai_reasoning}")
                    
                    if ai_analysis and ai_analysis.get("ingredients_to_match"):
                        ai_identified_actives = ai_analysis.get("ingredients_to_match", [])
                        print(f"  ✓ AI suggested {len(ai_identified_actives)} ingredients to match: {ai_identified_actives[:5]}")
                        input_actives.extend(ai_identified_actives)
                        
                        if ai_analysis_message:
                            print(f"  AI Message: {ai_analysis_message}")
                except Exception as e:
                    print(f"  ❌ Error using AI to analyze formulation: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Fetch all products
        try:
            all_products = await external_products_col.find({
                "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
            }).to_list(length=None)
            
            print(f"✅ Fetched {len(all_products)} products to check")
            
            if len(all_products) == 0:
                fallback_overview = f"Market Research Overview\n\nNo products found in the database to match against. Please ensure the database contains product data with ingredient information."
                
                return MarketResearchProductsResponse(
                    products=[],
                    extracted_ingredients=ingredients,
                    total_matched=0,
                    processing_time=round(time.time() - start, 2),
                    input_type=input_type,
                    ai_analysis=ai_analysis_message,
                    ai_reasoning=ai_reasoning,
                    ai_interpretation=ai_interpretation,
                    primary_category=primary_category,
                    subcategory=subcategory,
                    category_confidence=category_confidence
                )
        except Exception as e:
            print(f"\n❌ ERROR fetching products: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch products from database: {str(e)}"
            )
        
        if len(input_actives) == 0:
            return MarketResearchProductsResponse(
                products=[],
                extracted_ingredients=ingredients,
                total_matched=0,
                processing_time=round(time.time() - start, 2),
                input_type=input_type,
                ai_analysis=ai_analysis_message,
                ai_reasoning=ai_reasoning,
                ai_interpretation=ai_interpretation,
                primary_category=primary_category,
                subcategory=subcategory,
                category_confidence=category_confidence
            )
        
        # Match products
        print(f"\n{'='*60}")
        print("STEP 2: Matching products...")
        print(f"{'='*60}")
        matched_products = []
        
        for product in all_products:
            product_ingredients = product.get("ingredients", "")
            if not product_ingredients:
                continue
            
            # Parse product ingredients
            if isinstance(product_ingredients, str):
                product_ing_list = parse_inci_string(product_ingredients)
            elif isinstance(product_ingredients, list):
                product_ing_list = product_ingredients
            else:
                continue
            
            # Normalize product ingredients
            normalized_product_ings = []
            for ing in product_ing_list:
                if ing and ing.strip():
                    normalized = re.sub(r"\s+", " ", ing.strip()).strip().lower()
                    if normalized:
                        normalized_product_ings.append(normalized)
            
            # Find matching actives
            matched_actives = [ing for ing in input_actives if ing in normalized_product_ings]
            active_match_count = len(matched_actives)
            
            if active_match_count > 0:
                # Calculate match percentage
                active_match_percentage = (active_match_count / len(input_actives)) * 100
                
                # Category filtering
                should_include = True
                if primary_category and category_confidence in ["high", "medium"]:
                    product_category = product.get("category", "").lower() if product.get("category") else ""
                    product_subcategory = product.get("subcategory", "").lower() if product.get("subcategory") else ""
                    
                    category_match = False
                    if product_category and primary_category in product_category:
                        category_match = True
                    elif product_subcategory and primary_category in product_subcategory:
                        category_match = True
                    
                    if not category_match and subcategory:
                        if product_subcategory and subcategory in product_subcategory:
                            category_match = True
                        elif product_category and subcategory in product_category:
                            category_match = True
                    
                    if not category_match:
                        should_include = False
                
                if should_include:
                    product_data = {
                        "id": str(product.get("_id", "")),
                        "productName": product.get("productName") or product.get("name", "Unknown"),
                        "brand": product.get("brand", ""),
                        "category": product.get("category", ""),
                        "subcategory": product.get("subcategory", ""),
                        "match_percentage": round(active_match_percentage, 1),
                        "active_match_count": active_match_count,
                        "active_ingredients": matched_actives,
                        "total_ingredients": len(normalized_product_ings),
                        "image": product.get("image") or product.get("productImage", ""),
                        "price": product.get("price"),
                        "url": product.get("url", ""),
                        "description": product.get("description", "")
                    }
                    
                    # Clean description
                    if product_data.get("description"):
                        desc = product_data["description"]
                        patterns_to_remove = [
                            r"Expiry Date:\s*[^\n]*",
                            r"Country of Origin:\s*[^\n]*",
                            r"Manufacturer:\s*[^\n]*",
                            r"Address:\s*[^\n]*",
                            r"&nbsp;",
                        ]
                        for pattern in patterns_to_remove:
                            desc = re.sub(pattern, "", desc, flags=re.IGNORECASE)
                        desc = re.sub(r"\s+", " ", desc).strip()
                        if desc:
                            product_data["description"] = desc
                        else:
                            product_data.pop("description", None)
                    
                    matched_products.append(product_data)
        
        # AI-Powered Product Ranking (optional)
        if claude_client and len(matched_products) > 0 and len(input_actives) > 0:
            try:
                print(f"\n{'='*60}")
                print("AI-Powered Product Ranking...")
                print(f"{'='*60}")
                matched_products = await enhance_product_ranking_with_ai(
                    matched_products,
                    input_actives,
                    ingredients
                )
                print(f"  ✓ AI-enhanced ranking completed")
            except Exception as e:
                print(f"  ⚠️  Error in AI ranking (using default ranking): {e}")
        
        # Sort by match percentage
        matched_products.sort(
            key=lambda x: (
                x.get("match_percentage", 0),
                x.get("active_match_count", 0),
            ),
            reverse=True
        )
        
        # Return ALL matched products (no pagination in POST API - pagination is handled by GET detail endpoint)
        total_matched_count = len(matched_products)
        
        processing_time = time.time() - start
        
        print(f"\n{'='*60}")
        print(f"Market Research Products Summary:")
        print(f"  Total products matched: {total_matched_count}")
        print(f"  Returning all {total_matched_count} products (pagination handled by GET detail endpoint)")
        print(f"  Category: {primary_category}/{subcategory}")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"{'='*60}\n")
        
        # Return response with ALL products (no pagination in POST API)
        response = MarketResearchProductsResponse(
            products=matched_products,  # Return ALL products (no pagination in POST API)
            extracted_ingredients=ingredients,
            total_matched=total_matched_count,
            processing_time=round(processing_time, 2),
            input_type=input_type,
            ai_analysis=ai_analysis_message,
            ai_reasoning=ai_reasoning,
            ai_interpretation=ai_interpretation,
            primary_category=primary_category,
            subcategory=subcategory,
            category_confidence=category_confidence,
            # Pagination fields (deprecated - kept for backward compatibility, but not used)
            page=1,
            page_size=total_matched_count,
            total_pages=1
        )
        
        # 🔹 Auto-save: Update history with completed status and research_result
        if history_id and user_id_value:
            try:
                # Convert response to dict for storage
                research_result_dict = response.dict()
                # ⚠️ IMPORTANT: Save ALL products, not just paginated ones for proper pagination later
                research_result_dict["products"] = matched_products  # Save all products, not paginated_products
                
                update_doc = {
                    "research_result": research_result_dict,
                    "ai_analysis": ai_analysis_message,
                    "ai_reasoning": ai_reasoning,
                    "ai_interpretation": ai_interpretation,
                    "primary_category": primary_category,
                    "subcategory": subcategory,
                    "category_confidence": category_confidence
                }
                
                await market_research_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with research results (saved {len(matched_products)} total products)")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in market research products: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to perform market research: {str(e)}"
        )
    finally:
        if scraper:
            try:
                await scraper.close()
            except:
                pass


# API 2: Overview Endpoint (detailed analysis)
@router.post("/market-research/overview", response_model=MarketResearchOverviewResponse)
async def market_research_overview(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Market Research Overview: Generate comprehensive AI-powered overview of market research findings.
    
    This endpoint generates a detailed market research overview based on the input formulation.
    It can optionally use pre-computed category info to avoid re-analysis.
    
    Request body:
    {
        "input_type": "url" or "inci",
        "url": "https://example.com/product/..." (required if input_type is "url"),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci"),
        "primary_category": "skincare" (optional, if already known),
        "subcategory": "cleanser" (optional, if already known),
        "category_confidence": "high" (optional, if already known)
    }
    
    Returns:
    {
        "market_research_overview": "Comprehensive AI-generated overview with summary, key findings, trends, insights, and recommendations",
        "processing_time": time taken (typically 5-8s),
        "history_id": "History item ID if saved (optional)"
    }
    
    Note: This endpoint requires matching products to generate a meaningful overview.
    If no products are found, it will return a basic overview message.
    """
    start = time.time()
    scraper = None
    
    try:
        # Validate payload
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'")
        
        ingredients = []
        extracted_text = ""
        
        if input_type == "url":
            url = payload.get("url", "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="url is required when input_type is 'url'")
            
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
            
            scraper = URLScraper()
            print(f"Scraping URL for market research overview: {url}")
            extraction_result = await scraper.extract_ingredients_from_url(url)
            
            ingredients_raw = extraction_result.get("ingredients", [])
            extracted_text = extraction_result.get("extracted_text", "")
            
            if isinstance(ingredients_raw, str):
                ingredients = parse_inci_string(ingredients_raw)
            elif isinstance(ingredients_raw, list):
                ingredients = ingredients_raw
            else:
                ingredients = []
            
            if not ingredients:
                raise HTTPException(
                    status_code=404,
                    detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
                )
        elif input_type == "inci":
            inci = payload.get("inci", "").strip()
            if not inci:
                raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'")
            
            ingredients = parse_inci_string(inci)
            extracted_text = inci
            
            if not ingredients:
                raise HTTPException(
                    status_code=400,
                    detail="No valid ingredients found after parsing. Please check your input format."
                )
        
        # Normalize ingredients
        import re
        normalized_input_ingredients = []
        for ing in ingredients:
            if ing and ing.strip():
                normalized = re.sub(r"\s+", " ", ing.strip()).strip().lower()
                if normalized:
                    normalized_input_ingredients.append(normalized)
        
        seen = set()
        normalized_input_ingredients = [x for x in normalized_input_ingredients if not (x in seen or seen.add(x))]
        
        # Get category info (use provided or analyze)
        category_info = {
            "primary_category": payload.get("primary_category"),
            "subcategory": payload.get("subcategory"),
            "interpretation": None,
            "confidence": payload.get("category_confidence", "low")
        }
        
        # If category info not provided, analyze it
        if not category_info.get("primary_category") and claude_client and ingredients:
            try:
                print(f"\n{'='*60}")
                print("AI Category Analysis for Overview...")
                print(f"{'='*60}")
                
                product_name = ""
                if input_type == "url":
                    url = payload.get("url", "")
                    if extracted_text:
                        lines = extracted_text.split('\n')[:30]
                        for line in lines:
                            line_lower = line.lower()
                            if any(keyword in line_lower for keyword in ['product', 'name', 'title', 'cleanser', 'serum', 'moisturizer', 'shampoo', 'conditioner']):
                                cleaned = line.strip()[:150]
                                for prefix in ['product name:', 'product:', 'name:', 'title:']:
                                    if cleaned.lower().startswith(prefix):
                                        cleaned = cleaned[len(prefix):].strip()
                                if cleaned and len(cleaned) > 3:
                                    product_name = cleaned
                                    break
                
                url_for_ai = payload.get("url", "") if input_type == "url" else ""
                analyzed_category = await analyze_product_categories_with_ai(
                    ingredients,
                    normalized_input_ingredients,
                    extracted_text[:1000] if extracted_text else "",
                    product_name,
                    url_for_ai
                )
                
                category_info.update(analyzed_category)
                print(f"  ✓ Category analysis completed")
            except Exception as e:
                print(f"  ⚠️  Error in AI category analysis: {e}")
        
        # Get active ingredients for matching
        input_actives = []
        input_category_map = {}
        if normalized_input_ingredients:
            try:
                inci_query = {
                    "inciName_normalized": {"$in": normalized_input_ingredients}
                }
                inci_cursor = inci_col.find(inci_query, {"inciName_normalized": 1, "category": 1})
                inci_results = await inci_cursor.to_list(length=None)
                
                for result in inci_results:
                    norm_name = result.get("inciName_normalized")
                    category = result.get("category", "").lower() if result.get("category") else ""
                    if norm_name:
                        input_category_map[norm_name] = category
                
                for norm_ing in normalized_input_ingredients:
                    category = input_category_map.get(norm_ing, "").lower()
                    if category == "active":
                        input_actives.append(norm_ing)
            except Exception as e:
                print(f"  ⚠️  Error categorizing ingredients: {e}")
        
        # If no actives, try AI analysis
        if len(input_actives) == 0 and claude_client:
            try:
                ai_analysis = await analyze_formulation_and_suggest_matching_with_ai(
                    ingredients,
                    normalized_input_ingredients,
                    input_category_map
                )
                if ai_analysis and ai_analysis.get("ingredients_to_match"):
                    input_actives.extend(ai_analysis.get("ingredients_to_match", []))
            except Exception as e:
                print(f"  ⚠️  Error in AI analysis: {e}")
        
        # Fetch and match products (simplified - just get top matches for overview)
        matched_products = []
        try:
            external_products_col = db["externalproducts"]
            all_products = await external_products_col.find({
                "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
            }).to_list(length=None)
            
            if len(input_actives) > 0:
                for product in all_products:
                    product_ingredients = product.get("ingredients", "")
                    if not product_ingredients:
                        continue
                    
                    if isinstance(product_ingredients, str):
                        product_ing_list = parse_inci_string(product_ingredients)
                    elif isinstance(product_ingredients, list):
                        product_ing_list = product_ingredients
                    else:
                        continue
                    
                    normalized_product_ings = []
                    for ing in product_ing_list:
                        if ing and ing.strip():
                            normalized = re.sub(r"\s+", " ", ing.strip()).strip().lower()
                            if normalized:
                                normalized_product_ings.append(normalized)
                    
                    matched_actives = [ing for ing in input_actives if ing in normalized_product_ings]
                    if len(matched_actives) > 0:
                        active_match_percentage = (len(matched_actives) / len(input_actives)) * 100
                        
                        # Category filtering
                        should_include = True
                        primary_category = category_info.get("primary_category")
                        subcategory = category_info.get("subcategory")
                        category_confidence = category_info.get("confidence", "low")
                        
                        if primary_category and category_confidence in ["high", "medium"]:
                            product_category = product.get("category", "").lower() if product.get("category") else ""
                            product_subcategory = product.get("subcategory", "").lower() if product.get("subcategory") else ""
                            
                            category_match = False
                            if product_category and primary_category in product_category:
                                category_match = True
                            elif product_subcategory and primary_category in product_subcategory:
                                category_match = True
                            
                            if not category_match and subcategory:
                                if product_subcategory and subcategory in product_subcategory:
                                    category_match = True
                                elif product_category and subcategory in product_category:
                                    category_match = True
                            
                            if not category_match:
                                should_include = False
                        
                        if should_include:
                            product_data = {
                                "id": str(product.get("_id", "")),
                                "productName": product.get("productName") or product.get("name", "Unknown"),
                                "brand": product.get("brand", ""),
                                "category": product.get("category", ""),
                                "subcategory": product.get("subcategory", ""),
                                "match_percentage": round(active_match_percentage, 1),
                                "active_match_count": len(matched_actives),
                                "active_ingredients": matched_actives,
                                "total_ingredients": len(normalized_product_ings)
                            }
                            matched_products.append(product_data)
                
                # Sort by match percentage
                matched_products.sort(
                    key=lambda x: (x.get("match_percentage", 0), x.get("active_match_count", 0)),
                    reverse=True
                )
                matched_products = matched_products[:50]  # Top 50 for overview
        except Exception as e:
            print(f"  ⚠️  Error fetching products for overview: {e}")
        
        total_matched = len(matched_products)
        
        # Generate overview
        print(f"\n{'='*60}")
        print("Generating Market Research Overview...")
        print(f"{'='*60}")
        
        try:
            market_research_overview = await generate_market_research_overview_with_ai(
                ingredients,
                matched_products,
                category_info,
                total_matched
            )
            
            if not market_research_overview:
                category = category_info.get('primary_category', 'product')
                subcategory = category_info.get('subcategory', 'product')
                market_research_overview = f"Market Research Overview\n\nFound {total_matched} matching {category} {subcategory} products. Review the product list for detailed ingredient matches and formulations."
            
            print(f"  ✓ Market research overview generated ({len(market_research_overview)} characters)")
        except Exception as e:
            print(f"  ⚠️  Error generating market research overview: {e}")
            import traceback
            traceback.print_exc()
            category = category_info.get('primary_category', 'product')
            subcategory = category_info.get('subcategory', 'product')
            market_research_overview = f"Market Research Overview\n\nFound {total_matched} matching {category} {subcategory} products. An error occurred while generating the detailed overview. Review the product list for specific ingredient matches and formulations."
        
        processing_time = time.time() - start
        
        print(f"\n{'='*60}")
        print(f"Market Research Overview Summary:")
        print(f"  Total products matched: {total_matched}")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"{'='*60}\n")
        
        return MarketResearchOverviewResponse(
            market_research_overview=market_research_overview,
            processing_time=round(processing_time, 2),
            history_id=None  # Can be set if auto-save is implemented
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in market research overview: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate market research overview: {str(e)}"
        )
    finally:
        if scraper:
            try:
                await scraper.close()
            except:
                pass


