"""
AI Analysis Functions
====================

AI-powered analysis functions using Claude AI.
Extracted from analyze_inci.py for better modularity.
"""

import os
import json
import re
from typing import List, Dict

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
    total_matched: int
) -> str:
    """
    Use Claude AI to generate a concluding overview of the market research.
    
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

    user_prompt = f"""Generate a comprehensive market research overview based on the following data:

INPUT PRODUCT INGREDIENTS:
{chr(10).join(f"- {ing}" for ing in input_ingredients[:20])}

CATEGORY ANALYSIS:
- Primary Category: {category_info.get('primary_category', 'Unknown')}
- Subcategory: {category_info.get('subcategory', 'Unknown')}
- Interpretation: {category_info.get('interpretation', 'N/A')}

MATCHED PRODUCTS ({total_matched} total, showing top {len(product_summaries)}):
{json.dumps(product_summaries, indent=2)}

TASK:
Generate a comprehensive market research overview that includes:
1. Summary of the research
2. Key findings about the market
3. Product trends and patterns
4. Market insights
5. Recommendations

Make it insightful, professional, and actionable."""

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

