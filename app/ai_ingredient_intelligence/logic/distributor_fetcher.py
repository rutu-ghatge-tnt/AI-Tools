"""
Distributor Fetcher Logic
==========================

Business logic for fetching distributor information for branded ingredients.
Extracted from analyze_inci.py for better modularity.
"""

from typing import List, Dict
from bson import ObjectId
from app.ai_ingredient_intelligence.models.schemas import AnalyzeInciItem
from app.ai_ingredient_intelligence.db.collections import distributor_col, branded_ingredients_col
from app.ai_ingredient_intelligence.db.mongodb import db


async def fetch_distributors_for_branded_ingredients(items: List[AnalyzeInciItem]) -> Dict[str, List[Dict]]:
    """
    Fetch distributor information for all branded ingredients in a single batch call.
    
    Args:
        items: List of AnalyzeInciItem objects (only branded ingredients with ingredient_id will be processed)
    
    Returns:
        Dict mapping ingredient_name to list of distributors: { 'ingredient_name': [distributor1, distributor2, ...] }
    """
    # Collect all branded ingredients with IDs
    branded_ingredients = []
    for item in items:
        if item.tag == 'B' and item.ingredient_id:
            branded_ingredients.append({
                "name": item.ingredient_name,
                "id": item.ingredient_id
            })
    
    if not branded_ingredients:
        return {}
    
    try:
        # Collect all ingredient IDs and names
        all_ingredient_ids = []
        ingredient_id_map = {}  # Maps ingredient_name -> list of IDs
        
        for ing in branded_ingredients:
            ingredient_name = ing["name"]
            ingredient_id = ing.get("id")
            
            if ingredient_id:
                try:
                    ObjectId(ingredient_id)  # Validate format
                    all_ingredient_ids.append(ingredient_id)
                    if ingredient_name not in ingredient_id_map:
                        ingredient_id_map[ingredient_name] = []
                    ingredient_id_map[ingredient_name].append(ingredient_id)
                except:
                    pass
        
        if not all_ingredient_ids:
            return {}
        
        # Build query conditions
        query_conditions = []
        
        # Primary: Search by ingredientIds array using $in operator
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
        all_ingredient_names = [ing["name"] for ing in branded_ingredients]
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
        
        # OPTIMIZED: Batch fetch all ingredient names in one query instead of individual find_one calls
        # Collect all unique ingredient IDs from all distributors
        all_ingredient_ids_to_fetch = set()
        for distributor in all_distributors:
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                                all_ingredient_ids_to_fetch.add(ing_id_obj)
                            except:
                                continue
                        else:
                            all_ingredient_ids_to_fetch.add(ing_id)
                    except:
                        pass
        
        # Batch fetch all ingredient documents in one query (including supplier info)
        ingredient_id_to_name_map = {}
        ingredient_id_to_supplier_map = {}  # Maps ingredient_id -> supplier_name
        suppliers_col = db["ingre_suppliers"]
        
        if all_ingredient_ids_to_fetch:
            ingredient_docs = await branded_ingredients_col.find(
                {"_id": {"$in": list(all_ingredient_ids_to_fetch)}}
            ).to_list(length=None)
            
            # Collect supplier IDs
            supplier_ids = set()
            for ing_doc in ingredient_docs:
                ing_id = ing_doc["_id"]
                ingredient_id_to_name_map[ing_id] = ing_doc.get("ingredient_name", "")
                supplier_id = ing_doc.get("supplier_id")
                if supplier_id:
                    try:
                        if isinstance(supplier_id, str):
                            supplier_id = ObjectId(supplier_id)
                        supplier_ids.add(supplier_id)
                        ingredient_id_to_supplier_map[ing_id] = supplier_id
                    except:
                        pass
            
            # Batch fetch supplier names - fetch ALL suppliers (old behavior, no isValid filter)
            if supplier_ids:
                supplier_docs = await suppliers_col.find(
                    {"_id": {"$in": list(supplier_ids)}},
                    {"supplierName": 1}
                ).to_list(length=None)
                supplier_id_to_name = {doc["_id"]: doc.get("supplierName", "") for doc in supplier_docs}
                
                # Update ingredient_id_to_supplier_map with supplier names
                for ing_id, supplier_id in ingredient_id_to_supplier_map.items():
                    supplier_name = supplier_id_to_name.get(supplier_id, "")
                    ingredient_id_to_supplier_map[ing_id] = supplier_name
        
        # Process distributors: convert ObjectId to string and fetch ingredient names and supplier info from map
        processed_distributors = []
        for distributor in all_distributors:
            distributor["_id"] = str(distributor["_id"])
            
            # Fetch ingredientName and supplierName from ingredientIds using the pre-fetched maps
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                ingredient_names = []
                supplier_names = []
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                            except:
                                continue
                        else:
                            ing_id_obj = ing_id
                        
                        # Use pre-fetched maps instead of individual queries
                        ingredient_name = ingredient_id_to_name_map.get(ing_id_obj)
                        if ingredient_name:
                            ingredient_names.append(ingredient_name)
                        
                        supplier_name = ingredient_id_to_supplier_map.get(ing_id_obj)
                        if supplier_name:  # Only add non-None, non-empty supplier names
                            supplier_names.append(supplier_name)
                    except Exception as e:
                        pass
                
                if ingredient_names:
                    distributor["ingredientName"] = ingredient_names[0] if len(ingredient_names) == 1 else ", ".join(ingredient_names)
                else:
                    distributor["ingredientName"] = distributor.get("ingredientName", "")
                
                # Add supplier name(s) - use first if single, or join if multiple
                if supplier_names:
                    unique_suppliers = list(set(supplier_names))  # Remove duplicates
                    distributor["supplierName"] = unique_suppliers[0] if len(unique_suppliers) == 1 else ", ".join(unique_suppliers)
                else:
                    # Don't set supplierName if not found - keep existing value or None
                    if "supplierName" not in distributor:
                        distributor["supplierName"] = None
            else:
                distributor["ingredientName"] = distributor.get("ingredientName", "")
                # Don't set supplierName if not found - keep existing value or None
                if "supplierName" not in distributor:
                    distributor["supplierName"] = None
            
            processed_distributors.append(distributor)
        
        # Group distributors by ingredient name
        result_map = {}
        
        # Initialize result map with empty arrays for all requested ingredients
        for ing in branded_ingredients:
            result_map[ing["name"]] = []
        
        # Group distributors by matching ingredient
        for distributor in processed_distributors:
            distributor_ingredient_name = distributor.get("ingredientName", "")
            
            # Try to match distributor to requested ingredients
            matched = False
            for ing in branded_ingredients:
                ingredient_name = ing["name"]
                normalized_name = ingredient_name.strip().lower()
                distributor_normalized = distributor_ingredient_name.strip().lower()
                
                # Check if distributor matches this ingredient
                # Match by exact name or if distributor's ingredientIds contains this ingredient's ID
                if (normalized_name == distributor_normalized or 
                    (ingredient_name in ingredient_id_map and 
                     distributor.get("ingredientIds") and
                     any(str(ing_id) in [str(x) for x in distributor.get("ingredientIds", [])] 
                         for ing_id in ingredient_id_map[ingredient_name]))):
                    result_map[ingredient_name].append(distributor)
                    matched = True
                    break
            
            # If no match found but distributor has ingredientName, try fuzzy match
            if not matched and distributor_ingredient_name:
                for ing in branded_ingredients:
                    ingredient_name = ing["name"]
                    if ingredient_name.strip().lower() == distributor_ingredient_name.strip().lower():
                        result_map[ingredient_name].append(distributor)
                        break
        
        return result_map
            
    except Exception as e:
        print(f"Error fetching distributors for branded ingredients: {e}")
        # Return empty dict on error - don't fail the whole analysis
        return {}

