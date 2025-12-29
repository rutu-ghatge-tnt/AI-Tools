"""
Analysis Core Logic
===================

Core business logic for ingredient analysis.
Extracted from analyze_inci.py for better modularity.
"""

import time
import asyncio
from typing import List, Dict
from collections import defaultdict
from fastapi import HTTPException

from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.logic.bis_rag import get_bis_cautions_for_ingredients
from app.ai_ingredient_intelligence.logic.cas_api import get_synonyms_batch
from app.ai_ingredient_intelligence.logic.category_computer import fetch_and_compute_categories
from app.ai_ingredient_intelligence.logic.distributor_fetcher import fetch_distributors_for_branded_ingredients
from app.ai_ingredient_intelligence.models.schemas import (
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup
)


async def analyze_ingredients_core(ingredients: List[str]) -> AnalyzeInciResponse:
    """
    Core ingredient analysis logic that can be called directly.
    This function performs the analysis without history saving or authentication.
    
    Args:
        ingredients: List of ingredient names to analyze
        
    Returns:
        AnalyzeInciResponse with analysis results
    """
    start = time.time()
    
    try:
        if not ingredients:
            raise ValueError("No ingredients provided")
        
        # OPTIMIZED: Run CAS synonyms and BIS cautions in parallel (they're independent)
        print("Retrieving synonyms from CAS API and BIS cautions in parallel...")
        synonyms_task = get_synonyms_batch(ingredients)
        bis_cautions_task = get_bis_cautions_for_ingredients(ingredients)
        
        # Wait for both to complete
        synonyms_map, bis_cautions = await asyncio.gather(synonyms_task, bis_cautions_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(synonyms_map, Exception):
            print(f"Warning: Error getting synonyms: {synonyms_map}")
            synonyms_map = {}
        if isinstance(bis_cautions, Exception):
            print(f"Warning: Error getting BIS cautions: {bis_cautions}")
            bis_cautions = {}
        
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        if bis_cautions:
            print(f"[OK] Retrieved BIS cautions for {len(bis_cautions)} ingredients: {list(bis_cautions.keys())}")
        else:
            print("[WARNING] No BIS cautions retrieved - this may indicate an issue with the BIS retriever")
        
        # Match ingredients using new flow
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
    except Exception as e:
        print(f"Error in analyze_ingredients_core: {e}")
        # Show operation stack
        import traceback
        print(f"\n{'='*60}")
        print(f"OPERATION STACK in analyze_ingredients_core:")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"{'='*60}\n")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    # Convert to objects
    items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

    # OPTIMIZED: Run categories and distributors fetching in parallel (they're independent)
    print("Fetching ingredient categories and distributor information in parallel...")
    categories_task = fetch_and_compute_categories(items)
    distributors_task = fetch_distributors_for_branded_ingredients(items)
    
    # Wait for both to complete
    categories_result, distributor_info = await asyncio.gather(
        categories_task, 
        distributors_task, 
        return_exceptions=True
    )
    
    # Handle exceptions
    if isinstance(categories_result, Exception):
        print(f"Warning: Error fetching categories: {categories_result}")
        inci_categories, items_processed = {}, items
    else:
        inci_categories, items_processed = categories_result
    
    if isinstance(distributor_info, Exception):
        print(f"Warning: Error fetching distributors: {distributor_info}")
        distributor_info = {}
    
    print(f"Found categories for {len(inci_categories)} INCI names")
    if distributor_info:
        print(f"Found distributors for {len(distributor_info)} branded ingredients")
    else:
        print("No distributor information found")

    # 🔹 Group ALL detected ingredients (branded + general) by matched_inci
    detected_dict = defaultdict(list)
    for item in items_processed:
        key = tuple(sorted(item.matched_inci))
        detected_dict[key].append(item)

    detected: List[InciGroup] = [
        InciGroup(
            inci_list=list(key),
            items=val,
            count=len(val)
        )
        for key, val in detected_dict.items()
    ]
    # Sort by number of INCI: more INCI first, then lower, single at last
    detected.sort(key=lambda x: len(x.inci_list), reverse=True)

    # Filter out water-related BIS cautions
    filtered_bis_cautions = None
    if bis_cautions:
        filtered_bis_cautions = {}
        water_related_keywords = ['water', 'aqua']
        for ingredient, cautions in bis_cautions.items():
            ingredient_lower = ingredient.lower()
            is_water_related = any(water_term in ingredient_lower for water_term in water_related_keywords)
            if not is_water_related:
                filtered_bis_cautions[ingredient] = cautions

    # Build response (deprecated fields are not included - they will be excluded by exclude_none=True in schema)
    response = AnalyzeInciResponse(
        detected=detected,  # All detected ingredients (branded + general) grouped by INCI
        unable_to_decode=unable_to_decode,
        processing_time=round(time.time() - start, 3),
        bis_cautions=filtered_bis_cautions if filtered_bis_cautions else None,
        categories=inci_categories if inci_categories else None,  # INCI categories for bifurcation
        distributor_info=distributor_info if distributor_info else None,  # Distributor info for branded ingredients
    )
    
    return response

