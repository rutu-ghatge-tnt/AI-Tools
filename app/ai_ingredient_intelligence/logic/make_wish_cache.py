"""
Make A Wish Cache - Fallback responses for AI timeouts
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Cache for AI responses
AI_RESPONSE_CACHE = {}

def get_cached_parse_wish(wish_text: str) -> Optional[Dict[str, Any]]:
    """Get cached parse wish response"""
    cache_key = f"parse_wish_{hash(wish_text)}"
    
    if cache_key in AI_RESPONSE_CACHE:
        cached = AI_RESPONSE_CACHE[cache_key]
        if datetime.now() - cached['timestamp'] < timedelta(hours=1):
            return cached['response']
    
    return None

def cache_parse_wish(wish_text: str, response: Dict[str, Any]):
    """Cache parse wish response"""
    cache_key = f"parse_wish_{hash(wish_text)}"
    AI_RESPONSE_CACHE[cache_key] = {
        'response': response,
        'timestamp': datetime.now()
    }

def get_fallback_parse_wish(wish_text: str) -> Dict[str, Any]:
    """Get fallback parse wish response when AI times out"""
    # Basic fallback based on common patterns
    response = {
        "category": "skincare",
        "product_type": {
            "id": "serum",
            "name": "Serum",
            "icon": "flask",
            "confidence": 0.8
        },
        "detected_ingredients": [],
        "detected_benefits": [],
        "detected_exclusions": [],
        "detected_skin_types": [],
        "detected_hair_concerns": [],
        "auto_texture": {
            "id": "watery",
            "label": "Light & Fast-Absorbing",
            "auto_selected": True
        },
        "needs_clarification": [],
        "compatibility_issues": []
    }
    
    # Extract basic information from wish text
    wish_lower = wish_text.lower()
    
    # Detect product type
    if "serum" in wish_lower:
        response["product_type"]["id"] = "serum"
        response["product_type"]["name"] = "Serum"
        response["auto_texture"]["label"] = "Light & Fast-Absorbing"
    elif "cream" in wish_lower or "moisturizer" in wish_lower:
        response["product_type"]["id"] = "cream"
        response["product_type"]["name"] = "Cream"
        response["auto_texture"]["label"] = "Rich & Nourishing"
    elif "cleanser" in wish_lower or "wash" in wish_lower:
        response["product_type"]["id"] = "cleanser"
        response["product_type"]["name"] = "Cleanser"
        response["auto_texture"]["label"] = "Gentle & Effective"
    
    # Detect common ingredients
    ingredients = []
    if "vitamin c" in wish_lower or "ascorbic" in wish_lower:
        ingredients.append({
            "name": "Vitamin C",
            "confidence": 0.9,
            "has_alternatives": True
        })
    if "niacinamide" in wish_lower:
        ingredients.append({
            "name": "Niacinamide",
            "confidence": 0.85,
            "has_alternatives": True
        })
    if "hyaluronic" in wish_lower:
        ingredients.append({
            "name": "Hyaluronic Acid",
            "confidence": 0.9,
            "has_alternatives": True
        })
    if "retinol" in wish_lower:
        ingredients.append({
            "name": "Retinol",
            "confidence": 0.9,
            "has_alternatives": True
        })
    
    response["detected_ingredients"] = ingredients
    
    # Detect benefits
    benefits = []
    if "brighten" in wish_lower or "glow" in wish_lower:
        benefits.append("brightening")
    if "hydrat" in wish_lower or "moistur" in wish_lower:
        benefits.append("hydration")
    if "anti-aging" in wish_lower or "wrinkle" in wish_lower:
        benefits.append("anti-aging")
    if "acne" in wish_lower or "blemish" in wish_lower:
        benefits.append("acne control")
    if "barrier" in wish_lower or "repair" in wish_lower:
        benefits.append("barrier repair")
    
    response["detected_benefits"] = benefits
    
    # Detect exclusions
    exclusions = []
    if "paraben" in wish_lower:
        exclusions.append("paraben-free")
    if "fragrance" in wish_lower or "scent" in wish_lower:
        exclusions.append("fragrance-free")
    if "sulfate" in wish_lower:
        exclusions.append("sulfate-free")
    if "silicone" in wish_lower:
        exclusions.append("silicone-free")
    
    response["detected_exclusions"] = exclusions
    
    # Detect skin types
    skin_types = []
    if "oily" in wish_lower:
        skin_types.append("oily")
    if "dry" in wish_lower:
        skin_types.append("dry")
    if "sensitive" in wish_lower:
        skin_types.append("sensitive")
    if "combination" in wish_lower:
        skin_types.append("combination")
    
    response["detected_skin_types"] = skin_types
    
    # Add compatibility issues for known conflicts
    compatibility_issues = []
    ingredient_names = [ing["name"].lower() for ing in ingredients]
    
    if "vitamin c" in ingredient_names and "niacinamide" in ingredient_names:
        compatibility_issues.append({
            "severity": "warning",
            "title": "pH Sensitivity",
            "problem": "Vitamin C works best at low pH, may affect niacinamide",
            "solution": "Use them in separate steps or adjust pH carefully",
            "ingredients_involved": ["Vitamin C", "Niacinamide"]
        })
    
    if "vitamin c" in ingredient_names and "retinol" in ingredient_names:
        compatibility_issues.append({
            "severity": "warning",
            "title": "Irritation Risk",
            "problem": "Both are strong actives, may cause irritation when used together",
            "solution": "Alternate use times or use lower concentrations",
            "ingredients_involved": ["Vitamin C", "Retinol"]
        })
    
    response["compatibility_issues"] = compatibility_issues
    
    return response

def get_fallback_generate_formula(parsed_data: Dict[str, Any], complexity: str) -> Dict[str, Any]:
    """Get fallback generate formula response"""
    formulas = {
        "minimalist": {
            "name": f"{parsed_data['product_type']['name']} (Minimalist)",
            "complexity": "minimalist",
            "total_ingredients": 5,
            "total_hero_actives": 1,
            "formula_id": f"minimalist-{datetime.now().strftime('%Y%m%d')}-001",
            "formula": {
                "name": f"{parsed_data['product_type']['name']} (Minimalist)",
                "complexity": "minimalist",
                "total_percentage": 100.0,
                "target_ph": {"min": 5.5, "max": 6.5},
                "texture_achieved": "Light & Fast-Absorbing"
            },
            "ingredients": [
                {
                    "id": "water",
                    "name": "Water",
                    "inci": "Aqua",
                    "percentage": "75.00%",
                    "phase": "A",
                    "function": "Solvent",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "glycerin",
                    "name": "Glycerin",
                    "inci": "Glycerin",
                    "percentage": "5.00%",
                    "phase": "A",
                    "function": "Humectant",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "vitamin_c",
                    "name": "Vitamin C",
                    "inci": "Ascorbic Acid",
                    "percentage": "10.00%",
                    "phase": "C",
                    "function": "Antioxidant",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "preservative",
                    "name": "Preservative",
                    "inci": "Phenoxyethanol",
                    "percentage": "1.00%",
                    "phase": "C",
                    "function": "Preservative",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "ph_adjuster",
                    "name": "pH Adjuster",
                    "inci": "Sodium Hydroxide",
                    "percentage": "0.20%",
                    "phase": "C",
                    "function": "pH Adjustment",
                    "is_hero": False,
                    "is_base": True
                }
            ],
            "insights": {
                "why_these_ingredients": [
                    {
                        "ingredient_name": "Vitamin C",
                        "icon": "flask",
                        "explanation": "Powerful antioxidant for brightening",
                        "complexity_reason": "Essential active for minimalist formula"
                    }
                ],
                "challenges": [
                    {
                        "title": "Stability",
                        "icon": "alert-triangle",
                        "description": "Vitamin C can oxidize quickly",
                        "tip": "Store in dark, cool place",
                        "severity": "attention"
                    }
                ],
                "marketing_tips": [
                    {
                        "title": "Positioning",
                        "icon": "lightbulb",
                        "content": "Pure and simple formulation",
                        "category": "positioning"
                    }
                ],
                "faq": [
                    {
                        "question": "How often should I use this?",
                        "answer": "Use once daily, preferably in the morning"
                    }
                ]
            }
        },
        "classic": {
            "name": f"{parsed_data['product_type']['name']} (Classic)",
            "complexity": "classic",
            "total_ingredients": 8,
            "total_hero_actives": 2,
            "formula_id": f"classic-{datetime.now().strftime('%Y%m%d')}-001",
            "formula": {
                "name": f"{parsed_data['product_type']['name']} (Classic)",
                "complexity": "classic",
                "total_percentage": 100.0,
                "target_ph": {"min": 5.5, "max": 6.5},
                "texture_achieved": "Balanced"
            },
            "ingredients": [
                {
                    "id": "water",
                    "name": "Water",
                    "inci": "Aqua",
                    "percentage": "70.00%",
                    "phase": "A",
                    "function": "Solvent",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "glycerin",
                    "name": "Glycerin",
                    "inci": "Glycerin",
                    "percentage": "5.00%",
                    "phase": "A",
                    "function": "Humectant",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "niacinamide",
                    "name": "Niacinamide",
                    "inci": "Niacinamide",
                    "percentage": "4.00%",
                    "phase": "A",
                    "function": "Skin Brightening",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "hyaluronic_acid",
                    "name": "Hyaluronic Acid",
                    "inci": "Sodium Hyaluronate",
                    "percentage": "1.00%",
                    "phase": "A",
                    "function": "Hydration",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "vitamin_c",
                    "name": "Vitamin C",
                    "inci": "Ascorbic Acid",
                    "percentage": "8.00%",
                    "phase": "C",
                    "function": "Antioxidant",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "emulsifier",
                    "name": "Emulsifier",
                    "inci": "Cetearyl Alcohol",
                    "percentage": "3.00%",
                    "phase": "B",
                    "function": "Emulsifier",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "preservative",
                    "name": "Preservative",
                    "inci": "Phenoxyethanol",
                    "percentage": "1.00%",
                    "phase": "C",
                    "function": "Preservative",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "ph_adjuster",
                    "name": "pH Adjuster",
                    "inci": "Sodium Hydroxide",
                    "percentage": "0.20%",
                    "phase": "C",
                    "function": "pH Adjustment",
                    "is_hero": False,
                    "is_base": True
                }
            ],
            "insights": {
                "why_these_ingredients": [
                    {
                        "ingredient_name": "Vitamin C",
                        "icon": "flask",
                        "explanation": "Powerful antioxidant for brightening",
                        "complexity_reason": "Key active for classic formula"
                    },
                    {
                        "ingredient_name": "Niacinamide",
                        "icon": "flask",
                        "explanation": "Multi-tasking vitamin for skin health",
                        "complexity_reason": "Complements Vitamin C for classic formula"
                    }
                ],
                "challenges": [
                    {
                        "title": "pH Balance",
                        "icon": "alert-triangle",
                        "description": "Multiple actives require careful pH balancing",
                        "tip": "Test pH after adding all ingredients",
                        "severity": "attention"
                    }
                ],
                "marketing_tips": [
                    {
                        "title": "Positioning",
                        "icon": "lightbulb",
                        "content": "Balanced formula for everyday use",
                        "category": "positioning"
                    }
                ],
                "faq": [
                    {
                        "question": "Can I use this with other products?",
                        "answer": "Yes, but avoid using with other strong actives at the same time"
                    }
                ]
            }
        },
        "luxe": {
            "name": f"{parsed_data['product_type']['name']} (Luxe)",
            "complexity": "luxe",
            "total_ingredients": 12,
            "total_hero_actives": 3,
            "formula_id": f"luxe-{datetime.now().strftime('%Y%m%d')}-001",
            "formula": {
                "name": f"{parsed_data['product_type']['name']} (Luxe)",
                "complexity": "luxe",
                "total_percentage": 100.0,
                "target_ph": {"min": 5.5, "max": 6.5},
                "texture_achieved": "Luxurious"
            },
            "ingredients": [
                {
                    "id": "water",
                    "name": "Water",
                    "inci": "Aqua",
                    "percentage": "65.00%",
                    "phase": "A",
                    "function": "Solvent",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "glycerin",
                    "name": "Glycerin",
                    "inci": "Glycerin",
                    "percentage": "4.00%",
                    "phase": "A",
                    "function": "Humectant",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "sodium_hyaluronate",
                    "name": "Sodium Hyaluronate",
                    "inci": "Sodium Hyaluronate",
                    "percentage": "0.10%",
                    "phase": "A",
                    "function": "Hydration",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "peptides",
                    "name": "Peptides",
                    "inci": "Palmitoyl Pentapeptide-4",
                    "percentage": "2.00%",
                    "phase": "A",
                    "function": "Anti-aging",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "niacinamide",
                    "name": "Niacinamide",
                    "inci": "Niacinamide",
                    "percentage": "4.00%",
                    "phase": "A",
                    "function": "Skin Brightening",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "vitamin_e",
                    "name": "Vitamin E",
                    "inci": "Tocopherol",
                    "percentage": "1.00%",
                    "phase": "B",
                    "function": "Antioxidant",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "squalane",
                    "name": "Squalane",
                    "inci": "Squalane",
                    "percentage": "3.00%",
                    "phase": "B",
                    "function": "Emollient",
                    "is_hero": False,
                    "is_base": False
                },
                {
                    "id": "vitamin_c",
                    "name": "Vitamin C",
                    "inci": "Ascorbic Acid",
                    "percentage": "10.00%",
                    "phase": "C",
                    "function": "Antioxidant",
                    "is_hero": True,
                    "is_base": False
                },
                {
                    "id": "ferulic_acid",
                    "name": "Ferulic Acid",
                    "inci": "Ferulic Acid",
                    "percentage": "0.50%",
                    "phase": "C",
                    "function": "Antioxidant Booster",
                    "is_hero": False,
                    "is_base": False
                },
                {
                    "id": "emulsifier",
                    "name": "Emulsifier",
                    "inci": "Cetearyl Alcohol",
                    "percentage": "3.00%",
                    "phase": "B",
                    "function": "Emulsifier",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "preservative",
                    "name": "Preservative",
                    "inci": "Phenoxyethanol",
                    "percentage": "1.00%",
                    "phase": "C",
                    "function": "Preservative",
                    "is_hero": False,
                    "is_base": True
                },
                {
                    "id": "ph_adjuster",
                    "name": "pH Adjuster",
                    "inci": "Sodium Hydroxide",
                    "percentage": "0.20%",
                    "phase": "C",
                    "function": "pH Adjustment",
                    "is_hero": False,
                    "is_base": True
                }
            ],
            "insights": {
                "why_these_ingredients": [
                    {
                        "ingredient_name": "Vitamin C",
                        "icon": "flask",
                        "explanation": "Premium antioxidant with Ferulic Acid booster",
                        "complexity_reason": "Luxury formulation with multiple antioxidants"
                    },
                    {
                        "ingredient_name": "Peptides",
                        "icon": "flask",
                        "explanation": "Advanced anti-aging ingredient",
                        "complexity_reason": "Premium active for luxe formula"
                    }
                ],
                "challenges": [
                    {
                        "title": "Cost",
                        "icon": "alert-triangle",
                        "description": "Premium ingredients increase cost",
                        "tip": "Position as luxury product",
                        "severity": "info"
                    }
                ],
                "marketing_tips": [
                    {
                        "title": "Positioning",
                        "icon": "lightbulb",
                        "content": "Premium formulation with advanced actives",
                        "category": "positioning"
                    }
                ],
                "faq": [
                    {
                        "question": "Is this worth the extra cost?",
                        "answer": "Yes, the combination of premium ingredients provides superior results"
                    }
                ]
            }
        }
    }
    
    return formulas.get(complexity, formulas["classic"])
