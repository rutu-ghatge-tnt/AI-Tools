"""
Board management logic for Inspiration Boards
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from app.ai_ingredient_intelligence.db.collections import inspiration_boards_col, inspiration_products_col
from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
    CreateBoardRequest, UpdateBoardRequest, BoardResponse, BoardDetailResponse
)


async def create_board(user_id: str, request: CreateBoardRequest) -> Dict[str, Any]:
    """Create a new inspiration board"""
    board_data = {
        "user_id": user_id,
        "name": request.name,
        "description": request.description or "",
        "icon": request.icon,
        "color": request.color,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "products": []  # Will store product IDs
    }
    
    result = await inspiration_boards_col.insert_one(board_data)
    board_id = str(result.inserted_id)
    
    return {
        "board_id": board_id,
        "user_id": user_id,
        "name": request.name,
        "description": request.description,
        "icon": request.icon,
        "color": request.color,
        "created_at": board_data["created_at"],
        "updated_at": board_data["updated_at"],
        "product_count": 0,
        "decoded_count": 0
    }


async def get_boards(user_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """Get all boards for a user"""
    query = {"user_id": user_id}
    
    # Get total count
    total = await inspiration_boards_col.count_documents(query)
    
    # Get boards with pagination
    cursor = inspiration_boards_col.find(query).sort("created_at", -1).skip(offset).limit(limit)
    boards = []
    
    async for doc in cursor:
        # Count products and decoded products
        product_count = await inspiration_products_col.count_documents({"board_id": ObjectId(doc["_id"])})
        decoded_count = await inspiration_products_col.count_documents({
            "board_id": ObjectId(doc["_id"]),
            "decoded": True
        })
        
        boards.append({
            "board_id": str(doc["_id"]),
            "user_id": doc["user_id"],
            "name": doc["name"],
            "description": doc.get("description", ""),
            "icon": doc.get("icon", "🎯"),
            "color": doc.get("color", "rose"),
            "created_at": doc["created_at"],
            "updated_at": doc.get("updated_at", doc["created_at"]),
            "product_count": product_count,
            "decoded_count": decoded_count
        })
    
    return {
        "boards": boards,
        "total": total,
        "limit": limit,
        "offset": offset
    }


async def get_board_detail(user_id: str, board_id: str) -> Optional[Dict[str, Any]]:
    """Get board details with products"""
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return None
    
    board = await inspiration_boards_col.find_one({
        "_id": board_obj_id,
        "user_id": user_id
    })
    
    if not board:
        return None
    
    # Get all products for this board
    print(f"DEBUG: Getting products for board {board_id} (ObjectId: {board_obj_id})")
    products_cursor = inspiration_products_col.find({"board_id": board_obj_id}).sort("date_added", -1)
    products = []
    
    product_count_before = await inspiration_products_col.count_documents({"board_id": board_obj_id})
    print(f"DEBUG: Found {product_count_before} products in database for this board")
    
    async for product_doc in products_cursor:
        product = await _format_product_summary(product_doc)
        products.append(product)
    
    print(f"DEBUG: Formatted {len(products)} products for response")
    
    # Calculate stats
    if products:
        prices = [p["price"] for p in products if p.get("price")]
        decoded_count = sum(1 for p in products if p.get("decoded"))
        stats = {
            "total_products": len(products),
            "decoded_count": decoded_count,
            "pending_count": len(products) - decoded_count,
            "price_range": {
                "min": min(prices) if prices else 0,
                "max": max(prices) if prices else 0
            },
            "avg_price": sum(prices) / len(prices) if prices else 0
        }
    else:
        stats = {
            "total_products": 0,
            "decoded_count": 0,
            "pending_count": 0,
            "price_range": {"min": 0, "max": 0},
            "avg_price": 0
        }
    
    return {
        "board_id": str(board["_id"]),
        "user_id": board["user_id"],
        "name": board["name"],
        "description": board.get("description", ""),
        "icon": board.get("icon", "🎯"),
        "color": board.get("color", "rose"),
        "created_at": board["created_at"],
        "updated_at": board.get("updated_at", board["created_at"]),
        "products": products,
        "stats": stats
    }


async def update_board(user_id: str, board_id: str, request: UpdateBoardRequest) -> Optional[Dict[str, Any]]:
    """Update a board"""
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return None
    
    update_data = {"updated_at": datetime.utcnow()}
    
    if request.name is not None:
        update_data["name"] = request.name
    if request.description is not None:
        update_data["description"] = request.description
    if request.icon is not None:
        update_data["icon"] = request.icon
    if request.color is not None:
        update_data["color"] = request.color
    
    result = await inspiration_boards_col.update_one(
        {"_id": board_obj_id, "user_id": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        return None
    
    # Return updated board
    return await get_board_detail(user_id, board_id)


async def delete_board(user_id: str, board_id: str) -> Dict[str, Any]:
    """Delete a board and all its products"""
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return {"deleted": False, "error": "Invalid board ID"}
    
    # Check if board exists and belongs to user
    board = await inspiration_boards_col.find_one({
        "_id": board_obj_id,
        "user_id": user_id
    })
    
    if not board:
        return {"deleted": False, "error": "Board not found"}
    
    # Delete all products
    delete_result = await inspiration_products_col.delete_many({"board_id": board_obj_id})
    products_deleted = delete_result.deleted_count
    
    # Delete board
    await inspiration_boards_col.delete_one({"_id": board_obj_id})
    
    return {
        "deleted": True,
        "board_id": board_id,
        "products_deleted": products_deleted
    }


def _filter_platforms_for_list(platforms: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """Filter platforms to only include fields needed for list display: title, logo_url, platform_display_name"""
    if not platforms:
        return None
    
    filtered = []
    for platform in platforms:
        if isinstance(platform, dict):
            filtered.append({
                "title": platform.get("title", ""),
                "logo_url": platform.get("logo_url"),
                "platform_display_name": platform.get("platform_display_name", platform.get("platform", ""))
            })
    
    return filtered if filtered else None


async def _format_product_summary(product_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format product document as summary (excludes large decoded_data)"""
    decoded_data = product_doc.get("decoded_data") if product_doc.get("decoded") else None
    has_decoded_data = decoded_data is not None
    
    # Extract summary fields from decoded_data if available
    hero_ingredients_preview = None
    estimated_cost = None
    if decoded_data and isinstance(decoded_data, dict):
        hero_ingredients = decoded_data.get("hero_ingredients", [])
        if hero_ingredients and isinstance(hero_ingredients, list):
            hero_ingredients_preview = hero_ingredients[:3]  # First 3 only
        estimated_cost = decoded_data.get("estimated_cost")
    
    # Handle image based on product type (use emoji for formulations)
    image = product_doc.get("image", "🧴")
    product_type = product_doc.get("product_type")
    if product_type == "formulation":
        # Use emoji for formulations instead of real images
        image = "✨"
    
    # Filter platforms to only include title, logo_url, and platform_display_name for list display
    platforms_raw = product_doc.get("platforms")
    platforms_filtered = _filter_platforms_for_list(platforms_raw)
    
    return {
        "product_id": str(product_doc["_id"]),
        "board_id": str(product_doc["board_id"]),
        "user_id": product_doc["user_id"],
        "name": product_doc["name"],
        "brand": product_doc["brand"],
        "url": product_doc.get("url"),
        "platform": product_doc.get("platform", "other"),
        "image": image,
        "price": product_doc.get("price", 0),
        "mrp": product_doc.get("mrp"),  # MRP (Maximum Retail Price) - optional
        "size": product_doc.get("size", 0),
        "unit": product_doc.get("unit", "ml"),
        "price_per_ml": product_doc.get("price_per_ml", 0),
        "category": product_doc.get("category"),
        "date_added": product_doc.get("date_added", product_doc.get("created_at")),
        "notes": product_doc.get("notes"),
        "tags": product_doc.get("tags", []),
        "my_rating": product_doc.get("my_rating"),
        "decoded": product_doc.get("decoded", False),
        "created_at": product_doc.get("created_at"),
        "updated_at": product_doc.get("updated_at", product_doc.get("created_at")),
        "has_decoded_data": has_decoded_data,
        "hero_ingredients_preview": hero_ingredients_preview,
        "estimated_cost": estimated_cost,
        # New fields for feature integration
        "product_type": product_doc.get("product_type"),
        "history_link": product_doc.get("history_link"),
        # Platform links filtered for list display (only title, logo_url, platform_display_name)
        "platforms": platforms_filtered,
        "platforms_fetched_at": product_doc.get("platforms_fetched_at")
    }


async def _format_product(product_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format product document for full response (includes decoded_data)"""
    decoded_data = None
    if product_doc.get("decoded") and product_doc.get("decoded_data"):
        decoded_data = product_doc["decoded_data"]
    
    # Handle image based on product type (use emoji for formulations)
    image = product_doc.get("image", "🧴")
    product_type = product_doc.get("product_type")
    if product_type == "formulation":
        # Use emoji for formulations instead of real images
        image = "✨"
    
    return {
        "product_id": str(product_doc["_id"]),
        "board_id": str(product_doc["board_id"]),
        "user_id": product_doc["user_id"],
        "name": product_doc["name"],
        "brand": product_doc["brand"],
        "url": product_doc.get("url"),
        "platform": product_doc.get("platform", "other"),
        "image": image,
        "price": product_doc.get("price", 0),
        "size": product_doc.get("size", 0),
        "unit": product_doc.get("unit", "ml"),
        "price_per_ml": product_doc.get("price_per_ml", 0),
        "category": product_doc.get("category"),
        "date_added": product_doc.get("date_added", product_doc.get("created_at")),
        "notes": product_doc.get("notes"),
        "tags": product_doc.get("tags", []),
        "my_rating": product_doc.get("my_rating"),
        "decoded": product_doc.get("decoded", False),
        "decoded_data": decoded_data,
        "created_at": product_doc.get("created_at"),
        "updated_at": product_doc.get("updated_at", product_doc.get("created_at")),
        # New fields for feature integration
        "product_type": product_doc.get("product_type"),
        "history_link": product_doc.get("history_link"),
        "feature_data": None,  # Will be populated on demand
        # Platform links fetched from Serper API
        "platforms": product_doc.get("platforms"),
        "platforms_fetched_at": product_doc.get("platforms_fetched_at")
    }

