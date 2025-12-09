"""Ingredient Search API - Autocomplete for ingredient names"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict
from app.ai_ingredient_intelligence.db.collections import (
    branded_ingredients_col, 
    inci_col,
    distributor_col
)

router = APIRouter(prefix="/ingredients", tags=["Ingredient Search"])


@router.get("/search")
async def search_ingredients(query: str, limit: int = 10):
    """Search branded ingredients by name - for autocomplete"""
    if not query or len(query) < 2:
        return {"results": []}
    
    try:
        # Don't escape - use flexible regex that handles special characters
        # MongoDB regex handles special characters when using $options: "i"
        search_pattern = query.strip()
        
        # Search in branded ingredients collection - use both ingredient_name and original_inci_name
        cursor = branded_ingredients_col.find(
            {
                "$or": [
                    {"ingredient_name": {"$regex": search_pattern, "$options": "i"}},
                    {"original_inci_name": {"$regex": search_pattern, "$options": "i"}}
                ]
            },
            {
                "ingredient_name": 1, 
                "original_inci_name": 1,
                "inci_ids": 1, 
                "_id": 1,
                "category_decided": 1,
                "supplier_id": 1
            }
        ).limit(limit)
        
        results = []
        async for doc in cursor:
            ing_id = str(doc["_id"])
            ing_name = doc.get("ingredient_name", "")
            
            # Get INCI name - prefer original_inci_name, fallback to inci_ids
            inci_name = doc.get("original_inci_name", "")
            inci_names = []
            category = doc.get("category_decided", "")
            
            # If no original_inci_name, get from inci_ids
            if not inci_name and doc.get("inci_ids"):
                inci_cursor = inci_col.find(
                    {"_id": {"$in": doc["inci_ids"]}},
                    {"inciName": 1, "category": 1}
                )
                async for inci_doc in inci_cursor:
                    inci_name_from_db = inci_doc.get("inciName", "")
                    if inci_name_from_db:
                        inci_names.append(inci_name_from_db)
                        if not inci_name:
                            inci_name = inci_name_from_db
                    if not category:
                        category = inci_doc.get("category", "")
            
            if inci_name and inci_name not in inci_names:
                inci_names.insert(0, inci_name)
            
            # Get cost from distributor using supplier_id or ingredientIds
            cost_per_kg = None
            supplier_id = doc.get("supplier_id")
            
            # Try supplier_id first
            if supplier_id:
                distributor_doc = await distributor_col.find_one(
                    {"supplierId": str(supplier_id)},
                    sort=[("createdAt", -1)]
                )
                if distributor_doc and distributor_doc.get("pricePerKg"):
                    cost_per_kg = float(distributor_doc.get("pricePerKg", 0))
            
            # If not found, try ingredientIds
            if not cost_per_kg:
                distributor_doc = await distributor_col.find_one(
                    {"ingredientIds": ing_id},
                    sort=[("createdAt", -1)]
                )
                if distributor_doc and distributor_doc.get("pricePerKg"):
                    cost_per_kg = float(distributor_doc.get("pricePerKg", 0))
            
            # Default cost based on category
            if not cost_per_kg:
                if category == "Active":
                    cost_per_kg = 5000
                else:
                    cost_per_kg = 500
            
            result_item = {
                "id": ing_id,
                "name": ing_name,
                "inci": inci_name or (inci_names[0] if inci_names else ""),
                "all_inci": inci_names if inci_names else ([inci_name] if inci_name else []),
                "category": category or "Other",
                "cost_per_kg": cost_per_kg
            }
            results.append(result_item)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/by-name/{name}")
async def get_ingredient_by_name(name: str):
    """Get ingredient details by name - returns full details including cost"""
    try:
        import re
        escaped_name = re.escape(name)
        
        # Try exact match first (case insensitive)
        doc = await branded_ingredients_col.find_one(
            {"ingredient_name": {"$regex": f"^{escaped_name}$", "$options": "i"}}
        )
        
        if not doc:
            return {"found": False}
        
        ing_id = str(doc["_id"])
        
        # Get INCI name - prefer original_inci_name
        inci_name = doc.get("original_inci_name", "")
        inci_names = []
        category = doc.get("category_decided", "")
        
        # If no original_inci_name, get from inci_ids
        if not inci_name and doc.get("inci_ids"):
            inci_cursor = inci_col.find(
                {"_id": {"$in": doc["inci_ids"]}},
                {"inciName": 1, "category": 1}
            )
            async for inci_doc in inci_cursor:
                inci_name_from_db = inci_doc.get("inciName", "")
                if inci_name_from_db:
                    inci_names.append({
                        "name": inci_name_from_db,
                        "category": inci_doc.get("category", "")
                    })
                    if not inci_name:
                        inci_name = inci_name_from_db
                if not category:
                    category = inci_doc.get("category", "")
        
        if inci_name and inci_name not in [i["name"] for i in inci_names]:
            inci_names.insert(0, {"name": inci_name, "category": category})
        
        # Get cost from distributor
        cost_per_kg = None
        supplier_id = doc.get("supplier_id")
        
        # Try supplier_id first
        if supplier_id:
            distributor_doc = await distributor_col.find_one(
                {"supplierId": str(supplier_id)},
                sort=[("createdAt", -1)]
            )
            if distributor_doc and distributor_doc.get("pricePerKg"):
                cost_per_kg = float(distributor_doc.get("pricePerKg", 0))
        
        # If not found, try ingredientIds
        if not cost_per_kg:
            distributor_doc = await distributor_col.find_one(
                {"ingredientIds": ing_id},
                sort=[("createdAt", -1)]
            )
            if distributor_doc and distributor_doc.get("pricePerKg"):
                cost_per_kg = float(distributor_doc.get("pricePerKg", 0))
        
        # Default cost based on category
        if not cost_per_kg:
            if category == "Active":
                cost_per_kg = 5000
            else:
                cost_per_kg = 500
        
        return {
            "found": True,
            "id": ing_id,
            "name": doc.get("ingredient_name", ""),
            "inci": inci_name or (inci_names[0]["name"] if inci_names else ""),
            "category": category or "Other",
            "cost_per_kg": cost_per_kg,
            "function": category or "Other",
            "all_inci": [i["name"] for i in inci_names] if inci_names else ([inci_name] if inci_name else [])
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

