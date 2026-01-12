"""
Distributor Management API Endpoint
===================================

API endpoints for distributor and supplier management.
Extracted from analyze_inci.py for better modularity.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
import re

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import (
    distributor_col,
    branded_ingredients_col,
    inci_col
)

router = APIRouter(tags=["Distributor Management"])


@router.get("/suppliers")
async def get_suppliers(current_user: dict = Depends(verify_jwt_token)):  # JWT token validation
    """
    Get all valid suppliers from ingre_suppliers collection
    Returns list of supplier names (only suppliers with isValid: true)
    """
    try:
        suppliers_collection = db["ingre_suppliers"]
        # Only return valid suppliers
        cursor = suppliers_collection.find({"isValid": True}, {"supplierName": 1, "_id": 0})
        suppliers = await cursor.to_list(length=None)
        
        # Extract supplier names and sort alphabetically
        supplier_names = sorted([s.get("supplierName", "") for s in suppliers if s.get("supplierName")])
        
        return {"suppliers": supplier_names}
    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch suppliers: {str(e)}")


@router.post("/ingredients/categories")
async def get_ingredient_categories(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get categories (Active/Excipient) for INCI ingredients from ingre_inci collection
    Accepts: { "inci_names": ["INCI1", "INCI2", ...] }
    Returns: { "categories": { "INCI1": "Active", "INCI2": "Excipient", ... } }
    """
    try:
        if "inci_names" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: inci_names")
        
        inci_names = payload["inci_names"]
        if not isinstance(inci_names, list):
            raise HTTPException(status_code=400, detail="inci_names must be a list")
        
        if not inci_names:
            return {"categories": {}}
        
        # Normalize INCI names for matching (lowercase, trim)
        normalized_names = [name.strip().lower() for name in inci_names]
        
        # Query ingre_inci collection for matching INCI names
        # Match on inciName_normalized field
        query = {
            "inciName_normalized": {"$in": normalized_names}
        }
        
        cursor = inci_col.find(query, {"inciName": 1, "inciName_normalized": 1, "category": 1})
        results = await cursor.to_list(length=None)
        
        # Build mapping: normalized_name -> category
        category_map = {}
        for doc in results:
            normalized = doc.get("inciName_normalized", "").strip().lower()
            category = doc.get("category")
            if normalized and category:
                category_map[normalized] = category
        
        # Map back to original INCI names (case-insensitive)
        result_categories = {}
        for original_name in inci_names:
            normalized = original_name.strip().lower()
            if normalized in category_map:
                result_categories[original_name] = category_map[normalized]
        
        return {"categories": result_categories}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching ingredient categories: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch categories: {str(e)}")


@router.get("/suppliers/paginated")
async def get_suppliers_paginated(skip: int = 0, limit: int = 50, search: Optional[str] = None):
    """
    Get valid suppliers with pagination and search (only suppliers with isValid: true)
    """
    try:
        suppliers_collection = db["ingre_suppliers"]
        
        # Build query - only valid suppliers
        query = {"isValid": True}
        if search:
            query["supplierName"] = {"$regex": search, "$options": "i"}
        
        # Get total count
        total = await suppliers_collection.count_documents(query)
        
        # Get paginated results - include _id for supplierId
        cursor = suppliers_collection.find(query, {"supplierName": 1, "_id": 1}).skip(skip).limit(limit)
        suppliers = await cursor.to_list(length=None)
        
        # Map to objects with supplierId and supplierName
        supplier_objects = [
            {
                "supplierId": str(s["_id"]),
                "supplierName": s.get("supplierName", "")
            }
            for s in suppliers if s.get("supplierName")
        ]
        
        return {
            "suppliers": supplier_objects,
            "total": total,
            "skip": skip,
            "limit": limit,
            "hasMore": (skip + limit) < total
        }
    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch suppliers: {str(e)}")


@router.post("/distributor/register")
async def register_distributor(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Register a new distributor and save to distributor collection
    
    Request body:
    {
        "firmName": "ABC Distributors",
        "category": "Pvt Ltd",
        "registeredAddress": "123 Main St, City",
        "contactPersons": [
            {
                "name": "John Doe",
                "number": "+91-1234567890",
                "email": "contact@abc.com",
                "zones": ["India"]
            }
        ],
        "ingredientName": "Hyaluronic Acid",
        "principlesSuppliers": ["Supplier 1", "Supplier 2"],
        "yourInfo": {
            "name": "John Doe",
            "email": "john@abc.com",
            "designation": "Director",
            "contactNo": "+91-9876543210"
        },
        "acceptTerms": true
    }
    """
    try:
        # Validate required fields
        required_fields = ["firmName", "category", "registeredAddress", "contactPersons", 
                         "ingredientName", "principlesSuppliers", "yourInfo", "acceptTerms"]
        for field in required_fields:
            if field not in payload:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        if not payload.get("acceptTerms"):
            raise HTTPException(status_code=400, detail="Terms and conditions must be accepted")
        
        # Validate contact persons
        contact_persons = payload.get("contactPersons", [])
        if not isinstance(contact_persons, list) or len(contact_persons) == 0:
            raise HTTPException(status_code=400, detail="At least one contact person is required")
        
        for idx, contact_person in enumerate(contact_persons):
            if not isinstance(contact_person, dict):
                raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: Must be an object")
            
            contact_fields = ["name", "number", "email", "zones"]
            for field in contact_fields:
                if field not in contact_person:
                    raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: Missing required field: {field}")
                
                # Validate zones field specifically
                if field == "zones":
                    if not isinstance(contact_person["zones"], list) or len(contact_person["zones"]) == 0:
                        raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: At least one zone is required")
                # Validate other fields are not empty
                elif not contact_person[field] or (isinstance(contact_person[field], str) and not contact_person[field].strip()):
                    raise HTTPException(status_code=400, detail=f"Contact Person {idx + 1}: {field} cannot be empty")
        
        # Validate principles suppliers
        principles_suppliers = payload.get("principlesSuppliers", [])
        if not isinstance(principles_suppliers, list) or len(principles_suppliers) == 0:
            raise HTTPException(status_code=400, detail="At least one supplier must be selected in Principles You Represent")
        
        # Validate your info
        your_info = payload.get("yourInfo", {})
        if not isinstance(your_info, dict):
            raise HTTPException(status_code=400, detail="yourInfo must be an object")
        
        your_info_fields = ["name", "email", "designation", "contactNo"]
        for field in your_info_fields:
            if field not in your_info or not your_info[field]:
                raise HTTPException(status_code=400, detail=f"Your Info: Missing required field: {field}")
        
        # Lookup ingredient IDs from branded ingredients collection by name
        ingredient_name = payload["ingredientName"]
        ingredient_id_provided = payload.get("ingredientId")  # Optional ingredient ID from frontend
        ingredient_ids = []
        
        # Clean ingredient name (remove trailing commas, extra spaces)
        ingredient_name_clean = ingredient_name.strip().rstrip(',').strip()
        
        print(f"🔍 Looking up ingredient IDs for: '{ingredient_name_clean}'")
        
        # CRITICAL: If ingredientId is provided from frontend, use it directly (most reliable)
        if ingredient_id_provided:
            try:
                ing_id_obj = ObjectId(ingredient_id_provided)
                # Verify the ID exists in the collection
                verify_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                if verify_doc:
                    ingredient_ids.append(str(ing_id_obj))
                    print(f"✅✅✅ Using provided ingredient ID: {ingredient_id_provided}")
                    print(f"   Verified: Ingredient '{verify_doc.get('ingredient_name', 'N/A')}' exists with this ID")
                else:
                    print(f"❌ WARNING: Provided ingredient ID {ingredient_id_provided} not found! Will lookup by name instead.")
                    ingredient_id_provided = None  # Fall back to name lookup
            except Exception as e:
                print(f"❌ WARNING: Invalid ingredient ID format {ingredient_id_provided}: {e}. Will lookup by name instead.")
                ingredient_id_provided = None  # Fall back to name lookup
        
        # If no valid ID provided, lookup by name
        if not ingredient_ids:
            print(f"🔍 No ingredient ID provided, looking up by name: '{ingredient_name_clean}'")
            
            # Strategy 1: Try exact match on ingredient_name field (case-insensitive)
            print(f"🔍 Strategy 1: Exact match search for '{ingredient_name_clean}'")
            count_found = 0
            async for branded_ingredient in branded_ingredients_col.find(
                {"ingredient_name": {"$regex": f"^{ingredient_name_clean}$", "$options": "i"}}
            ):
                count_found += 1
                ing_id_obj = branded_ingredient["_id"]
                ing_id_str = str(ing_id_obj)
                
                # CRITICAL: Verify the ID exists by querying it directly
                verify_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                if verify_doc:
                    if ing_id_str not in ingredient_ids:
                        ingredient_ids.append(ing_id_str)
                        print(f"✅ Found ingredient ID (exact match): {ing_id_str}")
                else:
                    print(f"❌ CRITICAL: ID {ing_id_str} verification FAILED - document not found!")
            
            if count_found == 0:
                print(f"   No exact matches found")
            
            # Strategy 2: If no exact match, try normalized match (remove special chars, normalize spaces)
            if len(ingredient_ids) == 0:
                normalized_search = re.sub(r'[^\w\s]', '', ingredient_name_clean).strip()
                normalized_search = re.sub(r'\s+', ' ', normalized_search)
                print(f"🔍 Trying normalized match: '{normalized_search}'")
                
                async for branded_ingredient in branded_ingredients_col.find(
                    {"ingredient_name": {"$regex": f"^{re.escape(normalized_search)}$", "$options": "i"}}
                ):
                    ing_id = str(branded_ingredient["_id"])
                    if ing_id not in ingredient_ids:
                        ingredient_ids.append(ing_id)
                        print(f"✅ Found ingredient ID (normalized): {ing_id} for '{branded_ingredient.get('ingredient_name', 'N/A')}'")
            
            # Strategy 3: Try partial match (contains) on ingredient_name
            if len(ingredient_ids) == 0:
                print(f"🔍 Trying partial match (contains)...")
                async for branded_ingredient in branded_ingredients_col.find(
                    {"ingredient_name": {"$regex": re.escape(ingredient_name_clean), "$options": "i"}}
                ):
                    ing_id = str(branded_ingredient["_id"])
                    if ing_id not in ingredient_ids:
                        ingredient_ids.append(ing_id)
                        print(f"✅ Found ingredient ID (partial): {ing_id} for '{branded_ingredient.get('ingredient_name', 'N/A')}'")
            
            # Strategy 4: Try matching against INCI names in the ingredient's inci_ids
            if len(ingredient_ids) == 0:
                print(f"🔍 Trying INCI name match...")
                # First, get the INCI document that matches the name
                inci_doc = await inci_col.find_one(
                    {"inciName": {"$regex": f"^{ingredient_name_clean}$", "$options": "i"}}
                )
                if inci_doc:
                    inci_id = inci_doc["_id"]
                    # Now find branded ingredients that have this INCI in their inci_ids
                    async for branded_ingredient in branded_ingredients_col.find(
                        {"inci_ids": inci_id}
                    ):
                        ing_id = str(branded_ingredient["_id"])
                        if ing_id not in ingredient_ids:
                            ingredient_ids.append(ing_id)
                            print(f"✅ Found ingredient ID (via INCI): {ing_id} for '{branded_ingredient.get('ingredient_name', 'N/A')}'")
        
        # Final verification: Check all found IDs actually exist in the collection
        verified_ids = []
        print(f"\n🔍 FINAL VERIFICATION: Testing {len(ingredient_ids)} ID(s)...")
        for ing_id_str in ingredient_ids:
            try:
                ing_id_obj = ObjectId(ing_id_str)
                verify_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                if verify_doc:
                    verify_doc2 = await branded_ingredients_col.find_one({"_id": ObjectId(ing_id_str)})
                    if verify_doc2:
                        verified_ids.append(ing_id_str)
                        print(f"   ✅✅✅ ID {ing_id_str} is VALID and VERIFIED")
            except Exception as e:
                print(f"   ❌ ERROR: Invalid ID format {ing_id_str}: {type(e).__name__}: {e}")
        
        print(f"\n📊 Verification Summary:")
        print(f"   Original IDs: {len(ingredient_ids)}")
        print(f"   Verified IDs: {len(verified_ids)}")
        print(f"   Verified ID List: {verified_ids}")
        
        ingredient_ids = verified_ids  # Use only verified IDs
        
        if len(ingredient_ids) == 0:
            print(f"❌ ERROR: No valid ingredient IDs found for '{ingredient_name_clean}'. Please check if the ingredient exists in the database.")
        else:
            print(f"✅ Successfully found and verified {len(ingredient_ids)} ingredient ID(s): {ingredient_ids}")
        
        # Validate and prepare contact persons data
        contact_persons_data = []
        for idx, cp in enumerate(contact_persons):
            contact_person_data = {
                "name": cp.get("name", "").strip(),
                "number": cp.get("number", "").strip(),
                "email": cp.get("email", "").strip(),
                "zones": cp.get("zones", []) if isinstance(cp.get("zones"), list) else []
            }
            # Ensure zones is a list of strings
            if contact_person_data["zones"]:
                contact_person_data["zones"] = [str(zone).strip() for zone in contact_person_data["zones"] if zone]
            contact_persons_data.append(contact_person_data)
            print(f"📝 Contact Person {idx + 1}: {contact_person_data['name']} - {contact_person_data['email']} - Zones: {contact_person_data['zones']}")
        
        # Store only ingredientIds (list) - names will be fetched from IDs when needed
        distributor_doc = {
            "firmName": payload["firmName"],
            "category": payload["category"],
            "registeredAddress": payload["registeredAddress"],
            "contactPersons": contact_persons_data,
            "ingredientIds": ingredient_ids,  # Store ONLY list of ingredient IDs (as strings)
            "principlesSuppliers": payload["principlesSuppliers"],
            "yourInfo": payload["yourInfo"],
            "acceptTerms": payload["acceptTerms"],
            "status": "under review",  # under review, approved, rejected
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        print(f"💾 Saving distributor document:")
        print(f"   - Firm: {payload['firmName']}")
        print(f"   - Ingredient Name: {ingredient_name_clean}")
        print(f"   - Ingredient IDs: {ingredient_ids}")
        print(f"   - Contact Persons: {len(contact_persons_data)}")
        
        # CRITICAL: Final verification before saving
        final_verified_ids = []
        if ingredient_ids:
            print(f"\n🔍 CRITICAL FINAL VERIFICATION: Testing {len(ingredient_ids)} ID(s) can be queried...")
            for ing_id_str in ingredient_ids:
                try:
                    ing_id_obj = ObjectId(ing_id_str)
                    test_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                    if test_doc:
                        if str(test_doc['_id']) == ing_id_str:
                            final_verified_ids.append(ing_id_str)
                        else:
                            final_verified_ids.append(str(test_doc['_id']))
                except Exception as e:
                    print(f"   ❌❌❌ CRITICAL ERROR with ID {ing_id_str}: {type(e).__name__}: {e}")
            
            ingredient_ids = final_verified_ids
            distributor_doc["ingredientIds"] = ingredient_ids
            
            if len(ingredient_ids) == 0:
                print(f"\n⚠️⚠️⚠️ WARNING: No valid ingredient IDs to save! Distributor will be saved with empty ingredientIds array.")
        
        # Insert into distributor collection
        result = await distributor_col.insert_one(distributor_doc)
        
        if result.inserted_id:
            return {
                "success": True,
                "message": "Distributor registration submitted successfully",
                "distributorId": str(result.inserted_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save distributor registration")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error registering distributor: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to register distributor: {str(e)}")


@router.get("/distributor/verify-ingredient-id/{ingredient_id}")
async def verify_ingredient_id(
    ingredient_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Debug endpoint to verify if an ingredient ID exists in the branded ingredients collection
    """
    try:
        print(f"🔍 Verifying ingredient ID: {ingredient_id}")
        
        # Try to find the ingredient
        try:
            ing_id_obj = ObjectId(ingredient_id)
        except Exception as e:
            return {
                "valid_format": False,
                "error": f"Invalid ObjectId format: {e}",
                "ingredient_id": ingredient_id
            }
        
        # Query the collection
        ingredient_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
        
        if ingredient_doc:
            return {
                "valid_format": True,
                "exists": True,
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_doc.get("ingredient_name", "N/A"),
                "document_id": str(ingredient_doc["_id"]),
                "document_id_type": str(type(ingredient_doc["_id"])),
                "match": str(ingredient_doc["_id"]) == ingredient_id
            }
        else:
            # Show sample documents to help debug
            sample_docs = await branded_ingredients_col.find({}).limit(3).to_list(length=3)
            sample_info = []
            for doc in sample_docs:
                sample_info.append({
                    "ingredient_name": doc.get("ingredient_name", "N/A"),
                    "_id": str(doc["_id"]),
                    "_id_type": str(type(doc["_id"]))
                })
            
            return {
                "valid_format": True,
                "exists": False,
                "ingredient_id": ingredient_id,
                "error": "Ingredient ID not found in branded_ingredients collection",
                "sample_documents": sample_info,
                "total_documents": await branded_ingredients_col.count_documents({})
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "ingredient_id": ingredient_id
        }


@router.get("/distributor/by-ingredient/{ingredient_name}")
async def get_distributor_by_ingredient(
    ingredient_name: str,
    ingredient_id: Optional[str] = Query(None),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get all distributor information for a specific ingredient
    
    Searches by ingredientIds array (primary) and ingredient name (backward compatibility).
    Returns list of all distributors for the ingredient, otherwise returns empty list
    
    Query params:
    - ingredient_name: Name of the ingredient (required, from path)
    - ingredient_id: ID of the ingredient (optional, from query string)
    """
    try:
        # Build query to search by ingredientIds array (primary) and name (backward compatibility)
        query_conditions = []
        ingredient_ids_to_search = []
        
        # If ingredient_id is provided, use it
        if ingredient_id:
            try:
                ObjectId(ingredient_id)
                ingredient_ids_to_search.append(ingredient_id)
            except:
                pass
        else:
            # If ingredient_id not provided, lookup IDs from ingredient name
            async for branded_ingredient in branded_ingredients_col.find(
                {"ingredient_name": {"$regex": f"^{ingredient_name}$", "$options": "i"}}
            ):
                ingredient_ids_to_search.append(str(branded_ingredient["_id"]))
        
        # Primary: Search by ingredientIds array using $in operator
        if ingredient_ids_to_search:
            ingredient_ids_as_objectids = []
            for ing_id_str in ingredient_ids_to_search:
                try:
                    ingredient_ids_as_objectids.append(ObjectId(ing_id_str))
                except:
                    print(f"⚠️ Invalid ObjectId format: {ing_id_str}")
            
            if ingredient_ids_as_objectids:
                query_conditions.append({
                    "$or": [
                        {"ingredientIds": {"$in": ingredient_ids_as_objectids}},  # ObjectId format
                        {"ingredientIds": {"$in": ingredient_ids_to_search}}  # String format
                    ]
                })
        
        # Backward compatibility: Also search by ingredient name (case-insensitive)
        query_conditions.append({"ingredientName": {"$regex": f"^{ingredient_name}$", "$options": "i"}})
        
        # Use $or to search by either ingredientIds or name
        query = {"$or": query_conditions} if len(query_conditions) > 1 else query_conditions[0]
        
        # Find all distributors matching the query
        distributors = await distributor_col.find(query).sort("createdAt", -1).to_list(length=None)
        
        # Convert ObjectId to string and fetch ingredientName from IDs for response
        for distributor in distributors:
            distributor["_id"] = str(distributor["_id"])
            
            # Always fetch ingredientName from ingredientIds (primary source)
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                ingredient_names = []
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                            except:
                                continue
                        else:
                            ing_id_obj = ing_id
                        
                        ing_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                        if ing_doc:
                            ingredient_names.append(ing_doc.get("ingredient_name", ""))
                    except Exception as e:
                        pass
                
                if ingredient_names:
                    distributor["ingredientName"] = ingredient_names[0] if len(ingredient_names) == 1 else ", ".join(ingredient_names)
                else:
                    distributor["ingredientName"] = distributor.get("ingredientName", ingredient_name)
            else:
                if "ingredientName" not in distributor:
                    distributor["ingredientName"] = ingredient_name
        
        return distributors if distributors else []
            
    except Exception as e:
        print(f"Error fetching distributors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch distributors: {str(e)}")


@router.post("/distributor/by-ingredients")
async def get_distributors_by_ingredients(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get distributor information for multiple ingredients in a single batch call
    
    Request body:
    {
        "ingredients": [
            {"name": "Ingredient1", "id": "optional_id1"},
            {"name": "Ingredient2", "id": "optional_id2"},
            ...
        ]
    }
    
    Returns:
    {
        "Ingredient1": [distributor1, distributor2, ...],
        "Ingredient2": [distributor3, ...],
        ...
    }
    """
    try:
        if "ingredients" not in payload or not isinstance(payload["ingredients"], list):
            raise HTTPException(status_code=400, detail="Request must contain 'ingredients' array")
        
        ingredients = payload["ingredients"]
        if not ingredients:
            return {}
        
        # Collect all ingredient IDs and names
        all_ingredient_ids = []
        all_ingredient_names = []
        ingredient_id_map = {}  # Maps ingredient_name -> list of IDs
        
        for ing in ingredients:
            if not isinstance(ing, dict) or "name" not in ing:
                continue
            
            ingredient_name = ing["name"]
            ingredient_id = ing.get("id")
            
            # If ID provided, use it
            if ingredient_id:
                try:
                    ObjectId(ingredient_id)  # Validate format
                    all_ingredient_ids.append(ingredient_id)
                    if ingredient_name not in ingredient_id_map:
                        ingredient_id_map[ingredient_name] = []
                    ingredient_id_map[ingredient_name].append(ingredient_id)
                except:
                    pass
            
            all_ingredient_names.append(ingredient_name)
        
        # If no IDs provided, lookup IDs from names
        if not all_ingredient_ids:
            for ing in ingredients:
                if not isinstance(ing, dict) or "name" not in ing:
                    continue
                ingredient_name = ing["name"]
                async for branded_ingredient in branded_ingredients_col.find(
                    {"ingredient_name": {"$regex": f"^{ingredient_name}$", "$options": "i"}}
                ):
                    ing_id_str = str(branded_ingredient["_id"])
                    all_ingredient_ids.append(ing_id_str)
                    if ingredient_name not in ingredient_id_map:
                        ingredient_id_map[ingredient_name] = []
                    ingredient_id_map[ingredient_name].append(ing_id_str)
        
        # Build query conditions
        query_conditions = []
        
        # Primary: Search by ingredientIds array using $in operator
        if all_ingredient_ids:
            ingredient_ids_as_objectids = []
            for ing_id_str in all_ingredient_ids:
                try:
                    ingredient_ids_as_objectids.append(ObjectId(ing_id_str))
                except:
                    pass
            
            if ingredient_ids_as_objectids:
                query_conditions.append({
                    "$or": [
                        {"ingredientIds": {"$in": ingredient_ids_as_objectids}},  # ObjectId format
                        {"ingredientIds": {"$in": all_ingredient_ids}}  # String format
                    ]
                })
        
        # Backward compatibility: Also search by ingredient names (case-insensitive)
        if all_ingredient_names:
            name_regex_conditions = [
                {"ingredientName": {"$regex": f"^{name}$", "$options": "i"}}
                for name in all_ingredient_names
            ]
            if name_regex_conditions:
                query_conditions.append({"$or": name_regex_conditions})
        
        # Build final query
        if not query_conditions:
            return {}
        
        query = {"$or": query_conditions} if len(query_conditions) > 1 else query_conditions[0]
        
        # Single database query for all distributors
        all_distributors = await distributor_col.find(query).sort("createdAt", -1).to_list(length=None)
        
        # Process distributors: convert ObjectId to string and fetch ingredient names
        processed_distributors = []
        for distributor in all_distributors:
            distributor["_id"] = str(distributor["_id"])
            
            # Fetch ingredientName from ingredientIds
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                ingredient_names = []
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                            except:
                                continue
                        else:
                            ing_id_obj = ing_id
                        
                        ing_doc = await branded_ingredients_col.find_one({"_id": ing_id_obj})
                        if ing_doc:
                            ingredient_names.append(ing_doc.get("ingredient_name", ""))
                    except Exception as e:
                        pass
                
                if ingredient_names:
                    distributor["ingredientName"] = ingredient_names[0] if len(ingredient_names) == 1 else ", ".join(ingredient_names)
                else:
                    distributor["ingredientName"] = distributor.get("ingredientName", "")
            else:
                distributor["ingredientName"] = distributor.get("ingredientName", "")
            
            processed_distributors.append(distributor)
        
        # Group distributors by ingredient name
        result_map = {}
        
        # Initialize result map with empty arrays for all requested ingredients
        for ing in ingredients:
            if isinstance(ing, dict) and "name" in ing:
                result_map[ing["name"]] = []
        
        # Group distributors by matching ingredient
        for distributor in processed_distributors:
            distributor_ingredient_name = distributor.get("ingredientName", "")
            
            # Try to match distributor to requested ingredients
            matched = False
            for ing in ingredients:
                if not isinstance(ing, dict) or "name" not in ing:
                    continue
                
                ingredient_name = ing["name"]
                normalized_name = ingredient_name.strip().lower()
                distributor_normalized = distributor_ingredient_name.strip().lower()
                
                # Check if distributor matches this ingredient
                if (normalized_name == distributor_normalized or 
                    (ingredient_name in ingredient_id_map and 
                     distributor.get("ingredientIds") and
                     any(str(ing_id) in [str(x) for x in distributor.get("ingredientIds", [])] 
                         for ing_id in ingredient_id_map[ingredient_name]))):
                    if ingredient_name not in result_map:
                        result_map[ingredient_name] = []
                    result_map[ingredient_name].append(distributor)
                    matched = True
                    break
            
            # If no match found but distributor has ingredientName, try fuzzy match
            if not matched and distributor_ingredient_name:
                for ing in ingredients:
                    if not isinstance(ing, dict) or "name" not in ing:
                        continue
                    ingredient_name = ing["name"]
                    if ingredient_name.strip().lower() == distributor_ingredient_name.strip().lower():
                        if ingredient_name not in result_map:
                            result_map[ingredient_name] = []
                        result_map[ingredient_name].append(distributor)
                        break
        
        return result_map
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching distributors in batch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch distributors: {str(e)}")

