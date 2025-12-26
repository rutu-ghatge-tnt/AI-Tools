# app/logic/matcher.py
import re
from typing import List, Tuple, Dict, Set, Optional
from bson import ObjectId  # type: ignore

from app.ai_ingredient_intelligence.db.mongodb import db

# Try to import rapidfuzz for fuzzy matching
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    print("Warning: rapidfuzz not available for fuzzy matching. Install with: pip install rapidfuzz")


def normalize_ingredient_name(name: str) -> str:
    """Normalize ingredient name for matching"""
    if not name:
        return ""
    import unicodedata
    normalized = unicodedata.normalize("NFKD", name)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


async def build_category_tree(collection, category_ids, name_field):
    """
    Given a collection and list of category ObjectIds, build a list of name paths.
    Example: [["Colorants", "Organic Colorants", "Natural Organic Colorants"]]
    """
    results = []
    for cid in category_ids:
        if not isinstance(cid, ObjectId):
            try:
                cid = ObjectId(cid)
            except:
                continue

        path = []
        current = await collection.find_one({"_id": cid})
        while current:
            path.insert(0, current.get(name_field))
            parent_id = current.get("parent_id")
            if parent_id:
                current = await collection.find_one({"_id": parent_id})
            else:
                current = None
        results.append(path)
    return results


async def build_category_trees_batch(collection, all_category_ids, name_field):
    """
    OPTIMIZED: Batch version that builds category trees for multiple category ID lists.
    Collects all unique category IDs first, then builds trees in one pass.
    
    Args:
        collection: MongoDB collection
        all_category_ids: List of lists of category IDs (e.g., [[id1, id2], [id3, id4]])
        name_field: Field name to extract from documents
    
    Returns:
        List of category tree results (same structure as build_category_tree)
    """
    if not all_category_ids:
        return []
    
    # Collect all unique category IDs
    all_unique_ids = set()
    for category_id_list in all_category_ids:
        for cid in category_id_list:
            if not isinstance(cid, ObjectId):
                try:
                    cid = ObjectId(cid)
                except:
                    continue
            all_unique_ids.add(cid)
    
    if not all_unique_ids:
        return []
    
    # Batch fetch all category documents
    category_docs = await collection.find({"_id": {"$in": list(all_unique_ids)}}).to_list(length=None)
    category_map = {doc["_id"]: doc for doc in category_docs}
    
    # Build all trees using the pre-fetched map
    all_results = []
    for category_id_list in all_category_ids:
        tree_results = []
        for cid in category_id_list:
            if not isinstance(cid, ObjectId):
                try:
                    cid = ObjectId(cid)
                except:
                    continue
            
            path = []
            visited = set()  # Prevent infinite loops
            current_id = cid
            
            while current_id and current_id not in visited:
                visited.add(current_id)
                current = category_map.get(current_id)
                if not current:
                    break
                
                path.insert(0, current.get(name_field))
                parent_id = current.get("parent_id")
                if parent_id:
                    if not isinstance(parent_id, ObjectId):
                        try:
                            parent_id = ObjectId(parent_id)
                        except:
                            break
                    current_id = parent_id
                else:
                    current_id = None
            
            if path:
                tree_results.append(path)
        
        all_results.append(tree_results)
    
    return all_results


async def match_inci_names(
    inci_names: List[str], 
    synonyms_map: Optional[Dict[str, List[str]]] = None
) -> Tuple[List[dict], List[str], Dict[str, str], List[str]]:
    """
    Matches given INCI names following the new flow:
    1. Direct MongoDB query for exact branded matches (original logic)
    2. Fuzzy/NLP matching for branded ingredients (spelling mistakes)
    3. CAS API synonyms lookup for unmatched → check if synonyms match branded
    4. Check general INCI collection
    5. Remaining unmatched → "Unable to Decode"
    
    Returns:
    - matched_results: List of matched ingredients (branded or general)
    - general_ingredients: List of general INCI ingredients (tagged as 'G')
    - ingredient_tags: Dict mapping ingredient name to tag ('B' for branded, 'G' for general)
    - unable_to_decode: List of ingredients that couldn't be found even after all steps
    """
    branded_ingredients_col = db["ingre_branded_ingredients"]
    inci_col = db["ingre_inci"]
    func_cat_col = db["ingre_functional_categories"]
    chem_class_col = db["ingre_chemical_classes"]

    # Normalize product INCI list (keep original for reference)
    product_inci_original = {name: name.strip().lower() for name in inci_names}
    product_inci_set = set(product_inci_original.values())
    
    # Identify INCI combinations (ingredients with "(and)", "&", or "and" when other separators exist)
    # These should be searched as combinations in MongoDB
    from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
    import re
    
    # Parse to identify combinations
    parsed_ingredients = parse_inci_string(inci_names)
    
    # Separate combinations from single ingredients
    combinations = []  # List of tuples: (original_combination_string, list_of_inci_names_in_combination)
    single_ingredients = []  # Regular single ingredients
    
    for ingredient in parsed_ingredients:
        # Check if this is a combination (contains "(and)", "&", or multiple "and" when other separators exist)
        normalized_ing = ingredient.lower()
        has_and_paren = bool(re.search(r'\(and\)', normalized_ing, re.IGNORECASE))
        has_ampersand = '&' in normalized_ing
        has_multiple_and = len(re.findall(r'\s+and\s+', normalized_ing, re.IGNORECASE)) > 0
        
        # Check if there are other separators in the original input
        original_has_separators = any(sep in ', '.join(inci_names) for sep in [',', ';', '|', '\n'])
        
        if (has_and_paren or has_ampersand or (has_multiple_and and original_has_separators)):
            # This is a combination - extract individual INCI names
            # Split by "(and)", "&", or "and" while preserving the ingredient names
            combo_text = ingredient  # Keep original case for better matching
            
            # Split by combination separators
            if has_and_paren:
                # Split by "(and)" or "(And)" etc.
                combo_parts = re.split(r'\s*\(and\)\s*', combo_text, flags=re.IGNORECASE)
            elif has_ampersand:
                # Split by "&"
                combo_parts = re.split(r'\s+&\s+', combo_text)
            else:
                # Split by "and"
                combo_parts = re.split(r'\s+and\s+', combo_text, flags=re.IGNORECASE)
            
            # Clean and filter parts
            combo_inci_list = [part.strip() for part in combo_parts if part.strip() and len(part.strip()) > 2]
            
            if len(combo_inci_list) > 1:
                combinations.append((ingredient, combo_inci_list))
                print(f"[INFO] Detected INCI combination: '{ingredient}' -> {combo_inci_list}")
            else:
                single_ingredients.append(ingredient)
        else:
            single_ingredients.append(ingredient)
    
    matched_results = []
    ingredient_tags = {}  # Maps ingredient name to 'B' (branded) or 'G' (general)
    matched_inci_all: Set[str] = set()  # All INCI names that have been matched
    matched_original_names: Set[str] = set()  # Original ingredient names that have been matched
    matched_combinations: Set[str] = set()  # Track which combinations have been matched

    # ============================================
    # STEP 0: Search for INCI combinations in branded ingredients
    # ============================================
    # Build pipeline for combination matching (same as Step 1)
    pipeline_combos = [
        {
            "$lookup": {
                "from": "ingre_inci",
                "localField": "inci_ids",
                "foreignField": "_id",
                "as": "inci_docs"
            }
        },
        {
            "$lookup": {
                "from": "ingre_suppliers",
                "localField": "supplier_id",
                "foreignField": "_id",
                "as": "supplier_docs"
            }
        },
        {
            "$project": {
                "_id": 1,
                "ingredient_name": 1,
                "supplier_name": {"$arrayElemAt": ["$supplier_docs.supplierName", 0]},
                "description": 1,
                "enhanced_description": 1,  # Prefer enhanced_description for branded ingredients
                "category_decided": 1,  # Include category_decided field
                "functional_category_ids": 1,
                "chemical_class_ids": 1,
                "inci_list": "$inci_docs.inciName_normalized"
            }
        }
    ]
    
    if combinations:
        print(f"[INFO] Step 0: Searching for {len(combinations)} INCI combination(s) in branded ingredients...")
        
        for combo_string, combo_inci_list in combinations:
            if combo_string.lower() in matched_combinations:
                continue
            
            # Normalize combo INCI list
            combo_inci_set = {inci.strip().lower() for inci in combo_inci_list}
            
            # Search for branded ingredients where ALL INCI in the combination are present
            async for doc in branded_ingredients_col.aggregate(pipeline_combos):
                brand_inci_list = [i.strip().lower() for i in doc.get("inci_list", [])]
                brand_inci_set = set(brand_inci_list)
                
                # Check if this branded ingredient's INCI list contains ALL INCI from the combination
                if combo_inci_set.issubset(brand_inci_set) and len(combo_inci_set) > 0:
                    # Also check that the combination matches a significant portion (at least 2 INCI or 50% match)
                    match_ratio = len(combo_inci_set) / len(brand_inci_set) if brand_inci_set else 0
                    if len(combo_inci_set) >= 2 or match_ratio >= 0.5:
                        func_tree = await build_category_tree(
                            func_cat_col,
                            doc.get("functional_category_ids", []),
                            "functionalName"
                        )
                        chem_tree = await build_category_tree(
                            chem_class_col,
                            doc.get("chemical_class_ids", []),
                            "chemicalClassName"
                        )
                        
                        # Use enhanced_description if available, otherwise fallback to description
                        description = doc.get("enhanced_description") or doc.get("description")
                        
                        matched_results.append({
                            "ingredient_name": doc["ingredient_name"],
                            "ingredient_id": str(doc["_id"]),
                            "supplier_name": doc.get("supplier_name"),
                            "description": description,  # Use enhanced_description if available
                            "rephrased_description": doc.get("enhanced_description"),  # Keep for backward compatibility
                            "category_decided": doc.get("category_decided"),  # Include category_decided from MongoDB
                            "functionality_category_tree": func_tree,
                            "chemical_class_category_tree": chem_tree,
                            "match_score": 1.0,
                            "matched_inci": list(combo_inci_set),  # The INCI that matched from the combination
                            "matched_count": len(combo_inci_set),
                            "total_brand_inci": len(brand_inci_set),
                            "tag": "B",  # Branded
                            "match_method": "combination"
                        })
                        
                        # Mark combination as matched
                        matched_combinations.add(combo_string.lower())
                        matched_original_names.add(combo_string)
                        
                        # Mark all matched INCI as branded
                        for inci in combo_inci_set:
                            matched_inci_all.add(inci)
                            ingredient_tags[inci] = "B"
                        
                        print(f"[OK] Matched combination '{combo_string}' to branded ingredient '{doc['ingredient_name']}'")
                        break  # Found a match for this combination, move to next
    
    # ============================================
    # STEP 1: Direct MongoDB query for exact branded matches (original logic)
    # ============================================
    print("[INFO] Step 1: Direct MongoDB query for exact branded matches...")
    
    pipeline = [
        {
            "$lookup": {
                "from": "ingre_inci",
                "localField": "inci_ids",
                "foreignField": "_id",
                "as": "inci_docs"
            }
        },
        {
            "$lookup": {
                "from": "ingre_suppliers",
                "localField": "supplier_id",
                "foreignField": "_id",
                "as": "supplier_docs"
            }
        },
        {
            "$project": {
                "_id": 1,
                "ingredient_name": 1,
                "supplier_name": {"$arrayElemAt": ["$supplier_docs.supplierName", 0]},
                "description": 1,
                "enhanced_description": 1,  # Prefer enhanced_description for branded ingredients
                "category_decided": 1,  # Include category_decided field
                "functional_category_ids": 1,
                "chemical_class_ids": 1,
                "inci_list": "$inci_docs.inciName_normalized"
            }
        }
    ]

    async for doc in branded_ingredients_col.aggregate(pipeline):
        brand_inci_list = [i.strip().lower() for i in doc.get("inci_list", [])]
        brand_inci_set = set(brand_inci_list)
        total_brand_inci = len(brand_inci_set)

        if brand_inci_set.issubset(product_inci_set) and total_brand_inci > 0:
            func_tree = await build_category_tree(
                func_cat_col,
                doc.get("functional_category_ids", []),
                "functionalName"
            )
            chem_tree = await build_category_tree(
                chem_class_col,
                doc.get("chemical_class_ids", []),
                "chemicalClassName"
            )

            # Use enhanced_description if available, otherwise fallback to description
            description = doc.get("enhanced_description") or doc.get("description")
            
            matched_results.append({
                "ingredient_name": doc["ingredient_name"],
                "ingredient_id": str(doc["_id"]),  # Add ingredient ID for distributor mapping
                "supplier_name": doc.get("supplier_name"),
                "description": description,  # Use enhanced_description if available
                "rephrased_description": doc.get("enhanced_description"),  # Keep for backward compatibility
                "category_decided": doc.get("category_decided"),  # Include category_decided from MongoDB
                "functionality_category_tree": func_tree,
                "chemical_class_category_tree": chem_tree,
                "match_score": 1.0,
                "matched_inci": list(brand_inci_set),
                "matched_count": total_brand_inci,
                "total_brand_inci": total_brand_inci,
                "tag": "B",  # Branded
                "match_method": "exact"
            })
            
            # Mark all matched INCI as branded
            for inci in brand_inci_set:
                matched_inci_all.add(inci)
                ingredient_tags[inci] = "B"
                # Find original name that matched
                for orig_name, norm_name in product_inci_original.items():
                    if norm_name == inci:
                        matched_original_names.add(orig_name)

    # ============================================
    # STEP 2: Fuzzy/NLP matching for branded ingredients (spelling mistakes)
    # ============================================
    print("[INFO] Step 2: Fuzzy matching for branded ingredients...")
    
    # For matching, use single ingredients and unmatched combinations
    remaining_original = [name for name in inci_names if name not in matched_original_names]
    # Also check parsed ingredients for unmatched combinations
    for ingredient in parsed_ingredients:
        if ingredient not in matched_original_names and ingredient.lower() not in matched_combinations:
            if ingredient not in remaining_original:
                remaining_original.append(ingredient)
    
    remaining_normalized = {normalize_ingredient_name(name) for name in remaining_original}
    remaining_normalized = remaining_normalized - matched_inci_all
    
    if remaining_normalized and RAPIDFUZZ_AVAILABLE:
        # Get all branded ingredient INCI names for fuzzy matching
        all_branded_inci = []
        async for doc in branded_ingredients_col.aggregate(pipeline):
            brand_inci_list = [i.strip().lower() for i in doc.get("inci_list", [])]
            for inci in brand_inci_list:
                if inci not in matched_inci_all:
                    all_branded_inci.append((inci, doc))
        
        # Fuzzy match remaining ingredients against branded INCI
        for ingredient_norm in remaining_normalized:
            if ingredient_norm in matched_inci_all:
                continue
                
            # Find best fuzzy match
            candidates = [inci for inci, _ in all_branded_inci]
            if candidates:
                best_match = process.extractOne(
                    ingredient_norm,
                    candidates,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=75  # 75% similarity threshold
                )
                
                if best_match:
                    matched_inci, score, _ = best_match
                    confidence = score / 100.0
                    
                    # Find the branded ingredient document for this matched INCI
                    for matched_inci_candidate, doc in all_branded_inci:
                        if matched_inci_candidate == matched_inci:
                            # Check if this doc is already in results
                            doc_inci_set = {i.strip().lower() for i in doc.get("inci_list", [])}
                            if matched_inci in doc_inci_set:
                                func_tree = await build_category_tree(
                                    func_cat_col,
                                    doc.get("functional_category_ids", []),
                                    "functionalName"
                                )
                                chem_tree = await build_category_tree(
                                    chem_class_col,
                                    doc.get("chemical_class_ids", []),
                                    "chemicalClassName"
                                )
                                
                                # Use enhanced_description if available, otherwise fallback to description
                                description = doc.get("enhanced_description") or doc.get("description")
                                
                                matched_results.append({
                                    "ingredient_name": doc["ingredient_name"],
                                    "ingredient_id": str(doc["_id"]),  # Add ingredient ID for distributor mapping
                                    "supplier_name": doc.get("supplier_name"),
                                    "description": description,  # Use enhanced_description if available
                                    "rephrased_description": doc.get("enhanced_description"),  # Keep for backward compatibility
                                    "category_decided": doc.get("category_decided"),  # Include category_decided from MongoDB
                                    "functionality_category_tree": func_tree,
                                    "chemical_class_category_tree": chem_tree,
                                    "match_score": confidence,
                                    "matched_inci": [matched_inci],
                                    "matched_count": 1,
                                    "total_brand_inci": len(doc_inci_set),
                                    "tag": "B",
                                    "match_method": "fuzzy"
                                })
                                
                                matched_inci_all.add(matched_inci)
                                ingredient_tags[matched_inci] = "B"
                                # Find original name
                                for orig_name, norm_name in product_inci_original.items():
                                    if normalize_ingredient_name(orig_name) == ingredient_norm:
                                        matched_original_names.add(orig_name)
                                break

    # ============================================
    # STEP 3: CAS API synonyms lookup for unmatched → check if synonyms match branded
    # ============================================
    print("[INFO] Step 3: Checking CAS API synonyms for unmatched ingredients...")
    
    remaining_after_fuzzy = [name for name in inci_names if name not in matched_original_names]
    
    if remaining_after_fuzzy and synonyms_map:
        # Check if any synonyms match branded ingredients
        for ingredient in remaining_after_fuzzy:
            if ingredient in matched_original_names:
                continue
                
            synonyms = synonyms_map.get(ingredient, [])
            if not synonyms:
                continue
            
            # Normalize synonyms
            normalized_synonyms = {normalize_ingredient_name(s) for s in synonyms}
            
            # Check if any synonym matches a branded ingredient
            async for doc in branded_ingredients_col.aggregate(pipeline):
                brand_inci_list = [i.strip().lower() for i in doc.get("inci_list", [])]
                brand_inci_set = set(brand_inci_list)
                
                # Check if any synonym matches this branded ingredient
                if normalized_synonyms.intersection(brand_inci_set):
                    matched_synonyms = normalized_synonyms.intersection(brand_inci_set)
                    
                    func_tree = await build_category_tree(
                        func_cat_col,
                        doc.get("functional_category_ids", []),
                        "functionalName"
                    )
                    chem_tree = await build_category_tree(
                        chem_class_col,
                        doc.get("chemical_class_ids", []),
                        "chemicalClassName"
                    )
                    
                    # Use enhanced_description if available, otherwise fallback to description
                    description = doc.get("enhanced_description") or doc.get("description")
                    
                    matched_results.append({
                        "ingredient_name": doc["ingredient_name"],
                        "ingredient_id": str(doc["_id"]),  # Add ingredient ID for distributor mapping
                        "supplier_name": doc.get("supplier_name"),
                        "description": description,  # Use enhanced_description if available
                        "rephrased_description": doc.get("enhanced_description"),  # Keep for backward compatibility
                        "category_decided": doc.get("category_decided"),  # Include category_decided from MongoDB
                        "functionality_category_tree": func_tree,
                        "chemical_class_category_tree": chem_tree,
                        "match_score": 0.9,  # Slightly lower score for synonym match
                        "matched_inci": list(matched_synonyms),
                        "matched_count": len(matched_synonyms),
                        "total_brand_inci": len(brand_inci_set),
                        "tag": "B",
                        "match_method": "synonym"
                    })
                    
                    for syn in matched_synonyms:
                        matched_inci_all.add(syn)
                        ingredient_tags[syn] = "B"
                    
                    matched_original_names.add(ingredient)
                    break

    # ============================================
    # STEP 4: Check general INCI collection for remaining
    # ============================================
    print("[INFO] Step 4: Checking general INCI collection...")
    
    remaining_for_general = product_inci_set - matched_inci_all
    
    general_ingredients = []
    if remaining_for_general:
        # Query INCI collection for these names
        inci_docs = await inci_col.find({
            "inciName_normalized": {"$in": list(remaining_for_general)}
        }).to_list(length=None)
        
        for inci_doc in inci_docs:
            inci_name_normalized = inci_doc.get("inciName_normalized", "").lower()
            inci_name_original = inci_doc.get("inciName", "")
            
            if inci_name_normalized in remaining_for_general:
                # This is a general INCI (not branded)
                matched_results.append({
                    "ingredient_name": inci_name_original,
                    "ingredient_id": None,  # General INCI ingredients don't have ingredient_id
                    "supplier_name": None,
                    "description": None,
                    "functionality_category_tree": [],
                    "chemical_class_category_tree": [],
                    "match_score": 1.0,
                    "matched_inci": [inci_name_normalized],
                    "matched_count": 1,
                    "total_brand_inci": 1,
                    "tag": "G",  # General
                    "match_method": "exact"
                })
                
                general_ingredients.append(inci_name_original)
                matched_inci_all.add(inci_name_normalized)
                ingredient_tags[inci_name_normalized] = "G"
                
                # Find original name
                for orig_name, norm_name in product_inci_original.items():
                    if norm_name == inci_name_normalized:
                        matched_original_names.add(orig_name)

    # ============================================
    # STEP 5: Remaining unmatched → "Unable to Decode"
    # ============================================
    print("[INFO] Step 5: Identifying unable to decode ingredients...")
    
    unable_to_decode = []
    for orig_name in inci_names:
        if orig_name not in matched_original_names:
            unable_to_decode.append(orig_name)
    
    # Sort matches: Branded first (by match method: exact > fuzzy > synonym), then General
    matched_results.sort(key=lambda x: (
        x.get("tag", "G") == "G",  # Branded first
        {"exact": 0, "fuzzy": 1, "synonym": 2}.get(x.get("match_method", "exact"), 3),
        -x.get("match_score", 0)
    ))

    return matched_results, general_ingredients, ingredient_tags, unable_to_decode
