"""Ingredient Search API - Autocomplete for ingredient names"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Optional, Union
from bson import ObjectId
import re

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.db.collections import (
    branded_ingredients_col, 
    inci_col,
    distributor_col,
    suppliers_col,
    functional_categories_col,
    chemical_classes_col
)
from app.ai_ingredient_intelligence.logic.matcher import build_category_tree
from app.ai_ingredient_intelligence.models.schemas import (
    IngredientInfoRequest,
    IngredientInfoResponse,
    IngredientInfoFull,
    IngredientInfoDescriptionOnly,
    SupplierInfo
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


@router.post("/info", response_model=IngredientInfoResponse)
async def get_ingredients_info(
    request: IngredientInfoRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get ingredient information by names.
    
    If include_all_info is True: Returns all available info including supplier, functionality, cost, etc.
    If include_all_info is False: Returns only the description field.
    
    Description field: Uses enhanced_description if available, otherwise falls back to description.
    
    Request body:
    {
        "ingredient_names": ["Ingredient Name 1", "Ingredient Name 2"],
        "include_all_info": true/false
    }
    """
    try:
        if not request.ingredient_names:
            return IngredientInfoResponse(results=[])
        
        # Build query to find all ingredients by name (case-insensitive)
        # We'll match each ingredient name individually for better accuracy
        ingredient_names_clean = [name.strip() for name in request.ingredient_names if name.strip()]
        if not ingredient_names_clean:
            return IngredientInfoResponse(results=[])
        
        # Helper function to normalize ingredient names for matching
        def normalize_for_match(name: str) -> str:
            """Normalize ingredient name by removing common variations"""
            if not name:
                return ""
            # Remove common prefixes/suffixes and normalize
            normalized = name.lower().strip()
            # Remove content in parentheses (e.g., "Aqua (Water)" -> "Aqua")
            normalized = re.sub(r'\s*\([^)]*\)', '', normalized).strip()
            # Remove extra whitespace
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            return normalized
        
        # Build query to match both ingredient_name and original_inci_name
        # Also try normalized versions (without parentheses)
        query_conditions = []
        for name in ingredient_names_clean:
            escaped_name = re.escape(name)
            normalized_name = normalize_for_match(name)
            escaped_normalized = re.escape(normalized_name)
            
            # Exact match on ingredient_name
            query_conditions.append({"ingredient_name": {"$regex": f"^{escaped_name}$", "$options": "i"}})
            # Exact match on original_inci_name
            query_conditions.append({"original_inci_name": {"$regex": f"^{escaped_name}$", "$options": "i"}})
            
            # If normalized is different, also try normalized match
            if normalized_name != name.lower():
                query_conditions.append({"ingredient_name": {"$regex": f"^{escaped_normalized}$", "$options": "i"}})
                query_conditions.append({"original_inci_name": {"$regex": f"^{escaped_normalized}$", "$options": "i"}})
            
            # Also try partial match (contains) for cases like "Aqua (Water)" matching "Water"
            # But only if the search term is a single word or short
            if len(name.split()) <= 2:
                query_conditions.append({"ingredient_name": {"$regex": escaped_name, "$options": "i"}})
                query_conditions.append({"original_inci_name": {"$regex": escaped_name, "$options": "i"}})
        
        query = {"$or": query_conditions}
        
        # Fetch all matching documents
        cursor = branded_ingredients_col.find(query)
        all_docs = await cursor.to_list(length=None)
        
        # Create a map of ingredient_name (lowercase) -> document for quick lookup
        # Also create maps for normalized names and original_inci_name
        ingredient_map = {}
        normalized_map = {}  # normalized name -> document
        inci_name_map = {}  # original_inci_name (lowercase) -> document
        
        for doc in all_docs:
            ing_name = doc.get("ingredient_name", "").strip()
            ing_name_lower = ing_name.lower()
            original_inci = doc.get("original_inci_name", "").strip()
            original_inci_lower = original_inci.lower() if original_inci else ""
            
            # Map by exact ingredient_name
            if ing_name_lower not in ingredient_map:
                ingredient_map[ing_name_lower] = doc
            
            # Map by normalized ingredient_name (without parentheses)
            ing_name_normalized = normalize_for_match(ing_name)
            if ing_name_normalized and ing_name_normalized not in normalized_map:
                normalized_map[ing_name_normalized] = doc
            
            # Map by original_inci_name (exact and normalized)
            if original_inci_lower:
                if original_inci_lower not in inci_name_map:
                    inci_name_map[original_inci_lower] = doc
                # Also map normalized version of original_inci_name
                original_inci_normalized = normalize_for_match(original_inci)
                if original_inci_normalized and original_inci_normalized not in inci_name_map:
                    inci_name_map[original_inci_normalized] = doc
        
        results = []
        
        # If only description is needed, return simple results
        if not request.include_all_info:
            for ingredient_name in ingredient_names_clean:
                ing_name_lower = ingredient_name.lower()
                ing_name_normalized = normalize_for_match(ingredient_name)
                
                # Try multiple matching strategies
                doc = None
                
                # 1. Try exact match on ingredient_name
                if ing_name_lower in ingredient_map:
                    doc = ingredient_map[ing_name_lower]
                # 2. Try normalized match
                elif ing_name_normalized in normalized_map:
                    doc = normalized_map[ing_name_normalized]
                # 3. Try match on original_inci_name
                elif ing_name_lower in inci_name_map:
                    doc = inci_name_map[ing_name_lower]
                # 4. Try normalized match on original_inci_name
                elif ing_name_normalized in inci_name_map:
                    doc = inci_name_map[ing_name_normalized]
                # 5. Fallback: check if search term is contained in any found document's name
                else:
                    # Search through all found documents for partial match
                    for found_doc in all_docs:
                        found_ing_name = found_doc.get("ingredient_name", "").lower()
                        found_original_inci = found_doc.get("original_inci_name", "").lower()
                        
                        # Check if search term is contained in ingredient_name or original_inci_name
                        if (ing_name_lower in found_ing_name or 
                            ing_name_normalized in found_ing_name or
                            ing_name_lower in found_original_inci or
                            ing_name_normalized in found_original_inci):
                            doc = found_doc
                            break
                
                if doc:
                    # Use enhanced_description if available, otherwise fallback to description
                    description = doc.get("enhanced_description") or doc.get("description")
                    
                    results.append(IngredientInfoDescriptionOnly(
                        ingredient_name=ingredient_name,
                        description=description,
                        found=True
                    ))
                else:
                    results.append(IngredientInfoDescriptionOnly(
                        ingredient_name=ingredient_name,
                        description=None,
                        found=False
                    ))
            
            return IngredientInfoResponse(results=results)
        
        # Full info mode - batch fetch all related data
        # Collect all IDs for batch queries
        all_ingredient_ids = []
        all_inci_ids = []
        all_func_category_ids = []
        all_chem_class_ids = []
        all_supplier_ids = []
        doc_inci_map = {}  # Map ingredient_id -> list of inci_ids
        doc_func_map = {}  # Map ingredient_id -> list of func_category_ids
        doc_chem_map = {}  # Map ingredient_id -> list of chem_class_ids
        
        for doc in all_docs:
            ing_id = str(doc["_id"])
            all_ingredient_ids.append(ing_id)
            
            # Collect INCI IDs
            if doc.get("inci_ids"):
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
            
            # Collect functional category IDs
            if doc.get("functional_category_ids"):
                valid_func_ids = []
                for func_id in doc.get("functional_category_ids", []):
                    try:
                        if isinstance(func_id, str):
                            valid_func_ids.append(ObjectId(func_id))
                        else:
                            valid_func_ids.append(func_id)
                    except:
                        pass
                if valid_func_ids:
                    doc_func_map[ing_id] = valid_func_ids
                    all_func_category_ids.extend(valid_func_ids)
            
            # Collect chemical class IDs
            if doc.get("chemical_class_ids"):
                valid_chem_ids = []
                for chem_id in doc.get("chemical_class_ids", []):
                    try:
                        if isinstance(chem_id, str):
                            valid_chem_ids.append(ObjectId(chem_id))
                        else:
                            valid_chem_ids.append(chem_id)
                    except:
                        pass
                if valid_chem_ids:
                    doc_chem_map[ing_id] = valid_chem_ids
                    all_chem_class_ids.extend(valid_chem_ids)
            
            # Collect supplier IDs
            supplier_id = doc.get("supplier_id")
            if supplier_id:
                if isinstance(supplier_id, ObjectId):
                    all_supplier_ids.append(supplier_id)
                elif isinstance(supplier_id, str):
                    try:
                        all_supplier_ids.append(ObjectId(supplier_id))
                    except:
                        pass
        
        # Batch fetch INCI documents
        inci_map = {}
        if all_inci_ids:
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
                inci_map[inci_doc["_id"]] = {
                    "inciName": inci_doc.get("inciName", ""),
                    "category": inci_doc.get("category", "")
                }
        
        # Batch fetch supplier documents
        supplier_map = {}
        unique_supplier_ids = []
        if all_supplier_ids:
            seen = set()
            for sup_id in all_supplier_ids:
                sup_id_str = str(sup_id)
                if sup_id_str not in seen:
                    seen.add(sup_id_str)
                    unique_supplier_ids.append(sup_id)
            
            if unique_supplier_ids:
                supplier_cursor = suppliers_col.find(
                    {"_id": {"$in": unique_supplier_ids}},
                    {"supplierName": 1}
                )
                async for sup_doc in supplier_cursor:
                    supplier_map[sup_doc["_id"]] = sup_doc.get("supplierName", "")
        
        # Batch fetch distributor costs by supplierId
        supplier_distributor_map = {}
        if unique_supplier_ids:
            for sup_id in unique_supplier_ids:
                dist_doc = await distributor_col.find_one(
                    {"supplierId": str(sup_id)},
                    sort=[("createdAt", -1)]
                )
                if dist_doc and dist_doc.get("pricePerKg") is not None:
                    try:
                        supplier_distributor_map[str(sup_id)] = float(dist_doc.get("pricePerKg", 0))
                    except (ValueError, TypeError):
                        pass
        
        # Batch fetch distributor costs by ingredientIds
        ingredient_distributor_map = {}
        if all_ingredient_ids:
            dist_cursor = distributor_col.find(
                {"ingredientIds": {"$in": all_ingredient_ids}},
                {"ingredientIds": 1, "pricePerKg": 1, "createdAt": 1}
            ).sort("createdAt", -1)
            
            async for dist_doc in dist_cursor:
                price = dist_doc.get("pricePerKg")
                if price is not None:
                    try:
                        cost = float(price)
                        for ing_id in dist_doc.get("ingredientIds", []):
                            if ing_id not in ingredient_distributor_map:
                                ingredient_distributor_map[ing_id] = cost
                    except (ValueError, TypeError):
                        pass
        
        # Build results in the same order as input
        for ingredient_name in ingredient_names_clean:
            ing_name_lower = ingredient_name.lower()
            ing_name_normalized = normalize_for_match(ingredient_name)
            
            # Try multiple matching strategies
            doc = None
            
            # 1. Try exact match on ingredient_name
            if ing_name_lower in ingredient_map:
                doc = ingredient_map[ing_name_lower]
            # 2. Try normalized match
            elif ing_name_normalized in normalized_map:
                doc = normalized_map[ing_name_normalized]
            # 3. Try match on original_inci_name
            elif ing_name_lower in inci_name_map:
                doc = inci_name_map[ing_name_lower]
            # 4. Try normalized match on original_inci_name
            elif ing_name_normalized in inci_name_map:
                doc = inci_name_map[ing_name_normalized]
            # 5. Fallback: check if search term is contained in any found document's name
            else:
                # Search through all found documents for partial match
                for found_doc in all_docs:
                    found_ing_name = found_doc.get("ingredient_name", "").lower()
                    found_original_inci = found_doc.get("original_inci_name", "").lower()
                    
                    # Check if search term is contained in ingredient_name or original_inci_name
                    if (ing_name_lower in found_ing_name or 
                        ing_name_normalized in found_ing_name or
                        ing_name_lower in found_original_inci or
                        ing_name_normalized in found_original_inci):
                        doc = found_doc
                        break
            
            if doc:
                doc = ingredient_map[ing_name_lower]
                ing_id = str(doc["_id"])
                
                # Get enhanced_description if available, otherwise fallback to description
                description = doc.get("enhanced_description") or doc.get("description")
                
                # Get supplier info
                supplier_info = None
                supplier_id = doc.get("supplier_id")
                if supplier_id:
                    supplier_id_str = str(supplier_id) if isinstance(supplier_id, ObjectId) else supplier_id
                    supplier_id_obj = supplier_id if isinstance(supplier_id, ObjectId) else ObjectId(supplier_id)
                    
                    supplier_name = supplier_map.get(supplier_id_obj)
                    if supplier_name:
                        supplier_info = SupplierInfo(
                            supplier_id=supplier_id_str,
                            supplier_name=supplier_name
                        )
                
                # Get category
                category = doc.get("category_decided", "")
                
                # Get INCI names
                inci_names = []
                original_inci = doc.get("original_inci_name", "")
                if original_inci:
                    inci_names.append(original_inci)
                
                if ing_id in doc_inci_map:
                    for inci_id_obj in doc_inci_map[ing_id]:
                        if inci_id_obj in inci_map:
                            inci_name = inci_map[inci_id_obj].get("inciName", "")
                            if inci_name and inci_name not in inci_names:
                                inci_names.append(inci_name)
                            if not category:
                                category = inci_map[inci_id_obj].get("category", "")
                
                # Get functional categories
                functional_categories = []
                if ing_id in doc_func_map:
                    func_ids = doc_func_map[ing_id]
                    for func_id in func_ids:
                        func_tree = await build_category_tree(
                            functional_categories_col,
                            [func_id],
                            "functionalName"
                        )
                        functional_categories.extend(func_tree)
                
                # Get chemical classes
                chemical_classes = []
                if ing_id in doc_chem_map:
                    chem_ids = doc_chem_map[ing_id]
                    for chem_id in chem_ids:
                        chem_tree = await build_category_tree(
                            chemical_classes_col,
                            [chem_id],
                            "chemicalClassName"
                        )
                        chemical_classes.extend(chem_tree)
                
                # Get cost
                cost_per_kg = None
                if supplier_id:
                    supplier_id_str = str(supplier_id) if isinstance(supplier_id, ObjectId) else supplier_id
                    if supplier_id_str in supplier_distributor_map:
                        cost_per_kg = supplier_distributor_map[supplier_id_str]
                
                if cost_per_kg is None and ing_id in ingredient_distributor_map:
                    cost_per_kg = ingredient_distributor_map[ing_id]
                
                # Default cost based on category
                if cost_per_kg is None:
                    if category == "Active":
                        cost_per_kg = 5000.0
                    else:
                        cost_per_kg = 500.0
                
                results.append(IngredientInfoFull(
                    ingredient_id=ing_id,
                    ingredient_name=ingredient_name,
                    description=description,
                    supplier=supplier_info,
                    category=category or None,
                    inci_names=inci_names,
                    functional_categories=functional_categories,
                    chemical_classes=chemical_classes,
                    cost_per_kg=cost_per_kg,
                    found=True
                ))
            else:
                # Ingredient not found
                results.append(IngredientInfoFull(
                    ingredient_id="",
                    ingredient_name=ingredient_name,
                    description=None,
                    supplier=None,
                    category=None,
                    inci_names=[],
                    functional_categories=[],
                    chemical_classes=[],
                    cost_per_kg=None,
                    found=False
                ))
        
        return IngredientInfoResponse(results=results)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

