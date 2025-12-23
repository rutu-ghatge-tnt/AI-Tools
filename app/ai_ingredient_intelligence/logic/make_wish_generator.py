"""
Make a Wish - Formula Generator
================================

This module implements the complete 4-stage AI pipeline for generating
cosmetic formulations from user wishes.

STAGES:
1. Ingredient Selection
2. Formula Optimization
3. Manufacturing Process
4. Compliance Check
"""

import os
import json
import re
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# Import prompts
from app.ai_ingredient_intelligence.logic.make_wish_prompts import (
    INGREDIENT_SELECTION_SYSTEM_PROMPT,
    FORMULA_OPTIMIZATION_SYSTEM_PROMPT,
    MANUFACTURING_PROCESS_SYSTEM_PROMPT,
    COMPLIANCE_CHECK_SYSTEM_PROMPT
)

# Import cache manager
from app.ai_ingredient_intelligence.logic.prompt_cache_manager import get_cache_manager

# Import rules engine
from app.ai_ingredient_intelligence.logic.make_wish_rules_engine import (
    get_rules_engine,
    ValidationSeverity
)

# Import URL scraper for ingredient lookup
from app.ai_ingredient_intelligence.logic.url_scraper import URLScraper

# Claude API setup
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

claude_api_key = os.getenv("CLAUDE_API_KEY")
# Make a Wish uses Opus - HARDCODED (same as Formulation Report)
# IMPORTANT: This is hardcoded to Opus, not using env vars
claude_model = "claude-3-opus-20240229"
print(f"✅ Make a Wish model: {claude_model} (Opus - hardcoded)")

if not claude_api_key:
    raise RuntimeError("CLAUDE_API_KEY is required for Make a Wish feature")

if ANTHROPIC_AVAILABLE and claude_api_key:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
        print(f"🤖 Make a Wish: Claude client initialized with model: {claude_model}")
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        claude_client = None
else:
    claude_client = None
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package is required. Install it with: pip install anthropic")


# ============================================================================
# PROMPT GENERATION FUNCTIONS
# ============================================================================

def generate_ingredient_selection_prompt(wish_data: dict) -> str:
    """Generate the user prompt for ingredient selection."""
    
    # Extract data from wish
    category = wish_data.get('category', 'skincare')  # skincare or haircare
    product_type = wish_data.get('productType', 'serum')
    benefits = wish_data.get('benefits', [])
    exclusions = wish_data.get('exclusions', [])
    hero_ingredients = wish_data.get('heroIngredients', [])
    must_have_ingredients = wish_data.get('mustHaveIngredients', [])
    texture = wish_data.get('texture', 'lightweight')
    claims = wish_data.get('claims', [])
    target_audience = wish_data.get('targetAudience', [])
    skin_types = wish_data.get('skinTypes', [])
    age_group = wish_data.get('ageGroup', '')
    additional_notes = wish_data.get('additionalNotes', '') or wish_data.get('notes', '')
    product_name = wish_data.get('productName', '')
    
    # Format benefits
    if benefits:
        benefits_text = "\n".join([f"  • {b}" for b in benefits])
    else:
        benefits_text = "  • General skincare/haircare"
    
    # Format exclusions with detailed expansion
    exclusion_mapping = {
        'silicone-free': 'ALL silicones (Dimethicone, Cyclomethicone, Cyclopentasiloxane, Amodimethicone, Phenyl Trimethicone, etc.)',
        'sulfate-free': 'ALL sulfates (SLS, SLES, ALS, Sodium Coco Sulfate, Ammonium Lauryl Sulfate, etc.)',
        'paraben-free': 'ALL parabens (Methylparaben, Propylparaben, Butylparaben, Ethylparaben, etc.)',
        'fragrance-free': 'Parfum/Fragrance AND all synthetic fragrances',
        'alcohol-free': 'Drying alcohols (Alcohol Denat, SD Alcohol, Isopropyl Alcohol) - Note: Fatty alcohols like Cetyl Alcohol ARE allowed',
        'mineral-oil-free': 'Mineral Oil, Paraffinum Liquidum, Petrolatum, Microcrystalline Wax',
        'essential-oil-free': 'ALL essential oils (Lavender, Tea Tree, Peppermint, etc.)',
        'vegan': 'ALL animal-derived ingredients (Lanolin, Carmine, Collagen, Keratin from animals, Beeswax, Squalane from shark, etc.)',
        'gluten-free': 'Wheat, Barley, Oat derivatives unless certified gluten-free'
    }
    
    exclusions_detailed = []
    for exc in exclusions:
        exc_lower = exc.lower().replace(' ', '-').replace('_', '-')
        if exc_lower in exclusion_mapping:
            exclusions_detailed.append(f"  ❌ {exc}: {exclusion_mapping[exc_lower]}")
        else:
            exclusions_detailed.append(f"  ❌ {exc}")
    
    exclusions_text = "\n".join(exclusions_detailed) if exclusions_detailed else "  • None specified"
    
    # Format hero ingredients with emphasis
    if hero_ingredients:
        hero_text = "\n".join([f"  ⭐ {h}" for h in hero_ingredients])
        primary_hero = hero_ingredients[0] if hero_ingredients else "Not specified"
    else:
        hero_text = "  • None specified (select best options for the benefits)"
        primary_hero = "Based on benefits"
    
    # Format must-have ingredients
    if must_have_ingredients:
        must_have_text = "\n".join([f"  ✓ {ing}" for ing in must_have_ingredients])
    else:
        must_have_text = "  • None specified"
    
    # Format claims
    claims_text = "\n".join([f"  • {c}" for c in claims]) if claims else "  • No specific claims required"
    
    # Format target audience
    audience_parts = []
    if skin_types:
        audience_parts.append(f"Skin Types: {', '.join(skin_types)}")
    if age_group:
        audience_parts.append(f"Age Group: {age_group}")
    if target_audience:
        audience_parts.append(f"Target: {', '.join(target_audience)}")
    audience_text = " | ".join(audience_parts) if audience_parts else "General consumer"
    
    # Build the prompt
    prompt = f"""
═══════════════════════════════════════════════════════════════════════════════
                              FORMULA REQUEST
═══════════════════════════════════════════════════════════════════════════════

## PRODUCT IDENTITY
- Product Name: {product_name if product_name else f'{primary_hero} {product_type.title()}'}
- Category: {category.upper()}
- Product Type: {product_type}
- Desired Texture: {texture}

───────────────────────────────────────────────────────────────────────────────
                    ⚠️ MANDATORY HERO INGREDIENTS (MUST INCLUDE ALL)
───────────────────────────────────────────────────────────────────────────────

{hero_text}

🚨 CRITICAL: Every ingredient listed above MUST appear in your final formula.
   - The formula name MUST include "{primary_hero}"
   - If ANY hero ingredient cannot be included, you MUST add a CRITICAL warning
   - Do NOT silently omit or substitute without explicit disclosure

───────────────────────────────────────────────────────────────────────────────
                    ✓ USER-REQUESTED INGREDIENTS (MUST INCLUDE OR JUSTIFY)
───────────────────────────────────────────────────────────────────────────────

{must_have_text}

RULE: Each ingredient above was specifically requested. You MUST either:
  1. Include it at an effective percentage, OR
  2. Add a WARNING explaining why it was excluded/substituted
  3. Suggest an alternative if excluded

───────────────────────────────────────────────────────────────────────────────
                    ❌ STRICT EXCLUSIONS (ZERO TOLERANCE)
───────────────────────────────────────────────────────────────────────────────

{exclusions_text}

⛔ Do NOT include ANY ingredient matching these exclusions or their families.

───────────────────────────────────────────────────────────────────────────────
                              TARGET BENEFITS
───────────────────────────────────────────────────────────────────────────────

{benefits_text}

───────────────────────────────────────────────────────────────────────────────
                              TARGET AUDIENCE
───────────────────────────────────────────────────────────────────────────────

{audience_text}

───────────────────────────────────────────────────────────────────────────────
                         PRODUCT CLAIMS TO SUPPORT
───────────────────────────────────────────────────────────────────────────────

{claims_text}

───────────────────────────────────────────────────────────────────────────────
                         TEXTURE & SENSORY
───────────────────────────────────────────────────────────────────────────────

- Desired texture: {texture}
- Consider Indian climate (hot, humid) for stability and feel
- Ensure pleasant sensory experience appropriate for product type

"""
    
    # Add category-specific requirements
    if category == 'haircare':
        prompt += f"""
### HAIRCARE-SPECIFIC REQUIREMENTS

- Product: {product_type}
- Consider:
  • Scalp health and compatibility
  • Hair fiber protection
  • Rinse-off vs leave-on requirements
  • Hard water compatibility (where applicable)
  • Climate resistance (heat, humidity, cold as relevant)

"""
        
        if product_type in ['shampoo']:
            prompt += """
- SHAMPOO SPECIFIC:
  • Use gentle surfactant system (preferably sulfate-free if specified)
  • Include conditioning agents for post-wash feel
  • pH range: 4.5-6.0
  • Consider foam quality and stability

"""
        elif product_type in ['conditioner', 'hair-mask']:
            prompt += """
- CONDITIONER/MASK SPECIFIC:
  • Focus on conditioning quaternaries (BTMS, Cetrimonium Chloride)
  • Include slip agents for detangling
  • Consider protein content for repair
  • pH range: 4.0-5.0

"""
        elif product_type in ['hair-serum', 'hair-oil']:
            prompt += """
- SERUM/OIL SPECIFIC:
  • Consider silicone alternatives if silicone-free
  • Include heat protection if applicable
  • Focus on shine and frizz control
  • Lightweight, non-greasy feel

"""
        elif product_type in ['scalp-treatment']:
            prompt += """
- SCALP TREATMENT SPECIFIC:
  • Focus on scalp-soothing ingredients
  • Include anti-microbial agents if for dandruff
  • Consider penetration enhancers for actives
  • Non-comedogenic for scalp

"""
    
    else:  # skincare
        prompt += f"""
### SKINCARE-SPECIFIC REQUIREMENTS

- Product: {product_type}
- Consider:
  • Skin type compatibility
  • Non-comedogenic if for face
  • Photostability if includes actives
  • Layering compatibility in skincare routine

"""
        
        if product_type in ['serum']:
            prompt += """
- SERUM SPECIFIC:
  • High concentration of actives
  • Lightweight, fast-absorbing
  • Can be water-based, oil-based, or bi-phase
  • pH dependent on actives used

"""
        elif product_type in ['moisturizer', 'cream']:
            prompt += """
- MOISTURIZER SPECIFIC:
  • Balance of humectants, emollients, occlusives
  • Appropriate for specified skin type
  • Consider AM/PM usage
  • Include barrier-supporting ingredients

"""
        elif product_type in ['cleanser']:
            prompt += """
- CLEANSER SPECIFIC:
  • Gentle surfactant system
  • pH 4.5-6.5 (skin-compatible)
  • Consider double-cleansing if oil-based
  • Non-stripping, maintains barrier

"""
        elif product_type in ['sunscreen']:
            prompt += """
- SUNSCREEN SPECIFIC:
  • UV filters must provide broad spectrum protection
  • Consider photostability of filters
  • Water resistance if specified
  • Check BIS compliance for UV filter limits

"""
    
    # Add URL if provided for ingredient reference
    reference_url = wish_data.get('referenceUrl') or wish_data.get('url') or wish_data.get('reference_url')
    if reference_url:
        prompt += f"""
### REFERENCE PRODUCT URL

- Reference URL: {reference_url}
- If ingredients are not found in standard databases, use web search to extract accurate ingredient information from this URL
- Use the actual ingredients from this product as a reference, not random selections
- Ensure ingredient names match what is actually listed on the product page

"""
    
    # Add additional notes if provided
    if additional_notes:
        prompt += f"""
### ADDITIONAL REQUIREMENTS FROM USER

{additional_notes}

"""
    
    prompt += """
═══════════════════════════════════════════════════════════════════════════════
                              YOUR TASK
═══════════════════════════════════════════════════════════════════════════════

⚠️ CRITICAL: This is a NEW formula being created from scratch. There is NO 
   "original formula" or "previous formula". NEVER mention "original formula", 
   "previous formula", "was this", "now it is", or any comparison language.

1. ⭐ INCLUDE ALL hero ingredients (MANDATORY - not optional)

2. ✓ INCLUDE ALL user-requested ingredients OR add warning explaining exclusion

3. ❌ STRICTLY EXCLUDE all ingredients matching exclusion criteria

4. 🔄 If substituting ANY requested ingredient:
   - Add explicit warning with category "substitution"
   - Explain why and what alternative was chosen
   - NEVER say "original formula had X" - just state the substitution

5. 📊 Select supporting ingredients (total 8-15) that deliver requested benefits

6. 📋 Organize ingredients into appropriate phases with temperatures

7. ✅ VERIFY BEFORE RESPONDING:
   - Every ingredient in "insights" appears in ingredients table
   - Percentages in explanations match table exactly
   - No phantom ingredients (explained but not included)
   - Formula name includes the primary hero ingredient
   - user_request_validation section is complete and accurate
   - NO mentions of "original formula" or "previous formula"

9. 📄 Return complete JSON following the specified format

═══════════════════════════════════════════════════════════════════════════════
"""
    
    return prompt


def generate_optimization_prompt(wish_data: dict, selected_ingredients: list) -> str:
    """Generate the optimization prompt."""
    
    product_type = wish_data.get('productType', 'serum')
    category = wish_data.get('category', 'skincare')
    benefits = wish_data.get('benefits', [])
    texture = wish_data.get('texture', 'lightweight')
    
    # Format ingredients
    ingredients_text = "\n".join([
        f"  • {ing.get('ingredient_name', ing.get('name', 'Unknown'))} (INCI: {ing.get('inci_name', ing.get('inci', 'Unknown'))})\n"
        f"    - Function: {ing.get('functional_category', ing.get('function', 'Unknown'))}\n"
        f"    - Usage Range: {ing.get('usage_range', {}).get('min', 0)}-{ing.get('usage_range', {}).get('max', 0)}%\n"
        f"    - Phase: {ing.get('phase', 'Unknown')}\n"
        f"    - Hero: {'Yes' if ing.get('is_hero', False) else 'No'}"
        for ing in selected_ingredients
    ])
    
    return f"""
## OPTIMIZE FORMULA PERCENTAGES FOR NEW FORMULA

⚠️ IMPORTANT: This is a NEW formula being created from scratch. There is NO "original formula" or "previous formula". Simply optimize percentages for this new formula. NEVER mention "original formula", "previous formula", "was this", "now it is", or any comparison language.

### PRODUCT DETAILS

- Category: {category.upper()}
- Product Type: {product_type}
- Desired Texture: {texture}

### TARGET BENEFITS

{chr(10).join([f"  • {b}" for b in benefits])}

### SELECTED INGREDIENTS TO OPTIMIZE

{ingredients_text}

### OPTIMIZATION REQUIREMENTS

1. **Percentage Allocation**
   - Total MUST equal exactly 100.00%
   - Water/base makes up the remainder
   - Round all percentages to 2 decimal places

2. **Active Optimization**
   - Hero ingredients at optimal efficacious levels
   - Balance multiple actives for synergy
   - Avoid excessive concentrations without benefit

3. **Texture Achievement**
   - "{texture}" texture requires appropriate thickener/emollient levels
   - Consider sensory properties

4. **Stability Considerations**
   - Ensure preservative at effective level
   - pH adjusters sufficient for target range
   - Consider ingredient interactions

Return the optimized formula as JSON with exact percentages totaling 100.00%. State what the percentages ARE, not what they were changed from.

"""


def generate_manufacturing_prompt(optimized_formula: dict) -> str:
    """Generate the manufacturing process prompt."""
    
    formula_name = optimized_formula.get('optimized_formula', {}).get('name', 'Formula')
    ingredients = optimized_formula.get('ingredients', [])
    phases = optimized_formula.get('phase_summary', [])
    
    # Format ingredients by phase
    phase_ingredients = {}
    for ing in ingredients:
        phase = ing.get('phase', 'A')
        if phase not in phase_ingredients:
            phase_ingredients[phase] = []
        phase_ingredients[phase].append(ing)
    
    phases_text = "\n".join([
        f"Phase {p.get('phase', 'Unknown')} ({p.get('name', 'Unknown')}): {p.get('total_percent', 0)}%"
        for p in phases
    ])
    
    ingredients_by_phase = "\n\n".join([
        f"**Phase {phase}:**\n" + "\n".join([
            f"  - {ing.get('name', 'Unknown')}: {ing.get('percent', 0)}% ({ing.get('function', 'Unknown')})"
            for ing in phase_ingredients.get(phase, [])
        ])
        for phase in sorted(phase_ingredients.keys())
    ])
    
    return f"""
## GENERATE MANUFACTURING PROCESS

### FORMULA INFORMATION

- Formula Name: {formula_name}
- Total Percentage: {optimized_formula.get('optimized_formula', {}).get('total_percentage', 100)}%
- Target pH: {optimized_formula.get('optimized_formula', {}).get('target_ph', {})}

### PHASE BREAKDOWN

{phases_text}

### INGREDIENTS BY PHASE

{ingredients_by_phase}

### YOUR TASK

Generate detailed manufacturing instructions including:

1. Process type (cold/hot/combined)
2. Step-by-step instructions for each phase
3. Temperature requirements
4. Mixing parameters
5. Quality checkpoints
6. Troubleshooting guide
7. Packaging recommendations
8. Safety precautions

Return the complete manufacturing process as JSON following the specified format.

"""




def generate_compliance_prompt(optimized_formula: dict) -> str:
    """Generate the compliance check prompt."""
    
    formula_name = optimized_formula.get('optimized_formula', {}).get('name', 'Formula')
    ingredients = optimized_formula.get('ingredients', [])
    
    # Format ingredients with concentrations
    ingredients_text = "\n".join([
        f"  • {ing.get('name', 'Unknown')} (INCI: {ing.get('inci', 'Unknown')}): {ing.get('percent', 0)}%"
        for ing in ingredients
    ])
    
    return f"""
## CHECK REGULATORY COMPLIANCE

### FORMULA INFORMATION

- Formula Name: {formula_name}
- Target Markets: India (BIS), EU, US

### INGREDIENTS WITH CONCENTRATIONS

{ingredients_text}

### YOUR TASK

1. Check compliance with BIS IS 4707 (India)
2. Check compliance with EU Cosmetics Regulation
3. Check compliance with US FDA regulations
4. Verify all ingredient concentrations are within limits
5. Identify any required warnings or labeling
6. Provide claims guidance (allowed, needs substantiation, prohibited)
7. List any compliance issues or concerns

Return the complete compliance analysis as JSON following the specified format.

"""


# ============================================================================
# AI CALL FUNCTION
# ============================================================================

async def call_ai_with_claude(
    system_prompt: str,
    user_prompt: str,
    prompt_type: str = "general",
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Call Claude API for Make a Wish pipeline with prompt caching support.
    Uses Claude as per project preference.
    
    Args:
        system_prompt: The system prompt (will be cached)
        user_prompt: The user prompt (dynamic content)
        prompt_type: Type of prompt for cache tracking (e.g., "ingredient_selection")
        max_retries: Maximum number of retry attempts
    
    Returns:
        Dictionary containing AI response
    """
    
    if not claude_client:
        raise RuntimeError("Claude client not initialized. Check CLAUDE_API_KEY environment variable.")
    
    
    # Get cache manager and check if we should use caching
    cache_manager = get_cache_manager(claude_client)
    cache_block_id = await cache_manager.get_or_create_cache(
        prompt_type=prompt_type,
        system_prompt=system_prompt,
        claude_client=claude_client
    )
    
    # Prepare API call parameters
    # HARDCODED to Opus (same as Formulation Report)
    api_params = {
        "model": "claude-3-opus-20240229",  # Hardcoded to Opus
        "max_tokens": 4096,  # Maximum allowed for claude-3-opus-20240229
        "temperature": 0.3,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }
    
    # Debug: Log the model being used
    print(f"🔍 Make a Wish API call - Using model: {api_params['model']} for {prompt_type}")
    
    # Note: cache_control is not supported in current Anthropic SDK version
    # The cache_block_id is tracked for future use when SDK supports it
    if cache_block_id:
        print(f"💾 Cache tracking enabled for {prompt_type} (cache_control not yet supported in SDK)")
    else:
        print(f"📝 No cache tracking for {prompt_type}")
    
    for attempt in range(max_retries):
        try:
            # Call Claude API with caching support
            response = claude_client.messages.create(**api_params)
            
            # Verify response (if available)
            print(f"✅ API call succeeded for {prompt_type}")
            
            if not response.content or len(response.content) == 0:
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise ValueError("Empty response from Claude API")
            
            content = response.content[0].text.strip()
            
            if not content:
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise ValueError("Empty text in Claude response")
            
            # Try to parse JSON
            try:
                # Remove markdown code blocks if present
                content = re.sub(r'```json\s*', '', content)
                content = re.sub(r'```\s*', '', content)
                content = content.strip()
                
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from text
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        return result
                    except json.JSONDecodeError:
                        pass
                
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                else:
                    raise ValueError(f"Failed to parse JSON from Claude response. Content: {content[:500]}")
        
        except Exception as e:
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                print(f"Error calling Claude API: {e}")
                raise Exception(f"Claude API error after {max_retries} attempts: {str(e)}")
    
    raise Exception("All retry attempts failed")


# ============================================================================
# INGREDIENT VALIDATION CACHE
# ============================================================================

# Cache for ingredient validation results to avoid repeated DB lookups
_ingredient_validation_cache: Dict[str, Optional[Dict]] = {}

def _get_cache_key(ingredient_name: str, inci_names: List[str]) -> str:
    """Generate cache key for ingredient validation."""
    inci_str = "|".join(sorted(inci_names)) if inci_names else ""
    return f"{ingredient_name.lower().strip()}|{inci_str}"

async def _check_ingredient_cached(ingredient_name: str, inci_names: List[str]) -> Optional[Dict]:
    """Check ingredient in cache first, then database."""
    cache_key = _get_cache_key(ingredient_name, inci_names)
    
    if cache_key in _ingredient_validation_cache:
        return _ingredient_validation_cache[cache_key]
    
    from app.ai_ingredient_intelligence.logic.formula_generator import check_ingredient_exists_in_db
    result = await check_ingredient_exists_in_db(ingredient_name, inci_names)
    _ingredient_validation_cache[cache_key] = result
    return result

# ============================================================================
# EARLY URL SCRAPING (OPTIMIZATION)
# ============================================================================

async def scrape_reference_url_early(reference_url: Optional[str]) -> Optional[Dict]:
    """
    Scrape reference URL early if provided, to inform ingredient selection.
    This optimization allows us to use scraped ingredients during selection phase.
    
    Returns:
        Dictionary with scraped ingredients and metadata, or None if URL not provided/failed
    """
    if not reference_url:
        return None
    
    print(f"🔍 Early URL scraping from: {reference_url}")
    try:
        scraper = URLScraper()
        extraction_result = await scraper.extract_ingredients_from_url(reference_url)
        
        if extraction_result and extraction_result.get("ingredients"):
            scraped_count = len(extraction_result.get("ingredients", []))
            print(f"✅ Early scrape: Found {scraped_count} ingredients from reference URL")
            return extraction_result
        else:
            print(f"⚠️ Early scrape: No ingredients found in URL")
            return None
    except Exception as e:
        print(f"⚠️ Early URL scraping failed (non-blocking): {e}")
        return None

# ============================================================================
# PRE-VALIDATE HERO/MUST-HAVE INGREDIENTS (OPTIMIZATION)
# ============================================================================

async def pre_validate_required_ingredients(
    hero_ingredients: List[str],
    must_have_ingredients: List[str],
    scraped_ingredients: Optional[List[str]] = None
) -> Tuple[List[str], List[str], Dict[str, bool]]:
    """
    Pre-validate hero and must-have ingredients before AI selection.
    This helps catch issues early and provides better context to AI.
    
    Returns:
        Tuple of (valid_hero_ingredients, valid_must_have_ingredients, validation_map)
    """
    from app.ai_ingredient_intelligence.logic.formula_generator import check_ingredient_exists_in_db
    
    validation_map = {}
    valid_hero = []
    valid_must_have = []
    
    # Normalize scraped ingredients for matching
    scraped_normalized = set()
    if scraped_ingredients:
        for ing in scraped_ingredients:
            scraped_normalized.add(ing.lower().strip())
            # Also add key words for partial matching
            words = ing.lower().strip().split()
            if len(words) > 1:
                scraped_normalized.add(' '.join(words[:2]))
    
    # Validate hero ingredients
    for hero in hero_ingredients:
        hero_lower = hero.lower().strip()
        # Check cache/database
        db_result = await _check_ingredient_cached(hero, [])
        is_valid = db_result is not None
        
        # Also check if it's in scraped ingredients
        if not is_valid and scraped_ingredients:
            is_valid = hero_lower in scraped_normalized or any(
                hero_lower in scraped or scraped in hero_lower 
                for scraped in scraped_normalized
            )
        
        validation_map[hero] = is_valid
        if is_valid:
            valid_hero.append(hero)
        else:
            print(f"⚠️ Hero ingredient '{hero}' not found in database or reference URL")
    
    # Validate must-have ingredients
    for must_have in must_have_ingredients:
        must_have_lower = must_have.lower().strip()
        # Check cache/database
        db_result = await _check_ingredient_cached(must_have, [])
        is_valid = db_result is not None
        
        # Also check if it's in scraped ingredients
        if not is_valid and scraped_ingredients:
            is_valid = must_have_lower in scraped_normalized or any(
                must_have_lower in scraped or scraped in must_have_lower 
                for scraped in scraped_normalized
            )
        
        validation_map[must_have] = is_valid
        if is_valid:
            valid_must_have.append(must_have)
        else:
            print(f"⚠️ Must-have ingredient '{must_have}' not found in database or reference URL")
    
    return valid_hero, valid_must_have, validation_map

# ============================================================================
# INGREDIENT VALIDATION WITH URL SCRAPING
# ============================================================================

async def validate_and_enrich_ingredients_with_url_fallback(
    selected_ingredients: List[Dict],
    reference_url: Optional[str] = None,
    pre_scraped_data: Optional[Dict] = None
) -> Tuple[List[Dict], List[str]]:
    """
    Validate ingredients and use URL scraping if ingredients are not found.
    Optimized to use pre-scraped data if available.
    
    Args:
        selected_ingredients: List of ingredients from AI selection
        reference_url: Optional URL to scrape for ingredient information
        pre_scraped_data: Optional pre-scraped data from early URL scraping
        
    Returns:
        Tuple of (validated_ingredients, missing_ingredients)
    """
    validated_ingredients = []
    missing_ingredients = []
    url_scraped_ingredients = []
    
    # Use pre-scraped data if available, otherwise prepare to scrape
    scraped_ingredients = None
    if pre_scraped_data and pre_scraped_data.get("ingredients"):
        scraped_ingredients = pre_scraped_data.get("ingredients", [])
        print(f"✅ Using pre-scraped ingredients ({len(scraped_ingredients)} found)")
    
    # First, check which ingredients are missing from database (using cache)
    for ing in selected_ingredients:
        ingredient_name = ing.get("ingredient_name", "")
        inci_names = ing.get("inci_aliases", [])
        if ing.get("inci_name"):
            inci_names.insert(0, ing.get("inci_name"))
        
        # Check if ingredient exists in database (with caching)
        db_ingredient = await _check_ingredient_cached(ingredient_name, inci_names)
        
        if db_ingredient:
            validated_ingredients.append(ing)
        else:
            missing_ingredients.append(ing)
    
    # If we have missing ingredients, use pre-scraped data or scrape now
    if missing_ingredients:
        if scraped_ingredients:
            # Use pre-scraped data
            print(f"🔍 Validating {len(missing_ingredients)} missing ingredients against pre-scraped data")
        elif reference_url:
            # Scrape now (fallback if early scraping didn't happen)
            print(f"🔍 {len(missing_ingredients)} ingredients not found in database. Attempting URL scrape from: {reference_url}")
            try:
                scraper = URLScraper()
                extraction_result = await scraper.extract_ingredients_from_url(reference_url)
                
                if extraction_result and extraction_result.get("ingredients"):
                    scraped_ingredients = extraction_result.get("ingredients", [])
                    print(f"✅ Scraped {len(scraped_ingredients)} ingredients from URL")
                else:
                    scraped_ingredients = None
            except Exception as e:
                print(f"⚠️ Error scraping URL for ingredients: {e}")
                scraped_ingredients = None
        
        # Process scraped ingredients if available
        if scraped_ingredients:
            # Normalize scraped ingredients for better matching
            scraped_normalized = {}
            for scraped_ing in scraped_ingredients:
                scraped_lower = scraped_ing.lower().strip()
                # Store both full name and key words for matching
                scraped_normalized[scraped_lower] = scraped_ing
                # Also store key words (first 2-3 words) for partial matching
                words = scraped_lower.split()
                if len(words) > 1:
                    key_phrase = ' '.join(words[:2])
                    if key_phrase not in scraped_normalized:
                        scraped_normalized[key_phrase] = scraped_ing
            
            # Match scraped ingredients with missing ones
            for missing_ing in missing_ingredients:
                missing_name = missing_ing.get("ingredient_name", "").lower().strip()
                missing_inci = missing_ing.get("inci_name", "").lower().strip()
                
                # Check if this ingredient appears in scraped list
                found_in_scraped = False
                matched_scraped_name = None
                
                # Try exact match first
                if missing_name in scraped_normalized:
                    found_in_scraped = True
                    matched_scraped_name = scraped_normalized[missing_name]
                elif missing_inci and missing_inci in scraped_normalized:
                    found_in_scraped = True
                    matched_scraped_name = scraped_normalized[missing_inci]
                else:
                    # Try partial matching - check if key words match
                    missing_words = missing_name.split() if missing_name else []
                    if missing_words:
                        missing_key = ' '.join(missing_words[:2]) if len(missing_words) > 1 else missing_words[0]
                        if missing_key in scraped_normalized:
                            found_in_scraped = True
                            matched_scraped_name = scraped_normalized[missing_key]
                        else:
                            # Check if any scraped ingredient contains the missing ingredient name or vice versa
                            for scraped_lower, scraped_original in scraped_normalized.items():
                                if (missing_name and (missing_name in scraped_lower or scraped_lower in missing_name)) or \
                                   (missing_inci and (missing_inci in scraped_lower or scraped_lower in missing_inci)):
                                    found_in_scraped = True
                                    matched_scraped_name = scraped_original
                                    break
                
                if found_in_scraped:
                    # Update ingredient with scraped information
                    missing_ing["found_via_url"] = True
                    missing_ing["source_url"] = reference_url
                    missing_ing["scraped_ingredient_name"] = matched_scraped_name
                    # If INCI name is missing, try to use the scraped name
                    if not missing_ing.get("inci_name") and matched_scraped_name:
                        missing_ing["inci_name"] = matched_scraped_name
                    validated_ingredients.append(missing_ing)
                    url_scraped_ingredients.append(missing_ing.get("ingredient_name"))
                else:
                    print(f"⚠️ '{missing_ing.get('ingredient_name')}' not found in scraped ingredients from URL")
            
            if url_scraped_ingredients:
                print(f"✅ Validated {len(url_scraped_ingredients)} ingredients via URL scraping: {', '.join(url_scraped_ingredients)}")
    
    # Return validated ingredients and list of still-missing ingredient names
    still_missing = [ing.get("ingredient_name") for ing in missing_ingredients if ing not in validated_ingredients]
    return validated_ingredients, still_missing


# ============================================================================
# COMPLETE PIPELINE FUNCTION
# ============================================================================

async def generate_formula_from_wish(wish_data: dict) -> dict:
    """
    Complete pipeline for generating a formula from user wish.
    
    Args:
        wish_data: Dictionary containing user requirements
        
    Returns:
        Complete formula with all analysis
    """
    
    print("🚀 Starting Make a Wish pipeline...")
    
    # Validate and apply rules engine (ONCE - removed duplicate)
    rules_engine = get_rules_engine()
    can_proceed, validation_results, fixed_wish_data = rules_engine.validate_wish_data(wish_data)
    
    if not can_proceed:
        blocking_errors = [r for r in validation_results if r.severity == ValidationSeverity.BLOCK]
        error_messages = [r.message for r in blocking_errors]
        raise ValueError(f"Validation failed: {'; '.join(error_messages)}")
    
    # Log warnings if any
    warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARN]
    if warnings:
        print(f"⚠️ Validation warnings: {len(warnings)}")
        for warning in warnings:
            print(f"   - {warning.message}")
    
    # Use fixed wish data (with auto-selections applied)
    wish_data = fixed_wish_data
    
    # OPTIMIZATION: Early URL scraping if reference URL provided
    reference_url = wish_data.get('referenceUrl') or wish_data.get('url') or wish_data.get('reference_url')
    pre_scraped_data = await scrape_reference_url_early(reference_url)
    
    # OPTIMIZATION: Pre-validate hero and must-have ingredients
    hero_ingredients = wish_data.get('heroIngredients', [])
    must_have_ingredients = wish_data.get('mustHaveIngredients', [])
    scraped_ing_list = pre_scraped_data.get('ingredients', []) if pre_scraped_data else None
    
    if hero_ingredients or must_have_ingredients:
        valid_hero, valid_must_have, validation_map = await pre_validate_required_ingredients(
            hero_ingredients,
            must_have_ingredients,
            scraped_ing_list
        )
        # Update wish_data with validated ingredients (warn about invalid ones)
        if len(valid_hero) < len(hero_ingredients):
            print(f"⚠️ {len(hero_ingredients) - len(valid_hero)} hero ingredients not validated")
        if len(valid_must_have) < len(must_have_ingredients):
            print(f"⚠️ {len(must_have_ingredients) - len(valid_must_have)} must-have ingredients not validated")
        # Keep original for now, but validation_map can be used in prompt
    
    # Stage 1: Ingredient Selection
    print("📋 Stage 1: Ingredient Selection...")
    selection_prompt = generate_ingredient_selection_prompt(wish_data)
    selected_ingredients = await call_ai_with_claude(
        system_prompt=INGREDIENT_SELECTION_SYSTEM_PROMPT,
        user_prompt=selection_prompt,
        prompt_type="ingredient_selection"
    )
    print(f"✅ Selected {len(selected_ingredients.get('ingredients', []))} ingredients")
    
    # Validate ingredients and use URL scraping if needed (with pre-scraped data)
    if selected_ingredients.get('ingredients'):
        validated_ingredients, missing_ingredients = await validate_and_enrich_ingredients_with_url_fallback(
            selected_ingredients.get('ingredients', []),
            reference_url,
            pre_scraped_data  # Pass pre-scraped data to avoid re-scraping
        )
        
        if missing_ingredients:
            print(f"⚠️ {len(missing_ingredients)} ingredients could not be validated: {', '.join(missing_ingredients)}")
            # Update selected ingredients to only include validated ones
            selected_ingredients['ingredients'] = validated_ingredients
            # Add warning to the response
            if 'warnings' not in selected_ingredients:
                selected_ingredients['warnings'] = []
            selected_ingredients['warnings'].append({
                "severity": "info",
                "category": "ingredient_validation",
                "text": f"The following ingredients could not be found in our database: {', '.join(missing_ingredients)}. They have been excluded from the formula.",
                "solution": "If you have a reference product URL, provide it to enable web search for these ingredients."
            })
        else:
            print(f"✅ All {len(validated_ingredients)} ingredients validated successfully")
    
    # Stage 2: Formula Optimization
    print("🔧 Stage 2: Formula Optimization...")
    optimization_prompt = generate_optimization_prompt(
        wish_data,
        selected_ingredients.get('ingredients', [])
    )
    optimized_formula = await call_ai_with_claude(
        system_prompt=FORMULA_OPTIMIZATION_SYSTEM_PROMPT,
        user_prompt=optimization_prompt,
        prompt_type="formula_optimization"
    )
    print(f"✅ Optimized formula: {optimized_formula.get('optimized_formula', {}).get('total_percentage', 0)}%")
    
    # OPTIMIZATION: Stages 3 and 4 can run in parallel (they both depend only on optimized_formula)
    print("🏭 Stage 3 & 4: Manufacturing Process & Compliance Check (parallel)...")
    manufacturing_prompt = generate_manufacturing_prompt(optimized_formula)
    compliance_prompt = generate_compliance_prompt(optimized_formula)
    
    # Run both stages in parallel
    manufacturing_task = call_ai_with_claude(
        system_prompt=MANUFACTURING_PROCESS_SYSTEM_PROMPT,
        user_prompt=manufacturing_prompt,
        prompt_type="manufacturing_process"
    )
    compliance_task = call_ai_with_claude(
        system_prompt=COMPLIANCE_CHECK_SYSTEM_PROMPT,
        user_prompt=compliance_prompt,
        prompt_type="compliance_check"
    )
    
    # Wait for both to complete
    manufacturing_process, compliance = await asyncio.gather(
        manufacturing_task,
        compliance_task
    )
    
    print(f"✅ Generated {len(manufacturing_process.get('manufacturing_steps', []))} manufacturing steps")
    print(f"✅ Compliance: {compliance.get('overall_status', 'UNKNOWN')}")
    
    # Combine all results
    result = {
        "wish_data": wish_data,
        "ingredient_selection": selected_ingredients,
        "optimized_formula": optimized_formula,
        "manufacturing": manufacturing_process,
        "compliance": compliance,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "formula_version": "1.0",
            "ai_model": "claude-3-opus-20240229",  # Hardcoded to Opus
            "cache_stats": get_cache_manager().get_cache_stats()
        }
    }
    
    print("🎉 Make a Wish pipeline complete!")
    
    return result

