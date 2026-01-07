"""
Product management logic for Inspiration Boards
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from app.ai_ingredient_intelligence.db.collections import inspiration_products_col, inspiration_boards_col
from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
    AddProductFromURLRequest, AddProductManualRequest, UpdateProductRequest, ProductResponse
)


async def add_product_from_url(
    user_id: str,
    board_id: str,
    request: AddProductFromURLRequest,
    fetched_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Add product to board from URL"""
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return None
    
    # Verify board belongs to user
    board = await inspiration_boards_col.find_one({
        "_id": board_obj_id,
        "user_id": user_id
    })
    
    if not board:
        return None
    
    # Calculate price_per_ml (handle None values)
    price = fetched_data.get("price") or 0
    size = fetched_data.get("size") or 0
    price_per_ml = price / size if size > 0 else 0
    
    # Ensure price and size are numbers
    try:
        price = float(price) if price else 0
        size = float(size) if size else 0
    except (ValueError, TypeError):
        price = 0
        size = 0
    
    product_data = {
        "board_id": board_obj_id,
        "user_id": user_id,
        "name": fetched_data.get("name", "Unknown Product"),
        "brand": fetched_data.get("brand", "Unknown Brand"),
        "url": request.url,
        "platform": fetched_data.get("platform", "other"),
        "image": fetched_data.get("image", "🧴"),
        "price": price,
        "size": size,
        "unit": fetched_data.get("unit", "ml"),
        "price_per_ml": price_per_ml,
        "category": fetched_data.get("category"),
        "date_added": datetime.utcnow(),
        "notes": request.notes or "",
        "tags": request.tags or [],
        "my_rating": None,
        "decoded": False,
        "decoded_data": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    # Validate tags if provided
    if request.tags:
        from app.ai_ingredient_intelligence.logic.product_tags import validate_tags
        tag_validation = await validate_tags(request.tags)
        if tag_validation.get("invalid"):
            # Log but don't fail - just use valid tags
            print(f"WARNING: Invalid tags filtered: {tag_validation.get('invalid')}")
        product_data["tags"] = tag_validation.get("valid", [])
    
    # Insert product
    try:
        result = await inspiration_products_col.insert_one(product_data)
        product_id = result.inserted_id
    except Exception as e:
        print(f"ERROR: Failed to insert product: {e}")
        raise Exception(f"Failed to insert product: {str(e)}")
    
    # Update board's updated_at timestamp (non-blocking, don't wait for it)
    try:
        await inspiration_boards_col.update_one(
            {"_id": board_obj_id},
            {"$set": {"updated_at": datetime.utcnow()}}
        )
    except Exception as e:
        # Non-critical, log but continue
        print(f"WARNING: Failed to update board timestamp: {e}")
    
    # Format and return product (no verification query needed - insert_one already confirms success)
    formatted_product = await _format_product({
        **product_data,
        "_id": product_id
    })
    
    return formatted_product


async def add_product_manual(
    user_id: str,
    board_id: str,
    request: AddProductManualRequest
) -> Dict[str, Any]:
    """Add product to board manually"""
    try:
        board_obj_id = ObjectId(board_id)
    except:
        return None
    
    # Verify board belongs to user
    board = await inspiration_boards_col.find_one({
        "_id": board_obj_id,
        "user_id": user_id
    })
    
    if not board:
        return None
    
    # Calculate price_per_ml
    price_per_ml = request.price / request.size if request.size > 0 else 0
    
    product_data = {
        "board_id": board_obj_id,
        "user_id": user_id,
        "name": request.name,
        "brand": request.brand,
        "url": request.url,
        "platform": request.platform,
        "image": request.image or "🧴",
        "price": request.price,
        "size": request.size,
        "unit": request.unit,
        "price_per_ml": price_per_ml,
        "category": request.category,
        "date_added": datetime.utcnow(),
        "notes": request.notes or "",
        "tags": request.tags or [],
        "my_rating": None,
        "decoded": False,
        "decoded_data": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await inspiration_products_col.insert_one(product_data)
    
    return await _format_product({
        **product_data,
        "_id": result.inserted_id
    })


async def get_product(user_id: str, product_id: str) -> Optional[Dict[str, Any]]:
    """Get product details"""
    try:
        product_obj_id = ObjectId(product_id)
    except:
        return None
    
    product = await inspiration_products_col.find_one({
        "_id": product_obj_id,
        "user_id": user_id
    })
    
    if not product:
        return None
    
    return await _format_product(product)


async def update_product(
    user_id: str,
    product_id: str,
    request: UpdateProductRequest
) -> Optional[Dict[str, Any]]:
    """Update product"""
    try:
        product_obj_id = ObjectId(product_id)
    except:
        return None
    
    update_data = {"updated_at": datetime.utcnow()}
    
    if request.notes is not None:
        update_data["notes"] = request.notes
    if request.tags is not None:
        update_data["tags"] = request.tags
    if request.my_rating is not None:
        update_data["my_rating"] = request.my_rating
    
    result = await inspiration_products_col.update_one(
        {"_id": product_obj_id, "user_id": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        return None
    
    # Return updated product
    return await get_product(user_id, product_id)


async def delete_product(user_id: str, product_id: str) -> Dict[str, Any]:
    """Delete product"""
    try:
        product_obj_id = ObjectId(product_id)
    except:
        return {"deleted": False, "error": "Invalid product ID"}
    
    result = await inspiration_products_col.delete_one({
        "_id": product_obj_id,
        "user_id": user_id
    })
    
    if result.deleted_count == 0:
        return {"deleted": False, "error": "Product not found"}
    
    return {
        "deleted": True,
        "product_id": product_id
    }


async def _format_product(product_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format product document for response"""
    decoded_data = None
    if product_doc.get("decoded") and product_doc.get("decoded_data"):
        decoded_data = product_doc["decoded_data"]
    
    return {
        "product_id": str(product_doc["_id"]),
        "board_id": str(product_doc["board_id"]),
        "user_id": product_doc["user_id"],
        "name": product_doc["name"],
        "brand": product_doc["brand"],
        "url": product_doc.get("url"),
        "platform": product_doc.get("platform", "other"),
        "image": product_doc.get("image", "🧴"),
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
        "updated_at": product_doc.get("updated_at", product_doc.get("created_at"))
    }

