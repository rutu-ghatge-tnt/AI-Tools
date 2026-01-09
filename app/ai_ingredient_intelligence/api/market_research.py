"""
Market Research API Endpoints
==============================

API endpoints for market research functionality including:
- Market research history management
- Product matching and comparison
- AI-powered category analysis and overview generation

Extracted from analyze_inci.py for better modularity.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
import time
import os
import json
import re
import asyncio
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
    extract_structured_product_info_with_ai,
    claude_client  # Import claude_client directly
)
from app.ai_ingredient_intelligence.logic.serper_product_search import fetch_platforms
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
    ProductAnalysisRequest,
    ProductAnalysisResponse,
    ProductStructuredAnalysis,
    ProductKeywords,
    UpdateKeywordsRequest,
    UpdateKeywordsResponse,
    MarketResearchWithKeywordsRequest,
    MarketResearchPaginatedResponse,
    ActiveIngredient,
    FetchPlatformsRequest,
    FetchPlatformsResponse,
    PlatformInfo,
)

router = APIRouter(tags=["Market Research"])


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-inspiration-board")
async def export_market_research_to_board(
    request: dict,
    user_id: str = Query(..., description="User ID"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Export market research results to inspiration board"""
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
                    feature_type="market_research",
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
        print(f"ERROR exporting market research to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXISTING ENDPOINTS CONTINUE...
# ============================================================================

# REMOVED: POST /save-market-research-history endpoint
# This endpoint was disabled and has been removed.
# Market research endpoints now auto-save results to history.


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
            # Handle both string and list formats (some old data might be stored as list)
            input_data_raw = item.get("input_data", "")
            if isinstance(input_data_raw, list):
                input_data = ", ".join(str(x) for x in input_data_raw if x)
            elif isinstance(input_data_raw, str):
                input_data = input_data_raw
            else:
                input_data = str(input_data_raw) if input_data_raw else ""
            
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
            
            # Handle input_data - convert list to string if needed (for backward compatibility with old data)
            input_data_raw = item_meta.get("input_data", "")
            if isinstance(input_data_raw, list):
                item_meta["input_data"] = ", ".join(str(x) for x in input_data_raw if x)
            elif not isinstance(input_data_raw, str):
                item_meta["input_data"] = str(input_data_raw) if input_data_raw else ""
            
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
        
        # Handle input_data - convert list to string if needed (for backward compatibility with old data)
        input_data_raw = item_meta.get("input_data", "")
        if isinstance(input_data_raw, list):
            input_data = ", ".join(str(x) for x in input_data_raw if x)
        elif isinstance(input_data_raw, str):
            input_data = input_data_raw
        else:
            input_data = str(input_data_raw) if input_data_raw else ""
        
        # Build complete item
        item = {
            "id": str(item_meta["_id"]),
            "user_id": item_meta.get("user_id"),
            "name": item_meta.get("name"),
            "tag": item_meta.get("tag"),
            "input_type": item_meta.get("input_type"),
            "input_data": input_data,
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


async def fetch_platforms_background(history_id: str, user_id: str):
    """
    Background task to fetch platforms for a product after history update.
    Extracts product name from history and fetches platform links.
    """
    try:
        # Fetch the updated history item
        history_item = await market_research_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not history_item:
            print(f"[BACKGROUND] History item {history_id} not found, skipping platform fetch")
            return
        
        # Extract product name from history
        product_name = None
        
        # Try to get product name from name field
        if history_item.get("name"):
            product_name = history_item.get("name")
        
        # If not found, try to get from research_result products
        if not product_name:
            research_result = history_item.get("research_result", {})
            products = research_result.get("products", [])
            if products and len(products) > 0:
                # Get product name from first product
                first_product = products[0]
                product_name = first_product.get("productName") or first_product.get("name")
        
        # If still not found, try to get from input_data if it's a URL
        if not product_name:
            input_data = history_item.get("input_data", "")
            if input_data and isinstance(input_data, str) and input_data.startswith("http"):
                # Try to extract product name from URL or use a generic name
                # For now, we'll skip if we can't find a good product name
                print(f"[BACKGROUND] Could not extract product name from history {history_id}, skipping platform fetch")
                return
        
        if not product_name or not product_name.strip():
            print(f"[BACKGROUND] No valid product name found in history {history_id}, skipping platform fetch")
            return
        
        print(f"[BACKGROUND] Fetching platforms for product: {product_name}")
        
        # Fetch platforms (run sync function in thread pool to avoid blocking)
        platforms = await asyncio.to_thread(fetch_platforms, product_name.strip())
        
        # Update history with platforms data
        await market_research_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": {
                "platforms": platforms,
                "platforms_fetched_at": datetime.utcnow().isoformat()
            }}
        )
        
        print(f"[BACKGROUND] Successfully fetched and saved {len(platforms)} platforms for history {history_id}")
        
    except Exception as e:
        print(f"[BACKGROUND] Error fetching platforms for history {history_id}: {e}")
        import traceback
        traceback.print_exc()
        # Don't raise - background failures shouldn't affect user experience


@router.patch("/market-research-history/{history_id}")
async def update_market_research_history(
    history_id: str, 
    payload: dict,
    background_tasks: BackgroundTasks,
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
        
        # Trigger background task to fetch platforms
        background_tasks.add_task(fetch_platforms_background, history_id, user_id)
        
        return {
            "success": True,
            "message": "Market research history updated successfully. Platforms are being fetched in the background."
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
# NEW MARKET RESEARCH ENDPOINTS (Enhanced Flow)
# ============================================================================

def build_mongo_query_from_keywords(
    selected_keywords: Optional[ProductKeywords],
    structured_analysis: Optional[Dict],
    additional_filters: Optional[Dict] = None,
    collection_sample: Optional[Dict] = None
) -> Dict:
    """
    Build MongoDB query from selected keywords and structured analysis.
    
    Maps queries to externalproducts collection structure:
    - Top-level fields: form, application, functional_categories, main_category, subcategory, price, brand, category
    - Nested keywords object: keywords.form, keywords.target_area, keywords.product_type_id, 
      keywords.concerns, keywords.benefits, keywords.functionality, keywords.application,
      keywords.market_positioning, keywords.functional_categories, keywords.main_category,
      keywords.subcategory, keywords.mrp, keywords.price_tier
    
    Args:
        selected_keywords: Selected keywords organized by category
        structured_analysis: Structured analysis data
        additional_filters: Additional filters (price_range, brand, etc.)
        collection_sample: Sample product to check field existence
    
    Returns:
        MongoDB query dictionary
    """
    query = {}
    
    # Build $or conditions for fields that exist in both top-level and keywords object
    or_conditions = []
    
    # Always use category/subcategory (we know these exist at top-level)
    if structured_analysis:
        main_category = structured_analysis.get("main_category")
        subcategory = structured_analysis.get("subcategory")
        
        if main_category:
            # Query both top-level category and keywords.main_category
            or_conditions.append({"category": {"$regex": main_category, "$options": "i"}})
            or_conditions.append({"keywords.main_category": {"$regex": main_category, "$options": "i"}})
        
        if subcategory:
            # Query both top-level subcategory and keywords.subcategory
            or_conditions.append({"subcategory": {"$regex": subcategory, "$options": "i"}})
            or_conditions.append({"keywords.subcategory": {"$regex": subcategory, "$options": "i"}})
    
    # Process selected keywords
    if selected_keywords:
        # Product formulation keywords → form field (top-level and keywords.form)
        if selected_keywords.product_formulation:
            form_keywords = selected_keywords.product_formulation
            or_conditions.append({"form": {"$in": form_keywords}})
            or_conditions.append({"keywords.form": {"$in": form_keywords}})
        
        # Primary form → form field (top-level and keywords.form)
        if selected_keywords.form:
            or_conditions.append({"form": selected_keywords.form})
            or_conditions.append({"keywords.form": selected_keywords.form})
        
        # Application keywords → application field (top-level and keywords.application)
        if selected_keywords.application:
            app_keywords = selected_keywords.application
            or_conditions.append({"application": {"$in": app_keywords}})
            or_conditions.append({"keywords.application": {"$in": app_keywords}})
        
        # Functionality keywords → functional_categories field (top-level and keywords.functional_categories)
        # Also check keywords.functionality
        if selected_keywords.functionality:
            func_keywords = selected_keywords.functionality
            or_conditions.append({"functional_categories": {"$in": func_keywords}})
            or_conditions.append({"keywords.functional_categories": {"$in": func_keywords}})
            or_conditions.append({"keywords.functionality": {"$in": func_keywords}})
        
        # Benefits → keywords.benefits
        if selected_keywords.benefits:
            or_conditions.append({"keywords.benefits": {"$in": selected_keywords.benefits}})
        
        # Target area → keywords.target_area
        if selected_keywords.target_area:
            or_conditions.append({"keywords.target_area": selected_keywords.target_area})
        
        # Product type ID → keywords.product_type_id
        if selected_keywords.product_type_id:
            or_conditions.append({"keywords.product_type_id": selected_keywords.product_type_id})
        
        # Concerns → keywords.concerns
        if selected_keywords.concerns:
            or_conditions.append({"keywords.concerns": {"$in": selected_keywords.concerns}})
        
        # Market positioning → keywords.market_positioning
        if selected_keywords.market_positioning:
            or_conditions.append({"keywords.market_positioning": {"$in": selected_keywords.market_positioning}})
        
        # Price tier → keywords.price_tier
        if selected_keywords.price_tier:
            or_conditions.append({"keywords.price_tier": selected_keywords.price_tier})
        
        # MRP keywords → keywords.mrp (array of price tier IDs)
        if selected_keywords.mrp:
            or_conditions.append({"keywords.mrp": {"$in": selected_keywords.mrp}})
        
        # MRP value → price range filter (using top-level price field)
        if selected_keywords.mrp and structured_analysis:
            mrp_value = structured_analysis.get("mrp")
            
            if mrp_value:
                # Convert keywords to price ranges
                price_min = mrp_value * 0.8  # 20% below
                price_max = mrp_value * 1.2  # 20% above
                
                # Adjust based on keywords (Formulynx price tier IDs)
                mrp_keywords = selected_keywords.mrp
                if "prestige" in mrp_keywords:
                    price_min = max(price_min, 1500)
                elif "premium" in mrp_keywords:
                    price_min = max(price_min, 700)
                    price_max = min(price_max, 1500)
                elif "masstige" in mrp_keywords:
                    price_min = max(price_min, 300)
                    price_max = min(price_max, 700)
                elif "mass_market" in mrp_keywords:
                    price_max = min(price_max, 300)
                
                # Add price filter (top-level price field)
                if "price" not in query:
                    query["price"] = {}
                query["price"] = {
                    "$gte": price_min,
                    "$lte": price_max
                }
        
        # Legacy fields: main_category and subcategory from keywords
        if selected_keywords.main_category:
            or_conditions.append({"keywords.main_category": {"$regex": selected_keywords.main_category, "$options": "i"}})
        
        if selected_keywords.subcategory:
            or_conditions.append({"keywords.subcategory": {"$regex": selected_keywords.subcategory, "$options": "i"}})
    
    # Additional filters
    if additional_filters:
        if "price_range" in additional_filters:
            price_range = additional_filters["price_range"]
            if "min" in price_range and "max" in price_range:
                if "price" in query:
                    # Merge with existing price filter
                    existing = query["price"]
                    query["price"] = {
                        "$gte": max(existing.get("$gte", 0), price_range["min"]),
                        "$lte": min(existing.get("$lte", float("inf")), price_range["max"])
                    }
                else:
                    query["price"] = {"$gte": price_range["min"], "$lte": price_range["max"]}
        
        if "brand" in additional_filters:
            query["brand"] = {"$regex": additional_filters["brand"], "$options": "i"}
        
        if "category" in additional_filters:
            # Query both top-level and keywords
            or_conditions.append({"category": {"$regex": additional_filters["category"], "$options": "i"}})
            or_conditions.append({"keywords.main_category": {"$regex": additional_filters["category"], "$options": "i"}})
        
        if "subcategory" in additional_filters:
            # Query both top-level and keywords
            or_conditions.append({"subcategory": {"$regex": additional_filters["subcategory"], "$options": "i"}})
            or_conditions.append({"keywords.subcategory": {"$regex": additional_filters["subcategory"], "$options": "i"}})
    
    # Combine all $or conditions if any exist
    # MongoDB automatically ANDs top-level conditions with $or, so we can just add it
    if or_conditions:
        query["$or"] = or_conditions
    
    return query


def sort_products(products: List[Dict], sort_by: str) -> List[Dict]:
    """Sort products based on sort_by parameter"""
    if sort_by == "price_low":
        return sorted(products, key=lambda x: x.get("price", 0) or 0)
    elif sort_by == "price_high":
        return sorted(products, key=lambda x: x.get("price", 0) or 0, reverse=True)
    elif sort_by == "match_score":
        return sorted(products, key=lambda x: x.get("match_score", 0), reverse=True)
    else:
        return products  # Default: no sort


@router.post("/market-research/analyze", response_model=ProductAnalysisResponse)
async def market_research_analyze(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    AI Analysis: Extract structured product information from URL or INCI.
    
    This endpoint performs AI analysis to extract:
    - Active ingredients with percentages
    - MRP (scraped or AI-estimated)
    - Product form, categories, application
    - Keywords organized by feature category
    
    Request body:
    {
        "input_type": "url" | "inci",
        "url": "https://..." (required if input_type is "url"),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci"),
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional)
    }
    
    Returns structured analysis with keywords organized by:
    - product_formulation: Form-related keywords
    - mrp: Price range keywords
    - application: Use case keywords
    - functionality: Functional benefit keywords
    """
    start = time.time()
    scraper = None
    history_id = None
    
    try:
        # Extract user_id from JWT token
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate payload
        input_type = payload.get("input_type", "").lower()
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'")
        
        ingredients = []
        extracted_text = ""
        product_name = ""
        scraped_price = None
        
        if input_type == "url":
            url = payload.get("url", "").strip()
            if not url:
                raise HTTPException(status_code=400, detail="url is required when input_type is 'url'")
            
            if not url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="Invalid URL format")
            
            # Scrape URL
            scraper = URLScraper()
            extraction_result = await scraper.extract_ingredients_from_url(url)
            
            ingredients_raw = extraction_result.get("ingredients", [])
            extracted_text = extraction_result.get("extracted_text", "")
            product_name = extraction_result.get("product_name", "")
            
            # Try to extract price from scraped text
            if extracted_text:
                import re
                price_patterns = [
                    r'₹\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                    r'Rs\.?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                    r'INR\s*(\d+(?:,\d+)*(?:\.\d+)?)',
                ]
                for pattern in price_patterns:
                    matches = re.findall(pattern, extracted_text)
                    if matches:
                        try:
                            scraped_price = float(matches[0].replace(',', ''))
                            break
                        except:
                            pass
            
            # Parse ingredients
            if isinstance(ingredients_raw, str):
                ingredients = parse_inci_string(ingredients_raw)
            elif isinstance(ingredients_raw, list):
                ingredients = ingredients_raw
            else:
                ingredients = []
            
            if not ingredients:
                raise HTTPException(
                    status_code=404,
                    detail="No ingredients found on the product page"
                )
            
            input_data_value = url
        else:
            inci = payload.get("inci")
            if not inci:
                raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'")
            
            # Validate that inci is a list
            if not isinstance(inci, list):
                raise HTTPException(status_code=400, detail="inci must be an array of strings")
            
            if not inci:
                raise HTTPException(status_code=400, detail="inci cannot be empty")
            
            # Parse INCI list (handles list of strings, each may contain separators)
            ingredients = parse_inci_string(inci)
            if not ingredients:
                raise HTTPException(status_code=400, detail="No valid ingredients found in INCI list")
            
            # Store as comma-separated string for history
            input_data_value = ", ".join(inci)
        
        # Perform AI structured analysis
        structured_data = await extract_structured_product_info_with_ai(
            ingredients=ingredients,
            extracted_text=extracted_text,
            product_name=product_name,
            url=input_data_value if input_type == "url" else "",
            input_type=input_type,
            scraped_price=scraped_price
        )
        
        # Convert to schema format
        active_ingredients = [
            ActiveIngredient(name=ai.get("name", ""), percentage=ai.get("percentage"))
            for ai in structured_data.get("active_ingredients", [])
        ]
        
        keywords_dict = structured_data.get("keywords", {})
        
        # Handle redundancy: extract form from product_formulation[0] if form is not set
        form_value = keywords_dict.get("form")
        if not form_value and keywords_dict.get("product_formulation"):
            form_value = keywords_dict.get("product_formulation", [])[0] if keywords_dict.get("product_formulation") else None
        
        # Handle redundancy: extract price_tier from mrp[0] if price_tier is not set
        price_tier_value = keywords_dict.get("price_tier")
        if not price_tier_value and keywords_dict.get("mrp"):
            price_tier_value = keywords_dict.get("mrp", [])[0] if keywords_dict.get("mrp") else None
        
        keywords = ProductKeywords(
            product_formulation=keywords_dict.get("product_formulation", []),
            form=form_value,
            mrp=keywords_dict.get("mrp", []),
            price_tier=price_tier_value,
            application=keywords_dict.get("application", []),
            functionality=keywords_dict.get("functionality", []),
            benefits=keywords_dict.get("benefits", []),
            target_area=keywords_dict.get("target_area"),
            product_type_id=keywords_dict.get("product_type_id"),
            concerns=keywords_dict.get("concerns", []),
            market_positioning=keywords_dict.get("market_positioning", []),
            functional_categories=keywords_dict.get("functional_categories", []),
            main_category=keywords_dict.get("main_category"),
            subcategory=keywords_dict.get("subcategory")
        )
        
        structured_analysis = ProductStructuredAnalysis(
            active_ingredients=active_ingredients,
            mrp=structured_data.get("mrp"),
            mrp_per_ml=structured_data.get("mrp_per_ml"),
            mrp_source=structured_data.get("mrp_source")
        )
        
        # Auto-save to history if name provided
        if payload.get("name"):
            try:
                # Check if a history item with the same input_data already exists for this user
                existing_history_item = await market_research_history_col.find_one({
                    "user_id": user_id,
                    "input_type": input_type,
                    "input_data": input_data_value
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    # Update existing history with new analysis data
                    await market_research_history_col.update_one(
                        {"_id": existing_history_item["_id"]},
                        {"$set": {
                            "structured_analysis": structured_analysis.model_dump(),
                            "available_keywords": keywords.model_dump_exclude_empty(),
                            "name": payload.get("name", ""),  # Update name in case it changed
                            "tag": payload.get("tag")  # Update tag in case it changed
                        }}
                    )
                    print(f"✅ Updated existing history item: {history_id}")
                else:
                    history_doc = {
                        "user_id": user_id,
                        "name": payload.get("name", ""),
                        "tag": payload.get("tag"),
                        "input_type": input_type,
                        "input_data": input_data_value,
                        "structured_analysis": structured_analysis.model_dump(),
                        "available_keywords": keywords.model_dump_exclude_empty(),
                        "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                    }
                    
                    result = await market_research_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"✅ Auto-saved analysis to history: {history_id}")
            except Exception as e:
                print(f"⚠️  Error auto-saving to history: {e}")
        
        processing_time = round(time.time() - start, 2)
        
        return ProductAnalysisResponse(
            structured_analysis=structured_analysis,
            available_keywords=keywords,
            extracted_ingredients=ingredients,
            processing_time=processing_time,
            history_id=history_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in market research analyze: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze product: {str(e)}"
        )


@router.put("/market-research/update-keywords", response_model=UpdateKeywordsResponse)
async def update_market_research_keywords(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update selected keywords for a market research history item.
    
    Request body:
    {
        "history_id": "abc123",
        "selected_keywords": {
            "product_formulation": ["serum"],
            "mrp": ["premium"],
            "application": ["night_cream", "brightening"],
            "functionality": ["brightening", "moisturizing"]
        }
    }
    """
    try:
        # Extract user_id from JWT token
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate payload
        history_id = payload.get("history_id")
        if not history_id:
            raise HTTPException(status_code=400, detail="history_id is required")
        
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history_id")
        
        selected_keywords_dict = payload.get("selected_keywords")
        if not selected_keywords_dict:
            raise HTTPException(status_code=400, detail="selected_keywords is required")
        
        # Convert to schema
        selected_keywords = ProductKeywords(**selected_keywords_dict)
        
        # Update history item
        result = await market_research_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": {"selected_keywords": selected_keywords.model_dump_exclude_empty()}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to update it"
            )
        
        return UpdateKeywordsResponse(
            success=True,
            message="Keywords updated successfully",
            selected_keywords=selected_keywords,
            history_id=history_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating keywords: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update keywords: {str(e)}"
        )


@router.get("/market-research/products/paginated", response_model=MarketResearchPaginatedResponse)
async def market_research_products_paginated(
    history_id: str = Query(..., description="History item ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("match_score", description="Sort by: price_low, price_high, match_score"),
    filters: Optional[str] = Query(None, description="JSON string of additional filters"),
    unlock_page: bool = Query(False, description="Flag to unlock page after credits are deducted (frontend should set this to true after calling credit deduction API)"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get paginated products from existing analysis (fast, no re-analysis).
    
    Uses stored selected_keywords and structured_analysis from history to filter products.
    
    Credit-Based Pagination:
    - Pages 1-2 are free (automatically unlocked)
    - Pages 3+ require credits (must be unlocked via unlock_page flag)
    - Frontend should call credit deduction API first, then call this endpoint with unlock_page=true
    - Once a page is unlocked, it remains unlocked for that history_id
    
    Query Parameters:
    - history_id: History item ID (required)
    - page: Page number (default: 1)
    - page_size: Items per page (default: 10, max: 100)
    - sort_by: Sort method - "price_low", "price_high", or "match_score" (default: "match_score")
    - filters: JSON string of additional filters (optional)
    - unlock_page: Set to true after deducting credits via third-party API (default: false)
    
    Example:
    GET /api/market-research/products/paginated?history_id=abc123&page=1&page_size=20&sort_by=price_low
    GET /api/market-research/products/paginated?history_id=abc123&page=3&unlock_page=true
    """
    start = time.time()
    
    try:
        # Extract user_id from JWT token
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Validate history_id
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history_id")
        
        # Get history item
        history_item = await market_research_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id
        })
        
        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # ========================================================================
        # CREDIT-BASED PAGINATION LOGIC
        # ========================================================================
        # Get accessed_pages from history (pages user has unlocked)
        accessed_pages = history_item.get("accessed_pages", [])
        
        # Pages 1-2 are free
        FREE_PAGES_LIMIT = 2
        
        # Check if page requires credit
        page_requires_credit = page > FREE_PAGES_LIMIT
        is_page_unlocked = page in accessed_pages
        
        # Handle credit-based access control
        if page_requires_credit and not is_page_unlocked:
            # Page requires credit but is not unlocked
            if unlock_page:
                # Frontend has deducted credits - unlock the page
                await market_research_history_col.update_one(
                    {"_id": ObjectId(history_id)},
                    {"$addToSet": {"accessed_pages": page}}  # $addToSet prevents duplicates
                )
                # Update accessed_pages for response
                accessed_pages.append(page)
                is_page_unlocked = True
            else:
                # Page not unlocked and no unlock flag - return error
                raise HTTPException(
                    status_code=402,
                    detail=f"This page requires credits. Please unlock it first. Page {page} requires payment. Unlocked pages: {sorted(accessed_pages)}"
                )
        elif not page_requires_credit:
            # Free page - add to accessed_pages if not already there (for tracking)
            if page not in accessed_pages:
                await market_research_history_col.update_one(
                    {"_id": ObjectId(history_id)},
                    {"$addToSet": {"accessed_pages": page}}
                )
                accessed_pages.append(page)
        # ========================================================================
        
        # Get stored data
        structured_analysis_dict = history_item.get("structured_analysis")
        selected_keywords_dict = history_item.get("selected_keywords")
        research_result = history_item.get("research_result", {})
        
        if not structured_analysis_dict:
            raise HTTPException(
                status_code=400,
                detail="History item does not contain structured_analysis. Please run /market-research/analyze first."
            )
        
        # Convert to schemas
        # Remove 'keywords' from structured_analysis_dict if present (for backward compatibility with old records)
        if isinstance(structured_analysis_dict, dict) and "keywords" in structured_analysis_dict:
            structured_analysis_dict = {k: v for k, v in structured_analysis_dict.items() if k != "keywords"}
        
        structured_analysis = ProductStructuredAnalysis(**structured_analysis_dict)
        selected_keywords = ProductKeywords(**selected_keywords_dict) if selected_keywords_dict else None
        
        # Get available_keywords for main_category and subcategory
        available_keywords_dict = history_item.get("available_keywords")
        available_keywords = ProductKeywords(**available_keywords_dict) if available_keywords_dict else None
        
        # Parse additional filters
        additional_filters = {}
        if filters:
            try:
                additional_filters = json.loads(filters)
            except:
                pass
        
        # Get sample product to check field existence
        external_products_col = db["externalproducts"]
        sample_product = await external_products_col.find_one({})
        
        # Build MongoDB query
        mongo_query = build_mongo_query_from_keywords(
            selected_keywords=selected_keywords,
            structured_analysis=structured_analysis.model_dump(),
            additional_filters=additional_filters,
            collection_sample=sample_product
        )
        
        # Add ingredients filter if we have extracted ingredients
        extracted_ingredients = research_result.get("extracted_ingredients", [])
        if extracted_ingredients:
            # Normalize ingredients for matching
            normalized_ingredients = [ing.strip().lower() for ing in extracted_ingredients]
            # Add ingredient matching to query (products must have at least one matching ingredient)
            mongo_query["ingredients"] = {
                "$exists": True,
                "$ne": None,
                "$ne": ""
            }
        
        # Fetch products
        all_products_cursor = external_products_col.find(mongo_query)
        all_products = await all_products_cursor.to_list(length=None)
        
        # Match products by ingredients (if we have extracted ingredients)
        matched_products = []
        if extracted_ingredients:
            normalized_ingredients = [ing.strip().lower() for ing in extracted_ingredients]
            
            for product in all_products:
                product_ingredients = product.get("ingredients", [])
                if isinstance(product_ingredients, str):
                    product_ingredients = parse_inci_string(product_ingredients)
                elif not isinstance(product_ingredients, list):
                    product_ingredients = []
                
                # Normalize product ingredients
                normalized_product_ingredients = [ing.strip().lower() for ing in product_ingredients]
                
                # Check for matches
                matches = []
                for input_ing in normalized_ingredients:
                    for prod_ing in normalized_product_ingredients:
                        if input_ing in prod_ing or prod_ing in input_ing:
                            if prod_ing not in matches:
                                matches.append(prod_ing)
                            break
                
                if matches:
                    # Build product data
                    product_data = {
                        "id": str(product.get("_id", "")),
                        "productName": product.get("name") or product.get("productName", ""),
                        "brand": product.get("brand", ""),
                        "ingredients": product_ingredients,
                        "image": product.get("image") or product.get("s3Image", ""),
                        "images": product.get("images") or product.get("s3Images", []),
                        "price": product.get("price"),
                        "salePrice": product.get("salePrice"),
                        "description": product.get("description", ""),
                        "matched_ingredients": matches,
                        "match_count": len(matches),
                        "total_ingredients": len(product_ingredients),
                        "match_percentage": (len(matches) / len(normalized_ingredients) * 100) if normalized_ingredients else 0,
                        "match_score": (len(matches) / len(normalized_ingredients) * 100) if normalized_ingredients else 0,
                        "active_match_count": len(matches),
                        "active_ingredients": matches
                    }
                    matched_products.append(product_data)
        else:
            # No ingredient matching, just return all products matching the query
            for product in all_products:
                product_data = {
                    "id": str(product.get("_id", "")),
                    "productName": product.get("name") or product.get("productName", ""),
                    "brand": product.get("brand", ""),
                    "ingredients": product.get("ingredients", []),
                    "image": product.get("image") or product.get("s3Image", ""),
                    "images": product.get("images") or product.get("s3Images", []),
                    "price": product.get("price"),
                    "salePrice": product.get("salePrice"),
                    "description": product.get("description", ""),
                    "matched_ingredients": [],
                    "match_count": 0,
                    "total_ingredients": len(product.get("ingredients", [])),
                    "match_percentage": 0,
                    "match_score": 0,
                    "active_match_count": 0,
                    "active_ingredients": []
                }
                matched_products.append(product_data)
        
        # Sort products
        matched_products = sort_products(matched_products, sort_by)
        
        # Paginate
        total_matched = len(matched_products)
        total_pages = (total_matched + page_size - 1) // page_size if total_matched > 0 else 0
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_products = matched_products[start_idx:end_idx]
        
        # Build filters_applied
        filters_applied = {}
        if selected_keywords:
            filters_applied["keywords"] = selected_keywords.model_dump_exclude_empty()
        if additional_filters:
            filters_applied.update(additional_filters)
        
        processing_time = round(time.time() - start, 2)
        
        # Determine next page unlock status
        next_page = page + 1
        next_page_requires_credit = next_page > FREE_PAGES_LIMIT
        next_page_unlocked = next_page in accessed_pages if next_page_requires_credit else True
        
        return MarketResearchPaginatedResponse(
            products=paginated_products,
            total_matched=total_matched,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            sort_by=sort_by,
            filters_applied=filters_applied,
            processing_time=processing_time,
            extracted_ingredients=extracted_ingredients,
            input_type=history_item.get("input_type", "inci"),
            ai_interpretation=history_item.get("ai_interpretation"),
            primary_category=available_keywords.main_category if available_keywords else history_item.get("primary_category"),
            subcategory=available_keywords.subcategory if available_keywords else history_item.get("subcategory"),
            category_confidence=history_item.get("category_confidence"),
            history_id=history_id,
            page_requires_credit=page_requires_credit,
            is_unlocked=is_page_unlocked if page_requires_credit else True,
            unlocked_pages=sorted(accessed_pages),
            next_page_requires_credit=next_page_requires_credit,
            next_page_unlocked=next_page_unlocked
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in market research products paginated: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get paginated products: {str(e)}"
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
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = payload.get("name", "").strip() if payload.get("name") else ""  # Required: custom name for history
    tag = payload.get("tag")  # Optional: tag for history
    notes = payload.get("notes")  # Optional: notes for history
    provided_history_id = payload.get("history_id")  # Optional: reuse existing history item
    history_id = None
    
    # Validate name is provided if auto-save is enabled (user_id is present)
    if user_id_value and not provided_history_id and not name:
        raise HTTPException(status_code=400, detail="name is required for auto-save")
    
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
            inci = payload.get("inci")
            if not inci:
                raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'")
            
            # Validate that inci is a list
            if not isinstance(inci, list):
                raise HTTPException(status_code=400, detail="inci must be an array of strings")
            
            if not inci:
                raise HTTPException(status_code=400, detail="inci cannot be empty")
            
            # Parse INCI list (handles list of strings, each may contain separators)
            ingredients = parse_inci_string(inci)
            extracted_text = ", ".join(inci)  # Join for display
            input_data_value = ", ".join(inci)  # Store as comma-separated string for auto-save
            
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
                    # Name is required - already validated above
                    # Truncate if too long
                    if len(name) > 100:
                        name = name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
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
        
        # Get selected_keywords and structured_analysis for overview if available
        selected_keywords_for_overview = None
        structured_analysis_for_overview = None
        
        # Check if selected_keywords provided in payload
        selected_keywords_payload = payload.get("selected_keywords")
        if selected_keywords_payload:
            selected_keywords_for_overview = selected_keywords_payload
        
        # Get structured_analysis from history if available
        if history_id and user_id_value:
            try:
                existing_item = await market_research_history_col.find_one({
                    "_id": ObjectId(history_id),
                    "user_id": user_id_value
                })
                if existing_item:
                    structured_analysis_for_overview = existing_item.get("structured_analysis")
                    # Remove 'keywords' if present (backward compatibility)
                    if isinstance(structured_analysis_for_overview, dict) and "keywords" in structured_analysis_for_overview:
                        structured_analysis_for_overview = {k: v for k, v in structured_analysis_for_overview.items() if k != "keywords"}
            except:
                pass
        
        try:
            market_research_overview = await generate_market_research_overview_with_ai(
                ingredients,
                matched_products[:50],  # Use top 50 for overview generation
                category_info,
                total_matched_count,
                selected_keywords=selected_keywords_for_overview,
                structured_analysis=structured_analysis_for_overview
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
        
        # 🔹 Auto-save: Create or update history with completed status and research_result
        if user_id_value:
            try:
                # Convert response to dict for storage
                research_result_dict = response.dict()
                # ⚠️ IMPORTANT: Save ALL products, not just paginated ones for proper pagination later
                research_result_dict["products"] = matched_products  # Save all products, not paginated_products
                
                # Get structured_analysis and available_keywords from history if history_id provided
                structured_analysis_dict = None
                available_keywords_dict = None
                
                if history_id:
                    existing_item = await market_research_history_col.find_one({
                        "_id": ObjectId(history_id),
                        "user_id": user_id_value
                    })
                    if existing_item:
                        structured_analysis_dict = existing_item.get("structured_analysis")
                        available_keywords_dict = existing_item.get("available_keywords")
                        
                        # Remove 'keywords' from structured_analysis_dict if present (for backward compatibility)
                        if isinstance(structured_analysis_dict, dict) and "keywords" in structured_analysis_dict:
                            structured_analysis_dict = {k: v for k, v in structured_analysis_dict.items() if k != "keywords"}
                
                # Build update/create document
                update_doc = {
                    "research_result": research_result_dict,
                    "ai_analysis": ai_analysis_message,
                    "ai_reasoning": ai_reasoning,
                    "ai_interpretation": ai_interpretation,
                    "primary_category": primary_category,
                    "subcategory": subcategory,
                    "category_confidence": category_confidence
                }
                
                # Add structured_analysis and keywords if available from history
                if structured_analysis_dict:
                    update_doc["structured_analysis"] = structured_analysis_dict
                if available_keywords_dict:
                    update_doc["available_keywords"] = available_keywords_dict
                
                # Save selected_keywords if provided in payload
                selected_keywords_payload = payload.get("selected_keywords")
                if selected_keywords_payload:
                    try:
                        selected_keywords_obj = ProductKeywords(**selected_keywords_payload)
                        update_doc["selected_keywords"] = selected_keywords_obj.model_dump_exclude_empty()
                    except Exception as e:
                        print(f"[AUTO-SAVE] Warning: Could not parse selected_keywords: {e}")
                
                if history_id:
                    # Update existing history
                    await market_research_history_col.update_one(
                        {"_id": ObjectId(history_id), "user_id": user_id_value},
                        {"$set": update_doc}
                    )
                    print(f"[AUTO-SAVE] Updated history {history_id} with research results (saved {len(matched_products)} total products)")
                elif name:
                    # Check if a history item with the same input_data already exists for this user
                    existing_history_item = await market_research_history_col.find_one({
                        "user_id": user_id_value,
                        "input_type": input_type,
                        "input_data": input_data_value
                    }, sort=[("created_at", -1)])  # Get the most recent one
                    
                    if existing_history_item:
                        # Update existing history instead of creating new one
                        history_id = str(existing_history_item["_id"])
                        await market_research_history_col.update_one(
                            {"_id": existing_history_item["_id"]},
                            {"$set": update_doc}
                        )
                        print(f"[AUTO-SAVE] Updated existing history {history_id} with research results (saved {len(matched_products)} total products)")
                    else:
                        # Create new history item
                        history_doc = {
                            "user_id": user_id_value,
                            "name": name,
                            "tag": tag,
                            "input_type": input_type,
                            "input_data": input_data_value,
                            "notes": notes,
                            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                            **update_doc
                        }
                        result = await market_research_history_col.insert_one(history_doc)
                        history_id = str(result.inserted_id)
                        print(f"[AUTO-SAVE] Created new history {history_id} with research results (saved {len(matched_products)} total products)")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save/update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        # Add history_id to response if available (convert to dict to add extra field)
        if history_id:
            response_dict = response.dict()
            response_dict["history_id"] = history_id
            return response_dict
        
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
    Market Research Products: Fast endpoint that returns matched products with optional keyword filtering.
    
    ENHANCED: Now supports keyword-based filtering, sorting, and pagination.
    
    Request body:
    {
        "input_type": "url" | "inci",
        "url": "https://..." (required if input_type is "url"),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci"),
        "selected_keywords": {  // NEW: Optional keyword filtering
            "product_formulation": ["serum"],
            "mrp": ["premium"],
            "application": ["night_cream", "brightening"],
            "functionality": ["brightening", "moisturizing"]
        },
        "filters": {  // NEW: Additional filters
            "price_range": {"min": 500, "max": 2000},
            "brand": "Brand Name"
        },
        "page": 1,  // NEW: Page number (default: 1)
        "page_size": 10,  // NEW: Items per page (default: 10, max: 100)
        "sort_by": "price_low" | "price_high" | "match_score",  // NEW: Sorting (default: "match_score")
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional)
    }
    
    Returns:
    {
        "products": [paginated matched products],
        "extracted_ingredients": [list of ingredients],
        "total_matched": total number of matched products,
        "page": 1,
        "page_size": 10,
        "total_pages": 15,
        "sort_by": "price_low",
        "filters_applied": {...},
        "processing_time": time taken,
        "input_type": "url" | "inci",
        "ai_interpretation": "AI interpretation",
        "primary_category": "skincare" | etc.,
        "subcategory": "serum" | etc.,
        "category_confidence": "high" | "medium" | "low"
    }
    
    BACKWARD COMPATIBLE: If selected_keywords not provided, uses existing ingredient-based matching.
    
    AUTO-SAVE: Results are automatically saved to market research history if user is authenticated.
    """
    start = time.time()
    scraper = None
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = payload.get("name", "").strip() if payload.get("name") else ""  # Required: custom name for history
    tag = payload.get("tag")  # Optional: tag for history
    notes = payload.get("notes")  # Optional: notes for history
    provided_history_id = payload.get("history_id")  # Optional: reuse existing history item
    history_id = None
    
    # Validate history_id if provided and retrieve stored data
    existing_item = None
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
        # Get input_type from payload or from history if history_id provided
        input_type = payload.get("input_type", "").lower()
        if not input_type and existing_item:
            # Retrieve input_type from history
            input_type = existing_item.get("input_type", "").lower()
            print(f"[AUTO-SAVE] Retrieved input_type '{input_type}' from history")
        
        # Validate input_type
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'. If using history_id, ensure the history item has a valid input_type.")
        
        ingredients = []
        extracted_text = ""
        input_data_value = ""  # For auto-save
        
        # If history_id provided, try to get ingredients from history first
        if existing_item and not payload.get("url") and not payload.get("inci"):
            # Try to get ingredients from research_result (if products were already fetched)
            research_result = existing_item.get("research_result", {})
            if research_result and research_result.get("extracted_ingredients"):
                ingredients = research_result.get("extracted_ingredients", [])
                input_data_value = existing_item.get("input_data", "")
                print(f"[AUTO-SAVE] Retrieved {len(ingredients)} ingredients from research_result")
            else:
                # If no research_result, we'll need to extract from input_data based on input_type
                # This will be handled in the URL/INCI processing below
                input_data_value = existing_item.get("input_data", "")
                print(f"[AUTO-SAVE] No research_result found, will extract from input_data if needed")
        
        # Only process URL/INCI if we don't already have ingredients from history
        if not ingredients:
            if input_type == "url":
                url = payload.get("url", "").strip()
                if not url and existing_item:
                    # Try to get from history input_data
                    url = existing_item.get("input_data", "").strip()
                    if url:
                        print(f"[AUTO-SAVE] Using URL from history input_data")
                
                if not url:
                    raise HTTPException(status_code=400, detail="url is required when input_type is 'url'. Provide url in payload or ensure history has input_data.")
                
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
                # INCI input - can come from payload or from history input_data
                inci = payload.get("inci")
                if not inci and existing_item:
                    # Try to get from history input_data
                    input_data_from_history = existing_item.get("input_data", "")
                    if input_data_from_history:
                        # Parse input_data (could be comma-separated string)
                        if isinstance(input_data_from_history, str):
                            inci = [ing.strip() for ing in input_data_from_history.split(",") if ing.strip()]
                        elif isinstance(input_data_from_history, list):
                            inci = input_data_from_history
                        print(f"[AUTO-SAVE] Using INCI from history input_data: {len(inci)} items")
                
                if not inci:
                    raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'. Provide inci in payload or ensure history has input_data.")
                
                # Validate that inci is a list
                if not isinstance(inci, list):
                    raise HTTPException(status_code=400, detail="inci must be an array of strings")
                
                if not inci:
                    raise HTTPException(status_code=400, detail="inci cannot be empty")
                
                # Parse INCI list (handles list of strings, each may contain separators)
                ingredients = parse_inci_string(inci)
                extracted_text = ", ".join(inci)  # Join for display
                if not input_data_value:
                    input_data_value = ", ".join(inci)  # Store as comma-separated string for auto-save
                
                if not ingredients:
                    raise HTTPException(
                        status_code=400,
                        detail="No valid ingredients found after parsing. Please check your input format."
                    )
        else:
            # Ingredients already retrieved from history, use them
            print(f"Using {len(ingredients)} ingredients retrieved from history")
            if not extracted_text and input_data_value:
                # Try to create extracted_text from input_data if available
                if isinstance(input_data_value, str):
                    extracted_text = input_data_value
        
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
                    # Name is required - already validated above
                    # Truncate if too long
                    if len(name) > 100:
                        name = name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
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
        
        # ENHANCED: Check for keyword filtering, sorting, and pagination
        selected_keywords_dict = payload.get("selected_keywords")
        additional_filters = payload.get("filters", {})
        sort_by = payload.get("sort_by", "match_score")
        page = payload.get("page", 1)
        page_size = payload.get("page_size", 10)
        
        # Apply keyword filtering if provided
        if selected_keywords_dict:
            try:
                selected_keywords = ProductKeywords(**selected_keywords_dict)
                
                # Get structured analysis if available from history or perform analysis
                structured_analysis_dict = None
                if history_id:
                    history_item = await market_research_history_col.find_one({
                        "_id": ObjectId(history_id),
                        "user_id": user_id_value
                    })
                    if history_item:
                        structured_analysis_dict = history_item.get("structured_analysis")
                
                # If no structured analysis, create one from category info
                if not structured_analysis_dict:
                    structured_analysis_dict = {
                        "main_category": primary_category,
                        "subcategory": subcategory,
                        "form": None,
                        "functional_categories": [],
                        "application": [],
                        "mrp": None
                    }
                
                # Get sample product to check field existence
                external_products_col = db["externalproducts"]
                sample_product = await external_products_col.find_one({})
                
                # Build MongoDB query for keyword filtering
                keyword_query = build_mongo_query_from_keywords(
                    selected_keywords=selected_keywords,
                    structured_analysis=structured_analysis_dict,
                    additional_filters=additional_filters,
                    collection_sample=sample_product
                )
                
                # Filter matched_products by keyword query
                # This is a simplified filter - in production, you'd want to query MongoDB directly
                # For now, we filter the already matched products
                if keyword_query:
                    filtered_products = []
                    for product in matched_products:
                        # Check if product matches keyword filters
                        matches = True
                        
                        # Check category
                        if "category" in keyword_query:
                            product_category = product.get("category", "").lower()
                            if keyword_query["category"].get("$regex", "").lower() not in product_category:
                                matches = False
                        
                        # Check subcategory
                        if matches and "subcategory" in keyword_query:
                            product_subcategory = product.get("subcategory", "").lower()
                            if keyword_query["subcategory"].get("$regex", "").lower() not in product_subcategory:
                                matches = False
                        
                        # Check price range
                        if matches and "price" in keyword_query:
                            product_price = product.get("price", 0) or 0
                            price_filter = keyword_query["price"]
                            if "$gte" in price_filter and product_price < price_filter["$gte"]:
                                matches = False
                            if "$lte" in price_filter and product_price > price_filter["$lte"]:
                                matches = False
                        
                        # Check brand
                        if matches and "brand" in keyword_query:
                            product_brand = product.get("brand", "").lower()
                            if keyword_query["brand"].get("$regex", "").lower() not in product_brand:
                                matches = False
                        
                        if matches:
                            filtered_products.append(product)
                    
                    matched_products = filtered_products
                    print(f"  ✅ Keyword filtering applied: {len(matched_products)} products after filtering")
            except Exception as e:
                print(f"  ⚠️  Error applying keyword filtering: {e}")
                import traceback
                traceback.print_exc()
        
        # Apply sorting
        matched_products = sort_products(matched_products, sort_by)
        
        # Apply pagination
        total_matched_count = len(matched_products)
        total_pages = (total_matched_count + page_size - 1) // page_size if total_matched_count > 0 else 0
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_products = matched_products[start_idx:end_idx]
        
        processing_time = time.time() - start
        
        print(f"\n{'='*60}")
        print(f"Market Research Products Summary:")
        print(f"  Total products matched: {total_matched_count}")
        print(f"  Page: {page}/{total_pages}")
        print(f"  Showing: {len(paginated_products)} products")
        print(f"  Sort by: {sort_by}")
        print(f"  Category: {primary_category}/{subcategory}")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"{'='*60}\n")
        
        # Return response with paginated products
        response = MarketResearchProductsResponse(
            products=paginated_products,
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
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
        # 🔹 Auto-save: Create or update history with completed status and research_result
        if user_id_value:
            try:
                # Convert response to dict for storage
                research_result_dict = response.dict()
                # ⚠️ IMPORTANT: Save ALL products, not just paginated ones for proper pagination later
                research_result_dict["products"] = matched_products  # Save all products, not paginated_products
                
                # Get structured_analysis and available_keywords from history if history_id provided
                structured_analysis_dict = None
                available_keywords_dict = None
                
                if history_id:
                    existing_item = await market_research_history_col.find_one({
                        "_id": ObjectId(history_id),
                        "user_id": user_id_value
                    })
                    if existing_item:
                        structured_analysis_dict = existing_item.get("structured_analysis")
                        available_keywords_dict = existing_item.get("available_keywords")
                        
                        # Remove 'keywords' from structured_analysis_dict if present (for backward compatibility)
                        if isinstance(structured_analysis_dict, dict) and "keywords" in structured_analysis_dict:
                            structured_analysis_dict = {k: v for k, v in structured_analysis_dict.items() if k != "keywords"}
                
                # Build update/create document
                update_doc = {
                    "research_result": research_result_dict,
                    "ai_analysis": ai_analysis_message,
                    "ai_reasoning": ai_reasoning,
                    "ai_interpretation": ai_interpretation,
                    "primary_category": primary_category,
                    "subcategory": subcategory,
                    "category_confidence": category_confidence
                }
                
                # Add structured_analysis and keywords if available from history
                if structured_analysis_dict:
                    update_doc["structured_analysis"] = structured_analysis_dict
                if available_keywords_dict:
                    update_doc["available_keywords"] = available_keywords_dict
                
                # Save selected_keywords if provided in payload
                selected_keywords_payload = payload.get("selected_keywords")
                if selected_keywords_payload:
                    try:
                        selected_keywords_obj = ProductKeywords(**selected_keywords_payload)
                        update_doc["selected_keywords"] = selected_keywords_obj.model_dump_exclude_empty()
                    except Exception as e:
                        print(f"[AUTO-SAVE] Warning: Could not parse selected_keywords: {e}")
                
                if history_id:
                    # Update existing history
                    await market_research_history_col.update_one(
                        {"_id": ObjectId(history_id), "user_id": user_id_value},
                        {"$set": update_doc}
                    )
                    print(f"[AUTO-SAVE] Updated history {history_id} with research results (saved {len(matched_products)} total products)")
                elif name:
                    # Check if a history item with the same input_data already exists for this user
                    existing_history_item = await market_research_history_col.find_one({
                        "user_id": user_id_value,
                        "input_type": input_type,
                        "input_data": input_data_value
                    }, sort=[("created_at", -1)])  # Get the most recent one
                    
                    if existing_history_item:
                        # Update existing history instead of creating new one
                        history_id = str(existing_history_item["_id"])
                        await market_research_history_col.update_one(
                            {"_id": existing_history_item["_id"]},
                            {"$set": update_doc}
                        )
                        print(f"[AUTO-SAVE] Updated existing history {history_id} with research results (saved {len(matched_products)} total products)")
                    else:
                        # Create new history item
                        history_doc = {
                            "user_id": user_id_value,
                            "name": name,
                            "tag": tag,
                            "input_type": input_type,
                            "input_data": input_data_value,
                            "notes": notes,
                            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                            **update_doc
                        }
                        result = await market_research_history_col.insert_one(history_doc)
                        history_id = str(result.inserted_id)
                        print(f"[AUTO-SAVE] Created new history {history_id} with research results (saved {len(matched_products)} total products)")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save/update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        # Add history_id to response if available (convert to dict to add extra field)
        if history_id:
            response_dict = response.dict()
            response_dict["history_id"] = history_id
            return response_dict
        
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
        "history_id": "abc123" (optional, if provided, will use stored data from history),
        "input_type": "url" or "inci" (optional if history_id provided),
        "url": "https://example.com/product/..." (required if input_type is "url" and no history_id),
        "inci": "Water, Glycerin, ..." (required if input_type is "inci" and no history_id),
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
    
    # Extract user info
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    provided_history_id = payload.get("history_id")
    history_id = None
    existing_item = None
    
    # Validate history_id if provided and retrieve stored data
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await market_research_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_item:
                    history_id = provided_history_id
                    print(f"[OVERVIEW] Using existing history_id: {history_id}")
                else:
                    print(f"[OVERVIEW] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user")
            else:
                print(f"[OVERVIEW] Warning: Invalid history_id format: {provided_history_id}")
        except Exception as e:
            print(f"[OVERVIEW] Warning: Error validating history_id: {e}")
    
    try:
        # Get input_type from payload or from history if history_id provided
        input_type = payload.get("input_type", "").lower()
        if not input_type and existing_item:
            # Retrieve input_type from history
            input_type = existing_item.get("input_type", "").lower()
            print(f"[OVERVIEW] Retrieved input_type '{input_type}' from history")
        
        # Validate input_type
        if input_type not in ["url", "inci"]:
            raise HTTPException(status_code=400, detail="input_type must be 'url' or 'inci'. If using history_id, ensure the history item has a valid input_type.")
        
        ingredients = []
        extracted_text = ""
        input_data_value = ""
        
        # If history_id provided, try to get ingredients from history first
        if existing_item and not payload.get("url") and not payload.get("inci"):
            # Try to get ingredients from research_result
            research_result = existing_item.get("research_result", {})
            if research_result and research_result.get("extracted_ingredients"):
                ingredients = research_result.get("extracted_ingredients", [])
                input_data_value = existing_item.get("input_data", "")
                print(f"[OVERVIEW] Retrieved {len(ingredients)} ingredients from research_result")
            else:
                input_data_value = existing_item.get("input_data", "")
                print(f"[OVERVIEW] No research_result found, will extract from input_data if needed")
        
        # Only process URL/INCI if we don't already have ingredients from history
        if not ingredients:
            if input_type == "url":
                url = payload.get("url", "").strip()
                if not url and existing_item:
                    # Try to get from history input_data
                    url = existing_item.get("input_data", "").strip()
                    if url:
                        print(f"[OVERVIEW] Using URL from history input_data")
                
                if not url:
                    raise HTTPException(status_code=400, detail="url is required when input_type is 'url'. Provide url in payload or ensure history has input_data.")
                
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
                
                input_data_value = url
            elif input_type == "inci":
                # INCI input - can come from payload or from history input_data
                inci = payload.get("inci")
                if not inci and existing_item:
                    # Try to get from history input_data
                    input_data_from_history = existing_item.get("input_data", "")
                    if input_data_from_history:
                        # Parse input_data (could be comma-separated string)
                        if isinstance(input_data_from_history, str):
                            inci = [ing.strip() for ing in input_data_from_history.split(",") if ing.strip()]
                        elif isinstance(input_data_from_history, list):
                            inci = input_data_from_history
                        print(f"[OVERVIEW] Using INCI from history input_data: {len(inci)} items")
                
                if not inci:
                    raise HTTPException(status_code=400, detail="inci is required when input_type is 'inci'. Provide inci in payload or ensure history has input_data.")
            
                # Validate that inci is a list
                if not isinstance(inci, list):
                    raise HTTPException(status_code=400, detail="inci must be an array of strings")
                
                if not inci:
                    raise HTTPException(status_code=400, detail="inci cannot be empty")
                
                # Parse INCI list (handles list of strings, each may contain separators)
                ingredients = parse_inci_string(inci)
                extracted_text = ", ".join(inci)  # Join for display
                if not input_data_value:
                    input_data_value = ", ".join(inci)
                
                if not ingredients:
                    raise HTTPException(
                        status_code=400,
                        detail="No valid ingredients found after parsing. Please check your input format."
                    )
        else:
            # Ingredients already retrieved from history, use them
            print(f"[OVERVIEW] Using {len(ingredients)} ingredients retrieved from history")
            if not extracted_text and input_data_value:
                if isinstance(input_data_value, str):
                    extracted_text = input_data_value
        
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
        
        # Get selected_keywords and structured_analysis from history if available
        selected_keywords_for_overview = None
        structured_analysis_for_overview = None
        history_id_for_overview = payload.get("history_id")
        user_id_for_overview = current_user.get("user_id") or current_user.get("_id")
        
        if history_id_for_overview and user_id_for_overview:
            try:
                existing_item = await market_research_history_col.find_one({
                    "_id": ObjectId(history_id_for_overview),
                    "user_id": user_id_for_overview
                })
                if existing_item:
                    selected_keywords_for_overview = existing_item.get("selected_keywords")
                    structured_analysis_for_overview = existing_item.get("structured_analysis")
                    # Remove 'keywords' if present (backward compatibility)
                    if isinstance(structured_analysis_for_overview, dict) and "keywords" in structured_analysis_for_overview:
                        structured_analysis_for_overview = {k: v for k, v in structured_analysis_for_overview.items() if k != "keywords"}
            except:
                pass
        
        try:
            market_research_overview = await generate_market_research_overview_with_ai(
                ingredients,
                matched_products,
                category_info,
                total_matched,
                selected_keywords=selected_keywords_for_overview,
                structured_analysis=structured_analysis_for_overview
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
        
        # 🔹 Auto-save: Update history with overview if history_id provided or find/create history
        if user_id_value:
            try:
                if history_id:
                    # Update existing history with overview
                    await market_research_history_col.update_one(
                        {"_id": ObjectId(history_id), "user_id": user_id_value},
                        {"$set": {
                            "market_research_overview": market_research_overview,
                            "primary_category": category_info.get("primary_category"),
                            "subcategory": category_info.get("subcategory"),
                            "category_confidence": category_info.get("confidence")
                        }}
                    )
                    print(f"[OVERVIEW] Updated history {history_id} with overview")
                elif input_data_value and input_type:
                    # Check if a history item with the same input_data already exists
                    existing_history_item = await market_research_history_col.find_one({
                        "user_id": user_id_value,
                        "input_type": input_type,
                        "input_data": input_data_value
                    }, sort=[("created_at", -1)])  # Get the most recent one
                    
                    if existing_history_item:
                        # Update existing history with overview
                        history_id = str(existing_history_item["_id"])
                        await market_research_history_col.update_one(
                            {"_id": existing_history_item["_id"]},
                            {"$set": {
                                "market_research_overview": market_research_overview,
                                "primary_category": category_info.get("primary_category"),
                                "subcategory": category_info.get("subcategory"),
                                "category_confidence": category_info.get("confidence")
                            }}
                        )
                        print(f"[OVERVIEW] Updated existing history {history_id} with overview")
                    else:
                        # No existing history found - overview endpoint doesn't create new history
                        # (it should be created by the main research endpoints first)
                        print(f"[OVERVIEW] No existing history found for input_data, overview not saved")
            except Exception as e:
                print(f"[OVERVIEW] Warning: Failed to save/update history with overview: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        print(f"\n{'='*60}")
        print(f"Market Research Overview Summary:")
        print(f"  Total products matched: {total_matched}")
        print(f"  Processing time: {processing_time:.2f}s")
        print(f"{'='*60}\n")
        
        return MarketResearchOverviewResponse(
            market_research_overview=market_research_overview,
            processing_time=round(processing_time, 2),
            history_id=history_id
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


# ============================================================================
# PLATFORM FETCHER ENDPOINT
# ============================================================================

@router.post("/fetch-platforms", response_model=FetchPlatformsResponse)
async def fetch_platforms_endpoint(
    request: FetchPlatformsRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Fetch all platform links for a product using Serper.dev API.
    
    This endpoint searches for a product across multiple e-commerce platforms
    and returns one link per platform (deduplicated).
    
    REQUEST BODY:
    {
        "product_name": "Simple Kind to Skin Face Wash"
    }
    
    RESPONSE:
    {
        "platforms": [
            {
                "platform": "amazon",
                "platform_display_name": "Amazon",
                "url": "https://amazon.in/...",
                "logo_url": "https://platform_logos.s3.../amazon.png",
                "title": "Product Title",
                "price": "₹499",
                "position": 1
            },
            ...
        ],
        "total_platforms": 6,
        "product_name": "Simple Kind to Skin Face Wash"
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    """
    try:
        if not request.product_name or not request.product_name.strip():
            raise HTTPException(
                status_code=400,
                detail="product_name is required and cannot be empty"
            )
        
        # Fetch platforms
        platforms = fetch_platforms(request.product_name.strip())
        
        # Convert to response format using PlatformInfo schema
        platform_info_list = [
            PlatformInfo(
                platform=p["platform"],
                platform_display_name=p["platform_display_name"],
                url=p["url"],
                logo_url=p.get("logo_url"),
                title=p["title"],
                price=p.get("price"),
                position=p["position"]
            )
            for p in platforms
        ]
        
        return FetchPlatformsResponse(
            platforms=platform_info_list,
            total_platforms=len(platform_info_list),
            product_name=request.product_name.strip()
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch platforms: {str(e)}"
        )


