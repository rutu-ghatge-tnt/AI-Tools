"""
Feature History Accessor
=======================

Unified module to access history data from different features.
Provides a single interface to fetch data from any feature's history collection.
"""

from typing import Dict, Any, Optional, List
from bson import ObjectId
from datetime import datetime
import re

# Import all feature collections
from app.ai_ingredient_intelligence.db.collections import (
    market_research_history_col,
    wish_history_col,
    decode_history_col,
    compare_history_col
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
    },
    "make_wish_revised": {
        "type_name": "formulation",
        "emoji": "🚀",
        "label": "My Formulation (Revised)",
        "has_real_image": False
    }
}


async def get_feature_history(feature_type: str, history_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch history data from any feature's collection
    
    Args:
        feature_type: Type of feature (market_research, make_wish, make_wish_revised, formulation_decode, product_comparison)
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
    elif feature_type == "make_wish_revised":
        return await wish_history_col.find_one({"_id": obj_id})
    elif feature_type == "formulation_decode":
        return await decode_history_col.find_one({"_id": obj_id})
    elif feature_type == "product_comparison":
        return await compare_history_col.find_one({"_id": obj_id})
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
    elif feature_type == "make_wish_revised":
        return _extract_make_wish_revised_product(history_data)
    elif feature_type == "formulation_decode":
        return _extract_formulation_decode_product(history_data)
    elif feature_type == "product_comparison":
        return _extract_product_comparison_product(history_data)
    else:
        return {}


async def extract_products_from_history(feature_type: str, history_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract multiple products from feature history (useful for product_comparison)
    
    Args:
        feature_type: Type of feature
        history_data: Raw history data from feature collection
        
    Returns:
        List of standardized product data for inspiration board
    """
    if feature_type == "product_comparison":
        return _extract_product_comparison_products(history_data)
    else:
        # For other features, return single product as list
        product_data = await extract_product_data_from_history(feature_type, history_data)
        return [product_data] if product_data else []


def _extract_market_research_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from market research history"""
    # Market research history structure:
    # - Top level: name (user-provided), input_url, input_data, research_result
    # - research_result.products[]: Array of matched products with full details
    
    # Try to get product from research_result.products array (first product)
    research_result = history_data.get("research_result", {}) or {}
    products = research_result.get("products", [])
    
    # Use first product if available, otherwise fallback to top-level fields
    product = products[0] if products else {}
    
    # Extract product name
    name = (
        product.get("productName") or 
        product.get("name") or 
        history_data.get("name") or  # User-provided name
        "Unknown Product"
    )
    
    # Extract brand
    brand = (
        product.get("brand") or 
        history_data.get("brand") or 
        "Unknown Brand"
    )
    
    # Extract URL
    url = (
        product.get("url") or 
        product.get("productUrl") or 
        history_data.get("input_url") or 
        history_data.get("url")
    )
    
    # Extract price and MRP
    price = product.get("price") or history_data.get("price") or 0
    mrp = product.get("mrp") or history_data.get("mrp")
    
    # Convert to float if string
    if isinstance(price, str):
        price = _parse_price_string(price)
    if isinstance(mrp, str):
        mrp = _parse_price_string(mrp)
    
    # If price is 0 but MRP exists, use MRP as price
    if price == 0 and mrp:
        price = mrp
    
    # Extract size and unit
    size = product.get("size") or history_data.get("size") or 0
    unit = product.get("unit") or history_data.get("unit") or "ml"
    
    # If size is 0, try to extract from product name or description
    if size == 0:
        size_text = product.get("productName") or product.get("description") or ""
        extracted_size, extracted_unit = _extract_size_from_text(size_text)
        if extracted_size > 0:
            size = extracted_size
            unit = extracted_unit
    
    # Extract category
    category = (
        product.get("category") or 
        history_data.get("category") or 
        history_data.get("primary_category")
    )
    
    # Extract image
    image = (
        product.get("productImage") or 
        product.get("product_image") or 
        product.get("image") or 
        history_data.get("product_image") or 
        "🧴"
    )
    
    # Extract ingredients
    ingredients = (
        product.get("inci") or 
        product.get("ingredients") or 
        []
    )
    if isinstance(ingredients, str):
        ingredients = [ing.strip() for ing in ingredients.split(",") if ing.strip()]
    
    # Build notes with ingredients if available
    notes = f"Market research analysis from {history_data.get('created_at', 'unknown date')}"
    if ingredients:
        notes += f"\n\nIngredients: {', '.join(ingredients[:10])}"  # First 10 ingredients
    
    product_data = {
        "name": name,
        "brand": brand,
        "url": url,
        "platform": _detect_platform(url or ""),
        "price": float(price) if price else 0,
        "mrp": float(mrp) if mrp else None,
        "size": float(size) if size else 0,
        "unit": unit,
        "category": category,
        "image": image,
        "notes": notes,
        "tags": ["market_research"],
        "product_type": PRODUCT_TYPE_CONFIG["market_research"]["type_name"],
        "ingredients": ingredients  # Store ingredients for reference
    }
    
    return product_data


def _extract_make_wish_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from make a wish history"""
    # Make a wish history contains:
    # - wish_data: User input parameters
    # - formula_result: Generated formula with all analysis
    # - name, tag, notes: User-provided metadata
    
    wish_data = history_data.get("wish_data", {})
    formula_result = history_data.get("formula_result", {})
    optimized_formula = formula_result.get("optimized_formula", {})
    
    # Extract product name - use user-provided name first, then generate from wish data
    user_name = history_data.get("name", "")
    if user_name and user_name.strip():
        name = user_name.strip()
    else:
        # Generate name from wish parameters
        product_type = wish_data.get("productType", "Formulation")
        benefits = wish_data.get("benefits", [])
        if benefits:
            name = f"{product_type} - {', '.join(benefits[:2])}"
        else:
            name = f"Custom {product_type}"
    
    # Extract ingredients from optimized formula
    ingredients = []
    if optimized_formula:
        # Extract ingredient names from formula structure
        formula_items = optimized_formula.get("ingredients", []) or optimized_formula.get("formula", [])
        if isinstance(formula_items, list):
            for item in formula_items:
                if isinstance(item, dict):
                    ing_name = item.get("name") or item.get("ingredient") or item.get("inci")
                    if ing_name:
                        ingredients.append(ing_name)
                elif isinstance(item, str):
                    ingredients.append(item)
    
    # Build comprehensive notes
    notes_parts = []
    
    # Add user notes if available
    user_notes = history_data.get("notes", "")
    if user_notes and user_notes.strip():
        notes_parts.append(f"Notes: {user_notes.strip()}")
    
    # Add wish parameters
    if wish_data.get("benefits"):
        notes_parts.append(f"Benefits: {', '.join(wish_data['benefits'])}")
    
    if wish_data.get("heroIngredients"):
        notes_parts.append(f"Hero Ingredients: {', '.join(wish_data['heroIngredients'])}")
    
    if wish_data.get("exclusions"):
        notes_parts.append(f"Exclusions: {', '.join(wish_data['exclusions'])}")
    
    # Add ingredients list
    if ingredients:
        notes_parts.append(f"Ingredients: {', '.join(ingredients[:15])}")  # First 15 ingredients
    
    # Add cost analysis if available
    cost_analysis = formula_result.get("cost_analysis", {})
    if cost_analysis:
        total_cost = cost_analysis.get("raw_material_cost", {}).get("total_per_100g", 0)
        if total_cost:
            notes_parts.append(f"Estimated Cost: ₹{total_cost}/100g")
    
    # Add compliance status if available
    compliance = formula_result.get("compliance", {})
    if compliance:
        overall_status = compliance.get("overall_status", "")
        if overall_status:
            notes_parts.append(f"Compliance: {overall_status}")
    
    notes = "\n".join(notes_parts) if notes_parts else "Custom formulation generated from wish"
    
    # Extract cost from formula result
    cost_per_100g = 0
    if cost_analysis:
        cost_per_100g = cost_analysis.get("raw_material_cost", {}).get("total_per_100g", 0) or 0
    
    product_data = {
        "name": name,
        "brand": "Custom Formulation",
        "url": None,  # No real URL for formulations
        "platform": "formulation",
        "price": cost_per_100g,
        "size": 100,  # Standard 100g
        "unit": "g",
        "category": wish_data.get("productType", "Custom"),
        "image": PRODUCT_TYPE_CONFIG["make_wish"]["emoji"],  # Use emoji instead of real image
        "notes": notes,
        "tags": ["formulation", "custom"] + (wish_data.get("benefits", [])[:2] if wish_data.get("benefits") else []),
        "product_type": PRODUCT_TYPE_CONFIG["make_wish"]["type_name"],
        "ingredients": ingredients
    }
    
    return product_data


def _extract_make_wish_revised_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from revised make a wish history"""
    # Revised Make a Wish history contains:
    # - wish_text: Natural language input
    # - parsed_data: Structured parsed information
    # - formula_data: Generated formula with all analysis
    # - name, tag, notes: User-provided metadata
    # - complexity: Selected complexity level
    
    wish_text = history_data.get("wish_text", "")
    parsed_data = history_data.get("parsed_data", {})
    formula_data = history_data.get("formula_data", {})
    optimized_formula = formula_data.get("optimized_formula", {})
    complexity = history_data.get("complexity", "classic")
    
    # Extract product name - use user-provided name first, then from formula
    user_name = history_data.get("name", "")
    if user_name and user_name.strip():
        name = user_name.strip()
    else:
        # Generate name from formula or parsed data
        formula_name = optimized_formula.get("name", "")
        if formula_name:
            name = formula_name
        else:
            product_type = parsed_data.get("product_type", {}).get("name", "Formulation")
            benefits = parsed_data.get("detected_benefits", [])
            if benefits:
                name = f"{product_type} - {', '.join(benefits[:2])}"
            else:
                name = f"Custom {product_type}"
    
    # Extract ingredients from optimized formula
    ingredients = []
    if optimized_formula:
        # Extract ingredient names from formula structure
        formula_items = optimized_formula.get("ingredients", []) or optimized_formula.get("formula", [])
        if isinstance(formula_items, list):
            for item in formula_items:
                if isinstance(item, dict):
                    ing_name = item.get("name") or item.get("ingredient") or item.get("inci")
                    if ing_name:
                        ingredients.append(ing_name)
                elif isinstance(item, str):
                    ingredients.append(item)
    
    # Build comprehensive notes
    notes_parts = []
    
    # Add user notes if available
    user_notes = history_data.get("notes", "")
    if user_notes and user_notes.strip():
        notes_parts.append(f"Notes: {user_notes.strip()}")
    
    # Add wish text (truncated)
    if wish_text:
        notes_parts.append(f"Wish: {wish_text[:100]}...")
    
    # Add complexity level
    complexity_emoji = {"minimalist": "⚡", "classic": "✨", "luxe": "💎"}.get(complexity, "✨")
    notes_parts.append(f"Complexity: {complexity_emoji} {complexity.title()}")
    
    # Add parsed benefits and exclusions
    if parsed_data.get("detected_benefits"):
        notes_parts.append(f"Benefits: {', '.join(parsed_data['detected_benefits'])}")
    
    if parsed_data.get("detected_exclusions"):
        notes_parts.append(f"Exclusions: {', '.join(parsed_data['detected_exclusions'])}")
    
    # Add detected ingredients
    if parsed_data.get("detected_ingredients"):
        detected_ings = [ing.get("name", "") for ing in parsed_data["detected_ingredients"] if ing.get("name")]
        if detected_ings:
            notes_parts.append(f"Requested Ingredients: {', '.join(detected_ings[:5])}")
    
    # Add ingredients list
    if ingredients:
        notes_parts.append(f"Ingredients: {', '.join(ingredients[:15])}")  # First 15 ingredients
    
    # Add cost analysis if available
    if formula_data.get("cost_analysis"):
        cost_analysis = formula_data["cost_analysis"]
        total_cost = cost_analysis.get("raw_material_cost", {}).get("total_per_100g", 0)
        if total_cost:
            notes_parts.append(f"Estimated Cost: ₹{total_cost}/100g")
    
    # Add compliance status if available
    if formula_data.get("compliance"):
        compliance = formula_data["compliance"]
        overall_status = compliance.get("overall_status", "")
        if overall_status:
            notes_parts.append(f"Compliance: {overall_status}")
    
    notes = "\n".join(notes_parts) if notes_parts else "Custom formulation generated from revised wish"
    
    # Extract cost from formula data
    cost_per_100g = 0
    if formula_data.get("cost_analysis"):
        cost_per_100g = formula_data["cost_analysis"].get("raw_material_cost", {}).get("total_per_100g", 0) or 0
    
    # Extract product type from parsed data
    product_type = parsed_data.get("product_type", {}).get("name", "Custom")
    
    # Create tags including complexity and benefits
    tags = ["formulation", "revised", complexity]
    if parsed_data.get("detected_benefits"):
        tags.extend(parsed_data["detected_benefits"][:2])  # First 2 benefits
    
    product_data = {
        "name": name,
        "brand": "Custom Formulation (Revised)",
        "url": None,  # No real URL for formulations
        "platform": "formulation_revised",
        "price": cost_per_100g,
        "size": 100,  # Standard 100g
        "unit": "g",
        "category": product_type,
        "image": complexity_emoji,  # Use complexity emoji
        "notes": notes,
        "tags": tags,
        "product_type": "formulation",  # Keep same type for compatibility
        "ingredients": ingredients
    }
    
    return product_data


def _extract_formulation_decode_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from formulation decode history"""
    # Formulation decode history structure:
    # - name: User-provided name
    # - input_type: "url" or "inci"
    # - input_data: URL or INCI list
    # - analysis_result: Analysis results (may contain product info)
    
    # Get name from history (user-provided name)
    name = history_data.get("name", "Decoded Product")
    
    # Extract URL if input_type is "url"
    url = None
    input_type = history_data.get("input_type", "")
    input_data = history_data.get("input_data", "")
    
    if input_type == "url" and input_data:
        # input_data contains the URL
        url = input_data if isinstance(input_data, str) and input_data.startswith(("http://", "https://")) else None
    
    # Try to get product info from analysis_result if available (some older data might have it)
    analysis_result = history_data.get("analysis_result", {}) or {}
    
    # Extract price and MRP
    price = history_data.get("price") or analysis_result.get("price") or 0
    mrp = history_data.get("mrp") or analysis_result.get("mrp")
    
    # Convert to float if string
    if isinstance(price, str):
        price = _parse_price_string(price)
    if isinstance(mrp, str):
        mrp = _parse_price_string(mrp)
    
    # Extract size and unit
    size = history_data.get("size") or analysis_result.get("size") or 0
    unit = history_data.get("unit") or analysis_result.get("unit") or "ml"
    
    # Extract ingredients from input_data or analysis_result
    ingredients = []
    if input_type == "inci" and input_data:
        if isinstance(input_data, str):
            ingredients = [ing.strip() for ing in input_data.split(",") if ing.strip()]
        elif isinstance(input_data, list):
            ingredients = [str(ing).strip() for ing in input_data if ing]
    
    # Also check analysis_result for ingredients
    if not ingredients and analysis_result:
        decoded_data = analysis_result.get("decoded_data", {})
        if decoded_data:
            ingredient_list = decoded_data.get("ingredients", [])
            if ingredient_list:
                ingredients = [item.get("name") or item.get("inci") or str(item) for item in ingredient_list if item]
    
    # Build notes with ingredients if available
    notes = f"Formulation decoded on {history_data.get('created_at', 'unknown date')}"
    if ingredients:
        notes += f"\n\nIngredients: {', '.join(ingredients[:15])}"  # First 15 ingredients
    
    product_data = {
        "name": name,
        "brand": history_data.get("brand") or analysis_result.get("brand") or "Unknown Brand",
        "url": url,
        "platform": _detect_platform(url or ""),
        "price": float(price) if price else 0,
        "mrp": float(mrp) if mrp else None,
        "size": float(size) if size else 0,
        "unit": unit,
        "category": history_data.get("category") or analysis_result.get("category"),
        "image": history_data.get("product_image") or analysis_result.get("product_image") or PRODUCT_TYPE_CONFIG["formulation_decode"]["emoji"],
        "notes": notes,
        "tags": ["decoded", "analysis"],
        "product_type": PRODUCT_TYPE_CONFIG["formulation_decode"]["type_name"],
        "ingredients": ingredients
    }
    
    return product_data


def _extract_product_comparison_products(history_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract product data from product comparison history - returns list of products"""
    # Product comparison history structure:
    # - comparison_result.products[]: Array of ProductComparisonItem objects
    #   Each product has: product_name, brand_name, price (string), url, inci, etc.
    
    comparison_result = history_data.get("comparison_result", {}) or {}
    products = comparison_result.get("products", [])
    
    if not products:
        # Fallback: return single product with basic info
        return [{
            "name": history_data.get("name", "Compared Product"),
            "brand": "Unknown Brand",
            "url": None,
            "platform": "comparison",
            "price": 0,
            "size": 0,
            "unit": "ml",
            "category": None,
            "image": PRODUCT_TYPE_CONFIG["product_comparison"]["emoji"],
            "notes": f"Product comparison from {history_data.get('created_at', 'unknown date')}",
            "tags": ["comparison"],
            "product_type": PRODUCT_TYPE_CONFIG["product_comparison"]["type_name"],
            "ingredients": []
        }]
    
    extracted_products = []
    
    for idx, product in enumerate(products):
        # Extract product name
        name = product.get("product_name") or product.get("name") or f"Compared Product {idx + 1}"
        
        # Extract brand
        brand = product.get("brand_name") or product.get("brand") or "Unknown Brand"
        
        # Extract URL
        url = product.get("url")
        
        # Extract and parse price
        price_str = product.get("price") or "0"
        price = _parse_price_string(price_str) if isinstance(price_str, str) else (float(price_str) if price_str else 0)
        
        # Extract MRP if available
        mrp_str = product.get("mrp")
        mrp = _parse_price_string(mrp_str) if isinstance(mrp_str, str) else (float(mrp_str) if mrp_str else None)
        
        # Extract size and unit from product name or description
        size = 0
        unit = "ml"
        product_name_text = name
        extracted_text = product.get("extracted_text", "")
        size_text = product_name_text + " " + extracted_text
        extracted_size, extracted_unit = _extract_size_from_text(size_text)
        if extracted_size > 0:
            size = extracted_size
            unit = extracted_unit
        
        # Extract category
        category = product.get("category")
        
        # Extract image (may not be available in comparison)
        image = product.get("image") or product.get("product_image") or PRODUCT_TYPE_CONFIG["product_comparison"]["emoji"]
        
        # Extract ingredients
        ingredients = product.get("inci") or product.get("ingredients") or []
        if isinstance(ingredients, str):
            ingredients = [ing.strip() for ing in ingredients.split(",") if ing.strip()]
        elif not isinstance(ingredients, list):
            ingredients = []
        
        # Build notes with ingredients if available
        notes = f"Product {idx + 1} from comparison: {history_data.get('name', 'Product Comparison')}"
        if ingredients:
            notes += f"\n\nIngredients: {', '.join(ingredients[:15])}"  # First 15 ingredients
        
        product_data = {
            "name": name,
            "brand": brand,
            "url": url,
            "platform": _detect_platform(url or ""),
            "price": float(price) if price else 0,
            "mrp": float(mrp) if mrp else None,
            "size": float(size) if size else 0,
            "unit": unit,
            "category": category,
            "image": image,
            "notes": notes,
            "tags": ["comparison"],
            "product_type": PRODUCT_TYPE_CONFIG["product_comparison"]["type_name"],
            "ingredients": ingredients
        }
        
        extracted_products.append(product_data)
    
    return extracted_products


def _extract_product_comparison_product(history_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract product data from product comparison history - returns first product for backward compatibility"""
    products = _extract_product_comparison_products(history_data)
    return products[0] if products else {
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
        "product_type": PRODUCT_TYPE_CONFIG["product_comparison"]["type_name"],
        "ingredients": []
    }


def _parse_price_string(price_str: str) -> float:
    """Parse price string like '₹999', '$29.99', 'INR 1,299' to float"""
    if not price_str or not isinstance(price_str, str):
        return 0.0
    
    # Remove currency symbols and text
    price_str = re.sub(r'[₹$€£]', '', price_str)
    price_str = re.sub(r'INR|USD|EUR|GBP', '', price_str, flags=re.IGNORECASE)
    price_str = re.sub(r'Rs\.?|rupees?', '', price_str, flags=re.IGNORECASE)
    
    # Remove commas and whitespace
    price_str = price_str.replace(',', '').strip()
    
    # Extract numbers
    numbers = re.findall(r'\d+\.?\d*', price_str)
    if numbers:
        try:
            return float(numbers[0])
        except ValueError:
            return 0.0
    
    return 0.0


def _extract_size_from_text(text: str) -> tuple:
    """Extract size and unit from text (e.g., '50ml', '100g', '30 ml')"""
    if not text:
        return (0, "ml")
    
    # Look for patterns like "50ml", "100g", "30 ml", "1.5 oz"
    patterns = [
        r'(\d+\.?\d*)\s*(ml|g|oz|kg|mg|l)',
        r'(\d+\.?\d*)\s*(ml|g|oz|kg|mg|l)\s*',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            size = float(match.group(1))
            unit = match.group(2).lower()
            return (size, unit)
    
    return (0, "ml")


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
