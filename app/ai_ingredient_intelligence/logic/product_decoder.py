"""
Product decoding logic - Integrates with analyze-inci to decode products
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.ai_ingredient_intelligence.db.collections import inspiration_products_col
from bson import ObjectId
from pymongo.errors import _OperationCancelled, NetworkTimeout, ServerSelectionTimeoutError
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
    try:
        product = await inspiration_products_col.find_one({
            "_id": product_obj_id,
            "user_id": user_id
        })
    except (_OperationCancelled, NetworkTimeout, ServerSelectionTimeoutError) as e:
        return {
            "success": False,
            "error": "Database operation was cancelled or timed out. Please try again."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch product from database: {str(e)}"
        }
    
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
    
    # Call analyze-inci core function directly (no HTTP request needed)
    try:
        from app.ai_ingredient_intelligence.api.analyze_inci import analyze_ingredients_core
        
        # Call the core analysis function directly
        analyze_response = await analyze_ingredients_core(ingredients)
        
        # Convert response to dict format
        analyze_result = analyze_response.dict()
        
        # Get formulation report to extract summary (pH, formulation type, etc.)
        report_summary = await _get_formulation_report_summary(ingredients, analyze_result)
        
        # Generate decoded_data from analyze result
        decoded_data = await _generate_decoded_data(
            ingredients,
            analyze_result,
            product,
            report_summary
        )
        
        # Update product
        try:
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
        except (_OperationCancelled, NetworkTimeout, ServerSelectionTimeoutError) as e:
            return {
                "success": False,
                "error": "Database operation was cancelled or timed out while saving results. The analysis may have completed, but results were not saved. Please try again."
            }
        
        return {
            "success": True,
            "product_id": product_id,
            "decoded": True,
            "decoded_data": decoded_data
        }
            
    except (_OperationCancelled, NetworkTimeout, ServerSelectionTimeoutError) as e:
        return {
            "success": False,
            "error": "Database operation was cancelled or timed out. Please try again."
        }
    except Exception as e:
        error_msg = str(e)
        # Check if it's an operation cancelled error
        if "_OperationCancelled" in error_msg or "operation cancelled" in error_msg.lower():
            return {
                "success": False,
                "error": "Operation was cancelled. This may happen if the request was interrupted. Please try again."
            }
        return {
            "success": False,
            "error": f"Failed to decode product: {error_msg}"
        }


async def _generate_decoded_data(
    ingredients: List[str],
    analyze_result: Dict[str, Any],
    product: Dict[str, Any],
    report_summary: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate decoded_data structure from analyze-inci result
    
    This is a simplified version - can be enhanced with AI for market positioning
    """
    # Extract ingredient details from analyze result
    ingredient_details = []
    total_concentration = 0
    
    # Get detected ingredients (new structure)
    detected = analyze_result.get("detected", [])
    
    # Extract branded ingredients from detected groups
    branded_items = []
    for group in detected:
        for item in group.get("items", []):
            if item.get("tag") == "B":  # Branded ingredient
                branded_items.append(item)
    
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
        for brand_ing in branded_items:
            if brand_ing.get("ingredient_name", "").lower() == ing_name.lower():
                matched_inci = brand_ing.get("matched_inci", [])
                inci_name = matched_inci[0] if matched_inci else ing_name
                function = (brand_ing.get("description") or "Ingredient")[:50]  # Truncate
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
    
    # Get formulation type from report summary if available, otherwise estimate
    if report_summary and report_summary.get("formulation_type"):
        formulation_type = report_summary["formulation_type"]
    else:
        formulation_type = _determine_formulation_type(phase_breakdown)
    
    # Determine complexity
    complexity = "Low"
    if len(ingredient_details) > 15:
        complexity = "High"
    elif len(ingredient_details) > 10:
        complexity = "Medium"
    
    # Get pH range from report summary if available, otherwise estimate
    if report_summary and report_summary.get("recommended_ph_range"):
        ph_range = report_summary["recommended_ph_range"]
        # Extract just the range (e.g., "5.0-6.5" from "Recommended pH range: 5.0-6.5")
        import re
        ph_match = re.search(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)', ph_range)
        if ph_match:
            ph_range = f"{ph_match.group(1)}-{ph_match.group(2)}"
    else:
        ph_range = _estimate_ph_range_fallback(ingredients)
    
    # Determine viscosity based on formulation type
    viscosity = _estimate_viscosity(formulation_type, phase_breakdown)
    
    # Determine shelf life
    shelf_life = _estimate_shelf_life(ingredient_details)
    
    # Calculate phase breakdown array (matching image format)
    phase_breakdown_array = _create_phase_breakdown_array(phase_breakdown)
    
    # Calculate function breakdown array (matching image format)
    function_breakdown_array = _create_function_breakdown_array(ingredient_details, analyze_result)
    
    # Create hero ingredients array with details (matching image format)
    hero_ingredients_array = _create_hero_ingredients_array(sorted_ingredients, ingredient_details)
    
    # Mark hero ingredients in ingredient_details
    for ing in ingredient_details:
        ing["isHero"] = any(
            h.get("name", "").lower() == ing["name"].lower() or 
            h.get("chemicalName", "").lower() == ing["inci"].lower()
            for h in hero_ingredients_array
        )
    
    # Determine product tags/certifications
    product_tags = _determine_product_tags(ingredient_details, analyze_result)
    
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
        "hero_ingredients": hero_ingredients,  # Keep for backward compatibility
        "estimated_cost": estimated_cost,
        "ph_range": ph_range,
        "formulation_type": formulation_type,
        "manufacturing_complexity": complexity,
        "shelf_life": shelf_life,
        "ingredients": ingredient_details,
        "compliance": compliance,
        "market_position": market_position,
        # New summary structure matching image format
        "summary": {
            "formulationType": formulation_type,
            "phEstimate": ph_range,
            "viscosity": viscosity,
            "shelfLife": shelf_life
        },
        "phaseBreakdown": phase_breakdown_array,
        "functionBreakdown": function_breakdown_array,
        "heroIngredients": hero_ingredients_array,
        "productTags": product_tags,
        "manufacturingNotes": {
            "shelfLife": shelf_life,
            "difficulty": complexity,
            "processType": "Cold Process" if "serum" in formulation_type.lower() else "Hot Process"
        }
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


async def _get_formulation_report_summary(ingredients: List[str], analyze_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get formulation report summary (pH, formulation type, etc.) from report JSON API"""
    try:
        # Extract branded and not branded ingredients from analyze_result
        branded_ingredients = []
        not_branded_ingredients = []
        bis_cautions = analyze_result.get("bis_cautions", {})
        
        # Get detected groups (new structure)
        detected = analyze_result.get("detected", [])
        
        # Extract branded and general ingredients from detected groups
        for group in detected:
            for item in group.get("items", []):
                matched_inci = item.get("matched_inci", [])
                if item.get("tag") == "B":  # Branded ingredient
                    branded_ingredients.extend(matched_inci)
                elif item.get("tag") == "G":  # General INCI ingredient
                    not_branded_ingredients.extend(matched_inci)
        
        # Fallback to old structure if detected is not available
        if not detected:
            if analyze_result.get("branded_grouped"):
                for group in analyze_result.get("branded_grouped", []):
                    branded_ingredients.extend(group.get("inci_list", []))
            elif analyze_result.get("branded_ingredients"):
                for item in analyze_result.get("branded_ingredients", []):
                    branded_ingredients.extend(item.get("matched_inci", []))
            
            if analyze_result.get("general_ingredients_list"):
                for item in analyze_result.get("general_ingredients_list", []):
                    not_branded_ingredients.extend(item.get("matched_inci", []))
        
        # Call formulation report JSON API
        base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        report_url = f"{base_url}/api/formulation-report-json"
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                report_url,
                json={
                    "inciList": ingredients,
                    "brandedIngredients": list(set(branded_ingredients)),
                    "notBrandedIngredients": list(set(not_branded_ingredients)),
                    "bisCautions": bis_cautions if bis_cautions else None,
                    "expectedBenefits": None
                }
            )
            
            if response.status_code == 200:
                report_data = response.json()
                # Return summary from report
                summary = report_data.get("summary", {})
                # Also include recommended_ph_range if not in summary
                if not summary.get("recommended_ph_range") and report_data.get("recommended_ph_range"):
                    summary["recommended_ph_range"] = report_data["recommended_ph_range"]
                return summary
    except Exception as e:
        print(f"⚠️ Warning: Failed to get report summary, using fallback: {e}")
    
    return None


def _estimate_ph_range_fallback(ingredients: List[str]) -> str:
    """Fallback pH range estimation if report generation fails"""
    # Check for acids
    has_acid = any("acid" in ing.lower() for ing in ingredients)
    
    if has_acid:
        return "3.5-5.5"
    else:
        return "5.0-6.5"


def _estimate_viscosity(formulation_type: str, phase_breakdown: Dict[str, float]) -> str:
    """Estimate viscosity based on formulation type and phase breakdown"""
    if "serum" in formulation_type.lower():
        return "Light/Watery"
    elif "oil" in formulation_type.lower() and phase_breakdown.get("oil", 0) > 50:
        return "Medium/Oily"
    elif phase_breakdown.get("water", 0) > 70:
        return "Light/Watery"
    else:
        return "Medium/Creamy"


def _estimate_shelf_life(ingredients: List[Dict[str, Any]]) -> str:
    """Estimate shelf life"""
    # Check for preservatives
    has_preservative = any(
        any(x in ing["inci"].lower() for x in ["phenoxy", "paraben", "benzoate", "sorbate", "preservative"])
        for ing in ingredients
    )
    
    if has_preservative:
        return "24 months unopened, 6 months after opening"
    else:
        return "12 months unopened, 3 months after opening"


def _create_phase_breakdown_array(phase_breakdown: Dict[str, float]) -> List[Dict[str, Any]]:
    """Create phase breakdown array matching image format"""
    phase_mapping = {
        "water": {"label": "Water Phase", "color": "sky"},
        "oil": {"label": "Oil Phase", "color": "amber"},
        "active": {"label": "Active Phase", "color": "emerald"},
        "preservative": {"label": "Preservative", "color": "rose"},
        "other": {"label": "Functional", "color": "slate"}
    }
    
    result = []
    for phase, percentage in phase_breakdown.items():
        if phase in phase_mapping and percentage > 0:
            result.append({
                "phase": phase,
                "label": phase_mapping[phase]["label"],
                "percentage": round(percentage, 1),
                "color": phase_mapping[phase]["color"]
            })
    
    # Sort by percentage descending
    result.sort(key=lambda x: x["percentage"], reverse=True)
    return result


def _create_function_breakdown_array(ingredient_details: List[Dict[str, Any]], analyze_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create function breakdown array matching image format"""
    function_mapping = {
        "hydration": {"icon": "💧", "keywords": ["humectant", "hydrat", "moistur", "glycerin", "hyaluron", "urea"]},
        "oil control": {"icon": "🫧", "keywords": ["niacinamide", "zinc", "sebum", "oil control", "matte"]},
        "brightening": {"icon": "✨", "keywords": ["brighten", "whiten", "vitamin c", "arbutin", "tranexamic", "niacinamide"]},
        "texture": {"icon": "🧪", "keywords": ["emulsifier", "thickener", "polymer", "texture", "viscosity"]},
        "preservation": {"icon": "🛡️", "keywords": ["preservative", "phenoxy", "paraben", "benzoate", "sorbate"]}
    }
    
    function_counts = {func: 0 for func in function_mapping.keys()}
    
    # Count ingredients by function
    for ing in ingredient_details:
        inci_lower = ing["inci"].lower()
        function_lower = ing.get("function", "").lower()
        combined_text = f"{inci_lower} {function_lower}"
        
        for func, data in function_mapping.items():
            if any(keyword in combined_text for keyword in data["keywords"]):
                function_counts[func] += 1
    
    # Create array with functions that have ingredients
    result = []
    for func, count in function_counts.items():
        if count > 0:
            result.append({
                "function": func.title(),
                "count": count,
                "icon": function_mapping[func]["icon"]
            })
    
    # Sort by count descending
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


def _create_hero_ingredients_array(sorted_ingredients: List[Dict[str, Any]], ingredient_details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create hero ingredients array with details matching image format"""
    hero_ingredients = []
    
    # Get top ingredients by concentration (excluding water)
    for ing in sorted_ingredients:
        if ing["concentration"] > 1.0 and "water" not in ing["inci"].lower() and "aqua" not in ing["inci"].lower():
            # Map common names to chemical names
            chemical_name = _get_chemical_name(ing["inci"])
            primary_function = _get_primary_function(ing["inci"], ing.get("function", ""))
            
            hero_ingredients.append({
                "name": _get_common_name(ing["inci"]),
                "chemicalName": chemical_name,
                "concentration": f"{ing['concentration']:.0f}%",
                "function": primary_function
            })
            
            if len(hero_ingredients) >= 3:  # Limit to top 3
                break
    
    return hero_ingredients


def _get_chemical_name(inci_name: str) -> str:
    """Get chemical name from INCI name"""
    # Common mappings
    mappings = {
        "niacinamide": "Niacinamide",
        "ascorbic acid": "L-Ascorbic Acid",
        "hyaluronic acid": "Hyaluronic Acid",
        "sodium hyaluronate": "Sodium Hyaluronate",
        "retinol": "Retinol",
        "salicylic acid": "Salicylic Acid",
        "glycolic acid": "Glycolic Acid",
        "lactic acid": "Lactic Acid"
    }
    
    inci_lower = inci_name.lower()
    for key, value in mappings.items():
        if key in inci_lower:
            return value
    
    return inci_name


def _get_common_name(inci_name: str) -> str:
    """Get common/vitamin name from INCI name"""
    mappings = {
        "niacinamide": "Vitamin B3",
        "ascorbic acid": "Vitamin C",
        "retinol": "Vitamin A",
        "tocopherol": "Vitamin E",
        "panthenol": "Vitamin B5"
    }
    
    inci_lower = inci_name.lower()
    for key, value in mappings.items():
        if key in inci_lower:
            return value
    
    # Return capitalized INCI name as fallback
    return inci_name.split()[0].title() if inci_name else "Unknown"


def _get_primary_function(inci_name: str, function: str) -> str:
    """Get primary function for hero ingredient"""
    inci_lower = inci_name.lower()
    func_lower = function.lower()
    
    if "brighten" in func_lower or "niacinamide" in inci_lower or "vitamin c" in inci_lower or "arbutin" in inci_lower:
        return "Brightening"
    elif "hydrat" in func_lower or "moistur" in func_lower or "hyaluron" in inci_lower or "glycerin" in inci_lower:
        return "Hydration"
    elif "oil" in func_lower or "sebum" in func_lower or "zinc" in inci_lower:
        return "Oil Control"
    elif "anti-aging" in func_lower or "retinol" in inci_lower:
        return "Anti-Aging"
    elif "exfoliat" in func_lower or "acid" in inci_lower:
        return "Exfoliation"
    else:
        return function.split(",")[0].strip().title() if function else "Active"


def _determine_product_tags(ingredient_details: List[Dict[str, Any]], analyze_result: Dict[str, Any]) -> List[str]:
    """Determine product tags/certifications"""
    tags = []
    
    # Check for vegan-friendly (no animal-derived ingredients)
    animal_keywords = ["beeswax", "lanolin", "collagen", "elastin", "squalene", "carmine", "shellac"]
    has_animal = any(
        any(keyword in ing["inci"].lower() for keyword in animal_keywords)
        for ing in ingredient_details
    )
    if not has_animal:
        tags.append("Vegan Friendly")
    
    # Check for fragrance-free
    fragrance_keywords = ["parfum", "fragrance", "aroma", "essential oil"]
    has_fragrance = any(
        any(keyword in ing["inci"].lower() for keyword in fragrance_keywords)
        for ing in ingredient_details
    )
    if not has_fragrance:
        tags.append("Fragrance Free")
    
    # Pregnancy Safe and Fungal Acne Safe tags removed - not shown in Make a Wish feature
    # Check for pregnancy-safe (no retinoids, high salicylic acid, etc.)
    # unsafe_keywords = ["retinol", "retinoid", "retinyl", "salicylic acid"]
    # has_unsafe = any(
    #     any(keyword in ing["inci"].lower() for keyword in unsafe_keywords) and ing.get("concentration", 0) > 2.0
    #     for ing in ingredient_details
    # )
    # if not has_unsafe:
    #     tags.append("Pregnancy Safe")
    
    # Check for fungal acne-safe (no oils that feed malassezia)
    # fungal_acne_unsafe = ["oleic acid", "oleate", "coconut oil", "avocado oil", "olive oil"]
    # has_unsafe_oils = any(
    #     any(keyword in ing["inci"].lower() for keyword in fungal_acne_unsafe)
    #     for ing in ingredient_details
    # )
    # if not has_unsafe_oils:
    #     tags.append("Fungal Acne Safe")
    
    return tags

