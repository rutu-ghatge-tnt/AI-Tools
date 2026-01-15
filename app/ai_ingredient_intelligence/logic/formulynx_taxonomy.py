"""
Formulynx Canonical Taxonomy
============================

Hierarchical Structure:
TARGET AREA → CONCERN → BENEFIT → PRODUCT TYPE → FORM → PRICE TIER

Key Distinction:
- FORM = Physical state/texture (cream, gel, oil, spray, etc.)
- PRODUCT TYPE = Functional category (cleanser, moisturizer, sunscreen, etc.)
"""

from typing import Optional, List, Dict, Any
import json
from pathlib import Path

# Load enhanced taxonomy data from Excel workbook
ENHANCED_TAXONOMY_PATH = Path(__file__).parent.parent.parent.parent / "enhanced_formulynx_taxonomy.json"

def load_enhanced_taxonomy():
    """Load enhanced taxonomy data from JSON file"""
    try:
        with open(ENHANCED_TAXONOMY_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Enhanced taxonomy file not found at {ENHANCED_TAXONOMY_PATH}")
        return {}
    except Exception as e:
        print(f"Error loading enhanced taxonomy: {e}")
        return {}

# Load enhanced taxonomy data
ENHANCED_FORMULYNX_TAXONOMY = load_enhanced_taxonomy()

FORMULYNX_CANONICAL_TAXONOMY = {
    # ═══════════════════════════════════════════════════════════════════════════
    # UNIVERSAL FORMS (Physical state - applies across all categories)
    # ═══════════════════════════════════════════════════════════════════════════
    "forms": {
        # ─────────────── CREAMY/RICH TEXTURES ───────────────
        "cream": {
            "label": "Cream",
            "icon": "🧴",
            "description": "Rich, emollient semi-solid",
            "texture_feel": "rich"
        },
        "lotion": {
            "label": "Lotion",
            "icon": "🥛",
            "description": "Lightweight, pourable emulsion",
            "texture_feel": "light"
        },
        "milk": {
            "label": "Milk",
            "icon": "🥛",
            "description": "Light, milky liquid emulsion",
            "texture_feel": "light"
        },
        "balm": {
            "label": "Balm",
            "icon": "🫙",
            "description": "Thick, waxy, highly occlusive",
            "texture_feel": "rich"
        },
        "butter": {
            "label": "Butter",
            "icon": "🧈",
            "description": "Whipped, rich, creamy texture",
            "texture_feel": "rich"
        },
        "ointment": {
            "label": "Ointment",
            "icon": "💊",
            "description": "Very occlusive, petroleum-based",
            "texture_feel": "rich"
        },
        "pomade": {
            "label": "Pomade",
            "icon": "🫙",
            "description": "Waxy, shiny, heavy hold",
            "texture_feel": "rich"
        },
        "paste": {
            "label": "Paste",
            "icon": "🎨",
            "description": "Thick, clay-like consistency",
            "texture_feel": "rich"
        },
        # ─────────────── LIQUID/WATERY TEXTURES ───────────────
        "gel": {
            "label": "Gel",
            "icon": "💧",
            "description": "Water-based, lightweight, clear/translucent",
            "texture_feel": "light"
        },
        "serum": {
            "label": "Serum",
            "icon": "💎",
            "description": "Concentrated liquid, fast-absorbing",
            "texture_feel": "light"
        },
        "essence": {
            "label": "Essence",
            "icon": "✨",
            "description": "Watery, ultra-fast absorbing",
            "texture_feel": "watery"
        },
        "toner": {
            "label": "Toner/Tonic",
            "icon": "💦",
            "description": "Liquid, prep/treatment step",
            "texture_feel": "watery"
        },
        "ampoule": {
            "label": "Ampoule",
            "icon": "💉",
            "description": "Highly concentrated, single-dose treatment",
            "texture_feel": "light"
        },
        "water": {
            "label": "Water/Micellar",
            "icon": "🌊",
            "description": "Cleansing or treatment liquid",
            "texture_feel": "watery"
        },
        "emulsion": {
            "label": "Emulsion",
            "icon": "🌫️",
            "description": "Light lotion, between toner & cream",
            "texture_feel": "light"
        },
        "fluid": {
            "label": "Fluid",
            "icon": "💧",
            "description": "Ultra-lightweight liquid",
            "texture_feel": "watery"
        },
        "drops": {
            "label": "Drops/Concentrate",
            "icon": "💧",
            "description": "Concentrated liquid drops",
            "texture_feel": "watery"
        },
        # ─────────────── OIL-BASED ───────────────
        "oil": {
            "label": "Oil",
            "icon": "🫒",
            "description": "Pure oil or oil blend",
            "texture_feel": "oil"
        },
        "cleansing_balm": {
            "label": "Cleansing Balm",
            "icon": "🫙",
            "description": "Solid oil that melts on contact",
            "texture_feel": "oil"
        },
        # ─────────────── AEROSOLIZED/SPRAY ───────────────
        "spray": {
            "label": "Spray",
            "icon": "🌫️",
            "description": "Fine mist application",
            "texture_feel": "mist"
        },
        "mist": {
            "label": "Mist",
            "icon": "💨",
            "description": "Ultra-fine spray",
            "texture_feel": "mist"
        },
        "aerosol": {
            "label": "Aerosol",
            "icon": "🌫️",
            "description": "Pressurized spray",
            "texture_feel": "mist"
        },
        # ─────────────── SOLID FORMS ───────────────
        "stick": {
            "label": "Stick",
            "icon": "🖊️",
            "description": "Solid, swipe application",
            "texture_feel": "solid"
        },
        "bar": {
            "label": "Bar",
            "icon": "🧼",
            "description": "Solid bar form",
            "texture_feel": "solid"
        },
        "powder": {
            "label": "Powder",
            "icon": "✨",
            "description": "Loose or pressed powder",
            "texture_feel": "powder"
        },
        "wax": {
            "label": "Wax",
            "icon": "🕯️",
            "description": "Solid waxy texture",
            "texture_feel": "solid"
        },
        # ─────────────── AERATED TEXTURES ───────────────
        "foam": {
            "label": "Foam",
            "icon": "🫧",
            "description": "Aerated, light bubbly texture",
            "texture_feel": "foam"
        },
        "mousse": {
            "label": "Mousse",
            "icon": "☁️",
            "description": "Whipped, airy texture",
            "texture_feel": "foam"
        },
        "whip": {
            "label": "Whip",
            "icon": "🍦",
            "description": "Fluffy, whipped cream texture",
            "texture_feel": "foam"
        },
        # ─────────────── SHEET/PATCH FORMS ───────────────
        "sheet": {
            "label": "Sheet Mask",
            "icon": "📄",
            "description": "Fabric/hydrogel/bio-cellulose sheet",
            "texture_feel": "sheet"
        },
        "patches": {
            "label": "Patches",
            "icon": "🩹",
            "description": "Targeted adhesive patches",
            "texture_feel": "patch"
        },
        "pad": {
            "label": "Pad/Wipe",
            "icon": "⚪",
            "description": "Pre-soaked treatment pads",
            "texture_feel": "pad"
        },
        # ─────────────── WASH-OFF/TREATMENT TEXTURES ───────────────
        "scrub": {
            "label": "Scrub",
            "icon": "🧂",
            "description": "Granular, physical exfoliating",
            "texture_feel": "gritty"
        },
        "peel": {
            "label": "Peel",
            "icon": "🍊",
            "description": "Peel-off or acid peel",
            "texture_feel": "varies"
        },
        "clay": {
            "label": "Clay/Mud",
            "icon": "🏺",
            "description": "Clay or mud-based",
            "texture_feel": "clay"
        }
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # TARGET AREAS WITH COMPLETE PRODUCT TYPES, CONCERNS & BENEFITS
    # ═══════════════════════════════════════════════════════════════════════════
    "target_areas": {
        "face": {
            "icon": "👩",
            "label": "Face",
            "category": "skin",
            "sub_areas": ["full_face", "t_zone", "cheeks", "chin", "forehead", "nose"],
            "product_types": [
                {
                    "id": "cleanser",
                    "label": "Cleanser",
                    "description": "Removes dirt, oil, makeup, impurities",
                    "forms": ["gel", "foam", "cream", "oil", "balm", "milk", "water", "bar", "powder", "clay"],
                    "sub_types": ["first_cleanser", "second_cleanser", "morning_cleanser", "makeup_remover"]
                },
                {
                    "id": "exfoliator",
                    "label": "Exfoliator",
                    "description": "Removes dead skin cells",
                    "forms": ["scrub", "gel", "peel", "serum", "toner", "pad", "powder"],
                    "sub_types": ["physical_exfoliator", "chemical_exfoliator", "enzyme_exfoliator"]
                },
                {
                    "id": "toner",
                    "label": "Toner/Essence",
                    "description": "Preps skin, balances pH, first treatment",
                    "forms": ["toner", "essence", "mist", "water", "pad"],
                    "sub_types": ["hydrating_toner", "exfoliating_toner", "balancing_toner"]
                },
                {
                    "id": "serum",
                    "label": "Serum/Treatment",
                    "description": "Concentrated active ingredients for targeted concerns",
                    "forms": ["serum", "ampoule", "essence", "oil", "gel", "drops", "emulsion"],
                    "sub_types": ["vitamin_c_serum", "retinol_serum", "hydrating_serum", "brightening_serum", "anti_aging_serum"]
                },
                {
                    "id": "spot_treatment",
                    "label": "Spot Treatment",
                    "description": "Targeted treatment for specific areas",
                    "forms": ["gel", "cream", "patches", "serum", "stick"],
                    "sub_types": ["acne_spot", "dark_spot", "pimple_patches"]
                },
                {
                    "id": "moisturizer",
                    "label": "Moisturizer",
                    "description": "Hydrates and seals in moisture",
                    "forms": ["cream", "gel", "lotion", "emulsion", "oil", "balm", "butter", "gel"],
                    "sub_types": ["day_cream", "night_cream", "gel_cream", "sleeping_mask"]
                },
                {
                    "id": "face_oil",
                    "label": "Face Oil",
                    "description": "Oil-based hydration and nourishment",
                    "forms": ["oil", "serum"],
                    "sub_types": ["dry_oil", "treatment_oil", "facial_oil"]
                },
                {
                    "id": "sunscreen",
                    "label": "Sunscreen/SPF",
                    "description": "UV protection",
                    "forms": ["cream", "gel", "lotion", "spray", "stick", "milk", "fluid", "powder", "mist", "essence"],
                    "sub_types": ["chemical_sunscreen", "mineral_sunscreen", "hybrid_sunscreen", "tinted_sunscreen"]
                },
                {
                    "id": "mask",
                    "label": "Face Mask",
                    "description": "Intensive treatment mask",
                    "forms": ["cream", "gel", "sheet", "clay", "peel", "paste", "patches", "powder"],
                    "sub_types": ["hydrating_mask", "clay_mask", "sheet_mask", "overnight_mask", "peel_off_mask", "wash_off_mask"]
                },
                {
                    "id": "face_mist",
                    "label": "Face Mist",
                    "description": "Refreshing, hydrating spray",
                    "forms": ["mist", "spray"],
                    "sub_types": ["hydrating_mist", "setting_mist", "toner_mist"]
                }
            ],
            "concerns": [
                {"id": "dark_spots", "label": "Dark Spots", "parent": "pigmentation"},
                {"id": "uneven_tone", "label": "Uneven Skin Tone", "parent": "pigmentation"},
                {"id": "melasma", "label": "Melasma", "parent": "pigmentation"},
                {"id": "post_inflammatory_hyperpigmentation", "label": "PIH (Post-Acne Marks)", "parent": "pigmentation"},
                {"id": "sun_spots", "label": "Sun Spots/Age Spots", "parent": "pigmentation"},
                {"id": "dullness", "label": "Dullness/Lackluster Skin", "parent": "pigmentation"},
                {"id": "tan", "label": "Tan/Sun Damage", "parent": "pigmentation"},
                {"id": "sallowness", "label": "Sallowness/Yellow Undertone", "parent": "pigmentation"},
                {"id": "fine_lines", "label": "Fine Lines", "parent": "aging"},
                {"id": "wrinkles", "label": "Wrinkles", "parent": "aging"},
                {"id": "deep_wrinkles", "label": "Deep Wrinkles/Creases", "parent": "aging"},
                {"id": "sagging", "label": "Sagging/Loss of Firmness", "parent": "aging"},
                {"id": "loss_of_elasticity", "label": "Loss of Elasticity", "parent": "aging"},
                {"id": "crepey_skin", "label": "Crepey/Thin Skin", "parent": "aging"},
                {"id": "volume_loss", "label": "Volume Loss/Hollowness", "parent": "aging"},
                {"id": "large_pores", "label": "Large/Visible Pores", "parent": "texture"},
                {"id": "rough_texture", "label": "Rough/Bumpy Texture", "parent": "texture"},
                {"id": "uneven_texture", "label": "Uneven Texture", "parent": "texture"},
                {"id": "congestion", "label": "Congestion/Clogged Pores", "parent": "texture"},
                {"id": "milia", "label": "Milia (Tiny White Bumps)", "parent": "texture"},
                {"id": "acne", "label": "Acne/Pimples", "parent": "acne"},
                {"id": "blackheads", "label": "Blackheads", "parent": "acne"},
                {"id": "whiteheads", "label": "Whiteheads", "parent": "acne"},
                {"id": "cystic_acne", "label": "Cystic/Hormonal Acne", "parent": "acne"},
                {"id": "fungal_acne", "label": "Fungal Acne", "parent": "acne"},
                {"id": "acne_scars", "label": "Acne Scars", "parent": "acne"},
                {"id": "excess_sebum", "label": "Excess Oil/Sebum", "parent": "acne"},
                {"id": "dryness", "label": "Dryness", "parent": "hydration"},
                {"id": "dehydration", "label": "Dehydration", "parent": "hydration"},
                {"id": "flakiness", "label": "Flakiness/Peeling", "parent": "hydration"},
                {"id": "tight_skin", "label": "Tight/Uncomfortable Skin", "parent": "hydration"},
                {"id": "compromised_barrier", "label": "Damaged Barrier", "parent": "hydration"},
                {"id": "trans_epidermal_water_loss", "label": "TEWL (Water Loss)", "parent": "hydration"},
                {"id": "redness", "label": "Redness/Erythema", "parent": "sensitivity"},
                {"id": "rosacea", "label": "Rosacea", "parent": "sensitivity"},
                {"id": "irritation", "label": "Irritation/Inflammation", "parent": "sensitivity"},
                {"id": "reactive_skin", "label": "Reactive/Easily Triggered Skin", "parent": "sensitivity"},
                {"id": "eczema", "label": "Eczema/Dermatitis", "parent": "sensitivity"},
                {"id": "psoriasis", "label": "Psoriasis", "parent": "sensitivity"},
                {"id": "contact_dermatitis", "label": "Contact Dermatitis", "parent": "sensitivity"},
                {"id": "oiliness", "label": "Oiliness/Shine", "parent": "oil"},
                {"id": "enlarged_oil_glands", "label": "Enlarged Oil Glands", "parent": "oil"},
                {"id": "combination_skin", "label": "Combination Skin (Oily T-Zone)", "parent": "oil"}
            ],
            "benefits": [
                {"id": "hydrating", "label": "Hydrating", "description": "Adds water to skin"},
                {"id": "moisturizing", "label": "Moisturizing", "description": "Seals in moisture"},
                {"id": "barrier_repair", "label": "Barrier Repair", "description": "Restores skin barrier"},
                {"id": "plumping", "label": "Plumping", "description": "Adds volume/fullness"},
                {"id": "brightening", "label": "Brightening", "description": "Evens tone, adds radiance"},
                {"id": "dark_spot_correcting", "label": "Dark Spot Correcting", "description": "Fades hyperpigmentation"},
                {"id": "tone_evening", "label": "Tone Evening", "description": "Creates uniform complexion"},
                {"id": "radiance_boosting", "label": "Radiance Boosting", "description": "Adds glow"},
                {"id": "detan", "label": "De-tan", "description": "Removes tan"},
                {"id": "anti_aging", "label": "Anti-Aging", "description": "Reduces signs of aging"},
                {"id": "anti_wrinkle", "label": "Anti-Wrinkle", "description": "Smooths wrinkles"},
                {"id": "firming", "label": "Firming", "description": "Tightens skin"},
                {"id": "lifting", "label": "Lifting", "description": "Lifts sagging skin"},
                {"id": "collagen_boosting", "label": "Collagen Boosting", "description": "Stimulates collagen"},
                {"id": "elasticity_improving", "label": "Elasticity Improving", "description": "Restores bounce"},
                {"id": "anti_acne", "label": "Anti-Acne", "description": "Fights breakouts"},
                {"id": "pore_minimizing", "label": "Pore Minimizing", "description": "Reduces pore appearance"},
                {"id": "oil_control", "label": "Oil Control", "description": "Reduces sebum"},
                {"id": "mattifying", "label": "Mattifying", "description": "Reduces shine"},
                {"id": "purifying", "label": "Purifying", "description": "Deep cleans pores"},
                {"id": "clarifying", "label": "Clarifying", "description": "Clears congestion"},
                {"id": "exfoliating", "label": "Exfoliating", "description": "Removes dead skin"},
                {"id": "smoothening", "label": "Smoothening", "description": "Refines texture"},
                {"id": "resurfacing", "label": "Resurfacing", "description": "Renews skin surface"},
                {"id": "cell_renewal", "label": "Cell Renewal", "description": "Speeds cell turnover"},
                {"id": "soothing", "label": "Soothing", "description": "Calms irritation"},
                {"id": "anti_inflammatory", "label": "Anti-Inflammatory", "description": "Reduces inflammation"},
                {"id": "redness_reducing", "label": "Redness Reducing", "description": "Calms redness"},
                {"id": "sun_protection", "label": "Sun Protection", "description": "Blocks UV rays"},
                {"id": "antioxidant", "label": "Antioxidant Protection", "description": "Fights free radicals"},
                {"id": "pollution_protection", "label": "Pollution Protection", "description": "Environmental shield"},
                {"id": "nourishing", "label": "Nourishing", "description": "Feeds skin with nutrients"},
                {"id": "revitalizing", "label": "Revitalizing", "description": "Energizes tired skin"},
                {"id": "strengthening", "label": "Strengthening", "description": "Fortifies skin"}
            ]
        },
        # Add other target areas (undereye, lips, neck, body, hands, feet, scalp, hair) similarly
        # For brevity, I'll include a simplified version - you can expand this
        "hair": {
            "icon": "💇",
            "label": "Hair",
            "category": "hair",
            "sub_areas": ["roots", "mid_lengths", "ends", "edges", "baby_hair", "overall"],
            "product_types": [
                {
                    "id": "shampoo",
                    "label": "Shampoo",
                    "description": "Cleanses hair",
                    "forms": ["liquid", "cream", "gel", "foam", "bar", "powder"],
                    "sub_types": ["daily_shampoo", "clarifying_shampoo", "sulfate_free_shampoo", "color_safe_shampoo"]
                },
                {
                    "id": "conditioner",
                    "label": "Conditioner",
                    "description": "Conditions and detangles",
                    "forms": ["cream", "lotion", "liquid"],
                    "sub_types": ["daily_conditioner", "deep_conditioner", "lightweight_conditioner"]
                }
            ],
            "concerns": [
                {"id": "dry_hair", "label": "Dry Hair", "parent": "moisture"},
                {"id": "frizz", "label": "Frizz", "parent": "texture"},
                {"id": "breakage", "label": "Breakage", "parent": "damage"}
            ],
            "benefits": [
                {"id": "moisturizing_hair", "label": "Moisturizing", "description": "Adds hydration"},
                {"id": "frizz_control", "label": "Frizz Control", "description": "Tames frizz"},
                {"id": "strengthening_hair", "label": "Strengthening", "description": "Fortifies hair"}
            ]
        }
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # PRICE TIERS
    # ═══════════════════════════════════════════════════════════════════════════
    "price_tiers": [
        {"id": "mass_market", "label": "Mass Market", "range": "< ₹300", "icon": "💚", "color": "emerald"},
        {"id": "masstige", "label": "Masstige", "range": "₹300 - ₹700", "icon": "💙", "color": "blue"},
        {"id": "premium", "label": "Premium", "range": "₹700 - ₹1500", "icon": "💜", "color": "violet"},
        {"id": "prestige", "label": "Prestige", "range": "> ₹1500", "icon": "🧡", "color": "amber"}
    ],

    # ═══════════════════════════════════════════════════════════════════════════
    # MARKET POSITIONING
    # ═══════════════════════════════════════════════════════════════════════════
    "market_positioning": [
        {"id": "natural", "label": "Natural"},
        {"id": "organic", "label": "Organic"},
        {"id": "clinical", "label": "Clinical/Dermatological"},
        {"id": "ayurvedic", "label": "Ayurvedic"},
        {"id": "korean", "label": "K-Beauty (Korean)"},
        {"id": "japanese", "label": "J-Beauty (Japanese)"},
        {"id": "french", "label": "French Pharmacy"},
        {"id": "sustainable", "label": "Sustainable/Eco"},
        {"id": "vegan", "label": "Vegan"},
        {"id": "cruelty_free", "label": "Cruelty-Free"},
        {"id": "fragrance_free", "label": "Fragrance-Free"},
        {"id": "dermat_tested", "label": "Dermatologist Tested"},
        {"id": "salon_professional", "label": "Salon/Professional"},
        {"id": "pharmacy", "label": "Pharmacy"},
        {"id": "luxury", "label": "Luxury"},
        {"id": "clean_beauty", "label": "Clean Beauty"},
        {"id": "reef_safe", "label": "Reef Safe"},
        {"id": "waterless", "label": "Waterless/Concentrate"},
        {"id": "indie", "label": "Indie Brand"}
    ]
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_all_forms() -> dict:
    """Get all available forms"""
    return FORMULYNX_CANONICAL_TAXONOMY["forms"]


def get_form_by_id(form_id: str) -> Optional[dict]:
    """Get form details by ID"""
    return FORMULYNX_CANONICAL_TAXONOMY["forms"].get(form_id)


def get_target_area_by_id(target_area_id: str) -> Optional[dict]:
    """Get target area details by ID"""
    return FORMULYNX_CANONICAL_TAXONOMY["target_areas"].get(target_area_id)


def get_all_target_areas() -> dict:
    """Get all target areas"""
    return FORMULYNX_CANONICAL_TAXONOMY["target_areas"]


def get_product_types_for_target_area(target_area_id: str) -> List[dict]:
    """Get product types for a specific target area"""
    target_area = get_target_area_by_id(target_area_id)
    if target_area:
        return target_area.get("product_types", [])
    return []


def get_concerns_for_target_area(target_area_id: str) -> List[dict]:
    """Get concerns for a specific target area"""
    target_area = get_target_area_by_id(target_area_id)
    if target_area:
        return target_area.get("concerns", [])
    return []


def get_benefits_for_target_area(target_area_id: str) -> List[dict]:
    """Get benefits for a specific target area"""
    target_area = get_target_area_by_id(target_area_id)
    if target_area:
        return target_area.get("benefits", [])
    return []


def get_forms_for_product_type(target_area_id: str, product_type_id: str) -> List[str]:
    """Get valid forms for a product type within a target area"""
    target_area = get_target_area_by_id(target_area_id)
    if not target_area:
        return []
    
    for product_type in target_area.get("product_types", []):
        if product_type.get("id") == product_type_id:
            return product_type.get("forms", [])
    return []


def validate_form_for_product_type(form_id: str, product_type_id: str, target_area_id: str) -> bool:
    """Validate if a form is valid for a product type"""
    valid_forms = get_forms_for_product_type(target_area_id, product_type_id)
    return form_id in valid_forms


def get_price_tier_by_mrp(mrp: Optional[float]) -> Optional[str]:
    """Get price tier ID based on MRP value"""
    if mrp is None:
        return "masstige"  # Default
    
    if mrp < 300:
        return "mass_market"
    elif mrp < 700:
        return "masstige"
    elif mrp < 1500:
        return "premium"
    else:
        return "prestige"


def map_category_to_target_area(category: str) -> Optional[str]:
    """Map legacy category names to target area IDs"""
    mapping = {
        "skincare": "face",
        "haircare": "hair",
        "bodycare": "body",
        "lipcare": "lips"
    }
    return mapping.get(category.lower())


def get_all_price_tiers() -> List[dict]:
    """Get all price tiers"""
    return FORMULYNX_CANONICAL_TAXONOMY["price_tiers"]


def get_all_market_positioning() -> List[dict]:
    """Get all market positioning options"""
    return FORMULYNX_CANONICAL_TAXONOMY["market_positioning"]


def get_all_valid_form_ids() -> List[str]:
    """Get all valid form IDs from taxonomy"""
    return list(FORMULYNX_CANONICAL_TAXONOMY["forms"].keys())


def get_all_valid_target_area_ids() -> List[str]:
    """Get all valid target area IDs from taxonomy"""
    return list(FORMULYNX_CANONICAL_TAXONOMY["target_areas"].keys())


def get_all_valid_product_type_ids(target_area_id: Optional[str] = None) -> List[str]:
    """Get all valid product type IDs from taxonomy"""
    if target_area_id:
        product_types = get_product_types_for_target_area(target_area_id)
        return [pt.get("id") for pt in product_types if pt.get("id")]
    else:
        # Get all product types across all target areas
        all_product_types = []
        for target_area in FORMULYNX_CANONICAL_TAXONOMY["target_areas"].values():
            for pt in target_area.get("product_types", []):
                if pt.get("id") and pt.get("id") not in all_product_types:
                    all_product_types.append(pt.get("id"))
        return all_product_types


def get_all_valid_concern_ids(target_area_id: Optional[str] = None) -> List[str]:
    """Get all valid concern IDs from taxonomy"""
    if target_area_id:
        concerns = get_concerns_for_target_area(target_area_id)
        return [c.get("id") for c in concerns if c.get("id")]
    else:
        # Get all concerns across all target areas
        all_concerns = []
        for target_area in FORMULYNX_CANONICAL_TAXONOMY["target_areas"].values():
            for concern in target_area.get("concerns", []):
                if concern.get("id") and concern.get("id") not in all_concerns:
                    all_concerns.append(concern.get("id"))
        return all_concerns


def get_all_valid_benefit_ids(target_area_id: Optional[str] = None) -> List[str]:
    """Get all valid benefit IDs from taxonomy"""
    if target_area_id:
        benefits = get_benefits_for_target_area(target_area_id)
        return [b.get("id") for b in benefits if b.get("id")]
    else:
        # Get all benefits across all target areas
        all_benefits = []
        for target_area in FORMULYNX_CANONICAL_TAXONOMY["target_areas"].values():
            for benefit in target_area.get("benefits", []):
                if benefit.get("id") and benefit.get("id") not in all_benefits:
                    all_benefits.append(benefit.get("id"))
        return all_benefits


def get_all_valid_market_positioning_ids() -> List[str]:
    """Get all valid market positioning IDs from taxonomy"""
    return [mp.get("id") for mp in FORMULYNX_CANONICAL_TAXONOMY["market_positioning"] if mp.get("id")]


def get_all_valid_price_tier_ids() -> List[str]:
    """Get all valid price tier IDs from taxonomy"""
    return [pt.get("id") for pt in FORMULYNX_CANONICAL_TAXONOMY["price_tiers"] if pt.get("id")]


def validate_and_filter_keywords(keywords_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and filter keyword values against Formulynx taxonomy.
    Removes invalid values and keeps only taxonomy-compliant ones.
    
    Args:
        keywords_dict: Dictionary with keyword values
        
    Returns:
        Validated and filtered keywords dictionary
    """
    validated = {}
    
    # Get target_area first (needed for validating other fields)
    target_area = keywords_dict.get("target_area")
    
    # Validate form
    form = keywords_dict.get("form")
    valid_forms = get_all_valid_form_ids()
    if form and form in valid_forms:
        validated["form"] = form
    elif form:
        print(f"    ⚠️  Invalid form ID: {form}, skipping")
    
    # Validate product_formulation (array of form IDs)
    # Remove form from product_formulation to avoid redundancy
    product_formulation = keywords_dict.get("product_formulation", [])
    if isinstance(product_formulation, list):
        validated["product_formulation"] = [f for f in product_formulation if f in valid_forms and f != validated.get("form")]
        if len(validated["product_formulation"]) < len(product_formulation):
            invalid = set(product_formulation) - set(validated["product_formulation"])
            if invalid:
                print(f"    ⚠️  Invalid/filtered product_formulation IDs: {invalid}, filtered out")
    else:
        validated["product_formulation"] = []
    
    # Validate target_area
    valid_target_areas = get_all_valid_target_area_ids()
    if target_area and target_area in valid_target_areas:
        validated["target_area"] = target_area
    elif target_area:
        print(f"    ⚠️  Invalid target_area ID: {target_area}, skipping")
    
    # Validate product_type_id
    product_type_id = keywords_dict.get("product_type_id")
    if target_area:
        valid_product_types = get_all_valid_product_type_ids(target_area)
    else:
        valid_product_types = get_all_valid_product_type_ids()
    
    if product_type_id and product_type_id in valid_product_types:
        validated["product_type_id"] = product_type_id
    elif product_type_id:
        print(f"    ⚠️  Invalid product_type_id: {product_type_id}, skipping")
    
    # Validate concerns (array)
    concerns = keywords_dict.get("concerns", [])
    if isinstance(concerns, list):
        if target_area:
            valid_concerns = get_all_valid_concern_ids(target_area)
        else:
            valid_concerns = get_all_valid_concern_ids()
        validated["concerns"] = [c for c in concerns if c in valid_concerns]
        if len(validated["concerns"]) < len(concerns):
            invalid = set(concerns) - set(validated["concerns"])
            print(f"    ⚠️  Invalid concern IDs: {invalid}, filtered out")
    else:
        validated["concerns"] = []
    
    # Validate benefits (array)
    benefits = keywords_dict.get("benefits", [])
    if isinstance(benefits, list):
        if target_area:
            valid_benefits = get_all_valid_benefit_ids(target_area)
        else:
            valid_benefits = get_all_valid_benefit_ids()
        validated["benefits"] = [b for b in benefits if b in valid_benefits]
        if len(validated["benefits"]) < len(benefits):
            invalid = set(benefits) - set(validated["benefits"])
            print(f"    ⚠️  Invalid benefit IDs: {invalid}, filtered out")
    else:
        validated["benefits"] = []
    
    # Validate functionality (should match benefits)
    functionality = keywords_dict.get("functionality", [])
    if isinstance(functionality, list):
        # Use same validation as benefits
        if target_area:
            valid_benefits = get_all_valid_benefit_ids(target_area)
        else:
            valid_benefits = get_all_valid_benefit_ids()
        validated["functionality"] = [f for f in functionality if f in valid_benefits]
    else:
        validated["functionality"] = []
    
    # Validate market_positioning (array)
    market_positioning = keywords_dict.get("market_positioning", [])
    if isinstance(market_positioning, list):
        valid_market_positioning = get_all_valid_market_positioning_ids()
        validated["market_positioning"] = [mp for mp in market_positioning if mp in valid_market_positioning]
        if len(validated["market_positioning"]) < len(market_positioning):
            invalid = set(market_positioning) - set(validated["market_positioning"])
            print(f"    ⚠️  Invalid market_positioning IDs: {invalid}, filtered out")
    else:
        validated["market_positioning"] = []
    
    # Validate price_tier
    price_tier = keywords_dict.get("price_tier")
    valid_price_tiers = get_all_valid_price_tier_ids()
    if price_tier and price_tier in valid_price_tiers:
        validated["price_tier"] = price_tier
    elif price_tier:
        print(f"    ⚠️  Invalid price_tier ID: {price_tier}, skipping")
    
    # Validate mrp (array of price tier IDs)
    # Remove price_tier from mrp to avoid redundancy
    mrp = keywords_dict.get("mrp", [])
    if isinstance(mrp, list):
        validated["mrp"] = [p for p in mrp if p in valid_price_tiers and p != validated.get("price_tier")]
        if len(validated["mrp"]) < len(mrp):
            invalid = set(mrp) - set(validated["mrp"])
            if invalid:
                print(f"    ⚠️  Invalid/filtered mrp price tier IDs: {invalid}, filtered out")
    else:
        validated["mrp"] = []
    
    # Preserve other fields (application, functional_categories, main_category, subcategory) as-is
    # These are legacy fields and don't need strict taxonomy validation
    validated["application"] = keywords_dict.get("application", [])
    validated["functional_categories"] = keywords_dict.get("functional_categories", [])
    validated["main_category"] = keywords_dict.get("main_category")
    validated["subcategory"] = keywords_dict.get("subcategory")
    
    return validated


# ============================================================================
# ENHANCED TAXONOMY RELATIONSHIP FUNCTIONS (from Excel workbook)
# ============================================================================

def get_related_concerns(concern_id: str) -> List[str]:
    """Get related concerns for a given concern ID"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    concern_data = ENHANCED_FORMULYNX_TAXONOMY.get("skin_concerns", {}).get(concern_id)
    if concern_data:
        return concern_data.get("related_concerns", [])
    
    # Try hair concerns
    concern_data = ENHANCED_FORMULYNX_TAXONOMY.get("hair_concerns", {}).get(concern_id)
    if concern_data:
        return concern_data.get("related_concerns", [])
    
    return []


def get_benefits_for_concern(concern_id: str) -> List[str]:
    """Get benefits that address a given concern"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    concern_data = ENHANCED_FORMULYNX_TAXONOMY.get("skin_concerns", {}).get(concern_id)
    if concern_data:
        return concern_data.get("addressed_by_benefits", [])
    
    # Try hair concerns
    concern_data = ENHANCED_FORMULYNX_TAXONOMY.get("hair_concerns", {}).get(concern_id)
    if concern_data:
        return concern_data.get("addressed_by_benefits", [])
    
    return []


def get_concerns_for_benefit(benefit_id: str) -> List[str]:
    """Get concerns addressed by a given benefit"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    benefit_data = ENHANCED_FORMULYNX_TAXONOMY.get("skin_benefits", {}).get(benefit_id)
    if benefit_data:
        return benefit_data.get("addresses_concerns", [])
    
    # Try hair benefits
    benefit_data = ENHANCED_FORMULYNX_TAXONOMY.get("hair_benefits", {}).get(benefit_id)
    if benefit_data:
        return benefit_data.get("addresses_concerns", [])
    
    return []


def get_related_benefits(benefit_id: str) -> List[str]:
    """Get related benefits for a given benefit"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    benefit_data = ENHANCED_FORMULYNX_TAXONOMY.get("skin_benefits", {}).get(benefit_id)
    if benefit_data:
        return benefit_data.get("related_benefits", [])
    
    # Try hair benefits
    benefit_data = ENHANCED_FORMULYNX_TAXONOMY.get("hair_benefits", {}).get(benefit_id)
    if benefit_data:
        return benefit_data.get("related_benefits", [])
    
    return []


def get_ingredients_for_concern(concern_id: str) -> List[str]:
    """Get ingredients that address a given concern"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    ingredients = []
    
    # Check skin ingredients
    skin_ingredients = ENHANCED_FORMULYNX_TAXONOMY.get("skin_ingredients", {})
    for ingredient_id, ingredient_data in skin_ingredients.items():
        if concern_id in ingredient_data.get("concerns", []):
            ingredients.append(ingredient_id)
    
    # Check hair ingredients
    hair_ingredients = ENHANCED_FORMULYNX_TAXONOMY.get("hair_ingredients", {})
    for ingredient_id, ingredient_data in hair_ingredients.items():
        if concern_id in ingredient_data.get("concerns", []):
            ingredients.append(ingredient_id)
    
    return list(set(ingredients))  # Remove duplicates


def get_ingredients_for_benefit(benefit_id: str) -> List[str]:
    """Get ingredients that provide a given benefit"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    ingredients = []
    
    # Check skin ingredients
    skin_ingredients = ENHANCED_FORMULYNX_TAXONOMY.get("skin_ingredients", {})
    for ingredient_id, ingredient_data in skin_ingredients.items():
        if benefit_id in ingredient_data.get("benefits", []):
            ingredients.append(ingredient_id)
    
    # Check hair ingredients
    hair_ingredients = ENHANCED_FORMULYNX_TAXONOMY.get("hair_ingredients", {})
    for ingredient_id, ingredient_data in hair_ingredients.items():
        if benefit_id in ingredient_data.get("benefits", []):
            ingredients.append(ingredient_id)
    
    return list(set(ingredients))  # Remove duplicates


def get_products_for_concern(concern_id: str) -> List[str]:
    """Get product types that address a given concern"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    # Get benefits that address this concern
    addressing_benefits = get_benefits_for_concern(concern_id)
    
    # Map benefits to product types using existing taxonomy
    products = []
    for benefit_id in addressing_benefits:
        # This would need mapping from benefits to product types
        # For now, return common product types for concerns
        if concern_id in ["acne", "oiliness", "congestion"]:
            products.extend(["cleanser", "toner", "serum", "moisturizer"])
        elif concern_id in ["aging", "wrinkles", "fine_lines"]:
            products.extend(["serum", "moisturizer", "eye_cream", "night_cream"])
        elif concern_id in ["dryness", "dehydration"]:
            products.extend(["moisturizer", "serum", "face_oil", "mask"])
        elif concern_id in ["dark_spots", "uneven_tone", "pigmentation"]:
            products.extend(["serum", "moisturizer", "spot_treatment", "sunscreen"])
    
    return list(set(products))


def get_related_forms(form_id: str) -> List[str]:
    """Get related forms for a given form"""
    if not form_id:
        return []
    
    # Get all valid forms from existing taxonomy
    all_forms = get_all_valid_form_ids()
    
    # Return forms in same category
    form_categories = {
        "cream": ["cream", "lotion", "milk", "balm", "butter", "ointment"],
        "gel": ["gel", "serum", "essence", "fluid", "drops"],
        "oil": ["oil", "cleansing_balm"],
        "foam": ["foam", "mousse", "whip"],
        "solid": ["stick", "bar", "powder", "wax"],
        "sheet": ["sheet", "patches", "pad"],
        "spray": ["spray", "mist", "aerosol"]
    }
    
    for category, forms in form_categories.items():
        if form_id in forms:
            return forms
    
    # If not found, return all forms
    return all_forms


def get_related_applications(application_id: str) -> List[str]:
    """Get related applications for a given application"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    # Common application groupings
    application_groups = {
        "daily_use": ["morning", "evening", "night", "daily_use"],
        "morning": ["daily_use", "evening"],
        "evening": ["night", "daily_use"],
        "night": ["evening", "daily_use"],
        "spot_treatment": ["acne_spot", "dark_spot", "pimple_patches"],
        "makeup_remover": ["first_cleanser", "cleanser"],
        "post_procedure": ["soothing", "barrier_repair"],
        "outdoor_protection": ["sun_protection", "antioxidant"],
        "sensitive_skin": ["soothing", "anti_inflammatory"],
        "acne_prone": ["anti_acne", "oil_control", "purifying"]
    }
    
    return application_groups.get(application_id, [application_id])


def get_related_functionality(functionality_id: str) -> List[str]:
    """Get related functionality/benefits for a given functionality"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return []
    
    # Get related benefits from enhanced taxonomy
    related_benefits = get_related_benefits(functionality_id)
    
    # Also add benefits that address similar concerns
    functionality_groups = {
        "brightening": ["tone_evening", "dark_spot_correcting", "anti_oxidant", "exfoliating"],
        "hydrating": ["moisturizing", "barrier_repair", "plumping"],
        "anti_aging": ["anti_wrinkle", "firming", "lifting", "collagen_boosting"],
        "anti_wrinkle": ["anti_aging", "smoothening", "plumping"],
        "firming": ["lifting", "collagen_boosting", "elasticity_improving"],
        "anti_acne": ["oil_control", "purifying", "clarifying", "pore_minimizing"],
        "soothing": ["anti_inflammatory", "redness_reducing", "barrier_repair"]
    }
    
    related = functionality_groups.get(functionality_id, [])
    if related_benefits:
        related.extend(related_benefits)
    
    return list(set(related))  # Remove duplicates


def search_taxonomy_by_keyword(keyword: str) -> Dict[str, List[dict]]:
    """Search taxonomy by keyword across all categories"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return {}
    
    keyword = keyword.lower().strip()
    results = {
        "concerns": [],
        "benefits": [],
        "ingredients": [],
        "product_types": []
    }
    
    # Search skin concerns
    for concern_id, concern_data in ENHANCED_FORMULYNX_TAXONOMY.get("skin_concerns", {}).items():
        if (keyword in concern_data["id"] or 
            keyword in concern_data["label"].lower() or
            keyword in [term.lower() for term in concern_data.get("search_terms", [])]):
            results["concerns"].append(concern_data)
    
    # Search hair concerns
    for concern_id, concern_data in ENHANCED_FORMULYNX_TAXONOMY.get("hair_concerns", {}).items():
        if (keyword in concern_data["id"] or 
            keyword in concern_data["label"].lower() or
            keyword in [term.lower() for term in concern_data.get("search_terms", [])]):
            results["concerns"].append(concern_data)
    
    # Search skin benefits
    for benefit_id, benefit_data in ENHANCED_FORMULYNX_TAXONOMY.get("skin_benefits", {}).items():
        if (keyword in benefit_data["id"] or 
            keyword in benefit_data["label"].lower() or
            keyword in [term.lower() for term in benefit_data.get("search_terms", [])]):
            results["benefits"].append(benefit_data)
    
    # Search hair benefits
    for benefit_id, benefit_data in ENHANCED_FORMULYNX_TAXONOMY.get("hair_benefits", {}).items():
        if (keyword in benefit_data["id"] or 
            keyword in benefit_data["label"].lower() or
            keyword in [term.lower() for term in benefit_data.get("search_terms", [])]):
            results["benefits"].append(benefit_data)
    
    # Search skin ingredients
    for ingredient_id, ingredient_data in ENHANCED_FORMULYNX_TAXONOMY.get("skin_ingredients", {}).items():
        if (keyword in ingredient_data["id"] or 
            keyword in ingredient_data["label"].lower() or
            keyword in [term.lower() for term in ingredient_data.get("search_terms", [])] or
            keyword in [term.lower() for term in ingredient_data.get("inci_names", [])]):
            results["ingredients"].append(ingredient_data)
    
    # Search hair ingredients
    for ingredient_id, ingredient_data in ENHANCED_FORMULYNX_TAXONOMY.get("hair_ingredients", {}).items():
        if (keyword in ingredient_data["id"] or 
            keyword in ingredient_data["label"].lower() or
            keyword in [term.lower() for term in ingredient_data.get("search_terms", [])] or
            keyword in [term.lower() for term in ingredient_data.get("inci_names", [])]):
            results["ingredients"].append(ingredient_data)
    
    # Search product types
    for product_id, product_data in ENHANCED_FORMULYNX_TAXONOMY.get("skin_product_types", {}).items():
        if (keyword in product_data["id"] or 
            keyword in product_data["label"].lower() or
            keyword in [term.lower() for term in product_data.get("search_terms", [])]):
            results["product_types"].append(product_data)
    
    return results


def get_available_keywords_for_analysis(analyzed_keywords: Dict[str, Any]) -> Dict[str, Any]:
    """Generate available keywords based on analysis"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return {}
    
    available = {
        "form": [],
        "mrp": ["mass_market", "masstige", "premium", "prestige"],
        "application": [],
        "functionality": [],
        "concerns": [],
        "benefits": [],
        "product_types": [],
        "relationships": {}
    }
    
    # Get related forms
    form_value = analyzed_keywords.get("form")
    if form_value:
        available["form"] = get_related_forms(form_value)
    
    # Get related applications
    app_value = analyzed_keywords.get("application")
    if isinstance(app_value, list) and app_value:
        available["application"] = get_related_applications(app_value[0])
    elif isinstance(app_value, str):
        available["application"] = get_related_applications(app_value)
    
    # Get related functionality
    func_value = analyzed_keywords.get("functionality")
    if isinstance(func_value, list) and func_value:
        available["functionality"] = get_related_functionality(func_value[0])
    elif isinstance(func_value, str):
        available["functionality"] = get_related_functionality(func_value)
    
    # Get concerns and benefits based on functionality
    if func_value:
        func_id = func_value[0] if isinstance(func_value, list) else func_value
        
        # Get concerns for this functionality
        concerns_for_func = get_concerns_for_benefit(func_id)
        available["concerns"] = concerns_for_func
        
        # Get benefits related to this functionality
        available["benefits"] = get_related_benefits(func_id)
        
        # Get products for these concerns
        products_for_concerns = []
        for concern in concerns_for_func:
            products = get_products_for_concern(concern)
            products_for_concerns.extend(products)
        available["product_types"] = list(set(products_for_concerns))
        
        # Build relationships object
        available["relationships"] = {
            "concerns": {
                concern_id: {
                    "related_concerns": get_related_concerns(concern_id),
                    "addressed_by_benefits": get_benefits_for_concern(concern_id)
                }
                for concern_id in concerns_for_func[:10]  # Limit to prevent huge responses
            },
            "benefits": {
                func_id: {
                    "related_benefits": get_related_benefits(func_id),
                    "addresses_concerns": get_concerns_for_benefit(func_id)
                }
            }
        }
    
    return available


def get_all_enhanced_concerns() -> Dict[str, dict]:
    """Get all enhanced concerns (skin + hair)"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return {}
    
    all_concerns = {}
    all_concerns.update(ENHANCED_FORMULYNX_TAXONOMY.get("skin_concerns", {}))
    all_concerns.update(ENHANCED_FORMULYNX_TAXONOMY.get("hair_concerns", {}))
    return all_concerns


def get_all_enhanced_benefits() -> Dict[str, dict]:
    """Get all enhanced benefits (skin + hair)"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return {}
    
    all_benefits = {}
    all_benefits.update(ENHANCED_FORMULYNX_TAXONOMY.get("skin_benefits", {}))
    all_benefits.update(ENHANCED_FORMULYNX_TAXONOMY.get("hair_benefits", {}))
    return all_benefits


def get_all_enhanced_ingredients() -> Dict[str, dict]:
    """Get all enhanced ingredients (skin + hair)"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return {}
    
    all_ingredients = {}
    all_ingredients.update(ENHANCED_FORMULYNX_TAXONOMY.get("skin_ingredients", {}))
    all_ingredients.update(ENHANCED_FORMULYNX_TAXONOMY.get("hair_ingredients", {}))
    return all_ingredients


def get_all_enhanced_product_types() -> Dict[str, dict]:
    """Get all enhanced product types (skin + hair)"""
    if not ENHANCED_FORMULYNX_TAXONOMY:
        return {}
    
    all_products = {}
    all_products.update(ENHANCED_FORMULYNX_TAXONOMY.get("skin_product_types", {}))
    all_products.update(ENHANCED_FORMULYNX_TAXONOMY.get("hair_product_types", {}))
    return all_products
