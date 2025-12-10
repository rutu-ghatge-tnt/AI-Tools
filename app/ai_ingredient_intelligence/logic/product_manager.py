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
    
    # Calculate price_per_ml
    price = fetched_data.get("price", 0)
    size = fetched_data.get("size", 0)
    price_per_ml = price / size if size > 0 else 0
    
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
        "rating": fetched_data.get("rating"),
        "reviews": fetched_data.get("reviews"),
        "date_added": datetime.utcnow(),
        "notes": request.notes or "",
        "tags": request.tags or [],
        "my_rating": None,
        "decoded": False,
        "decoded_data": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    print(f"DEBUG: Inserting product for board {board_id}, user {user_id}")
    print(f"DEBUG: Product data: name={product_data.get('name')}, brand={product_data.get('brand')}, url={product_data.get('url')}")
    
    result = await inspiration_products_col.insert_one(product_data)
    
    print(f"DEBUG: Product inserted with ID: {result.inserted_id}")
    
    # Update board's updated_at timestamp
    await inspiration_boards_col.update_one(
        {"_id": board_obj_id},
        {"$set": {"updated_at": datetime.utcnow()}}
    )
    
    # Verify the product was inserted
    verify_product = await inspiration_products_col.find_one({"_id": result.inserted_id})
    print(f"DEBUG: Verification - Product found in DB: {verify_product is not None}")
    if verify_product:
        print(f"DEBUG: Product board_id in DB: {verify_product.get('board_id')}, expected: {board_obj_id}")
    
    formatted_product = await _format_product({
        **product_data,
        "_id": result.inserted_id
    })
    
    print(f"DEBUG: Returning formatted product: {formatted_product.get('product_id')}")
    
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
        "rating": request.rating,
        "reviews": request.reviews,
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
        "rating": product_doc.get("rating"),
        "reviews": product_doc.get("reviews"),
        "date_added": product_doc.get("date_added", product_doc.get("created_at")),
        "notes": product_doc.get("notes"),
        "tags": product_doc.get("tags", []),
        "my_rating": product_doc.get("my_rating"),
        "decoded": product_doc.get("decoded", False),
        "decoded_data": decoded_data,
        "created_at": product_doc.get("created_at"),
        "updated_at": product_doc.get("updated_at", product_doc.get("created_at"))
    }

