"""
Formulynx Canonical Taxonomy
============================

Hierarchical Structure:
TARGET AREA → CONCERN → BENEFIT → PRODUCT TYPE → FORM → PRICE TIER

Key Distinction:
- FORM = Physical state/texture (cream, gel, oil, spray, etc.)
- PRODUCT TYPE = Functional category (cleanser, moisturizer, sunscreen, etc.)
"""

from typing import Optional, List

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

