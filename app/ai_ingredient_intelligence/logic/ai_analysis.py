"""
AI Analysis Functions
====================

AI-powered analysis functions using Claude AI.
Extracted from analyze_inci.py for better modularity.
"""

import os
import json
import re
from typing import List, Dict, Optional
from app.ai_ingredient_intelligence.logic.formulynx_taxonomy import (
    FORMULYNX_CANONICAL_TAXONOMY,
    get_price_tier_by_mrp,
    map_category_to_target_area,
    validate_and_filter_keywords
)

# Claude AI setup
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

claude_api_key = os.getenv("CLAUDE_API_KEY")
claude_model = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"

if ANTHROPIC_AVAILABLE and claude_api_key:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        claude_client = None
else:
    claude_client = None


# ============================================================================
# KEYWORD CLEANING AND NORMALIZATION FUNCTIONS
# ============================================================================

def normalize_mrp_keyword(mrp: Optional[float]) -> str:
    """
    Normalize MRP to a single fixed keyword based on Formulynx taxonomy price tiers.
    
    Formulynx Price Tiers:
    - "mass_market": < ₹300
    - "masstige": ₹300 - ₹700
    - "premium": ₹700 - ₹1500
    - "prestige": > ₹1500
    
    Returns a single keyword string (Formulynx taxonomy price_tier ID).
    """
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


def deduplicate_keywords(keywords_list: List[str]) -> List[str]:
    """
    Remove duplicate keywords that mean the same thing.
    Handles synonyms and case-insensitive duplicates.
    """
    if not keywords_list:
        return []
    
    # Normalize keywords (lowercase, strip)
    normalized_map = {}
    seen_normalized = set()
    result = []
    
    # Common synonym mappings (add more as needed)
    synonym_map = {
        "affordable": "budget",
        "cheap": "budget",
        "economy": "budget",
        "expensive": "premium",
        "high_end": "premium",
        "luxurious": "luxury",
        "high_end": "luxury",
        "mid_price": "mid_range",
        "moderate": "mid_range",
        "medium": "mid_range",
    }
    
    for keyword in keywords_list:
        if not keyword or not isinstance(keyword, str):
            continue
        
        # Normalize
        normalized = keyword.strip().lower()
        if not normalized:
            continue
        
        # Check if it's a synonym
        canonical = synonym_map.get(normalized, normalized)
        
        # Only add if we haven't seen this canonical form
        if canonical not in seen_normalized:
            seen_normalized.add(canonical)
            # Keep original casing from first occurrence
            normalized_map[canonical] = keyword.strip()
            result.append(keyword.strip())
    
    return result


def clean_keywords(keywords_dict: Dict[str, any], mrp: Optional[float] = None) -> Dict[str, any]:
    """
    Clean and normalize keywords:
    1. Deduplicate keywords in each category
    2. Normalize MRP to a single fixed keyword
    3. Preserve all taxonomy fields (form, price_tier, target_area, etc.)
    
    Args:
        keywords_dict: Dictionary with keyword categories
        mrp: MRP value for normalization
    
    Returns:
        Cleaned keywords dictionary with all fields preserved
    """
    # Normalize MRP to price tier
    price_tier_value = normalize_mrp_keyword(mrp)
    
    # Get price_tier from keywords_dict if available, otherwise use normalized value
    price_tier = keywords_dict.get("price_tier") or price_tier_value
    
    # Get form from keywords_dict
    form_value = keywords_dict.get("form")
    
    # Handle redundancy: remove form from product_formulation if it exists there
    # (form is the canonical single value, so we don't need it in the list)
    product_formulation = deduplicate_keywords(keywords_dict.get("product_formulation", []))
    if form_value and form_value in product_formulation:
        product_formulation = [pf for pf in product_formulation if pf != form_value]
    
    # Handle redundancy: remove price_tier from mrp list if it exists there
    # (price_tier is the canonical single value, so we don't need it in the list)
    mrp_list = deduplicate_keywords(keywords_dict.get("mrp", []))
    if price_tier and price_tier in mrp_list:
        mrp_list = [m for m in mrp_list if m != price_tier]
    
    cleaned = {
        # List fields - deduplicate
        "product_formulation": product_formulation,
        "mrp": mrp_list,
        "application": deduplicate_keywords(keywords_dict.get("application", [])),
        "functionality": deduplicate_keywords(keywords_dict.get("functionality", [])),
        "benefits": deduplicate_keywords(keywords_dict.get("benefits", [])),
        "concerns": deduplicate_keywords(keywords_dict.get("concerns", [])),
        "market_positioning": deduplicate_keywords(keywords_dict.get("market_positioning", [])),
        "functional_categories": deduplicate_keywords(keywords_dict.get("functional_categories", [])),
        
        # Single value fields - preserve as-is
        "form": form_value,
        "price_tier": price_tier,
        "target_area": keywords_dict.get("target_area"),
        "product_type_id": keywords_dict.get("product_type_id"),
        "main_category": keywords_dict.get("main_category"),
        "subcategory": keywords_dict.get("subcategory")
    }
    
    return cleaned


async def analyze_formulation_and_suggest_matching_with_ai(
    original_ingredients: List[str],
    normalized_ingredients: List[str],
    category_map: Dict[str, str]
) -> Dict[str, any]:
    """
    Use Claude AI to analyze formulation and suggest what ingredients/products to match
    for market research when no active ingredients are found in the database.
    
    Returns dict with:
    - analysis: AI's analysis message
    - product_type: Type of product (cleanser, lotion, etc.)
    - ingredients_to_match: List of normalized ingredient names to use for matching
    """
    if not claude_client:
        return {
            "analysis": None,
            "product_type": None,
            "ingredients_to_match": [],
            "reasoning": None
        }
    
    print(f"    [AI Function] Analyzing formulation with {len(original_ingredients)} ingredients...")
    
    # Build context about what we found
    categorized_ingredients = []
    uncategorized_ingredients = []
    
    for norm_ing in normalized_ingredients:
        category = category_map.get(norm_ing)
        original = next((ing for ing in original_ingredients if ing.strip().lower() == norm_ing), norm_ing)
        if category:
            categorized_ingredients.append(f"- {original} → {category}")
        else:
            uncategorized_ingredients.append(f"- {original}")
    
    system_prompt = """You are an expert cosmetic chemist analyzing formulations for market research matching.

Your task is to:
1. Analyze the formulation to determine if it has active ingredients
2. Identify the product type (cleanser, lotion, serum, etc.)
3. If no actives found, provide a clear analysis message
4. Suggest which ingredients should be used for matching similar products

ANALYSIS APPROACH:
- First, check if there are any therapeutic/active ingredients (moisturizers like urea/glycerin, sunscreens, acne actives, soothing agents, etc.)
- If NO actives found, provide a message like: "This formulation contains no defined active ingredient (e.g., no moisturizer like urea/glycerin, no sunscreen, no acne actives, no soothing agents, etc.). Based on ingredients, it resembles a [product_type]."
- Identify the product type: cleanser, lotion base, cream base, shampoo, conditioner, etc.
- Based on the product type, suggest which ingredients to use for matching (even if they're excipients, they can help find similar base formulations)

MATCHING STRATEGY:
- If actives exist: Use those for matching
- If no actives: Use key functional ingredients that define the product type (e.g., for cleansers: surfactants; for lotions: emollients, humectants)

OUTPUT FORMAT:
Return a JSON object with this structure:
{
  "analysis": "Your analysis message (e.g., 'This formulation contains no defined active ingredient...')",
  "product_type": "cleanser" | "lotion" | "cream" | "serum" | "shampoo" | "conditioner" | "other",
  "ingredients_to_match": ["normalized_ingredient1", "normalized_ingredient2", ...],
  "reasoning": "Brief explanation of matching strategy"
}

The "ingredients_to_match" array should contain NORMALIZED (lowercase, trimmed) ingredient names from the input list that should be used for matching products."""

    user_prompt = f"""Analyze this formulation and determine the matching strategy for market research.

ORIGINAL INGREDIENT LIST:
{chr(10).join(original_ingredients[:50])}

CATEGORIZED INGREDIENT S (from database):
{chr(10).join(categorized_ingredients[:20]) if categorized_ingredients else "None found in database"}

UNCATEGORIZED INGREDIENTS (not in database):
{chr(10).join(uncategorized_ingredients[:30]) if uncategorized_ingredients else "None"}

TASK:
1. Check if this formulation has any active/therapeutic ingredients
2. If NO actives: Provide analysis message explaining why (e.g., "This formulation contains no defined active ingredient...")
3. Identify the product type based on ingredient profile
4. Suggest which ingredients to use for matching (actives if present, or key functional ingredients if no actives)
5. Return normalized ingredient names for matching

Return your analysis as JSON with the structure specified in the system prompt."""

    try:
        # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
        max_tokens = 4096 if "claude-3-opus-20240229" in claude_model else 8192
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=max_tokens,
            temperature=0.2,  # Lower temperature for more consistent classification
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return {
                "analysis": None,
                "product_type": None,
                "ingredients_to_match": [],
                "reasoning": None
            }
        
        content = response.content[0].text.strip()
        
        # Try to extract JSON from the response
        # Handle cases where response might have markdown code blocks
        json_match = re.search(r'\{[^{}]*"ingredients_to_match"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        analysis = result.get("analysis", "")
        product_type = result.get("product_type", "")
        ingredients_to_match = result.get("ingredients_to_match", [])
        reasoning = result.get("reasoning", "")
        
        print(f"    AI Analysis: {analysis}")
        if product_type:
            print(f"    Product Type: {product_type}")
        print(f"    AI Reasoning: {reasoning}")
        
        # Normalize the AI-identified ingredients to match our format
        normalized_actives = []
        for ai_ing in ingredients_to_match:
            normalized = re.sub(r"\s+", " ", str(ai_ing).strip()).strip().lower()
            if normalized and normalized in normalized_ingredients:
                normalized_actives.append(normalized)
        
        return {
            "analysis": analysis,
            "product_type": product_type,
            "ingredients_to_match": normalized_actives,
            "reasoning": reasoning
        }
        
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Error parsing AI response as JSON: {e}")
        print(f"    Response was: {content[:200]}")
        # Return empty dict instead of empty list to maintain structure
        return {
            "analysis": None,
            "product_type": None,
            "ingredients_to_match": [],
            "reasoning": None
        }
    except Exception as e:
        print(f"    ⚠️  Error calling Claude AI: {e}")
        import traceback
        traceback.print_exc()
        # Return empty dict instead of empty list to maintain structure
        return {
            "analysis": None,
            "product_type": None,
            "ingredients_to_match": [],
            "reasoning": None
        }


async def analyze_product_categories_with_ai(
    ingredients: List[str],
    normalized_ingredients: List[str],
    extracted_text: str = "",
    product_name: str = "",
    url: str = ""
) -> Dict[str, any]:
    """
    Use Claude AI to analyze input URL/INCI and determine product categories and subcategories.
    
    Args:
        ingredients: List of ingredient names
        normalized_ingredients: Normalized ingredient names
        extracted_text: Extracted text from URL scraping
        product_name: Product name if available
        url: Product URL if available (helps AI understand product context)
    
    Returns dict with:
    - primary_category: Main category (haircare, skincare, lipcare, bodycare, etc.)
    - subcategory: Specific product type (serum, cleanser, shampoo, etc.)
    - interpretation: AI's interpretation of the input
    - confidence: Confidence level (high, medium, low)
    """
    if not claude_client:
        return {
            "primary_category": None,
            "subcategory": None,
            "interpretation": None,
            "confidence": "low"
        }
    
    print(f"    [AI Category Analysis] Analyzing {len(ingredients)} ingredients for category identification...")
    
    system_prompt = """You are an expert cosmetic product analyst specializing in product categorization.

Your task is to analyze product ingredients and determine:
1. PRIMARY CATEGORY: The main product category (haircare, skincare, lipcare, bodycare, etc.)
2. SUBCATEGORY: The specific product type (serum, cleanser, shampoo, conditioner, face mask, etc.)

CATEGORY DEFINITIONS:
- **haircare**: Products for hair and scalp (shampoo, conditioner, hair mask, hair serum, hair oil, scalp treatment)
- **skincare**: Products for facial skin (cleanser, serum, moisturizer, toner, face mask, eye cream, sunscreen, exfoliant)
- **lipcare**: Products specifically for lips (lip balm, lip scrub, lip mask, lip serum)
- **bodycare**: Products for body skin (body lotion, body wash, body scrub, body oil)
- **other**: Products that don't fit clearly into above categories

SUBCATEGORY EXAMPLES:
- Skincare: cleanser, serum, moisturizer, toner, face mask, eye cream, sunscreen, exfoliant, face oil
- Haircare: shampoo, conditioner, hair mask, hair serum, hair oil, scalp treatment, hair spray
- Lipcare: lip balm, lip scrub, lip mask, lip serum
- Bodycare: body lotion, body wash, body scrub, body oil

CRITICAL ANALYSIS APPROACH (in priority order):
1. **PRODUCT URL/NAME CONTEXT IS PRIMARY**: 
   - If URL path contains clear category indicators (e.g., "/cleanser", "/shampoo", "/conditioner", "/serum", "/cetaphil", "/face", "/hair", "/lip"), use this as the PRIMARY indicator
   - If product name contains category indicators, use this as PRIMARY indicator
   - URLs and product names are highly reliable indicators
2. **Ingredient profile analysis**: Analyze ingredient combinations (e.g., surfactants suggest cleanser/shampoo, but distinguish based on context)
3. **Category-specific ingredients**: Look for category-specific ingredients (e.g., hair conditioning agents, facial actives)
4. **Common patterns**: 
   - "cleanser" in URL/name → skincare/cleanser (NOT haircare/conditioner)
   - "face" or "facial" in URL/name → skincare
   - "hair" in URL/name → haircare
   - "lip" in URL/name → lipcare
   - "body" in URL/name → bodycare

IMPORTANT RULES:
- If product name contains "cleanser", it is ALWAYS skincare/cleanser, NOT haircare/conditioner
- If product name contains "face" or "facial", it is ALWAYS skincare
- If product name contains "hair", it is ALWAYS haircare
- If product name contains "lip" (e.g., "lip balm", "lipstick", "lip care", "lip serum"), it is ALWAYS lipcare, NOT haircare or skincare
- If product name contains "balm" and context suggests lips (e.g., "lip balm"), it is ALWAYS lipcare
- Product name context takes precedence over ingredient analysis when there's ambiguity

OUTPUT FORMAT:
Return a JSON object with this structure:
{
  "primary_category": "haircare" | "skincare" | "lipcare" | "bodycare" | "other",
  "subcategory": "serum" | "cleanser" | "shampoo" | "conditioner" | etc.,
  "interpretation": "Detailed interpretation explaining the category determination",
  "confidence": "high" | "medium" | "low"
}

Be specific and accurate. If uncertain, use "other" as primary_category and set confidence to "low"."""

    user_prompt = f"""Analyze this product formulation and determine its category and subcategory.

{f'**PRODUCT URL (HIGHEST PRIORITY): {url}**' if url else ''}
{f'**PRODUCT NAME/CONTEXT (HIGHEST PRIORITY): {product_name}**' if product_name else ''}

INGREDIENTS:
{chr(10).join(f"- {ing}" for ing in ingredients[:50])}

{f'EXTRACTED TEXT (if available): {extracted_text[:500]}' if extracted_text else ''}

TASK (follow priority order):
1. **FIRST**: Check URL path and product name for category indicators (cleanser, shampoo, conditioner, face, hair, lip, body, etc.)
   - URL paths often contain product type information (e.g., "/cetaphil-gentle-skin-cleanser" → skincare/cleanser)
   - Product names are also highly reliable indicators
2. Analyze the ingredient profile to confirm or refine the category
3. Determine the primary category (haircare, skincare, lipcare, bodycare, or other)
4. Identify the specific subcategory/product type
5. Provide a clear interpretation explaining your reasoning, emphasizing how URL/product name/context influenced the decision
6. Assess confidence level (high if URL/product name clearly indicates category, medium/low if relying mainly on ingredients)

CRITICAL: If the URL path or product name contains words like "cleanser", "face", "facial", "hair", "lip", or "body", use that as the PRIMARY indicator. URLs and product names are more reliable than ingredient analysis alone.

Return your analysis as JSON with the structure specified in the system prompt."""

    try:
        max_tokens = 4096 if "claude-3-opus-20240229" in claude_model else 8192
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=max_tokens,
            temperature=0.1,  # Lower temperature for more consistent categorization
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return {
                "primary_category": None,
                "subcategory": None,
                "interpretation": None,
                "confidence": "low"
            }
        
        content = response.content[0].text.strip()
        
        # Extract JSON
        json_match = re.search(r'\{[^{}]*"primary_category"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        primary_category = result.get("primary_category", "").lower() if result.get("primary_category") else None
        subcategory = result.get("subcategory", "").lower() if result.get("subcategory") else None
        interpretation = result.get("interpretation", "")
        confidence = result.get("confidence", "low")
        
        print(f"    AI Category Analysis:")
        print(f"      Primary Category: {primary_category}")
        print(f"      Subcategory: {subcategory}")
        print(f"      Confidence: {confidence}")
        
        return {
            "primary_category": primary_category,
            "subcategory": subcategory,
            "interpretation": interpretation,
            "confidence": confidence
        }
        
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Error parsing AI category response as JSON: {e}")
        print(f"    Response was: {content[:200]}")
        return {
            "primary_category": None,
            "subcategory": None,
            "interpretation": None,
            "confidence": "low"
        }
    except Exception as e:
        print(f"    ⚠️  Error calling Claude AI for category analysis: {e}")
        import traceback
        traceback.print_exc()
        return {
            "primary_category": None,
            "subcategory": None,
            "interpretation": None,
            "confidence": "low"
        }


async def generate_market_research_overview_with_ai(
    input_ingredients: List[str],
    matched_products: List[Dict],
    category_info: Dict[str, any],
    total_matched: int,
    selected_keywords: Optional[Dict[str, List[str]]] = None,
    structured_analysis: Optional[Dict[str, any]] = None
) -> str:
    """
    Use Claude AI to generate a concluding overview of the market research.
    
    Args:
        input_ingredients: List of input ingredients
        matched_products: List of matched products
        category_info: Category information dict
        total_matched: Total number of matched products
        selected_keywords: Optional selected keywords used for filtering (ProductKeywords format)
        structured_analysis: Optional structured analysis data
    
    Returns a comprehensive overview string summarizing the research findings.
    Always returns a string, never None.
    """
    # If no products matched, return a default overview
    if len(matched_products) == 0:
        category = category_info.get('primary_category', 'product')
        subcategory = category_info.get('subcategory', 'product')
        return f"Market Research Overview\n\nNo matching products were found for this {category} {subcategory} formulation. This may indicate:\n- Unique ingredient combination\n- Limited market presence\n- Need for custom formulation\n\nConsider expanding the search criteria or exploring alternative ingredient combinations."
    
    if not claude_client:
        # Fallback overview when AI is not available
        category = category_info.get('primary_category', 'product')
        subcategory = category_info.get('subcategory', 'product')
        top_products = matched_products[:5]
        product_names = [p.get("productName", "Unknown") for p in top_products]
        return f"Market Research Overview\n\nFound {total_matched} matching {category} {subcategory} products in the market.\n\nTop Matched Products:\n" + "\n".join(f"- {name}" for name in product_names) + f"\n\nThis analysis identified {total_matched} products with similar active ingredient profiles. Review the detailed product list for specific ingredient matches and formulations."
    
    print(f"    [AI Overview] Generating market research overview for {len(matched_products)} products...")
    
    # Build product summary for AI
    product_summaries = []
    for i, product in enumerate(matched_products[:20]):  # Limit to top 20 for overview
        product_summaries.append({
            "name": product.get("productName", "Unknown"),
            "brand": product.get("brand", ""),
            "matched_actives": product.get("active_ingredients", [])[:5],
            "match_percentage": product.get("match_percentage", 0),
            "category": product.get("category", ""),
            "subcategory": product.get("subcategory", "")
        })
    
    system_prompt = """You are an expert market research analyst specializing in cosmetic and personal care products.

Your task is to generate a comprehensive, insightful overview of market research findings.

OVERVIEW STRUCTURE:
1. **Summary**: Brief overview of what was researched
2. **Key Findings**: Main insights about the market landscape
3. **Product Trends**: Notable patterns in matched products (ingredients, categories, brands)
4. **Market Insights**: What the research reveals about the competitive landscape
5. **Recommendations**: Actionable insights based on the findings

TONE:
- Professional and analytical
- Clear and concise
- Data-driven with specific observations
- Actionable insights

OUTPUT FORMAT:
Return a well-structured text overview (not JSON). Use clear sections and bullet points where appropriate."""

    # Build selected keywords section if provided
    selected_keywords_section = ""
    if selected_keywords:
        selected_keywords_section = f"""
SELECTED KEYWORDS (used for filtering):
- Product Formulation: {', '.join(selected_keywords.get('product_formulation', [])) or 'None'}
- MRP Range: {', '.join(selected_keywords.get('mrp', [])) or 'None'}
- Application: {', '.join(selected_keywords.get('application', [])) or 'None'}
- Functionality: {', '.join(selected_keywords.get('functionality', [])) or 'None'}
"""
    
    # Build structured analysis section if provided
    structured_analysis_section = ""
    if structured_analysis:
        structured_analysis_section = f"""
PRODUCT ANALYSIS:
- Form: {structured_analysis.get('form', 'Unknown')}
- Main Category: {structured_analysis.get('main_category', 'Unknown')}
- Subcategory: {structured_analysis.get('subcategory', 'Unknown')}
- MRP: ₹{structured_analysis.get('mrp', 'N/A')} ({structured_analysis.get('mrp_source', 'unknown')} source)
- Functional Categories: {', '.join(structured_analysis.get('functional_categories', [])) or 'None'}
- Application Types: {', '.join(structured_analysis.get('application', [])) or 'None'}
"""
    
    user_prompt = f"""Generate a comprehensive market research overview based on the following data:

INPUT PRODUCT INGREDIENTS:
{chr(10).join(f"- {ing}" for ing in input_ingredients[:20])}

CATEGORY ANALYSIS:
- Primary Category: {category_info.get('primary_category', 'Unknown')}
- Subcategory: {category_info.get('subcategory', 'Unknown')}
- Interpretation: {category_info.get('interpretation', 'N/A')}
{structured_analysis_section}{selected_keywords_section}
MATCHED PRODUCTS ({total_matched} total, showing top {len(product_summaries)}):
{json.dumps(product_summaries, indent=2)}

TASK:
Generate a comprehensive market research overview that includes:
1. Summary of the research (mention selected keywords if provided)
2. Key findings about the market
3. Product trends and patterns (consider the selected keywords/filters applied)
4. Market insights (relate to the filtering criteria if keywords were selected)
5. Recommendations (based on the filtered results and selected criteria)

Make it insightful, professional, and actionable. If keywords were selected for filtering, acknowledge how they influenced the results."""

    try:
        max_tokens = 4096 if "claude-3-opus-20240229" in claude_model else 8192
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=max_tokens,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            # Return fallback overview if AI response is empty
            category = category_info.get('primary_category', 'product')
            subcategory = category_info.get('subcategory', 'product')
            return f"Market Research Overview\n\nFound {total_matched} matching {category} {subcategory} products. Review the product list for detailed ingredient matches and formulations."
        
        overview = response.content[0].text.strip()
        
        # Ensure overview is not empty
        if not overview:
            category = category_info.get('primary_category', 'product')
            subcategory = category_info.get('subcategory', 'product')
            overview = f"Market Research Overview\n\nFound {total_matched} matching {category} {subcategory} products. Review the product list for detailed ingredient matches and formulations."
        
        print(f"    ✓ Generated market research overview ({len(overview)} characters)")
        
        return overview
        
    except Exception as e:
        print(f"    ⚠️  Error generating market research overview: {e}")
        import traceback
        traceback.print_exc()
        # Return fallback overview on error
        category = category_info.get('primary_category', 'product')
        subcategory = category_info.get('subcategory', 'product')
        return f"Market Research Overview\n\nFound {total_matched} matching {category} {subcategory} products. An error occurred while generating the detailed overview. Review the product list for specific ingredient matches and formulations."


async def enhance_product_ranking_with_ai(
    products: List[Dict],
    input_actives: List[str],
    original_ingredients: List[str]
) -> List[Dict]:
    """
    Use AI to intelligently re-rank products based on ingredient analysis.
    Considers ingredient importance, concentration, and product similarity.
    """
    if not claude_client or len(products) == 0:
        return products
    
    # Limit to top 20 products for AI analysis (to avoid too many API calls)
    products_to_analyze = products[:20]
    
    # Build product summary for AI
    product_summaries = []
    for i, product in enumerate(products_to_analyze):
        product_summaries.append({
            "index": i,
            "name": product.get("productName", "Unknown"),
            "brand": product.get("brand", ""),
            "matched_actives": product.get("active_ingredients", [])[:5],  # Top 5
            "match_percentage": product.get("match_percentage", 0),
            "total_ingredients": product.get("total_ingredients", 0)
        })
    
    system_prompt = """You are an expert cosmetic product analyst specializing in market research and product matching.

Your task is to analyze and rank products based on their similarity to a target product's active ingredients.

RANKING CRITERIA (in order of importance):
1. **Active Ingredient Match Quality**: Products with more matching active ingredients rank higher
2. **Ingredient Importance**: Key actives (e.g., Retinol, Niacinamide, Salicylic Acid) are more important than less common ones
3. **Match Completeness**: Products that match ALL or most target actives rank higher than partial matches
4. **Product Relevance**: Products with similar active profiles are more relevant

OUTPUT FORMAT:
Return a JSON object with this structure:
{
  "ranked_indices": [3, 1, 5, 2, ...],  // Product indices in order of relevance (0-based)
  "reasoning": "Brief explanation of ranking logic"
}

The ranked_indices array should contain the product indices (from the input) in order from most relevant to least relevant."""

    user_prompt = f"""Analyze and rank the following products based on their similarity to the target product's active ingredients.

TARGET PRODUCT ACTIVE INGREDIENTS:
{chr(10).join(f"- {ing}" for ing in input_actives[:10])}

PRODUCTS TO RANK:
{json.dumps(product_summaries, indent=2)}

TASK:
1. Analyze each product's matched active ingredients
2. Compare them to the target product's active ingredients
3. Rank products from most similar/relevant to least similar
4. Consider both the number of matches and the importance of matched ingredients

Return your ranking as JSON with the structure specified in the system prompt."""

    try:
        # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
        max_tokens = 4096 if "claude-3-opus-20240229" in claude_model else 8192
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return products
        
        content = response.content[0].text.strip()
        
        # Extract JSON
        json_match = re.search(r'\{[^{}]*"ranked_indices"[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        ranked_indices = result.get("ranked_indices", [])
        reasoning = result.get("reasoning", "")
        
        print(f"    AI Ranking Reasoning: {reasoning}")
        
        # Re-order products based on AI ranking
        if ranked_indices and len(ranked_indices) == len(products_to_analyze):
            # Create mapping from index to product
            reordered = []
            used_indices = set()
            for idx in ranked_indices:
                if 0 <= idx < len(products_to_analyze) and idx not in used_indices:
                    reordered.append(products_to_analyze[idx])
                    used_indices.add(idx)
            
            # Add any products not in the AI ranking (shouldn't happen, but safety check)
            for i, product in enumerate(products_to_analyze):
                if i not in used_indices:
                    reordered.append(product)
            
            # Combine with products not analyzed
            return reordered + products[len(products_to_analyze):]
        
        return products
        
    except Exception as e:
        print(f"    ⚠️  Error in AI ranking: {e}")
        return products


def ensure_complete_analysis(result: Dict[str, any], ingredients: List[str], product_name: str = "", url: str = "") -> Dict[str, any]:
    """
    Ensure analysis result has no null/empty fields by providing intelligent fallbacks.
    
    Args:
        result: AI analysis result that may have null/empty fields
        ingredients: List of ingredients for inference
        product_name: Product name for context
        url: Product URL for context
    
    Returns:
        Complete analysis result with all fields filled
    """
    from app.ai_ingredient_intelligence.logic.formulynx_taxonomy import (
        map_category_to_target_area, get_price_tier_by_mrp
    )
    
    # Helper function to infer product type from ingredients
    def infer_product_type():
        ingredient_str = " ".join(ingredients).lower()
        
        # Check for cleanser indicators
        if any(indicator in ingredient_str for indicator in ["surfact", "sodium laureth", "sodium lauryl", "cocamidopropyl", "glucoside"]):
            return "cleanser"
        
        # Check for serum indicators  
        if any(indicator in ingredient_str for indicator in ["hyaluronic", "niacinamide", "vitamin c", "ascorbic", "retinol"]):
            return "serum"
            
        # Check for moisturizer indicators
        if any(indicator in ingredient_str for indicator in ["ceramide", "glycerin", "butyrospermum", "shea", "dimethicone"]):
            return "moisturizer"
            
        # Check for sunscreen indicators
        if any(indicator in ingredient_str for indicator in ["zinc oxide", "titanium dioxide", "avobenzone", "octocrylene"]):
            return "sunscreen"
            
        # Check for shampoo indicators
        if any(indicator in ingredient_str for indicator in ["sodium laureth sulfate", "cocamidopropyl betaine", "behentrimonium"]):
            return "shampoo"
            
        # Default fallback
        return "serum"
    
    # Helper function to infer benefits from ingredients
    def infer_benefits():
        ingredient_str = " ".join(ingredients).lower()
        benefits = []
        
        if any(indicator in ingredient_str for indicator in ["hyaluronic", "glycerin", "ceramide", "urea"]):
            benefits.extend(["hydrating", "moisturizing"])
            
        if any(indicator in ingredient_str for indicator in ["niacinamide", "vitamin c", "ascorbic", "kojic"]):
            benefits.extend(["brightening", "dark_spot_correcting"])
            
        if any(indicator in ingredient_str for indicator in ["salicylic", "glycolic", "lactic", "mandelic"]):
            benefits.extend(["exfoliating", "smoothening"])
            
        if any(indicator in ingredient_str for indicator in ["retinol", "peptide", "collagen"]):
            benefits.extend(["anti_aging", "anti_wrinkle"])
            
        if any(indicator in ingredient_str for indicator in ["zinc", "tea tree", "salicylic"]):
            benefits.extend(["anti_acne", "purifying"])
            
        if any(indicator in ingredient_str for indicator in ["ceramide", "dimethicone", "petrolatum"]):
            benefits.extend(["barrier_repair"])
            
        return list(set(benefits)) or ["hydrating"]  # Default to hydrating if no benefits found
    
    # Helper function to infer concerns from benefits
    def infer_concerns(benefits_list):
        benefit_to_concern = {
            "hydrating": ["dryness", "dehydration"],
            "brightening": ["dark_spots", "uneven_tone", "dullness"],
            "anti_aging": ["fine_lines", "wrinkles", "loss_of_elasticity"],
            "anti_acne": ["acne", "blackheads", "excess_sebum"],
            "barrier_repair": ["compromised_barrier", "dryness"],
            "exfoliating": ["rough_texture", "congestion"]
        }
        
        concerns = []
        for benefit in benefits_list:
            if benefit in benefit_to_concern:
                concerns.extend(benefit_to_concern[benefit])
        
        return list(set(concerns)) or ["dryness"]  # Default to dryness
    
    # Start with the result and fill missing fields
    complete_result = result.copy()
    
    # Ensure basic fields
    complete_result["active_ingredients"] = result.get("active_ingredients", [])
    complete_result["mrp"] = result.get("mrp", 499.0)  # Default MRP
    complete_result["mrp_per_ml"] = result.get("mrp_per_ml", complete_result["mrp"] / 30.0)  # Assume 30ml
    complete_result["mrp_source"] = result.get("mrp_source", "ai_estimated")
    
    # Get or infer form
    form = result.get("form")
    if not form:
        form = infer_product_type()
    
    complete_result["form"] = form
    
    # Get or infer target area
    target_area = result.get("target_area")
    if not target_area:
        if form in ["shampoo", "conditioner", "hair_mask", "hair_serum", "hair_oil"]:
            target_area = "hair"
        elif form in ["lip_balm", "lip_scrub", "lip_mask"]:
            target_area = "lips"
        else:
            target_area = "face"  # Default to face
    
    # Get or infer product_type_id
    product_type_id = result.get("product_type_id")
    if not product_type_id:
        product_type_id = form  # Use form as product_type_id
    
    complete_result["target_area"] = target_area
    complete_result["product_type_id"] = product_type_id
    
    # Get or infer main category and subcategory
    main_category = result.get("main_category")
    if not main_category:
        main_category = "skincare" if target_area == "face" else "haircare" if target_area == "hair" else "lipcare" if target_area == "lips" else "bodycare"
    
    subcategory = result.get("subcategory")
    if not subcategory:
        subcategory = f"{target_area}_{form}" if target_area != "face" else form
    
    complete_result["main_category"] = main_category
    complete_result["subcategory"] = subcategory
    
    # Get or infer benefits and concerns
    keywords = result.get("keywords", {})
    benefits = keywords.get("benefits", [])
    if not benefits:
        benefits = infer_benefits()
    
    concerns = keywords.get("concerns", [])
    if not concerns:
        concerns = infer_concerns(benefits)
    
    # Get or infer price tier
    mrp_value = complete_result["mrp"]
    price_tier = keywords.get("price_tier") or get_price_tier_by_mrp(mrp_value)
    
    # Build complete keywords object
    complete_keywords = {
        "product_formulation": keywords.get("product_formulation", [form]) if form else [],
        "form": form,
        "mrp": keywords.get("mrp", [price_tier]) if price_tier else ["masstige"],
        "price_tier": price_tier,
        "application": keywords.get("application", ["daily_use"]),
        "functionality": keywords.get("functionality", benefits.copy()),
        "benefits": benefits,
        "target_area": target_area,
        "product_type_id": product_type_id,
        "concerns": concerns,
        "market_positioning": keywords.get("market_positioning", ["natural"]),
        "functional_categories": keywords.get("functional_categories", benefits.copy()),
        "main_category": main_category,
        "subcategory": subcategory
    }
    
    complete_result["keywords"] = complete_keywords
    complete_result["functional_categories"] = benefits.copy()
    complete_result["application"] = ["daily_use"]
    
    return complete_result


async def extract_structured_product_info_with_ai(
    ingredients: List[str],
    extracted_text: str = "",
    product_name: str = "",
    url: str = "",
    input_type: str = "inci",
    scraped_price: Optional[float] = None
) -> Dict[str, any]:
    """
    Extract structured product information using AI analysis.
    
    Args:
        ingredients: List of INCI ingredient names
        extracted_text: Full scraped text from URL (if URL input)
        product_name: Product name if available
        url: Product URL if available
        input_type: "url" or "inci"
        scraped_price: Price extracted from scraping (if URL input)
    
    Returns dict with:
    - active_ingredients: List of {name, percentage}
    - mrp: MRP value
    - mrp_per_ml: MRP per ml
    - mrp_source: "scraped" or "ai_estimated"
    - form: Product form (serum, cream, etc.) - Formulynx taxonomy form ID
    - functional_categories: List of functional categories
    - main_category: Main category (skincare, haircare, etc.)
    - subcategory: Subcategory
    - application: List of application types
    - keywords: Dict with product_formulation, mrp, application, functionality
    - target_area: Formulynx target area ID
    - product_type_id: Formulynx product type ID
    - concerns: List of Formulynx concern IDs
    - benefits: List of Formulynx benefit IDs
    - price_tier: Formulynx price tier ID
    - market_positioning: List of Formulynx market positioning IDs
    """
    if not claude_client:
        # Create fallback result and ensure completeness
        fallback_result = {
            "active_ingredients": [],
            "mrp": None,
            "mrp_per_ml": None,
            "mrp_source": None,
            "form": None,
            "functional_categories": [],
            "main_category": None,
            "subcategory": None,
            "application": [],
            "keywords": {
                "product_formulation": [],
                "mrp": [],
                "application": [],
                "functionality": [],
                "form": None,
                "target_area": None,
                "product_type_id": None,
                "concerns": [],
                "benefits": [],
                "price_tier": None,
                "market_positioning": [],
                "functional_categories": [],
                "main_category": None,
                "subcategory": None
            }
        }
        
        # Ensure all fields are complete with intelligent fallbacks
        complete_result = ensure_complete_analysis(fallback_result, ingredients, product_name, url)
        return complete_result
    
    print(f"    [AI Structured Analysis] Analyzing product information...")
    
    # Build ingredients text
    ingredients_text = "\n".join(f"- {ing}" for ing in ingredients[:50])
    
    # Build context text
    context_parts = []
    if url:
        context_parts.append(f"**PRODUCT URL: {url}**")
    if product_name:
        context_parts.append(f"**PRODUCT NAME: {product_name}**")
    if scraped_price:
        context_parts.append(f"**SCRAPED PRICE: ₹{scraped_price}**")
    if extracted_text:
        context_parts.append(f"**EXTRACTED TEXT (first 1000 chars):\n{extracted_text[:1000]}**")
    
    context = "\n\n".join(context_parts) if context_parts else ""
    
    # Build taxonomy keywords for AI prompt (hardcoded in prompt)
    system_prompt = """You are an expert cosmetic product analyst. Extract structured product information from the provided data.

You MUST use Formulynx Canonical Taxonomy IDs for classification. This ensures consistency and enables proper categorization.

Your task is to analyze the product and return ONLY a valid JSON object with the following structure:
{{
  "active_ingredients": [
    {{"name": "Niacinamide", "percentage": "10%"}},
    {{"name": "Hyaluronic Acid", "percentage": "2%"}}
  ],
  "mrp": 1299.00,
  "mrp_per_ml": 12.99,
  "mrp_source": "scraped" | "ai_estimated",
  "keywords": {{
    "product_formulation": ["serum", "water_based"],
    "form": "serum",
    "mrp": ["premium"],
    "price_tier": "premium",
    "target_area": "face",
    "product_type_id": "serum",
    "concerns": ["dark_spots", "acne", "dryness"],
    "benefits": ["brightening", "hydrating", "anti_aging"],
    "functionality": ["brightening", "moisturizing", "anti_acne"],
    "market_positioning": ["natural", "clinical"],
    "application": ["night_cream", "brightening", "daily_use"],
    "functional_categories": ["brightening", "moisturizing", "anti_aging"],
    "main_category": "skincare",
    "subcategory": "face_serum"
  }}
}}

FORMULYNX TAXONOMY REFERENCE (use exact IDs):

Available Forms: "cream", "lotion", "milk", "balm", "butter", "ointment", "pomade", "paste", "gel", "serum", "essence", "toner", "ampoule", "water", "emulsion", "fluid", "drops", "oil", "cleansing_balm", "spray", "mist", "aerosol", "stick", "bar", "powder", "wax", "foam", "mousse", "whip", "sheet", "patches", "pad", "scrub", "peel", "clay"

Target Areas: "face", "undereye", "lips", "neck", "body", "hands", "feet", "scalp", "hair"

Product Types for Face: "cleanser", "exfoliator", "toner", "serum", "spot_treatment", "moisturizer", "face_oil", "sunscreen", "mask", "face_mist"
Product Types for Hair: "shampoo", "conditioner", "hair_mask", "hair_serum", "hair_oil", "scalp_treatment", "hair_spray", "styling_cream", "styling_gel", "mousse", "texturizer", "pomade_wax", "heat_protectant", "uv_protectant", "color_care"

Concerns for Face: "dark_spots", "uneven_tone", "melasma", "post_inflammatory_hyperpigmentation", "sun_spots", "dullness", "tan", "sallowness", "fine_lines", "wrinkles", "deep_wrinkles", "sagging", "loss_of_elasticity", "crepey_skin", "volume_loss", "large_pores", "rough_texture", "uneven_texture", "congestion", "milia", "acne", "blackheads", "whiteheads", "cystic_acne", "fungal_acne", "acne_scars", "excess_sebum", "dryness", "dehydration", "flakiness", "tight_skin", "compromised_barrier", "trans_epidermal_water_loss", "redness", "rosacea", "irritation", "reactive_skin", "eczema", "psoriasis", "contact_dermatitis", "oiliness", "enlarged_oil_glands", "combination_skin"

Benefits for Face: "hydrating", "moisturizing", "barrier_repair", "plumping", "brightening", "dark_spot_correcting", "tone_evening", "radiance_boosting", "detan", "anti_aging", "anti_wrinkle", "firming", "lifting", "collagen_boosting", "elasticity_improving", "anti_acne", "pore_minimizing", "oil_control", "mattifying", "purifying", "clarifying", "exfoliating", "smoothening", "resurfacing", "cell_renewal", "soothing", "anti_inflammatory", "redness_reducing", "sun_protection", "antioxidant", "pollution_protection", "nourishing", "revitalizing", "strengthening"

Market Positioning: "natural", "organic", "clinical", "ayurvedic", "korean", "japanese", "french", "sustainable", "vegan", "cruelty_free", "fragrance_free", "dermat_tested", "salon_professional", "pharmacy", "luxury", "clean_beauty", "reef_safe", "waterless", "indie"

Price Tiers (based on MRP):
- "mass_market" for MRP < ₹300
- "masstige" for MRP ₹300-₹700
- "premium" for MRP ₹700-₹1500
- "prestige" for MRP > ₹1500

RULES:
1. **active_ingredients**: Extract active ingredients with percentages if mentioned. If percentage not available, set to null.
   - Look for patterns like "Niacinamide 10%", "Vitamin C 20%", "Retinol 0.5%"
   - Only include ingredients with therapeutic/active properties (not excipients)

2. **mrp**: 
   - If scraped_price is provided, use it as mrp
   - If not, estimate based on product type, brand, and market standards
   - For serums: typically ₹500-3000
   - For creams: typically ₹300-2000
   - For cleansers: typically ₹200-1500
   - Set mrp_source to "scraped" if scraped_price provided, else "ai_estimated"

3. **mrp_per_ml**: Calculate mrp / volume (if volume can be inferred from product name/description)
   - Common sizes: 30ml, 50ml, 100ml, 200ml
   - If volume unknown, estimate based on product type (serums usually 30ml, creams 50ml)

4. **keywords**: ALL taxonomy fields MUST be inside the keywords object. YOU MUST INFER THESE VALUES from ingredients, product name, and context - do NOT leave them as null/empty unless absolutely impossible to determine:
    - **product_formulation**: Array of Formulynx form IDs (e.g., ["serum", "water_based"]). Infer from product name, ingredients, or context.
    - **form**: Single primary Formulynx form ID (e.g., "serum", "cream", "gel"). MUST be set - infer from product name or ingredients (e.g., if ingredients suggest a lightweight water-based formula, likely "serum" or "essence").
    - **mrp**: Array with EXACTLY ONE Formulynx price_tier ID: ["mass_market"], ["masstige"], ["premium"], or ["prestige"]. Calculate from mrp value above.
    - **price_tier**: Single Formulynx price tier ID (same as mrp[0]). Calculate from mrp value above.
    - **target_area**: Single Formulynx target area ID: "face", "hair", "body", "lips", "undereye", "neck", "hands", "feet", "scalp". MUST be set - infer from product name, ingredients, or context (e.g., if it's a serum with ceramides and hyaluronic acid, likely "face").
    - **product_type_id**: Single Formulynx product type ID: "cleanser", "serum", "moisturizer", "shampoo", etc. MUST be set - infer from form and ingredients (e.g., if form is "serum", product_type_id should be "serum").
    - **concerns**: Array of Formulynx concern IDs (e.g., ["acne", "dark_spots", "dryness"]). Infer from active ingredients and their known benefits (e.g., Ceramides → ["dryness", "compromised_barrier"], Hyaluronic Acid → ["dehydration", "dryness"]).
    - **benefits**: Array of Formulynx benefit IDs (e.g., ["brightening", "hydrating", "anti_aging"]). MUST NOT be empty - infer from active ingredients (e.g., Ceramides → ["barrier_repair", "moisturizing"], Hyaluronic Acid → ["hydrating", "plumping"]).
    - **functionality**: Array of Formulynx benefit IDs (same as benefits, for backward compatibility). MUST match benefits array.
    - **market_positioning**: Array of Formulynx market positioning IDs (e.g., ["natural", "clinical"]). Infer from ingredients (e.g., if contains natural extracts → ["natural"], if contains clinical actives → ["clinical"]).
    - **application**: Array of application keywords (legacy). Infer from benefits and product type (e.g., hydrating serum → ["daily_use", "hydrating"]).
    - **functional_categories**: Array of functional categories (legacy). Should match benefits array.
    - **main_category**: "skincare", "haircare", "lipcare", "bodycare" (legacy). MUST be set - infer from target_area (e.g., "face" → "skincare", "hair" → "haircare").
    - **subcategory**: Product subcategory (legacy). Infer from product_type_id and target_area (e.g., "face" + "serum" → "face_serum").

CRITICAL RULES FOR KEYWORDS:
- **NEVER leave target_area, product_type_id, main_category, or subcategory as null** - always infer from available information
- **NEVER leave benefits or functionality as empty arrays** - always infer from active ingredients
- **If concerns cannot be determined, use empty array [] (not null)**
- **If market_positioning cannot be determined, use empty array [] (not null)**
- **ALL taxonomy fields (form, target_area, product_type_id, concerns, benefits, price_tier, market_positioning) MUST be inside the keywords object, NOT at the top level of the response**

Return ONLY valid JSON, no markdown code blocks, no explanations."""

    user_prompt = f"""Extract structured product information from this data:

{context}

INGREDIENTS:
{ingredients_text}

Extract all fields as specified in the system prompt. Return ONLY the JSON object."""

    try:
        max_tokens = 4096 if "claude-3-opus-20240229" in claude_model else 8192
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            raise ValueError("Empty response from AI")
        
        content = response.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        
        # Ensure keywords structure exists
        if "keywords" not in result:
            result["keywords"] = {
                "product_formulation": [],
                "mrp": [],
                "application": [],
                "functionality": []
            }
        
        # Ensure all keyword categories exist
        keywords = result.get("keywords", {})
        if "product_formulation" not in keywords:
            keywords["product_formulation"] = []
        if "mrp" not in keywords:
            keywords["mrp"] = []
        if "application" not in keywords:
            keywords["application"] = []
        if "functionality" not in keywords:
            keywords["functionality"] = []
        
        # Populate mrp_source if not set
        if "mrp_source" not in result:
            result["mrp_source"] = "scraped" if scraped_price else "ai_estimated"
        
        # Ensure arrays are lists
        for field in ["active_ingredients", "functional_categories", "application"]:
            if field in result and not isinstance(result[field], list):
                result[field] = []
        
        # Move taxonomy fields from structured_analysis to keywords
        mrp_value = result.get("mrp")
        keywords = result.get("keywords", {})
        
        # Extract taxonomy fields from keywords dict (AI returns them in keywords object)
        # Also check top-level result as fallback for legacy compatibility
        target_area = keywords.get("target_area") or result.pop("target_area", None)
        product_type_id = keywords.get("product_type_id") or result.pop("product_type_id", None)
        concerns = keywords.get("concerns", []) or result.pop("concerns", [])
        benefits = keywords.get("benefits", []) or result.pop("benefits", [])
        price_tier = keywords.get("price_tier") or result.pop("price_tier", None)
        market_positioning = keywords.get("market_positioning", []) or result.pop("market_positioning", [])
        form = keywords.get("form") or result.pop("form", None)
        functional_categories = keywords.get("functional_categories", []) or result.pop("functional_categories", [])
        main_category = keywords.get("main_category") or result.pop("main_category", None)
        subcategory = keywords.get("subcategory") or result.pop("subcategory", None)
        application = keywords.get("application", []) or result.pop("application", [])
        
        # Map legacy fields if taxonomy fields not provided
        if not target_area and main_category:
            target_area = map_category_to_target_area(main_category)
        
        if not product_type_id and subcategory:
            subcategory_lower = subcategory.lower()
            if "serum" in subcategory_lower:
                product_type_id = "serum"
            elif "cleanser" in subcategory_lower:
                product_type_id = "cleanser"
            elif "moisturizer" in subcategory_lower or "cream" in subcategory_lower:
                product_type_id = "moisturizer"
            elif "toner" in subcategory_lower:
                product_type_id = "toner"
            elif "sunscreen" in subcategory_lower or "spf" in subcategory_lower:
                product_type_id = "sunscreen"
            elif "mask" in subcategory_lower:
                product_type_id = "mask"
            elif "shampoo" in subcategory_lower:
                product_type_id = "shampoo"
            elif "conditioner" in subcategory_lower:
                product_type_id = "conditioner"
        
        if not price_tier:
            price_tier = get_price_tier_by_mrp(mrp_value)
        
        # Ensure arrays are lists
        if not isinstance(concerns, list):
            concerns = []
        if not isinstance(benefits, list):
            benefits = []
        if not isinstance(market_positioning, list):
            market_positioning = []
        if not isinstance(functional_categories, list):
            functional_categories = []
        if not isinstance(application, list):
            application = []
        
        # Build keywords object with all taxonomy fields
        # First, ensure form is extracted from keywords if not already set
        if not form:
            form = keywords.get("form")
        
        keywords["form"] = form
        keywords["target_area"] = target_area
        keywords["product_type_id"] = product_type_id
        keywords["concerns"] = concerns
        keywords["benefits"] = benefits
        keywords["price_tier"] = price_tier
        keywords["market_positioning"] = market_positioning
        keywords["functional_categories"] = functional_categories
        keywords["main_category"] = main_category
        keywords["subcategory"] = subcategory
        
        # Update product_formulation to include form if not already there
        if form and form not in keywords.get("product_formulation", []):
            if "product_formulation" not in keywords:
                keywords["product_formulation"] = []
            keywords["product_formulation"].append(form)
        
        # Update functionality to include benefits if not already there
        if benefits:
            if "functionality" not in keywords:
                keywords["functionality"] = []
            for benefit in benefits:
                if benefit not in keywords["functionality"]:
                    keywords["functionality"].append(benefit)
        
        # Additional fallback inference for missing values
        # Infer target_area from form if not set
        # Also check keywords dict for form if form variable is None
        if not form:
            form = keywords.get("form")
        
        if not target_area and form:
            # Most forms are for face unless specified otherwise
            if form in ["serum", "essence", "toner", "ampoule", "cleanser", "exfoliator", "moisturizer", "face_oil", "sunscreen", "mask", "face_mist", "spot_treatment"]:
                target_area = "face"
            elif form in ["shampoo", "conditioner", "hair_mask", "hair_serum", "hair_oil", "scalp_treatment", "hair_spray"]:
                target_area = "hair"
            elif form in ["lip_balm", "lip_scrub", "lip_mask"]:
                target_area = "lips"
            else:
                target_area = "face"  # Default to face
        
        # Infer product_type_id from form if not set
        if not product_type_id and form:
            form_to_product_type = {
                "serum": "serum",
                "essence": "serum",
                "toner": "toner",
                "ampoule": "serum",
                "cleanser": "cleanser",
                "gel": "cleanser" if product_name and "cleanser" in product_name.lower() else "serum",
                "cream": "moisturizer",
                "lotion": "moisturizer",
                "moisturizer": "moisturizer",
                "sunscreen": "sunscreen",
                "mask": "mask",
                "shampoo": "shampoo",
                "conditioner": "conditioner",
                "hair_mask": "hair_mask",
                "hair_serum": "hair_serum",
                "hair_oil": "hair_oil"
            }
            product_type_id = form_to_product_type.get(form, form)
        
        # Infer main_category from target_area if not set
        if not main_category and target_area:
            if target_area == "face":
                main_category = "skincare"
            elif target_area == "hair":
                main_category = "haircare"
            elif target_area == "lips":
                main_category = "lipcare"
            elif target_area in ["body", "hands", "feet"]:
                main_category = "bodycare"
            else:
                main_category = "skincare"  # Default
        
        # Infer subcategory from target_area and product_type_id if not set
        if not subcategory and target_area and product_type_id:
            subcategory = f"{target_area}_{product_type_id}"
        
        # Infer benefits from active ingredients if empty
        active_ingredients_list = result.get("active_ingredients", [])
        if not benefits and active_ingredients_list:
            ingredient_benefits_map = {
                "ceramide": ["barrier_repair", "moisturizing"],
                "hyaluronic": ["hydrating", "plumping"],
                "hyaluronate": ["hydrating", "plumping"],
                "niacinamide": ["brightening", "oil_control", "pore_minimizing"],
                "retinol": ["anti_aging", "anti_wrinkle", "cell_renewal"],
                "vitamin c": ["brightening", "antioxidant"],
                "peptide": ["anti_aging", "firming"],
                "salicylic": ["anti_acne", "exfoliating", "pore_minimizing"],
                "glycolic": ["exfoliating", "brightening"],
                "azelaic": ["anti_acne", "brightening"],
                "zinc": ["anti_acne", "soothing"],
                "glycerin": ["hydrating", "moisturizing"],
                "urea": ["moisturizing", "barrier_repair"],
                "panthenol": ["soothing", "barrier_repair"],
                "allantoin": ["soothing", "barrier_repair"]
            }
            inferred_benefits = set()
            ingredients_lower = " ".join([ai.get("name", "").lower() for ai in active_ingredients_list])
            for ingredient_key, benefit_list in ingredient_benefits_map.items():
                if ingredient_key in ingredients_lower:
                    inferred_benefits.update(benefit_list)
            if inferred_benefits:
                benefits = list(inferred_benefits)
                # Update functionality too
                if "functionality" not in keywords:
                    keywords["functionality"] = []
                for benefit in benefits:
                    if benefit not in keywords["functionality"]:
                        keywords["functionality"].append(benefit)
        
        # Infer concerns from benefits if empty
        if not concerns and benefits:
            benefit_to_concerns = {
                "barrier_repair": ["compromised_barrier", "dryness"],
                "moisturizing": ["dryness", "dehydration"],
                "hydrating": ["dehydration", "dryness"],
                "anti_acne": ["acne", "blackheads", "whiteheads"],
                "pore_minimizing": ["large_pores"],
                "brightening": ["dark_spots", "dullness", "uneven_tone"],
                "anti_aging": ["fine_lines", "wrinkles"],
                "anti_wrinkle": ["wrinkles", "fine_lines"],
                "soothing": ["irritation", "redness"],
                "oil_control": ["excess_sebum", "oiliness"]
            }
            inferred_concerns = set()
            for benefit in benefits:
                if benefit in benefit_to_concerns:
                    inferred_concerns.update(benefit_to_concerns[benefit])
            if inferred_concerns:
                concerns = list(inferred_concerns)
        
        # Update keywords with inferred values
        keywords["target_area"] = target_area
        keywords["product_type_id"] = product_type_id
        keywords["benefits"] = benefits
        keywords["concerns"] = concerns
        keywords["main_category"] = main_category
        keywords["subcategory"] = subcategory
        
        # Clean and normalize keywords (handles MRP normalization)
        cleaned_keywords = clean_keywords(keywords, mrp_value)
        
        # Validate and filter keywords against Formulynx taxonomy
        validated_keywords = validate_and_filter_keywords(cleaned_keywords)
        
        result["keywords"] = validated_keywords
        
        print(f"    ✅ AI Structured Analysis completed")
        
        # Ensure all fields are complete with intelligent fallbacks
        complete_result = ensure_complete_analysis(result, ingredients, product_name, url)
        
        return complete_result
        
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Error parsing AI response as JSON: {e}")
        print(f"    Response was: {content[:200] if 'content' in locals() else 'N/A'}")
        
        # Create fallback result and ensure completeness
        fallback_result = {
            "active_ingredients": [],
            "mrp": None,
            "mrp_per_ml": None,
            "mrp_source": None,
            "form": None,
            "functional_categories": [],
            "main_category": None,
            "subcategory": None,
            "application": [],
            "keywords": {
                "product_formulation": [],
                "mrp": [],
                "application": [],
                "functionality": [],
                "form": None,
                "target_area": None,
                "product_type_id": None,
                "concerns": [],
                "benefits": [],
                "price_tier": None,
                "market_positioning": [],
                "functional_categories": [],
                "main_category": None,
                "subcategory": None
            }
        }
        
        # Ensure all fields are complete with intelligent fallbacks
        complete_result = ensure_complete_analysis(fallback_result, ingredients, product_name, url)
        return complete_result
    except Exception as e:
        print(f"    ⚠️  Error calling Claude AI: {e}")
        import traceback
        traceback.print_exc()
        
        # Create fallback result and ensure completeness
        fallback_result = {
            "active_ingredients": [],
            "mrp": None,
            "mrp_per_ml": None,
            "mrp_source": None,
            "keywords": {
                "product_formulation": [],
                "mrp": [],
                "application": [],
                "functionality": [],
                "form": None,
                "target_area": None,
                "product_type_id": None,
                "concerns": [],
                "benefits": [],
                "price_tier": None,
                "market_positioning": [],
                "functional_categories": [],
                "main_category": None,
                "subcategory": None
            }
        }
        
        # Ensure all fields are complete with intelligent fallbacks
        complete_result = ensure_complete_analysis(fallback_result, ingredients, product_name, url)
        return complete_result
