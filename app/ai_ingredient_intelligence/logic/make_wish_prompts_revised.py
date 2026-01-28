"""
Revised Make A Wish AI Prompts (January 2025)
=============================================

This module contains all the AI prompts for the revised Make A Wish pipeline,
including natural language parsing, ingredient selection with complexity,
and insights generation.
"""

# ============================================================================
# STAGE 1: PARSE WISH PROMPT
# ============================================================================

PARSE_WISH_PROMPT = """
Parse this cosmetic wish and return JSON:

Wish: {wish_text}

Return ONLY valid JSON with this structure:
{{
    "category": "skincare",
    "product_type": {{
        "id": "serum",
        "name": "Serum",
        "icon": "flask",
        "confidence": 0.95
    }},
    "detected_ingredients": [
        {{"name": "Vitamin C", "confidence": 0.9, "has_alternatives": true}}
    ],
    "detected_benefits": ["brightening"],
    "detected_exclusions": ["paraben-free"],
    "detected_skin_types": [],
    "detected_hair_concerns": [],
    "auto_texture": {{
        "id": "watery",
        "label": "Light & Fast-Absorbing",
        "auto_selected": true
    }},
    "needs_clarification": [],
    "compatibility_issues": []
}}

Analyze the wish and fill in actual values. Return only JSON.
"""

# ============================================================================
# STAGE 2: INGREDIENT SELECTION WITH COMPLEXITY
# ============================================================================

INGREDIENT_SELECTION_COMPLEXITY_PROMPT = """
Select {max_ingredients} ingredients for {complexity} {product_type} with {active_slots} hero actives.

Requirements: {benefits}, {exclusions}, {texture}
Base: {base_ingredients}

Return JSON:
{{
    "selected_ingredients": [
        {{
            "id": "vitamin_c",
            "inci_name": "Ascorbic Acid",
            "display_name": "Vitamin C",
            "icon": "flask",
            "percentage_range": "10-15%",
            "phase": "C",
            "purpose": "brightening",
            "is_hero": true,
            "is_base": false,
            "has_alternatives": true
        }}
    ],
    "selection_summary": {{
        "total_ingredients": {max_ingredients},
        "hero_actives": {active_slots},
        "complexity_compliance": true
    }}
}}

Be concise.
"""

# ============================================================================
# STAGE 3: FORMULA OPTIMIZATION (REVISED)
# ============================================================================

FORMULA_OPTIMIZATION_REVISED_PROMPT = """
Optimize {product_type} ({texture}) formula to 100%:

{ingredients_list}

Rules: Total 100%, Water 60-80%, Preservative 1%, pH adjuster 0.2%

Return JSON:
{{
    "optimized_formula": {{
        "name": "Formula Name",
        "complexity": "{complexity}",
        "total_percentage": 100.0
    }},
    "ingredients": [
        {{
            "id": "water",
            "name": "Water",
            "inci": "Aqua",
            "percentage": "70.00%",
            "phase": "A",
            "function": "solvent",
            "is_hero": false,
            "is_base": true
        }}
    ]
}}

Be fast.
"""

# ============================================================================
# STAGE 4: INSIGHTS GENERATION (NEW)
# ============================================================================

INSIGHTS_GENERATION_PROMPT = """
Generate insights for {formula_name} ({product_type}) with {complexity} complexity.

Key ingredients: {key_ingredients}
Benefits: {benefits}

Return JSON:
{{
    "why_these_ingredients": [
        {{
            "ingredient_name": "Ingredient Name",
            "icon": "flask",
            "explanation": "Why chosen",
            "complexity_reason": "Why for {complexity}"
        }}
    ],
    "challenges": [
        {{
            "title": "Challenge Title",
            "icon": "alert-triangle",
            "description": "What to expect",
            "tip": "How to handle",
            "severity": "info|attention"
        }}
    ],
    "marketing_tips": [
        {{
            "title": "Tip Title",
            "icon": "lightbulb",
            "content": "Actionable advice",
            "category": "positioning|pricing|targeting"
        }}
    ],
    "faq": [
        {{
            "question": "Common question",
            "answer": "Clear answer"
        }}
    ]
}}

Be practical and marketing-focused.
"""

# ============================================================================
# STAGE 5: ALTERNATIVES ANALYSIS
# ============================================================================

ALTERNATIVES_ANALYSIS_PROMPT = """
Analyze alternatives for {ingredient_name} in {product_type} ({complexity} complexity).

Current: {current_variant}
Available alternatives:
{alternatives_list}

Return JSON:
{{
    "current_analysis": {{
        "name": "{current_variant}",
        "inci": "INCI Name",
        "icon": "flask",
        "description": "Current ingredient description",
        "benefit_tag": "Key benefit",
        "suggested_percentage": "X-X%",
        "cost_impact": "baseline",
        "complexity_fit": ["{complexity}"]
    }},
    "alternatives": [
        {{
            "name": "Alternative Name",
            "inci": "INCI Name",
            "icon": "leaf",
            "description": "Description",
            "benefit_tag": "Unique benefit",
            "suggested_percentage": "X-X%",
            "cost_impact": "higher|similar|lower",
            "complexity_fit": ["complexity1", "complexity2"],
            "considerations": "Usage notes"
        }}
    ],
    "recommendation": {{
        "best_alternative": "Alternative Name",
        "reasoning": "Why best choice"
    }}
}}

Focus on practical formulation considerations.
"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_ingredients_list(ingredients):
    """Format ingredients for prompt"""
    return "\n".join([
        f"- {ing.get('display_name', ing.get('name', 'Unknown'))} ({ing.get('inci_name', 'Unknown')})\n"
        f"  Purpose: {ing.get('purpose', 'Unknown')}\n"
        f"  Range: {ing.get('percentage_range', 'Unknown')}\n"
        f"  Phase: {ing.get('phase', 'Unknown')}\n"
        f"  Hero: {ing.get('is_hero', False)}"
        for ing in ingredients
    ])

def format_alternatives_list(alternatives):
    """Format alternatives for prompt"""
    return "\n".join([
        f"- {alt.get('name', 'Unknown')}\n"
        f"  INCI: {alt.get('inci', 'Unknown')}\n"
        f"  Benefit: {alt.get('benefit', 'Unknown')}\n"
        f"  Percentage: {alt.get('percentage', 'Unknown')}\n"
        f"  Cost: {alt.get('cost_tier', 'Unknown')}\n"
        f"  Complexities: {', '.join(alt.get('complexity', []))}"
        for alt in alternatives
    ])
