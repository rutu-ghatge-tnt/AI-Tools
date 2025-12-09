"""
Utility functions for parsing INCI ingredient lists with various separators
"""
import re
from typing import List, Union


def parse_inci_string(inci_input: Union[str, List[str]]) -> List[str]:
    """
    Parse INCI ingredient input into a list of individual ingredients.
    Handles ALL possible separators: comma, semicolon, pipe, hyphen, "and", "&", newline
    
    Args:
        inci_input: Can be:
            - A string with ingredients separated by various delimiters
            - A list of strings (each may contain multiple ingredients)
            - A list of already-separated ingredients
    
    Returns:
        List of cleaned ingredient names
    
    Examples:
        parse_inci_string("Water, Glycerin, Sodium Hyaluronate")
        -> ["Water", "Glycerin", "Sodium Hyaluronate"]
        
        parse_inci_string("Water | Glycerin | Sodium Hyaluronate")
        -> ["Water", "Glycerin", "Sodium Hyaluronate"]
        
        parse_inci_string("Water and Glycerin and Sodium Hyaluronate")
        -> ["Water", "Glycerin", "Sodium Hyaluronate"]
        
        parse_inci_string(["Water, Glycerin", "Sodium Hyaluronate"])
        -> ["Water", "Glycerin", "Sodium Hyaluronate"]
    """
    if not inci_input:
        return []
    
    # If input is a list, join with comma first, then parse
    if isinstance(inci_input, list):
        # Join list items, but also parse each item in case it contains separators
        all_ingredients = []
        for item in inci_input:
            if isinstance(item, str) and item.strip():
                # Parse each item individually
                parsed = _parse_single_string(item)
                all_ingredients.extend(parsed)
        return all_ingredients
    
    # If input is a string, parse it
    if isinstance(inci_input, str):
        return _parse_single_string(inci_input)
    
    return []


def _parse_single_string(inci_str: str) -> List[str]:
    """
    Parse a single INCI string into list of ingredients.
    Handles all separators: comma, semicolon, pipe, hyphen, "and", "&", newline
    
    Special handling: When other separators (comma, pipe, etc.) are present,
    "(and)" or "&" within combinations indicates ingredient combinations that should
    be kept together as single items for MongoDB INCI combo searches.
    """
    if not inci_str or not inci_str.strip():
        return []
    
    # Check if there are other separators (comma, semicolon, pipe, newline) in the input
    # If yes, then "(and)" or "&" indicates combinations that should be preserved
    has_other_separators = bool(re.search(r'[,;\n|]', inci_str))
    
    if has_other_separators:
        # Other separators exist - treat "(and)", "and", and "&" as combination indicators
        # First, protect combinations that use "(and)", "and", or "&" by replacing them with placeholders
        normalized = inci_str
        combinations = []
        combination_counter = 0
        
        # Find and protect all combinations
        def protect_combination(match):
            nonlocal combination_counter
            # Get the full match including all parts
            full_match = match.group(0)
            placeholder = f"__COMBINATION_{combination_counter}__"
            combinations.append(full_match.strip())
            combination_counter += 1
            return placeholder
        
        # Strategy: Find all potential combinations by looking for patterns between separators
        # A combination is: "Ingredient1 (and) Ingredient2 (and) Ingredient3" or similar
        # We need to match the entire combination including all parts
        
        # Pattern 1: Match combinations with "(and)" - case insensitive
        # Matches: "Xylitylglucoside (and) Anhydroxylitol (and) Xylitol"
        # This pattern matches one or more ingredients connected by "(and)"
        pattern_and_paren = r'[^,;\n|]+(?:\s*\(and\)\s*[^,;\n|]+)+'
        
        # Pattern 2: Match combinations with "&" when other separators exist
        # Matches: "Acacia Senegal Gum & Xanthan Gum"
        # Only match if it's between other separators (comma, semicolon, pipe, etc.)
        pattern_ampersand = r'[^,;\n|]+(?:\s+&\s+[^,;\n|]+)+'
        
        # Pattern 3: Match combinations with "and" (without parentheses) when other separators exist
        # Matches: "Ingredient1 and Ingredient2 and Ingredient3"
        # Only when other separators are present
        pattern_and_word = r'[^,;\n|]+(?:\s+and\s+[^,;\n|]+)+'
        
        # Protect combinations in order of specificity (most specific first)
        # First protect "(and)" combinations
        normalized = re.sub(pattern_and_paren, protect_combination, normalized, flags=re.IGNORECASE)
        
        # Then protect "&" combinations (only those not already protected)
        normalized = re.sub(pattern_ampersand, protect_combination, normalized)
        
        # Finally protect "and" word combinations (only those not already protected)
        normalized = re.sub(pattern_and_word, protect_combination, normalized, flags=re.IGNORECASE)
        
        # Now split by other separators (comma, semicolon, pipe, newline, hyphen with spaces)
        # CRITICAL: Only split on commas followed by space or at end of string, not commas in ingredient names (e.g., "1,2-Hexanediol")
        ingredients = re.split(r'(?:,\s+|,\s*$|[;\n|]+|\s+-\s+)', normalized)
        
        # Restore combinations and clean
        result = []
        for ing in ingredients:
            ing = ing.strip()
            if not ing:
                continue
            
            # Check if this is a placeholder
            match = re.match(r'__COMBINATION_(\d+)__', ing)
            if match:
                idx = int(match.group(1))
                if idx < len(combinations):
                    result.append(combinations[idx])
            else:
                result.append(ing)
        
        return result if result else [inci_str.strip()] if inci_str.strip() else []
    
    else:
        # No other separators - treat "and" and "&" as regular separators
        normalized = inci_str
        
        # Replace " and " (with spaces) - case insensitive
        normalized = re.sub(r'\s+and\s+', ',', normalized, flags=re.IGNORECASE)
        
        # Replace " & " (with spaces)
        normalized = re.sub(r'\s+&\s+', ',', normalized)
        
        # Replace standalone & without spaces (but be careful not to break things like "A&B")
        # Only replace & when it's clearly a separator (surrounded by word boundaries or spaces)
        normalized = re.sub(r'(?<=\w)\s*&\s*(?=\w)', ',', normalized)
        
        # Split by multiple delimiters:
        # - Comma (,) only when followed by space or at end of string (not in ingredient names like "1,2-Hexanediol")
        # - Semicolon (;)
        # - Pipe (|)
        # - Newline (\n)
        # - Hyphen (-) when used as separator (with spaces around it, like "Water - Glycerin")
        #   Only split on hyphens that have spaces around them to avoid splitting ingredient names like "Alpha-Hydroxy Acid"
        ingredients = re.split(r'(?:,\s+|,\s*$|[;\n|]+|\s+-\s+)', normalized)
        
        # Clean and filter
        ingredients = [ing.strip() for ing in ingredients if ing.strip()]
        
        # Remove empty strings
        ingredients = [ing for ing in ingredients if ing]
        
        # If no separators found, return the whole string as single ingredient
        if not ingredients:
            ingredients = [inci_str.strip()] if inci_str.strip() else []
        
        return ingredients


def normalize_ingredient_name(name: str) -> str:
    """
    Normalize an ingredient name for comparison.
    Removes extra whitespace and normalizes common variations.
    """
    if not name:
        return ""
    
    # Remove leading/trailing whitespace
    normalized = name.strip()
    
    # Normalize multiple spaces to single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized

