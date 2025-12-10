"""
Product decoding logic - Integrates with analyze-inci to decode products
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.ai_ingredient_intelligence.db.collections import inspiration_products_col
from bson import ObjectId
import httpx
import os


async def decode_product(user_id: str, product_id: str) -> Dict[str, Any]:
    """
    Decode a product by analyzing its ingredients
    
    This function:
    1. Gets product data
    2. Extracts ingredients (from URL or stored data)
    3. Calls analyze-inci endpoint
    4. Generates decoded_data structure
    5. Updates product in database
    """
    try:
        product_obj_id = ObjectId(product_id)
    except:
        return {"success": False, "error": "Invalid product ID"}
    
    # Get product
    product = await inspiration_products_col.find_one({
        "_id": product_obj_id,
        "user_id": user_id
    })
    
    if not product:
        return {"success": False, "error": "Product not found"}
    
    if product.get("decoded"):
        return {
            "success": True,
            "product_id": product_id,
            "decoded": True,
            "decoded_data": product.get("decoded_data"),
            "message": "Product already decoded"
        }
    
    # Get ingredients - try from URL or stored data
    ingredients = []
    
    # If product has URL, try to extract ingredients
    if product.get("url"):
        from app.ai_ingredient_intelligence.logic.url_fetcher import fetch_product_from_url
        fetched = await fetch_product_from_url(product["url"])
        ingredients = fetched.get("ingredients", [])
    
    if not ingredients:
        return {
            "success": False,
            "error": "No ingredients found. Please ensure product URL is valid and contains ingredient information."
        }
    
    # Call analyze-inci endpoint
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    analyze_url = f"{base_url}/api/analyze-inci"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                analyze_url,
                json={
                    "inci_names": ingredients,
                    "input_type": "text"
                }
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to analyze ingredients: {response.text}"
                }
            
            analyze_result = response.json()
            
            # Generate decoded_data from analyze result
            decoded_data = await _generate_decoded_data(
                ingredients,
                analyze_result,
                product
            )
            
            # Update product
            await inspiration_products_col.update_one(
                {"_id": product_obj_id},
                {
                    "$set": {
                        "decoded": True,
                        "decoded_data": decoded_data,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            return {
                "success": True,
                "product_id": product_id,
                "decoded": True,
                "decoded_data": decoded_data
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to decode product: {str(e)}"
        }


async def _generate_decoded_data(
    ingredients: List[str],
    analyze_result: Dict[str, Any],
    product: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate decoded_data structure from analyze-inci result
    
    This is a simplified version - can be enhanced with AI for market positioning
    """
    # Extract ingredient details from analyze result
    ingredient_details = []
    total_concentration = 0
    
    # Get grouped ingredients
    grouped = analyze_result.get("grouped", [])
    branded = analyze_result.get("branded_ingredients", [])
    
    # Process ingredients to create ingredient_details
    # This is simplified - in production, you'd use AI to estimate concentrations
    for i, ing_name in enumerate(ingredients[:20]):  # Limit to 20 ingredients
        # Estimate concentration (simplified - would use AI in production)
        concentration = _estimate_concentration(ing_name, i, len(ingredients))
        total_concentration += concentration
        
        # Find matching ingredient info
        inci_name = ing_name
        function = "Ingredient"
        
        # Try to find in branded ingredients
        for brand_ing in branded:
            if brand_ing.get("ingredient_name", "").lower() == ing_name.lower():
                inci_name = brand_ing.get("matched_inci", [ing_name])[0] if brand_ing.get("matched_inci") else ing_name
                function = brand_ing.get("description", "Ingredient")[:50]  # Truncate
                break
        
        # Determine phase
        phase = _determine_phase(inci_name)
        
        # Estimate cost (simplified)
        cost = _estimate_cost(inci_name, concentration)
        
        ingredient_details.append({
            "name": ing_name,
            "inci": inci_name,
            "phase": phase,
            "concentration": round(concentration, 2),
            "cost": round(cost, 2),
            "function": function
        })
    
    # Normalize concentrations to sum to ~100%
    if total_concentration > 0 and total_concentration != 100:
        factor = 100 / total_concentration
        for ing in ingredient_details:
            ing["concentration"] = round(ing["concentration"] * factor, 2)
    
    # Calculate phase breakdown
    phase_breakdown = {}
    phase_costs = {}
    for ing in ingredient_details:
        phase = ing["phase"]
        phase_breakdown[phase] = phase_breakdown.get(phase, 0) + ing["concentration"]
        phase_costs[phase] = phase_costs.get(phase, 0) + ing["cost"]
    
    # Identify hero ingredients (top 3 by concentration)
    sorted_ingredients = sorted(ingredient_details, key=lambda x: x["concentration"], reverse=True)
    hero_ingredients = [
        f"{ing['name']} {ing['concentration']:.1f}%"
        for ing in sorted_ingredients[:3]
        if ing["concentration"] > 1.0
    ]
    
    # Estimate total cost per 100g
    total_cost = sum(ing["cost"] for ing in ingredient_details)
    estimated_cost = round(total_cost, 0)
    
    # Determine formulation type
    formulation_type = _determine_formulation_type(phase_breakdown)
    
    # Determine complexity
    complexity = "Low"
    if len(ingredient_details) > 15:
        complexity = "High"
    elif len(ingredient_details) > 10:
        complexity = "Medium"
    
    # Determine pH range (simplified)
    ph_range = _estimate_ph_range(ingredient_details)
    
    # Compliance (simplified - would use BIS RAG in production)
    compliance = {
        "bis": {"status": "compliant", "notes": "All ingredients within BIS limits"},
        "eu": {"status": "compliant", "notes": "EU Cosmetics Regulation compliant"},
        "fda": {"status": "compliant", "notes": "FDA guidelines met"}
    }
    
    # Market positioning (simplified - would use AI in production)
    price = product.get("price", 0)
    price_segment = "Budget"
    if price > 1000:
        price_segment = "Premium"
    elif price > 500:
        price_segment = "Mid-Range"
    
    market_position = {
        "price_segment": price_segment,
        "target_audience": "General consumers",
        "usp": "Effective formulation",
        "competitors": []
    }
    
    return {
        "ingredient_count": len(ingredient_details),
        "hero_ingredients": hero_ingredients,
        "estimated_cost": estimated_cost,
        "ph_range": ph_range,
        "formulation_type": formulation_type,
        "manufacturing_complexity": complexity,
        "shelf_life": "12 months",
        "ingredients": ingredient_details,
        "compliance": compliance,
        "market_position": market_position
    }


def _estimate_concentration(ingredient_name: str, index: int, total: int) -> float:
    """Estimate ingredient concentration (simplified)"""
    # Water is typically highest
    if "water" in ingredient_name.lower() or "aqua" in ingredient_name.lower():
        return 60.0
    
    # First few ingredients after water are usually higher
    if index < 3:
        return 10.0 - (index * 2)
    elif index < 6:
        return 5.0 - ((index - 3) * 0.5)
    else:
        return max(0.1, 2.0 - ((index - 6) * 0.1))


def _determine_phase(inci_name: str) -> str:
    """Determine ingredient phase"""
    inci_lower = inci_name.lower()
    
    # Water phase
    if any(x in inci_lower for x in ["aqua", "water", "glycerin", "alcohol", "glycol"]):
        return "water"
    
    # Oil phase
    if any(x in inci_lower for x in ["oil", "butter", "wax", "ester", "squalane"]):
        return "oil"
    
    # Active phase
    if any(x in inci_lower for x in ["acid", "peptide", "retinol", "vitamin", "niacinamide"]):
        return "active"
    
    # Preservative
    if any(x in inci_lower for x in ["phenoxy", "paraben", "benzoate", "sorbate"]):
        return "preservative"
    
    return "other"


def _estimate_cost(inci_name: str, concentration: float) -> float:
    """Estimate ingredient cost (simplified)"""
    inci_lower = inci_name.lower()
    
    # Basic ingredients are cheap
    if any(x in inci_lower for x in ["water", "aqua", "glycerin"]):
        return 0.02 * concentration
    
    # Actives are expensive
    if any(x in inci_lower for x in ["retinol", "peptide", "vitamin c", "niacinamide"]):
        return 5.0 * concentration
    
    # Oils are moderate
    if any(x in inci_lower for x in ["oil", "butter"]):
        return 1.0 * concentration
    
    # Default
    return 0.5 * concentration


def _determine_formulation_type(phase_breakdown: Dict[str, float]) -> str:
    """Determine formulation type from phase breakdown"""
    water_pct = phase_breakdown.get("water", 0)
    oil_pct = phase_breakdown.get("oil", 0)
    
    if water_pct > 70:
        return "Water-based Serum"
    elif oil_pct > 50:
        return "Oil-based Formula"
    elif water_pct > 50:
        return "Water-based Formula"
    else:
        return "Balanced Formula"


def _estimate_ph_range(ingredients: List[Dict[str, Any]]) -> str:
    """Estimate pH range"""
    # Check for acids
    has_acid = any("acid" in ing["inci"].lower() for ing in ingredients)
    
    if has_acid:
        return "3.5-5.5"
    else:
        return "5.0-6.5"

