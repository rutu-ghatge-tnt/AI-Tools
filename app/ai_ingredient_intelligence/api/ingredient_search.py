"""Ingredient Search API - Autocomplete for ingredient names"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Optional

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.db.collections import (
    branded_ingredients_col, 
    inci_col,
    distributor_col,
    suppliers_col
)

router = APIRouter(prefix="/ingredients", tags=["Ingredient Search"])


@router.get("/search")
async def search_ingredients(
    query: str,
    limit: int = 10,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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
async def get_ingredient_by_name(
    name: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
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


@router.get("/by-supplier/{supplier_name}")
async def get_ingredients_by_supplier(
    supplier_name: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Get all ingredients for a specific supplier by supplier name"""
    try:
        from bson import ObjectId
        
        # First, find the supplier by name (case-insensitive, exact match)
        # Try exact match first
        supplier_doc = await suppliers_col.find_one(
            {"supplierName": {"$regex": f"^{supplier_name.strip()}$", "$options": "i"}}
        )
        
        # If not found, try without case sensitivity and with trimmed whitespace
        if not supplier_doc:
            # Try with trimmed supplier name from DB
            all_suppliers = await suppliers_col.find(
                {"supplierName": {"$regex": supplier_name.strip(), "$options": "i"}}
            ).to_list(length=None)
            
            # Find the best match (exact case-insensitive match preferred)
            supplier_name_lower = supplier_name.strip().lower()
            for sup in all_suppliers:
                if sup.get("supplierName", "").strip().lower() == supplier_name_lower:
                    supplier_doc = sup
                    break
            
            # If still not found, use first match if any
            if not supplier_doc and all_suppliers:
                supplier_doc = all_suppliers[0]
        
        if not supplier_doc:
            raise HTTPException(
                status_code=404, 
                detail=f'Supplier "{supplier_name}" not found. Please verify the supplier name.'
            )
        
        supplier_id = supplier_doc["_id"]
        
        # Find all ingredients with this supplier_id
        # Handle both ObjectId and string formats (supplier_id can be stored as either)
        query = {
            "$or": [
                {"supplier_id": supplier_id},  # ObjectId match
                {"supplier_id": str(supplier_id)}  # String match
            ]
        }
        cursor = branded_ingredients_col.find(
            query,
            {
                "ingredient_name": 1,
                "original_inci_name": 1,
                "inci_ids": 1,
                "_id": 1,
                "category_decided": 1,
                "supplier_id": 1
            }
        )
        
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
        
        return {
            "supplier": supplier_doc.get("supplierName", ""),
            "ingredients": results,
            "count": len(results)
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/by-supplier-id/{supplier_id}")
async def get_ingredients_by_supplier_id(
    supplier_id: str,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term to filter ingredients by name"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Get all ingredients for a specific supplier by supplier ID with pagination and search"""
    try:
        from bson import ObjectId
        
        # Validate and convert supplier_id to ObjectId
        try:
            supplier_object_id = ObjectId(supplier_id)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=f'Invalid supplier ID format: "{supplier_id}". Must be a valid MongoDB ObjectId.'
            )
        
        # Find the supplier by ID
        supplier_doc = await suppliers_col.find_one({"_id": supplier_object_id})
        
        if not supplier_doc:
            raise HTTPException(
                status_code=404,
                detail=f'Supplier with ID "{supplier_id}" not found.'
            )
        
        # Find all ingredients with this supplier_id
        # Handle both ObjectId and string formats (supplier_id can be stored as either)
        base_query = {
            "$or": [
                {"supplier_id": supplier_object_id},  # ObjectId match
                {"supplier_id": str(supplier_object_id)}  # String match
            ]
        }
        
        # Add search filter if provided
        if search:
            search_trimmed = search.strip()
            if search_trimmed:
                # Escape special regex characters and add search condition
                import re
                search_pattern = re.escape(search_trimmed)
                query = {
                    "$and": [
                        base_query,
                        {
                            "$or": [
                                {"ingredient_name": {"$regex": search_pattern, "$options": "i"}},
                                {"original_inci_name": {"$regex": search_pattern, "$options": "i"}}
                            ]
                        }
                    ]
                }
            else:
                query = base_query
        else:
            query = base_query
        
        # Get total count for pagination
        total = await branded_ingredients_col.count_documents(query)
        
        # Get paginated results
        cursor = branded_ingredients_col.find(
            query,
            {
                "ingredient_name": 1,
                "original_inci_name": 1,
                "inci_ids": 1,
                "_id": 1,
                "category_decided": 1,
                "supplier_id": 1
            }
        ).skip(skip).limit(limit)
        
        # Collect paginated ingredient documents
        all_docs = await cursor.to_list(length=None)
        
        if not all_docs:
            return {
                "supplier_id": str(supplier_object_id),
                "supplier_name": supplier_doc.get("supplierName", ""),
                "supplier": supplier_doc.get("supplierName", ""),  # For backward compatibility
                "ingredients": [],
                "total": total,
                "skip": skip,
                "limit": limit,
                "hasMore": False,
                "count": 0
            }
        
        # Batch fetch: Collect all INCI IDs and ingredient IDs for batch queries
        all_inci_ids = []
        all_ingredient_ids = []
        doc_inci_map = {}  # Map ingredient_id -> list of inci_ids
        
        for doc in all_docs:
            ing_id = str(doc["_id"])
            all_ingredient_ids.append(ing_id)
            
            # Collect INCI IDs for batch lookup
            if doc.get("inci_ids"):
                # Filter valid ObjectIds
                valid_inci_ids = []
                for inci_id in doc["inci_ids"]:
                    try:
                        if isinstance(inci_id, str):
                            valid_inci_ids.append(ObjectId(inci_id))
                        else:
                            valid_inci_ids.append(inci_id)
                    except:
                        pass
                if valid_inci_ids:
                    doc_inci_map[ing_id] = valid_inci_ids
                    all_inci_ids.extend(valid_inci_ids)
        
        # Batch fetch all INCI documents
        inci_map = {}  # Map inci_id (ObjectId) -> {inciName, category}
        if all_inci_ids:
            # Remove duplicates by converting to string set, then back to ObjectId list
            unique_inci_ids = []
            seen = set()
            for inci_id in all_inci_ids:
                inci_id_str = str(inci_id)
                if inci_id_str not in seen:
                    seen.add(inci_id_str)
                    unique_inci_ids.append(inci_id)
            
            inci_cursor = inci_col.find(
                {"_id": {"$in": unique_inci_ids}},
                {"inciName": 1, "category": 1}
            )
            async for inci_doc in inci_cursor:
                inci_id_obj = inci_doc["_id"]
                inci_map[inci_id_obj] = {
                    "inciName": inci_doc.get("inciName", ""),
                    "category": inci_doc.get("category", "")
                }
        
        # Batch fetch distributor costs by supplierId (one query for all)
        supplier_distributor = None
        supplier_distributor_doc = await distributor_col.find_one(
            {"supplierId": str(supplier_object_id)},
            sort=[("createdAt", -1)]
        )
        if supplier_distributor_doc:
            try:
                price = supplier_distributor_doc.get("pricePerKg")
                if price is not None:
                    supplier_distributor = float(price)
            except (ValueError, TypeError):
                pass
        
        # Batch fetch distributor costs by ingredientIds
        ingredient_distributors = {}  # Map ingredient_id -> cost_per_kg
        if all_ingredient_ids:
            distributor_cursor = distributor_col.find(
                {"ingredientIds": {"$in": all_ingredient_ids}},
                {"ingredientIds": 1, "pricePerKg": 1, "createdAt": 1}
            ).sort("createdAt", -1)
            
            async for dist_doc in distributor_cursor:
                price = dist_doc.get("pricePerKg")
                if price is not None:
                    try:
                        cost = float(price)
                        # Map each ingredientId to this cost (latest wins due to sort)
                        for ing_id in dist_doc.get("ingredientIds", []):
                            if ing_id not in ingredient_distributors:
                                ingredient_distributors[ing_id] = cost
                    except (ValueError, TypeError):
                        pass
        
        # Build results
        results = []
        for doc in all_docs:
            ing_id = str(doc["_id"])
            ing_name = doc.get("ingredient_name", "")
            
            # Get INCI name - prefer original_inci_name, fallback to inci_ids
            inci_name = doc.get("original_inci_name", "")
            inci_names = []
            category = doc.get("category_decided", "")
            
            # If no original_inci_name, get from inci_ids (using batch-fetched data)
            if not inci_name and ing_id in doc_inci_map:
                for inci_id_obj in doc_inci_map[ing_id]:
                    if inci_id_obj in inci_map:
                        inci_data = inci_map[inci_id_obj]
                        inci_name_from_db = inci_data.get("inciName", "")
                        if inci_name_from_db:
                            inci_names.append(inci_name_from_db)
                            if not inci_name:
                                inci_name = inci_name_from_db
                        if not category:
                            category = inci_data.get("category", "")
            
            if inci_name and inci_name not in inci_names:
                inci_names.insert(0, inci_name)
            
            # Get cost from distributor - try supplier-level first, then ingredient-level
            cost_per_kg = None
            
            # Try supplier-level distributor first
            if supplier_distributor is not None:
                cost_per_kg = supplier_distributor
            
            # If not found, try ingredient-level distributor
            if cost_per_kg is None and ing_id in ingredient_distributors:
                cost_per_kg = ingredient_distributors[ing_id]
            
            # Default cost based on category
            if cost_per_kg is None:
                if category == "Active":
                    cost_per_kg = 5000
                else:
                    cost_per_kg = 500
            
            result_item = {
                "ingredient_id": ing_id,
                "ingredient_name": ing_name,
                "original_inci_name": inci_name or (inci_names[0] if inci_names else ""),
                "category": category or "Other",
                "supplier_id": str(supplier_object_id)
            }
            results.append(result_item)
        
        return {
            "supplier_id": str(supplier_object_id),
            "supplier_name": supplier_doc.get("supplierName", ""),  # Optional for backward compatibility
            "supplier": supplier_doc.get("supplierName", ""),  # Actual field name from API
            "ingredients": results,
            "total": total,
            "skip": skip,
            "limit": limit,
            "hasMore": (skip + limit) < total,
            "count": len(results)  # Some responses include count
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

