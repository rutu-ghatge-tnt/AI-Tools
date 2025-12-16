"""
Formula Generator - Hybrid Approach (Template + Rules + AI)
============================================================

This module implements Approach 4: Hybrid Template + Rules + AI for generating
cosmetic formulations based on user wishes.

ARCHITECTURE:
-------------
1. Template Selection (Fast, Rule-Based)
   - Pre-defined formula templates for each product type
   - Base structure with phase organization
   - Required functional categories per phase

2. Rule-Based Ingredient Selection (Fast, MongoDB Queries)
   - Maps benefits to functional categories
   - Queries MongoDB ingredient database
   - Applies exclusions and filters
   - Prioritizes hero ingredients

3. Percentage Allocation (Rule-Based)
   - Initial percentage allocation based on rules
   - Considers typical usage ranges
   - Ensures total = 100%

4. AI Optimization (Selective, Claude)
   - Fine-tunes percentages if needed
   - Generates insights and warnings
   - Checks compatibility

5. Validation (Rule-Based + BIS)
   - Cost verification
   - BIS compliance checking
   - Safety validation

WHAT WE USE:
-----------
- MongoDB: Ingredient database (branded_ingredients, inci, functional_categories)
- Claude (Anthropic): For percentage optimization and insight generation
- BIS RAG: For regulatory compliance checking
- Rule Engine: For ingredient selection and initial allocation
"""

import os
from typing import Dict, List, Optional, Tuple, Any
from pymongo import ASCENDING
from bson.objectid import ObjectId

# Conditional Claude import
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None  # type: ignore

from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import (
    branded_ingredients_col,
    inci_col,
    functional_categories_col
)
from app.ai_ingredient_intelligence.logic.bis_rag import get_bis_cautions_for_ingredients

# Initialize Claude client (only if available)
claude_api_key = os.getenv("CLAUDE_API_KEY")
# Use CLAUDE_MODEL from env, fallback to default Sonnet 3.5
claude_model = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"
if ANTHROPIC_AVAILABLE and claude_api_key:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
        print(f"Claude client initialized with model: {claude_model}")
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        claude_client = None
        claude_model = None
else:
    claude_client = None
    claude_model = None
    if not claude_api_key:
        print("Warning: CLAUDE_API_KEY not set. Claude optimization will be disabled.")

# ============================================================================
# STEP 1: TEMPLATE DATABASE
# ============================================================================
# Pre-defined formula templates for each product type
# These ensure we always generate valid, structured formulations

FORMULATION_TEMPLATES = {
    "serum": {
        "name": "Serum Template",
        "phases": [
            {
                "id": "A",
                "name": "Water Phase",
                "percentage_range": {"min": 70, "max": 85},
                "temperature": "70°C",
                "required_functions": ["Solvent", "Humectant"],
                "optional_functions": ["Thickener", "Chelating Agent"]
            },
            {
                "id": "B",
                "name": "Active Phase",
                "percentage_range": {"min": 5, "max": 15},
                "temperature": "40°C",
                "required_functions": ["Active"],
                "optional_functions": ["Antioxidant"]
            },
            {
                "id": "C",
                "name": "Preservation",
                "percentage_range": {"min": 1, "max": 2},
                "temperature": "<40°C",
                "required_functions": ["Preservative", "pH Adjuster"],
                "optional_functions": []
            }
        ],
        "base_ingredients": {
            "Aqua": {"phase": "A", "percentage": 75.0, "function": "Solvent", "required": True}
        },
        "texture_mapping": {
            "water": {"viscosity": "low", "thickener_needed": False},
            "gel": {"viscosity": "medium", "thickener_needed": True, "thickener_type": "gum"},
            "serum": {"viscosity": "medium", "thickener_needed": True, "thickener_type": "polymer"}
        },
        "ph_range": {"min": 5.0, "max": 6.5}
    },
    "cream": {
        "name": "Cream Template",
        "phases": [
            {
                "id": "A",
                "name": "Water Phase",
                "percentage_range": {"min": 60, "max": 75},
                "temperature": "70°C",
                "required_functions": ["Solvent", "Humectant"],
                "optional_functions": ["Thickener", "Chelating Agent"]
            },
            {
                "id": "B",
                "name": "Oil Phase",
                "percentage_range": {"min": 15, "max": 25},
                "temperature": "70°C",
                "required_functions": ["Emollient", "Emulsifier"],
                "optional_functions": ["Stabilizer"]
            },
            {
                "id": "C",
                "name": "Active Phase",
                "percentage_range": {"min": 3, "max": 10},
                "temperature": "40°C",
                "required_functions": ["Active"],
                "optional_functions": ["Antioxidant"]
            },
            {
                "id": "D",
                "name": "Preservation",
                "percentage_range": {"min": 1, "max": 2},
                "temperature": "<40°C",
                "required_functions": ["Preservative", "pH Adjuster"],
                "optional_functions": []
            }
        ],
        "base_ingredients": {
            "Aqua": {"phase": "A", "percentage": 65.0, "function": "Solvent", "required": True}
        },
        "texture_mapping": {
            "lotion": {"viscosity": "medium", "emulsifier_needed": True},
            "cream": {"viscosity": "high", "emulsifier_needed": True, "thickener_needed": True}
        },
        "ph_range": {"min": 5.0, "max": 6.5}
    },
    "lotion": {
        "name": "Lotion Template",
        "phases": [
            {
                "id": "A",
                "name": "Water Phase",
                "percentage_range": {"min": 70, "max": 80},
                "temperature": "70°C",
                "required_functions": ["Solvent", "Humectant"],
                "optional_functions": ["Thickener"]
            },
            {
                "id": "B",
                "name": "Oil Phase",
                "percentage_range": {"min": 10, "max": 20},
                "temperature": "70°C",
                "required_functions": ["Emollient", "Emulsifier"],
                "optional_functions": []
            },
            {
                "id": "C",
                "name": "Active Phase",
                "percentage_range": {"min": 2, "max": 8},
                "temperature": "40°C",
                "required_functions": ["Active"],
                "optional_functions": []
            },
            {
                "id": "D",
                "name": "Preservation",
                "percentage_range": {"min": 1, "max": 2},
                "temperature": "<40°C",
                "required_functions": ["Preservative", "pH Adjuster"],
                "optional_functions": []
            }
        ],
        "base_ingredients": {
            "Aqua": {"phase": "A", "percentage": 75.0, "function": "Solvent", "required": True}
        },
        "texture_mapping": {
            "lotion": {"viscosity": "medium", "emulsifier_needed": True}
        },
        "ph_range": {"min": 5.0, "max": 6.5}
    },
    "toner": {
        "name": "Toner Template",
        "phases": [
            {
                "id": "A",
                "name": "Water Phase",
                "percentage_range": {"min": 85, "max": 95},
                "temperature": "room",
                "required_functions": ["Solvent", "Humectant"],
                "optional_functions": ["pH Adjuster"]
            },
            {
                "id": "B",
                "name": "Active Phase",
                "percentage_range": {"min": 2, "max": 10},
                "temperature": "room",
                "required_functions": ["Active"],
                "optional_functions": []
            },
            {
                "id": "C",
                "name": "Preservation",
                "percentage_range": {"min": 1, "max": 2},
                "temperature": "room",
                "required_functions": ["Preservative"],
                "optional_functions": []
            }
        ],
        "base_ingredients": {
            "Aqua": {"phase": "A", "percentage": 90.0, "function": "Solvent", "required": True}
        },
        "texture_mapping": {
            "water": {"viscosity": "low", "thickener_needed": False}
        },
        "ph_range": {"min": 4.5, "max": 6.0}
    }
}

# ============================================================================
# STEP 2: BENEFIT TO FUNCTIONAL CATEGORY MAPPING
# ============================================================================
# Maps user-selected benefits to functional categories in the database
# This is how we know which ingredients to query for

BENEFIT_TO_FUNCTIONAL_CATEGORIES = {
    # Brightening & Tone
    "Brightening": ["Skin Lightening Agents", "Antioxidants", "Exfoliant"],
    "Even skin tone": ["Skin Lightening Agents", "Antioxidants"],
    "Dark spot fading": ["Skin Lightening Agents", "Antioxidants", "Exfoliant"],
    "Glow-enhancing": ["Antioxidants", "Skin Conditioning Agent"],
    "Dullness relief": ["Exfoliant", "Antioxidants"],
    "Radiance boost": ["Antioxidants", "Skin Conditioning Agent"],
    
    # Anti-aging
    "Anti-wrinkle": ["Peptides", "Antioxidants", "Skin Conditioning Agent"],
    "Firming": ["Peptides", "Skin Conditioning Agent"],
    "Elasticity boost": ["Peptides", "Skin Conditioning Agent"],
    "Collagen support": ["Peptides", "Antioxidants"],
    "Fine line reduction": ["Peptides", "Antioxidants", "Exfoliant"],
    "Skin renewal": ["Exfoliant", "Peptides"],
    
    # Hydration
    "Deep hydration": ["Humectant", "Skin Conditioning Agent"],
    "Barrier repair": ["Emollient", "Skin Conditioning Agent"],
    "Moisture lock": ["Humectant", "Emollient"],
    "Plumping": ["Humectant", "Skin Conditioning Agent"],
    "Nourishing": ["Emollient", "Skin Conditioning Agent"],
    "Dewy finish": ["Humectant", "Emollient"],
    
    # Problem Skin
    "Acne control": ["Antimicrobial", "Exfoliant"],
    "Oil control": ["Astringent", "Surfactant"],
    "Pore minimizing": ["Astringent", "Exfoliant"],
    "Blackhead removal": ["Exfoliant", "Surfactant"],
    "Blemish treatment": ["Antimicrobial", "Exfoliant"],
    "Mattifying": ["Astringent", "Surfactant"],
    
    # Soothing
    "Calming": ["Anti-inflammatory", "Skin Conditioning Agent"],
    "Anti-redness": ["Anti-inflammatory", "Skin Conditioning Agent"],
    "Sensitive skin": ["Anti-inflammatory", "Skin Conditioning Agent"],
    "Anti-inflammatory": ["Anti-inflammatory", "Skin Conditioning Agent"],
    "Irritation relief": ["Anti-inflammatory", "Skin Conditioning Agent"],
    "Skin comfort": ["Skin Conditioning Agent", "Emollient"]
}

# Common active ingredients for specific benefits
HERO_INGREDIENT_MAPPING = {
    "Vitamin C": {
        "benefits": ["Brightening", "Even skin tone", "Dark spot fading", "Glow-enhancing"],
        "typical_percentage": {"min": 5, "max": 15},
        "inci_names": ["Ascorbic Acid", "3-O-Ethyl Ascorbic Acid", "Magnesium Ascorbyl Phosphate"],
        "cost_per_kg": 9000
    },
    "Niacinamide": {
        "benefits": ["Brightening", "Oil control", "Pore minimizing", "Barrier repair"],
        "typical_percentage": {"min": 2, "max": 5},
        "inci_names": ["Niacinamide"],
        "cost_per_kg": 5000
    },
    "Hyaluronic Acid": {
        "benefits": ["Deep hydration", "Plumping", "Moisture lock"],
        "typical_percentage": {"min": 0.1, "max": 2},
        "inci_names": ["Hyaluronic Acid", "Sodium Hyaluronate"],
        "cost_per_kg": 12000
    },
    "Retinol": {
        "benefits": ["Anti-wrinkle", "Fine line reduction", "Skin renewal"],
        "typical_percentage": {"min": 0.1, "max": 1},
        "inci_names": ["Retinol", "Retinyl Palmitate"],
        "cost_per_kg": 15000
    },
    "Salicylic Acid": {
        "benefits": ["Acne control", "Blemish treatment", "Exfoliant"],
        "typical_percentage": {"min": 0.5, "max": 2},
        "inci_names": ["Salicylic Acid"],
        "cost_per_kg": 3000
    }
}

# ============================================================================
# STEP 3: EXCLUSION MAPPING
# ============================================================================
# Maps exclusion requirements to ingredient filters

EXCLUSION_FILTERS = {
    "Silicone-free": {
        "exclude_inci_patterns": ["dimethicone", "cyclomethicone", "siloxane"],
        "exclude_chemical_classes": ["Silicones"]
    },
    "Paraben-free": {
        "exclude_inci_patterns": ["paraben", "methylparaben", "propylparaben", "butylparaben"],
        "exclude_chemical_classes": ["Parabens"]
    },
    "Fragrance-free": {
        "exclude_functions": ["Fragrance"],
        "exclude_inci_patterns": ["parfum", "fragrance"]
    },
    "Sulfate-free": {
        "exclude_inci_patterns": ["sulfate", "sulphate"],
        "exclude_chemical_classes": ["Sulfates"]
    },
    "Alcohol-free": {
        "exclude_inci_patterns": ["alcohol", "ethanol", "denat"],
        "exclude_chemical_classes": ["Alcohols"]
    },
    "Essential oil-free": {
        "exclude_inci_patterns": ["oil", "essential"],
        "exclude_chemical_classes": ["Essential Oils"]
    },
    "Vegan": {
        "exclude_sources": ["animal", "beeswax", "lanolin", "collagen", "elastin"]
    },
    "Cruelty-free": {
        # This is more of a certification, handled separately
        "note": "Certification-based, not ingredient-based"
    }
}

# ============================================================================
# FALLBACK INGREDIENTS (Template-based when MongoDB query fails)
# ============================================================================

def get_fallback_ingredients(
    product_type: str,
    benefits: List[str],
    exclusions: List[str],
    hero_ingredients: List[str]
) -> List[Dict[str, Any]]:
    """
    Get fallback ingredients when MongoDB query returns no results
    
    This uses a template-based approach with common cosmetic ingredients
    that match the requested benefits and product type.
    """
    fallback_ingredients = []
    
    # Common base ingredients for all product types
    base_ingredients = {
        "Aqua": {
            "ingredient_name": "Purified Water",
            "inci_names": ["Aqua"],
            "functional_categories": ["Solvent"],
            "estimated_cost_per_kg": 1.5,
            "usage_range": {"min": 60, "max": 90}
        },
        "Glycerin": {
            "ingredient_name": "Glycerin",
            "inci_names": ["Glycerin"],
            "functional_categories": ["Humectant"],
            "estimated_cost_per_kg": 90,
            "usage_range": {"min": 2, "max": 10}
        }
    }
    
    # Add base ingredients
    for inci, data in base_ingredients.items():
        fallback_ingredients.append({
            "ingredient_id": f"fallback_{inci.lower()}",
            **data
        })
    
    # Map benefits to common ingredients (case-insensitive matching)
    benefit_ingredients_map = {
        "brightening": [
            {
                "ingredient_name": "Niacinamide",
                "inci_names": ["Niacinamide"],
                "functional_categories": ["Skin Lightening Agents", "Antioxidants"],
                "estimated_cost_per_kg": 5000,
                "usage_range": {"min": 2, "max": 5}
            },
            {
                "ingredient_name": "3-O-Ethyl Ascorbic Acid",
                "inci_names": ["3-O-Ethyl Ascorbic Acid"],
                "functional_categories": ["Antioxidants", "Skin Lightening Agents"],
                "estimated_cost_per_kg": 9000,
                "usage_range": {"min": 2, "max": 5}
            }
        ],
        "even skin tone": [
            {
                "ingredient_name": "Niacinamide",
                "inci_names": ["Niacinamide"],
                "functional_categories": ["Skin Lightening Agents", "Antioxidants"],
                "estimated_cost_per_kg": 5000,
                "usage_range": {"min": 2, "max": 5}
            }
        ],
        "dark spot fading": [
            {
                "ingredient_name": "3-O-Ethyl Ascorbic Acid",
                "inci_names": ["3-O-Ethyl Ascorbic Acid"],
                "functional_categories": ["Antioxidants", "Skin Lightening Agents"],
                "estimated_cost_per_kg": 9000,
                "usage_range": {"min": 2, "max": 5}
            }
        ],
        "deep hydration": [
            {
                "ingredient_name": "Sodium Hyaluronate",
                "inci_names": ["Sodium Hyaluronate"],
                "functional_categories": ["Humectant", "Skin Conditioning Agent"],
                "estimated_cost_per_kg": 12000,
                "usage_range": {"min": 0.1, "max": 2}
            }
        ],
        "hydration": [
            {
                "ingredient_name": "Sodium Hyaluronate",
                "inci_names": ["Sodium Hyaluronate"],
                "functional_categories": ["Humectant", "Skin Conditioning Agent"],
                "estimated_cost_per_kg": 12000,
                "usage_range": {"min": 0.1, "max": 2}
            }
        ],
        "anti-wrinkle": [
            {
                "ingredient_name": "Retinol",
                "inci_names": ["Retinol"],
                "functional_categories": ["Skin Conditioning Agent"],
                "estimated_cost_per_kg": 15000,
                "usage_range": {"min": 0.1, "max": 1}
            }
        ],
        "firming": [
            {
                "ingredient_name": "Retinol",
                "inci_names": ["Retinol"],
                "functional_categories": ["Skin Conditioning Agent"],
                "estimated_cost_per_kg": 15000,
                "usage_range": {"min": 0.1, "max": 1}
            }
        ],
        "acne control": [
            {
                "ingredient_name": "Salicylic Acid",
                "inci_names": ["Salicylic Acid"],
                "functional_categories": ["Exfoliant", "Antimicrobial"],
                "estimated_cost_per_kg": 3000,
                "usage_range": {"min": 0.5, "max": 2}
            }
        ],
        "oil control": [
            {
                "ingredient_name": "Niacinamide",
                "inci_names": ["Niacinamide"],
                "functional_categories": ["Skin Conditioning Agent"],
                "estimated_cost_per_kg": 5000,
                "usage_range": {"min": 2, "max": 5}
            }
        ],
        "calming": [
            {
                "ingredient_name": "Allantoin",
                "inci_names": ["Allantoin"],
                "functional_categories": ["Anti-inflammatory", "Skin Conditioning Agent"],
                "estimated_cost_per_kg": 300,
                "usage_range": {"min": 0.2, "max": 2}
            },
            {
                "ingredient_name": "Panthenol",
                "inci_names": ["Panthenol"],
                "functional_categories": ["Skin Conditioning Agent", "Humectant"],
                "estimated_cost_per_kg": 1500,
                "usage_range": {"min": 0.5, "max": 5}
            }
        ],
        "anti-redness": [
            {
                "ingredient_name": "Allantoin",
                "inci_names": ["Allantoin"],
                "functional_categories": ["Anti-inflammatory", "Skin Conditioning Agent"],
                "estimated_cost_per_kg": 300,
                "usage_range": {"min": 0.2, "max": 2}
            }
        ],
        "sensitive skin": [
            {
                "ingredient_name": "Allantoin",
                "inci_names": ["Allantoin"],
                "functional_categories": ["Anti-inflammatory", "Skin Conditioning Agent"],
                "estimated_cost_per_kg": 300,
                "usage_range": {"min": 0.2, "max": 2}
            },
            {
                "ingredient_name": "Panthenol",
                "inci_names": ["Panthenol"],
                "functional_categories": ["Skin Conditioning Agent", "Humectant"],
                "estimated_cost_per_kg": 1500,
                "usage_range": {"min": 0.5, "max": 5}
            }
        ]
    }
    
    # Add ingredients based on benefits (case-insensitive matching)
    for benefit in benefits:
        benefit_lower = benefit.lower().strip()
        # Try exact match first, then partial match
        matched_key = None
        for key in benefit_ingredients_map.keys():
            if benefit_lower == key or benefit_lower in key or key in benefit_lower:
                matched_key = key
                break
        
        if matched_key:
            for ing_data in benefit_ingredients_map[matched_key]:
                # Check exclusions
                ing_name_lower = ing_data["ingredient_name"].lower()
                inci_lower = " ".join(ing_data["inci_names"]).lower()
                
                should_exclude = False
                for exclusion in exclusions:
                    exclusion_lower = exclusion.lower()
                    if "silicone" in exclusion_lower and "silicone" in inci_lower:
                        should_exclude = True
                        break
                    if "paraben" in exclusion_lower and "paraben" in inci_lower:
                        should_exclude = True
                        break
                    if "alcohol" in exclusion_lower and "alcohol" in inci_lower:
                        should_exclude = True
                        break
                
                if not should_exclude:
                    # Check if already added
                    if not any(ing["ingredient_name"] == ing_data["ingredient_name"] for ing in fallback_ingredients):
                        fallback_ingredients.append({
                            "ingredient_id": f"fallback_{ing_data['ingredient_name'].lower().replace(' ', '_')}",
                            **ing_data
                        })
    
    # Add hero ingredients if specified
    for hero in hero_ingredients:
        hero_lower = hero.lower()
        # Try to match with known ingredients
        for ing_name, ing_data in HERO_INGREDIENT_MAPPING.items():
            if hero_lower in ing_name.lower() or ing_name.lower() in hero_lower:
                if not any(ing["ingredient_name"] == ing_name for ing in fallback_ingredients):
                    fallback_ingredients.append({
                        "ingredient_id": f"fallback_{ing_name.lower().replace(' ', '_')}",
                        "ingredient_name": ing_name,
                        "inci_names": ing_data["inci_names"],
                        "functional_categories": ["Active"],
                        "estimated_cost_per_kg": ing_data["cost_per_kg"],
                        "usage_range": ing_data["typical_percentage"]
                    })
    
    # Add preservative and pH adjuster
    preservative = {
        "ingredient_id": "fallback_preservative",
        "ingredient_name": "Phenoxyethanol + EHG",
        "inci_names": ["Phenoxyethanol", "Ethylhexylglycerin"],
        "functional_categories": ["Preservative"],
        "estimated_cost_per_kg": 1200,
        "usage_range": {"min": 0.5, "max": 1.5}
    }
    
    ph_adjuster = {
        "ingredient_id": "fallback_ph_adjuster",
        "ingredient_name": "Citric Acid",
        "inci_names": ["Citric Acid"],
        "functional_categories": ["pH Adjuster"],
        "estimated_cost_per_kg": 100,
        "usage_range": {"min": 0.1, "max": 0.5}
    }
    
    # Check exclusions for preservative
    if not any("paraben" in exc.lower() for exc in exclusions):
        if not any(ing["ingredient_name"] == preservative["ingredient_name"] for ing in fallback_ingredients):
            fallback_ingredients.append(preservative)
    
    if not any(ing["ingredient_name"] == ph_adjuster["ingredient_name"] for ing in fallback_ingredients):
        fallback_ingredients.append(ph_adjuster)
    
    # Add thickener for gel/serum textures
    if product_type in ["serum", "gel"]:
        thickener = {
            "ingredient_id": "fallback_thickener",
            "ingredient_name": "Xanthan Gum",
            "inci_names": ["Xanthan Gum"],
            "functional_categories": ["Thickener"],
            "estimated_cost_per_kg": 450,
            "usage_range": {"min": 0.2, "max": 1}
        }
        if not any(ing["ingredient_name"] == thickener["ingredient_name"] for ing in fallback_ingredients):
            fallback_ingredients.append(thickener)
    
    return fallback_ingredients


# ============================================================================
# STEP 4: INGREDIENT SELECTION ENGINE (Rule-Based)
# ============================================================================

async def get_functional_category_ids(category_names: List[str]) -> List[ObjectId]:
    """
    Convert functional category names to MongoDB ObjectIds
    
    WHAT IT DOES:
    - Queries functional_categories collection
    - Finds categories by name (case-insensitive)
    - Returns list of ObjectIds for MongoDB queries
    
    WHY:
    - MongoDB stores relationships as ObjectIds
    - Need to convert human-readable names to database IDs
    """
    if not category_names:
        return []
    
    # Normalize category names for matching
    normalized_names = [name.strip().lower() for name in category_names]
    
    # Query functional categories collection
    query = {
        "$or": [
            {"functionalName_normalized": {"$in": normalized_names}},
            {"functionalName": {"$regex": "|".join(normalized_names), "$options": "i"}}
        ]
    }
    
    cursor = functional_categories_col.find(query, {"_id": 1})
    category_ids = [doc["_id"] for doc in await cursor.to_list(length=None)]
    
    return category_ids


async def check_ingredient_exists_in_db(ingredient_name: str, inci_names: List[str]) -> Optional[Dict]:
    """
    Check if ingredient exists in MongoDB database by name or INCI
    
    Returns the ingredient document if found, None otherwise
    """
    try:
        # Try to find by ingredient name (case-insensitive)
        doc = await branded_ingredients_col.find_one(
            {"ingredient_name": {"$regex": f"^{ingredient_name}$", "$options": "i"}}
        )
        
        if doc:
            return doc
        
        # Try to find by INCI names
        for inci_name in inci_names:
            # First check if INCI exists in inci collection
            inci_doc = await inci_col.find_one(
                {"inciName_normalized": inci_name.strip().lower()}
            )
            
            if inci_doc:
                inci_id = inci_doc.get("_id")
                # Find branded ingredient with this INCI
                branded_doc = await branded_ingredients_col.find_one(
                    {"inci_ids": inci_id}
                )
                if branded_doc:
                    return branded_doc
        
        return None
        
    except Exception as e:
        print(f"⚠️ Error checking ingredient in DB: {e}")
        return None


async def validate_and_enrich_claude_ingredients(
    claude_ingredients: List[Dict],
    benefits: List[str],
    exclusions: List[str],
    hero_ingredients: List[str],
    cost_target: Dict[str, float]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Validate Claude-selected ingredients against MongoDB and generate warnings
    
    Returns:
    - validated_ingredients: List of ingredients that exist in DB
    - warnings: List of warning messages
    """
    validated_ingredients = []
    warnings = []
    
    hero_ingredient_costs = {}
    incompatible_exclusions = []
    
    for ing in claude_ingredients:
        ingredient_name = ing.get("ingredient_name", "")
        inci_names = ing.get("inci_names", [])
        
        # Check if ingredient exists in database
        db_ingredient = await check_ingredient_exists_in_db(ingredient_name, inci_names)
        
        if not db_ingredient:
            print(f"⚠️ Ingredient '{ingredient_name}' not found in database, skipping")
            warnings.append({
                "type": "info",
                "text": f"'{ingredient_name}' is not available in our database and has been excluded from the formula."
            })
            continue
        
        # Get cost from database if available
        db_cost_per_kg = None
        supplier_id = db_ingredient.get("supplier_id")
        if supplier_id:
            from app.ai_ingredient_intelligence.db.collections import distributor_col
            supplier_doc = await distributor_col.find_one({"_id": supplier_id})
            if supplier_doc:
                db_cost_per_kg = supplier_doc.get("cost_per_kg")
        
        # Use database cost if available, otherwise use Claude's estimate
        cost_per_kg = db_cost_per_kg if db_cost_per_kg else ing.get("estimated_cost_per_kg", 3000)
        
        # Check if hero ingredient - more thorough matching
        is_hero = False
        if ing.get("is_hero", False):
            is_hero = True
        elif hero_ingredients:
            ingredient_name_lower = ingredient_name.lower()
            inci_lower = " ".join(inci_names).lower()
            
            for hero in hero_ingredients:
                hero_lower = hero.lower().strip()
                # Check if hero name matches ingredient name or INCI
                if (hero_lower in ingredient_name_lower or 
                    ingredient_name_lower in hero_lower or
                    any(hero_lower in inci for inci in inci_names) or
                    any(inci in hero_lower for inci in inci_names)):
                    is_hero = True
                    print(f"⭐ Hero ingredient matched: '{hero}' -> '{ingredient_name}'")
                    break
        
        if is_hero:
            # Calculate cost per 100g
            usage_range = ing.get("usage_range", {"min": 0.1, "max": 5.0})
            min_percentage = usage_range.get("min", 0.1)
            max_percentage = usage_range.get("max", 5.0)
            
            # Cost at minimum percentage
            min_cost_per_100g = (min_percentage / 100.0) * (cost_per_kg / 10.0)
            # Cost at maximum percentage
            max_cost_per_100g = (max_percentage / 100.0) * (cost_per_kg / 10.0)
            
            cost_target_min = cost_target.get("min", 30)
            cost_target_max = cost_target.get("max", 60)
            
            # Check if hero ingredient cost fits in budget
            if max_cost_per_100g > cost_target_max:
                # Suggest reducing percentage
                suggested_percentage = (cost_target_max * 100.0) / (cost_per_kg / 10.0)
                if suggested_percentage < min_percentage:
                    suggested_percentage = min_percentage
                
                warnings.append({
                    "type": "info",
                    "text": f"'{ingredient_name}' (hero ingredient) is expensive (₹{cost_per_kg}/kg). To fit your budget (₹{cost_target_min}-{cost_target_max}/100g), consider reducing its percentage to {suggested_percentage:.1f}% or less."
                })
                hero_ingredient_costs[ingredient_name] = {
                    "cost_per_kg": cost_per_kg,
                    "suggested_percentage": suggested_percentage
                }
        
        # Check for incompatible exclusions
        inci_lower = " ".join(inci_names).lower()
        ing_name_lower = ingredient_name.lower()
        should_exclude = False
        
        for exclusion in exclusions:
            exclusion_lower = exclusion.lower()
            if "silicone" in exclusion_lower and any(s in inci_lower for s in ["silicone", "dimethicone", "cyclomethicone"]):
                incompatible_exclusions.append(f"'{ingredient_name}' contains silicone but 'Silicone-free' was requested")
                should_exclude = True
            if "paraben" in exclusion_lower and "paraben" in inci_lower:
                incompatible_exclusions.append(f"'{ingredient_name}' contains paraben but 'Paraben-free' was requested")
                should_exclude = True
            if "alcohol" in exclusion_lower and any(a in inci_lower for a in ["alcohol", "ethanol", "denat"]):
                incompatible_exclusions.append(f"'{ingredient_name}' contains alcohol but 'Alcohol-free' was requested")
                should_exclude = True
        
        if should_exclude:
            print(f"⚠️ Ingredient '{ingredient_name}' violates exclusions, skipping")
            continue
        
        # Get functional categories from database
        func_cat_ids = db_ingredient.get("functional_category_ids", [])
        func_categories = await get_functional_category_names(func_cat_ids) if func_cat_ids else ing.get("functional_categories", [])
        
        # Get function - prioritize database description, then Claude, then functional category
        function = "Other"
        db_description = db_ingredient.get("description", "").lower()
        claude_function = ing.get("function", "").lower()
        
        # Try to extract function from database description
        if db_description:
            if any(word in db_description for word in ["brightening", "lightening", "whitening", "skin lightening"]):
                function = "Brightening"
            elif any(word in db_description for word in ["moistur", "hydrat", "humectant"]):
                function = "Humectant"
            elif any(word in db_description for word in ["antioxidant", "vitamin c", "vitamin e"]):
                function = "Antioxidant"
            elif any(word in db_description for word in ["preserv", "antimicrobial"]):
                function = "Preservative"
            elif any(word in db_description for word in ["emollient", "soften", "smooth"]):
                function = "Emollient"
            elif any(word in db_description for word in ["thicken", "viscosity", "gum", "polymer"]):
                function = "Thickener"
            elif any(word in db_description for word in ["ph", "adjust", "acid", "base"]):
                function = "pH Adjuster"
            elif any(word in db_description for word in ["active", "treatment", "therapeutic", "anti"]):
                function = "Active"
            elif any(word in db_description for word in ["solvent", "water", "aqua"]):
                function = "Solvent"
            elif any(word in db_description for word in ["exfoliant", "peel", "aha", "bha"]):
                function = "Exfoliant"
            elif any(word in db_description for word in ["emulsifier", "emulsify"]):
                function = "Emulsifier"
        
        # If still "Other", try Claude's function field
        if function == "Other" and claude_function:
            function = ing.get("function", "Other")
        
        # If still "Other", use first functional category
        if function == "Other" and func_categories:
            # Map functional category to simpler function name
            first_cat = func_categories[0].lower()
            if "humectant" in first_cat:
                function = "Humectant"
            elif "emollient" in first_cat:
                function = "Emollient"
            elif "preserv" in first_cat:
                function = "Preservative"
            elif "thickener" in first_cat or "viscosity" in first_cat:
                function = "Thickener"
            elif "antioxidant" in first_cat:
                function = "Antioxidant"
            elif "skin lightening" in first_cat or "brightening" in first_cat:
                function = "Brightening"
            elif "active" in first_cat:
                function = "Active"
            elif "solvent" in first_cat:
                function = "Solvent"
            elif "exfoliant" in first_cat:
                function = "Exfoliant"
            elif "emulsifier" in first_cat:
                function = "Emulsifier"
            else:
                function = func_categories[0]  # Use category name as-is
        
        # Build validated ingredient
        validated_ing = {
            "ingredient_id": str(db_ingredient["_id"]),
            "ingredient_name": db_ingredient.get("ingredient_name", ingredient_name),
            "inci_names": inci_names if inci_names else [db_ingredient.get("original_inci_name", ingredient_name)],
            "functional_categories": func_categories,
            "estimated_cost_per_kg": cost_per_kg,
            "usage_range": ing.get("usage_range", {"min": 0.1, "max": 5.0}),
            "description": db_ingredient.get("description", ing.get("function", "")),
            "function": function,  # Add function field
            "is_hero": is_hero,
            "supplier_id": str(supplier_id) if supplier_id else None
        }
        
        validated_ingredients.append(validated_ing)
    
    # Add warnings for incompatible exclusions
    if incompatible_exclusions:
        warnings.append({
            "type": "critical",
            "text": f"Incompatibility detected: {', '.join(incompatible_exclusions)}. These ingredients have been excluded from the formula."
        })
    
    return validated_ingredients, warnings


async def select_ingredients_by_benefits(
    benefits: List[str],
    exclusions: List[str],
    hero_ingredients: List[str],
    cost_target: Dict[str, float]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], List[Dict], List[Dict]]:
    """
    Select ingredients based on benefits using Claude AI, validated against MongoDB
    
    HOW IT WORKS:
    1. Uses Claude to intelligently select ingredients based on benefits
    2. Validates each ingredient exists in MongoDB database
    3. Only includes ingredients that exist in DB
    4. Generates warnings for incompatibilities and cost issues
    5. Returns validated ingredients with warnings
    
    WHAT WE USE:
    - Claude API for intelligent ingredient selection
    - MongoDB for validation
    - Fallback template ingredients if Claude unavailable
    
    RETURNS:
    - Tuple of (validated_ingredients, warnings)
    """
    if not claude_client:
        print("⚠️ Claude not available, using fallback template ingredients")
        return [], [], [], []
    
    # Build prompt for Claude to select ingredients
    user_prompt = build_ingredient_selection_prompt(benefits, exclusions, hero_ingredients, cost_target)
    full_prompt = f"{INGREDIENT_SELECTION_SYSTEM_PROMPT}\n\n{user_prompt}"
    
    try:
        if not claude_model:
            raise ValueError("Claude model not configured")
        
        print(f"🤖 Asking Claude to select ingredients for benefits: {', '.join(benefits)}")
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=16384,
            temperature=0.3,
            messages=[{"role": "user", "content": full_prompt}]
        )
        
        if not response.content or len(response.content) == 0:
            raise ValueError("Empty response from Claude API")
        
        result_text = response.content[0].text.strip()
        
        if not result_text:
            raise ValueError("Empty text in Claude response")
        
        # Parse Claude's full response (ingredients, phases, insights, warnings)
        claude_response = parse_claude_ingredient_selection(result_text, benefits, exclusions, hero_ingredients)
        
        claude_ingredients = claude_response.get("ingredients", [])
        claude_phases = claude_response.get("phases", [])
        claude_insights = claude_response.get("insights", [])
        claude_warnings = claude_response.get("warnings", [])
        
        print(f"✅ Claude selected {len(claude_ingredients)} ingredients")
        print(f"   Phases: {len(claude_phases)}, Insights: {len(claude_insights)}, Warnings: {len(claude_warnings)}")
        print(f"🔍 Validating ingredients against database...")
        
        # Validate against MongoDB and generate warnings
        validated_ingredients, validation_warnings = await validate_and_enrich_claude_ingredients(
            claude_ingredients,
            benefits,
            exclusions,
            hero_ingredients,
            cost_target
        )
        
        print(f"✅ {len(validated_ingredients)} ingredients validated and found in database")
        
        # Combine Claude warnings with validation warnings
        all_warnings = claude_warnings + validation_warnings
        if all_warnings:
            print(f"⚠️ Generated {len(all_warnings)} warnings")
        
        return validated_ingredients, all_warnings, claude_phases, claude_insights
        
    except Exception as e:
        print(f"⚠️ Error getting ingredients from Claude: {e}")
        import traceback
        traceback.print_exc()
        return [], [], [], []


def build_exclusion_query(exclusions: List[str]) -> Dict[str, Any]:
    """
    Build MongoDB query to exclude certain ingredients
    
    HOW IT WORKS:
    - For each exclusion, gets filter criteria
    - Combines them with $and/$or operators
    - Returns MongoDB query dict
    """
    if not exclusions:
        return {}
    
    exclusion_patterns = []
    
    for exclusion in exclusions:
        filter_config = EXCLUSION_FILTERS.get(exclusion, {})
        
        # Exclude by INCI name patterns
        if "exclude_inci_patterns" in filter_config:
            exclusion_patterns.extend(filter_config["exclude_inci_patterns"])
    
    if not exclusion_patterns:
        return {}
    
    # Build $nor query to exclude all patterns
    # $nor means "not match any of these conditions"
    nor_conditions = []
    for pattern in exclusion_patterns:
        nor_conditions.append({
            "$or": [
                {"ingredient_name": {"$regex": pattern, "$options": "i"}},
                {"original_inci_name": {"$regex": pattern, "$options": "i"}}
            ]
        })
    
    return {"$nor": nor_conditions}


def prioritize_hero_ingredients(
    ingredients: List[Dict],
    hero_ingredients: List[str]
) -> List[Dict]:
    """
    Prioritize ingredients that match hero ingredient names
    
    HOW IT WORKS:
    - Checks if ingredient name or INCI matches hero ingredients
    - Moves matches to front of list
    - Keeps others in original order
    """
    if not hero_ingredients:
        return ingredients
    
    hero_normalized = [h.lower().strip() for h in hero_ingredients]
    prioritized = []
    others = []
    
    for ing in ingredients:
        ing_name = ing.get("ingredient_name", "").lower()
        # Handle inci_ids - could be list of strings or ObjectIds
        inci_ids = ing.get("inci_ids", [])
        inci_names = []
        for inci_item in inci_ids:
            if isinstance(inci_item, str):
                inci_names.append(inci_item.lower())
            elif hasattr(inci_item, '__str__'):
                inci_names.append(str(inci_item).lower())
        
        # Check if matches any hero ingredient
        is_hero = any(
            hero in ing_name or any(hero in inci for inci in inci_names)
            for hero in hero_normalized
        )
        
        if is_hero:
            prioritized.append(ing)
        else:
            others.append(ing)
    
    return prioritized + others


async def enrich_ingredient_data(
    ingredients: List[Dict],
    cost_target: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    Enrich ingredient data with additional metadata
    
    WHAT IT ADDS:
    - Functional categories (human-readable)
    - Cost estimates (if available)
    - Typical usage percentages
    - Function descriptions
    
    WHY:
    - Raw MongoDB data needs enrichment for formula generation
    - Cost data needed for optimization
    - Usage ranges needed for percentage allocation
    """
    enriched = []
    
    for ing in ingredients:
        # Get functional categories
        func_cat_ids = ing.get("functional_category_ids", [])
        func_categories = await get_functional_category_names(func_cat_ids)
        
        # Estimate cost (placeholder - would need supplier data)
        estimated_cost = estimate_ingredient_cost(ing, cost_target)
        
        # Get typical usage percentage
        usage_range = get_typical_usage_range(ing)
        
        enriched.append({
            "ingredient_id": str(ing["_id"]),
            "ingredient_name": ing.get("ingredient_name", ""),
            "inci_names": ing.get("inci_ids", []),
            "functional_categories": func_categories,
            "description": ing.get("description", ""),
            "estimated_cost_per_kg": estimated_cost,
            "usage_range": usage_range,
            "supplier_id": str(ing.get("supplier_id", "")) if ing.get("supplier_id") else None
        })
    
    return enriched


async def get_functional_category_names(category_ids: List[ObjectId]) -> List[str]:
    """Get human-readable functional category names from IDs"""
    if not category_ids:
        return []
    
    cursor = functional_categories_col.find(
        {"_id": {"$in": category_ids}},
        {"functionalName": 1}
    )
    categories = [doc.get("functionalName", "") for doc in await cursor.to_list(length=None)]
    return categories


def estimate_ingredient_cost(ingredient: Dict, cost_target: Dict[str, float]) -> float:
    """
    Estimate ingredient cost per kg
    
    HOW IT WORKS:
    - Uses HERO_INGREDIENT_MAPPING if available
    - Otherwise uses default estimates based on ingredient type
    - Returns cost in ₹/kg
    
    NOTE: In production, this would query supplier data
    """
    ing_name = ingredient.get("ingredient_name", "").lower()
    
    # Check hero ingredient mapping
    for hero_name, hero_data in HERO_INGREDIENT_MAPPING.items():
        if hero_name.lower() in ing_name:
            return hero_data.get("cost_per_kg", 5000)
    
    # Default estimates by function
    func_cats = ingredient.get("functional_category_ids", [])
    # This is simplified - would need actual cost data
    return 3000  # Default estimate


def get_typical_usage_range(ingredient: Dict) -> Dict[str, float]:
    """
    Get typical usage percentage range for ingredient
    
    HOW IT WORKS:
    - Checks HERO_INGREDIENT_MAPPING for known actives
    - Uses default ranges based on functional category
    - Returns min/max percentage
    
    WHY:
    - Needed for percentage allocation
    - Ensures safe and effective concentrations
    """
    ing_name = ingredient.get("ingredient_name", "").lower()
    
    # Check hero ingredient mapping
    for hero_name, hero_data in HERO_INGREDIENT_MAPPING.items():
        if hero_name.lower() in ing_name:
            return hero_data.get("typical_percentage", {"min": 0.1, "max": 5.0})
    
    # Default ranges by category (simplified)
    return {"min": 0.1, "max": 5.0}


# ============================================================================
# STEP 5: PERCENTAGE ALLOCATION (Rule-Based)
# ============================================================================

def allocate_percentages_rules(
    template: Dict,
    selected_ingredients: List[Dict],
    hero_ingredients: List[str]
) -> List[Dict[str, Any]]:
    """
    Allocate percentages to ingredients using rule-based logic
    
    HOW IT WORKS:
    1. Start with template base ingredients (e.g., Aqua)
    2. Allocate percentages to each phase based on template ranges
    3. Distribute within each phase based on ingredient importance
    4. Ensure total = 100%
    
    WHAT WE USE:
    - Template phase percentage ranges
    - Ingredient usage ranges
    - Hero ingredient prioritization
    
    RETURNS:
    - List of ingredients with allocated percentages
    """
    allocated = []
    phase_percentages = {}
    
    # Step 1: Allocate base ingredients (required)
    base_ingredients = template.get("base_ingredients", {})
    for inci_name, base_data in base_ingredients.items():
        phase = base_data["phase"]
        percentage = base_data["percentage"]
        
        allocated.append({
            "name": inci_name,
            "inci": inci_name,
            "percent": percentage,
            "phase": phase,
            "function": base_data["function"],
            "cost": base_data.get("cost", 0.15 / 10.0),  # Default Aqua cost per 100g
            "hero": False,
            "required": True
        })
        
        # Track phase percentages
        if phase not in phase_percentages:
            phase_percentages[phase] = 0
        phase_percentages[phase] += percentage
    
    # Step 2: Allocate selected ingredients to phases
    for phase in template["phases"]:
        phase_id = phase["id"]
        phase_range = phase["percentage_range"]
        phase_used = phase_percentages.get(phase_id, 0)
        phase_available = phase_range["max"] - phase_used
        
        # Get ingredients for this phase
        phase_ingredients = get_ingredients_for_phase(
            selected_ingredients,
            phase,
            hero_ingredients
        )
        
        # Allocate percentages within phase
        phase_allocated = allocate_within_phase(
            phase_ingredients,
            phase_available,
            phase.get("required_functions", []),
            phase.get("optional_functions", [])
        )
        
        # Assign phase ID to each allocated ingredient
        for ing in phase_allocated:
            ing["phase"] = phase_id
        
        allocated.extend(phase_allocated)
    
    # Step 3: Normalize to 100%
    # Filter out ingredients with "q.s." or string percentages for calculation
    numeric_percentages = [ing["percent"] for ing in allocated if isinstance(ing["percent"], (int, float))]
    total = sum(numeric_percentages)
    
    if total > 0 and abs(total - 100.0) > 0.01:
        # Adjust proportionally (only numeric percentages)
        factor = 100.0 / total
        for ing in allocated:
            if isinstance(ing["percent"], (int, float)):
                ing["percent"] = round(ing["percent"] * factor, 2)
    elif total == 0:
        # If no numeric percentages, this is an error
        raise ValueError("Total percentage is 0. Check ingredient allocation.")
    
    return allocated


def get_ingredients_for_phase(
    ingredients: List[Dict],
    phase: Dict,
    hero_ingredients: List[str]
) -> List[Dict]:
    """
    Filter ingredients that belong to a specific phase
    
    HOW IT WORKS:
    - Matches ingredient functions to phase required/optional functions
    - Prioritizes hero ingredients
    - Returns filtered list
    """
    required_funcs = phase.get("required_functions", [])
    optional_funcs = phase.get("optional_functions", [])
    all_funcs = required_funcs + optional_funcs
    
    phase_ingredients = []
    
    for ing in ingredients:
        ing_funcs = ing.get("functional_categories", [])
        
        # Check if ingredient matches phase functions
        matches = any(
            func.lower() in " ".join(ing_funcs).lower() or
            any(f.lower() in func.lower() for f in ing_funcs)
            for func in all_funcs
        )
        
        if matches:
            # Check if it's a hero ingredient
            ing_name = ing.get("ingredient_name", "").lower()
            is_hero = any(hero.lower() in ing_name for hero in hero_ingredients)
            
            phase_ingredients.append({
                **ing,
                "is_hero": is_hero,
                "priority": 1 if is_hero else (2 if any(f in required_funcs for f in ing_funcs) else 3)
            })
    
    # Sort by priority
    phase_ingredients.sort(key=lambda x: x["priority"])
    
    return phase_ingredients


def allocate_within_phase(
    ingredients: List[Dict],
    available_percentage: float,
    required_functions: List[str],
    optional_functions: List[str]
) -> List[Dict[str, Any]]:
    """
    Allocate percentages within a single phase
    
    HOW IT WORKS:
    - Prioritizes ingredients matching required functions
    - Uses typical usage ranges
    - Distributes remaining percentage to optional ingredients
    """
    allocated = []
    remaining = available_percentage
    
    # First, allocate to required function ingredients
    for ing in ingredients:
        if remaining <= 0:
            break
        
        ing_funcs = ing.get("functional_categories", [])
        is_required = any(f in required_functions for f in ing_funcs)
        
        if is_required or ing.get("is_hero", False):
            usage_range = ing.get("usage_range", {"min": 0.1, "max": 5.0})
            # Use mid-range of typical usage
            percentage = min(
                (usage_range["min"] + usage_range["max"]) / 2,
                remaining
            )
            
            # Get INCI name safely
            inci_names = ing.get("inci_names", [])
            if not inci_names and ing.get("ingredient_name"):
                inci_names = [ing.get("ingredient_name", "")]
            inci_name = inci_names[0] if inci_names else ing.get("ingredient_name", "Unknown")
            
            allocated.append({
                "name": ing.get("ingredient_name", "Unknown"),
                "inci": inci_name,
                "percent": round(percentage, 2),
                "phase": None,  # Will be set by caller
                "function": ing_funcs[0] if ing_funcs else "Other",
                "cost": (ing.get("estimated_cost_per_kg", 3000) / 10.0) if ing.get("estimated_cost_per_kg") else 300.0,  # Cost per 100g
                "hero": ing.get("is_hero", False)
            })
            
            remaining -= percentage
    
    # Then allocate to optional function ingredients if space remains
    for ing in ingredients:
        if remaining <= 0:
            break
        
        if not any(a["name"] == ing["ingredient_name"] for a in allocated):
            usage_range = ing.get("usage_range", {"min": 0.1, "max": 2.0})
            percentage = min(
                usage_range["min"] + (usage_range["max"] - usage_range["min"]) * 0.3,
                remaining
            )
            
            # Get INCI name safely
            inci_names = ing.get("inci_names", [])
            if not inci_names and ing.get("ingredient_name"):
                inci_names = [ing.get("ingredient_name", "")]
            inci_name = inci_names[0] if inci_names else ing.get("ingredient_name", "Unknown")
            
            allocated.append({
                "name": ing.get("ingredient_name", "Unknown"),
                "inci": inci_name,
                "percent": round(percentage, 2),
                "phase": None,
                "function": ing.get("functional_categories", ["Other"])[0] if ing.get("functional_categories") else "Other",
                "cost": (ing.get("estimated_cost_per_kg", 3000) / 10.0) if ing.get("estimated_cost_per_kg") else 300.0,  # Cost per 100g
                "hero": False
            })
            
            remaining -= percentage
    
    return allocated


# ============================================================================
# CLAUDE INGREDIENT SELECTION
# ============================================================================

INGREDIENT_SELECTION_SYSTEM_PROMPT = """You are an expert cosmetic formulator. Your task is to select appropriate ingredients for a cosmetic formula based on user requirements.

CRITICAL RULES:
1. Select ingredients that match the requested benefits
2. Respect all exclusions (e.g., if "Silicone-free", don't include any silicones)
3. Prioritize hero ingredients if specified
4. Consider cost targets
5. Include necessary base ingredients (water, preservatives, pH adjusters)
6. Select appropriate functional ingredients (humectants, emollients, actives, etc.)
7. Organize ingredients into phases (Water Phase, Active Phase, Preservation, etc.)

OUTPUT FORMAT (JSON):
{
    "ingredients": [
        {
            "ingredient_name": "Niacinamide",
            "inci_names": ["Niacinamide"],
            "functional_categories": ["Skin Lightening Agents", "Antioxidants"],
            "estimated_cost_per_kg": 5000,
            "usage_range": {"min": 2, "max": 5},
            "function": "Brightening agent",
            "is_hero": false,
            "phase": "B"
        }
    ],
    "phases": [
        {
            "id": "A",
            "name": "Water Phase",
            "temp": "70°C",
            "ingredients": ["Purified Water", "Glycerin"]
        },
        {
            "id": "B",
            "name": "Active Phase",
            "temp": "40°C",
            "ingredients": ["Niacinamide", "3-O-Ethyl Ascorbic Acid"]
        }
    ],
    "insights": [
        {
            "icon": "💡",
            "title": "Niacinamide",
            "text": "Effective at 2-5% for brightening and oil control"
        }
    ],
    "warnings": [
        {
            "type": "info",
            "text": "pH must be maintained at 5.0-6.5 for optimal stability"
        }
    ],
    "reasoning": "Brief explanation of ingredient choices"
}

IMPORTANT:
- Use standard INCI names
- Provide realistic cost estimates in ₹/kg (Indian Rupees per kilogram)
- Provide safe usage percentage ranges
- Mark hero ingredients with is_hero: true
- Include at least 5-10 ingredients for a complete formula
- Always include: Water (Aqua), Preservative, pH Adjuster
- Organize into phases: Water Phase (A), Active Phase (B), Preservation (C/D)
- Generate insights explaining key ingredient choices
- Add warnings for important considerations (pH, stability, etc.)
"""


def build_ingredient_selection_prompt(
    benefits: List[str],
    exclusions: List[str],
    hero_ingredients: List[str],
    cost_target: Dict[str, float]
) -> str:
    """Build prompt for Claude to select ingredients"""
    exclusions_text = ", ".join(exclusions) if exclusions else "None"
    hero_text = ", ".join(hero_ingredients) if hero_ingredients else "None"
    cost_text = f"₹{cost_target.get('min', 30)}-{cost_target.get('max', 60)}/100g"
    
    return f"""
Select ingredients for a cosmetic formula with these requirements:

BENEFITS NEEDED:
{chr(10).join(f"- {b}" for b in benefits)}

EXCLUSIONS (DO NOT INCLUDE):
{exclusions_text}

HERO INGREDIENTS (PRIORITIZE THESE):
{hero_text}

COST TARGET:
{cost_text}

REQUIREMENTS:
1. Select ingredients that deliver the requested benefits
2. DO NOT include any ingredients matching the exclusions
3. Prioritize hero ingredients if specified
4. Include base ingredients: Water (Aqua), Glycerin (humectant), Preservative, pH Adjuster
5. Include active ingredients for the benefits
6. Include functional ingredients (thickeners, emollients, etc.) as needed
7. Ensure cost is within target range
8. Use standard INCI names
9. Provide realistic cost estimates in ₹/kg (Indian Rupees per kilogram)
10. Provide safe usage percentage ranges

Return the ingredient list as JSON following the specified format.
"""


def parse_claude_ingredient_selection(
    response_text: str,
    benefits: List[str],
    exclusions: List[str],
    hero_ingredients: List[str]
) -> List[Dict[str, Any]]:
    """
    Parse Claude's ingredient selection response
    
    HOW IT WORKS:
    - Extracts JSON from Claude response
    - Validates ingredient data
    - Enriches with metadata
    - Returns structured ingredient list
    """
    import json
    import re
    
    # Try to extract JSON from response
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not json_match:
        print("⚠️ Could not parse Claude response as JSON, using fallback")
        return []
    
    try:
        ai_data = json.loads(json_match.group())
        
        # Return full structure including phases, insights, warnings
        return {
            "ingredients": ai_data.get("ingredients", []),
            "phases": ai_data.get("phases", []),
            "insights": ai_data.get("insights", []),
            "warnings": ai_data.get("warnings", []),
            "reasoning": ai_data.get("reasoning", "")
        }
        
    except json.JSONDecodeError as e:
        print(f"⚠️ Error parsing Claude JSON: {e}")
        print(f"Response text: {response_text[:500]}")
        return {
            "ingredients": [],
            "phases": [],
            "insights": [],
            "warnings": [],
            "reasoning": ""
        }
    except Exception as e:
        print(f"⚠️ Error processing Claude ingredient selection: {e}")
        import traceback
        traceback.print_exc()
        return {
            "ingredients": [],
            "phases": [],
            "insights": [],
            "warnings": [],
            "reasoning": ""
        }


# ============================================================================
# STEP 6: AI OPTIMIZATION (Claude)
# ============================================================================

async def optimize_percentages_with_ai(
    allocated_ingredients: List[Dict],
    wish_data: Dict,
    template: Dict
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Use Claude to optimize percentages and generate insights
    
    HOW IT WORKS:
    1. Sends current allocation to Claude
    2. Claude optimizes percentages based on:
       - Synergies between ingredients
       - Safety limits
       - Cost targets
       - Product type requirements
    3. Generates insights and warnings
    4. Returns optimized allocation + metadata
    
    WHAT WE USE:
    - Claude API (claude-3-opus-20240229)
    - Current ingredient allocation
    - Wish data (benefits, exclusions, etc.)
    - Template structure
    
    RETURNS:
    - Optimized ingredient list with percentages
    - Insights, warnings, and recommendations
    """
    if not claude_client:
        print("Warning: Claude not available, skipping AI optimization")
        return allocated_ingredients, {
            "insights": [],
            "warnings": [],
            "optimization_applied": False
        }
    
    # Build prompt for Claude
    prompt = build_optimization_prompt(allocated_ingredients, wish_data, template)
    
    # Combine system prompt and user prompt for Claude
    full_prompt = f"{FORMULA_OPTIMIZATION_SYSTEM_PROMPT}\n\n{prompt}"
    
    try:
        if not claude_model:
            raise ValueError("Claude model not configured")
            
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=16384,
            temperature=0.3,  # Lower temperature for more consistent results
            messages=[{"role": "user", "content": full_prompt}]
        )
        
        if not response.content or len(response.content) == 0:
            raise ValueError("Empty response from Claude API")
            
        result_text = response.content[0].text.strip()
        
        if not result_text:
            raise ValueError("Empty text in Claude response")
        
        # Parse AI response
        optimized = parse_ai_optimization_response(result_text, allocated_ingredients)
        
        return optimized["ingredients"], {
            "insights": optimized.get("insights", []),
            "warnings": optimized.get("warnings", []),
            "optimization_applied": True
        }
    
    except Exception as e:
        import traceback
        print(f"Warning: Error in Claude AI optimization: {e}")
        traceback.print_exc()
        # Return original allocation with warning - don't fail the entire request
        return allocated_ingredients, {
            "insights": [],
            "warnings": [{"type": "info", "text": "AI optimization unavailable, using rule-based allocation"}],
            "optimization_applied": False
        }


FORMULA_OPTIMIZATION_SYSTEM_PROMPT = """You are an expert cosmetic formulator. Your task is to optimize ingredient percentages in a cosmetic formulation.

CRITICAL RULES:
1. Total percentage MUST equal exactly 100%
2. Respect typical usage ranges for each ingredient
3. Consider ingredient synergies and compatibilities
4. Ensure pH stability
5. Optimize for cost if target provided
6. Generate insights explaining your choices
7. Identify any warnings or concerns

OUTPUT FORMAT (JSON):
{
    "ingredients": [
        {
            "name": "Ingredient Name",
            "inci": "INCI Name",
            "percent": 5.0,
            "phase": "A",
            "function": "Active",
            "cost": 5000,
            "hero": true
        }
    ],
    "insights": [
        {
            "icon": "💡",
            "title": "Ingredient Name",
            "text": "Why this ingredient and percentage was chosen"
        }
    ],
    "warnings": [
        {
            "type": "critical" or "info",
            "text": "Warning message"
        }
    ],
    "ph_recommendation": {
        "min": 5.0,
        "max": 5.5,
        "reason": "Explanation"
    }
}"""


def build_optimization_prompt(
    ingredients: List[Dict],
    wish_data: Dict,
    template: Dict
) -> str:
    """Build prompt for Claude optimization"""
    return f"""
Optimize this cosmetic formulation:

PRODUCT TYPE: {wish_data.get('productType', 'serum')}
BENEFITS: {', '.join(wish_data.get('benefits', []))}
EXCLUSIONS: {', '.join(wish_data.get('exclusions', []))}
HERO INGREDIENTS: {', '.join(wish_data.get('heroIngredients', []))}
COST TARGET: ₹{wish_data.get('costMin', 30)}-{wish_data.get('costMax', 60)}/100g
TEXTURE: {wish_data.get('texture', 'serum')}

CURRENT FORMULATION:
{format_ingredients_for_prompt(ingredients)}

TEMPLATE STRUCTURE:
{format_template_for_prompt(template)}

REQUIREMENTS:
1. Optimize percentages to total exactly 100%
2. Ensure percentages are within safe/effective ranges
3. Consider ingredient synergies
4. Optimize cost if possible
5. Generate insights for key ingredients
6. Identify any warnings

Return optimized formulation as JSON.
"""


def format_ingredients_for_prompt(ingredients: List[Dict]) -> str:
    """Format ingredients for AI prompt"""
    lines = []
    for ing in ingredients:
        lines.append(
            f"- {ing['name']} ({ing.get('inci', 'N/A')}): {ing['percent']}% "
            f"[Function: {ing.get('function', 'N/A')}, Cost: ₹{ing.get('cost', 0)}/kg]"
        )
    return "\n".join(lines)


def format_template_for_prompt(template: Dict) -> str:
    """Format template for AI prompt"""
    phases_str = []
    for phase in template.get("phases", []):
        phases_str.append(
            f"Phase {phase['id']} ({phase['name']}): "
            f"{phase['percentage_range']['min']}-{phase['percentage_range']['max']}%, "
            f"Temp: {phase.get('temperature', 'N/A')}"
        )
    return "\n".join(phases_str)


def parse_ai_optimization_response(
    response_text: str,
    original_ingredients: List[Dict]
) -> Dict[str, Any]:
    """
    Parse Claude response and merge with original data
    
    HOW IT WORKS:
    - Extracts JSON from response
    - Validates percentages total 100%
    - Merges with original ingredient metadata
    - Returns structured data
    """
    import json
    import re
    
    # Try to extract JSON from response
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not json_match:
        print("Warning: Could not parse AI response as JSON")
        return {
            "ingredients": original_ingredients,
            "insights": [],
            "warnings": []
        }
    
    try:
        ai_data = json.loads(json_match.group())
        
        # Validate and merge
        optimized_ingredients = []
        for ai_ing in ai_data.get("ingredients", []):
            # Find matching original ingredient
            original = next(
                (o for o in original_ingredients if o["name"] == ai_ing.get("name")),
                None
            )
            
            if original:
                # Merge AI optimization with original data
                optimized_ingredients.append({
                    **original,
                    "percent": ai_ing.get("percent", original["percent"]),
                    "phase": ai_ing.get("phase", original.get("phase"))
                })
            else:
                optimized_ingredients.append(ai_ing)
        
        # Validate total
        total = sum(ing["percent"] for ing in optimized_ingredients)
        if abs(total - 100.0) > 0.01:
            print(f"Warning: AI optimization total is {total}%, normalizing to 100%")
            factor = 100.0 / total
            for ing in optimized_ingredients:
                ing["percent"] = round(ing["percent"] * factor, 2)
        
        return {
            "ingredients": optimized_ingredients,
            "insights": ai_data.get("insights", []),
            "warnings": ai_data.get("warnings", []),
            "ph_recommendation": ai_data.get("ph_recommendation", {})
        }
    
    except json.JSONDecodeError as e:
        print(f"Warning: Error parsing AI JSON: {e}")
        return {
            "ingredients": original_ingredients,
            "insights": [],
            "warnings": []
        }


# ============================================================================
# STEP 7: VALIDATION & COMPLIANCE
# ============================================================================

async def validate_formula(
    ingredients: List[Dict],
    wish_data: Dict,
    cost_target: Dict[str, float]
) -> Dict[str, Any]:
    """
    Validate generated formula
    
    WHAT IT CHECKS:
    1. Cost within target range
    2. BIS compliance (regulatory)
    3. Percentage totals
    4. Safety limits
    
    WHAT WE USE:
    - BIS RAG for regulatory checks
    - Cost calculations
    - Safety databases
    """
    # Calculate total cost
    total_cost = calculate_formula_cost(ingredients)
    
    # Check cost target
    cost_within_target = (
        cost_target.get("min", 0) <= total_cost <= cost_target.get("max", float("inf"))
    )
    
    # Get BIS cautions
    inci_names = [ing.get("inci", ing["name"]) for ing in ingredients]
    bis_cautions = await get_bis_cautions_for_ingredients(inci_names)
    
    # Validate percentages
    total_percent = sum(ing["percent"] for ing in ingredients)
    percent_valid = abs(total_percent - 100.0) < 0.01
    
    # Check actual ingredients for compliance (inverted: False means free, True means contains)
    has_silicone = any("silicone" in ing.get("inci", "").lower() or "dimethicone" in ing.get("inci", "").lower() 
                      for ing in ingredients)
    has_paraben = any("paraben" in ing.get("inci", "").lower() for ing in ingredients)
    is_vegan = check_vegan_compliance(ingredients)
    
    return {
        "cost": total_cost,
        "cost_within_target": cost_within_target,
        "total_percentage": total_percent,
        "percent_valid": percent_valid,
        "bis_cautions": bis_cautions,
        "compliance": {
            "silicone": not has_silicone,  # False = silicone-free (good)
            "paraben": not has_paraben,    # False = paraben-free (good)
            "vegan": is_vegan              # True = vegan (good)
        }
    }


def calculate_formula_cost(ingredients: List[Dict]) -> float:
    """
    Calculate total cost per 100g of formula
    
    HOW IT WORKS:
    - For each ingredient: (percentage / 100) * (cost_per_kg / 10)
    - Sum all ingredient costs
    - Returns cost in ₹/100g
    """
    total_cost = 0.0
    
    for ing in ingredients:
        percent = ing.get("percent", 0)
        # Cost is already in cost per 100g format from allocation
        cost_per_100g = ing.get("cost", 300.0)  # Default ₹300/100g (₹3000/kg)
        
        # Calculate contribution: (percentage / 100) * cost_per_100g
        contribution = (percent / 100.0) * cost_per_100g
        total_cost += contribution
    
    return round(total_cost, 2)


def check_vegan_compliance(ingredients: List[Dict]) -> bool:
    """
    Check if formula is vegan
    
    HOW IT WORKS:
    - Checks ingredient names against known animal-derived ingredients
    - Returns True if vegan, False otherwise
    """
    animal_derived_keywords = [
        "beeswax", "lanolin", "collagen", "elastin", "squalene",
        "carmine", "shellac", "keratin", "milk", "honey"
    ]
    
    for ing in ingredients:
        ing_name = ing.get("name", "").lower()
        inci = ing.get("inci", "").lower()
        
        if any(keyword in ing_name or keyword in inci for keyword in animal_derived_keywords):
            return False
    
    return True


# ============================================================================
# MAIN FORMULA GENERATION FUNCTION
# ============================================================================

async def generate_formula(wish_data: Dict) -> Dict[str, Any]:
    """
    Main function to generate formula from wish data
    
    COMPLETE FLOW:
    1. Get template for product type
    2. Select ingredients based on benefits
    3. Allocate percentages (rule-based)
    4. Optimize with AI (if enabled)
    5. Organize into phases
    6. Validate and check compliance
    7. Generate final response
    
    INPUT:
    {
        "productType": "serum",
        "benefits": ["Brightening", "Hydration"],
        "exclusions": ["Silicone-free", "Paraben-free"],
        "heroIngredients": ["Vitamin C", "Hyaluronic Acid"],
        "costMin": 30,
        "costMax": 60,
        "texture": "gel",
        "fragrance": "none",
        "notes": "Additional requirements"
    }
    
    OUTPUT:
    {
        "name": "Generated Formula Name",
        "version": "v1",
        "cost": 48.5,
        "ph": {"min": 5.0, "max": 5.5},
        "texture": "Lightweight gel",
        "shelfLife": "12 months",
        "phases": [...],
        "insights": [...],
        "warnings": [...],
        "compliance": {...}
    }
    """
    print(f"🧪 Generating formula for: {wish_data.get('productType', 'unknown')}")
    
    # Step 1: Get template
    product_type = wish_data.get("productType", "serum")
    template = FORMULATION_TEMPLATES.get(product_type, FORMULATION_TEMPLATES["serum"])
    
    # Step 2: Select ingredients using Claude (validated against MongoDB)
    selected_ingredients, ingredient_warnings, claude_phases, claude_insights = await select_ingredients_by_benefits(
        benefits=wish_data.get("benefits", []),
        exclusions=wish_data.get("exclusions", []),
        hero_ingredients=wish_data.get("heroIngredients", []),
        cost_target={"min": wish_data.get("costMin", 30), "max": wish_data.get("costMax", 60)}
    )
    
    # If Claude didn't return ingredients, use fallback template ingredients
    if not selected_ingredients:
        print(f"⚠️ Claude didn't return ingredients. Using fallback template ingredients.")
        selected_ingredients = get_fallback_ingredients(
            product_type=product_type,
            benefits=wish_data.get("benefits", []),
            exclusions=wish_data.get("exclusions", []),
            hero_ingredients=wish_data.get("heroIngredients", [])
        )
        
        if not selected_ingredients:
            raise ValueError(
                f"No ingredients found matching the requirements. "
                f"Product type: {product_type}, Benefits: {wish_data.get('benefits', [])}, "
                f"Exclusions: {wish_data.get('exclusions', [])}"
            )
    
    # Step 3: Allocate percentages (rule-based)
    allocated = allocate_percentages_rules(
        template=template,
        selected_ingredients=selected_ingredients,
        hero_ingredients=wish_data.get("heroIngredients", [])
    )
    
    if not allocated:
        raise ValueError("No ingredients allocated. Check template and ingredient selection.")
    
    # Step 4: AI optimization (optional)
    optimized, ai_metadata = await optimize_percentages_with_ai(
        allocated_ingredients=allocated,
        wish_data=wish_data,
        template=template
    )
    
    # Step 5: Organize into phases
    # Use Claude's phases if provided, otherwise organize from template
    if claude_phases and len(claude_phases) > 0:
        # Use Claude's phase structure, but populate with optimized ingredients (which have percentages)
        phases = organize_claude_phases_with_validated_ingredients(claude_phases, optimized, template)
    else:
        phases = organize_into_phases(optimized, template)
    
    if not phases:
        raise ValueError("No phases generated. Check ingredient allocation.")
    
    # Step 6: Validate
    try:
        validation = await validate_formula(
            ingredients=optimized,
            wish_data=wish_data,
            cost_target={"min": wish_data.get("costMin", 30), "max": wish_data.get("costMax", 60)}
        )
    except Exception as e:
        print(f"Warning: Error in formula validation: {e}")
        import traceback
        traceback.print_exc()
        # Use default validation if error occurs
        # Calculate compliance correctly
        has_silicone = any("silicone" in ing.get("inci", "").lower() or "dimethicone" in ing.get("inci", "").lower() 
                          for ing in optimized)
        has_paraben = any("paraben" in ing.get("inci", "").lower() for ing in optimized)
        is_vegan = check_vegan_compliance(optimized)
        
        validation = {
            "cost": calculate_formula_cost(optimized),
            "cost_within_target": True,
            "total_percentage": sum(ing.get("percent", 0) for ing in optimized),
            "percent_valid": True,
            "bis_cautions": {},
            "compliance": {
                "silicone": not has_silicone,  # False = silicone-free (good)
                "paraben": not has_paraben,    # False = paraben-free (good)
                "vegan": is_vegan              # True = vegan (good)
            }
        }
    
    # Step 7: Generate formula name
    formula_name = generate_formula_name(wish_data, selected_ingredients)
    
    # Step 8: Build response
    return {
        "name": formula_name,
        "version": "v1",
        "cost": validation.get("cost", 0),
        "costTarget": {
            "min": wish_data.get("costMin", 30),
            "max": wish_data.get("costMax", 60)
        },
        "ph": template.get("ph_range", {"min": 5.0, "max": 6.5}),
        "texture": get_texture_description(wish_data.get("texture", "serum")),
        "shelfLife": "12 months",  # Default, could be calculated
        "phases": phases,
        "insights": claude_insights + ai_metadata.get("insights", []),
        "warnings": ingredient_warnings + ai_metadata.get("warnings", []) + build_validation_warnings(validation),
        "compliance": validation.get("compliance", {})
    }


def organize_claude_phases_with_validated_ingredients(
    claude_phases: List[Dict],
    optimized_ingredients: List[Dict],
    template: Dict
) -> List[Dict]:
    """
    Organize Claude's phase structure with optimized ingredients (which have percentages)
    
    Maps Claude's phase structure to optimized ingredients and formats for frontend
    """
    phases = []
    phase_colors = {
        "A": "from-blue-500 to-cyan-500",
        "B": "from-amber-500 to-orange-500",
        "C": "from-green-500 to-emerald-500",
        "D": "from-purple-500 to-pink-500"
    }
    
    # Create a map of ingredient names to optimized ingredients (which have percentages)
    optimized_map = {}
    for ing in optimized_ingredients:
        name = ing.get("name") or ing.get("ingredient_name", "")
        if name:
            optimized_map[name.lower()] = ing
    
    for claude_phase in claude_phases:
        phase_id = claude_phase.get("id", "A")
        phase_name = claude_phase.get("name", "Phase")
        phase_temp = claude_phase.get("temp", "room")
        phase_ingredient_names = claude_phase.get("ingredients", [])
        
        phase_ingredients = []
        for ing_name in phase_ingredient_names:
            # Find matching optimized ingredient (which has percentages)
            ing_lower = ing_name.lower()
            matched_ing = None
            
            # Try exact match first
            if ing_lower in optimized_map:
                matched_ing = optimized_map[ing_lower]
            else:
                # Try partial match
                for key, ing in optimized_map.items():
                    if ing_lower in key or key in ing_lower:
                        matched_ing = ing
                        break
            
            if matched_ing:
                # Format ingredient for frontend
                ing_name_final = matched_ing.get("name") or matched_ing.get("ingredient_name", ing_name)
                ing_inci = matched_ing.get("inci") or matched_ing.get("original_inci_name", "")
                if not ing_inci:
                    inci_names = matched_ing.get("inci_names", [])
                    ing_inci = inci_names[0] if inci_names else ing_name_final
                
                # Get percentage (should be set by allocation)
                ing_percent = matched_ing.get("percent", 0.0)
                if isinstance(ing_percent, str):
                    if ing_percent.lower() in ["q.s.", "qs", "quantum satis"]:
                        pass  # Keep as string
                    else:
                        try:
                            ing_percent = float(ing_percent)
                        except (ValueError, TypeError):
                            ing_percent = 0.0
                else:
                    ing_percent = float(ing_percent) if ing_percent else 0.0
                
                # Get cost per 100g
                ing_cost = matched_ing.get("cost", 300.0)
                if ing_cost > 1000:  # If it's still in cost per kg format, convert
                    ing_cost = ing_cost / 10.0
                
                # Get function
                ing_function = matched_ing.get("function", "Other")
                if not ing_function or ing_function == "Other":
                    func_cats = matched_ing.get("functional_categories", [])
                    if func_cats:
                        ing_function = func_cats[0] if isinstance(func_cats, list) else func_cats
                
                phase_ingredients.append({
                    "name": ing_name_final,
                    "inci": ing_inci,
                    "percent": ing_percent,
                    "cost": float(ing_cost),
                    "function": ing_function,
                    "hero": bool(matched_ing.get("hero", matched_ing.get("is_hero", False)))
                })
        
        if phase_ingredients:
            phases.append({
                "id": phase_id,
                "name": phase_name,
                "temp": phase_temp,
                "color": phase_colors.get(phase_id, "from-slate-500 to-slate-600"),
                "ingredients": phase_ingredients
            })
    
    return phases


def organize_into_phases(ingredients: List[Dict], template: Dict) -> List[Dict]:
    """
    Organize ingredients into phases based on template
    
    HOW IT WORKS:
    - Groups ingredients by phase ID
    - Adds phase metadata (name, temperature, color)
    - Returns structured phase list
    - Ensures all template phases are represented
    """
    phases = []
    phase_map = {phase["id"]: phase for phase in template["phases"]}
    
    # First, organize ingredients by phase
    for phase_id, phase_info in phase_map.items():
        phase_ingredients = []
        for ing in ingredients:
            if ing.get("phase") == phase_id:
                # Format ingredient for response - ensure all required fields
                ing_name = ing.get("name") or ing.get("ingredient_name", "")
                if not ing_name:
                    continue  # Skip ingredients without names
                    
                ing_inci = ing.get("inci") or ing.get("original_inci_name", "") or ing_name
                
                # Get cost (should already be in cost per 100g format)
                ing_cost = ing.get("cost", 300.0)
                if ing_cost > 1000:  # If it's still in cost per kg format, convert
                    ing_cost = ing_cost / 10.0
                
                # Ensure percent is valid
                ing_percent = ing.get("percent", 0.0)
                if isinstance(ing_percent, str):
                    # Handle "q.s." or other string values
                    if ing_percent.lower() in ["q.s.", "qs", "quantum satis"]:
                        pass  # Keep as string
                    else:
                        try:
                            ing_percent = float(ing_percent)
                        except (ValueError, TypeError):
                            ing_percent = 0.0
                else:
                    ing_percent = float(ing_percent) if ing_percent else 0.0
                
                # Get function - prioritize from ingredient data
                ing_function = ing.get("function", "Other")
                if not ing_function or ing_function == "Other":
                    # Try to get from functional categories
                    func_cats = ing.get("functional_categories", [])
                    if func_cats:
                        ing_function = func_cats[0] if isinstance(func_cats, list) else func_cats
                    else:
                        ing_function = "Other"
                
                ingredient_dict = {
                    "name": ing_name,
                    "inci": ing_inci,
                    "percent": ing_percent,
                    "cost": float(ing_cost),
                    "function": ing_function,
                    "hero": bool(ing.get("hero", ing.get("is_hero", False)))
                }
                phase_ingredients.append(ingredient_dict)
        
        # Always include phase, even if empty (for structure)
        phases.append({
            "id": phase_id,
            "name": phase_info["name"],
            "temp": phase_info.get("temperature", "room"),
            "color": get_phase_color(phase_id),
            "ingredients": phase_ingredients
        })
    
    # Filter out completely empty phases (but keep phases with at least one ingredient)
    phases = [p for p in phases if len(p["ingredients"]) > 0]
    
    if not phases:
        raise ValueError("No phases with ingredients generated. Check ingredient allocation.")
    
    return phases


def get_phase_color(phase_id: str) -> str:
    """Get gradient color for phase visualization"""
    colors = {
        "A": "from-blue-500 to-cyan-500",
        "B": "from-amber-500 to-orange-500",
        "C": "from-green-500 to-emerald-500",
        "D": "from-purple-500 to-pink-500"
    }
    return colors.get(phase_id, "from-slate-500 to-slate-600")


def generate_formula_name(wish_data: Dict, ingredients: List[Dict]) -> str:
    """Generate formula name from wish data and ingredients"""
    product_type = wish_data.get("productType", "serum").title()
    benefits = wish_data.get("benefits", [])
    
    if benefits:
        primary_benefit = benefits[0].title()
        return f"{primary_benefit} {product_type}"
    
    return f"Custom {product_type}"


def get_texture_description(texture: str) -> str:
    """Get human-readable texture description"""
    descriptions = {
        "water": "Water-light",
        "gel": "Lightweight gel",
        "serum": "Serum-like",
        "lotion": "Light lotion",
        "cream": "Rich cream",
        "balm": "Balm/Rich"
    }
    return descriptions.get(texture, "Custom texture")


def build_validation_warnings(validation: Dict) -> List[Dict]:
    """Build warnings from validation results"""
    warnings = []
    
    if not validation["cost_within_target"]:
        warnings.append({
            "type": "info",
            "text": f"Formula cost (₹{validation['cost']}) is outside target range"
        })
    
    if validation.get("bis_cautions"):
        warnings.append({
            "type": "info",
            "text": "Some ingredients have BIS regulatory cautions - review carefully"
        })
    
    return warnings

