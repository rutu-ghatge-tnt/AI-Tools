"""
Feature History Accessor
=======================

Unified module to access history data from different features.
Provides a single interface to fetch data from any feature's history collection.
"""

from typing import Dict, Any, Optional
from bson import ObjectId
from datetime import datetime

# Import all feature collections
from app.ai_ingredient_intelligence.db.collections import (
    market_research_history_col,
    wish_history_col,
    inci_col
)


# Product type configurations
PRODUCT_TYPE_CONFIG = {
    "market_research": {
        "type_name": "researched",
        "emoji": "🔍",
        "label": "Researched Product",
        "has_real_image": True
    },
    "formulation_decode": {
        "type_name": "decoded",
        "emoji": "🧪",
        "label": "Decoded Product",
        "has_real_image": True
    },
    "product_comparison": {
        "type_name": "compared",
        "emoji": "⚖️",
        "label": "Compared Product",
        "has_real_image": True
    },
    "make_wish": {
        "type_name": "formulation",
        "emoji": "✨",
        "label": "My Formulation",
        "has_real_image": False
    }
}


async def get_feature_history(feature_type: str, history_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch history data from any feature's collection
    
    Args:
        feature_type: Type of feature (market_research, make_wish, formulation_decode, product_comparison)
        history_id: History ID from the feature's collection
        
    Returns:
        History data dictionary or None if not found
    """
    try:
        obj_id = ObjectId(history_id)
    except:
        return None
    
    if feature_type == "market_research":
        return await market_research_history_col.find_one({"_id": obj_id})
    elif feature_type == "make_wish":
        return await wish_history_col.find_one({"_id": obj_id})
    elif feature_type == "formulation_decode":
        return await inci_col.find_one({"_id": obj_id})
    elif feature_type == "product_comparison":
        # TODO: Implement when product comparison history collection is available
        # For now, return None or implement based on your comparison storage
        return None
    else:
        return None


async def extract_product_data_from_history(feature_type: str, history_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract standardized product data from feature history
    
    Args:
        feature_type: Type of feature
        history_data: Raw history data from feature collection
        
    Returns:
        Standardized product data for inspiration board
    """
    if feature_type == "market_research":
        return _extract_market_research_product(history_data)
    elif feature_type == "make_wish":
        return _extract_make_wish_product(history_data)
    elif feature_type == "formulation_decode":
        return _extract_formulation_decode_product(history_data)
    elif feature_type == "product_comparison":
        return _extract_product_comparison_product(history_data)
    else:
        return {}


def _extract_market_research_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from market research history"""
    # Market research history typically contains:
    # - url, inci, mrp, benefits, and other scraped data
    # - AI analysis results
    
    product_data = {
        "name": history_data.get("product_name", "Unknown Product"),
        "brand": history_data.get("brand", "Unknown Brand"),
        "url": history_data.get("url"),
        "platform": _detect_platform(history_data.get("url", "")),
        "price": history_data.get("mrp", 0),
        "size": history_data.get("size", 0),
        "unit": history_data.get("unit", "ml"),
        "category": history_data.get("category"),
        "image": history_data.get("product_image", "🧴"),
        "notes": f"Market research analysis from {history_data.get('created_at', 'unknown date')}",
        "tags": ["market_research"],
        "product_type": PRODUCT_TYPE_CONFIG["market_research"]["type_name"]
    }
    
    return product_data


def _extract_make_wish_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from make a wish history"""
    # Make a wish history contains:
    # - wish parameters
    # - generated formula
    # - cost analysis
    # - manufacturing process
    
    wish_data = history_data.get("wish_data", {})
    formula_data = history_data.get("formula_data", {})
    
    product_data = {
        "name": wish_data.get("product_name", "My Formulation"),
        "brand": "Custom Formulation",
        "url": None,  # No real URL for formulations
        "platform": "formulation",
        "price": formula_data.get("estimated_cost_per_100g", 0),
        "size": 100,  # Standard 100g
        "unit": "g",
        "category": wish_data.get("product_category", "Custom"),
        "image": PRODUCT_TYPE_CONFIG["make_wish"]["emoji"],  # Use emoji instead of real image
        "notes": f"Generated from wish: {wish_data.get('wish_text', 'Unknown wish')}",
        "tags": ["formulation", "custom"],
        "product_type": PRODUCT_TYPE_CONFIG["make_wish"]["type_name"]
    }
    
    return product_data


def _extract_formulation_decode_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from formulation decode history"""
    # Formulation decode history contains:
    # - scraped product data
    # - ingredient analysis
    # - decoded formulation
    
    product_data = {
        "name": history_data.get("product_name", "Decoded Product"),
        "brand": history_data.get("brand", "Unknown Brand"),
        "url": history_data.get("url"),
        "platform": _detect_platform(history_data.get("url", "")),
        "price": history_data.get("price", 0),
        "size": history_data.get("size", 0),
        "unit": history_data.get("unit", "ml"),
        "category": history_data.get("category"),
        "image": history_data.get("product_image", "🧴"),
        "notes": f"Formulation decoded on {history_data.get('created_at', 'unknown date')}",
        "tags": ["decoded", "analysis"],
        "product_type": PRODUCT_TYPE_CONFIG["formulation_decode"]["type_name"]
    }
    
    return product_data


def _extract_product_comparison_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from product comparison history"""
    # TODO: Implement based on your comparison history structure
    # This would extract data from comparison results
    
    product_data = {
        "name": "Compared Product",
        "brand": "Unknown Brand",
        "url": None,
        "platform": "comparison",
        "price": 0,
        "size": 0,
        "unit": "ml",
        "category": None,
        "image": PRODUCT_TYPE_CONFIG["product_comparison"]["emoji"],
        "notes": "Product comparison result",
        "tags": ["comparison"],
        "product_type": PRODUCT_TYPE_CONFIG["product_comparison"]["type_name"]
    }
    
    return product_data


def _detect_platform(url: str) -> str:
    """Detect e-commerce platform from URL"""
    if not url:
        return "other"
    
    url_lower = url.lower()
    if "amazon" in url_lower:
        return "amazon"
    elif "nykaa" in url_lower:
        return "nykaa"
    elif "purplle" in url_lower:
        return "purplle"
    elif "flipkart" in url_lower:
        return "flipkart"
    elif "myntra" in url_lower:
        return "myntra"
    else:
        return "other"


def get_product_type_config(feature_type: str) -> Dict[str, Any]:
    """Get product type configuration for a feature"""
    return PRODUCT_TYPE_CONFIG.get(feature_type, PRODUCT_TYPE_CONFIG["market_research"])


async def validate_history_ids(feature_type: str, history_ids: list) -> Dict[str, Any]:
    """
    Validate that history IDs exist for the given feature
    
    Returns:
        Dict with valid_ids, invalid_ids, and count
    """
    valid_ids = []
    invalid_ids = []
    
    for history_id in history_ids:
        history_data = await get_feature_history(feature_type, history_id)
        if history_data:
            valid_ids.append(history_id)
        else:
            invalid_ids.append(history_id)
    
    return {
        "valid_ids": valid_ids,
        "invalid_ids": invalid_ids,
        "valid_count": len(valid_ids),
        "invalid_count": len(invalid_ids)
    }
