"""
Make A Wish Configuration Data
===============================

This module contains all the configuration data for the revised Make A Wish flow,
including complexity configurations, texture mappings, and ingredient alternatives.
"""

# ============================================================================
# COMPLEXITY CONFIGURATION
# ============================================================================

COMPLEXITY_CONFIG = {
    "minimalist": {
        "max_ingredients": 8,
        "active_slots": 1,
        "include_sensorials": False,
        "base_ingredients": ["water", "humectant", "preservative", "ph_adjuster"],
        "cost_target_multiplier": 0.7,  # Lower cost target
        "description": "Clean, essential ingredients only",
        "emoji": "🌿",
        "name": "Minimalist",
        "highlights": ["5-8 ingredients", "Clean label friendly", "Essential actives only"],
        "marketing_angle": "Pure and simple - just what your skin needs"
    },
    "classic": {
        "max_ingredients": 14,
        "active_slots": 3,
        "include_sensorials": True,
        "base_ingredients": [
            "water", "humectant", "penetration_enhancer", 
            "preservative", "chelating_agent", "ph_adjuster", 
            "thickener", "texture_enhancer"
        ],
        "cost_target_multiplier": 1.0,  # Standard cost
        "description": "Well-rounded formula with proven efficacy",
        "emoji": "⚖️",
        "name": "Classic",
        "highlights": ["10-14 ingredients", "Proven actives", "Balanced formulation"],
        "marketing_angle": "The perfect balance of nature and science"
    },
    "luxe": {
        "max_ingredients": 22,
        "active_slots": 5,
        "include_sensorials": True,
        "base_ingredients": [
            "water", "humectant", "penetration_enhancer",
            "secondary_humectant", "preservative", "chelating_agent",
            "antioxidant_stabilizer", "ph_adjuster", "thickener",
            "texture_enhancer_1", "texture_enhancer_2", 
            "sensory_modifier", "botanical_extract"
        ],
        "cost_target_multiplier": 1.5,  # Higher cost allowed
        "description": "Multi-active powerhouse with beautiful sensorials",
        "emoji": "✨",
        "name": "Luxe",
        "highlights": ["15-22 ingredients", "Premium actives", "Luxurious experience"],
        "marketing_angle": "Indulge in the ultimate skincare experience"
    }
}

# ============================================================================
# AUTO-TEXTURE CONFIGURATION
# ============================================================================

AUTO_TEXTURE_MAP = {
    "serum": {
        "texture_id": "watery",
        "label": "Light & Fast-Absorbing",
        "viscosity_target": "low",
        "thickener_level": "minimal"
    },
    "moisturizer": {
        "texture_id": "cream", 
        "label": "Rich & Nourishing",
        "viscosity_target": "high",
        "thickener_level": "standard"
    },
    "cleanser": {
        "texture_id": "gel",
        "label": "Gentle & Effective",
        "viscosity_target": "medium",
        "thickener_level": "moderate"
    },
    "sunscreen": {
        "texture_id": "lotion",
        "label": "Lightweight & Protective",
        "viscosity_target": "medium",
        "thickener_level": "moderate"
    },
    "toner": {
        "texture_id": "watery",
        "label": "Refreshing & Hydrating",
        "viscosity_target": "very_low",
        "thickener_level": "none"
    },
    "face-oil": {
        "texture_id": "oil",
        "label": "Luxuriously Nourishing",
        "viscosity_target": "medium",
        "thickener_level": "none"
    },
    "hair-oil": {
        "texture_id": "oil",
        "label": "Deeply Nourishing",
        "viscosity_target": "medium",
        "thickener_level": "none"
    },
    "shampoo": {
        "texture_id": "liquid",
        "label": "Cleansing & Caring",
        "viscosity_target": "medium",
        "thickener_level": "standard"
    },
    "conditioner": {
        "texture_id": "cream",
        "label": "Smooth & Silky",
        "viscosity_target": "high",
        "thickener_level": "standard"
    }
}

# ============================================================================
# INGREDIENT ALTERNATIVES DATABASE
# ============================================================================

INGREDIENT_ALTERNATIVES = {
    "Vitamin C": {
        "category": "brightening_antioxidant",
        "variants": [
            {
                "name": "Sodium Ascorbyl Phosphate (SAP)",
                "inci": "Sodium Ascorbyl Phosphate",
                "benefit": "Stable, gentle",
                "percentage": "3-5%",
                "complexity": ["minimalist", "classic", "luxe"],
                "cost_tier": "mid",
                "emoji": "🍊",
                "description": "Most stable Vitamin C derivative, gentle on skin",
                "benefit_tag": "Stable & gentle",
                "cost_impact": "similar",
                "considerations": "pH 6-7 for best stability"
            },
            {
                "name": "Ascorbyl Glucoside",
                "inci": "Ascorbyl Glucoside", 
                "benefit": "Most stable form",
                "percentage": "2-5%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "mid",
                "emoji": "🍋",
                "description": "Converts to Vitamin C in skin, very stable",
                "benefit_tag": "Ultra-stable",
                "cost_impact": "similar",
                "considerations": "Works at pH 5-7"
            },
            {
                "name": "Ethyl Ascorbic Acid",
                "inci": "3-O-Ethyl Ascorbic Acid",
                "benefit": "Quick results",
                "percentage": "1-3%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "high",
                "emoji": "⚡",
                "description": "New generation Vitamin C with better penetration",
                "benefit_tag": "Fast-acting",
                "cost_impact": "higher",
                "considerations": "More expensive but highly effective"
            },
            {
                "name": "Kakadu Plum Extract",
                "inci": "Terminalia Ferdinandiana Fruit Extract",
                "benefit": "Natural & potent",
                "percentage": "1-2%",
                "complexity": ["luxe"],
                "cost_tier": "premium",
                "emoji": "🌺",
                "description": "World's highest natural Vitamin C content",
                "benefit_tag": "Natural superfood",
                "cost_impact": "higher",
                "considerations": "Natural source, may affect color"
            }
        ]
    },
    "Retinol": {
        "category": "anti_aging",
        "variants": [
            {
                "name": "Retinol",
                "inci": "Retinol",
                "benefit": "Gold standard",
                "percentage": "0.3-1%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "mid",
                "emoji": "👑",
                "description": "The original and most studied retinoid",
                "benefit_tag": "Gold standard",
                "cost_impact": "similar",
                "considerations": "Can be irritating, start low"
            },
            {
                "name": "Bakuchiol",
                "inci": "Bakuchiol",
                "benefit": "Gentle, suitable for sensitive skin",
                "percentage": "0.5-2%",
                "complexity": ["minimalist", "classic", "luxe"],
                "cost_tier": "mid",
                "emoji": "🌿",
                "description": "Natural retinol alternative with similar benefits",
                "benefit_tag": "Natural alternative",
                "cost_impact": "similar",
                "considerations": "Gentle alternative, less irritating"
            },
            {
                "name": "Granactive Retinoid",
                "inci": "Hydroxypinacolone Retinoate",
                "benefit": "Less irritating",
                "percentage": "0.5-2%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "high",
                "emoji": "🚀",
                "description": "New generation retinoid with lower irritation",
                "benefit_tag": "Advanced retinoid",
                "cost_impact": "higher",
                "considerations": "Patented ingredient, premium cost"
            },
            {
                "name": "Physavie®",
                "inci": "Withania Somnifera Root Extract",
                "benefit": "Ayurvedic alternative",
                "percentage": "1-3%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "high",
                "emoji": "🌱",
                "description": "Ayurvedic herb with retinol-like benefits",
                "benefit_tag": "Ayurvedic wisdom",
                "cost_impact": "higher",
                "considerations": "Traditional ingredient, modern validation"
            }
        ]
    },
    "Niacinamide": {
        "category": "multi_benefit",
        "variants": [
            {
                "name": "Niacinamide",
                "inci": "Niacinamide",
                "benefit": "Multi-tasking vitamin",
                "percentage": "2-5%",
                "complexity": ["minimalist", "classic", "luxe"],
                "cost_tier": "low",
                "emoji": "💎",
                "description": "Vitamin B3 with multiple skin benefits",
                "benefit_tag": "Multi-benefit",
                "cost_impact": "lower",
                "considerations": "Well-tolerated, pH 5-7"
            },
            {
                "name": "Nicotinoyl Tripeptide-1",
                "inci": "Nicotinoyl Tripeptide-1",
                "benefit": "Enhanced delivery",
                "percentage": "1-3%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "high",
                "emoji": "🎯",
                "description": "Peptide form of niacinamide with better penetration",
                "benefit_tag": "Advanced peptide",
                "cost_impact": "higher",
                "considerations": "More bioavailable form"
            }
        ]
    },
    "Hyaluronic Acid": {
        "category": "hydration",
        "variants": [
            {
                "name": "Sodium Hyaluronate",
                "inci": "Sodium Hyaluronate",
                "benefit": "Classic hydrator",
                "percentage": "0.1-1%",
                "complexity": ["minimalist", "classic", "luxe"],
                "cost_tier": "low",
                "emoji": "💧",
                "description": "Sodium salt of hyaluronic acid",
                "benefit_tag": "Essential hydration",
                "cost_impact": "lower",
                "considerations": "Different molecular weights available"
            },
            {
                "name": "Hydrolyzed Sodium Hyaluronate",
                "inci": "Hydrolyzed Sodium Hyaluronate",
                "benefit": "Deep penetration",
                "percentage": "0.1-0.5%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "mid",
                "emoji": "🔬",
                "description": "Low molecular weight for deeper penetration",
                "benefit_tag": "Deep hydration",
                "cost_impact": "similar",
                "considerations": "Smaller molecules penetrate deeper"
            },
            {
                "name": "Sodium Hyaluronate Crosspolymer",
                "inci": "Sodium Hyaluronate Crosspolymer",
                "benefit": "Film-forming",
                "percentage": "0.1-0.3%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "mid",
                "emoji": "🛡️",
                "description": "Forms protective film on skin",
                "benefit_tag": "Long-lasting",
                "cost_impact": "similar",
                "considerations": "Creates breathable barrier"
            }
        ]
    },
    "Peptides": {
        "category": "anti_aging",
        "variants": [
            {
                "name": "Matrixyl 3000",
                "inci": "Palmitoyl Tripeptide-1, Palmitoyl Tetrapeptide-7",
                "benefit": "Collagen booster",
                "percentage": "2-6%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "high",
                "emoji": "🔷",
                "description": "Signature peptide complex for anti-aging",
                "benefit_tag": "Proven anti-aging",
                "cost_impact": "higher",
                "considerations": "Patented blend, well-studied"
            },
            {
                "name": "Argireline",
                "inci": "Acetyl Hexapeptide-8",
                "benefit": "Botox alternative",
                "percentage": "5-10%",
                "complexity": ["classic", "luxe"],
                "cost_tier": "high",
                "emoji": "✨",
                "description": "Peptide that mimics Botox effects",
                "benefit_tag": "Relaxing peptide",
                "cost_impact": "higher",
                "considerations": "High concentration needed"
            },
            {
                "name": "Copper Tripeptide-1",
                "inci": "Copper Tripeptide-1",
                "benefit": "Wound healing",
                "percentage": "0.5-2%",
                "complexity": ["luxe"],
                "cost_tier": "premium",
                "emoji": "🌟",
                "description": "Copper-containing peptide for skin repair",
                "benefit_tag": "Skin repair",
                "cost_impact": "higher",
                "considerations": "Blue tint may affect product color"
            }
        ]
    }
}

# ============================================================================
# EDIT RULES ENGINE
# ============================================================================

EDIT_RULES = {
    "cannot_remove": [
        "preservative",
        "ph_adjuster", 
        "water"
    ],
    "warn_on_remove": [
        "chelating_agent",
        "antioxidant_stabilizer"
    ],
    "complexity_limits": {
        "minimalist": {"max_total": 8, "max_actives": 1},
        "classic": {"max_total": 14, "max_actives": 3},
        "luxe": {"max_total": 22, "max_actives": 5}
    },
    "rebalance_on_edit": True,  # Auto-rebalance percentages after edits
    "require_revalidation": ["compliance", "compatibility"]
}

# ============================================================================
# COMPATIBILITY CHECKS
# ============================================================================

COMPATIBILITY_RULES = {
    "critical_conflicts": [
        {
            "ingredients": ["Vitamin C", "Retinol"],
            "issue": "pH conflict - Vitamin C needs low pH, Retinol needs neutral pH",
            "solution": "Use Vitamin C derivative or separate applications"
        },
        {
            "ingredients": ["Vitamin C", "AHA/BHA"],
            "issue": "Over-exfoliation risk and pH conflict",
            "solution": "Use on alternate days or choose one"
        },
        {
            "ingredients": ["Retinol", "AHA/BHA"],
            "issue": "High irritation potential",
            "solution": "Use on alternate nights or lower concentrations"
        }
    ],
    "warnings": [
        {
            "ingredients": ["Niacinamide", "Vitamin C"],
            "issue": "Historically debated but now considered safe",
            "solution": "Can be used together, monitor for sensitivity"
        }
    ]
}

# ============================================================================
# QUEUE NUMBER GENERATION
# ============================================================================

def generate_queue_number():
    """Generate queue number: FLX-YYMMDD-XXX"""
    from datetime import datetime
    import random
    
    prefix = "FLX"
    date_part = datetime.now().strftime("%y%m%d")
    
    # For demo purposes, generate random sequence
    # In production, this would query database for today's count
    sequence = str(random.randint(1, 999)).zfill(3)
    
    return f"{prefix}-{date_part}-{sequence}"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_complexity_config(complexity_id):
    """Get complexity configuration by ID"""
    return COMPLEXITY_CONFIG.get(complexity_id)

def get_texture_for_product_type(product_type):
    """Get auto-detected texture for product type"""
    return AUTO_TEXTURE_MAP.get(product_type, {
        "texture_id": "gel",
        "label": "Balanced Texture",
        "viscosity_target": "medium",
        "thickener_level": "moderate"
    })

def get_alternatives_for_ingredient(ingredient_name):
    """Get alternatives for an ingredient"""
    return INGREDIENT_ALTERNATIVES.get(ingredient_name)

def check_compatibility(ingredients):
    """Check ingredient compatibility"""
    issues = []
    ingredient_names = [ing.lower() for ing in ingredients]
    
    for conflict in COMPATIBILITY_RULES["critical_conflicts"]:
        if all(conflict_ingredient.lower() in ingredient_names 
               for conflict_ingredient in conflict["ingredients"]):
            issues.append({
                "severity": "critical",
                **conflict
            })
    
    for warning in COMPATIBILITY_RULES["warnings"]:
        if all(warning_ingredient.lower() in ingredient_names 
               for warning_ingredient in warning["ingredients"]):
            issues.append({
                "severity": "warning",
                **warning
            })
    
    return issues
