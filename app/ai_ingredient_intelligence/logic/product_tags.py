"""
Product tags system - stores and manages all available tags
"""
from typing import List, Dict, Any
from app.ai_ingredient_intelligence.db.collections import product_tags_col


# Predefined tags organized by category
TAGS_DATA = {
    "market_position": {
        "category_name": "Market Position",
        "description": "Product positioning in the market",
        "tags": {
            "mass-market": "Wide distribution, affordable pricing",
            "premium": "Higher price point, quality positioning",
            "luxury": "Ultra-premium, exclusive positioning",
            "budget-friendly": "Value-focused, entry-level pricing",
            "mid-range": "Balanced price-quality ratio",
            "professional": "Salon/dermat-grade products",
            "pharmacy": "Sold through pharmacy channels",
            "d2c-native": "Direct-to-consumer born brands",
            "international": "Global brands available in India",
            "homegrown": "Indian origin brands"
        }
    },
    "brand_positioning": {
        "category_name": "Brand Positioning",
        "description": "Brand identity and positioning",
        "tags": {
            "clean-beauty": "Free from controversial ingredients",
            "natural": "Plant-derived, nature-inspired",
            "organic": "Certified organic ingredients",
            "ayurvedic": "Based on Ayurvedic principles",
            "clinical": "Science-backed, dermatologist-developed",
            "k-beauty": "Korean beauty influenced",
            "j-beauty": "Japanese beauty influenced",
            "french-pharmacy": "French dermocosmetic tradition",
            "indie": "Independent, small-batch brand",
            "legacy": "Established heritage brand"
        }
    },
    "claims": {
        "category_name": "Claims",
        "description": "Product claims and certifications",
        "tags": {
            "toxin-free-claims": "Markets as free from 'toxins'",
            "paraben-free": "No parabens",
            "sulfate-free": "No sulfates (SLS/SLES)",
            "silicone-free": "No silicones",
            "fragrance-free": "Unscented/no added fragrance",
            "alcohol-free": "No drying alcohols",
            "mineral-oil-free": "No mineral oil/petrolatum",
            "phthalate-free": "No phthalates",
            "formaldehyde-free": "No formaldehyde releasers",
            "essential-oil-free": "No essential oils",
            "fungal-acne-safe": "Malassezia-safe formulation",
            "non-comedogenic": "Won't clog pores",
            "hypoallergenic": "Reduced allergen risk",
            "dermatologist-tested": "Tested by dermatologists",
            "clinically-proven": "Clinical study backed",
            "ph-balanced": "Optimized pH level"
        }
    },
    "ethics_sustainability": {
        "category_name": "Ethics & Sustainability",
        "description": "Ethical and sustainability attributes",
        "tags": {
            "vegan": "No animal-derived ingredients",
            "cruelty-free": "No animal testing",
            "leaping-bunny": "Leaping Bunny certified",
            "peta-certified": "PETA cruelty-free certified",
            "sustainable": "Eco-conscious practices",
            "recyclable-packaging": "Recyclable containers",
            "refillable": "Refill system available",
            "zero-waste": "Minimal/no waste packaging",
            "carbon-neutral": "Carbon offset/neutral",
            "ocean-friendly": "Reef-safe, ocean-safe",
            "biodegradable": "Biodegradable formula",
            "upcycled-ingredients": "Uses upcycled materials",
            "fair-trade": "Fair trade sourced",
            "waterless": "Concentrated/water-free"
        }
    },
    "formulation": {
        "category_name": "Formulation",
        "description": "Formulation characteristics",
        "tags": {
            "high-concentration": "High % of active ingredients",
            "low-concentration": "Gentle, lower actives",
            "multi-active": "Multiple active ingredients",
            "single-active": "One hero ingredient focus",
            "minimalist-formula": "Short ingredient list",
            "complex-formula": "Multi-ingredient sophisticated formula",
            "patented-technology": "Proprietary technology",
            "encapsulated": "Encapsulated actives",
            "time-release": "Slow-release technology",
            "waterless-formula": "Anhydrous formulation",
            "oil-based": "Oil-dominant formula",
            "water-based": "Water-dominant formula",
            "gel-based": "Gel texture",
            "cream-based": "Cream texture",
            "serum-texture": "Lightweight serum",
            "balm-texture": "Rich balm consistency"
        }
    },
    "consumer_perception": {
        "category_name": "Consumer Perception",
        "description": "How consumers perceive the product",
        "tags": {
            "cult-favorite": "Strong loyal following",
            "bestseller": "Top-selling product",
            "award-winning": "Industry awards received",
            "viral": "Social media viral product",
            "tiktok-famous": "Popular on TikTok",
            "instagram-favorite": "Instagram popular",
            "influencer-recommended": "Influencer endorsed",
            "dermat-recommended": "Dermatologist recommended",
            "editor-pick": "Beauty editor favorite",
            "hidden-gem": "Underrated quality product",
            "dupe": "Affordable alternative to luxury",
            "splurge-worthy": "Worth the premium price",
            "holy-grail": "Highly repurchased staple",
            "newlaunch": "Recently launched",
            "reformulated": "Updated formula",
            "discontinued-risk": "May be discontinued"
        }
    },
    "skin_concerns": {
        "category_name": "Skin Concerns",
        "description": "Targeted skin concerns (Skincare)",
        "tags": {
            "anti-aging": "Targets aging signs",
            "brightening": "Targets pigmentation/dullness",
            "hydrating": "Moisture-focused",
            "acne-fighting": "Targets breakouts",
            "pore-minimizing": "Reduces pore appearance",
            "oil-control": "Manages sebum",
            "soothing": "Calms irritation",
            "barrier-repair": "Strengthens skin barrier",
            "exfoliating": "Chemical/physical exfoliation",
            "firming": "Improves skin firmness",
            "dark-circle": "Targets under-eye concerns",
            "sun-protection": "UV protection",
            "post-procedure": "For post-treatment care",
            "sensitive-skin": "Gentle for sensitivity",
            "redness-reducing": "Targets rosacea/redness"
        }
    },
    "hair_concerns": {
        "category_name": "Hair Concerns",
        "description": "Targeted hair concerns (Haircare)",
        "tags": {
            "hair-fall-control": "Reduces hair fall",
            "hair-growth": "Promotes growth",
            "dandruff-control": "Anti-dandruff",
            "frizz-control": "Manages frizz",
            "smoothening": "Smooths hair texture",
            "volumizing": "Adds volume/body",
            "color-safe": "Safe for colored hair",
            "heat-protection": "Protects from heat styling",
            "bond-repair": "Repairs hair bonds",
            "protein-treatment": "Protein-rich formula",
            "moisture-treatment": "Deep hydration",
            "scalp-care": "Focuses on scalp health",
            "curl-defining": "For curly/wavy hair",
            "straightening": "For straight hair maintenance",
            "grey-coverage": "Covers grey hair",
            "keratin-infused": "Contains keratin"
        }
    },
    "ingredient_highlights": {
        "category_name": "Ingredient Highlights",
        "description": "Key ingredients in the product",
        "tags": {
            "vitamin-c": "Contains Vitamin C",
            "retinol": "Contains retinoids",
            "niacinamide": "Contains Vitamin B3",
            "hyaluronic-acid": "Contains HA",
            "salicylic-acid": "Contains BHA",
            "glycolic-acid": "Contains AHA",
            "peptides": "Contains peptides",
            "ceramides": "Contains ceramides",
            "squalane": "Contains squalane",
            "bakuchiol": "Contains bakuchiol",
            "centella": "Contains Centella Asiatica",
            "snail-mucin": "Contains snail secretion",
            "fermented": "Fermented ingredients",
            "probiotic": "Contains probiotics",
            "cbd": "Contains cannabidiol",
            "rice": "Rice-based ingredients",
            "turmeric": "Contains turmeric",
            "tea-tree": "Contains tea tree oil",
            "argan-oil": "Contains argan oil",
            "coconut": "Coconut-derived",
            "biotin": "Contains biotin",
            "caffeine": "Contains caffeine",
            "onion": "Contains onion extract"
        }
    },
    "price_perception": {
        "category_name": "Price Perception",
        "description": "Price range categories",
        "tags": {
            "under-500": "Priced under ₹500",
            "under-1000": "Priced under ₹1000",
            "1000-2000": "Priced ₹1000-2000",
            "above-2000": "Priced above ₹2000",
            "value-pack": "Multi-pack/value size",
            "mini-size": "Travel/trial size",
            "subscription": "Subscription available"
        }
    },
    "channel": {
        "category_name": "Channel",
        "description": "Distribution channels",
        "tags": {
            "nykaa-exclusive": "Only on Nykaa",
            "amazon-exclusive": "Only on Amazon",
            "brand-website-only": "D2C only",
            "salon-exclusive": "Salon distribution",
            "offline-available": "Available in stores",
            "quick-commerce": "On Blinkit/Zepto/Instamart"
        }
    }
}


async def initialize_tags():
    """Initialize tags in database if not exists"""
    existing = await product_tags_col.find_one({"version": "1.0"})
    
    if not existing:
        # Convert to list format for storage
        categories = []
        for category_key, category_data in TAGS_DATA.items():
            tags_list = [
                {"tag": tag, "description": desc}
                for tag, desc in category_data["tags"].items()
            ]
            categories.append({
                "category_name": category_data["category_name"],
                "description": category_data["description"],
                "tags": tags_list
            })
        
        await product_tags_col.insert_one({
            "version": "1.0",
            "categories": categories,
            "created_at": "2024-12-01"
        })


async def get_all_tags() -> List[Dict[str, Any]]:
    """Get all tags organized by category"""
    tags_doc = await product_tags_col.find_one({"version": "1.0"})
    
    if not tags_doc:
        # Initialize if not exists
        await initialize_tags()
        tags_doc = await product_tags_col.find_one({"version": "1.0"})
    
    return tags_doc.get("categories", [])


async def validate_tags(tags: List[str]) -> Dict[str, Any]:
    """Validate tags against available tags"""
    all_tags_doc = await product_tags_col.find_one({"version": "1.0"})
    
    if not all_tags_doc:
        await initialize_tags()
        all_tags_doc = await product_tags_col.find_one({"version": "1.0"})
    
    # Get all valid tags
    valid_tags = set()
    for category in all_tags_doc.get("categories", []):
        for tag_item in category.get("tags", []):
            valid_tags.add(tag_item["tag"])
    
    # Validate input tags
    invalid_tags = [tag for tag in tags if tag not in valid_tags]
    valid_input_tags = [tag for tag in tags if tag in valid_tags]
    
    return {
        "valid": valid_input_tags,
        "invalid": invalid_tags,
        "all_valid_tags": list(valid_tags)
    }

