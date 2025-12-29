"""
Category Computer Logic
========================

Business logic for computing ingredient categories (Active/Excipient).
Extracted from analyze_inci.py for better modularity.
"""

from typing import List, Dict, Tuple, Optional
from app.ai_ingredient_intelligence.models.schemas import AnalyzeInciItem
from app.ai_ingredient_intelligence.db.collections import inci_col


async def compute_item_category(matched_inci: List[str], inci_categories: Dict[str, str]) -> Optional[str]:
    """
    Compute category for an item (handles both single and combination INCI)
    
    Logic:
    - If ANY INCI in the combination is "Active" → whole combination is "Active"
    - If ALL are "Excipient" (and no Active found) → combination is "Excipient"
    - If no categories found → None
    
    Args:
        matched_inci: List of INCI names (can be single or multiple for combinations)
        inci_categories: Dict mapping normalized INCI name to category ("Active" or "Excipient")
    
    Returns:
        "Active", "Excipient", or None
    """
    if not matched_inci:
        return None
    
    has_active = False
    has_excipient = False
    
    for inci in matched_inci:
        normalized = inci.strip().lower()
        category = inci_categories.get(normalized)
        
        if category:
            if category.upper() == "ACTIVE":
                has_active = True
            elif category.upper() == "EXCIPIENT":
                has_excipient = True
    
    # If ANY is active, whole combination is active
    if has_active:
        return "Active"
    elif has_excipient:
        # Only excipient if all are excipients (no active found)
        return "Excipient"
    
    return None


async def fetch_and_compute_categories(items: List[AnalyzeInciItem]) -> Tuple[Dict[str, str], List[AnalyzeInciItem]]:
    """
    Fetch categories for all INCI names and compute item-level categories
    
    Args:
        items: List of AnalyzeInciItem objects
    
    Returns:
        Tuple of:
        - inci_categories: Dict mapping normalized INCI name to category
        - items_processed: Items processed (category_decided for branded, category computed only for general INCI)
    """
    # Collect all unique INCI names from all items
    all_inci_names = set()
    for item in items:
        for inci in item.matched_inci:
            all_inci_names.add(inci.strip().lower())
    
    # Fetch categories from database
    inci_categories = {}
    if all_inci_names:
        normalized_names = list(all_inci_names)
        cursor = inci_col.find(
            {"inciName_normalized": {"$in": normalized_names}},
            {"inciName_normalized": 1, "category": 1}
        )
        results = await cursor.to_list(length=None)
        
        for doc in results:
            normalized = doc.get("inciName_normalized", "").strip().lower()
            category = doc.get("category")
            if normalized and category:
                inci_categories[normalized] = category
    
    # Process items: Compute category for bifurcation (actives/excipients tabs)
    # For general INCI: Get from MongoDB first, compute if not found
    # For combinations: Always compute based on individual INCI categories
    items_processed = []
    for item in items:
        # The matcher already sets description to enhanced_description if available
        display_description = item.description  # Already uses enhanced_description from matcher
        
        # Compute category for bifurcation (actives/excipients tabs)
        item_category = None
        
        if len(item.matched_inci) > 1:
            # COMBINATION: Always compute category based on individual INCI categories
            # Logic: If ANY INCI is Active → combination is Active
            item_category = await compute_item_category(item.matched_inci, inci_categories)
        elif item.tag == "G":
            # GENERAL INCI (single): Get from MongoDB first, compute if not found
            if len(item.matched_inci) == 1:
                inci_name = item.matched_inci[0].strip().lower()
                # Try to get from MongoDB first
                item_category = inci_categories.get(inci_name)
                # If not found in MongoDB, compute it (though it should be there)
                if not item_category:
                    item_category = await compute_item_category(item.matched_inci, inci_categories)
        elif item.tag == "B":
            # BRANDED (single): Use category_decided from MongoDB, but also compute for bifurcation
            # For single branded INCI, use category_decided if available, otherwise compute
            if item.category_decided:
                item_category = item.category_decided
            elif len(item.matched_inci) == 1:
                inci_name = item.matched_inci[0].strip().lower()
                item_category = inci_categories.get(inci_name)
                if not item_category:
                    item_category = await compute_item_category(item.matched_inci, inci_categories)
        
        # Create new item with only necessary fields
        item_dict = {
            "ingredient_name": item.ingredient_name,
            "ingredient_id": item.ingredient_id,
            "supplier_name": item.supplier_name,
            "description": display_description,  # Uses enhanced_description for branded ingredients
            "category_decided": item.category_decided,  # Keep category_decided from MongoDB for branded
            "category": item_category,  # Category for bifurcation (actives/excipients tabs)
            "functionality_category_tree": item.functionality_category_tree,
            "chemical_class_category_tree": item.chemical_class_category_tree,
            "match_score": item.match_score,
            "matched_inci": item.matched_inci,
            "tag": item.tag,
            "match_method": item.match_method
        }
        
        items_processed.append(AnalyzeInciItem(**item_dict))
    
    return inci_categories, items_processed

