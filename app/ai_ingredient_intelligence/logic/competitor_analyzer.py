"""
Competitor Analysis logic for Inspiration Boards
Only Overview and Ingredients analysis
"""
from typing import List, Dict, Any, Optional
from bson import ObjectId
from app.ai_ingredient_intelligence.db.collections import inspiration_products_col


async def analyze_competitors(product_ids: List[str], analysis_type: str = "overview") -> Dict[str, Any]:
    """
    Analyze competitor products
    
    Args:
        product_ids: List of product IDs to analyze (minimum 2)
        analysis_type: 'overview' or 'ingredients'
    
    Returns:
        Analysis results
    """
    if len(product_ids) < 2:
        return {
            "error": "At least 2 products required for analysis"
        }
    
    # Get all products
    products = []
    for product_id in product_ids:
        try:
            product_obj_id = ObjectId(product_id)
            product = await inspiration_products_col.find_one({"_id": product_obj_id})
            if product and product.get("decoded") and product.get("decoded_data"):
                products.append(product)
        except:
            continue
    
    if len(products) < 2:
        return {
            "error": "At least 2 decoded products required for analysis"
        }
    
    # Generate analysis based on type
    if analysis_type == "overview":
        return await _generate_overview_analysis(products)
    elif analysis_type == "ingredients":
        return await _generate_ingredients_analysis(products)
    else:
        return {
            "error": f"Invalid analysis_type: {analysis_type}. Use 'overview' or 'ingredients'"
        }


async def _generate_overview_analysis(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate overview analysis"""
    # Calculate price range
    prices = [p.get("price", 0) for p in products]
    price_range = {
        "min": min(prices),
        "max": max(prices),
        "avg": sum(prices) / len(prices)
    }
    
    # Calculate cost range
    costs = []
    for p in products:
        decoded_data = p.get("decoded_data", {})
        if decoded_data:
            costs.append(decoded_data.get("estimated_cost", 0))
    
    cost_range = {
        "min": min(costs) if costs else 0,
        "max": max(costs) if costs else 0,
        "avg": sum(costs) / len(costs) if costs else 0
    }
    
    # Get all unique ingredients
    all_ingredients = set()
    for p in products:
        decoded_data = p.get("decoded_data", {})
        if decoded_data:
            ingredients = decoded_data.get("ingredients", [])
            for ing in ingredients:
                all_ingredients.add(ing.get("inci", ""))
    
    # Find common ingredients
    common_ingredients = set()
    if products:
        first_product = products[0]
        first_decoded = first_product.get("decoded_data", {})
        first_ingredients = {ing.get("inci", "") for ing in first_decoded.get("ingredients", [])}
        
        common_ingredients = first_ingredients.copy()
        for p in products[1:]:
            decoded_data = p.get("decoded_data", {})
            if decoded_data:
                ingredients = {ing.get("inci", "") for ing in decoded_data.get("ingredients", [])}
                common_ingredients = common_ingredients.intersection(ingredients)
    
    # Side-by-side comparison
    side_by_side = []
    
    # Price metrics
    side_by_side.append({
        "metric": "Price",
        "values": {str(p["_id"]): f"₹{p.get('price', 0)}" for p in products}
    })
    
    side_by_side.append({
        "metric": "Price/ml",
        "values": {str(p["_id"]): f"₹{p.get('price_per_ml', 0):.2f}" for p in products}
    })
    
    side_by_side.append({
        "metric": "Rating",
        "values": {str(p["_id"]): f"⭐ {p.get('rating', 0)}" if p.get('rating') else "N/A" for p in products}
    })
    
    side_by_side.append({
        "metric": "Reviews",
        "values": {str(p["_id"]): f"{(p.get('reviews', 0) / 1000):.1f}K" if p.get('reviews') else "N/A" for p in products}
    })
    
    # Decoded data metrics
    for p in products:
        decoded_data = p.get("decoded_data", {})
        if decoded_data:
            side_by_side.append({
                "metric": "Est. Cost/100g",
                "values": {str(p["_id"]): f"₹{decoded_data.get('estimated_cost', 0)}"}
            })
            break
    
    side_by_side.append({
        "metric": "Ingredients",
        "values": {str(p["_id"]): p.get("decoded_data", {}).get("ingredient_count", 0) for p in products}
    })
    
    side_by_side.append({
        "metric": "Type",
        "values": {str(p["_id"]): p.get("decoded_data", {}).get("formulation_type", "N/A").split()[0] for p in products}
    })
    
    side_by_side.append({
        "metric": "Complexity",
        "values": {str(p["_id"]): p.get("decoded_data", {}).get("manufacturing_complexity", "N/A") for p in products}
    })
    
    # Price comparison for visualization
    price_comparison = []
    if price_range["max"] > price_range["min"]:
        for p in products:
            price = p.get("price", 0)
            width = ((price - price_range["min"]) / (price_range["max"] - price_range["min"])) * 100
            price_comparison.append({
                "product_id": str(p["_id"]),
                "product_name": p.get("name", "Unknown"),
                "brand": p.get("brand", "Unknown"),
                "price": price,
                "price_per_ml": p.get("price_per_ml", 0),
                "width_percentage": max(10, width)  # Minimum 10% for visibility
            })
    else:
        # All same price
        for p in products:
            price_comparison.append({
                "product_id": str(p["_id"]),
                "product_name": p.get("name", "Unknown"),
                "brand": p.get("brand", "Unknown"),
                "price": p.get("price", 0),
                "price_per_ml": p.get("price_per_ml", 0),
                "width_percentage": 50
            })
    
    return {
        "analysis_type": "overview",
        "products_analyzed": len(products),
        "overview": {
            "products_analyzed": len(products),
            "price_range": price_range,
            "cost_range": cost_range,
            "common_ingredients_count": len(common_ingredients),
            "total_unique_ingredients": len(all_ingredients),
            "side_by_side": side_by_side,
            "price_comparison": price_comparison
        }
    }


async def _generate_ingredients_analysis(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate ingredients analysis"""
    # Get all ingredients from all products
    all_ingredients_map = {}  # inci -> set of product_ids
    product_ingredients = {}  # product_id -> list of ingredients
    
    for p in products:
        product_id = str(p["_id"])
        decoded_data = p.get("decoded_data", {})
        if decoded_data:
            ingredients = decoded_data.get("ingredients", [])
            product_ingredients[product_id] = ingredients
            
            for ing in ingredients:
                inci = ing.get("inci", "")
                if inci:
                    if inci not in all_ingredients_map:
                        all_ingredients_map[inci] = set()
                    all_ingredients_map[inci].add(product_id)
    
    # Find common ingredients (in all products)
    common_ingredients = []
    for inci, product_set in all_ingredients_map.items():
        if len(product_set) == len(products):
            common_ingredients.append(inci)
    
    # Find unique ingredients per product
    unique_ingredients = []
    for p in products:
        product_id = str(p["_id"])
        decoded_data = p.get("decoded_data", {})
        if decoded_data:
            ingredients = decoded_data.get("ingredients", [])
            unique_incs = []
            
            for ing in ingredients:
                inci = ing.get("inci", "")
                if inci:
                    # Check if this ingredient is in other products
                    is_unique = True
                    for other_p in products:
                        if str(other_p["_id"]) != product_id:
                            other_decoded = other_p.get("decoded_data", {})
                            if other_decoded:
                                other_ingredients = other_decoded.get("ingredients", [])
                                if any(oi.get("inci", "") == inci for oi in other_ingredients):
                                    is_unique = False
                                    break
                    
                    if is_unique:
                        unique_incs.append({
                            "name": ing.get("name", ""),
                            "inci": inci,
                            "concentration": ing.get("concentration", 0)
                        })
            
            unique_ingredients.append({
                "product_id": product_id,
                "product_name": p.get("name", "Unknown"),
                "brand": p.get("brand", "Unknown"),
                "unique_ingredients": unique_incs
            })
    
    # Hero ingredients comparison
    hero_ingredients_comparison = {}
    for p in products:
        product_id = str(p["_id"])
        decoded_data = p.get("decoded_data", {})
        if decoded_data:
            hero_ingredients_comparison[product_id] = decoded_data.get("hero_ingredients", [])
    
    return {
        "analysis_type": "ingredients",
        "products_analyzed": len(products),
        "ingredients": {
            "common_ingredients": {
                "common_ingredients": common_ingredients,
                "common_count": len(common_ingredients),
                "total_unique_ingredients": len(all_ingredients_map)
            },
            "unique_ingredients": unique_ingredients,
            "hero_ingredients_comparison": hero_ingredients_comparison
        }
    }

