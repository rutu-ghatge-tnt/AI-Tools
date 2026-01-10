"""
Inspiration Boards API Endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from typing import List, Optional
import asyncio
from datetime import datetime

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
    CreateBoardRequest, UpdateBoardRequest, BoardResponse, BoardListResponse, BoardDetailResponse,
    AddProductFromURLRequest, AddProductManualRequest, UpdateProductRequest, ProductResponse,
    FetchProductRequest, FetchProductResponse,
    AnalysisRequest, AnalysisResponse,
    TagsResponse,
    ExportToBoardRequest, ExportToBoardResponse, ExportItemRequest
)
from app.ai_ingredient_intelligence.logic.board_manager import (
    create_board, get_boards, get_board_detail, update_board, delete_board
)
from app.ai_ingredient_intelligence.logic.product_manager import (
    add_product_from_url, add_product_manual, get_product, update_product, delete_product
)
from app.ai_ingredient_intelligence.logic.url_fetcher import fetch_product_from_url
from app.ai_ingredient_intelligence.logic.competitor_analyzer import analyze_competitors
from app.ai_ingredient_intelligence.logic.product_tags import get_all_tags, validate_tags, initialize_tags
from app.ai_ingredient_intelligence.logic.feature_history_accessor import (
    get_feature_history, extract_product_data_from_history, validate_history_ids, get_product_type_config
)
from app.ai_ingredient_intelligence.logic.serper_product_search import fetch_platforms
from app.ai_ingredient_intelligence.db.collections import inspiration_products_col
from bson import ObjectId

router = APIRouter(prefix="/inspiration-boards", tags=["Inspiration Boards"])


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def fetch_platforms_for_product_background(product_id: str, user_id: str):
    """
    Background task to fetch platforms for a product after it's added or updated.
    Extracts product name and fetches platform links.
    """
    try:
        # Fetch the product
        product = await inspiration_products_col.find_one({
            "_id": ObjectId(product_id),
            "user_id": user_id
        })
        
        if not product:
            print(f"[BACKGROUND] Product {product_id} not found, skipping platform fetch")
            return
        
        # Extract product name
        product_name = product.get("name")
        
        if not product_name or not product_name.strip() or product_name == "Unknown Product":
            print(f"[BACKGROUND] No valid product name found for product {product_id}, skipping platform fetch")
            return
        
        print(f"[BACKGROUND] Fetching platforms for product: {product_name}")
        
        # Fetch platforms (run sync function in thread pool to avoid blocking)
        platforms = await asyncio.to_thread(fetch_platforms, product_name.strip())
        
        # Update product with platforms data
        await inspiration_products_col.update_one(
            {"_id": ObjectId(product_id), "user_id": user_id},
            {"$set": {
                "platforms": platforms,
                "platforms_fetched_at": datetime.utcnow().isoformat()
            }}
        )
        
        print(f"[BACKGROUND] Successfully fetched and saved {len(platforms)} platforms for product {product_id}")
        
    except Exception as e:
        print(f"[BACKGROUND] Error fetching platforms for product {product_id}: {e}")
        import traceback
        traceback.print_exc()
        # Don't raise - background failures shouldn't affect user experience


# ============================================================================
# BOARD ENDPOINTS
# ============================================================================

@router.post("/boards", response_model=BoardResponse)
async def create_board_endpoint(
    request: CreateBoardRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Create a new inspiration board"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        result = await create_board(user_id, request)
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create board")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards", response_model=BoardListResponse)
async def list_boards_endpoint(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """List all boards for a user"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        result = await get_boards(user_id, limit, offset)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards/{board_id}", response_model=BoardDetailResponse)
async def get_board_endpoint(
    board_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Get board details with products"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        result = await get_board_detail(user_id, board_id)
        if not result:
            raise HTTPException(status_code=404, detail="Board not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/boards/{board_id}", response_model=BoardResponse)
async def update_board_endpoint(
    board_id: str,
    request: UpdateBoardRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Update a board"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        result = await update_board(user_id, board_id, request)
        if not result:
            raise HTTPException(status_code=404, detail="Board not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/boards/{board_id}")
async def delete_board_endpoint(
    board_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Delete a board and all its products"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        result = await delete_board(user_id, board_id)
        if not result.get("deleted"):
            raise HTTPException(status_code=404, detail=result.get("error", "Board not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRODUCT ENDPOINTS
# ============================================================================

@router.post("/boards/{board_id}/products", response_model=ProductResponse)
async def add_product_from_url_endpoint(
    board_id: str,
    request: AddProductFromURLRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Query(..., description="User ID"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Add product to board from URL - requires pre-fetched data from /fetch-product endpoint"""
    try:
        # This endpoint should ONLY add products, NOT scrape
        # Pre-fetched data MUST be provided from /fetch-product endpoint
        if not request.fetched_data:
            raise HTTPException(
                status_code=400,
                detail="Pre-fetched product data is required. Please call /fetch-product endpoint first and pass the result in 'fetched_data' field."
            )
        
        # Use pre-fetched data (from /fetch-product endpoint) - NO scraping here!
        fetched_data = request.fetched_data
        print(f"Adding product to board using pre-fetched data for {request.url}")
        
        # Validate fetched data - ensure we have minimum required data
        if not fetched_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid pre-fetched product data: data is empty"
            )
        
        # Check if we have at least name or URL (minimum requirement)
        has_name = fetched_data.get("name") and fetched_data.get("name") != "Unknown Product"
        has_url = request.url and request.url.strip()
        
        if not has_name and not has_url:
            error_msg = fetched_data.get("message", "Invalid product data")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pre-fetched product data: {error_msg}. Please ensure /fetch-product returned valid data."
            )
        
        # Add product to board
        try:
            result = await add_product_from_url(user_id, board_id, request, fetched_data)
            
            if not result:
                raise HTTPException(status_code=404, detail="Board not found or access denied")
            
            # Trigger background task to fetch platforms
            product_id = result.get("product_id")
            if product_id:
                background_tasks.add_task(fetch_platforms_for_product_background, product_id, user_id)
            
            return result
        except Exception as e:
            # Provide more specific error messages
            error_msg = str(e)
            if "Board not found" in error_msg or "access denied" in error_msg.lower():
                raise HTTPException(status_code=404, detail=error_msg)
            elif "Invalid product data" in error_msg or "Failed to insert" in error_msg:
                raise HTTPException(status_code=400, detail=error_msg)
            else:
                # Re-raise to be caught by outer exception handler
                raise
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR adding product: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boards/{board_id}/products/manual", response_model=ProductResponse)
async def add_product_manual_endpoint(
    board_id: str,
    request: AddProductManualRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token),  # JWT token validation
    user_id: str = Query(..., description="User ID")
):
    """Add product to board manually"""
    try:
        # Validate tags
        if request.tags:
            tag_validation = await validate_tags(request.tags)
            if tag_validation.get("invalid"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid tags: {', '.join(tag_validation['invalid'])}"
                )
            request.tags = tag_validation["valid"]
        
        result = await add_product_manual(user_id, board_id, request)
        
        if not result:
            raise HTTPException(status_code=404, detail="Board not found or access denied")
        
        # Trigger background task to fetch platforms
        product_id = result.get("product_id")
        if product_id:
            background_tasks.add_task(fetch_platforms_for_product_background, product_id, user_id)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product_endpoint(
    product_id: str,
    user_id: str = Query(..., description="User ID"),
    include_feature_data: bool = Query(False, description="Include full feature history data")
):
    """Get product details with optional feature data"""
    try:
        result = await get_product(user_id, product_id)
        if not result:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # If product has history link and feature data is requested, fetch it
        if include_feature_data and result.get("history_link"):
            history_link = result["history_link"]
            feature_data = await get_feature_history(
                history_link["feature_type"], 
                history_link["history_id"]
            )
            if feature_data:
                result["feature_data"] = feature_data
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product_endpoint(
    product_id: str,
    request: UpdateProductRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token),  # JWT token validation
    user_id: str = Query(..., description="User ID")
):
    """Update product (notes, tags, myRating)"""
    try:
        # Validate tags if provided
        if request.tags:
            tag_validation = await validate_tags(request.tags)
            if tag_validation.get("invalid"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid tags: {', '.join(tag_validation['invalid'])}"
                )
            request.tags = tag_validation["valid"]
        
        result = await update_product(user_id, product_id, request)
        if not result:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Trigger background task to fetch platforms (in case product name was updated)
        background_tasks.add_task(fetch_platforms_for_product_background, product_id, user_id)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/products/{product_id}")
async def delete_product_endpoint(
    product_id: str,
    user_id: str = Query(..., description="User ID"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Delete product"""
    try:
        result = await delete_product(user_id, product_id)
        if not result.get("deleted"):
            raise HTTPException(status_code=404, detail=result.get("error", "Product not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# URL FETCHING ENDPOINT
# ============================================================================

@router.post("/fetch-product", response_model=FetchProductResponse)
async def fetch_product_endpoint(
    request: FetchProductRequest,
    force_refresh: bool = Query(False, description="Force refresh cache and scrape fresh data"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Fetch product data from e-commerce URL with 30-day caching support"""
    try:
        result = await fetch_product_from_url(request.url, force_refresh=force_refresh)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMPETITOR ANALYSIS ENDPOINTS
# ============================================================================

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_competitors_endpoint(
    request: AnalysisRequest,
    user_id: str = Query(..., description="User ID"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Generate competitor analysis"""
    try:
        # Verify all products belong to user
        from app.ai_ingredient_intelligence.db.collections import inspiration_products_col
        from bson import ObjectId
        
        product_obj_ids = []
        for pid in request.product_ids:
            try:
                product_obj_ids.append(ObjectId(pid))
            except:
                raise HTTPException(status_code=400, detail=f"Invalid product ID: {pid}")
        
        # Verify ownership
        products = await inspiration_products_col.find({
            "_id": {"$in": product_obj_ids},
            "user_id": user_id
        }).to_list(length=len(product_obj_ids))
        
        if len(products) != len(request.product_ids):
            raise HTTPException(status_code=403, detail="Some products not found or access denied")
        
        # Generate analysis
        result = await analyze_competitors(request.product_ids, request.analysis_type)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-board", response_model=ExportToBoardResponse)
async def export_to_board_endpoint(
    request: ExportToBoardRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Query(..., description="User ID"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Export products from multiple features to an inspiration board"""
    try:
        # Verify board exists and belongs to user
        board_detail = await get_board_detail(user_id, request.board_id)
        if not board_detail:
            raise HTTPException(status_code=404, detail="Board not found or access denied")
        
        exported_products = []
        skipped_count = 0
        duplicates_count = 0
        errors = []
        
        # Process each export item
        for export_item in request.exports:
            feature_type = export_item.feature_type
            history_ids = export_item.history_ids
            
            # Validate history IDs
            validation = await validate_history_ids(feature_type, history_ids)
            
            if validation["invalid_count"] > 0:
                errors.append(f"{feature_type}: {validation['invalid_count']} invalid history IDs")
                skipped_count += validation["invalid_count"]
            
            # Process valid history IDs
            for history_id in validation["valid_ids"]:
                try:
                    # Fetch history data
                    history_data = await get_feature_history(feature_type, history_id)
                    if not history_data:
                        errors.append(f"{feature_type}: History ID {history_id} not found")
                        skipped_count += 1
                        continue
                    
                    # Extract product data
                    product_data = await extract_product_data_from_history(feature_type, history_data)
                    
                    # Check for duplicates within this board
                    if await _is_duplicate_in_board(request.board_id, product_data):
                        duplicates_count += 1
                        continue
                    
                    # Add history link
                    product_config = get_product_type_config(feature_type)
                    product_data["history_link"] = {
                        "feature_type": feature_type,
                        "history_id": history_id,
                        "source_description": f"{product_config['label']} from {history_data.get('created_at', 'unknown date')}"
                    }
                    
                    # Add product to board
                    added_product = await _add_exported_product_to_board(user_id, request.board_id, product_data)
                    if added_product:
                        exported_products.append(added_product)
                        # Trigger background task to fetch platforms
                        product_id = added_product.get("product_id")
                        if product_id:
                            background_tasks.add_task(fetch_platforms_for_product_background, product_id, user_id)
                    else:
                        errors.append(f"Failed to add product from {feature_type} history ID {history_id}")
                        skipped_count += 1
                        
                except Exception as e:
                    errors.append(f"Error processing {feature_type} history ID {history_id}: {str(e)}")
                    skipped_count += 1
        
        return ExportToBoardResponse(
            success=len(exported_products) > 0,
            exported_count=len(exported_products),
            skipped_count=skipped_count,
            duplicates_count=duplicates_count,
            errors=errors,
            exported_products=exported_products
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR in export to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _is_duplicate_in_board(board_id: str, product_data: dict) -> bool:
    """Check if product already exists in the board"""
    from app.ai_ingredient_intelligence.db.collections import inspiration_products_col
    from bson import ObjectId
    
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return False
    
    # Check for duplicates by URL or name+brand
    duplicate_query = {
        "board_id": board_obj_id,
        "$or": [
            {"url": product_data.get("url")},
            {"name": product_data["name"], "brand": product_data.get("brand")}
        ]
    }
    
    # Only check URL if it exists
    if not product_data.get("url"):
        duplicate_query["$or"] = [{"name": product_data["name"], "brand": product_data.get("brand")}]
    
    existing = await inspiration_products_col.find_one(duplicate_query)
    return existing is not None


async def _add_exported_product_to_board(user_id: str, board_id: str, product_data: dict) -> Optional[dict]:
    """Add exported product to board using existing product manager logic"""
    from app.ai_ingredient_intelligence.logic.product_manager import add_product_manual
    from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import AddProductManualRequest
    from bson import ObjectId
    
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return None
    
    # Create manual product request
    manual_request = AddProductManualRequest(
        name=product_data["name"],
        brand=product_data.get("brand", "Unknown"),
        url=product_data.get("url"),
        platform=product_data.get("platform", "other"),
        price=product_data.get("price", 0),
        size=product_data.get("size", 0),
        unit=product_data.get("unit", "ml"),
        category=product_data.get("category"),
        notes=product_data.get("notes"),
        tags=product_data.get("tags", []),
        image=product_data.get("image")
    )
    
    # Add product using existing logic
    result = await add_product_manual(user_id, board_id, manual_request)
    
    if result:
        # Update product with history_link and product_type
        from app.ai_ingredient_intelligence.db.collections import inspiration_products_col
        
        update_data = {}
        if product_data.get("history_link"):
            update_data["history_link"] = product_data["history_link"]
        if product_data.get("product_type"):
            update_data["product_type"] = product_data["product_type"]
        
        if update_data:
            await inspiration_products_col.update_one(
                {"_id": ObjectId(result["product_id"])},
                {"$set": update_data}
            )
            
            # Update result with new fields
            result["history_link"] = product_data.get("history_link")
            result["product_type"] = product_data.get("product_type")
        
        return result
    
    return None


# ============================================================================
# TAGS ENDPOINTS
# ============================================================================

@router.get("/tags", response_model=TagsResponse)
async def get_tags_endpoint(current_user: dict = Depends(verify_jwt_token)):  # JWT token validation
    """Get all available tags organized by category"""
    try:
        await initialize_tags()  # Ensure tags are initialized
        categories = await get_all_tags()
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tags/validate")
async def validate_tags_endpoint(
    tags: List[str],
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Validate tags against available tags"""
    try:
        result = await validate_tags(tags)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

