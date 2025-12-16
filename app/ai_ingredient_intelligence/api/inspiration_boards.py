"""
Inspiration Boards API Endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
    CreateBoardRequest, UpdateBoardRequest, BoardResponse, BoardListResponse, BoardDetailResponse,
    AddProductFromURLRequest, AddProductManualRequest, UpdateProductRequest, ProductResponse,
    DecodeProductResponse, BatchDecodeRequest, BatchDecodeResponse,
    FetchProductRequest, FetchProductResponse,
    AnalysisRequest, AnalysisResponse,
    TagsResponse
)
from app.ai_ingredient_intelligence.logic.board_manager import (
    create_board, get_boards, get_board_detail, update_board, delete_board
)
from app.ai_ingredient_intelligence.logic.product_manager import (
    add_product_from_url, add_product_manual, get_product, update_product, delete_product
)
from app.ai_ingredient_intelligence.logic.url_fetcher import fetch_product_from_url
from app.ai_ingredient_intelligence.logic.product_decoder import decode_product
from app.ai_ingredient_intelligence.logic.competitor_analyzer import analyze_competitors
from app.ai_ingredient_intelligence.logic.product_tags import get_all_tags, validate_tags, initialize_tags
from datetime import datetime

router = APIRouter(prefix="/inspiration-boards", tags=["Inspiration Boards"])


# ============================================================================
# BOARD ENDPOINTS
# ============================================================================

@router.post("/boards", response_model=BoardResponse)
async def create_board_endpoint(
    request: CreateBoardRequest,
    user_id: str = Query(..., description="User ID")
):
    """Create a new inspiration board"""
    try:
        result = await create_board(user_id, request)
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create board")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards", response_model=BoardListResponse)
async def list_boards_endpoint(
    user_id: str = Query(..., description="User ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List all boards for a user"""
    try:
        result = await get_boards(user_id, limit, offset)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards/{board_id}", response_model=BoardDetailResponse)
async def get_board_endpoint(
    board_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Get board details with products"""
    try:
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
    user_id: str = Query(..., description="User ID")
):
    """Update a board"""
    try:
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
    user_id: str = Query(..., description="User ID")
):
    """Delete a board and all its products"""
    try:
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
    user_id: str = Query(..., description="User ID")
):
    """Add product to board from URL"""
    try:
        # Fetch product data from URL
        fetched_data = await fetch_product_from_url(request.url)
        
        # Be more lenient - if we have any data, proceed (even if success is False)
        if not fetched_data or (not fetched_data.get("success") and not fetched_data.get("name") and not fetched_data.get("platform")):
            raise HTTPException(
                status_code=400,
                detail=fetched_data.get("message", "Failed to fetch product from URL") if fetched_data else "Failed to fetch product from URL"
            )
        
        # Add product to board
        result = await add_product_from_url(user_id, board_id, request, fetched_data)
        
        if not result:
            raise HTTPException(status_code=404, detail="Board not found or access denied")
        
        return result
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
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product_endpoint(
    product_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Get product details"""
    try:
        result = await get_product(user_id, product_id)
        if not result:
            raise HTTPException(status_code=404, detail="Product not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product_endpoint(
    product_id: str,
    request: UpdateProductRequest,
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
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/products/{product_id}")
async def delete_product_endpoint(
    product_id: str,
    user_id: str = Query(..., description="User ID")
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
# PRODUCT DECODING ENDPOINTS
# ============================================================================

@router.post("/products/{product_id}/decode", response_model=DecodeProductResponse)
async def decode_product_endpoint(
    product_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Decode a product (analyze ingredients)"""
    try:
        result = await decode_product(user_id, product_id)
        
        if not result.get("success"):
            # Check if it's a timeout/cancellation error
            error_msg = result.get("error", "Failed to decode product")
            if "cancelled" in error_msg.lower() or "timeout" in error_msg.lower():
                raise HTTPException(
                    status_code=408,  # Request Timeout
                    detail=error_msg
                )
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )
        
        return {
            "product_id": product_id,
            "decoded": result["decoded"],
            "decoded_data": result.get("decoded_data"),
            "message": result.get("message")
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        # Handle operation cancelled errors
        if "_OperationCancelled" in error_msg or "operation cancelled" in error_msg.lower():
            raise HTTPException(
                status_code=408,
                detail="Operation was cancelled. This may happen if the request was interrupted. Please try again."
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/boards/{board_id}/decode-all", response_model=BatchDecodeResponse)
async def batch_decode_endpoint(
    board_id: str,
    request: BatchDecodeRequest,
    user_id: str = Query(..., description="User ID")
):
    """Batch decode all undecoded products in a board"""
    try:
        from app.ai_ingredient_intelligence.db.collections import inspiration_products_col, inspiration_boards_col
        from bson import ObjectId
        
        # Verify board belongs to user
        try:
            board_obj_id = ObjectId(board_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid board ID")
        
        board = await inspiration_boards_col.find_one({
            "_id": board_obj_id,
            "user_id": user_id
        })
        
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")
        
        # Get products to decode
        if request.product_ids:
            # Decode specific products
            product_obj_ids = [ObjectId(pid) for pid in request.product_ids]
            query = {
                "_id": {"$in": product_obj_ids},
                "board_id": board_obj_id,
                "user_id": user_id,
                "decoded": False
            }
        else:
            # Decode all undecoded products in board
            query = {
                "board_id": board_obj_id,
                "user_id": user_id,
                "decoded": False
            }
        
        try:
            products_cursor = inspiration_products_col.find(query)
            products = []
            async for p in products_cursor:
                products.append(p)
        except Exception as e:
            error_msg = str(e)
            if "_OperationCancelled" in error_msg or "operation cancelled" in error_msg.lower():
                raise HTTPException(
                    status_code=408,
                    detail="Database operation was cancelled while fetching products. Please try again."
                )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch products: {error_msg}"
            )
        
        # Decode each product
        results = []
        decoded_count = 0
        failed_count = 0
        
        for product in products:
            product_id = str(product["_id"])
            decode_result = await decode_product(user_id, product_id)
            
            if decode_result.get("success"):
                decoded_count += 1
                results.append({
                    "product_id": product_id,
                    "status": "success",
                    "decoded": True
                })
            else:
                failed_count += 1
                results.append({
                    "product_id": product_id,
                    "status": "failed",
                    "error": decode_result.get("error", "Unknown error")
                })
        
        return {
            "decoded_count": decoded_count,
            "failed_count": failed_count,
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        # Handle operation cancelled errors
        if "_OperationCancelled" in error_msg or "operation cancelled" in error_msg.lower():
            raise HTTPException(
                status_code=408,
                detail="Operation was cancelled. This may happen if the request was interrupted. Please try again."
            )
        raise HTTPException(status_code=500, detail=error_msg)


# ============================================================================
# URL FETCHING ENDPOINT
# ============================================================================

@router.post("/fetch-product", response_model=FetchProductResponse)
async def fetch_product_endpoint(request: FetchProductRequest):
    """Fetch product data from e-commerce URL"""
    try:
        result = await fetch_product_from_url(request.url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMPETITOR ANALYSIS ENDPOINTS
# ============================================================================

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_competitors_endpoint(
    request: AnalysisRequest,
    user_id: str = Query(..., description="User ID")
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
# TAGS ENDPOINTS
# ============================================================================

@router.get("/tags", response_model=TagsResponse)
async def get_tags_endpoint():
    """Get all available tags organized by category"""
    try:
        await initialize_tags()  # Ensure tags are initialized
        categories = await get_all_tags()
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tags/validate")
async def validate_tags_endpoint(tags: List[str]):
    """Validate tags against available tags"""
    try:
        result = await validate_tags(tags)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

